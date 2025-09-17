import os
from bitarray import bitarray
from pathlib import Path


class BZZCompressor:
    def decompress(self, input_file_path, input_file, output_folder="out/") -> bytes:
        data = bitarray(endian="big")
        output_buffer = bytearray()
        index = 0x800

        # read the input file
        try:
            with open(f"{input_file_path}/{input_file}", "rb") as input_file:
                data.fromfile(input_file)
                data = data.tobytes()
        except IOError:
            print("Could not open input file...")
            raise

        if len(data) > 9:
            # Getting our method, this is likely imprecise, since I'm one dealing with one method type, but it gets what I want
            method = data[index]
            # We move on to the next byte in data
            index = index + 1

            # Gathering variables based on the method according to https://problemkaputt.de/psxspx-cdrom-file-compression-bzz.htm
            # Note: bin(int)[2:].zfill(8) converts a number to an 8-bit binary string

            # `>> 3` is the same as dividing by 8
            shifter = (method >> 3) & 0x03
            len_bits = (method & 0x07) ^ 0x07

            # The bin() function only returns the second half of the byte, so we pad the byte
            len_mask = 1 << len_bits

            threshold = len_mask >> 1

            if threshold > 0x07:
                threshold = 0x13

            len_table = []

            for i in range(len_mask):
                if i > threshold:
                    len_table.append((i - threshold << shifter) + threshold + 3)
                else:
                    len_table.append(i + 3)

            temp_flags = ""

            for item in data[index : index + 3]:
                temp_flags += bin(item)[2:].zfill(8)

            num_flags = int(temp_flags, 2) + 1
            index = index + 3

            print(f"Method: {hex(method)}")
            print(f"Shifter: {shifter}")
            print(f"Len Bits: {bin(len_bits)}")
            print(f"Len Mask: {bin(len_mask)}")
            print(f"Threshold: {threshold}")
            print(f"Len Table: {len_table}")
            print(f"Num Flags: {bin(num_flags)}")

            # Adding 0x100 here means the bitarray is a length of 9, and the first item is always 1
            # This means that later, when we need to gather more flag bits, we aren't losing any data, or
            # hitting an index out of bounds error
            flag_bits = bitarray(bin(data[index] + 0x100)[2:])
            index = index + 1

            print(f"Starting flag_bits: {flag_bits}")

            while num_flags > 0:
                carry = flag_bits[-1]
                flag_bits = flag_bits >> 1

                print(f"Carry: {carry}")
                print(f"Flag Bits: {flag_bits}")

                # if we are down to only 0 bits, we are out of file-driven data
                # Here we collect more flag bits and re-iterate the loop
                if int(flag_bits.to01(), 2) == 0x00:
                    flag_bits = bitarray(bin(data[index] + 0x100)[2:])
                    index = index + 1
                    continue

                # Carry means the next byte is raw data, no weird placement or indexing
                if carry:
                    try:
                        output_buffer.append(data[index])
                        index = index + 1
                    except IndexError:
                        print(output_buffer)
                        print(
                            f"Error processing file. Reached of data stream early. Index: {index}"
                        )
                        return

                # If Carry is 0, then we are doing actual decompression. This is the tricky part
                else:
                    # This shouldn't happen
                    if len(data) <= index + 1:
                        print("Error processing file. Reached of data stream early.")
                        return

                    # This is "temp" in our documentation
                    temp = ""
                    for item in data[index : index + 2]:
                        temp = temp + bin(item)[2:].zfill(8)

                    distance_data = int(temp, 2)
                    index = index + 2

                    # length here is the length of the data we are copying.
                    # We multiply by 8 since we are working with bits instead of bytes
                    length = len_table[(distance_data & len_mask) - 1]

                    # Displacement is how far back in the existing output_buffer we are
                    # looking to copy from. We multiply by 8 since we are working with bits and not bytes
                    displacement = distance_data >> len_bits

                    # This shouldn't happen
                    if displacement <= 0:
                        print(
                            f"Error processing file. Displacement was less than or equal to 0.\n"
                            + f"Distance Data: {distance_data}. Displacement: {displacement}. Index: {hex(index)}"
                        )
                        return

                    print(f"Output Buffer Size {len(output_buffer)}")
                    print(f"Distance Data: {distance_data}")
                    print(f"Displacement: {displacement}")
                    print(f"Length: {length}")

                    # Here we copy bit by bit from earlier in the output buffer.
                    # we use this instead of index slicing since the slice could lead to
                    # data we are currently copying into the buffer
                    copy_index = len(output_buffer) - displacement

                    # If start index is less than 0, we'll be checking something like output_buffer[-2]
                    # or smth, which will have an IndexOutOfBounds exception
                    if copy_index < 0:
                        print(output_buffer)
                        print("Error decompressing file. Start Index was out of range.")
                        return

                    for i in range(length):
                        output_buffer.append(output_buffer[copy_index + i])

                num_flags = num_flags - 1

            if len(data) > index:
                for item in data[index:]:
                    output_buffer.append(item)

        else:
            # If the file is less than 9 bits, it's just output
            for i in data:
                output_buffer.append(i)

        # This handoff is so I can change buffer logic without breaking write-out logic
        out_data = output_buffer

        try:
            if "bin_extract" in input_file_path[0:11]:
                output_file_path = input_file_path[12:]
            else:
                output_file_path = input_file_path

            if "/" in output_file_path:
                output_file_name = output_file_path.split("/")[-1] + ".file"
            else:
                output_file_name = output_file_path + ".file"

            # TODO: Create file path, if it doesn't exist
            with open(f"{output_folder}/{output_file_name}", "wb") as outfile:
                outfile.write(out_data)
                print(f"File {output_file_name} saved successfully!")
        except IOError as e:
            print(
                f"Unable to write file for {input_file_path}/{input_file}. Error: {e}"
            )


if __name__ == "__main__":
    compressor = BZZCompressor()

    for dirpath, dirnames, filenames in os.walk("./bin_extract"):
        print(f"{dirpath} | {', '.join(filenames)}")

        for file in filenames:
            if file[-4:] == ".bzz":
                output_folder_path = Path(f"out/{'/'.join(dirpath.split("/")[2:])}")
                output_folder_path.mkdir(parents=True, exist_ok=True)

                try:
                    compressor.decompress(dirpath, file, output_folder_path)
                except Exception as e:
                    print(
                        f"Error while decompressing {output_folder_path}/{file}. Error: {e}"
                    )
                    continue
