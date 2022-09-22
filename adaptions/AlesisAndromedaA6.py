#
#   Copyright (c) 2021 Christof Ruch. All rights reserved.
#
#   Dual licensed: Distributed under Affero GPL license by default, an MIT license is available for purchase
#
import hashlib


def name():
    return "Alesis Andromeda A6"


def createDeviceDetectMessage(channel):
    # The A6 replies to Universal Device Inquiry, p. 6 of the "Sysex specs" document
    return [0xf0, 0x7e, 0x7f, 0x06, 0x01, 0xf7]


def deviceDetectWaitMilliseconds():
    return 500


def needsChannelSpecificDetection():
    return False


def channelIfValidDeviceResponse(message):
    # Check for reply on Universal Device Inquiry
    if len(message) > 12 and message[:12] == [0xf0, 0x7e, 0x7f, 0x06, 0x02, 0x00, 0x00, 0x0e, 0x1d, 0x00, 0x00, 0x00]:
        # Just return any valid channel
        return 0x00
    return -1


def numberOfBanks():
    return 16


def numberOfPatchesPerBank():
    return 128


# Implementation for Edit Buffer commented out because there seems to be a bug that the edit buffer does indeed not work
# https://www.gearslutz.com/board/showpost.php?p=15188863&postcount=623
def createEditBufferRequest(channel):
    #    # Sysex documentation specifies an edit buffer exists
    #    # Edit buffer #16 (decimal) is called the program edit buffer
    #    # MS from https://electro-music.com/forum/viewtopic.php?t=59282
    #    # When you send a program edit buffer dump request (F0 00
    #    # 00 0E 1D 03 10 F7) to an Andromeda, you get in return a
    #    # program edit buffer dump (F0 00 00 0E 1D 02 10 <2341 bytes> F7).
    return [0xf0, 0x00, 0x00, 0x0e, 0x1d, 0x03, 0x10, 0xf7]


def isEditBufferDump(message):
    return len(message) > 6 and message[:7] == [0xf0, 0x00, 0x00, 0x0e, 0x1d, 0x02, 0x10]  # from chris on gh forum


def convertToEditBuffer(channel, message):  # from chris on gh
    bank = 0
    program = numberOfPatchesPerBank() - 1
    if isEditBufferDump(message):
        return [0xf0, 0x00, 0x00, 0x0e, 0x1d, 0x00, bank, program] + message[7:] + [0xc0 | (channel % 0x7f), program]
    if isSingleProgramDump(message):
        # We just need to adjust bank and program and position 6 and 7
        return message[:6] + [bank, program] + message[8:] + [0xc0 | (channel % 0x7f), program]
    raise Exception("Can only create program dumps from master keyboard dumps")


def createProgramDumpRequest(channel, program_number):
    bank = program_number // numberOfPatchesPerBank()
    program = program_number % numberOfPatchesPerBank()
    return [0xF0, 0x00, 0x00, 0x0E, 0x1D, 0x01, bank, program, 0xf7]


def isSingleProgramDump(message):
    return len(message) > 5 and message[:6] == [0xF0, 0x00, 0x00, 0x0E, 0x1D, 0x00]


def convertToProgramDump(channel, message, program_number):
    bank = program_number // numberOfPatchesPerBank()
    program = program_number % numberOfPatchesPerBank()
    if isEditBufferDump(message):
        return [0xF0, 0x00, 0x00, 0x0E, 0x1D, 0x00, bank, program] + message[7:]
    if isSingleProgramDump(message):
        # We just need to adjust bank and program and position 6 and 7, should there be an extra program change skip it
        f7 = rindex(message, 0xf7)
        return message[:6] + [bank, program] + message[8:f7 + 1]
    raise Exception("Can only create program dumps from master keyboard dumps")


