/*
   Copyright (c) 2020 Christof Ruch. All rights reserved.

   Dual licensed: Distributed under Affero GPL license by default, an MIT license is available for purchase
*/

#include "SetupView.h"

#include "Synth.h"
#include "MidiChannelPropertyEditor.h"
#include "SoundExpanderCapability.h"
#include "Logger.h"
#include "AutoDetection.h"
#include "Settings.h"
#include "GenericAdaption.h"
#include "CreateNewAdaptionDialog.h"
#include "AutoDetectProgressWindow.h"
#include "LoopDetection.h"


#include "UIModel.h"

#include "ColourHelpers.h"

#include <boost/format.hpp>
#include <algorithm>

SetupView::SetupView(midikraft::AutoDetection *autoDetection /*, HueLightControl *lights*/) :
	autoDetection_(autoDetection)/*, lights_(lights) */,
	functionButtons_(1501, LambdaButtonStrip::Direction::Horizontal)
{
	// We have two lists: One is the list of synths, where you just activate and deactivate them, and the second is the detail list which shows the
	// individual synths setup
	std::vector<std::string> sortedList;
	for (auto &synth : UIModel::instance()->synthList_.allSynths()) {
		if (!synth.device()) continue;
		sortedList.push_back(synth.getName());
	}
	std::sort(sortedList.begin(), sortedList.end());

	for (auto &synth : sortedList) {
		sortedSynthList_.push_back(UIModel::instance()->synthList_.synthByName(synth));
		synths_.push_back(std::make_shared<TypedNamedValue>(sortedSynthList_.back().getName(), "Activate support for synth", true));
	}

	// We need to know if any of these are clicked
	for (auto prop : synths_) prop->value().addListener(this);
	rebuildSetupColumn();
	refreshSynthActiveness();
	header_.setText("In case the auto-detection fails, setup the MIDI channel and MIDI interface below to get your synths detected.\n\n"
		"This can *not* be used to change the synth's channel, but rather in case the autodetection fails you can manually enter the correct channel here.");
	addAndMakeVisible(header_);
	addAndMakeVisible(synthSelection_);
	synthSelection_.setProperties(synths_);
	addAndMakeVisible(synthSetup_);
	synthSetup_.setProperties(properties_);

	// Define function buttons
	functionButtons_.setButtonDefinitions({
			{ "autoDetect", {0, "Auto-Configure", [this]() {
				autoDetect();
			} } },
			{ "synthDetection", {1, "Quick check connectivity", [this]() {
				quickConfigure();
			} } },
			{ "loopDetection", {2, "Check for MIDI loops", [this]() {
				loopDetection();
			} } },
			{"selectAdaptionDirectory", {3, "Set User Adaption Dir", [this]() {
				FileChooser directoryChooser("Please select the directory to store your user adaptions...", File(knobkraft::GenericAdaption::getAdaptionDirectory()));
				if (directoryChooser.browseForDirectory()) {
					knobkraft::GenericAdaption::setAdaptionDirectoy(directoryChooser.getResult().getFullPathName().toStdString());
					juce::AlertWindow::showMessageBox(AlertWindow::InfoIcon, "Restart required", "Your new adaptions directory will only be used after a restart of the application!");
				}
			} } },
			{"createNewAdaption", {4, "Create new adaption", [this]() {
				knobkraft::CreateNewAdaptionDialog::showDialog(&synthSetup_);
			} } }
		});
	addAndMakeVisible(functionButtons_);

	UIModel::instance()->currentSynth_.addChangeListener(this);
}

SetupView::~SetupView() {
	UIModel::instance()->currentSynth_.removeChangeListener(this);
}

void SetupView::resized() {
	Rectangle<int> area(getLocalBounds());

	int width = std::min(area.getWidth(), 600);
	functionButtons_.setBounds(area.removeFromBottom(40).reduced(8));
	header_.setBounds(area.removeFromTop(100).withSizeKeepingCentre(width, 100).reduced(8));

	// Two column setup, don't go to wide, I don't need more than 1000 pixels
	int setupWidth = std::min(area.getWidth(), 1000);
	synthSelection_.setBounds(area.removeFromLeft(area.getWidth() / 2).removeFromRight(setupWidth/2).reduced(8));
	synthSetup_.setBounds(area.removeFromLeft(setupWidth/2));
}

void SetupView::setValueWithoutListeners(Value &value, int newValue) {
	value.removeListener(this);
	value.setValue(newValue);
	value.addListener(this);
}

void SetupView::rebuildSetupColumn() {
	// Cleanup
	for (auto prop : properties_) prop->value().removeListener(this);
	properties_.clear();

	// Rebuild
	for (auto &synth: sortedSynthList_) {
		if (!UIModel::instance()->synthList_.isSynthActive(synth.device())) continue;
		auto sectionName = synth.getName();
		// For each synth, we need 3 properties, and we need to listen to changes: 
		properties_.push_back(std::make_shared<MidiDevicePropertyEditor>("Sent to device", sectionName, false));
		properties_.push_back(std::make_shared<MidiDevicePropertyEditor>("Receive from device", sectionName, true));
		properties_.push_back(std::make_shared<MidiChannelPropertyEditor>("MIDI channel", sectionName));
	}
	// We need to know if any of these are clicked
	for (auto prop : properties_) prop->value().addListener(this);

	synthSetup_.setProperties(properties_);
	refreshData();
}

void SetupView::refreshSynthActiveness() {
	int synthCount = 0;
	for (auto &synth : sortedSynthList_) {
		// Skip the active prop
		setValueWithoutListeners(synths_[synthCount++]->value(), UIModel::instance()->synthList_.isSynthActive(synth.device()));
	}
}

