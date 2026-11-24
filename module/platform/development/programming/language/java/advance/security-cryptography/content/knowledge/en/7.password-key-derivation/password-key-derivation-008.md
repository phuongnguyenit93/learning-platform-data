# 7.8. Handling `char[]`, `clearPassword`, and the Limits of Sensitive Data Erasure on the JVM

## 1. The problem to solve: password lifetime in memory

A password, passphrase, PIN, or key-derivation input normally only needs to live in memory briefly: received from the user, used to verify or derive a key, and then no longer needed in plaintext. On Java/JVM, the issue is not merely **avoiding logging passwords**, but also how the data is represented and **who owns each copy**.

Three practical goals:

1. **Minimize plaintext password retention:** release/overwrite controllable buffers immediately once work finishes.
2. **Avoid unintended copies:** especially `String`, string concatenation, encoder buffers, forms, library objects, and copies returned by APIs.
3. **Understand the limits:** clearing a `char[]` or calling `PBEKeySpec.clearPassword()` **does not prove** that every trace of the password in the JVM process, physical memory, heap dumps, swap, snapshots, or native libraries has vanished.

In JCA/JCE, `char[]` and `javax.crypto.spec.PBEKeySpec` are tools for *partially* controlling password lifetime. This is a risk-mitigation measure, **not an absolute guarantee of secret erasure**.

## 2. Why prefer `char[]` over `String` for plaintext passwords?

### 2.1. `String` has no API to erase individual characters

`String` is immutable. Once `String password` is created, the application has no public API to reliably overwrite the bytes/characters stored by that `String`. Assigning `password = null` only drops one reference; garbage collection timing is nondeterministic, and old memory may retain traces until reused or overwritten. A `String` can also linger longer than expected via logs, exceptions, caches, stack traces, request objects, serializers, or concatenation.

`char[]` is mutable: the application can call:

```java
Arrays.fill(password, '\0');
```

This **writes NUL into the elements of the `password` array itself** when executed. It helps limit copies on the heap owned by the application.

| Criterion | `String` | `char[]` |
| --- | --- | --- |
| Can contents be modified directly via public API? | No | Yes, using `Arrays.fill` or setting elements individually |
| Can you actively erase an owned buffer? | No guarantee via standard API | Can request overwriting that specific buffer, within JVM limits |
| Can it be copied in multiple places? | Yes | Yes |
| Guaranteed erasure of all traces in RAM/heap? | No | **No** |
| Used directly with `PBEKeySpec`? | No; must create a `char[]` | Yes |

**Important note:** `char[]` is not “completely safe” or “secretly shielded by the JVM.” It only lets you request modifying the contents of one specific array. Other copies are not cleared merely because you overwrote the original array.

### 2.2. Operations to avoid

```java
// Bad example when handling real passwords:
String immutable = new String(passwordChars);  // Creates a String copy hard to erase actively.
String text = String.valueOf(passwordChars);    // Also creates a String.
String logLine = "password=" + new String(passwordChars);
System.out.println(passwordChars);             // Never use to display secrets.
```

This snippet **illustrates anti-patterns**, not a complete program. `String.valueOf(char[])` creates a new `String` holding the characters; `System.out.println(char[])` can also print the contents via its `char[]` overload, so **never log any password char array**. Be cautious with `Arrays.toString(passwordChars)`, debugger/watch expressions, metric labels, structured log fields, and exception messages.

Also avoid moving passwords into `StringBuilder`/`StringBuffer` just to continue processing: they maintain their own internal buffers and are not reliable zeroization mechanisms. Conversely, if the input framework **already** created a `String`, calling `string.toCharArray()` only creates yet another array; **it does not erase the source `String`**.

## 3. Data ownership: one password can have many copies

Consider a simple flow:

```text
Input source (terminal / UI / HTTP framework)
   |
   v
char[] callerPassword  -----------------------------+
   |                                                |
   | new PBEKeySpec(callerPassword, ...)            | Arrays.fill(callerPassword, '\0')
   v                                                | clears only the caller's array
PBEKeySpec: internal copy                          <----+
   |
   | getPassword()
   v
Returned char[]: yet another new copy
   |
   +-- SecretKeyFactory / provider creates intermediate KDF data
   +-- SecretKey and potentially byte[] from getEncoded()
   +-- heap, native provider, stack, logs, snapshots (system-dependent)
```