def nameFromDump(message):
    if isSingleProgramDump(message):
        data_block = unescapeSysex(message[8:-1])  # The data block starts at index 8, and does not include the 0xf7
        return ''.join([chr(x) for x in data_block[2:2 + 16]])
    if isEditBufferDump(message):
        data_block = unescapeSysex(message[7:-1])
        return ''.join([chr(x) for x in data_block[2:2 + 16]])
    raise Exception("Can only extract name from master keyboard program dump")


def numberFromDump(message):
    if isSingleProgramDump(message):
        bank = message[6]
        program = message[7]
        return bank * numberOfPatchesPerBank() + program
    if isEditBufferDump(message):
        return 0
    raise Exception("Can only extract number from single program dumps")


def renamePatch(message, new_name):
    if isSingleProgramDump(message) or isEditBufferDump(message):
        data_block = unescapeSysex(getDataBlock(message))
        for i in range(16):
            if i < len(new_name):
                data_block[2 + i] = ord(new_name[i])
            else:
                data_block[2 + i] = ord(" ")
        if isSingleProgramDump(message):
            return message[:8] + escapeSysex(data_block) + [0xf7]
        elif isEditBufferDump(message):
            return message[:7] + escapeSysex(data_block) + [0xf7]
    raise Exception("Can only rename single program dumps!")


def createBankDumpRequest(channel, bank):
    # Page 4 of the sysex spec
    return [0xf0, 0x00, 0x00, 0x0e, 0x1d, 0x0a, bank, 0xf7]


def isPartOfBankDump(message):
    # A bank dump on the A6 consists of 128 single dumps
    return isSingleProgramDump(message)


def isBankDumpFinished(messages):
    count = 0
    for message in messages:
        if isPartOfBankDump(message):
            count = count + 1
    return count == numberOfPatchesPerBank()


def extractPatchesFromBank(message):
    if isSingleProgramDump(message):
        return message
    raise Exception("Only Single Program dumps are expected to be part of a bank dump")


def calculateFingerprint(message):
    if isSingleProgramDump(message) or isEditBufferDump(message):
        data_block = unescapeSysex(getDataBlock(message))
        # Blank out name
        data_block[2:2 + 16] = [0] * 16
        return hashlib.md5(bytearray(data_block)).hexdigest()  # Calculate the fingerprint from the cleaned payload data
    # Don't know why we should come here, but to be safe, just hash all bytes
    return hashlib.md5(bytearray(message)).hexdigest()


def getDataBlock(message):
    if isSingleProgramDump(message):
        return message[8:rindex(message, 0xf7)]  # The data block starts at index 8, and does not include the 0xf7
    if isEditBufferDump(message):
        f7 = rindex(message, 0xf7)
        return message[7:f7]
    raise Exception("Only single programs and edit buffers have a data block that can be extracted!")


def friendlyBankName(bank):
    return ["User", "Preset1", "Preset2", "Card 1", "Card 2", "Card 3", "Card 4", "Card 5", "Card 6", "Card 7",
            "Card 8", "Card 9", "Card 10", "Card 11", "Card 12", "Card 13"][bank]


def friendlyProgramName(patchNo):
    bank = patchNo // numberOfPatchesPerBank()
    program = patchNo % numberOfPatchesPerBank()
    return friendlyBankName(bank) + " %03d" % program


def unescapeSysex(data):
    # The A6 uses the shift technique to store 8 bits in 7 bit bytes. This is some particularly ugly code I could only
    # get to work with the help of the tests
    result = []
    roll_over = 0
    i = 0
    while i < len(data) - 1:
        mask1 = (0xFF << roll_over) & 0x7F
        mask2 = 0xFF >> (7 - roll_over)
        result.append((data[i] & mask1) >> roll_over | (data[i + 1] & mask2) << (7 - roll_over))
        roll_over = (roll_over + 1) % 7
        i = i + 1
        if roll_over == 0:
            i = i + 1
    return result


