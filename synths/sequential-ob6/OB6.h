/*
   Copyright (c) 2020 Christof Ruch. All rights reserved.

   Dual licensed: Distributed under Affero GPL license by default, an MIT license is available for purchase
*/

#pragma once

#include "DSI.h"
#include "GlobalSettingsCapability.h"

namespace midikraft {

	class OB6 : public DSISynth, public DataFileLoadCapability, public GlobalSettingsCapability,
		private Value::Listener 
	{
	public:
		enum DataType {
			PATCH = 0,
			GLOBAL_SETTINGS = 1,
			ALTERNATE_TUNING = 2
		};

		OB6();

		virtual std::string getName() const override;
		virtual int numberOfBanks() const override;
		virtual int numberOfPatches() const override;
		std::string friendlyBankName(MidiBankNumber bankNo) const;


		virtual std::shared_ptr<Patch> patchFromSysex(const MidiMessage& message) const override;
		virtual std::shared_ptr<DataFile> patchFromPatchData(const Synth::PatchData &data, std::string const &name, MidiProgramNumber place) const override;

		virtual PatchData filterVoiceRelevantData(std::shared_ptr<DataFile> unfilteredData) const override;
		virtual std::vector<MidiMessage> patchToSysex(const Patch &patch) const override;

		virtual std::shared_ptr<Patch> patchFromProgramDumpSysex(const MidiMessage& message) const override;
		virtual std::vector<MidiMessage> patchToProgramDumpSysex(const Patch &patch) const override;

		// It should not be necessary to override these two, but somehow I don't see the Sysex output for the device inquiry by the OB-6
		virtual MidiMessage deviceDetect(int channel) override;
		virtual MidiChannel channelIfValidDeviceResponse(const MidiMessage &message) override;

		// SoundExpanderCapability
		virtual void changeInputChannel(MidiController *controller, MidiChannel channel, std::function<void()> onFinished) override;
		virtual void setMidiControl(MidiController *controller, bool isOn) override;

		// MasterkeyboardCapability
		virtual void changeOutputChannel(MidiController *controller, MidiChannel channel, std::function<void()> onFinished) override;
		virtual void setLocalControl(MidiController *controller, bool localControlOn) override;

		// DataFileLoadCapability
		virtual std::vector<MidiMessage> requestDataItem(int itemNo, int dataTypeID) override;
		virtual int numberOfDataItemsPerType(int dataTypeID) const override;
		virtual bool isDataFile(const MidiMessage &message, int dataTypeID) const override;
		virtual std::vector<std::shared_ptr<DataFile>> loadData(std::vector<MidiMessage> messages, int dataTypeID) const override;
		virtual std::vector<DataFileDescription> dataTypeNames() const override;

		// GlobaSettingsCapability
		virtual void setGlobalSettingsFromDataFile(std::shared_ptr<DataFile> dataFile) override;
		virtual std::vector<std::shared_ptr<TypedNamedValue>> getGlobalSettings() override;
		virtual DataFileLoadCapability *loader() override;
		virtual int settingsDataFileType() const override;

	private:
		void initGlobalSettings();
		MidiMessage requestGlobalSettingsDump() const;
		bool isGlobalSettingsDump(MidiMessage const &message) const;

		virtual void valueChanged(Value& value) override;

		std::vector<std::shared_ptr<TypedNamedValue>> globalSettings_;
	};

}
