# 6.4. The `Cipher.init`, `update`, `doFinal` Lifecycle and Output Buffer Sizing

## Objectives

This lesson explains the lifecycle of **`javax.crypto.Cipher`** in the Java Cryptography Architecture (JCA) for symmetric encryption and decryption. The focus is on how data flows through **`init` → `update` → `doFinal`**, how to size output storage with **`getOutputSize`**, and how to properly use array/`ByteBuffer` overloads when the number of bytes emitted by each `update` call is unknown in advance.

After studying this lesson, you will be able to:

- Initialize `Cipher` with the proper encrypt/decrypt mode, key, IV/nonce, and algorithm parameters.
- Process messages in **single or multiple parts** without dropping output from `update` and `doFinal`.
- Distinguish output from padded block ciphers versus AEAD ciphers like AES-GCM, including the authentication tag.
- Allocate buffers using **`getOutputSize(inputLen)`** and track the **actual number of bytes written**.
- Handle `ShortBufferException`, `BadPaddingException`, and `AEADBadTagException`, and avoid reusing IVs/nonces or consuming plaintext before authentication.

The code in this lesson targets **Java 17+**, using `AES/GCM/NoPadding` as the primary example; `AES/CBC/PKCS5Padding` is used solely to illustrate block padding and sizing. **AES-GCM is preferred for data needing both confidentiality and authentication**, with properly managed keys and nonces.

## 1. What States Does a `Cipher` Transition Through?

`Cipher` is a **stateful engine**, not a stateless byte-transformation function. Before processing a payload, you must select a transformation and call `init`:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce));
```

This is a **snippet**, where `key` is an AES `SecretKey` and `nonce` is a valid 12-byte array generated specifically for this operation. You need imports for `javax.crypto.Cipher` and `javax.crypto.spec.GCMParameterSpec`, along with checked exception handling.

`Cipher.getInstance("AES/GCM/NoPadding")` selects a **full transformation** specifying algorithm, mode, and padding. Avoid writing just `"AES"` because default mode/padding interpretation depends on the provider and may be insecure.

Key steps:

```text
Cipher.getInstance(transformation)
       |
       v
uninitialized: NO update/doFinal
       |
       v
init(ENCRYPT_MODE/DECRYPT_MODE, key, params)
       |
       +-- for AEAD: updateAAD(aad) before payload data
       |
       v
update(chunk 1) -> update(chunk 2) -> ... -> update(chunk n)
       |               may emit 0 or more bytes per call
       v
doFinal(last chunk or no additional input)
       |
       +-- processes remaining bytes, padding, or tag
       +-- returns FINAL output; on GCM decrypt, verifies tag
       |
       v
