# Looking Up Javadoc, Serialization Specification, and Provider Capabilities in Java I/O

## 1. Purpose and How to Choose Documentation Sources

When using Java I/O, the key question is not just "Which method should I call?" but also "Which behaviors does Java guarantee, which depend on the operating system or provider, and where can errors occur?". Three documentation sources answer three different classes of questions:

| Source | What does it answer? | Example questions |
| --- | --- | --- |
| **Java SE Javadoc** | API signatures, semantics, parameters, return values, exceptions, guarantees, and limits of each class/method. | Does `Files.move` guarantee atomicity? What does `InputStream.read` return at end of data? |
| **Java Object Serialization Specification** | Standard rules of the object serialization mechanism: object graphs, saved state, stream format, restoration, version compatibility, hooks, and security. | How is `transient` handled? When fields or `serialVersionUID` change, how does reading old data behave? |
| **Documentation and capabilities of the running provider** | What an actual implementation supports, such as file attribute views, symbolic links, atomic move, ZIP filesystem, or file open options. | Does the provider of this `Path` support POSIX permissions? |

**Principle:** Javadoc and the specification are the contract for reasoning; runtime capability detection helps select the right code branch. An "optional" feature in Javadoc does not become an always-available feature just because it works on a development machine.

Lock in the **target JDK version** (e.g., Java 17 or 21) before looking things up. Pick the Java SE documentation matching that version; newer APIs may not exist on the running JDK. This guide illustrates with Java 17+ and links to Java SE 21 documentation for lookup.

## 2. Reading Javadoc Effectively

### 2.1. Identify the Exact Class, Package, Module, and Overload

Start from the class that owns the operation:

- Byte streams: `java.io.InputStream`, `OutputStream`, `BufferedInputStream`, `DataInputStream`.
- Character streams and charsets: `Reader`, `Writer`, `InputStreamReader`, `OutputStreamWriter`, `java.nio.charset.Charset`.
- Filesystem/NIO.2: `java.nio.file.Path`, `Paths`, `Files`, `FileSystem`, `FileStore`, `FileSystems`.
- Object serialization: `Serializable`, `Externalizable`, `ObjectOutputStream`, `ObjectInputStream`, `ObjectStreamClass`.

Each Javadoc page specifies the **module**, **package**, `Since`, inheritance information, and overloads. `Files.copy(Path, Path, CopyOption...)` has a different contract from `Files.copy(InputStream, Path, CopyOption...)`; never draw conclusions from method names alone.

### 2.2. Read the Description in Order

1. Read the class-level description first: resources, thread-safety, characteristics, or implementor requirements.
2. Select the exact signature/overload: parameter types, varargs, generics, return type, and `throws`.
3. Read the entire detailed description: defaults when no options are passed, symbolic link handling policy, and state when an operation fails.
4. Read `Parameters`, `Returns`, `Throws`, `Implementation Requirements/Notes`, `API Note`, and `See Also` if present.
5. Note down: **what is guaranteed**, **what is implementation-dependent**, **optional operations**, **exceptions to handle**, and **how to close resources**.

For example, in `InputStream.read()`: the result is an `int` representing a valid byte from 0 to 255, or `-1` at end of stream; do not cast immediately to `byte` before checking `-1`. Likewise, a `read(byte[])` call does not mean the entire array is always filled; you must check the actual number of bytes read.

For example, in `Files.newOutputStream(path)`: if no options are specified, the default is equivalent to `CREATE`, `TRUNCATE_EXISTING`, and `WRITE`. Thus "opening for writing" can erase old content. If overwriting must be prevented, look up `CREATE_NEW` and handle `FileAlreadyExistsException`; do not pick options by guessing.

### 2.3. "Having an API" Differs from "Every Implementation Supports It"

In Javadoc, phrases like "optional operation", "implementation specific", "if supported", and "not specified" are a crucial part of the contract.