void SetupView::refreshData() {
	int prop = 0;
	
	for (auto &synth : UIModel::instance()->synthList_.allSynths()) {
		if (!synth.device()) continue;
		if (!UIModel::instance()->synthList_.isSynthActive(synth.device())) continue;
		// Load
		midikraft::AutoDetection::loadSettings(synth.device().get());
		// Set output, input, and channel
		setValueWithoutListeners(properties_[prop]->value(), properties_[prop]->indexOfValue(synth.device()->midiOutput()));
		prop++;
		setValueWithoutListeners(properties_[prop]->value(), properties_[prop]->indexOfValue(synth.device()->midiInput()));
		prop++;
		if (!synth.device()->channel().isValid()) {
			setValueWithoutListeners(properties_[prop++]->value(), 18);
		}
		else if (synth.device()->channel().isOmni()) {
			setValueWithoutListeners(properties_[prop++]->value(), 17);
		}
		else {
			setValueWithoutListeners(properties_[prop++]->value(), synth.device()->channel().toOneBasedInt());
		}
	}
}

void SetupView::valueChanged(Value& value)
{
	// Determine the property that was changed, first search in the synth activation properties, and then in the synth setup properties
	for (auto prop : synths_) {
		if (prop->value().refersToSameSourceAs(value)) {
			auto synthFound = UIModel::instance()->synthList_.synthByName(prop->name().toStdString());
			if (synthFound.device()) {
				UIModel::instance()->synthList_.setSynthActive(synthFound.device().get(), value.getValue());
				auto activeKey = String(synthFound.getName()) + String("-activated");
				Settings::instance().set(activeKey.toStdString(), value.getValue().toString().toStdString());
				autoDetection_->persistSetting(synthFound.device().get());
				rebuildSetupColumn();
				return;
			}
			else {
				jassertfalse;
			}
		}
	}
	for (auto prop : properties_) {
		if (prop->value().refersToSameSourceAs(value)) {
			auto synthFound = UIModel::instance()->synthList_.synthByName(prop->sectionName().toStdString());
			if (synthFound.device()) {
				if (prop->name() == "Sent to device") {
					synthFound.device()->setOutput(prop->lookup()[value.getValue()]);
				}
				else if (prop->name() == "Receive from device") {
					synthFound.device()->setInput(prop->lookup()[value.getValue()]);
				}
				else if (prop->name() == "MIDI channel") {
					synthFound.device()->setChannel(MidiChannel::fromOneBase(value.getValue()));
				}
				else if (prop->name() == "Activated") {
					UIModel::instance()->synthList_.setSynthActive(synthFound.device().get(), value.getValue());
					auto activeKey = String(synthFound.getName()) + String("-activated");
					Settings::instance().set(activeKey.toStdString(), value.getValue().toString().toStdString());
				}
				else {
					// New property? Implement handler here
					jassertfalse;
				}
				autoDetection_->persistSetting(synthFound.device().get());
				/*timedAction_.callDebounced([this]() {
					quickConfigure();
				}, 1000);*/
				return;
			}
			else {
				jassertfalse;
			}
		}
	}
}

void SetupView::changeListenerCallback(ChangeBroadcaster* source)
{
	ignoreUnused(source);
	refreshSynthActiveness();
	refreshData();
	/*// Find out which of the color selectors sent this message
	for (int i = 0; i < colours_.size(); i++) {
		if (colours_[i] == source) {
			auto newColour = colours_[i]->getCurrentColour();
			// Set the colour to our lights
			//lights_->setStudioLight(HueLightState(newColour), 0);
			// Persist the new colour in the synth
			//synths_[i].setColor(newColour);
		}
	}*/
}

void SetupView::quickConfigure()
{
	auto currentSynths = UIModel::instance()->synthList_.activeSynths();
	autoDetection_->quickconfigure(currentSynths); // This rather should be synchronous!
	refreshData();
}

class LoopDetectorWindow : public ProgressHandlerWindow, public std::enable_shared_from_this<LoopDetectorWindow> {
public:
	LoopDetectorWindow() : ProgressHandlerWindow("Checking for MIDI loops...", "Sending test messages to all MIDI outputs to detect if we have a loop in the configuration") {
	}

	virtual void run() override {
		// Call the method that will block
		loops = midikraft::LoopDetection::detectLoops(shared_from_this());
	}

	std::vector<midikraft::MidiLoop> loops;
};

void SetupView::loopDetection()
{
	std::shared_ptr<LoopDetectorWindow> modalWindow = std::make_shared<LoopDetectorWindow>();
	modalWindow->runThread();
	for (auto loop : modalWindow->loops) {
		std::string typeName;
		switch (loop.type) {
		case midikraft::MidiLoopType::Note: typeName = "MIDI Note"; break;
		case midikraft::MidiLoopType::Sysex: typeName = "Sysex"; break;
		}
		SimpleLogger::instance()->postMessage((boost::format("Warning: %s loop detected. Sending sysex to %s is returned on %s") % typeName % loop.midiOutput % loop.midiInput).str());
	}
	if (modalWindow->loops.empty()) {
		SimpleLogger::instance()->postMessage("All clear, no MIDI loops detected when sending to all available MIDI outputs");
	}
}

void SetupView::autoDetect() {
	auto currentSynths = UIModel::instance()->synthList_.activeSynths();
	AutoDetectProgressWindow window(currentSynths);
	if (window.runThread()) {
		refreshData();
	}
}