complete: Cipher resets to post-init state if successful
```

- `init(Cipher.ENCRYPT_MODE, ...)` initializes for **encryption**; `init(Cipher.DECRYPT_MODE, ...)` initializes for **decryption**. Do not call `update/doFinal` before `init`; doing so can throw `IllegalStateException`.
- `init` also supports `WRAP_MODE`/`UNWRAP_MODE` for key `wrap/unwrap`, though this lesson focuses on `ENCRYPT_MODE`/`DECRYPT_MODE`.
- `update(...)` processes another chunk of payload. **The number of output bytes from a single call does not necessarily equal the input byte count**; the provider may buffer incomplete blocks or wait for padding or tag verification.
- `doFinal(...)` processes the final portion and finishes the transformation. In AES-GCM, encryption **appends the authentication tag to the output**, while decryption **verifies the tag** and may throw `AEADBadTagException`.
- After a successful `doFinal`, per the API, `Cipher` resets to its **previously initialized state**. However, with AES-GCM, **you must never encrypt a second message using the same key + nonce pair**: call `init` per encryption with a fresh nonce, even though the instance appears ready to continue.
- If `doFinal` throws an exception, do not assume the state remains safe to use; handle the error and **re-initialize** the object for a new message.

Think of **one `init` and a sequence of `update/doFinal` calls as corresponding to one message**. Do not call `init` between chunks of the same message: doing so discards state from earlier chunks.

## 2. Role of Key, IV/Nonce, and AAD

`AES` uses a symmetric key; to decrypt, the receiver needs the **exact same key**, mode, IV/nonce, and associated parameters. For AES-GCM:

- **Key:** e.g. AES-128 or AES-256; must be stored/transmitted via proper key management, **never logged**, and never hardcoded in source code.
- **Nonce/IV:** typically **12 bytes (96 bits)** for GCM. Each encryption under the **same key** must use a **different nonce**. Nonces can be generated via `SecureRandom` for demonstrations or appropriate scales; high-volume production systems need non-repeating nonce allocation designs and key rotation policies.
- **Tag:** e.g. `GCMParameterSpec(128, nonce)` sets a **128-bit = 16-byte** tag. When encryption finishes, `doFinal` appends the tag to the ciphertext; when decryption finishes, `doFinal` checks the tag, and invalid data/key/nonce/AAD causes verification failure.
- **AAD (Additional Authenticated Data):** data that is **authenticated but not encrypted**, such as a protocol header/version. Call `cipher.updateAAD(aad)` **before** any `update/doFinal` processing payload, and the decryptor must supply the **exact same AAD**.
- **Ciphertext+tag:** for GCM, Java `Cipher` emits ciphertext together with the tag; the nonce must be transmitted/stored separately (the nonce is not secret). A simple format might be `version || nonce || ciphertext || tag` with unambiguous length-parsing rules. Do not confuse the tag with the nonce.

**Mandatory GCM warning:** the same key + nonce must never be used for two different encryptions. The fact that `doFinal` "resets" state **does not legitimize** nonce reuse. If ciphertext/nonce/key/AAD or tag is altered, the decryptor must treat the entire message as **invalid** when tag verification fails.

## 3. Overloads of `update` and `doFinal`

| Method | Input | Output | Key Points |
| --- | --- | --- | --- |
| `update(byte[] in)` | Entire array `in` | `byte[]`, **may be `null`** if no block emitted yet | Never discard output when concatenating multiple chunks. |
| `update(byte[] in, int off, int len)` | Slice `[off, off+len)` | `byte[]`, may be `null` | Avoids processing trailing garbage in reused buffers. |
| `update(in, off, len, out, outOff)` | Input slice | Writes directly into `out`; returns **bytes written** | May return 0; may throw `ShortBufferException`. |
| `update(ByteBuffer in, ByteBuffer out)` | Remaining bytes of `in` | Writes into `out`, returns **bytes written** | Advances positions of both buffers on success. |
| `doFinal()` | No new input; finalizes prior `update` data | `byte[]` | Required to flush final block, padding/tag. |
| `doFinal(byte[] in)` | Final input + buffered data | `byte[]` | Can be used **single-shot** when chunking is unnecessary. |
| `doFinal(in, inOff, inLen)` | Final slice | `byte[]` | Also processes state from prior `update` calls. |
| `doFinal(out, outOff)` | No new input | Writes final portion into `out`; returns byte count | Used after `update` calls that wrote into the same output buffer. |
| `doFinal(in, inOff, inLen, out, outOff)` | Final input | Writes final output into `out`; returns byte count | Must have enough space accounting for buffered bytes. |
| `doFinal(ByteBuffer in, ByteBuffer out)` | `in.remaining()` | Writes directly into `out` | Watch position/limit and output space. |

**Unlike `MessageDigest`:** `Cipher.update` can **emit output** immediately. You cannot simply call `update` and take only the final `doFinal` output if you want the full ciphertext/plaintext. When using `byte[]`-returning methods, **collect every non-null array** in order. When writing into an existing buffer, **accumulate the returned byte count** after every call.

Example three-chunk processing diagram with output:

```text
in = [chunk1] [chunk2] [chunk3]
        |        |        |
     update   update    doFinal
        |        |        |
      out1     out2    out3 (includes final block, padding/tag)
        \        |       /
         result = out1 || out2 || out3
