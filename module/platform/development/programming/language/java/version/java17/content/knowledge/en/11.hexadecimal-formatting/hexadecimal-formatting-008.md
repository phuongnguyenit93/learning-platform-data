# Hex, Base64, Character Encoding, and Encryption Are Different Tasks

When working with data in Java 17, we often encounter the terms **hex**, **Base64**, **UTF-8**, **encode**, **decode**, **encrypt**, and **hash**. They all relate to transforming data, but they do not serve the same purpose.

For example, a Vietnamese string can be converted to bytes using UTF-8; that byte sequence can be represented as hex or Base64 for text storage; if secrecy is required, the data must be encrypted using a cryptographic algorithm and a key. Each step solves a distinct problem.

| Concept | What does it transform? | Primary purpose | Secures data by itself? |
|---|---|---|---|
| **Hex (base 16)** | Bytes into hex digits and back | Human-readable byte representation, debugging, text storage | No |
| **Base64** | Bytes into characters from the Base64 alphabet and back | Transferring binary data over text channels | No |
| **Character encoding (charset encoding)** | Text into bytes and back | Defining which bytes represent which characters | No |
| **Encryption** | Plaintext into ciphertext using an algorithm and key | Content confidentiality | Yes, if using proper algorithms and key management |
| **Hashing** | Arbitrary data into a fixed-length digest | Integrity checking, identification, building authentication mechanisms | Cannot be decrypted back |

The most important point: **hex and Base64 are byte representations; UTF-8 is a conversion between characters and bytes; encryption is a key-based cryptographic mechanism**. They can be combined in the same pipeline, but they do not substitute for one another.

## 1. Starting from Text, Characters, and Bytes

Computers store and transmit data as bytes. A `String` in Java is text; to write it to a file, send it over a network, or pass it to a byte-oriented API, an application must convert it into a byte sequence using a **character encoding**.

Example:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class TextToBytes {
    public static void main(String[] args) {
        String text = "Xin chào Java 17";

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        System.out.println(Arrays.toString(bytes));

        String restored = new String(bytes, StandardCharsets.UTF_8);
        System.out.println(restored);
    }
}
```

Workflow:

```text
String "Xin chào Java 17"
          |
          | UTF-8 encoding
          v
      byte[] data
          |
          | UTF-8 decoding
          v
String "Xin chào Java 17"
```

- `getBytes(StandardCharsets.UTF_8)` converts the string to bytes using UTF-8.
- `new String(bytes, StandardCharsets.UTF_8)` interprets the bytes as UTF-8 to reconstruct the string.
- If the same charset is used and the bytes are valid, the text is restored accurately.

### 1.1. A Character Does Not Equal One Byte

Different characters can require different numbers of bytes in UTF-8:

| Character | Unicode code point | UTF-8 byte count |
|---|---|---:|
| `A` | U+0041 | 1 |
| `é` | U+00E9 | 2 |
| `中` | U+4E2D | 3 |
| `😀` | U+1F600 | 4 |

Therefore, you must never assume one character always maps to one byte. Strings with Vietnamese, Chinese, or emoji can take more bytes than the visible character count.

Java `String` uses UTF-16 representation at the code-unit level; that does not mean file output defaults to UTF-16. The charset used to convert strings to bytes is an explicit application choice.

### 1.2. Why Specify the Charset Explicitly?

In Java 17, calling:

```java
byte[] bytes = text.getBytes();
```

uses the **runtime environment's default charset**. The default charset can vary across developer machines, servers, containers, and operating systems.

Similarly:

```java
String text = new String(bytes);
```

also depends on the default charset. If the writer and reader use different charsets, text can become garbled.

Specify it explicitly:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String textAgain = new String(bytes, StandardCharsets.UTF_8);
```

`StandardCharsets.UTF_8` is a built-in constant in Java, requiring no string-based charset lookup and throwing no checked exceptions.

**Version note:** starting in Java 18, UTF-8 became the standard default charset via JEP 400. However, for Java 17 projects, do not rely on Java 18's change; specifying UTF-8 explicitly remains clear and reliable.

## 2. What Is Hex?

**Hexadecimal (hex, base 16)** uses 16 symbols:

```text
0 1 2 3 4 5 6 7 8 9 A B C D E F
```

