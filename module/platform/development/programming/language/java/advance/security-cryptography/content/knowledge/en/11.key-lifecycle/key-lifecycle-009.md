# 11.9. Limitations of Keeping Secrets in `byte[]`, `String`, Heap Dumps, and Error Messages

In Java application cryptography, many security failures **do not lie in AES, RSA, or HMAC**, but occur after a key, password, or plaintext enters the process: the secret value gets converted into a `String`, copied into hard-to-control arrays, lingers on the heap longer than intended, appears in a heap dump, or is accidentally written to logs or error messages.

A program can use textbook-correct cryptographic algorithms and still expose its key via a statement like:

```java
logger.debug("AES key: " + keyAsHex);
```

Or leak a secret when constructing an error from user-submitted data:

```java
throw new IllegalArgumentException("Invalid token: " + token);
```

**Core principle:** in a JVM with automatic memory management, we can **reduce the number of copies, lifetime, and exposure surface** of secrets, yet we cannot claim “all traces are completely erased” merely by calling `Arrays.fill(secret, 0)` or dropping a reference. Practical security combines lifecycle management, appropriate APIs, runtime/observability configuration, operational permissions, incident controls, and a threat model.

## 1. Learning Objectives and Scope

After this lesson, you will be able to:
- Distinguish **secret representations** across `byte[]`, `char[]`, `String`, `SecretKeySpec`, `ByteBuffer`, and JCA/JCE objects.
- Explain why `String` is unsuitable when an application wants to actively clear a secret value from a buffer.
- Know exactly **which buffer** `Arrays.fill(...)` and `PBEKeySpec.clearPassword()` clear, while recognizing copies outside the caller's control.
- Identify data that can be captured by **heap dumps, crash dumps, core dumps, profilers, debuggers, logs, tracing, error reporting, and telemetry**.
- Design paths for passwords, AES keys, tokens, ciphertexts, and plaintexts with **least privilege, minimal lifetime, and safe error handling**.
- Distinguish **public error responses** from **internal diagnostics**; avoid leaking keys, secrets, tokens, and oracle-style flaws via messages or response timing.
- Run a Java 17+ example demonstrating that **clearing a caller's array differs from erasing every secret copy**, and apply a testing/operations checklist.

This lesson belongs to the **key lifecycle** topic: from key creation/receipt, usage, derivation, copying, temporary storage, logging, and error handling until no longer needed. It is not a guide to building a custom secure-memory allocator or claiming Java/JVM automatically guarantees zeroization at every layer.

## 2. Why Do Secrets Easily Escape “Where We Think They Are”?

A key can travel through multiple layers:

```text
Secret source                  Java application                 JVM / Infrastructure
------------------------       -----------------------------    -----------------------------
Vault / KMS / HSM ----+-----> byte[] / char[] input --------> heap, stack, GC regions
Console / login -------+       String / parser / serializer --> extra objects, char/byte copies
Random key generator ---+       SecretKeySpec / PBEKeySpec ---> JCE/provider copies
                               Cipher / Mac / KDF ----------> native/JNI/provider buffers
                               HTTP request/response -------> framework buffers
                               Logging / exception ---------> log files, traces, APM
                               Debugging / profiling -------> heap dumps, crash artifacts
                               Retry / cache / queue -------> longer lifetime and replicas
```

An application often only knows for sure that it holds a reference such as `byte[] secret`. Yet after calling `SecretKeySpec`, `Cipher.init`, an HTTP library, a JSON serializer, or a logger, **additional copies** may exist across multiple memory regions and systems.

For example, when receiving a token from a client as header text, the application may end up holding:
1. Network byte buffers.
2. A `String` created by the HTTP framework.
3. A new `String` from trimming/substringing or concatenating headers.
4. A request object carrying the token.
5. A log message or stack trace containing the token.
6. A copy inside a trace collector.

Clearing a variable at step 4 **does not mean** copies 1, 2, 3, 5, and 6 were erased. Therefore, the pragmatic rule is **keeping secrets out of layers that do not need secrets**, especially logging, tracing, exception messages, and data serialization.

### 2.1. What Counts as a Secret?

| Data | Sensitivity | Risk If Exposed |
| --- | --- | --- |
| AES key, HMAC key, RSA private key, key seed | **Secret** | Enables decryption or MAC/signature forgery within key scope |
| Password/passphrase, PIN, recovery code | **Secret** | Login, key guessing, account takeover |
| Access token, refresh token, session cookie, API key | **Bearer secret** | Session hijacking or API abuse |
| Unwrapped CEK/DEK, traffic/session key | **Secret** | Access to session/file-protected data |
| Decrypted plaintext | **Data-sensitive** | Leakage of user/business content |
| Salt, IV/nonce, public key, public certificate | Usually **non-secret** | Still requires correctness checks and context binding |
| Password verifier, encrypted file, KDF metadata | Not a plaintext secret, yet **security-sensitive** | Aids offline guessing attacks and privacy leaks |
| Logs/traces with identifiers | Depends on threat model and personal data | Activity correlation, sensitive inference, metadata leaks |

Never assume “it is hashed so it is no longer sensitive,” or “nonces are public so every log containing nonces is harmless.” Protection also depends on dataset context, storage scale, and record linkability.

## 3. `String`: Convenient Yet Impossible to Erase Intentionally

In Java, `String` is an **immutable** type (at the API level). When you have:

```java
String password = "...";
```

you have no safe public API to overwrite the underlying string bytes inside the JVM. Assigning:

```java
password = null;
```

only drops one reference in your code. It **does not guarantee** the old memory is zeroed immediately; the garbage collector governs reclamation timing, and memory may retain traces or copies.

### 3.1. Why Does `String` Create Extra Difficulties?

- `String` is immutable, so there is no public API to “erase a password.”
- Concatenating, formatting, parsing, encoding, logging, or passing strings through frameworks can spawn **many extra objects/buffers**.
- String literals in source can enter the constant pool/interning table; **never hard-code production secrets** as literals.
- Modern JVMs optimize string storage, such as Compact Strings in HotSpot, and internal representations can vary. Never rely on whether `String` holds `char[]` or `byte[]` internally to mutate it via reflection or `Unsafe`.
- `StringBuilder` can retain a backing buffer and allocate a new `String` on `toString()`; using a builder for “easier clearing” does not solve the whole problem.
- When a library only accepts `String`, converting from `char[]` already creates a hard-to-erase copy. Evaluate API boundaries instead of assuming one conversion step is harmless.