```

Never assume `out1.length == chunk1.length` or `out2.length == chunk2.length`. With padded block ciphers, `update` may return `null`/0 because a full block is not ready; with GCM decryption, a provider may buffer plaintext until the tag is verified. Applications **must not publish/consume unauthenticated plaintext** before `doFinal` succeeds.

## 4. What Is `Cipher.getOutputSize(inputLen)`?

The method:

```java
int capacity = cipher.getOutputSize(inputLen);
```

returns a buffer size **large enough to hold the output of the next `update` or `doFinal` call** for `inputLen` input bytes, **accounting for data already buffered by previous `update` calls**, padding, and the AEAD authentication tag. This is a **required upper bound**, **not** the exact byte count guaranteed to be written: the actual output may be shorter.

**Rules to follow:**

1. **You must call `init` before `getOutputSize`**; calling it in an invalid state may throw `IllegalStateException`.
2. When the total message byte length is known upfront, you can compute it **once after `init`, before `update` calls**: `byte[] output = new byte[cipher.getOutputSize(totalInputLength)]`. Then feed chunks and accumulate bytes written via output-buffer overloads.
3. If mid-stream, call `getOutputSize(remainingInputLength)` in the **current state** to size the next operation, including accumulated buffered data; **do not treat bounds computed at another point as if they were actual bytes already emitted**.
4. Use the **actual return counts** from each `update`/`doFinal` call to identify the valid slice of output. **Never** send/store the entire allocated array if only part of it was filled.
5. For `ByteBuffer`, `remaining()` is the available capacity, not total `capacity()`; `output.position()` advances by the bytes written.
6. If the buffer is too small, output-writing methods may throw **`ShortBufferException`**. Per Javadoc, after a buffer-shortage error you can retry that operation with a larger output buffer; however, after other processing/padding/authentication errors, you must explicitly re-initialize state.
7. Do not try to compute how many bytes `update` will emit from `inputLen` alone. Even knowing block size, buffering/padding/AEAD causes **when output appears** to depend on the implementation.

General pattern when **`allInput.length` is known** (snippet inside a method with an initialized `cipher`):

```java
byte[] allInput = /* bytes of a single message */;
int split = allInput.length / 2;
byte[] output = new byte[cipher.getOutputSize(allInput.length)];
int written = 0;

written += cipher.update(allInput, 0, split, output, written);
written += cipher.update(
        allInput, split, allInput.length - split, output, written);
written += cipher.doFinal(output, written);