One hex digit represents a value from 0 to 15. One byte has 8 bits, so it is represented by exactly **two hex digits**:

| Byte (binary) | Unsigned decimal value | Hex |
|---|---:|---|
| `0000 0000` | 0 | `00` |
| `0000 1010` | 10 | `0A` |
| `0111 1111` | 127 | `7F` |
| `1000 0000` | 128 | `80` |
| `1111 1111` | 255 | `FF` |

For example, the byte `0x4A` has the decimal value 74. When writing hex, the `0x` prefix is often added so readers know it is base 16.

**Hex is not a character encoding.** The hex string `41` can represent a byte with value 65; decoding that byte with ASCII or UTF-8 yields the character `A`. However, if the original data is arbitrary binary bytes, `41` is merely a way of writing down the byte and does not carry inherent text meaning.

### 2.1. Converting Bytes to Hex with Java 17 `HexFormat`

Since Java 17, the `java.util.HexFormat` class provides the standard API to convert between byte arrays and hex strings.

```java
import java.util.HexFormat;

public class HexDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x41, 0x42, 0x43, 0x0A, (byte) 0xFF
        };

        String hex = HexFormat.of().formatHex(data);

        System.out.println(hex);
    }
}
```

Output:

```text
4142430aff
```

`HexFormat.of()` defaults to lowercase and inserts no delimiter. You can choose uppercase or add a delimiter:

```java
import java.util.HexFormat;

byte[] data = {0x41, 0x42, 0x43, 0x0A};

String lower = HexFormat.of().formatHex(data);
String upper = HexFormat.of().withUpperCase().formatHex(data);
String separated = HexFormat.ofDelimiter(":").formatHex(data);

System.out.println(lower);     // 4142430a
System.out.println(upper);     // 4142430A
System.out.println(separated); // 41:42:43:0a
```

The delimiter is strictly for presentation. It is not a byte in the original data.

### 2.2. Converting a Hex String Back to Bytes

Use `parseHex`:

```java
import java.util.HexFormat;
import java.util.Arrays;

String hex = "48656c6c6f";
byte[] bytes = HexFormat.of().parseHex(hex);

System.out.println(Arrays.toString(bytes));
System.out.println(new String(bytes, java.nio.charset.StandardCharsets.UTF_8));
```

Output:

```text
[72, 101, 108, 108, 111]
Hello
```

`parseHex` converts two hex characters into one byte. A hex string must have an even number of digits; non-hex characters or malformed structure will throw `IllegalArgumentException`.

You can use a matching delimited format when parsing:

```java
HexFormat colonHex = HexFormat.ofDelimiter(":");
byte[] bytes = colonHex.parseHex("48:65:6c:6c:6f");
```

The parse format must match the chosen representation; do not arbitrarily strip delimiters if the data follows a specific convention.

### 2.3. Why Can Bytes in Java Appear as Negative Numbers?

Java's `byte` type is a signed integer ranging from -128 to 127. However, a data byte is often interpreted as an unsigned value from 0 to 255.

Example:

```java
byte value = (byte) 0xFF;

System.out.println(value);          // -1
System.out.println(value & 0xFF);   // 255
```

The `& 0xFF` operation retrieves the byte's unsigned value. When using `HexFormat`, you do not need to handle each byte like this manually; the library takes care of rendering the exact two hex digits.

## 3. What Is Base64?

**Base64** converts byte data into a string of characters from a character table that can safely traverse many text-oriented systems. It is commonly used when embedding binary data in JSON, email, configuration, or text-friendly protocols.

The basic Base64 alphabet consists of:

- `A-Z`: 26 characters.
- `a-z`: 26 characters.
- `0-9`: 10 characters.
- `+` and `/`: 2 characters.

64 characters in total. The `=` character may appear as **padding** at the end.

Base64 groups data by converting **3 input bytes into 4 Base64 characters** (24 bits divided into four 6-bit groups). As a result, the string size is typically about 1/3 larger than the original data, excluding padding or delimiters.

### 3.1. Java 17 Example

