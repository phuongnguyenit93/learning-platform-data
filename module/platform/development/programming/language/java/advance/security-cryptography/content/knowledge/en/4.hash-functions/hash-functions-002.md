# 4.2 MessageDigest with SHA-2, SHA-3, and Support Checking

## Learning Objectives

After this lesson, you will be able to: use `java.security.MessageDigest` to hash a byte array or data stream; distinguish SHA-2 from SHA-3 and choose the correct **standard algorithm name in Java**; verify whether an algorithm actually works on the target JVM/provider; read and handle `NoSuchAlgorithmException`; and avoid security mistakes such as treating a digest as proof of authentication or hashing passwords directly.

This lesson covers **cryptographic hash functions** in the JCA architecture, not encryption/decryption. Given the same input byte sequence and the same algorithm, the hash output is deterministic; arbitrarily long input data produces a fixed-length digest. Changing the input data usually causes the digest to change drastically, yet **a digest cannot be used to recover the plaintext** and cannot by itself prove who sent the data.

## 1. SHA-2 and SHA-3: Same Goal, Different Algorithms

Both SHA-2 (standard FIPS 180-4) and SHA-3 (standard FIPS 202) are cryptographic hash families. SHA-2 uses constructions based on compression functions; SHA-3 is based on the Keccak *sponge* construction. Having the same number of output bits does not mean the two algorithms produce the same digest or can be swapped arbitrarily in a deployed protocol.

| Family | Standard name passed to `MessageDigest.getInstance(...)` | Digest (bits) | Bytes | Hex characters |
| --- | --- | ---: | ---: | ---: |
| SHA-2 | `SHA-224` | 224 | 28 | 56 |
| SHA-2 | `SHA-256` | 256 | 32 | 64 |
| SHA-2 | `SHA-384` | 384 | 48 | 96 |
| SHA-2 | `SHA-512` | 512 | 64 | 128 |
| SHA-2 | `SHA-512/224` | 224 | 28 | 56 |
| SHA-2 | `SHA-512/256` | 256 | 32 | 64 |
| SHA-3 | `SHA3-224` | 224 | 28 | 56 |
| SHA-3 | `SHA3-256` | 256 | 32 | 64 |
| SHA-3 | `SHA3-384` | 384 | 48 | 96 |
| SHA-3 | `SHA3-512` | 512 | 64 | 128 |

**Common pitfalls:**

- `SHA-256` belongs to **SHA-2**, whereas `SHA3-256` belongs to **SHA-3**. Both hash values are 256 bits, yet **they differ for the same data**. A system already using SHA-256 cannot simply switch to SHA3-256 when verifying legacy data.
- `SHA-512/256` is **a separately defined SHA-2 variant** (with its own initial values), not equivalent to taking the first 32 bytes of the `SHA-512` result.
- `SHA3-256` is the SHA-3 name standardized under FIPS 202; do not assume outputs labeled `Keccak-256` in other libraries are compatible by default, because padding/domain separation conventions can differ.
- `SHA-1` does **not** belong to the SHA-2 family and is no longer suitable for new applications requiring collision resistance. `MD5` should also not be used to protect integrity against an active adversary.

The names above are Java SE 17 **standard algorithm names**; they describe naming conventions, not a guarantee that **every provider** implements every variant. Actual availability depends on the JDK build, registered providers, and runtime configuration. In particular, do not assume SHA3 is always available in every distribution or every provider.

### Inputs and Outputs Are Actually Bytes

`MessageDigest` processes `byte[]`/`ByteBuffer` or byte chunks passed via `update`; it knows nothing about JSON, Unicode, files, or protocol payloads. You must specify **exactly** how data is converted to bytes: for example, `"abc".getBytes(StandardCharsets.UTF_8)`. Different UTF-8 characters, `LF`/`CRLF` line endings, whitespace, JSON field ordering, or Unicode normalization can produce different digests even when the text looks nearly identical to a human reader.