- `Files.move(source, target, ATOMIC_MOVE)`: requests an atomic move. If it cannot be satisfied, `AtomicMoveNotSupportedException` may be thrown; do not silently treat an ordinary move as atomic. When `ATOMIC_MOVE` is present, how an existing target is handled is implementation-specific and other options are ignored.
- `Files.copy(..., COPY_ATTRIBUTES)`: which attributes are copied depends on the filesystem/provider; last-modified time is the minimum attribute attempted when both sides support it, and precision may be lost.
- `Files.createSymbolicLink` and `FileSystem.newWatchService` are features that may be unsupported.
- `Files.getFileAttributeView(path, SomeView.class)` may return `null` when the view is unavailable; corresponding attribute-reading operations may also throw `UnsupportedOperationException`.

Also distinguish check results: `Files.exists(path) == false` **does not assert** that the file definitely does not exist; the API may be unable to determine status due to access errors or I/O. Similarly, `Files.notExists(path) == false` does not by itself prove the file exists.

## 3. Looking Up the Java Object Serialization Specification Properly

Object serialization in Java is the mechanism for turning an **object graph** into a stream for storage/exchange and restoring it under dedicated rules. It is not synonymous with ordinary byte I/O via `Files` or with JSON. Rules that cannot be fully inferred from a single `ObjectOutputStream.writeObject` method are specified in the **Java Object Serialization Specification**.

### 3.1. Map of Sections Frequently Needed

| Question | Section to open in the Serialization Specification |
| --- | --- |
| Which fields are saved, object graph, shared references, and cycles? | Chapter 1 — System Architecture, especially 1.2–1.7 and 1.14 |
| How does `Serializable` differ from `Externalizable`? | Sections 1.10–1.11, 2.4, and 3.6 |
| Customizing object writing/reading with `writeObject`/`readObject`? | Chapters 2–3, especially 2.3 and 3.4 |
| `serialVersionUID`, class descriptor, serial form? | Chapter 4, especially 4.3 and 4.6 |
| Renaming/removing/adding fields, changing types, compatibility with stored data? | Chapter 5 — Versioning of Serializable Objects |
| Binary stream layout and protocol versions? | Chapter 6 — Object Serialization Stream Protocol |
| Attack surface and deserialization errors? | Appendices A/B and `ObjectInputFilter` Javadoc |

Read the Javadoc of `Serializable`, `ObjectInputStream`, and `ObjectOutputStream` alongside the relevant specification sections. The specification defines the mechanism; Javadoc provides how to call the APIs along with specific exceptions.

### 3.2. Core Rules to Know

- A class declares `implements Serializable` to participate in the default serialization mechanism. This marker interface has **no methods** to implement.
- By default, eligible instance fields are included in the serial form; `static` fields do not represent per-instance state and `transient` fields are not saved by the default mechanism. The value of a `transient` field after restoration is its type's default value, unless custom restoration logic sets it.
- A field referencing a non-serializable object may cause writing to throw `NotSerializableException` if that object is actually traversed in the serialization graph.
- `ObjectOutputStream` writes class descriptors and object data; `ObjectInputStream` reads according to the protocol and reconstructs shared references/cycles. Do not assume the `Serializable` class's constructor is invoked like creating a new object; the accessible no-arg constructor of the first **non-Serializable** superclass is invoked during restoration.
- Declaring `private static final long serialVersionUID = ...L;` on ordinary serializable classes helps control the version identifier. Mismatched UIDs can cause `InvalidClassException`; **matching UIDs do not prove every change in the class is compatible**. You must check the class evolution rules in Chapter 5.
- `private writeObject(ObjectOutputStream)`/`private readObject(ObjectInputStream)`, `writeReplace`/`readResolve`, `serialPersistentFields`, and `Externalizable` alter the protocol/serial form; read the exact declaration requirements and execution order in the specification. `Externalizable` is responsible for writing/reading its own data and requires a `public` no-arg constructor for restoration.
- Enums have dedicated serialization rules; serializable records also have dedicated rules. Do not extrapolate every hook of ordinary classes to enums/records.
- Java serialization is not an ideal general-purpose exchange format for long-lived APIs. If you need a cross-language contract or independently evolving schema, consider a format designed for that purpose.

### 3.3. Compilable Java 17+ Example: `transient` and Serial Form