**Every copy arrow represents a separate region to evaluate.** Clearing `callerPassword` does not automatically clear memory inside `PBEKeySpec`. Clearing `PBEKeySpec` does not automatically clear `char[]` instances returned by `getPassword()` or derived-key byte arrays. Clearing output `byte[]` arrays does not mean the `SecretKey` object or provider wiped its own copies.

This is why methods taking a password must never silently retain the caller-owned array or cache it. Define clearly: whether the caller or callee is responsible for clearing, whether copies are made, when buffers may be cleared, and which components lie outside your control.

## 4. `PBEKeySpec`: password copy and `clearPassword()`

`javax.crypto.spec.PBEKeySpec` supplies the password and optional salt, iteration count, and key length to *Password-Based Encryption/Key Derivation* (PBE/KDF) algorithms via `SecretKeyFactory`.

Example spec creation:

```java
PBEKeySpec spec = new PBEKeySpec(passwordChars, salt, iterations, 256);
```

The matching signature is `PBEKeySpec(char[] password, byte[] salt, int iterationCount, int keyLength)`; `keyLength` is in **bits**, not bytes.

### 4.1. The constructor copies data

`PBEKeySpec` creates **its own copy of the password** passed in by the application. Consequently:

- Mutating or calling `Arrays.fill(passwordChars, '\0')` after creating the spec **does not clear** the password inside the spec.
- This prevents unintended mutations while the KDF runs, yet creates an extra plaintext password region in memory.
- The spec provides an API to clear **its own copy**, without authority to automatically clear external arrays.

The salt is also copied when stored in the spec; `getSalt()` returns a copy. Salts are typically **non-secret** and must be stored alongside derivation metadata when re-verification is needed, though uniqueness and randomness matter. Salts do not need to be treated like passwords.

### 4.2. `getPassword()` returns a copy, not internal ownership

`spec.getPassword()` returns a **new** `char[]` containing the password currently held by the spec. Calling it repeatedly can unknowingly create multiple sensitive copies.

```java
char[] returnedCopy = spec.getPassword();
try {
    // If contents are truly needed, keep usage as brief as possible.
} finally {
    Arrays.fill(returnedCopy, '\0');
}
```

This snippet is illustrative; `spec` was constructed earlier. Wiping `returnedCopy` **does not** wipe the spec's internal copy and does not wipe the original array. Avoid calling `getPassword()` just for logging, debugging, unnecessary comparisons, or length checks.

### 4.3. What does `clearPassword()` affect?

`spec.clearPassword()` requests erasure of the password copy **stored inside `PBEKeySpec`**. Per the Java API contract, once cleared, `getPassword()` throws `IllegalStateException`.

What `clearPassword()` **does not do**:

- Does not modify the `passwordChars` array passed by the caller.
- Does not find or modify `char[]` copies previously returned by `getPassword()`.
- Does not erase any `String` if a framework created one earlier.
- Does not guarantee wiping temporary password bytes allocated by `SecretKeyFactory`/providers/native code.
- Does not erase key material inside the `SecretKey` returned by the KDF, and does not destroy `byte[]` returned by `getEncoded()`.
- Does not promise clean heap dumps, CPU registers, swap, OS page caches, core dumps, or backups/snapshots.

**Order of use:** create `PBEKeySpec` → use it to generate key/derived bytes → call `clearPassword()` in `finally`. **Never clear the spec before `SecretKeyFactory.generateSecret(spec)` if the password is still needed for derivation.**

If reusing the same spec across multiple calls, bound its lifetime; preferably construct it only when needed and close the “exposure window” right after the work finishes. After `clearPassword()`, you must create a new spec with a valid password to run another derivation—never expect the spec to reuse cleared content.

### 4.4. Comparing commonly confused APIs

| API / Operation | Target affected | What must **not** be inferred |
| --- | --- | --- |
| `Arrays.fill(charArray, '\0')` | Elements of that exact `charArray` | Does not erase other copies; does not guarantee hardware/RAM is scrubbed |
| `PBEKeySpec.clearPassword()` | Internal password copy inside the spec | Does not erase caller `char[]`, arrays from `getPassword()`, or derived keys |
| `PBEKeySpec.getPassword()` | Creates and returns a new **copy** | Not a direct reference for clearing the spec internally |
| `Arrays.fill(keyBytes, (byte) 0)` | That specific byte array | Does not erase key material inside other objects/providers |
| `password = null` | Local reference | No contract to erase heap contents immediately |
| `System.gc()` | Only a hint/request to the GC | Not a zeroization API; no guarantee of timely execution or erasure |