byte[] actualResult = Arrays.copyOf(output, written);
```

The snippet uses `java.util.Arrays` and handles exceptions; it is not a standalone program. For GCM, call `updateAAD` before payload if the protocol uses AAD. Only `actualResult` consisting of `written` bytes is valid data; trailing space past `written` is not part of the message.

### Example Output Sizes

| Transformation | Input Plaintext | Actual Encryption Output | Reason |
| --- | ---: | ---: | --- |
| `AES/GCM/NoPadding`, 128-bit tag | 0 byte | 16 byte | 16-byte tag, even when payload is empty. |
| `AES/GCM/NoPadding`, 128-bit tag | 3 byte | 19 byte | 3-byte ciphertext + 16-byte tag. |
| `AES/GCM/NoPadding`, 128-bit tag | 16 byte | 32 byte | 16-byte ciphertext + 16-byte tag. |
| `AES/CBC/PKCS5Padding` | 0 byte | 16 byte | Padding fills one block. |
| `AES/CBC/PKCS5Padding` | 3 byte | 16 byte | Padding fills the 16-byte AES block. |
| `AES/CBC/PKCS5Padding` | 16 byte | 32 byte | Even when input is block-aligned, a padding block is appended. |
| `AES/CBC/NoPadding` | 3 byte | Error on finalization | Input is not a multiple of the 16-byte block size. |

The table shows **final output lengths** for the stated configuration and valid input, rather than assuming `getOutputSize` for every provider in every state always equals these exact numbers. With AES-CBC + `PKCS5Padding`, for `P` input bytes and a 16-byte AES block, final encryption output length is `16 × (floor(P / 16) + 1)`. With AES-GCM 128-bit tag, encryption output length is `P + 16`; `NoPadding` **does not mean** no tag.

During decryption, exact plaintext size is known **only after unpadding/tag verification succeeds**. `getOutputSize` provides a buffer size guaranteed sufficient, which may be **larger** than the actual plaintext byte count.

## 5. Complete Example: AES-GCM Across Multiple `update` Calls with Output Buffer

The following program generates a random AES-128 key and 12-byte GCM nonce for **one encryption**. It splits plaintext into two chunks, accumulates bytes written by `update`, finalizes with `doFinal`, and then uses the same key/nonce/AAD to **decrypt and verify the tag**. The decryption Cipher is initialized **separately**. A decryption attempt with different AAD demonstrates authentication failure.

Save **`CipherFlowDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class CipherFlowDemo {
    private CipherFlowDemo() {}

    public static void main(String[] args) throws Exception {
        KeyGenerator keygen = KeyGenerator.getInstance("AES");
        keygen.init(128);
        SecretKey key = keygen.generateKey();

        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        GCMParameterSpec params = new GCMParameterSpec(128, iv);

        byte[] aad = "header:v1".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "Xin chao Cipher!".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, params);
        encrypt.updateAAD(aad);

        byte[] output = new byte[encrypt.getOutputSize(plain.length)];
        int split = 5;
        int used = encrypt.update(plain, 0, split, output, 0);
        used += encrypt.update(plain, split, plain.length - split, output, used);
        used += encrypt.doFinal(output, used);
        byte[] sealed = Arrays.copyOf(output, used);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, params);
        decrypt.updateAAD(aad);

        byte[] recovered = new byte[decrypt.getOutputSize(sealed.length)];
        int received = decrypt.update(sealed, 0, split, recovered, 0);
        received += decrypt.update(sealed, split, sealed.length - split,
                recovered, received);
        received += decrypt.doFinal(recovered, received);

        Cipher wrongHeader = Cipher.getInstance("AES/GCM/NoPadding");
        wrongHeader.init(Cipher.DECRYPT_MODE, key, params);
        wrongHeader.updateAAD("header:v2".getBytes(StandardCharsets.UTF_8));
        boolean rejected;
        try {
            wrongHeader.doFinal(sealed);
            rejected = false;
        } catch (AEADBadTagException expected) {
            rejected = true;
        }

        System.out.println("plainBytes=" + plain.length);
        System.out.println("sealedBytes=" + sealed.length);
        System.out.println("encryptionBoundEnough=" + (output.length >= sealed.length));
        System.out.println("roundTrip=" +
                Arrays.equals(plain, Arrays.copyOf(recovered, received)));
        System.out.println("wrongAadRejected=" + rejected);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CipherFlowDemo.java