The return value is a `byte[]`, not a hex string. Hex is just a **representation**: each byte is written as two hex characters. Java 17 provides `HexFormat.of().formatHex(digestBytes)` for consistent formatting.

## 2. Lifecycle of `MessageDigest`

Four core operations:

1. **Select engine/algorithm:** `MessageDigest.getInstance("SHA-256")` requests a provider implementing a JCA service of type `MessageDigest` with the name `SHA-256`.
2. **Feed data:** `update(byte[])`, `update(byte[], offset, length)`, or `update(ByteBuffer)` can be called multiple times, in the exact order of the bytes. This can be replaced with `digest(byte[])` if all content is already in a single array.
3. **Finalize hashing:** `digest()` processes all bytes passed via `update` and returns `byte[]`; `digest(byte[])` also processes that byte array. Both produce the same result if the byte sequence is identical.
4. **State after finalization:** after a `digest()` call, the `MessageDigest` object is reset so it can compute a new digest. Calling `digest()` again without feeding new data will hash the **empty byte sequence**, not repeat the previous result.

Illustrative code **placed inside a method that handles `NoSuchAlgorithmException`**:

```java
byte[] input = "abc".getBytes(StandardCharsets.UTF_8);

// One-shot: pass all bytes at once.
byte[] whole = MessageDigest.getInstance("SHA-256").digest(input);

// Incremental: the order and concatenated bytes must be identical.
MessageDigest md = MessageDigest.getInstance("SHA-256");
md.update((byte) 'a');
md.update("bc".getBytes(StandardCharsets.UTF_8));
byte[] parts = md.digest();

boolean equal = MessageDigest.isEqual(whole, parts); // true
```

The snippet above is only a fragment; imports require `java.security.MessageDigest` and `java.nio.charset.StandardCharsets`. A `MessageDigest` instance holds mutable state across `update` calls, so **do not share a single instance concurrently across multiple threads** without proper synchronization. The simplest approach is to create a separate instance per task. `getDigestLength()` typically returns the output byte length, though per the API it may return `0` if the provider cannot determine it; `digest().length` is the actual length of the computed result.

## 3. Runnable Java 17 Program: SHA-2, SHA-3, and Provider Support

Create the exact file **`HashFamiliesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Provider;
import java.security.Security;
import java.util.HexFormat;
import java.util.List;

public final class HashFamiliesDemo {
    public static void main(String[] args) throws Exception {
        byte[] abc = "abc".getBytes(StandardCharsets.UTF_8);

        for (String algorithm : List.of(
                "SHA-256", "SHA-512/256", "SHA3-256", "SHA3-512")) {
            try {
                MessageDigest digest = MessageDigest.getInstance(algorithm);
                byte[] bytes = digest.digest(abc);
                System.out.printf("%-11s bits=%3d provider=%s%n",
                        algorithm, bytes.length * 8, digest.getProvider().getName());
                if (algorithm.equals("SHA-256") || algorithm.equals("SHA3-256")) {
                    System.out.println("  abc=" + HexFormat.of().formatHex(bytes));
                }
            } catch (NoSuchAlgorithmException e) {
                System.out.println(algorithm + " unsupported");
            }
        }

        MessageDigest incremental = MessageDigest.getInstance("SHA-256");
        incremental.update((byte) 'a');
        incremental.update("bc".getBytes(StandardCharsets.UTF_8));
        byte[] chunked = incremental.digest();
        byte[] oneShot = MessageDigest.getInstance("SHA-256").digest(abc);
        System.out.println("SHA-256 one-shot == incremental: "
                + MessageDigest.isEqual(oneShot, chunked));

        System.out.println("MessageDigest names advertised: "
                + Security.getAlgorithms("MessageDigest").size());
        System.out.println("Providers registering SHA3-256:");
        boolean found = false;
        for (Provider provider : Security.getProviders()) {
            Provider.Service service = provider.getService("MessageDigest", "SHA3-256");
            if (service == null) {
                continue;
            }
            found = true;
            try {
                MessageDigest digest = MessageDigest.getInstance("SHA3-256", provider);
                System.out.printf("  %s -> %s (%d bits)%n",
                        provider.getName(), service.getAlgorithm(),
                        digest.digest(abc).length * 8);
            } catch (NoSuchAlgorithmException e) {
                System.out.println("  " + provider.getName()
                        + ": registered but unavailable");
            }
        }
        if (!found) {
            System.out.println("  none");
        }

        if (args.length > 0) {
            byte[] fileHash = hashFile(Path.of(args[0]), "SHA-256");
            System.out.println("SHA-256(file)=" + HexFormat.of().formatHex(fileHash));
        }
    }

    private static byte[] hashFile(Path file, String algorithm)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance(algorithm);
        try (InputStream in = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                if (count > 0) {
                    digest.update(buffer, 0, count);
                }
            }
        }
        return digest.digest();
    }
}
```