Using `java.util.Base64`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64Demo {
    public static void main(String[] args) {
        String text = "Hello Java 17";

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(bytes);
        System.out.println(encoded);

        byte[] decoded = Base64.getDecoder().decode(encoded);
        String restored = new String(decoded, StandardCharsets.UTF_8);

        System.out.println(restored);
    }
}
```

Output:

```text
SGVsbG8gSmF2YSAxNw==
Hello Java 17
```

Workflow:

```text
String
  |
  | UTF-8
  v
byte[]
  |
  | Base64 encode
  v
Base64 String
  |
  | Base64 decode
  v
byte[]
  |
  | UTF-8
  v
Original String
```

Note: Base64 encoding takes **`byte[]`**, not character semantics directly. To recover text, you must know the charset used in the initial step.

### 3.2. Three Encoder/Decoder Variants in Java

`Base64` provides three main encoder/decoder pairs:

| API | Alphabet | Purpose |
|---|---|---|
| `Base64.getEncoder()` | Basic Base64 (`+`, `/`), with padding | General Base64 data |
| `Base64.getUrlEncoder()` | URL-safe (`-`, `_`), with padding by default | Data used in URLs or filenames |
| `Base64.getMimeEncoder()` | Basic Base64, can insert line breaks per MIME | MIME/email content |

URL-safe without padding example:

```java
byte[] data = {0x01, 0x02, (byte) 0xFB, (byte) 0xFF};

String basic = Base64.getEncoder().encodeToString(data);

String urlSafe = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(data);

System.out.println(basic);
System.out.println(urlSafe);
```

URL-safe replaces `+` with `-` and `/` with `_`. Call `withoutPadding()` to omit trailing `=` characters when permitted by the protocol.

Do not manually replace Base64 characters with string operations when you can use the matching encoder/decoder. Both sides must agree on the same variant.

### 3.3. Is Base64 Encryption for Secrecy?

**No.** Base64 is merely a reversible representation, uses no key, and provides no security.

Anyone with the Base64 string can decode it:

```java
String encoded = "cGFzc3dvcmQ=";

byte[] bytes = Base64.getDecoder().decode(encoded);
String text = new String(bytes, StandardCharsets.UTF_8);

System.out.println(text); // password
```

Do not use Base64 to hide passwords, tokens, API keys, or personal data. If content needs secrecy, use an appropriate cryptographic encryption mechanism.

### 3.4. MIME Base64 and Multiline Data

The MIME encoder can insert line separators according to MIME rules:

```java
Base64.Encoder mimeEncoder = Base64.getMimeEncoder();
String mimeText = mimeEncoder.encodeToString(data);
```

The Basic decoder strictly requires characters from the Basic Base64 alphabet; the MIME decoder allows non-Base64 characters to accommodate MIME content with line breaks or auxiliary characters.

Do not pick MIME simply because a string is long. Use the encoder matching the protocol or format expected by the target system.

## 4. How Do Hex and Base64 Differ?

Both can represent the same byte sequence as text, but their representations differ.

| Criterion | Hex | Base64 |
|---|---|---|
| Grouping unit | 1 byte into 2 digits | 3 bytes into 4 characters |
| Text size | Roughly 2× original bytes | Roughly 4/3× original bytes |
| Characters | `0-9`, `a-f` (or uppercase) | 64 characters, optional `=` padding |
| Human readability | Easy to inspect byte by byte | More compact, harder to read individual bytes |
| Common uses | Debugging, hashes, byte dumps, hex identifiers | Text APIs, email, binary payloads in JSON |
| Security | None | None |

Example with the bytes of `Hello` (ASCII/UTF-8):

```java
byte[] data = "Hello".getBytes(StandardCharsets.UTF_8);

String hex = HexFormat.of().formatHex(data);
String base64 = Base64.getEncoder().encodeToString(data);