**Avoid these operations with secrets:**

```java
// DO NOT USE in production code:
String passwordText = new String(passwordChars);
String secretAsHex = java.util.HexFormat.of().formatHex(aesKeyBytes);
System.out.println("Authorization: Bearer " + token);
throw new RuntimeException("Failed with password=" + passwordText);
```

These are **anti-patterns** to recognize, not examples to run. Printing/logging/formatting secrets to text increases persistence and exfiltration risk.

### 3.2. How Much Better Is `char[]` Than `String`?

`char[]` lets the caller actively overwrite its elements:

```java
char[] password = /* input from controlled source */;
try {
    // Use password with an API accepting char[].
} finally {
    java.util.Arrays.fill(password, '\0');
}
```

This offers a real practical benefit: **the array you own** can be overwritten after use. However, it does not guarantee:
- That a library did not copy the array.
- That JIT/compiler, GC, or OS did not retain traces elsewhere.
- That the password never existed as a `String` in an earlier layer.
- That a heap dump or logger did not capture a copy before clearing.

`char[]` helps primarily when **the entire processing path** avoids converting the secret into strings or logs and bounds lifetimes properly. A password read first as a `String` and then converted to `char[]` does not “erase” the original `String`.

### 3.3. Password Input in Java

In a command-line app with a real console, `Console.readPassword()` returns `char[]`, avoiding some common `String` creation paths:

```java
java.io.Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Secure console unavailable");
}
char[] password = console.readPassword("Password: ");
if (password == null) {
    throw new IllegalStateException("No password supplied");
}
try {
    // Use password with an API accepting char[].
} finally {
    java.util.Arrays.fill(password, '\0');
}
```

This is an **API illustration snippet**, not a standalone program; `System.console()` is often `null` inside IDEs, many container environments, or piped streams. Do not automatically fall back to reading passwords with `Scanner.nextLine()` without reviewing application security requirements.

With HTTP, mobile, desktop UIs, or SDKs, frameworks have often already decoded inputs into `String`. Control **request logging, tracing, retention, memory lifetimes**, and transport layers; you cannot claim the caller “never held a `String`” if an upstream framework created it.

## 4. `byte[]`: Overwritable, Yet Not Equivalent to Erasing All Copies

`byte[]` is the common representation for AES keys, nonces, plaintext, ciphertext, HMAC outputs, and key derivation outputs. For a program-owned secret byte array:

```java
byte[] secret = /* securely obtained secret bytes */;
try {
    // Use secret.
} finally {
    java.util.Arrays.fill(secret, (byte) 0);
}
```

Once `Arrays.fill` finishes, elements of **that exact passed array** are set to zero under the normal Java memory model. Yet this is not a system-wide guarantee that all secret material is gone.

### 4.1. Reasons Copies Can Still Exist

1. **Constructors may copy.** For example, `SecretKeySpec(byte[], algorithm)` stores a copy of the key bytes. Zeroing the input array does not destroy the created secret key object.
2. **`getEncoded()` may return a copy** of exportable keys; callers must manage/clear the returned array. For some providers/HSMs, `getEncoded()` returns `null` because the key is non-exportable.
3. **`Cipher`, `Mac`, `KeyAgreement`, and providers** may retain data inside objects or native memory; APIs do not promise to wipe every copy when the caller clears its array.
4. **`Arrays.copyOf`, `clone`, `ByteArrayOutputStream.toByteArray()`** allocate new arrays. `toByteArray()` normally creates a copy while the stream's internal buffer can persist.
5. **String/hex/Base64 encoding** creates text objects that can outlive the original buffer. Never use such encodings just to “debug whether the key looks right.”
6. **GC, stack, and JIT** may relocate, rearrange, or retain data under runtime rules. Best-effort zeroization in Java does not defend against an adversary able to read arbitrary memory dumps at any time.

**True statement:** “I zeroized the `secret` array I held.”  
**Unsupported claim:** “Afterward, zero key bytes remain anywhere in the process, swap, heap dumps, or provider memory.”

### 4.2. Use `finally` to Shrink the Exposure Window

Do not clear secrets only at the end of the happy path:

```java
byte[] keyBytes = loadSensitiveKeyBytes();
doCrypto(keyBytes); // May throw an exception.
java.util.Arrays.fill(keyBytes, (byte) 0);
```

If `doCrypto` throws an exception, the trailing clear never runs. Safer pattern:

```java
byte[] keyBytes = loadSensitiveKeyBytes();
try {
    doCrypto(keyBytes);
} finally {
    java.util.Arrays.fill(keyBytes, (byte) 0);
}
```

This remains **pseudocode using illustrative functions** `loadSensitiveKeyBytes()` and `doCrypto()`, not a standalone Java class. The useful takeaway is placing cleanup inside `finally`.

Also manage lifetimes tightly:
- Fetch keys **as late as possible** right before use.
- Avoid holding keys in static fields, long-lived singletons, session objects, or global caches unless backed by an explicit threat model and lifecycle.
- Avoid creating unnecessary copies; restrict secret propagation across service layers.
- When a key is no longer needed, close provider sessions/handles per supported APIs.
- Clear sensitive plaintext buffers per policy too, not just key bytes.

### 4.3. `Arrays.fill` Is Best Effort, Not Provable Secure Erasure

In a managed JVM runtime, beyond visible arrays, data can linger in copies, registers, stacks, native state, swap, or earlier dumps. Compiler/JIT optimizations and garbage collection further prevent pure Java from guaranteeing **physical memory erasure**.

When a threat model demands OS/hardware-level zeroization, do not pretend `Arrays.fill` provides it. Evaluate secure-memory facilities, HSM/KMS, suitable providers, memory locking where feasible, debug/dump permissions, and non-exportable key designs. Native solutions still cannot erase copies the application already created or secrets already written to logs.

