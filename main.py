from bitarray import bitarray


class BZZCompressor:
    def decompress(self, input_file_path) -> bytes:
        data = bitarray(endian="big")
        output_buffer = bitarray(endian="big")

        # read the input file
        try:
            with open(input_file_path, "rb") as input_file:
                data.fromfile(input_file)
        except IOError:
            print("Could not open input file...")
            raise

        if len(data) > 9:
            # Getting our method, this is likely imprecise, since I'm one dealing with one method type, but it gets what I want
            method = data[0:8] | bitarray("00001010")
            # We move on to the next byte in data
            del data[0:8]

            # Gathering variables based on the method according to https://problemkaputt.de/psxspx-cdrom-file-compression-bzz.htm
            # Note: bin(int)[2:].zfill(8) converts a number to an 8-bit binary string

            # `>> 3` is the same as dividing by 8
            shifter = (method >> 3) & bitarray(bin(0x03)[2:].zfill(8))
            len_bits = (method & bitarray(bin(0x07)[2:].zfill(8))) ^ bitarray(
                bin(0x07)[2:].zfill(8)
            )

            # The bin() function only returns the second half of the byte, so we pad the byte
            len_mask = bitarray(bin((1 << int(len_bits.to01(), 2)) - 1)[2:].zfill(8))

            threshold = len_mask >> 1
            if int(threshold.to01(), 2) > 0x07:
                threshold = bitarray(bin(0x13).zfill(8))

            len_table = []

            for i in range(int(len_mask.to01(), 2)):
                if i > int(threshold.to01(), 2):
                    len_table.append(
                        (i - int(threshold.to01(), 2) << int(shifter.to01(), 2))
                        + int(threshold.to01(), 2)
                        + 3
                    )
                else:
                    len_table.append(i + 3)

            num_flags = bitarray(bin(int(data[0:24].to01(), 2) + 1)[2:].zfill(24))
            del data[0:24]

            print(f"Method: {method.tobytes()}")
            print(f"Shifter: {shifter.tobytes()}")
            print(f"Len Bits: {len_bits.tobytes()}")
            print(f"Len Mask: {len_mask.tobytes()}")
            print(f"Threshold: {threshold.tobytes()}")
            print(f"Len Table: {len_table}")
            print(f"Num Flags: {num_flags.tobytes()}")

            # Adding 0x100 here means the bitarray is a length of 9, and the first item is always 1
            # This means that later, when we need to gather more flag bits, we aren't losing any data, or
            # hitting an index out of bounds error
            flag_bits = bitarray(bin(int(data[0:8].to01(), 2) + 0x100)[2:])
            del data[0:8]

            print(f"Starting flag_bits: {flag_bits}")

            while int(num_flags.to01(), 2) > 0:
                carry = flag_bits[-1]
                flag_bits = flag_bits >> 1

                if len(flag_bits) > 8 and flag_bits[0] == 0:
                    flag_bits = flag_bits[1:]

                print(f"Carry: {carry}")
                print(f"Flag Bits: {flag_bits}")

                # if we are down to only 0 bits, we are out of file-driven data
                # Here we collect more flag bits and re-iterate the loop
                if len(flag_bits.to01()) == 0:
                    flag_bits = bitarray(bin(int(data[0:8].to01(), 2) + 0x100)[2:])
                    del data[0:8]
                    continue

                # Carry means the next byte is raw data, no weird placement or indexing
                if carry:
                    if len(data) == 0:
                        print("Error processing file. Reached of data stream early.")
                        return

                    output_buffer.append(data[0:8])
                    del data[0:8]

                # If Carry is 0, then we are doing actual decompression. This is the tricky part
                else:
                    # This shouldn't happen
                    if len(data) <= 8:
                        print("Error processing file. Reached of data stream early.")
                        return

                    # This is "temp" in our documentation
                    distance_data = data[0:16]
                    del data[0:16]

                    # length here is the length of the data we are copying.
                    # We multiply by 8 since we are working with bits instead of bytes
                    length = (
                        len_table[
                            int(
                                (
                                    distance_data
                                    & bitarray(
                                        bin(int(len_mask.to01(), 2))[2:].zfill(16)
                                    )
                                ).to01(),
                                2,
                            )
                        ]
                        * 8
                    )

                    # Displacement is how far back in the existing output_buffer we are
                    # looking to copy from. We multiply by 8 since we are working with bits and not bytes
                    displacement = (
                        int((distance_data >> int(len_bits.to01(), 2)).to01(), 2) * 8
                    )

                    # This shouldn't happen
                    if displacement <= 0:
                        print(
                            "Error processing file. Displacement was less than or equal to 0"
                        )
                        return

                    print(f"Output Buffer Size (in bits): {len(output_buffer)}")
                    print(f"Distance Data: {distance_data.tobytes()}")
                    print(f"Displacement (in bits): {displacement}")
                    print(f"Length (in bits): {length}")

                    # Here we copy bit by bit from earlier in the output buffer.
                    # we use this instead of index slicing since the slice could lead to
                    # data we are currently copying into the buffer
                    start_index = len(output_buffer) - displacement

                    # If start index is less than 0, we'll be checking something like output_buffer[-2]
                    # or smth, which will have an IndexOutOfBounds exception
                    if start_index < 0:
                        print("Error decompressing file. Start Index was out of range.")
                        return

                    for i in range(length):
                        output_buffer.append(output_buffer[start_index + i])

                num_flags = bitarray(bin(int(num_flags.to01(), 2) - 1)[2:].zfill(24))

            if len(data) > 0:
                output_buffer.append(
                    bitarray(data.to01() + "0".join("" for i in range(8 - len(data))))
                )

        else:
            # If the file is less than 9 bits, it's just output
            for i in data:
                output_buffer.append(i)

        out_data = b"".join(output_buffer.tobytes())

        try:
            if "bin_extract" in input_file_path[0:11]:
                output_file_path = input_file_path[12:]
            else:
                output_file_path = input_file_path

            if "/" in output_file_path:
                output_file_name = output_file_path.split("/")[-1]
            else:
                output_file_name = output_file_path

            # TODO: Create file path, if it doesn't exist
            with open(
                f"decompressed_files/{output_file_name[:4]}.file", "wb"
            ) as outfile:
                outfile.write(out_data)
                print(f"File {output_file_name} saved successfully!")
        except IOError:
            print(f"Unable to write file for {input_file_path}")


compressor = BZZCompressor()

compressor.decompress("bin_extract/level/mc/mccave01.bzz")