System.out.println(hex);
System.out.println(base64);
```

Output:

```text
48656c6c6f
SGVsbG8=
```

The two strings look different, yet when decoded properly, both restore the exact same byte array.

### 4.1. Choose Hex When You Need to Inspect Individual Bytes

Hex is well suited for:

- Displaying binary data during debugging.
- Writing SHA-256 digests in logs or checksum files.
- Reading byte dumps of protocols or files.
- Representing fixed-length identifiers according to system conventions.

For example, SHA-256 is usually printed as 64 hex characters because the digest is 32 bytes.

### 4.2. Choose Base64 When You Need a Shorter String

Base64 is well suited for:

- Embedding images or binary data in JSON.
- Packing bytes inside text protocols.
- Representing bytes in MIME/email content.
- Representing binary tokens in URLs when using the URL-safe variant.

Base64 is shorter than hex for the same data, yet it remains a publicly decodable string.

## 5. Character Encoding (Charset Encoding) Is a Different Task

Charset encoding answers the question:

> Which bytes represent this text?

Common charsets:

- **UTF-8:** encodes Unicode using 1–4 bytes per Unicode code point; standard across the web and modern systems.
- **UTF-16:** encodes using 16-bit code units; some code points require surrogate pairs.
- **ISO-8859-1:** a single-byte character table for a limited character set.
- **Windows-1252:** a single-byte charset commonly found in legacy Windows data.

You cannot always look at a sequence of bytes and know the text without knowing the charset or data convention.

Example showing the same byte can have different interpretations depending on charset:

```java
byte[] bytes = {(byte) 0xE9};

String latin1 = new String(bytes, java.nio.charset.StandardCharsets.ISO_8859_1);
String utf8 = new String(bytes, StandardCharsets.UTF_8);

System.out.println(latin1);
System.out.println(utf8);
```

`0xE9` is the character `é` in ISO-8859-1. However, a single byte `E9` is not a valid complete UTF-8 sequence for `é` (UTF-8 for `é` is `C3 A9`); the default `String` constructor replaces malformed byte sequences with a replacement character.

This example shows that **decoding with the wrong charset can corrupt text** even though the bytes have not changed.

### 5.1. UTF-8 Round-Trip

Example:

```java
String original = "Tiếng Việt: Chào bạn!";

byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

System.out.println(original.equals(decoded)); // true
```

When transmitting text between systems, specify the charset in the protocol (such as UTF-8) rather than letting each side guess.

### 5.2. Strict Decoding When Invalid Bytes Must Be Detected

`new String(bytes, charset)` may replace invalid byte sequences with the replacement character. If the data must strictly be valid, use `CharsetDecoder` in `REPORT` mode:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

With this approach, invalid data throws `CharacterCodingException` instead of being silently replaced. This is useful for file imports, protocols, or data requiring strict quality checks.

## 6. What Is Encryption?

**Encryption** transforms *plaintext* into *ciphertext* using a cryptographic algorithm and a key. Only someone with the matching key can decrypt it back.

```text
Plaintext + Key + Algorithm + Parameters
                    |
                    | Encrypt
                    v
               Ciphertext
                    |
                    | Decrypt with the matching key
                    v
                 Plaintext
```

Unlike hex and Base64:

- Encryption depends on a key.
- The same plaintext can produce different ciphertexts when a random nonce/IV is used properly.
- Anyone without the key cannot simply decode it to read the contents, provided the algorithm and key management are secure.
- Encryption does not turn data into text; ciphertext is still bytes and may need Base64/hex for transmission or storage in text systems.

### 6.1. Symmetric and Asymmetric Encryption

| Type | Key usage | Example | Use cases |
|---|---|---|---|
| Symmetric | Same secret key for encryption and decryption | AES-GCM | Encrypting stored data, payloads |
| Asymmetric | Public key / private key pair; encryption/decryption or signing/verifying depending on algorithm | RSA-OAEP, EC-based schemes | Key exchange, digital signatures, security protocols |

In typical Java applications, AES-GCM is a suitable choice for symmetric data encryption because it protects both confidentiality and the integrity of the ciphertext and any associated authenticated data.

Do not design your own encryption algorithm. Use standard Java Cryptography Architecture (JCA/JCE) APIs and recommended configurations.

## 7. AES-GCM Example in Java 17

The following example illustrates generating an AES key, generating a random IV, encrypting bytes, and decrypting. The key in the example is created in memory for learning; real applications must manage and store keys securely.

```java
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