Some APIs expose `Destroyable.destroy()` or `isDestroyed()`, yet **not every `SecretKey`, `PrivateKey`, or provider implements real destruction the same way**. Check implementation docs and behavior, handle errors, and never equate `destroy()` with destroying a key inside an HSM or backup.

## 5. `SecretKeySpec` and Copying Key Material

In JCA/JCE, a common pattern is:

```java
byte[] keyBytes = /* AES or HMAC key bytes */;
javax.crypto.spec.SecretKeySpec key =
    new javax.crypto.spec.SecretKeySpec(keyBytes, "AES");
java.util.Arrays.fill(keyBytes, (byte) 0);
```

At this point **the caller's key array has been cleared**, yet `SecretKeySpec` still holds the key material needed to run cryptographic operations. That is not a bug: its constructor maintains its own copy of the key material.

Consequences:

- Do not treat zeroing `keyBytes` as destroying all `SecretKeySpec`/provider state.
- Avoid keeping `SecretKeySpec` alive longer than necessary, especially in application-scoped objects.
- Never call `key.getEncoded()` just to print hex or compare; it allocates yet another byte copy of the secret.
- If non-exportable keys are required, use provider mechanisms, `KeyStore`, PKCS#11/HSM, or KMS with proper handle APIs. **Never assume** every Java `SecretKey` is non-extractable; `SecretKeySpec` is not an HSM key.
- Govern rotation, expiration, revocation, and backups via your key management system, never by relying on GC reclaiming objects.

### 5.1. Why Does Clearing the Source Array Not Stop `Mac` from Working?

`SecretKeySpec` copies the input key value. If the application clears the original array and then runs:

```java
javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
mac.init(secretKeySpec);
byte[] tag = mac.doFinal(messageBytes);
```

MAC computation still works normally because the key object retains the required material. This is a key point in the runnable example in Section 10: **a still-usable key object** proves you cannot claim “all copies of the key were erased.”

Conversely, the fact that `Mac` can use the key object afterward **does not prove** `Mac` itself caches the key forever. Lifetime depends on scope, implementation, and how the application holds references.

## 6. `PBEKeySpec` and Password KDFs: Frequently Overlooked Copies

Java provides `PBEKeySpec` for using a `char[]` password with a salt and key-derivation parameters:

```java
char[] password = /* user input */;
byte[] salt = /* random salt */;
javax.crypto.spec.PBEKeySpec spec =
    new javax.crypto.spec.PBEKeySpec(password, salt, 100_000, 256);
```

Per API contract, the `PBEKeySpec` constructor copies the password data. Therefore:
- Zeroing the caller's `password` array **does not prevent** `spec` from deriving keys.
- Once finished, call `spec.clearPassword()` to clear the copy owned by `PBEKeySpec`.
- `spec.getPassword()` returns a **fresh copy**; the caller must manage/clear that copy if called.
- `SecretKeyFactory.generateSecret(spec)` and `getEncoded()` create additional outputs/key material; manage the lifetime of every output object and array, not just the input password array.
- `PBEKeySpec` takes `char[]`, yet a provider may convert the password into internal bytes; clearing `spec` does not prove all provider copies are wiped.
- Salts are usually non-secret, yet must be stored/preserved accurately to verify passwords or re-derive keys per KDF profile.

Lifecycle illustration:

```text
Caller char[] password
   |
   +-- PBEKeySpec constructor -> internal password copy
   |                                   |
   |                                   +-- SecretKeyFactory -> derived key material
   |                                                                |
   v                                                                v
Caller Arrays.fill(password, '\0')                     Derived byte[] / SecretKey / provider
             |                                                      |
             v                                                      v
Own array cleared                              Must separately scope/clear as supported
                                     |
                          spec.clearPassword() for spec's copy
```

For password storage, use dedicated password-hashing schemes and vetted libraries per deployment requirements; `PBKDF2WithHmacSHA256` in the example only illustrates the API and copies. Never use plain SHA-256 as a password verifier, and never treat a publicly stored PBKDF2 verifier as a reusable AES key.

### 6.1. What If the Password Arrives from the Framework as a `String`?

If an HTTP framework delivers a password as a `String`, converting it to `char[]` and wiping the array **does not wipe the already-allocated `String`**. When you cannot control the entire upstream path, mitigate risk by:
- Never logging request bodies, form fields, or Authorization headers containing passwords.
- Never storing passwords in long-lived user/session DTOs, exception objects, or async task queues.
- Never placing passwords in templates/error messages, metrics labels, or tracing span attributes.
- Performing verification/derivation immediately in a narrow scope, avoiding caches.
- Restricting access to heap dumps, debuggers, and process memory.
- Separating auditable metadata from secret data; log status, correlation IDs, and error categories instead of password values.

Designing clean boundaries usually matters far more than debating “`String` vs. `char[]`” if the surrounding pipeline replicates the secret everywhere.

## 7. `ByteBuffer`, Off-Heap, and Native Memory: Not Safe by Default

`ByteBuffer` can be heap-backed or direct/off-heap. Both require distinguishing **position management** from **overwriting data**.

Example:

```java
java.nio.ByteBuffer buffer = java.nio.ByteBuffer.allocateDirect(1024);
buffer.put(secretBytes);
buffer.clear(); // Resets position/limit only. Does NOT zero memory!
```

`clear()` in the buffer API **does not** erase contents; it prepares the buffer for writing/reading from the start. Similarly, `flip()` and `rewind()` manipulate cursors/bounds with zero wiping guarantees.

If an app owns a mutable buffer and wants to zero it:
- Overwrite **the exact full sensitive region** via supported operations, accounting for position, limit, slices, and shared-memory views.
- Account for copies in heap, native allocations, JNI/FFI, and provider state.
- Handle deallocation lifetimes; off-heap memory does not defend against crash dumps, process memory reads, swap, or privileged debuggers.
- Never rely on reflection/`Unsafe` to mutate `String` or JCE class internals.
- For high-assurance needs, evaluate audited native/secure-memory libraries and OS policies; being direct memory **does not turn RAM into an HSM**.

Even when a direct buffer is zeroed, the secret may have passed through a `byte[]` to call an API or been copied by a provider; always trace the full **data flow**.

## 8. Heap Dumps, Crash Dumps, Profilers, and Infrastructure Copies