## 5. Standalone Java 17+ demo and verified stdout

This demo verifies three exact behaviors: a caller-owned array, a password copy from `PBEKeySpec.getPassword()`, and the internal password becoming unavailable after `clearPassword()`. It also derives a key using `PBKDF2WithHmacSHA256` to show the spec still works even after the caller zeroes its original array.

**Note:** the fixed characters in code are solely for a deterministic example, **not a real password**. `10_000` iterations illustrates syntax and fast execution, **not** a secure production setting. Production systems must choose derivation algorithms and costs per current guidance, benchmarks, and threat model.

Create `PasswordMemoryDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordMemoryDemo {
    private static boolean allZero(char[] data) {
        for (char c : data) {
            if (c != '\0') return false;
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        // Fixed characters for a repeatable DEMO; never hardcode real passwords.
        char[] entered = {'d', 'e', 'm', 'o', '-', 'o', 'n', 'l', 'y'};
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);

        PBEKeySpec spec = null;
        char[] fromSpec = null;
        byte[] keyBytes = null;
        try {
            spec = new PBEKeySpec(entered, salt, 10_000, 256);
            fromSpec = spec.getPassword(); // A separate copy; wipe it too.
            System.out.println("Separate returned copy: " + (fromSpec != entered));

            Arrays.fill(entered, '\0'); // Clear caller-owned array.
            System.out.println("Caller cleared: " + allZero(entered));
            System.out.println("Spec copy still held password: " +
                    !allZero(fromSpec));

            Arrays.fill(fromSpec, '\0');
            fromSpec = null;

            SecretKey derived = SecretKeyFactory
                    .getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec);
            keyBytes = derived.getEncoded(); // Another sensitive buffer.
            System.out.println("Derived key size: " + keyBytes.length + " bytes");

            spec.clearPassword(); // Wipes internal password copy.
            boolean unavailable = false;
            try {
                spec.getPassword();
            } catch (IllegalStateException expected) {
                unavailable = true;
            }
            System.out.println("Spec inaccessible after clear: " + unavailable);
        } finally {
            if (fromSpec != null) Arrays.fill(fromSpec, '\0');
            if (keyBytes != null) Arrays.fill(keyBytes, (byte) 0);
            Arrays.fill(entered, '\0');
            if (spec != null) spec.clearPassword();
        }
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac PasswordMemoryDemo.java
java PasswordMemoryDemo
```

Exact stdout:

```text
Separate returned copy: true
Caller cleared: true
Spec copy still held password: true
Derived key size: 32 bytes
Spec inaccessible after clear: true
```

**Line-by-line explanation:**

1. `spec = new PBEKeySpec(entered, salt, ...)` makes an internal copy; `fromSpec = spec.getPassword()` creates **another copy**, with a different reference from `entered`.
2. `Arrays.fill(entered, '\0')` sets every element of the caller's array to NUL. This **does not** alter `fromSpec` copied earlier; that is why `Spec copy still held password: true` prints.
3. We explicitly wipe `fromSpec` right after use. The spec still retains its internal copy so `SecretKeyFactory.generateSecret(spec)` can finish derivation.
4. A 256-**bit** key length corresponds to `32 bytes` from `derived.getEncoded()` in this demo. The `keyBytes` array is also sensitive, so it is wiped with `Arrays.fill` in `finally`.
5. `spec.clearPassword()` clears the internal password, and subsequent `getPassword()` calls are rejected with `IllegalStateException` per API contract.
6. `finally` ensures cleanup runs on owned arrays and the spec even if the KDF or another step throws an exception. It **does not** promise to erase `SecretKey derived` or internal provider/JVM copies.

**Do not misread the demo:** `Caller cleared: true` only checks **the elements of one specific array in the current execution context**. It is not a measurement proving the heap, native memory, or OS retains no password. Omitting printing the password or key is also intentional.

## 6. Building cleaner password input and handling flows

### 6.1. `Console.readPassword()` returns `char[]` (unlike `readLine()`)

`java.io.Console.readPassword(...)` reads password characters (typically without echoing to screen) and returns `char[]`. It is a good choice for CLI applications when an interactive console is available.