Save the following code to `SerializationProbe.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class SerializationProbe {
    private static final class Profile implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String name;
        private transient String sessionToken;

        private Profile(String name, String sessionToken) {
            this.name = name;
            this.sessionToken = sessionToken;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] saved;

        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Profile("Lan", "temporary-token"));
            out.flush();
            saved = bytes.toByteArray();
        }

        try (ObjectInputStream in =
                     new ObjectInputStream(new ByteArrayInputStream(saved))) {
            Profile restored = (Profile) in.readObject();
            System.out.println(restored.name);
            System.out.println(restored.sessionToken == null);
        }
    }
}
```

Compile and run:

```bash
javac SerializationProbe.java
java SerializationProbe
```

Output:

```text
Lan
true
```

`name` is saved; `sessionToken` is marked `transient` so its restored value is `null`. The example uses a byte array produced by the program itself, **not reading an untrusted stream**. `@Serial` lets the compiler check certain serialization-related declarations, but it does not change security requirements or automatically make data compatible.

### 3.4. Security During Deserialization

Do not use `ObjectInputStream.readObject()` on data controlled by untrusted parties merely because you have `serialVersionUID`, `transient`, or a type cast after reading. Object graph construction happens before casting and can trigger logic in classes on the classpath.

If Java native serialization must be used for a controlled data source, enforce an explicit type allowlist and limit size/depth/complexity with `ObjectInputFilter` (including per-stream filters), while authenticating the source and managing versions. Javadoc warns that deserializing untrusted data is dangerous even with filtering; prefer avoiding this mechanism at untrusted boundaries.

## 4. Providers in Java NIO.2: Who Executes Operations on `Path`?

A `Path` belongs to **a specific `FileSystem`**; that `FileSystem` is supplied by a `FileSystemProvider`. The `Files` utility class generally delegates operations to the corresponding provider of the `Path`. Consequently, the exact same `Files` call may have different constraints on the default filesystem, a ZIP filesystem, or a third-party implementation.

Lookup relationship:

```text
Path ──getFileSystem()──> FileSystem ──provider()──> FileSystemProvider
  │                         │                              │
  └── Files.* operations ────┴── implements operations <────┘
```

The default provider typically has the `file` scheme. Other providers have their own schemes (such as `jar` for the ZIP/JAR filesystem when the corresponding module/provider is available). The presence of a provider must be verified on the running JVM; it cannot be inferred solely from a `.zip` extension or from an API class being present.

### 4.1. APIs to Inspect Capabilities at Each Level

- `FileSystemProvider.installedProviders()`: lists installed providers discovered by the API; `provider.getScheme()` identifies the URI scheme.
- `path.getFileSystem().provider()`: identifies the provider that actually owns `Path`; `FileSystems.getDefault()` only represents the default filesystem.
- `fileSystem.supportedFileAttributeViews()`: set of view names supported by the **filesystem**, e.g. `basic`, `posix`, `dos`, `acl`, `user` (the actual set depends on the provider).
- `Files.getFileStore(path).supportsFileAttributeView(...)`: checks view support at the **file store** containing the path; standard `basic` is always supported. Results on some non-local storage may still not be completely exact.
- `Files.getFileAttributeView(path, PosixFileAttributeView.class)`: returns the view object if available, or `null` if that view type is unsupported.
- Other optional features (atomic move, symbolic/hard links, file locking, watch service, provider-specific options) must be looked up in the **Javadoc of the corresponding operation** and checked via actual execution with exception handling. There is no universal `isEverythingSupported()` function.

Note: **supported view names do not imply permission to perform operations**. Even if a system supports the POSIX view, changing permissions can still fail due to user privileges or read-only state. Moreover, the `FileStore` containing a specific `Path` may differ from the general capabilities of the `FileSystem`.

### 4.2. Runnable Java 17+ Example: Discovering Providers and File Attribute Views

Save `ProviderProbe.java`:

```java
import java.nio.file.FileStore;
import java.nio.file.FileSystem;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.spi.FileSystemProvider;

public class ProviderProbe {
    public static void main(String[] args) throws Exception {
        Path path = Path.of(".").toAbsolutePath().normalize();
        FileSystem fs = path.getFileSystem();
        FileStore store = Files.getFileStore(path);

        System.out.println("Path provider: "
                + fs.provider().getScheme());
        System.out.println("FileSystem attribute views: "
                + fs.supportedFileAttributeViews());
        System.out.println("FileStore supports POSIX: "
                + store.supportsFileAttributeView(PosixFileAttributeView.class));
        System.out.println("POSIX view available at Path: "
                + (Files.getFileAttributeView(
                        path, PosixFileAttributeView.class) != null));

        System.out.println("Installed providers:");
        for (FileSystemProvider provider : FileSystemProvider.installedProviders()) {
            System.out.println("  " + provider.getScheme());
        }
    }
}
```

Run:

```bash
javac ProviderProbe.java
java ProviderProbe
```

Output will **differ across Windows, Linux, macOS, filesystems, and JDKs**. For paths on the default filesystem, the scheme is typically `file`; the `posix` view is typically present on POSIX systems, though it should not be assumed always present. The list may include the `jar` provider when the ZIP filesystem provider is available. Do not take one machine's output as a portability guarantee for all machines.

### 4.3. Deciding Based on Capability and Intentional Fallbacks

Suppose you want to move a result file to a destination:

```java
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class MoveExample {
    public static void moveWithFallback(Path source, Path target)
            throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
```

This is a **method illustration snippet**, not a standalone program with `main`. The fallback branch accepts **non-atomic** semantics; use it **only when business requirements allow**. If you must publish a file where readers must never observe an intermediate state, this fallback cannot be treated as equivalent. When `ATOMIC_MOVE` is requested, handling of an existing target may vary by implementation, so overwrite rules must be designed separately. Other `IOException`s must still be propagated or handled; do not catch all errors and guess "unsupported by provider".

For POSIX permissions, you can branch only when `Files.getFileAttributeView(path, PosixFileAttributeView.class) != null`, while still handling `IOException` or permission errors at execution time. If a mandatory capability is unsupported by the provider, the right solution may be to **reject the operation and report the limitation clearly**, rather than falsely simulating the guarantee.

### 4.4. When Should You Read Provider-Specific Documentation?

Read the implementation's documentation whenever an application uses ZIP/JAR filesystems, third-party library filesystems, network/cloud filesystems, or extended open options and metadata. You need to verify:

1. URI scheme and how `FileSystem` is initialized (via `FileSystems.newFileSystem`, config map, `close()` lifecycle).
2. Path rules, case sensitivity, separators, access permissions, and read-only state.
3. File attribute views, symbolic/hard links, atomic move, watch service, and consistency characteristics.
4. Size limits, multithreaded operations, error handling, I/O blocking durations, and resource-closing behavior.

Standard Javadoc describes the common interface; do not project default provider features onto a `Path` belonging to another provider. When working with multiple `Path` sources, inspect the provider **from each `Path`** before deciding.

## 5. Classifying Errors Accurately During Lookup

| Symptom or exception | What to verify | Resolution |
| --- | --- | --- |
| `NotSerializableException` | Which component in the object graph fails serialization rules? | Inspect field types and reference paths; design suitable DTOs/serial form. |
| `InvalidClassException` | Are UID, class descriptor, and serial form changes compatible with Chapter 5? | Manage versions, migrations, or custom formats; never edit UID arbitrarily just to "bypass the error". |
| `StreamCorruptedException` | Does the stream follow the object stream protocol, or was it truncated/corrupted? | Verify source, framing, and write method; do not treat plain files as object streams. |
| `ProviderNotFoundException` | Is the provider for the scheme/file type installed and discoverable? | Check `FileSystemProvider.installedProviders()`, classpath/modules, and how it is opened. |
| `UnsupportedOperationException` | Is the API/option/view marked optional or unsupported? | Check exact overload and capability, use a valid alternative or report unsupported. |
| `AtomicMoveNotSupportedException` | Is `ATOMIC_MOVE` supported by the destination filesystem/store? | Fall back only when losing atomicity is acceptable. |
| `AccessDeniedException` / `IOException` | Permissions, actual path, device, connection, store, or implementation limits? | Log safe context, handle specific I/O errors; do not mistake every `IOException` for a missing capability. |