### 8.1. What Can a Heap Dump Contain?

A heap dump is a point-in-time snapshot of Java objects on the heap. Depending on the JVM and runtime state, it can contain:
- `String` instances still holding tokens, passwords, or text-encoded secrets.
- `byte[]` and `char[]` arrays containing keys, passwords, nonces, plaintexts, or other sensitive data.
- Request/response DTOs, cache entries, message payloads, HTTP headers, and exception objects.
- `SecretKeySpec` objects, KDF contexts, buffers, and live data structures.
- Indirect data linking users, sessions, tenants, hostnames, and security operations.

A heap dump **does not necessarily** capture native memory, registers, stacks, or all system copies, yet what it can hold is more than enough to classify it as a **sensitive asset**. Never attach production heap dumps to tickets, chat, or external tools without authorization, protection workflows, and proper redaction.

### 8.2. Conditions That Trigger Dumps

JVMs may be configured to emit heap dumps on out-of-memory errors, e.g., `-XX:+HeapDumpOnOutOfMemoryError` and `-XX:HeapDumpPath=...`. Admin/diagnostic tools can also trigger heap dumps with sufficient privileges. Crash dumps, core dumps, or OS memory snapshots have broader scopes and **can** include memory outside the Java heap.

Practical risks:
- Containers writing dumps onto shared volumes, object stores, or auto-backed-up directories.
- Crash reporting/telemetry uploading artifacts to services outside the trust boundary.
- A developer with prod debug access downloading a dump onto an unencrypted laptop.
- Dumps lingering post-incident with no TTL, access auditing, or deletion process.
- Log files/tickets carrying stack traces or command-line arguments exposing configs/credentials.

**Do not treat dumps as “evil” and ban all debugging.** Heap dumps are valuable for diagnosing memory leaks and incidents. The right approach is treating them as sensitive data: least-privilege access, encrypted storage, short retention, access auditing, authenticated transfer, redaction where feasible, controlled deletion, and never exporting to unauthorized environments.

### 8.3. Operational Configurations to Consider

1. **Access:** restrict who can attach debuggers/profilers or trigger/download dumps; review OS/container/hypervisor privileges.
2. **Storage:** store dumps in directories/volumes with tight filesystem permissions, encryption at rest, and dedicated key management where appropriate.
3. **Transfer:** use authenticated encrypted channels; avoid public dump URLs or long-lived links.
4. **Retention:** retain only as long as needed for investigation; enforce automated deletion and auditing.
5. **Automation:** know which agents can capture and upload diagnostic bundles; disable unnecessary sensitive collection.
6. **Incident response:** if evidence shows keys/passwords/tokens entered an uncontrolled dump, evaluate **rotation/revocation** and data impact per scope.
7. **Backups:** check whether dumps are swept into backups or DR snapshots; deleting the primary file does not always delete backup copies.
8. **Testing:** use fake canaries, staging environments, and approved tools to test exposure risk; never capture real production secrets just to prove a point.

A heap dump is a **point-in-time snapshot**. Zeroing a `byte[]` after the snapshot does not erase the captured artifact. One logging bug or dump export can stretch a secret's lifetime from milliseconds in RAM to months on storage.

### 8.4. Heap Dumps vs. Logs and Stack Traces

- **Heap dumps:** can capture raw object state even when code never intentionally logs keys.
- **Logs:** emitted by apps/frameworks logging requests, errors, `toString()` outputs, or diagnostics.
- **Stack traces:** include stack frames and exception messages/causes; if an exception embeds sensitive data in its message, logging the stack trace broadcasts it.
- **Distributed tracing/APM:** can copy HTTP headers/bodies, SQL parameters, and baggage/span attributes into external systems.
- **Metrics:** high-cardinality labels/tags or labels carrying tokens/user IDs can leak onto dashboards and persist long-term.

In practice, define policies for **every observability channel**; silencing one logger does not close leak paths through tracing, error reporting, or crash artifacts.

## 9. Error Messages: Where Secrets Often Escape the Process

### 9.1. Error Messages Must Never Contain Secrets

Never do this:

```java
// Anti-pattern: DO NOT use.
throw new IllegalArgumentException("Invalid API key: " + apiKey);
throw new SecurityException("Expected=" + expectedMac + ", actual=" + receivedMac);
logger.error("Failed to decrypt " + plaintext, exception);
```

Risks:
- Exception messages flow into access logs, app logs, APM, alerts, and support tickets.
- Frameworks may serialize exception messages directly into HTTP responses.
- Exception `toString()` and stack traces include messages and nested causes.
- Logging an object via `{}` can invoke a `toString()` exposing sensitive fields.
- Exceptions thrown inside async tasks, retries, or queues may be persisted or serialized by infrastructure.

**Keep secrets out of exceptions from the start.** “It is only an internal log” is never an excuse to embed passwords, keys, or tokens in exception messages and hope they stay contained.

### 9.2. Separate Public Errors from Internal Diagnostics

To untrusted clients, return a **stable error code and generic message**:

```json
{
  "code": "CRYPTO_OPERATION_FAILED",
  "message": "The requested operation could not be completed."
}
```

For login logic, a uniform message like `AUTHENTICATION_FAILED` is appropriate on wrong credentials. For encryption/decryption, never return “AES key valid but GCM tag failed at byte X,” “private key unwrapped successfully,” or sensitive parameter values to external callers.

In **access-controlled internal telemetry**, you may record:
- Random correlation/request ID.
- Non-sensitive component/operation name (e.g., `decrypt-document`).
- Allowlisted error code (e.g., `AUTH_TAG_INVALID`), severity, and occurrence count.
- Timestamp, protocol version, and non-sensitive key identifier **if policy allows**.
- Reviewed stack traces containing zero tokens, passwords, or decrypted data.

Never log:
- AES/private/HMAC/traffic keys, seeds, session cookies, bearer tokens, refresh tokens, passwords.
- Raw `Authorization`, `Cookie`, `Set-Cookie` headers, or secret form fields.
- Plaintext from confidential files, KDF-derived keys, or unencrypted key-wrap material.
- Exception causes or object dumps unless verified that messages and `toString()` contain no secrets.