public class AesGcmDemo {
    private static final int IV_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    static SecretKey newKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        return generator.generateKey();
    }

    static byte[] encrypt(byte[] plaintext, SecretKey key)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_LENGTH];
        RANDOM.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_LENGTH_BITS, iv);

        cipher.init(Cipher.ENCRYPT_MODE, key, parameters);
        byte[] ciphertext = cipher.doFinal(plaintext);

        // Package IV + ciphertext (ciphertext includes the authentication tag).
        byte[] result = new byte[iv.length + ciphertext.length];
        System.arraycopy(iv, 0, result, 0, iv.length);
        System.arraycopy(ciphertext, 0, result, iv.length, ciphertext.length);

        return result;
    }

    static byte[] decrypt(byte[] envelope, SecretKey key)
            throws GeneralSecurityException {
        if (envelope.length < IV_LENGTH + TAG_LENGTH_BITS / 8) {
            throw new IllegalArgumentException("Encrypted data is too short");
        }

        byte[] iv = Arrays.copyOfRange(envelope, 0, IV_LENGTH);
        byte[] ciphertext = Arrays.copyOfRange(
                envelope, IV_LENGTH, envelope.length
        );

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_LENGTH_BITS, iv);

        cipher.init(Cipher.DECRYPT_MODE, key, parameters);
        return cipher.doFinal(ciphertext);
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newKey();

        String message = "Sensitive data to protect";
        byte[] plaintext = message.getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = encrypt(plaintext, key);
        String encoded = Base64.getEncoder().encodeToString(encrypted);

        System.out.println("Ciphertext (Base64): " + encoded);

        byte[] decodedEnvelope = Base64.getDecoder().decode(encoded);
        byte[] restored = decrypt(decodedEnvelope, key);

        System.out.println(
                new String(restored, StandardCharsets.UTF_8)
        );
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 AesGcmDemo.java
java AesGcmDemo
```

The Base64 ciphertext line will change across runs because the IV is randomly generated. The final line should restore accurately:

```text
Sensitive data to protect
```

### 7.1. Role of the IV/Nonce in AES-GCM

- The IV (initialization vector) is an accompanying parameter when initializing the cipher.
- The example uses a 12-byte (96-bit) IV, which is the widely recommended size for GCM.
- The IV does not need to be kept secret; it must be stored alongside the ciphertext for decryption.
- **Never reuse the same IV with the same AES-GCM key.** Nonce reuse can severely compromise security.
- The example generates a new IV with `SecureRandom` for each encryption. For high-volume systems, you need a nonce-management design that respects limits and avoids collisions.

The 128-bit tag detects tampering with the ciphertext or authenticated data. If the tag is invalid, `doFinal()` on decryption throws `AEADBadTagException` (a subclass of `GeneralSecurityException`). Never ignore this error or return partial plaintext.

### 7.2. Keys Must Be Managed Separately

In the example, `KeyGenerator` creates a new key on every run. If you encrypt in the first run and the application exits, the in-memory key is lost; subsequent runs cannot decrypt old ciphertext without the exact original key.

In real applications:

- Store keys in a suitable key management system (KMS, HSM, or Java KeyStore with proper protection).
- Restrict access to keys.
- Never hard-code keys in source code or commit them to Git.
- Do not send keys alongside ciphertext over the same channel.
- Have plans for key backup, rotation, and revocation.
- Do not use a user password directly as an AES key; if deriving a key from a password is required, use a dedicated KDF such as PBKDF2 with salt and appropriate parameters, or a dedicated secrets management mechanism.

**Base64 ciphertext is no substitute for protecting the key.** Anyone who has both the ciphertext and the key can decrypt it; anyone who obtains the key defeats the security mechanism.

### 7.3. Why Not Use AES/ECB?

Do not use `AES/ECB` for general data requiring confidentiality. ECB encrypts each block independently and leaks repeating patterns in the plaintext. For new applications, prefer authenticated modes like AES-GCM, use IVs/nonces properly, and handle authentication errors.

Also avoid using AES-CBC without a separate authentication mechanism. Secure encryption must protect **both confidentiality and integrity**, not merely scramble data.

## 8. Hashing Is Not Encryption

A hash function takes input of arbitrary length and produces a fixed-length digest. For example, `SHA-256` produces a 256-bit (32-byte) digest.

```text
Input (arbitrary length)
       |
       | SHA-256
       v
32-byte Digest
```

Hashing is a **one-way** transformation by design. There is no decryption key to recover the exact original input from the digest.

Java 17 example:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class HashDemo {
    public static void main(String[] args) throws Exception {
        String text = "Hello Java 17";

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(
                text.getBytes(StandardCharsets.UTF_8)
        );

        System.out.println(HexFormat.of().formatHex(hash));
    }
}
```