Illustrative **code snippet**, not a standalone Java program:

```java
Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Interactive console unavailable");
}
char[] password = console.readPassword("Password: ");
if (password == null) {
    throw new IllegalStateException("End of input");
}
try {
    // Use password briefly with PBEKeySpec/SecretKeyFactory.
} finally {
    Arrays.fill(password, '\0');
}
```

Requires importing `java.io.Console` and `java.util.Arrays`. `System.console()` may return `null` inside IDEs, some CI environments, or when stdin/stdout are redirected; **never** automatically fall back to `Scanner.nextLine()` without recognizing it creates `String` objects and handles echoing/input differently.

Never write `new String(console.readPassword())`: that creates a plaintext `String` and drops the reference to the `char[]` just read, preventing active erasure of the original array.

### 6.2. `JPasswordField` and UI

In Swing, `JPasswordField.getPassword()` returns `char[]` to avoid requiring a public `String`. After use, call `Arrays.fill(password, '\0')` on the received array and clear the UI field per policy (e.g., when closing the form). Do not infer those steps erased every copy in UI documents, clipboards, accessibility tooling, event queues, or desktop/swap memory. Never copy passwords into the clipboard or place them in tooltips/exceptions.

### 6.3. Data arriving through HTTP/JSON frameworks

Most APIs receiving JSON/web forms pass through decoders, request parsers, and libraries that may allocate `String` objects or byte buffers. Once application code receives `String password`, calling `password.toCharArray()` only lets you **manage the new array**; it does not control memory holding the original `String` or framework buffers.

Audit the data path **starting from request ingestion**, disable logs/traces containing secrets, configure observability masking, bound request-object lifetimes, and keep passwords out of sessions/caches/message queues unnecessarily. Never claim that merely changing a DTO field from `String` to `char[]` solves zeroization.

## 7. Sensitive copies that often go unseen

| Copy source | Why might the password remain? | What the application can do |
| --- | --- | --- |
| `PBEKeySpec` constructor | Actively copies the password to hold for KDF use | `clearPassword()` in `finally` |
| `PBEKeySpec.getPassword()` | Returns a fresh array | Avoid calling unless needed; wipe received array |
| `String`, concatenation, formatters, logging | Immutable/copied, no wipe contract | Avoid creating and never log in plaintext |
| Charset/encoders and intermediate `byte[]` | Converts UTF-16 chars to bytes for encryption/KDF | Manage created `byte[]`, `Arrays.fill(..., (byte) 0)` |
| `SecretKeyFactory` and JCE provider | KDF may allocate copies/working buffers/private state | Minimize object lifetime; inspect API/provider, do not promise full erasure |
| `SecretKey.getEncoded()` | Usually returns a new byte array of key material; may be `null` for non-exportable keys | Wipe caller-owned `byte[]`, avoid exporting key bytes unnecessarily |
| Heap dumps, core dumps, crash reports | Snapshots may capture uncleaned objects/buffers | Restrict dump permissions, secure dump files, avoid production dumps needlessly |
| Swap, hibernation, VM/container snapshots | OS/infra may page memory out to storage | Host, swap/dump, and disk-encryption policies aligned with threat model |
| Native code/HSM/KMS/client libraries | Data may live off-heap outside Java `Arrays.fill` reach | Choose providers/APIs with clear key-protection contracts; never assume every key is wiped |

Some key objects implement `Destroyable.destroy()` or provider-specific cleanup. Still, **never assume** every `SecretKey` provides reliable material erasure, succeeds on destroy, or cleans up previously created copies. Read provider documentation, test behavior, and design to minimize secret export.

## 8. Fundamental limits of “memory erasure” on the JVM

### 8.1. GC is not a zeroization tool

**Garbage Collection (GC)** reclaims unreferenced objects; it makes no contract to scrub memory regions immediately when `password = null` or `System.gc()` runs. `System.gc()` is merely a hint; the application cannot force the JVM to walk all RAM and scrub secret traces.

The JVM may move/copy objects during GC, leaving previous memory regions intact until overwritten; on many systems, dumps/snapshots also exist outside heap control of Java code. This makes “I filled the array” very different from “no copy exists anywhere.”

### 8.2. Compilers and optimizations