Never automatically turn `keyId` or hashes of sensitive fields into public identifiers: they can still leak metadata, correlate activity, or assist guessing on low-entropy inputs.

### 9.3. Distinguish Errors for Operations Without Creating Oracles

An API needs enough signal for maintenance, yet cryptographic errors can become an **oracle** if an attacker can observe differences in:
- Returned messages: “RSA unwrap succeeded” vs. “AES tag invalid.”
- HTTP status/body depending on whether a password exists, a token prefix matches, or which private key was chosen.
- Response timing varying by validation stage or failure point.
- Response size, connection resets, or retry counts.
- Timing of secret comparison via standard string equality.

Therefore, design error mapping around the **protocol's threat model**, not merely hiding text in responses. Sensitive failure classes may need collapsing at public APIs, request bounds, consistent handling timing, rate limiting, and policy-enforced key checks. This **does not mean** you can trivially make an entire HTTP stack constant-time; use vetted cryptographic libraries and avoid obvious secret-dependent branches.

For example, if an API checks an HMAC and uses:

```java
if (expectedTagHex.equals(receivedTagHex)) { ... }
```

standard string comparison is not designed as a timing-safe secret tag comparison. **Decode the exact wire format, check lengths, and use a constant-time byte comparison API** such as `MessageDigest.isEqual(...)` where appropriate. Likewise, never “try multiple algorithms/keys until one works” without version/policy, as that invites algorithm/key confusion and multiple observable failure paths.

## 10. Java 17+: Verifying Memory Limitations and Safe Error Reporting

This runnable example **does not attempt to inspect heap dump contents** (which vary by JVM, GC, and timing), but verifies assertions observable through the API:

1. The caller's `char[]` password array is cleared; `PBEKeySpec` can still run the KDF because it owns a copy.
2. `PBEKeySpec.clearPassword()` blocks reading the password via `getPassword()` afterward.
3. The array holding the derived KDF output is zeroed in `finally`.
4. The source byte array passed to `SecretKeySpec` is cleared, yet **the key object remains usable** for HMAC. This proves clearing a source buffer does not erase all key material.
5. A public error helper returns only an **allowlisted error code**, never leaking raw provider messages externally.

Create file **`SecretMemoryDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public class SecretMemoryDemo {
    static boolean zeroed(char[] value) {
        for (char c : value) {
            if (c != '\0') return false;
        }
        return true;
    }

    static boolean zeroed(byte[] value) {
        for (byte b : value) {
            if (b != 0) return false;
        }
        return true;
    }

    static String publicError(Exception ignored) {
        return "CRYPTO_OPERATION_FAILED";
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        // Public fixture for demonstration only.
        // Do not hardcode real passwords in source.
        char[] password = {'d', 'e', 'm', 'o', '-', 'p', 'a', 's', 's'};
        byte[] salt = new byte[16];
        random.nextBytes(salt);

        PBEKeySpec spec = new PBEKeySpec(password, salt, 100_000, 256);
        Arrays.fill(password, '\0');

        byte[] derived = null;
        try {
            derived = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();

            System.out.println("Caller password cleared: "
                    + zeroed(password));
            System.out.println("KDF still worked after caller clear: "
                    + (derived.length == 32));
        } finally {
            spec.clearPassword();
            if (derived != null) {
                Arrays.fill(derived, (byte) 0);
            }
        }

        boolean passwordAccessRejected = false;
        try {
            spec.getPassword();
        } catch (IllegalStateException expected) {
            passwordAccessRejected = true;
        }
        System.out.println("PBEKeySpec password access rejected: "
                + passwordAccessRejected);
        System.out.println("Derived buffer cleared: "
                + zeroed(derived));

        byte[] originalKeyBytes = new byte[32];
        random.nextBytes(originalKeyBytes);
        SecretKeySpec key = new SecretKeySpec(
                originalKeyBytes, "HmacSHA256"
        );
        Arrays.fill(originalKeyBytes, (byte) 0);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        byte[] tag = mac.doFinal(
                "public demo input".getBytes(StandardCharsets.UTF_8)
        );

        System.out.println("Original key array cleared: "
                + zeroed(originalKeyBytes));
        System.out.println("Key object still usable: "
                + (tag.length == 32));

        Arrays.fill(tag, (byte) 0);
        System.out.println("Tag buffer cleared: " + zeroed(tag));

        try {
            throw new GeneralSecurityException(
                    "provider-specific diagnostic"
            );
        } catch (GeneralSecurityException internal) {
            System.out.println("Public error: "
                    + publicError(internal));
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac SecretMemoryDemo.java
java SecretMemoryDemo
```

**Verified stdout on a Java 17-compatible JDK:**

```text
Caller password cleared: true
KDF still worked after caller clear: true
PBEKeySpec password access rejected: true
Derived buffer cleared: true
Original key array cleared: true
Key object still usable: true
Tag buffer cleared: true
Public error: CRYPTO_OPERATION_FAILED
```

### 10.1. Interpreting Each Output Line Accurately

**“Caller password cleared: true”** states only that the program's `password` array was overwritten with `'\0'`. It does not state the password never existed in another object.

**“KDF still worked after caller clear: true”** shows `PBEKeySpec` retains the needed password data even after the caller wiped its input array. If code wipes only the caller's `char[]` and forgets `spec.clearPassword()`, the copy inside `spec` persists until collected. Some provider steps may also create copies outside `clearPassword()` control.

**“PBEKeySpec password access rejected: true”** verifies the API contract: after `clearPassword()`, calling `getPassword()` throws. This **does not** prove all of RAM was wiped.

**“Derived buffer cleared: true”** confirms the application zeroed the `derived` array in `finally`. Provider internals, key objects, or the JVM may still hold copies. Every buffer has its own lifetime and cleanup.

**“Original key array cleared: true” + “Key object still usable: true”** is the central point: `SecretKeySpec` owns its own key material; wiping the source array does not destroy the key object. Never claim “the key was safely destroyed” solely because the source array was zeroed.

**“Tag buffer cleared: true”** illustrates that output buffers can also be managed. A typical HMAC tag is not as secret as a key, though logging, context, and retention policies still apply. This shows array hygiene, not a mandate that every app zero every public tag.