java CipherFlowDemo
```

**Expected stdout (verified on JDK 24, Java 17+ compatible code):**

```text
plainBytes=16
sealedBytes=32
encryptionBoundEnough=true
roundTrip=true
wrongAadRejected=true
```

Even though the key and nonce are randomly generated—making **ciphertext bytes differ each run**—these lines do not print ciphertext and stay stable with 128-bit-tag AES-GCM.

**Detailed analysis:**

1. `KeyGenerator` produces a 128-bit AES key; `SecureRandom` produces a 12-byte nonce. The demo **does not print key/nonce**. Real systems must guarantee nonces never repeat under the same key and store/transmit the nonce for decryption.
2. `encrypt.init` sets encryption direction, key, and `GCMParameterSpec(128, iv)`. `updateAAD` comes **before** feeding plaintext bytes.
3. `getOutputSize(plain.length)` allocates a buffer big enough for ciphertext plus tag. `split=5` divides 16 bytes into a first part of 5 and a second of 11; total output is unchanged compared to single-shot encryption.
4. `used += encrypt.update(...)` tracks **output bytes written**, not input bytes. `encrypt.doFinal(output, used)` appends the final portion and tag at the next offset; `Arrays.copyOf(output, used)` strips unused buffer tail.
5. On the receiving side, `decrypt.init` uses the **same key/nonce**, followed by `updateAAD` with the **exact same bytes**. `decrypt.update` may return 0 due to buffering/authentication; do not guess output counts.
6. **Only after `decrypt.doFinal` succeeds** is `recovered` accepted and compared with plaintext. Never expose bytes from `update` to trusted systems before tag verification.
7. `wrongHeader` simulates mismatched AAD (v1 → v2). `doFinal` throws `AEADBadTagException` and the demo prints `wrongAadRejected=true`. Real applications must **reject the entire message**, never processing unauthenticated plaintext.

This is a **single-process** simulation. When transmitting over a network/file, the sender must send the nonce (along with version/format info; the tag is inside `sealed`), and the receiver must obtain the key securely and reconstruct the exact AAD. **No step may re-encrypt a second message using the same key + IV just used**.

## 6. Second Example: Padded CBC and `ByteBuffer`

AES-CBC in this example solely illustrates why **3 input bytes produce 16 output bytes after `doFinal`**, and how output buffers work with the `ByteBuffer` API. **CBC does not authenticate ciphertext**; do not use unauthenticated CBC where tampering must be prevented. For new applications, prefer AES-GCM with managed nonces.

Save **`CipherBufferSizeDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public final class CipherBufferSizeDemo {
    private CipherBufferSizeDemo() {}

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] iv = new byte[16];
        new SecureRandom().nextBytes(iv);
        IvParameterSpec params = new IvParameterSpec(iv);
        byte[] plain = "abc".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/CBC/PKCS5Padding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, params);
        int estimate = encrypt.getOutputSize(plain.length);
        byte[] ciphertext = new byte[estimate];
        int first = encrypt.update(plain, 0, 2, ciphertext, 0);
        int finalBytes = encrypt.doFinal(plain, 2, 1, ciphertext, first);
        int produced = first + finalBytes;

        Cipher decrypt = Cipher.getInstance("AES/CBC/PKCS5Padding");
        decrypt.init(Cipher.DECRYPT_MODE, key, params);
        ByteBuffer input = ByteBuffer.wrap(ciphertext, 0, produced);
        ByteBuffer output = ByteBuffer.allocate(decrypt.getOutputSize(input.remaining()));
        int restoredCount = decrypt.doFinal(input, output);
        output.flip();
        byte[] restored = new byte[output.remaining()];
        output.get(restored);

        System.out.println("plainBytes=" + plain.length);
        System.out.println("cipherBytes=" + produced);
        System.out.println("estimateEnough=" + (estimate >= produced));
        System.out.println("decodedBytes=" + restoredCount);
        System.out.println("inputConsumed=" + !input.hasRemaining());
        System.out.println("roundTrip=" + Arrays.equals(plain, restored));
    }
}
```

```bash
javac -encoding UTF-8 CipherBufferSizeDemo.java
java CipherBufferSizeDemo
```

Exact stdout when the transformation is supported:

```text
plainBytes=3
cipherBytes=16
estimateEnough=true
decodedBytes=3
inputConsumed=true
roundTrip=true
```

Explanation:

- Input `"abc"` is 3 UTF-8 bytes. AES block size = **16 bytes**; JCA's `PKCS5Padding` provides AES-compatible block padding, so the final ciphertext is 16 bytes. `getOutputSize(3)` allocates sufficient space.
- `update(plain,0,2,ciphertext,0)` feeds the first two bytes. Since that is less than one block, the provider may buffer them and return **0 bytes**. `doFinal(plain,2,1,ciphertext,first)` feeds the last byte, adds padding, and finalizes. **Always sum `first + finalBytes`**.
- For decryption, `ByteBuffer.wrap(ciphertext,0,produced)` bounds the exact ciphertext length; do not assume the entire buffer is always full. `ByteBuffer.allocate(decrypt.getOutputSize(input.remaining()))` allocates enough output space; `decrypt.doFinal(input,output)` processes the remaining bytes.
- Input `ByteBuffer` advances to its limit, while `output.position` advances by the bytes written. Call `output.flip()` to switch output to **read mode**, then read only the valid remaining slice. `restoredCount=3`, not the allocated capacity.
- With `AES/CBC/NoPadding` instead, a 3-byte plaintext is not block-aligned and encryption `doFinal` can throw `IllegalBlockSizeException`. Switching to another mode must not be mistaken for automatically providing authentication.

For `Cipher.update(ByteBuffer input, ByteBuffer output)` and `doFinal(ByteBuffer input, ByteBuffer output)`, the two arguments **must not be the same `ByteBuffer` object**; the output buffer must also be writable with sufficient `remaining()`. An undersized output buffer can throw `ShortBufferException`; on success, the API updates `position` according to bytes processed.

## 7. Result Buffering: Right Thinking for Production

### Total Input Known Upfront

For a small/medium in-memory message in an array, the simplest strategy is to **compute the upper bound once**, use the output-buffer overloads, and retain only `written` result bytes. Each `update`/`doFinal` writes sequentially into the array. `CipherFlowDemo` in Section 5 is the complete example.

### Input Arriving in Chunks, Total Length Unknown

When processing large files/streams or continuous data sources, **do not** allocate a single array for the entire ciphertext/plaintext just because `getOutputSize` exists. Allocate an appropriately sized output buffer per step based on current state and incoming chunk size, write completed bytes to a sink, and make sure to retain/write **bytes from `doFinal` as well**. Note further:

- With **GCM encryption**, streaming ciphertext chunks out can work, provided the trailing **tag is written in full** and nonce/AAD follow protocol rules. Each message uses its own nonce.
- With **GCM decryption**, any plaintext emitted from `update` (if any) **is unauthenticated** until `doFinal`. Receiver design must **quarantine** plaintext until the tag succeeds; never execute, display, or overwrite trusted data based on unauthenticated plaintext. For very large messages, spool temporarily to an isolated staging area or use a framing format with per-frame AEAD; never treat streaming decryption as per-chunk authenticated.
- With padded CBC, the final output may yield bytes after unpadding. Check `BadPaddingException`; CBC still requires a separate authentication scheme in sensitive protocols.
- When using `CipherInputStream`/`CipherOutputStream`, read their exception and `close`-finalization contracts carefully. In particular, do not use wrappers that swallow authentication errors and implicitly trust AEAD plaintext; when verifying tags, prefer explicit control around `Cipher.doFinal`.

### When Does `ShortBufferException` Occur?

For example, in `doFinal(input, inOff, len, output, outOff)`, if `output.length - outOff` is insufficient for the resulting bytes, `ShortBufferException` may be thrown. Check offsets/lengths and query `getOutputSize(remainingInputLen)` from the current state before allocating the buffer. `getOutputSize` always includes previously buffered bytes, not just the newly supplied chunk. When an operation fails due to authentication or padding, **never treat partial output as valid data**.

### Common State Mistakes

| Situation | Result | Solution |
| --- | --- | --- |
| `update` before `init` | `IllegalStateException` or invalid-state error. | `getInstance`, then `init` properly. |
| Multiple `update` calls while ignoring their outputs | Ciphertext/plaintext missing leading portion. | Collect all `update` and `doFinal` outputs in order. |
| Assuming `update` returns exact input byte count | Fails with buffering, padding, AEAD. | Use actual returned byte counts and `getOutputSize` to allocate. |
| Allocating output with `new byte[input.length]` | Too small for padding/tag or buffered bytes. | Use `getOutputSize`. |
| Writing the whole allocated array when only partly filled | Appends trailing zeros/garbage, breaking protocol. | Use only `[0,written)` or actual written positions. |
| Omitting `doFinal` | Missing trailing bytes, missing GCM tag, or unverified tag. | Finalize exactly once per message. |
| Reusing GCM key + nonce after `doFinal` | Breaks AEAD security. | Use a **unique nonce per encryption** under the same key. |
| `updateAAD` after payload | `IllegalStateException` or invalid workflow. | Supply all AAD before payload. |
| Consuming GCM plaintext before tag verification | Risks acting on tampered/forged data. | Expose plaintext only after `doFinal` succeeds. |
| Using `Cipher.getInstance("AES")` | Mode/padding left unspecified. | Specify full `AES/GCM/NoPadding`. |
| Assuming `NoPadding` means no extra ciphertext bytes | Forgets the GCM tag. | Include tag in upper bound. |
| Using `ByteBuffer.capacity()` instead of `remaining()` | Misjudges readable/writable space. | Rely on position/limit/remaining. |
| Sharing one Cipher across threads | State may become corrupted/interleaved. | Separate instance per operation. |
| Catching `BadPaddingException` and keeping partial plaintext | Untrusted data, uncertain state. | Discard output, report error, and re-initialize. |

## 8. Exception API and Post-Error State

Exceptions to recognize:

- `NoSuchAlgorithmException` or `NoSuchPaddingException`: transformation unsupported by the chosen provider.
- `InvalidKeyException`: key unsuitable for algorithm or provider.
- `InvalidAlgorithmParameterException`: IV/nonce/mode parameters invalid or rejected.
- `IllegalStateException`: Cipher used in wrong state (uninitialized, wrong mode, wrong AAD order, etc.).
- `ShortBufferException`: insufficient output buffer; for buffer-writing overloads, the API explicitly indicates increasing buffer size.
- `IllegalBlockSizeException`: input fails block-size requirements without padding, or algorithm cannot process input.
- `BadPaddingException`: invalid padding during decryption in padded modes.
- `AEADBadTagException`: tag mismatch during AEAD decryption; this class **extends `BadPaddingException`**. To handle specifically, catch `AEADBadTagException` **before** `BadPaddingException`.

Never treat a tag error as a "close approximation of data"; all decrypted output from a failed attempt must be discarded. Do not assume you can keep calling `update` on an instance that threw an exception in `doFinal` without re-initializing it. Log error types, transformation names, and non-sensitive context; **never log keys, secret plaintext, or details that create a padding oracle**.

## 9. Comprehension Exercises

1. **Change split.** In `CipherFlowDemo`, change `split` from 5 to 1, 8, and 16. Why do output length and `roundTrip=true` stay unchanged? Observe individual byte counts returned by each `update` on your provider and explain why they do not necessarily match input chunk sizes.
2. **Upper bound math.** Encrypting 100-byte plaintext with AES-GCM and a 128-bit tag: explain why ciphertext+tag is 116 bytes, yet code should still call `getOutputSize(100)` before allocating the buffer.
3. **Padding.** For AES/CBC/PKCS5Padding, compute encryption output sizes for 0, 1, 15, 16, 17, and 32 plaintext bytes. Explain why 16 input bytes yield 32 ciphertext bytes.
4. **Change AAD.** Change `header:v1` to `header:v2` only on the decrypt side. Confirm `AEADBadTagException` and explain why no plaintext from that decryption attempt may be used.
5. **Change nonce.** Encrypt a message, save the nonce and sealed bytes. With the same key, try decrypting with a different nonce; explain the roles of nonce and tag. **Do not re-encrypt two messages with the same key + nonce** during the exercise.
6. **Test output buffer.** Intentionally allocate an array smaller than `getOutputSize` to observe `ShortBufferException`; then create/re-initialize a Cipher and allocate a sufficiently large buffer. Explain why tracking each `update` return count is mandatory.
7. **ByteBuffer.** Replace `ByteBuffer.allocate` with a buffer having a narrow limit to see that `remaining` is the true boundary. After `doFinal` succeeds, call `flip` and compare output against plaintext.
8. **Large message design.** When GCM-decrypting a multi-GB file, propose where to temporarily hold plaintext until the tag is verified before publishing. Explain why writing plaintext straight to the trusted destination file during `update` is dangerous.
9. **Workflow mistakes.** Describe the consequences of omitting `doFinal`, calling `init` between chunks, sharing one Cipher across two requests, or truncating the tag.

**Completion criteria:** you accurately describe how `init` selects mode/key/params, `update` produces state-dependent output, and `doFinal` finalizes padding/tag and resets upon success; you use `getOutputSize` and actual written byte counts; and you maintain proper nonces, AAD, and authentication boundaries with AES-GCM.

## Official References (Java 17)

- [`Cipher` API — `init`, `update`, `doFinal`, `getOutputSize`, `updateAAD`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html)
- [`GCMParameterSpec` — nonce and authentication tag length](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)
- [`AEADBadTagException` — AEAD tag verification error](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html)
- [`ByteBuffer` — `position`, `limit`, `remaining`, `flip`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)