The JIT/compiler may apply optimizations such as dead-store elimination for writes it deems have no observable effect on program semantics. Never treat an `Arrays.fill` in source code as a **cryptographic guarantee** that bytes at every memory tier were definitely scrubbed.

That does **not** make `Arrays.fill` useless: it is a sensible **best-effort** step to shorten how long values linger in application-owned arrays. The accurate claim is “the application requested zeroing that specific array,” not “the JVM/OS proved the entire secret was destroyed.”

### 8.3. Data representation and encoding

A Java `char` is a **UTF-16 code unit**, not a UTF-8 byte. When a KDF or protocol needs password bytes, transcoding, `byte[]` copies, Unicode normalization, and provider buffers may be created. Never treat `password.length` as the byte length of the password.

For two systems to derive the same key from the same password, align **KDF algorithm, salt, iterations/work factor, output length, encoding, and normalization**; avoid converting `char[]` to `String` merely to “normalize” without managing the consequences. Historical PBE algorithms handle characters differently; never assume every provider maps `char` to bytes identically.

### 8.4. Threat model determines what is necessary

For a typical backend application, keeping passwords out of logs, applying a proper KDF, restricting heap-dump access, and shortening buffer lifetimes may be practical controls. However, if an adversary **already executes code in the same process or has full RAM read access**, zeroing a few Java arrays provides no absolute isolation.

In high-assurance environments, consider non-exportable HSM/KMS APIs/providers, process isolation, disabling dumps, encrypted storage, OS hardening, and architectures that minimize where plaintext passwords appear. Standard Java/JVM has no general contract to “pin memory pages and guarantee erasing every copy” via `char[]` alone.

## 9. Practical implementation rules: controlled secret retention reduction

### 9.1. Ownership principles

- **The caller owns** the array it receives from UI/console/request: the caller is responsible for wiping it when done, usually in `finally`.
- **The callee holds** the password only transiently during processing and never stores the object/reference in caches, long-lived fields, thread locals, queues, or unnecessary callbacks.
- When a library creates a copy like `PBEKeySpec`, **close its lifecycle via the library's official API** (here `clearPassword`) rather than reflecting into private fields.
- `byte[]` arrays from encoding or `getEncoded()` belong to the caller once returned: wipe when no longer needed, understanding this **does not** touch material inside other objects.
- Never wipe a buffer **before** the crypto API needs to read it. Wrong ordering can derive the wrong key or break security logic. Clear buffers as soon as derivation/creation completes.

### 9.2. Recommended lifecycle

```text
RECEIVE password into char[] when input API supports it
    |
    v
VALIDATE minimal input rules (do not log password)
    |
    v
Create PBEKeySpec (creates internal copy)
    |
    v
SecretKeyFactory / password verification / key derivation
    |
    +-- Wipe temporary byte[]/char[] created and owned
    +-- Clean up key material if API/provider has an appropriate contract
    |
    v
PBEKeySpec.clearPassword() in finally
    |
    v
Arrays.fill(callerPassword, '\0') in finally
    |
    v
Continue with verified result / protected key,
keeping plaintext password no longer than necessary.
```

Not every system has full control to enforce every step; document the limits of your framework and libraries clearly.

### 9.3. Password hashing differs from RAM password management

Choosing `char[]` and wiping buffers **does not replace** offline-resistant password hashing. When storing user authentication credentials, use a dedicated password-hashing scheme with a per-account/per-record salt and sufficiently high cost—such as Argon2id or another choice aligned with policy, libraries, and system requirements. PBKDF2-HMAC-SHA256 may be needed in Java/JCA or compliance contexts, but its cost factor must be engineered/tuned—never take `10_000` from the demo as a production recommendation.

When using a password to **encrypt data**, use an appropriate KDF for key derivation and an authenticated encryption mode like AES-GCM with proper nonces; never fast-hash a password with SHA-256 and use it directly as an AES key without proper design and threat modeling. Salt, KDF parameters, and IV are usually **non-secret**, yet must be stored intact to reopen data; **derived keys** and plaintext passwords must be protected.

### 9.4. Logging, telemetry, and testing