**“Public error: CRYPTO_OPERATION_FAILED”** illustrates an API returning a **stable error code**. In production, pair this with correlation IDs, permissioned internal telemetry, and threat-model-driven error mapping.

### 10.2. Intentional Limitations of the Demo

- The demo password is written in source as individual characters. **Never** write real secrets into source, config, or version control; this is a public fixture and does not prove safe password input in a real system.
- `PBKDF2WithHmacSHA256` with 100,000 iterations **is solely for demonstrating memory lifecycle**, not a recommended production parameter set for password storage. In production, select password-hashing/KDF schemes and costs per current policy and benchmarks, preferring Argon2id with a trusted library where appropriate.
- `SecretKeySpec` persists until out of scope; the demo has no API to wipe its internal key material. Never infer “source array zeroed means zero secrets in the process.”
- Provider internals, JIT/GC, native heaps, swap, profilers, and dumps **cannot be fully verified** by a unit test alone.
- `Arrays.fill` at the end does not prevent a heap dump captured **earlier** from containing the secret.
- The `publicError` helper does not by itself supply security logging, rate limiting, timing-oracle defenses, access control, or incident response.
- To prove a system **never logs secrets**, test frameworks, filters, tracing, APM, log encoders, and exception handlers end-to-end.

## 11. Designing a Secret Lifecycle in a Java Application

Design the “path of the secret” rather than merely picking one container.

### 11.1. Receiving Secrets

- Fetch secrets over TLS/authenticated channels or authenticated KMS/Vault APIs, never via query strings, URLs, or command lines that can be logged.
- When passwords are user-entered, prefer `char[]` APIs where feasible; for HTTP, control logging, DTOs, and lifetimes.
- When the application generates random keys, use `SecureRandom` and standard key sizes/schemes. Never use `java.util.Random` for keys.
- Never convert secrets to `String`, hex/Base64, or JSON text just to pass between internal layers; if wire formats require text, minimize copies and disable sensitive logging.

### 11.2. Using Secrets

- Distinguish byte-managed keys from **non-exportable key handles** in an HSM/KMS; prefer restricting raw key export whenever your threat model calls for it.
- Grant key access only to components that genuinely need it.
- Avoid holding keys in static fields, generic caches, `toString()`, or serializable DTOs.
- For cryptography, use JCA/JCE providers or vetted libraries; never roll your own AES, HMAC, or padding logic.
- Enforce authorization for key-using actions, not merely “the key is in RAM.”

### 11.3. Ending Operations

- Use `try/finally` to clear caller-owned mutable secret buffers even on exceptions.
- Invoke appropriate cleanup/close/destroy APIs on secret holders and key sessions where implementations support them; verify exact behavior.
- Never retain references longer than needed. Avoid capturing secrets in lambdas, callbacks, async continuations, or uncleared `ThreadLocal`s.
- For borrowed buffers or shared arrays, do not zero data still needed by another caller; define clear ownership upfront.
- Keep lifetimes of decrypted plaintext outputs and records short; plaintext access control and retention matter as much as keys.

### 11.4. Operations

- Lock down heap-dump/crash-dump locations and debugger/profiler privileges.
- Block secret logging/tracing at ingress and response filters.
- Enforce retention on diagnostic artifacts and maintain rotation/revocation/deletion playbooks for leaks.
- Periodically audit APM configs, exception reporting, HTTP logging, access logs, and secret redaction.
- Protect caches, backups, and snapshots that may hold memory artifacts or plaintext.
- Test that unexpected failures—timeouts, retries, OOMs, or provider errors—do not drop secrets into logs or responses.

## 12. Critical Boundary: Keep Secrets In-Process or Never Load Them There?

For high-sensitivity systems, the strongest risk reduction is often **never loading raw long-term keys into the Java heap**.

### 12.1. Software Keys

A Java service loads an AES key from a secret manager, holds it as `byte[]`, and wraps it in `SecretKeySpec` for `Cipher`. This is common, yet the service process holds full key-usage capability and sometimes raw bytes in heap/provider memory. If the process is compromised deeply enough, memory hygiene alone cannot keep the key secret.

### 12.2. Non-Exportable Keys via HSM/KMS

A service can invoke `Encrypt/Decrypt/Sign/Verify` via KMS/HSM or a key-handle provider so long-term private/key bytes are never exported to the Java heap. Benefits:
- Fewer copies of long-term keys in app memory.
- Cleaner authorization by key/purpose and centralized auditing of key usage.
- Centralized rotation, disable/revoke, and access policy enforcement.

**Yet there is no magic:** the service still sees input/output plaintext and can **abuse its KMS call permissions** if compromised. If KMS returns a plaintext data key for local app encryption, **that data key still enters process memory**. Design key usage scopes, IAM, rate limits, encryption contexts, auditing, blast radius, and application hardening.

### 12.3. Avoid Claiming “Secrets Were Never in RAM”

An API may hide a secret from the client layer while TLS libraries, KMS SDKs, or the OS still buffer data. Make only claims backed by your threat model and provider documentation. “Non-exportable” applying to a **specific key object/handle** does not mean every plaintext or derived key in the workflow is non-exportable.

## 13. Comparison Table of Protection Tactics

| Tactic | What Does It Reduce? | What Does It Not Guarantee? |
| --- | --- | --- |
| Using `char[]`/`byte[]` instead of `String` when feasible | Caller can overwrite the buffer it owns | Does not erase prior or external copies |
| `Arrays.fill` in `finally` | Clears that specific array even on throws | Does not clear `SecretKeySpec`, providers, or earlier dumps |
| `PBEKeySpec.clearPassword()` | Clears `PBEKeySpec`'s copy per API | Does not clear prior `String`s or native provider copies |
| Shortening key lifetime/scope | Shrinks window and number of components seeing secrets | Does not stop an attacker with full process privileges |
| Avoiding hex/Base64/`String` key forms | Reduces objects, log exposure, and text copies | Does not eliminate internal JCE secret material |
| HSM/KMS non-exportable keys | Keeps long-term key bytes out of app memory | Does not stop a compromised service from calling sign/decrypt |
| Disabling/redacting request logging | Reduces secrets in logs/traces | Does not control heap dumps or crash artifacts |
| Access controls + encrypting dumps | Limits who can read snapshots | Does not make snapshots safe for public sharing |
| Stable error codes | Reduces secret/diagnostic leaks in public APIs | Does not automatically fix timing oracles or rate-limit gaps |
| Security tests / log scanning | Catches many observable leak paths | Cannot prove absolute absence of copies in RAM |