def escapeSysex(data):
    result = []
    roll_over = 7
    previous = 0
    i = 0
    while i < len(data):
        mask1 = 0xFF >> (8 - roll_over)
        mask2 = 0xFF >> roll_over << roll_over
        if mask1 > 0:
            result.append(((data[i] & mask1) << (7 - roll_over)) | previous)
            previous = (data[i] & mask2) >> roll_over
            roll_over = roll_over - 1
            i = i + 1
        else:
            result.append(previous)
            previous = 0
            roll_over = 7
    result.append(previous)
    return result


def rindex(mylist, myvalue):
    return len(mylist) - mylist[::-1].index(myvalue) - 1


import binascii


def bitsSet(byte):
    count = 0
    for i in range(8):
        if (byte >> i) & 0x01 == 0x01:
            count = count + 1
    return count


# Test data picked up by test_adaptation.py
def test_data():
    def programs(messages):
        single_program = "F000000E1D00000026150812172C1A3720020D23174D5D347472010172003C0000364014000400000001780105000040003800010000000000000000000000000000000000000000000038010E0000000000000000000000000000000000405240164336460C200040507C795F067C1F7F31400108000000000138010E6001000C000000002048030016000002041400007E7D3F102000000000000000000000000000080009030005000000000000000000000000605F7F010004080000000000000000000000007F7E07001020000000000000000000000000043844014002000000000000000000000000706F7F000002040000000000000000000000403F7F030008100000000000000000000000007E7D0F00204000000000000000000000000078773F000001020000000000000000000000605F7F010004080000000000000000000000007F7E070010200000000000000000000000007C7B1F00400001000000000000007A410000706F7F070002000000000000000018020800403F7F1F00080000000000000000501D3400007E7D6F00200000000000000000000000000078773F000001020000000000000022400100605F7F030004000000000000000060011800007F7E3F00100000000000000000203C7800007C7B7F214000000000000000000000000000706F7F00000204000000000000007C7B0F00403F7F0700081000000000000000400A3400007E7D4F00200000000000000000000000000078773F000001020000000000000000000000605F7F010004080000000000000000000000007F7E070010200000000000000000000000007C7B1F004000010000000000000000000000706F7F000102040000000000000000000000403F7F030008100000000000000000000000007E7D0F00204000000000000000000000000078773F000001020000000000000000000000605F7F100004000000000000000000000000007F7E430010000000000000000000000000007C7B1F004000000000000000000031004B07746F7F000002000000000000000060420A00403F7F030008000000000000000000000000007E7D0F0020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000100040010407F740100784F1F000000000000000000000100000010000000000200000000407F7801040000004000000000080000000001000000100000000002000000200000000000780F1F4000000000080000000001003C000000000000034414217448593408132A5D4A3933776F213818032615297768653439176E6E5A7F7B0F30404812440E194B067122552D193F761E1E040833645422754E5D4C18776A6D4D7B3F7F7F7D07002003000F000000000000000000000000000000000000000060016E0D010070011640200000000000200000000000000003200043020410100000000000000000000000000000000000000041125E011028621B000A442607000040000620070000000000020000000000001800021014200001010000000000000000000000000000000000000000000000000000005020343A0000000470003400000000001000000000000040011800240102080800000000000000000000000000000000000000000002001003400C60004002000000100000020028707F3F0000000000000000000000000000000000000000000000000000010002400F0A0000547C0600404002000A0C001020000142020408004001003C00000000000000000000000000000000000000002040007C06182A066A1430094A030000200000057E7F07000000000000000000000000000000000000000000000000500C140D3001000000406A6F000C14084000410102020410202840000100180040070000000000000000000000000000000000000000040000004026780118460E0000400000040040647F7F00000000000000000000000000000000000000000000000000000230041D0000000028790C4001010600142000204000022405081040010300780000000000000000000000000000000000001009000000000000706F3F000000301800000701030400000000000000000000000000000074030000000000003004000000000000000000000040006201000000000000000C000002030C0610003030011203600026600049013000183040670042053800184C004001245840594272041A6000386125020D30005F307300360A7224784720660752027C5D3032410170044013004E0038024009002600180160044012004A0040024009002600180160044013000000000000400811224408112244080000007810607F1700040800202027000000000000000000000000000000000000480100000000200000180060464000010000000020401700040800000000000000000000000000000000000000400E0000000000000100681D04000000000000000000600354183000000000000000000000400C007201000000000000000000000000000000000000000000607F7F000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000007E7F5702020000000000005141400100467D07004016000A002820010A000000000000400C407F50000000000040000001000030204003000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000F7"
        single = list(binascii.unhexlify(single_program))
        yield {"message": single, "name": "Brain Activity  ", "number": 0}

    return {"program_generator": programs}