Compile/run on JDK 17 or later (for example, code verified with `javac --release 17`):

```bash
javac --release 17 HashFamiliesDemo.java
java HashFamiliesDemo
```

One run on a JVM whose `SUN` provider supports the tested algorithms produced:

```text
SHA-256     bits=256 provider=SUN
  abc=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
SHA-512/256 bits=256 provider=SUN
SHA3-256    bits=256 provider=SUN
  abc=3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532
SHA3-512    bits=512 provider=SUN
SHA-256 one-shot == incremental: true
MessageDigest names advertised: 13
Providers registering SHA3-256:
  SUN -> SHA3-256 (256 bits)
```

This is **actual stdout from one test configuration**, not a mandatory output on every machine. The provider names, total number of registered names, provider count, and any algorithms reporting `unsupported` depend on the environment. The two hex strings shown above are **standard test vectors for UTF-8 `abc`**; any compliant SHA-256/SHA3-256 implementation must match these two digests.

When run with a file path argument, for example:

```bash
java HashFamiliesDemo document.bin
```

the program also prints `SHA-256(file)=...` for **all bytes** of the file `document.bin`. The file must exist; this is an optional operation when the learner supplies a real file. There is no fixed output line for an arbitrary file because it depends on the file's contents.

### Why Is File Hashing Memory-Safe?

The `hashFile` method reads at most an 8 KiB buffer per loop iteration and calls `update(buffer, 0, count)`. It does not need to hold the entire file in RAM. Passing **the exact `count` bytes read** is important: `update(buffer)` would include leftover old bytes in the buffer when the final read returns fewer than 8192 bytes. The buffer size can be changed without changing the digest value as long as the input byte stream remains the same.

Note: the hash function reads file contents at the time of opening/reading. If another process modifies the file while it is being hashed, the resulting digest does not necessarily represent a consistent snapshot; depending on requirements, you may need to freeze the source, check metadata, or use storage with snapshot support.

## 4. Checking Support: Three Layers of Evidence

### 4.1 Java Standard Names

The **Java Security Standard Algorithm Names** specification lists names such as `SHA-256`, `SHA-512/256`, and `SHA3-256`. Use the exact standard names to reduce reliance on provider-specific aliases. Do not treat a standard name existing in documentation as proof that the running JVM has a provider installed that supplies it.

### 4.2 List of Registered Algorithms

`Security.getAlgorithms("MessageDigest")` returns the set of algorithm names registered by providers for the `MessageDigest` engine at the time of the call. For example, the following snippet **is not a standalone program**:

```java
Set<String> names = Security.getAlgorithms("MessageDigest");
names.stream().sorted(String.CASE_INSENSITIVE_ORDER).forEach(System.out::println);
```

This requires importing `java.security.Security` and `java.util.Set`. It is a runtime **discovery** tool; do not rely on the ordering, names, or count returned as a portable contract across JVMs. A name appearing in the registered list does not yet prove that an instance can be initialized and compute a digest successfully.

### 4.3 Inspecting a Specific Provider and Computing a Digest

`Security.getProviders()` lists the registered providers. Use:

- `provider.getService("MessageDigest", "SHA3-256")` to see whether that provider **advertises** the appropriate service (it may match a primary name or a registered alias). `null` means no service with the requested name was found on that provider.
- `MessageDigest.getInstance("SHA3-256", provider)` to ask **that exact provider** to create an implementation. If successful, further verify the `digest` result against a standard test vector.
- `digest.getProvider().getName()` to identify the provider of the created instance when using an overload that **does not** specify a provider.
- `Security.getProviders("MessageDigest.SHA3-256")` is another filter for matching providers; the API can return `null` if none match, so you must check for null before iterating.

When calling `MessageDigest.getInstance("SHA3-256")` **without passing a provider**, JCA selects from the set of registered providers according to the runtime's selection mechanism. The JDK Reference Implementation also supports algorithm-based priority configuration; do not assume the final selection is determined solely by position in `Security.getProviders()`.

| Verification Level | API | What Can Be Concluded |
| --- | --- | --- |
| Standard name | Standard Algorithm Names | Valid name under the naming standard |
| Global registration | `Security.getAlgorithms("MessageDigest")` | Runtime advertises the name for the engine currently |
| Per-provider registration | `provider.getService(type, name)` | Provider advertises a matching service |
| Implementation instantiation | `MessageDigest.getInstance(name, provider)` | Provider can instantiate an object when requested |
| Correct operation | `digest(input)` compared with test vector | Created implementation computes correctly on test data |

If a provider supplies an alias such as `SHA256` for `SHA-256`, that alias is **not required** to exist in another provider. Use the standard name `SHA-256` for public APIs and system data fields, and explicitly record the algorithm name alongside the digest when exchanging across services: both sides must use the exact same family and variant.

## 5. Application Policy When an Algorithm Is Unavailable

`MessageDigest.getInstance("SHA3-256")` can throw `NoSuchAlgorithmException` if no provider supplies the service. When the algorithm is part of a protocol, data signature, checksum verification, or file format, **fail fast and report the missing capability** or deploy an approved provider. **Do not silently fall back** from `SHA3-256` → `SHA-256` merely because both digests are 256 bits long, or from SHA-256 → MD5/SHA-1 just to "make it run": both break the data contract, and weak fallbacks degrade security.

One way to organize startup checks is to place the required name explicitly in configuration:

```java
static MessageDigest requireDigest(String standardName) {
    try {
        return MessageDigest.getInstance(standardName);
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException(
                "Required MessageDigest unavailable: " + standardName, e);
    }
}
```

The snippet above is an illustrative method to place inside a Java class that imports `MessageDigest` and `NoSuchAlgorithmException`. Select/accept providers according to deployment policy. When FIPS compliance or a hardware provider is required, verify and specify the exact authorized provider; an instance merely "existing" in the JVM does not by itself prove the environment meets compliance requirements.

If a product **genuinely supports multiple choices** under a negotiated protocol, include the algorithm identifier in metadata, restrict the allowlist on both sides, and verify the digest using the exact negotiated algorithm. Do not guess the algorithm from the digest length.

## 6. Integrity, Authentication, and Digest Comparison

Suppose you store the SHA-256 of a release and later verify a downloaded copy. When the digests match, you have evidence that the downloaded bytes match **the content bound to the digest you trust**, within the security limits of the algorithm. However, if an adversary can alter **both the file and the published digest**, a plain digest does not prove origin and does not protect against forgery.

- To check for accidental data corruption or compare against a digest authenticated over a trusted channel: `MessageDigest` is appropriate.
- To **authenticate a message** using a secret key: use a `Mac` engine such as `HmacSHA256` with proper key management; do not build a homemade "MAC" by concatenating a secret string and data and calling `SHA-256`.
- To **authenticate origin using asymmetric keys**: use `Signature` with an appropriate algorithm/mode and verify against a trusted public key.
- To store passwords: **do not use SHA-256/SHA3-256 directly** even with a salt; use a dedicated password-hashing mechanism with a per-password salt and appropriate computational cost (for example, Argon2id, scrypt, bcrypt, or PBKDF2 depending on system requirements).