### 13.1. How Should You Prioritize?

If you have one day to harden a system:
1. Stop logging request headers/bodies containing credentials and stop logging raw keys/plaintext; audit APM/error reporting.
2. Ensure credentials, keys, and decrypted data are scoped tightly; add `finally` blocks to clear mutable buffers.
3. Audit APIs that create copies (`String`, `PBEKeySpec`, `getEncoded()`, streams, serialization).
4. Lock down privileges to trigger/download heap dumps and enforce retention.
5. Separate public errors from internal diagnostics, mitigating oracles on sensitive endpoints.
6. For high-impact long-term keys, evaluate non-exportable KMS/HSM keys and tighten blast radius.

Do not waste time first on reflection hacks to mutate `String` internals, unsupported memory pinning, or “byte scrambling to look unreadable” while still leaking keys in logs and stack traces.

## 14. Practical Scenarios

### Scenario A — Password on a REST API

An endpoint receives a login password. The framework binds the JSON field into a `String`. The developer converts it to `char[]` and zeroes it after verification, yet middleware logs the full request body.

**Conclusion:** clearing the caller's array neither prevents the password from reaching logs nor erases the parser's `String`. Fix ingress/logging first, limit DTO retention, use standard password hashing, apply rate limits, and review framework secret handling.

### Scenario B — Encrypting Documents with AES-GCM

A service fetches a CEK from KMS, constructs a `SecretKeySpec`, zeroes the `byte[]` CEK, and caches the `SecretKeySpec` in a singleton “to avoid calling KMS repeatedly.” Meanwhile, a heap dump gets uploaded to a support ticket.

**Conclusion:** the CEK can still reside in the key object and provider; zeroing the source array is not enough. Revisit key scope/lifetime, dump controls, and KMS/DEK usage; never upload sensitive dumps to untrusted systems.

### Scenario C — Decryption Failure

A server fails AES-GCM decryption and returns `"Tag failed for keyId X with input token Y"` to the client. Debugging gets easier, yet the error leaks metadata or secrets and distinguishes decryption states.

**Conclusion:** public responses must return a generic code; internal telemetry records a correlation ID and safe error category without embedding secrets/tokens. Also check oracle/timing behavior and rate limits.

### Scenario D — Debugging via `toString()`

An `ApiRequest` class generates a `toString()` containing `authorizationHeader`; when an exception occurs, the logger prints the entire request.

**Conclusion:** fix the DTO/`toString()`, serializers, and log filters, and test that secrets never appear; avoid relying solely on late-pipeline regex redaction, which can miss encodings/formats.

### Scenario E — Direct `ByteBuffer.clear()`

A developer calls `directBuffer.clear()` and believes private key data was zeroed. A native diagnostic tool still reads the buffer.

**Conclusion:** `clear()` does not erase contents; it only resets position/limit. Explicitly overwrite sensitive regions via supported APIs while tracking other copies; direct memory is not a vault.

### Scenario F — Password Inside a Stack Trace

`InvalidCredentialsException("password="+p)` is thrown in the auth layer; a global handler calls `exception.printStackTrace()` and returns 500.

**Conclusion:** the secret was baked into the exception message at instantiation. Use safe error codes only, keep secrets out of exception objects, govern logging/causes/responses, and apply uniform auth error handling.

### Scenario G — Private Key Inside an HSM

Java receives a non-exportable `PrivateKey` handle and signs via the provider. The app never sees the raw private key, yet holds permission to submit data for signing.

**Conclusion:** this reduces leakage of private-key material, yet you must still constrain signing permissions, allowed payloads/formats, rate limits, tenants, audits, and abuse detection. Hijacking signing capability is still dangerous even without exporting the key.

## 15. What Can Security and Operational Testing Actually Prove?

### 15.1. Unit Tests

- Supply dummy/fixture secrets, run valid and invalid paths, and assert the secret never appears in exception messages or public responses.
- Use log-capture tests to verify failure paths never log dummy passwords/tokens/keys.
- Verify cleanup in `finally` when APIs throw exceptions.
- Verify `PBEKeySpec.clearPassword()` after derivation and clearing of caller-owned derived buffers.
- Verify DTO `toString()` methods omit sensitive fields.
- Verify Base64/hex serialization helpers only process data permitted for output.

### 15.2. Integration / Security Tests

- Simulate an HTTP pipeline with proxies, access logging, exception handlers, and APM instrumentation; search logs/traces/metrics for dummy markers.
- Trigger controlled cryptographic failures like bad tags and bad credentials; ensure public errors leak no sensitive cause and internal logs contain no secrets.
- Test privileges to create/download heap dumps across operational roles.
- Inspect staging dumps using **non-real dummy markers** if approved; note that a clean snapshot **does not prove** leaks cannot occur at another instant.
- Audit container/runtime settings and core/heap dump upload/retention in CI and production.
- Exercise rotation/revocation if a secret is suspected of entering an unsafe artifact.

### 15.3. What Security QA Cannot Prove Absolutely

A unit test showing `byte[]` is zeroed does not prove:
- Zero key bytes in JIT registers, stacks, or native heap.
- Zero `String` instances created earlier by a framework.
- Zero old snapshots retained in APM or crash dumps.
- Zero secrets already shipped to central log servers.
- Zero copies inside library backing buffers.

Therefore, reports should use accurate phrasing: **“caller-owned buffer cleared,” “public error sanitized,” “no secret found in tested log paths”** rather than “all secrets permanently erased from RAM.”

## 16. Code Review Checklist for a Key or Password

### Input / Representation
- [ ] Secret originates from an authenticated source/channel, never hard-coded in source.
- [ ] Mutable containers matching APIs are used where zeroization is needed; avoid unnecessary `String` creation.
- [ ] Keys are not converted to hex/Base64/debug text unless required by wire format and protected.
- [ ] Input length limits and parsing rules prevent uncontrolled objects/copies.