When distinguishing errors, prefer the exception declared by Javadoc; avoid parsing OS-specific error message strings to drive control-flow branches.

## 6. Lookup Workflow from Question to Technical Decision

**Scenario A — "Read a Unicode file reliably across all machines":**

1. Identify the problem as text: look up `Files.newBufferedReader(Path, Charset)` or `Files.readString(Path, Charset)`.
2. Read Javadoc for charset, exceptions, and closing the reader; pass `StandardCharsets.UTF_8` explicitly instead of implicitly relying on the default charset in legacy code.
3. If streaming a large file is needed, prefer `BufferedReader` or streams with `try-with-resources`; do not use `readAllBytes` just because the code is shorter.
4. Distinguish encoding errors from provider, permission, and path errors.

**Scenario B — "Persist objects and read them back after deploying a new version":**

1. Look up Javadoc for `Serializable`, `ObjectOutputStream`, and `ObjectInputStream` to identify APIs.
2. Read Serialization Specification Chapters 4–5 and each class's serial form to evaluate changes.
3. Determine whether input data is trustworthy; if not, avoid Java deserialization. If truly necessary, design class filtering and resource limits.
4. Write real compatibility tests: write data with the old version and read with the new version (and vice versa if the product requires it). A single serialize–deserialize round-trip within the same version does not verify upgrade compatibility.

**Scenario C — "Copy/move files across drives, ZIPs, or network filesystems":**

1. Look up Javadoc for `Files.copy`/`Files.move` and required options; pay special attention to atomicity, replacement, links, and attributes.
2. From each `Path`, obtain its `FileSystem`/provider, using `FileStore` and attribute views to determine capabilities that can be checked upfront.
3. Test mandatory behaviors in the target environment, handle specific exceptions, and verify post-operation integrity.
4. Never treat "works on my machine" as proof that another provider behaves identically.

A useful lookup record for each decision includes: **JDK/version → class & overload → Javadoc guarantees → specification clause (if any) → provider/capabilities → failure cases → test results on target environment**. This lets reviewers trace the reasoning without guessing sources.

## 7. Common Learning Mistakes and Self-Check

- **Looking only at method names:** ignoring `Throws`, default options, and partial read/write semantics. Fix: read the exact overload's description completely.
- **Confusing Javadoc with the Serialization Specification:** believing all compatibility rules live on `writeObject`. Fix: cross-check Specification Chapters 4–5.
- **Assuming `Serializable` automatically guarantees safety and compatibility:** these are two separate concerns. Fix: evaluate object graphs, serial form/versioning, and trust boundaries.
- **Treating `serialVersionUID` as a complete schema version:** UID only participates in compatibility checks; it does not replace checking field/hook changes.
- **Assuming Linux/Windows and all `Path`s behave the same:** inspect capabilities on the actual `FileSystem`/`FileStore`/provider.
- **Treating `supportsFileAttributeView("posix")` as guaranteed `setPermissions` authority:** API support is not operational permission.
- **Treating atomic move and fallback as equivalent:** the fallback changes guarantees when errors occur or concurrent readers exist.
- **Reading only blog examples on a different JDK:** the fix is opening the exact Javadoc/specification for the target version, then verifying with examples.

Self-check: (1) explain why `read(byte[])` must handle the number of bytes read; (2) state why two versions with the same `serialVersionUID` can still break compatibility; (3) distinguish `FileSystem.supportedFileAttributeViews()`, `FileStore.supportsFileAttributeView(...)`, and `Files.getFileAttributeView(...)`; (4) explain when falling back from `ATOMIC_MOVE` is acceptable.

## 8. Official Sources for Further Lookup

- [Java SE 21 API Javadoc — overview](https://docs.oracle.com/en/java/javase/21/docs/api/index.html)
- [`Files` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [`FileSystem` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html)
- [`FileStore` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileStore.html)
- [`FileSystems` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html)
- [`FileSystemProvider` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html)
- [`Serializable` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html)
- [`ObjectInputFilter` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/)

If the system runs Java 17, open the `/en/java/javase/17/...` documentation tree for the corresponding classes and specification. Never alter API contract conclusions based on articles describing a different JDK.