A SHA-256 digest is 32 bytes, so its hex representation has 64 hex digits.

### 8.1. What Is Hashing Used For?

- Checking whether data has changed compared to a known digest.
- Identifying content in storage systems.
- Serving as a building block in digital signatures and many cryptographic protocols.
- Acting as input to HMAC or key-derivation mechanisms.

A plain digest does not authenticate the sender. An attacker can modify the data and recompute SHA-256. If authentication via a shared secret is needed, use HMAC; if identity verification via a public key is needed, use digital signatures.

### 8.2. Do Not Store Passwords with Plain SHA-256

User passwords have low entropy and are vulnerable to guessing. SHA-256 is very fast, allowing an attacker to test massive numbers of passwords offline if the hash database is compromised.

To store passwords, use a dedicated password-hashing / KDF algorithm such as:

- **Argon2id** (often recommended when a suitable library is available).
- **bcrypt** or **scrypt**.
- **PBKDF2** with HMAC and properly chosen cost parameters, with a unique random salt per password.

Do not invent custom schemes by concatenating a password with a string and running SHA-256 once. A salt is not a secret, but it must be random and unique per password; a KDF also requires sufficiently strong cost parameters. Follow current platform security libraries and guidelines.

## 9. HMAC: Keyed Integrity Checking

HMAC combines a hash function with a **secret key** to produce a message authentication code. Anyone holding the same key can verify whether the data was altered and whether it originated from a party knowing the key.

Example with HMAC-SHA-256:

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

byte[] secret = /* retrieve secret key from secure management */;
byte[] message = "transfer=100".getBytes(StandardCharsets.UTF_8);

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secret, "HmacSHA256"));

byte[] tag = mac.doFinal(message);
String tagHex = HexFormat.of().formatHex(tag);
```

`tagHex` is the hex representation of the HMAC result. Hex is only how the tag is printed; authenticity comes from the HMAC algorithm and the secret key.

When verifying, compare tags using an appropriate constant-time comparison method (for example `MessageDigest.isEqual` on two byte arrays), avoiding custom loops that exit on the first differing byte.

HMAC does not encrypt the content. Recipients can still read `transfer=100`; HMAC detects tampering by anyone lacking the key.

## 10. Combining Steps in the Right Order

A system may use multiple mechanisms in a single pipeline:

### 10.1. Representing Text for Transmission

```text
String
  |
  | UTF-8
  v
byte[]
  |
  | Base64
  v
Base64 string to place in JSON
```

Example:

```java
String text = "Hello Java 17";

String base64 = Base64.getEncoder().encodeToString(
        text.getBytes(StandardCharsets.UTF_8)
);

String jsonValue = "{\\"message\\":\\"" + base64 + "\\"}";
```

This is only an illustrative value example. In real applications, use a JSON library to escape and serialize syntax properly instead of concatenating strings manually.

### 10.2. Encrypting and Representing Ciphertext

```text
Plaintext String
      |
      | UTF-8
      v
  Plaintext bytes
      |
      | AES-GCM + key + fresh IV
      v
 Ciphertext bytes (+ authentication tag)
      |
      | Base64
      v
 String suitable for JSON / text database
```

On the receiving side:

1. Base64 decode to retrieve the envelope bytes.
2. Separate the IV and ciphertext according to the defined protocol.
3. Use the matching key to AES-GCM decrypt and verify the tag.
4. Only after decryption and authentication succeed, interpret the plaintext bytes as UTF-8.

Do not decode Base64 and think the content has been cryptographically decrypted. Base64 only removes the representation layer; AES-GCM is the cryptographic decryption step.

### 10.3. Hashing and Displaying a Digest

```text
Data bytes
     |
     | SHA-256
     v
Digest bytes (32 bytes)
     |
     | Hex
     v