Compare two digest byte arrays using `MessageDigest.isEqual(expected, actual)` instead of checking references with `==`. This helper compares byte contents; it **does not turn an unkeyed digest into a signature/MAC** and does not solve trust issues for the expected digest. Do not convert a digest to a `String` using a text charset; use `HexFormat` or Base64 when storing or transmitting textually.

## 7. Common Errors and Root-Cause Diagnosis

| Symptom | Likely Cause and Fix |
| --- | --- |
| `NoSuchAlgorithmException: SHA3-256` | No provider in the current runtime supplies the requested name; check the standard name, `Security.getProviders()`, and test `getInstance` per provider |
| `SHA3_256` or `SHA-3-256` not recognized | Wrong standard name; in JCA use `SHA3-256` (no hyphen between `SHA` and `3`) |
| Two programs hashing the "same text" output different hex strings | Compare UTF-8 **bytes**, newlines, BOM, Unicode normalization, whitespace characters, and algorithm names |
| `SHA-512/256` does not match the first 256 bits of `SHA-512` | These are two distinct algorithms; `SHA-512/256` has its own specification |
| Hashing a large file runs out of memory | Switch from `Files.readAllBytes` to streaming `InputStream` + buffered `update` |
| Second hash result is unexpected | `digest()` resets state; you must feed new data for the next hash. Do not share stateful instances across threads |
| `SHA3-256` appears in the list but `getInstance` fails | Advertising a name does not guarantee successful instantiation; test the provider-specific overload and inspect exceptions |
| Hash matches yet the sender is still untrusted | An unkeyed digest provides no authentication; authenticate the digest via a trusted channel or use a MAC/signature |

### Pre-Production Checklist

1. Confirm the required algorithm using its **standard name**, its availability in the exact target JVM/container, and the required provider policy.
2. Standardize how **input bytes** are produced (charset, serialization format, newlines, field order, canonicalization) on both the producer and verifier sides.
3. Use fixed test vectors: SHA-256(UTF-8 `abc`) = `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`; SHA3-256(UTF-8 `abc`) = `3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532`.
4. For large data, use incremental `update` and measure memory usage; preserve byte order and pass the exact byte count actually read.
5. When a required algorithm is missing, fail clearly at startup or point of use; never switch algorithms implicitly.
6. Store/transmit the algorithm identifier alongside the hash when data crosses system boundaries; remember that a digest does not prove authenticity if the digest's source is untrusted.

## 8. Self-Practice Exercises

1. Run the program, record the supported SHA-2/SHA-3 names, the provider chosen for each name, and the set of providers advertising `SHA3-256`.
2. Modify the `update` block to pass each character `a`, `b`, `c` in three separate calls, and verify whether the `SHA-256` value remains identical; then reverse the order of two chunks to observe the digest change.
3. Create two UTF-8 files differing only in their trailing newline, and run the program with each path. Explain why the hashes differ.
4. Try `MessageDigest.getInstance("SHA3-256", provider)` for each provider on your machine and distinguish **"provider advertises a service"** from **"instance passes the test vector"**.
5. Design metadata for a system that verifies files sent over a network: how should it store the hash, algorithm name, input-byte construction rules, and **the digest trust mechanism**?

## 9. References

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): standard SHA-2/SHA-3 names, digest sizes, and support requirements.
- [Java SE 17 — `MessageDigest` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `getInstance`, `update`, `digest`, `reset`, and `isEqual`.
- [Java SE 17 — `Security` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html): `getAlgorithms`, `getProviders`, and provider filtering.
- [Java SE 17 — `Provider` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Provider.html): `getService`, `getServices`, and provider-supported algorithm names.
- [NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final): SHA-2 variants.
- [NIST FIPS 202](https://csrc.nist.gov/pubs/fips/202/final): SHA-3 specification.
