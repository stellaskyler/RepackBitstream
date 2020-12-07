from app import *
from bitstring import BitArray
from hmac_helper import HashHelper
from crypto import *

from Crypto import Random 
from Crypto.Cipher import AES

class Repackager():
	
	def __init__(self, keyfile=None):
		if keyfile is not None:
			keys = self.parse_nky(keyfile)
			self.AES_KEY = BitArray(hex=keys["AES_KEY"]).bytes
			self.HKEY    = BitArray(hex=keys["HKEY"]).bytes
			self.IV      = BitArray(hex=keys["IV"]).bytes
		else:
			self.AES_KEY = None
			self.HKEY    = None
			self.IV      = None

		self.crypto_helper = AESCipher(key=self.AES_KEY)			
		self.key = b'\x00'
		return
	
	def decrypt_fabric(self, filename):
		read = io.BytesIO(open(filename, "rb").read())
		decryptor = DecryptParser(read, output="temp_decrypted.bin", key=self.key, hmac_out=False)
		decryptor.handle_bit()

	def calc_digest(self, filename):	
		stream = io.BytesIO(open(filename, "rb").read())	
		HashHandler = HashHelper(stream, hkey=self.HKEY)
		digest = HashHandler.calc_digest()
		return digest

	def parse_nky(self, filename):
		result = {"AES_KEY": "", "IV": "", "HKEY": ""}
		with open(filename, "r") as f:
			for l in f:
				if "Key 0" in l:
					result['AES_KEY'] = l.split()[2][:-1]
				elif "StartCBC" in l:
					result['IV'] = l.split()[2][:-1]
				elif "HMAC" in l:
					result['HKEY'] = l.split()[2][:-1]
		return result	
	
	def _read_until_match(self, stream, end_at):

		payload = b""
		count = 0

		while not payload.endswith(end_at):
			payload +=stream.read(1)
			count = count + 1 
		
		return stream, payload

	def get_full_ciphertext(self, filename):	
		
		stream = io.BytesIO(open(filename, "rb").read())
		stream, p = self._read_until_match(stream, b'\x30\x03\x40\x01')

		# Number of words to read until end of ciphertext
		DWC = BitArray(stream.read(4)).int
		
		ciphertext = stream.read(DWC * 4)
	
		return ciphertext

	def encrypt(self, filename):
		raw_bytes = open(filename,"rb").read() 
		cipher = AES.new(self.AES_KEY, AES.MODE_CBC, self.IV)
		return cipher.encrypt(raw_bytes)
	
	def encrypt_block(self, data, IV):
		
		IV = bytes(self.crypto_helper.swapBytes(IV)[0:16])
		
		d = bytes(self.crypto_helper.swapBytes(data)[0:16])		
		
		cipher = AES.new(self.AES_KEY, AES.MODE_CBC, IV)
		encrypted = cipher.encrypt(d)
		
		ciphertext = bytes(self.crypto_helper.swapBytes(encrypted)[0:16])
		
		return ciphertext

	def decrypt(self, filename, output_name="deciphered.bin"):
		
		stream = io.BytesIO(open(filename, "rb").read())
		IV = self.IV
		
		cipher = AESCipher(key=self.AES_KEY)

		f = open(output_name,"wb")

		while True:
			
			ciphertext = stream.read(16)

			if ciphertext == b'':
				return

			ptext = cipher.decrypt_word(ciphertext, iv=IV, xor=False)
			f.write(ptext)	
			IV = ciphertext 
		
	def repack(self, enc_name, modified_name, insert, output_filename="modified_bitstream"):
			
		new_digest = self.calc_digest(modified_name)
		print(BitArray(new_digest).hex)
		
		'''
			First thing we need to do is isolate the ciphertext from the original file.

			We are going to copy the plaintext IPAD and OPAD and splice our modified content between them. 
		
			We also need to apply the new HMAC digest to the end.
		'''

		ciphertext = Repack.get_full_ciphertext(enc_name)
		open("temp_0.bin","wb").write(ciphertext)
		#deciphered = Repack.decrypt("temp_0.bin", output_name="temp_0.bin")	
		
		MODIFIED_CONTENT = open(modified_name,"rb").read()

		with open("temp_1.bin", "wb") as f:
			
			stream = io.BytesIO(open("temp_0.bin", "rb").read())
			
			orig_IPAD   = stream.read(64)
			orig_body   = stream.read(len(MODIFIED_CONTENT))
			orig_OPAD   = stream.read(448)
			orig_digest = stream.read(32)
			
			f.write(orig_IPAD)
			f.write(MODIFIED_CONTENT)
			f.write(orig_OPAD)
			f.write(new_digest)
		
		stream = io.BytesIO(open("temp_1.bin","rb").read())
		
		IV = self.IV

		'''

			For the next step, we rencrypt the newly spliced/modified ciphertext using the original AES Key.

		'''

		with open("temp_2.bin","wb") as f:
			while True:
				data = stream.read(16)
					
				if data == b'':
					break
				else:
					cipher   = AES.new(self.AES_KEY, AES.MODE_CBC, IV)
					ciphertext = self.encrypt_block(data, IV)
					f.write(ciphertext)
					IV = ciphertext

		'''
		
			Finally, we need to reattach the plaintext portions of the bitstream before and after the ciphertext. 

		'''
		if(insert):
			with open("result","rb") as f:
				with open("temp_2.bin","wb") as f1:
					for line in f:
						f1.write(line)


		stream = io.BytesIO(open(enc_name,"rb").read())
		stream, config_header = self._read_until_match(stream, b'\x30\x03\x40\x01')
		DWC = stream.read(4)
		body = stream.read(BitArray(DWC).int * 4)
		footer = stream.read(2000)

		modified_ciphertext = open("temp_2.bin","rb").read()

		with open(output_filename,"wb") as f:
			f.write(config_header)
			f.write(DWC)
			f.write(modified_ciphertext)
			f.write(footer)

		with open("full_dec.bit","wb") as f:
			f.write(config_header)
			f.write(DWC)
			f.write(open("temp_1.bin","rb").read())
			f.write(footer)
		
		# clean up temp files.
		#os.remove("temp_0.bin")
		#os.remove("temp_1.bin")
		#os.remove("temp_2.bin")

		return print("Repackage Finished")