64 hex characters
```

Hashing has no reverse decode step. Hex at the end simply displays the digest as text.

## 11. Comparison Table for Choosing the Right Java 17 API

| Need | Suitable API | Input | Output |
|---|---|---|---|
| String to bytes in UTF-8 | `String.getBytes(StandardCharsets.UTF_8)` | `String` | `byte[]` |
| Bytes to UTF-8 String | `new String(bytes, StandardCharsets.UTF_8)` | `byte[]` | `String` |
| Bytes to hex | `HexFormat.of().formatHex(bytes)` | `byte[]` | `String` |
| Hex to bytes | `HexFormat.of().parseHex(hex)` | `String` | `byte[]` |
| Bytes to Base64 | `Base64.getEncoder().encodeToString(bytes)` | `byte[]` | `String` |
| Base64 to bytes | `Base64.getDecoder().decode(text)` | `String` | `byte[]` |
| AES-GCM encryption | `Cipher.getInstance("AES/GCM/NoPadding")` | `byte[]` + key + IV | `byte[]` ciphertext |
| SHA-256 hash | `MessageDigest.getInstance("SHA-256")` | `byte[]` | `byte[]` digest |
| HMAC-SHA-256 | `Mac.getInstance("HmacSHA256")` | `byte[]` + secret key | `byte[]` tag |

All of the APIs above are included in Java 17. `HexFormat` was added in Java 17; `Base64` has been available since Java 8; `StandardCharsets`, `MessageDigest`, `Cipher`, and `Mac` are core Java APIs.

## 12. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
|---|---|---|
| Vietnamese string has garbled characters | Written with one charset, read with another | Specify UTF-8 on both ends |
| Hex decode throws error | Non-hex characters, odd digit count, or wrong delimiter | Check format; use the matching `HexFormat` |
| Base64 decoder throws error | Wrong variant used or string truncated/corrupted | Identify Basic, URL-safe, or MIME; preserve padding per protocol |
| Base64 string is longer than original data | Normal encoding overhead | Base64 increases size by roughly 1/3 |
| Thinking Base64 protects secrecy | Confusing encoding with encryption | Use proper encryption if confidentiality is needed |
| AES-GCM decrypt reports invalid tag | Wrong key, IV, tampered ciphertext, or mismatched AAD | Verify envelope, key, nonce, and authenticated data; never ignore errors |
| Cannot decrypt AES after restart | Randomly generated key was not persisted securely | Manage keys persistently via KMS/keystore |
| Using SHA-256 to store passwords | Fast hash, vulnerable to brute-force | Use properly configured Argon2id, bcrypt, scrypt, or PBKDF2 |
| Windows path turns into tabs/newlines | Calling `translateEscapes()` on a string with literal backslashes | Do not unescape data that is not formatted as Java escapes |

### 12.1. Hex Bugs Caused by Negative Bytes

Do not format bytes manually with `Integer.toHexString(value)` without handling unsigned values:

```java
byte b = (byte) 0xFF;

System.out.println(Integer.toHexString(b));       // ffffffff
System.out.println(Integer.toHexString(b & 0xFF)); // ff
```

`byte` is sign-extended when widened to `int`. Use `b & 0xFF` or `HexFormat` for accurate byte representation.

### 12.2. Bugs Caused by Missing Base64 Padding

If a protocol uses standard Basic Base64, do not strip `=` padding and expect every decoder to accept all variants. Only use `withoutPadding()` when both sides agree on that convention; for URL-safe, choose `getUrlEncoder()` and `getUrlDecoder()`.

### 12.3. Bugs Caused by Relying on the Default Charset

Do not rely on `new String(bytes)` or `text.getBytes()` for data exchanged between systems. Specifying the charset ensures consistent results across developer machines, servers, and containers.

### 12.4. Mistake of Using Base64 to "Hide" Information

If a string can be decoded without a secret key, the content is not kept secret. Tokens or passwords must not simply be Base64-encoded and stored in public locations.

## 13. Complete Example: UTF-8, Hex, and Base64 on the Same Data

Create file `EncodingDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HexFormat;