### Usage / Lifetime
- [ ] Lifetimes of `byte[]`, `char[]`, `SecretKey`, `PBEKeySpec`, `Cipher/Mac`, and provider sessions are documented.
- [ ] Cleanup sits in `finally` or API-appropriate lifecycle hooks, covering exception paths.
- [ ] If `getEncoded()` or copies are created, the caller manages/clears outputs appropriately.
- [ ] Keys are not retained long-term in static fields, caches, or DTOs without justification and policy.
- [ ] IAM/authorization binds key usage under least privilege.
- [ ] For KMS/HSM, it is clear what data still enters the Java heap and which keys are non-exportable.

### Observability / Errors
- [ ] Zero logging of `Authorization`, `Cookie`, passwords, private keys, CEKs/DEKs, or sensitive plaintext.
- [ ] `toString()`, JSON serialization, and exception messages have been audited.
- [ ] Public errors use appropriate codes without echoing secrets or provider diagnostics.
- [ ] Traces/APM/metrics/core dumps/heap dumps do not inadvertently capture secrets.
- [ ] Rate limiting and padding/tag/timing oracle assessments exist for public crypto APIs.

### Operations / Incidents
- [ ] Debugger/profiler/dump access is limited to authorized personnel/tools.
- [ ] Dumps/logs have encryption, access auditing, storage policies, and proper retention/deletion.
- [ ] Rotation/revocation playbooks exist if sensitive artifacts leak.
- [ ] Incident response covers log backups, object stores, tickets, telemetry vendors, developer machines, and support accounts.
- [ ] Testing uses dummy fixtures/canaries, never production secrets.

## 17. Self-Check Questions

**Question 1.** Does setting `secretString = null` guarantee the password was erased from the heap?

**Answer:** No. It only drops the reference; `String` is immutable, GC governs reclamation, and multiple copies may exist.

**Question 2.** If `Arrays.fill(keyBytes, (byte)0)` is called right after creating `SecretKeySpec(keyBytes,"AES")`, is the key inside `SecretKeySpec` guaranteed erased?

**Answer:** No. `SecretKeySpec` keeps its own copy of key material per API contract; the key remains usable. Manage object/provider lifetimes and never claim all copies are gone.

**Question 3.** After calling `spec.clearPassword()` on `PBEKeySpec`, can `spec.getPassword()` still be called?

**Answer:** No per API contract; access is rejected. That does not mean all other password copies elsewhere vanished.

**Question 4.** Why is `ByteBuffer.clear()` not zeroization?

**Answer:** It only resets position and limit without writing zeroes to the data region.

**Question 5.** A heap dump is captured before the app zeroes a `byte[]`; afterward the app zeroes it successfully. Is the dump automatically safe?

**Answer:** No. An earlier snapshot retains data as of capture time. Protect dump artifacts via access controls, encryption, retention, and incident response.

**Question 6.** Should `"AES tag invalid, unwrap RSA successful"` be returned to an unauthenticated caller?

**Answer:** Avoid this; such messages can create an oracle and leak internal processing states. Use threat-model-aligned public errors, safe internal diagnostics, and rate limits.

**Question 7.** Does using an HSM non-exportable private key mean plaintext never touches the Java heap?

**Answer:** No. It restricts exporting that specific private key; plaintext/hashed inputs/outputs and other keys can still appear in process memory depending on design.

**Question 8.** Does one test finding zero dummy keys in a staging dump prove production will never leak secrets?

**Answer:** No. A dump is only one snapshot; GC, timing, and differing data flows can change outcomes. You need threat modeling, multi-layer testing, and sound operations.

**Question 9.** Why should access tokens never be logged even if only internal staff read the logs?

**Answer:** Tokens can be bearer credentials. Logs have multiple replicas, retention windows, readers, and export paths; leaking logs can equal leaking token access.

**Question 10.** What is the primary reason to use `finally` when handling mutable secrets?

**Answer:** To guarantee caller cleanup logic runs even when crypto, parsing, or I/O throws, shrinking how long caller-owned buffers hold secrets.

**Question 11.** Can a secret encrypted in a database appear in plaintext inside a memory dump?

**Answer:** Yes, if the app decrypts it for processing and holds plaintext on the heap or in native buffers. Encryption at rest does not mean encrypted inside active application memory.

**Question 12.** Which statement is more accurate: “erased the entire password from RAM” or “zeroed caller `char[]` and cleared `PBEKeySpec` per API”?

**Answer:** The second is verifiable and accurately scoped; the first overstates what Java managed memory guarantees.

## 18. Summary Diagram

```text
                 SECRET / PASSWORD / KEY
                           |
              +------------+-------------+
              |                          |
          Representations             Infrastructure
          byte[]  char[]              HTTP, logs, APM
          String  objects             heap, crash dumps
          KeySpec provider            debugger, backups
              |                          |
       Limit copies/lifetime         Access control
       Avoid String/logging          Encrypt / retain / audit
       finally + clear own arrays    Secure diagnostic path
              |                          |
              +------------+-------------+
                           |
                  NO ABSOLUTE ZEROIZATION
                  CLAIM FOR ENTIRE JVM
                           |
             Use purpose-bound keys, KMS/HSM
             where appropriate, safe errors,
             least privilege and incident response
```

**Conclusion:** In Java, `byte[]` and `char[]` let you shrink data lifetime **in the exact arrays your application owns**; `String` has no direct content-wiping API; `SecretKeySpec`, `PBEKeySpec`, providers, and frameworks can allocate copies. Heap dumps, profilers, logs, traces, and exceptions can carry secrets outside their intended lifecycle. A secure system never claims “RAM is completely clean,” but designs to **minimize copying, restrict permissions and lifetimes, perform best-effort cleanup, protect diagnostic artifacts, return secret-free errors, and plan key replacement when incidents occur**.

### References

- Java SE 17, `String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, `Arrays.fill`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html
- Java SE 17, `PBEKeySpec` and `clearPassword()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html
- Java SE 17, `SecretKeySpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html
- Java SE 17, `SecretKeyFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html
- Java SE 17, `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17, `Console.readPassword()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html
- Java SE 17, `Destroyable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Destroyable.html
- OWASP, *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP, *Secrets Management Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP, *Error Handling Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html