def all_kinds_of_tests():
    # Some tests
    assert friendlyBankName(4) == "Card 2"
    assert friendlyProgramName(128) == "Preset1 000"
    assert createProgramDumpRequest(1, 257) == [0xF0, 0x00, 0x00, 0x0E, 0x1D, 0x01, 2, 1, 0xf7]

    test_data = [0x7f, 0x01, 0x02, 0x00]
    raw = unescapeSysex(test_data)
    assert raw == [0xff, 0x80, 0x00]

    test_escape = [0xff, 0x00, 0x7f, 0x00, 0x1, 0xff]
    escaped = escapeSysex(test_escape)
    unescaped = unescapeSysex(escaped)
    assert unescaped == test_escape

    test_to_escape = [0xAA] * 15
    bits_set = sum(bitsSet(x) for x in test_to_escape)
    result = escapeSysex(test_to_escape)
    bits_set2 = sum(bitsSet(x) for x in result)
    assert bits_set == bits_set2

    test_to_escape = [0x55] * 16
    bits_set = sum(bitsSet(x) for x in test_to_escape)
    result = escapeSysex(test_to_escape)
    bits_set2 = sum(bitsSet(x) for x in result)
    assert bits_set == bits_set2

    test_to_escape = [0xff] * 15
    bits_set = sum(bitsSet(x) for x in test_to_escape)
    result = escapeSysex(test_to_escape)
    bits_set2 = sum(bitsSet(x) for x in result)
    assert bits_set == bits_set2
    assert result == [0x7f] * 17 + [0x01]

    test_data = [0x7f] * 16
    assert unescapeSysex(test_data) == [0xff] * 14
    test_data = [0x00] * 16
    assert unescapeSysex(test_data) == [0x00] * 14
    test_data = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x7f, 0x00, 0x00]
    assert unescapeSysex(test_data) == [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0x00]

    real_program = "f000000e1d00000026155042560c0822724a056b060408102040000102000000007e00560242027c0000000450042200000002000000000000000000000000000000000000000000000038010e00000000000000000000000000000000000040303d437e471a200b2e700100700512000000000008000000000138010e2000000c000000002031040018000104000000007e7d0f00204000000000000000407f5f010000001e030007000000000000000000000000605f7f010004080000000000000000000000007f7e0700102000000000000000607f62000000004f01400300000000000000002b400300706f3f080202000000000000000000000000403f7f030008100000000000000000000000007e7d0f00204000000000000000000000000078773f000001020000000000000000000000605f7f010004080000000000000000000000007f7e070010200000000000000000000000007c7b1f00400001000000000000004a210000706f3f01000200000000000000003c000d00403f7f050408000000000000000000450500007e7d4f00200000000000000000407c60000078775f40000100000000000000007e400100605f7f0d00040000000000000000300d1400007f7e1f0810200000000000000000000000007c7b1f004000010000000000000000000000706f7f000002040000000000000030070000403f7f050008000000000000000000000000007e7d0f00204000000000000000000000000078773f00000102000000000000003c400000605f7f0e0004000000000000000068031400007f7e0b0010200000000000000060091800007c7b5f014000000000000000000000000000706f7f000102040000000000000000000000403f7f030008100000000000000050071800007e7d070120400000000000000040155b010078771f040001020000000000000000000000605f7f100004000000000000000000000000007f7e430010000000000000000000083800007c7b1f004000000000000000000016102b69736f7f000002000000000000000070000f00403f7f030008000000000000000000000000007e7d0f00200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000020000001000400100000007e73070000000000040000000000000100000010000000000200000000407f7801040000004000000000080000000001000000100000000002000000200000000000780f1f4000000000080000000001003c000000000000034414217448593408132a5d4a3933776f213818032615297768653439176e6e5a7f7b0f30404812440e194b067122552d193f761e1e040833645422754e5d4c18776a6d4d7b3f7f7f7d07002003000f00000000000000000000000000000000000000002041234100007843094030000000000020000000000000000320004302041070400000000000000000000000000000000000000d7a150420033e1a000054310f000040001274030000000000020000000000001800022014200001010000000000000000000000000000000000000000000000000000005020343a00007c7f0f400b00000000001000000000000030001000240302080800000000000000000000000000000000000000000002001003400c60004002000000100000020028707f3f00000000000000000000000000000000000000000000000000000100010000000000543c7e0f404002000a0c001020000151020408004001003c00000000000000000000000000000000000000002040005c076c207b03091801306c0304405c7f7f7f7f0700000000000000000000000000000000000000000000000040044c2d5061400400406a677f0104000000010000020410102a40000100180040070000000000000000000000000000000000000000400040434440774166460c4038646006140040647f7f0000000000000000000000000000000000000000000000000000024805790d70000028790c0001010000002000204000022405081040010300780000000000000000000000000000000000001009000000000000706f3f000000181800000701030000000000000000000000000000000060030000000000003004000000000000000000000000003200000000000000000c0000000000000c003000000000000000000000000000000000000000000000000000000000003c0070014007001e0078006003000f003c0070014007001e0078006003000f003c007001000200080020000001000400100040000002000800200000010004001000400000020008000000000000400811224408112244080000001810607f170004080020002400000000000000000000000000000000000048010000000020000018003044000001000000300040170004080000000000000000000000000000000000000040210000000000000100681d0000000000000000000010032e094201000000000000000000400c007201000000000000000000000000000000000000000000607f7f000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b1000000000000000400c0d0700765a35081940000170010000403100000000400c407f50000000000040000000000030200001000018200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000f7"
    second = list(binascii.unhexlify(real_program))
    assert nameFromDump(second) == "The Dream       "
    third = renamePatch(second, "Renamed program")
    assert nameFromDump(third) == "Renamed program "

    data_block = unescapeSysex(second[8:-1])
    escape_back = escapeSysex(data_block)
    assert escape_back == second[8:-1]

    # test_edit_buffer = [0xf0, 0x00, 0x00, 0x0e, 0x1d, 0x02, 0x10] + getDataBlock(second) + [0xf7]
    real_edit_buffer = "f000000e1d021026152c7a266e19104d2601190324532a5042190342032a00007e7f674d410e54000000000000402c400100000000000000000000000000000000000000000000000020010a0000000000000000000000000000000000004260000030666c1f7d00000000000000000000003801000000176020010e6000000c0000000020510100102800716f3f00007e7d1f102040000000000000000000000000004014030007000000000000000000000000605f7f0e1004080000000000000000000200007f7e3b00102000000000000000000000000000204a01400301000000000000000d000100706f3f07000204000000000000001c000300403f7f2700081000000000000000301e0d00007e7d6700204000000000000000407934000078773f030001020000000000000018300600605f7f0c0004080000000000000060401900007f7e3700102000000000000000603c1a00007c7b6f014000010000000000000000030000706f7f070002040000000000000000020000403f7f1300081000000000000000701b3000007e7d1f10204000000000000000400f7f010078775f03000102000000000000007e7c0700605f7f090004080000000000000000022e39407f7e0f0810200000000000000060477f13647c7b6f01400001000000000000007f7e0300706f3f08000204000000000000007c7b0f00403f7f2100081000000000000000706f3f00007e7d0701204000000000000000000000000078773f00000102000000000000007e7d0700605f7f100004080000000000000078771f00007f7e4300102000000000000000605f7f00007c7b4f014000010000000000000000000000706f7f000002040000000000000000000000403f7f030008100000000000000040071a00007e7d6f00204000000000000000001e60010078773f030001020000000000000000000000605f7f100004080000000000000000000000007f7e430010200000000000000000000000007c7b1f004000000000000000000000000000706f7f00000200000000000000007c7b0f00403f7f030008000000000000000000000000007e7d0f0020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000100040010407f740100000000000000007c2f0f000000000e48050000204700000074080000400e01000068110000001d02000050230000004a040000204700000074080000400e01000068110000001d0200005023000000760400000000002021100002650c2642605522490c6e3b5c11024049642a243a593506491b6d77587d7b0f30403f7f450e194b067122552d193f761e1e040833645422754e5d4c18776a6d4d7b3f7f2b407f0b460000010000000000000000000010005d2e1702506b7502204168740000000800002c000000000020402f7e0100000003200042020410100200000000000000000000000000000000000025701100502418750000101f0b00401f60060c0300000000000218290600000018000250162000010700000000000000000000000000000000000028017b190041125e0100201034000008702800080000000000104049320000004001180072010208380000000000000000000000000000000000000000016a7e7f0f000040007e7f070000200000020028707f7f3f7f010000000000000000000000000000000000000000000000017c7b0f00000000545c0660404102050c0c004301030142020c18602000023c000000000000000000000000000000000000000020000000000000006c7f7f7f7f030400000600057e7f37001a000000006407010000000000000000000000000000000010403f7f01000000404a6f000a143040404101001830102068400103020428400700000000000000000000000000000000000000000400000000007f7f7f7f0f6017403000040040647f7f7f7e0300000000000000000000000000000000000000000000000278771f0000000028790c400103060a10200000030602244518306041000578000000000000000000000000000000000000500600007f7e0300706f3f000000181870000701030000000000000000000000000000007f7f67500900400300300400000000000000000000000000430100000020064c000c00004b016c7b107f43070000000072410300000000000000000000000000000000000000403f7f4702460f382d487f7e73045f16341b300070014007001e0078006003000f003c007009563458520264046806400500090038086004000800200000010004001000400000020008000000000000400801024408112244080006003800607f17070408002020250000000000000000000000000000000000004801000000400c1801180050454000010010003000401707040800000000000000000000000000000000000000000a47010100300000000c1e0e0000000000000000005008261130011c0700000000000010004b006c01000000000000000000000000000000000000000000607f7f000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003c513c0906000000000808514100020376012f200219000000000000000000000000000000000000000000000000000003003030200001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000f7"
    real_edit_buffer = "F000000E1D021026152C7A266E19104D2601190324532A5042190342032A00007E7F674D410E54000000000000402C400100000000000000000000000000000000000000000000000020010A0000000000000000000000000000000000004260000030666C1F7D00000000000000000000003801000000176020010E6000000C0000000020510100102800716F3F00007E7D1F102040000000000000000000000000004014030007000000000000000000000000605F7F0E1004080000000000000000000200007F7E3B00102000000000000000000000000000204A01400301000000000000000D000100706F3F07000204000000000000001C000300403F7F2700081000000000000000301E0D00007E7D6700204000000000000000407934000078773F030001020000000000000018300600605F7F0C0004080000000000000060401900007F7E3700102000000000000000603C1A00007C7B6F014000010000000000000000030000706F7F070002040000000000000000020000403F7F1300081000000000000000701B3000007E7D1F10204000000000000000400F7F010078775F03000102000000000000007E7C0700605F7F090004080000000000000000022E39407F7E0F0810200000000000000060477F13647C7B6F01400001000000000000007F7E0300706F3F08000204000000000000007C7B0F00403F7F2100081000000000000000706F3F00007E7D0701204000000000000000000000000078773F00000102000000000000007E7D0700605F7F100004080000000000000078771F00007F7E4300102000000000000000605F7F00007C7B4F014000010000000000000000000000706F7F000002040000000000000000000000403F7F030008100000000000000040071A00007E7D6F00204000000000000000001E60010078773F030001020000000000000000000000605F7F100004080000000000000000000000007F7E430010200000000000000000000000007C7B1F004000000000000000000000000000706F7F00000200000000000000007C7B0F00403F7F030008000000000000000000000000007E7D0F0020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000100040010407F740100000000000000007C2F0F000000000E48050000204700000074080000400E01000068110000001D02000050230000004A040000204700000074080000400E01000068110000001D0200005023000000760400000000002021100002650C2642605522490C6E3B5C11024049642A243A593506491B6D77587D7B0F30403F7F450E194B067122552D193F761E1E040833645422754E5D4C18776A6D4D7B3F7F2B407F0B460000010000000000000000000010005D2E1702506B7502204168740000000800002C000000000020402F7E0100000003200042020410100200000000000000000000000000000000000025701100502418750000101F0B00401F60060C0300000000000218290600000018000250162000010700000000000000000000000000000000000028017B190041125E0100201034000008702800080000000000104049320000004001180072010208380000000000000000000000000000000000000000016A7E7F0F000040007E7F070000200000020028707F7F3F7F010000000000000000000000000000000000000000000000017C7B0F00000000545C0660404102050C0C004301030142020C18602000023C000000000000000000000000000000000000000020000000000000006C7F7F7F7F030400000600057E7F37001A000000006407010000000000000000000000000000000010403F7F01000000404A6F000A143040404101001830102068400103020428400700000000000000000000000000000000000000000400000000007F7F7F7F0F6017403000040040647F7F7F7E0300000000000000000000000000000000000000000000000278771F0000000028790C400103060A10200000030602244518306041000578000000000000000000000000000000000000500600007F7E0300706F3F000000181870000701030000000000000000000000000000007F7F67500900400300300400000000000000000000000000430100000020064C000C00004B016C7B107F43070000000072410300000000000000000000000000000000000000403F7F4702460F382D487F7E73045F16341B300070014007001E0078006003000F003C007009563458520264046806400500090038086004000800200000010004001000400000020008000000000000400801024408112244080006003800607F17070408002020250000000000000000000000000000000000004801000000400C1801180050454000010010003000401707040800000000000000000000000000000000000000000A47010100300000000C1E0E0000000000000000005008261130011C0700000000000010004B006C01000000000000000000000000000000000000000000607F7F000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003C513C0906000000000808514100020376012F200219000000000000000000000000000000000000000000000000000003003030200001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000F7"
    test_edit_buffer = list(binascii.unhexlify(real_edit_buffer))
    assert isEditBufferDump(test_edit_buffer)
    program_dump = convertToEditBuffer(0, test_edit_buffer)
    assert isSingleProgramDump(program_dump)  # This is because the A6 cannot receive its own Edit Buffer
    assert program_dump[-2] == 0xc0  # There is a program change message appended
    assert program_dump[-3] == 0xf7
    new_program_dump = convertToProgramDump(0, program_dump, 77)
    assert numberFromDump(new_program_dump) == 77
    assert isSingleProgramDump(new_program_dump)
    assert new_program_dump[-1] == 0xf7

    # assert nameFromDump(test_edit_buffer) == nameFromDump(second)
    new_edit_buffer = renamePatch(test_edit_buffer, "new_name")
    assert isEditBufferDump(new_edit_buffer)
    assert nameFromDump(new_edit_buffer) == "new_name        "

    real_program_dump = convertToProgramDump(0, new_edit_buffer, 127)
    assert isSingleProgramDump(real_program_dump)
    assert real_program_dump[-1] == 0xf7  # No program change message at the end


if __name__ == "__main__":
    all_kinds_of_tests()