public class EncodingDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt - Java 17";

        // Step 1: text -> bytes using UTF-8.
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        // Step 2a: represent the same bytes in hex.
        String hex = HexFormat.of().formatHex(bytes);

        // Step 2b: represent the same bytes in Base64.
        String base64 = Base64.getEncoder().encodeToString(bytes);

        System.out.println("Original: " + original);
        System.out.println("Hex:      " + hex);
        System.out.println("Base64:   " + base64);

        // Step 3a: decode hex -> bytes -> UTF-8.
        byte[] fromHex = HexFormat.of().parseHex(hex);
        String textFromHex = new String(fromHex, StandardCharsets.UTF_8);

        // Step 3b: decode Base64 -> bytes -> UTF-8.
        byte[] fromBase64 = Base64.getDecoder().decode(base64);
        String textFromBase64 =
                new String(fromBase64, StandardCharsets.UTF_8);

        System.out.println("From hex:    " + textFromHex);
        System.out.println("From Base64: " + textFromBase64);
    }
}
```

Compile and run:

```bash
javac --release 17 EncodingDemo.java
java EncodingDemo
```

The exact hex and Base64 values are computed from the UTF-8 bytes of the string. The last two lines should accurately restore the original text.

**Observe:** hex and Base64 are produced from the exact same `byte[]`. They do not perform character encoding; UTF-8 is the step that converts text into bytes. Nor does any step in this example keep the data secret.

## 14. Self-Practice Exercises

### Exercise 1 — Identifying Each Transformation

Given the string `"A"`. Describe the following sequence of operations:

```java
byte[] bytes = "A".getBytes(StandardCharsets.UTF_8);
String hex = HexFormat.of().formatHex(bytes);
String base64 = Base64.getEncoder().encodeToString(bytes);
```

**Answer:**

- `"A"` is text.
- UTF-8 converts it to the byte `0x41`.
- Hex represents that byte as `"41"`.
- Base64 represents that byte as `"QQ=="`.
- Both `"41"` and `"QQ=="` can be converted back to byte `0x41`; they are not ciphertext.

### Exercise 2 — Why Is Base64 Not Encryption?

```java
String secret = "my-token";
String encoded = Base64.getEncoder().encodeToString(
        secret.getBytes(StandardCharsets.UTF_8)
);
```

**Answer:** Anyone can call `Base64.getDecoder().decode(encoded)` to recover the bytes and read the token. There is no secret key or cryptographic algorithm in this operation.

### Exercise 3 — Choosing a Charset

A Java 17 application writes Vietnamese strings to bytes on Windows and a Linux application reads them back. What needs to be done?

**Answer:** Specify the same charset on both sides, typically `StandardCharsets.UTF_8`. Do not let the two environments rely on their default charsets.

### Exercise 4 — Hashing or Encryption?

You need to store a checksum to detect whether a file has been modified, without needing to recover the file from the check value. Which should you choose?

**Answer:** Use a hash function such as SHA-256 to generate a digest. If you need to authenticate the digest against an attacker who could recompute it, use HMAC or a digital signature according to the trust model.

### Exercise 5 — Storing Recoverable Secrets

You need to store a message and read it back later, while preventing anyone without the key from reading the contents. Which should you choose?

**Answer:** Use authenticated encryption such as AES-GCM with secure key management. If the ciphertext needs to be placed in JSON, you can Base64-encode the ciphertext bytes after encryption. Base64 is only a representation layer, not a substitute for encryption.

## 15. Takeaways

- **Charset encoding** converts text to bytes; specify UTF-8 explicitly to avoid environment dependence.
- **Hex** represents each byte as two base-16 digits; useful for debugging and inspecting bytes.
- **Base64** groups three bytes into four characters; useful for transferring binary data over text channels.
- **Hex and Base64 do not provide secrecy.** Anyone can reverse them if they know the format.
- **Encryption** uses a key and cryptographic algorithm to protect content; requires proper key, IV/nonce, and authentication management.
- **Hashing** is a one-way computation; it is not an encryption method that can be decrypted.
- **HMAC** uses a key to authenticate data integrity without hiding the content.
- Layers can be combined: UTF-8 produces bytes, AES-GCM encrypts bytes, Base64 represents ciphertext, then Base64 decode and AES-GCM decrypt on the receiving end.

## Official Java 17 References

- [Java SE 17 API — `java.util.HexFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html).
- [Java SE 17 API — `java.util.Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html).
- [Java SE 17 API — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [Java SE 17 API — `java.nio.charset.CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Java SE 17 API — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html).
- [Java SE 17 API — `javax.crypto.spec.GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html).
- [Java SE 17 API — `java.security.MessageDigest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html).
- [Java SE 17 API — `javax.crypto.Mac`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html).
- [JEP 400 — UTF-8 by Default (Java 18)](https://openjdk.org/jeps/400).