- Never log passwords, salt+password, derived key bytes, or `char[]` via `toString()`/`Arrays.toString()`.
- Keep secrets out of URL query strings, error responses, exception text, event buses, and environment variables where safer alternatives exist; environments and frameworks may keep `String` copies.
- In tests, use **dummy values**, never real accounts or production tokens. Verify arrays are zeroed via logic tests, but **never** write tests claiming native memory or heap dumps are completely clean.
- Test `finally` on both success and failure paths: invalid input, KDF exceptions, timeouts, cancellations, and shutdown. Never let one exception skip cleanup of another buffer.
- In asynchronous processing, avoid capturing passwords in lambdas/callbacks/`CompletableFuture`/queues longer than intended; re-evaluate ownership and safe-to-clear timing.

## 10. Common misconceptions and bugs

| Misconception or bug | Why it is wrong | Remediation |
| --- | --- | --- |
| “We switched `String` to `char[]`, so passwords cannot leak” | `char[]` still lives on the heap and can be copied, dumped, logged, or read in-process | Manage lifetime, access controls, and threat model |
| “`clearPassword()` wipes the array passed to the constructor” | `PBEKeySpec` stores its own internal copy | Call `clearPassword()` on the spec **and** `Arrays.fill` on the caller array |
| “Calling `getPassword()` repeatedly creates no extra secret memory” | Each call allocates a new `char[]` copy | Avoid unnecessary calls; wipe every returned copy |
| “`Arrays.fill` erases a `String` created earlier” | `String` is immutable and lives in separate memory | Avoid creating password `String` objects from the start where possible |
| “Setting the reference to `null` erases the password right away” | GC has no contract for immediate wiping | Wipe mutable buffers, shorten lifetimes, and restrict dumps |
| “`System.gc()` is a secret-erasure API” | No guarantee on timing or overwriting | Never use GC as zeroization |
| “Wiping `keyBytes` guarantees the `SecretKey` is erased” | Objects/providers may hold separate key material | Minimize key export and check provider-specific cleanup |
| “Clearing the password before `generateSecret` is safer” | The KDF needs valid input data to run | Clean up **after** use, inside `finally` |
| “Password is a `char[]` so it can never appear in logs” | Logging, formatting, or debugging can stringify or print `char[]` directly | Enforce redaction and debugging policies |
| “Memory wiping replaces password hashing” | Breached DB credentials still face offline cracking | Use salted, properly costed KDF/password hashing |
| “One `Arrays.fill` proves no password remains in RAM” | Copies, providers, JIT/GC, native memory, swap, snapshots | Describe as **best-effort mitigation**, never an absolute guarantee |

## 11. Exercises and self-check questions

1. `PBEKeySpec` is constructed from `char[] original`. If you call `Arrays.fill(original, '\0')`, why can `SecretKeyFactory.generateSecret(spec)` still derive the key?
2. `spec.getPassword()` is called twice. How many copies must be tracked for ownership? Does `spec.clearPassword()` automatically wipe both returned arrays?
3. Why is `new String(passwordChars)` something to avoid in password-handling flows even if you call `Arrays.fill(passwordChars, '\0')` afterward?
4. State the differences among wiping the caller's array, clearing the spec's internal copy, wiping the `getEncoded()` result, and destroying `SecretKey`/provider state.
5. Why is `finally` critical when `SecretKeyFactory.generateSecret` can throw an exception?
6. If a framework passes the password to a controller as a `String`, what benefit does `toCharArray()` provide, and what **cannot** it solve?
7. Why do “zeroing `char[]`” and “using Argon2id/PBKDF2 properly” address two different categories of risk?
8. What information could still persist in a heap dump or snapshot even after every visible Java array has been filled with NUL?

**Practice:** modify the demo to call `spec.getPassword()` a second time and verify the two copies have distinct references and must be wiped independently. Add a branch simulating an exception inside `try`, ensuring `finally` runs without printing the password. Write a test verifying `spec.getPassword()` throws `IllegalStateException` after `clearPassword()`. Never run experiments with real passwords or capture heap dumps containing production secrets.

## 12. Official API references

- [PBEKeySpec — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): constructors, `getPassword`, `clearPassword`, password/salt copying, and post-clear exceptions.
- [SecretKeyFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): generating secret keys from `KeySpec` via providers.
- [Arrays — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `Arrays.fill(char[], char)` and `Arrays.fill(byte[], byte)`.
- [Console — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html): `readPassword` and behavior without an interactive console.
- [JPasswordField — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/JPasswordField.html): `getPassword()` instead of unnecessary `String` handling.
- [Java Cryptography Architecture (JCA) Reference Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): key concepts, providers, `SecretKeyFactory`, and password-based derivation.