if __name__ == "__main__":
	
	import argparse
	parser = argparse.ArgumentParser(
		description="Decrypt and Repackage Encrypted BASYS3 Bitstreams.")
 	
	parser.add_argument("bitfile", metavar="BITFILE",
                        help="Input bit file name")
	parser.add_argument("--output", "-o", type=str, help="Output bin file name", default=None)
	parser.add_argument("--keyfile", "-k", type=str, default=None, help="Input .nky keyfile name")
	parser.add_argument("--decrypt", "-D", type=bool, default=False, help="Decrypt bitstream")
	parser.add_argument("--repack", "-R", type=str, default=None, help="Repackage Bitstream with <param> binary file")
	parser.add_argument("--insert", "-i", type=bool, default=False, help="Insert your own ciphertext")

	args = parser.parse_args()
	
	if args.keyfile is None:
		print("Tool requires keyfile provided by -k flag")

	Repack = Repackager(keyfile=args.keyfile)

	# Parse and Decrypt
	
	if args.decrypt == True:
		Repack.decrypt_fabric(args.bitfile)

	if args.repack is not None:
		Repack.repack(args.bitfile, args.repack, args.insert, output_filename="mod.bit")

	# Snippets for other uses -

	# Calc Digest
	#digest = Repack.calc_digest("temp_decrypted.bin")
	#print(BitArray(digest).hex)

	# Obtain only ciphertext
	#ciphertext = Repack.get_full_ciphertext("enc.bit")
	#open('ciphertext.bin','wb').write(ciphertext)
	#deciphered = Repack.decrypt("ciphertext.bin")	

	# Reencrypt only ciphertext (no full bitstream)
	#recrypted = Repack.encrypt("temp_decrypted.bin")
	#with open("recrypted.bin","wb") as f:
	#	f.write(recrypted)

	# Repackage bitstream.
	#Repack.repack("enc.bit","temp_decrypted.bin",output_filename="mod.bit")
	
