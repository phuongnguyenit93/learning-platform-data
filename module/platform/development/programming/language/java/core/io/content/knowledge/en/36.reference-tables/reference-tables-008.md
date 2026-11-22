# Consulting Javadoc, the Serialization Specification, and Provider Capabilities in Java I/O

## 1. Purpose and How to Choose Documentation Sources

When using Java I/O, the key question is not merely "which method should I call?" but also "what behavior does Java guarantee, what behavior depends on the OS or provider, and where can errors occur?". Three information sources answer three different classes of questions:

| Source | What does it answer? | Example questions |
| --- | --- | --- |
| **Java SE Javadoc** | API signatures, semantics, parameters, return values, exceptions, guarantees, and limitations of each class/method. | Does `Files.move` guarantee atomicity? What does `InputStream.read` return at end of data? |
| **Java Object Serialization Specification** | Standard rules of the object serialization mechanism: object graphs, persisted state, stream format, restoration, version compatibility, hooks, and security. | How is `transient` handled? What happens when reading old data after changing fields or `serialVersionUID`? |
| **Documentation and capabilities of the active provider** | What a concrete implementation supports, such as file attribute views, symbolic links, atomic moves, ZIP filesystems, or file open options. | Does this `Path`'s provider support POSIX permissions? |

**Principle:** Javadoc and specifications form the contract for reasoning; runtime capability discovery helps select the right branch. An "optional" feature in Javadoc does not become universally guaranteed just because it works on a development machine.

Pin down your **target JDK version** (for example, Java 17 or 21) before looking things up. Pick the Java SE documentation matching that version; newer APIs may not exist on the runtime JDK. This article illustrates with Java 17+ and links to Java SE 21 documentation for reference.

## 2. Reading Javadoc Effectively

### 2.1. Identify the right class, package, module, and overload

Start from the class owning the operation:

- Byte streams: `java.io.InputStream`, `OutputStream`, `BufferedInputStream`, `DataInputStream`.
- Character streams and charsets: `Reader`, `Writer`, `InputStreamReader`, `OutputStreamWriter`, `java.nio.charset.Charset`.
- Filesystem/NIO.2: `java.nio.file.Path`, `Paths`, `Files`, `FileSystem`, `FileStore`, `FileSystems`.
- Object serialization: `Serializable`, `Externalizable`, `ObjectOutputStream`, `ObjectInputStream`, `ObjectStreamClass`.

Each Javadoc page specifies the **module**, **package**, `Since`, inheritance hierarchy, and overloads. `Files.copy(Path, Path, CopyOption...)` has a different contract from `Files.copy(InputStream, Path, CopyOption...)`; do not draw conclusions from the method name alone.

### 2.2. Read sections in order

1. Read the class-level description first: resources, thread-safety, characteristics, or implementor requirements.
2. Select the exact signature/overload: parameter types, varargs, generics, return type, and `throws`.
3. Read the full detailed description: defaults when no options are passed, symbolic link handling policy, and state when an operation fails.
4. Read `Parameters`, `Returns`, `Throws`, `Implementation Requirements/Notes`, `API Note`, and `See Also` if present.
5. Note down: **what is guaranteed**, **what is implementation-dependent**, **optional operations**, **exceptions to handle**, and **how to close resources**.

For example, on `InputStream.read()`: the result is an `int` representing a valid byte from 0 to 255, or `-1` at end of stream; do not cast directly to `byte` before checking `-1`. Similarly, a call to `read(byte[])` does not mean the entire array is always filled; you must check the actual number of bytes read.

For example, on `Files.newOutputStream(path)`: if no options are specified, the default is equivalent to `CREATE`, `TRUNCATE_EXISTING`, and `WRITE`. Thus "opening for writing" can wipe existing content. If you must avoid overwriting, look up `CREATE_NEW` and handle `FileAlreadyExistsException`; do not pick options by guessing.

### 2.3. "Having an API" is different from "every implementation supports it"

In Javadoc, phrases like "optional operation", "implementation specific", "if supported", and "not specified" are a crucial part of the contract.

- `Files.move(source, target, ATOMIC_MOVE)`: requests an atomic move. If it cannot be satisfied, `AtomicMoveNotSupportedException` may be thrown; do not silently assume an ordinary move is atomic too. When `ATOMIC_MOVE` is present, how an existing target is handled is implementation-specific and other options are ignored.
- `Files.copy(..., COPY_ATTRIBUTES)`: which attributes are copied depends on the filesystem/provider; last-modified time is the minimum attribute attempted when supported by both sides, and precision may be lost.
- `Files.createSymbolicLink` and `FileSystem.newWatchService` are features that may not be supported.
- `Files.getFileAttributeView(path, SomeView.class)` can return `null` when the view is unavailable; corresponding attribute-reading operations may also throw `UnsupportedOperationException`.

Also distinguish check results: `Files.exists(path) == false` **does not prove** that the file definitely does not exist; the API may simply be unable to determine existence due to permission or I/O errors. Likewise, `Files.notExists(path) == false` does not by itself prove the file exists.

## 3. Consulting the Java Object Serialization Specification Properly

Object serialization in Java is a mechanism for turning an **object graph** into a stream for persistence/exchange and restoring it according to dedicated rules. It is not synonymous with ordinary byte reading/writing via `Files` or with JSON. Rules that cannot be fully deduced from `ObjectOutputStream.writeObject` alone are specified in the **Java Object Serialization Specification**.

### 3.1. Map of sections frequently needed

| Question | Section to open in the Serialization Specification |
| --- | --- |
| Which fields are saved, object graphs, shared references, and cycles? | Chapter 1 — System Architecture, especially 1.2–1.7 and 1.14 |
| How does `Serializable` differ from `Externalizable`? | Sections 1.10–1.11, 2.4, and 3.6 |
| Customizing object writing/reading with `writeObject`/`readObject`? | Chapters 2–3, especially 2.3 and 3.4 |
| `serialVersionUID`, class descriptors, serial form? | Chapter 4, especially 4.3 and 4.6 |
| Renaming/removing/adding fields, changing types, compatibility with stored data? | Chapter 5 — Versioning of Serializable Objects |
| Stream binary layout and protocol versions? | Chapter 6 — Object Serialization Stream Protocol |
| Attack surface and deserialization errors? | Appendices A/B and `ObjectInputFilter` Javadoc |

Read the Javadoc of `Serializable`, `ObjectInputStream`, and `ObjectOutputStream` alongside the relevant specification sections. The specification defines the mechanism; Javadoc gives API call usage and specific exceptions.

### 3.2. Core rules to master

- A class declares `implements Serializable` to opt into the default serialization mechanism. This marker interface has **no methods** to implement.
- By default, eligible instance fields belong to the serial form; `static` fields do not represent per-instance state and `transient` fields are not persisted by the default mechanism. A `transient` field's value after restoration is its type's default value unless custom restoration logic sets it.
- A field referencing a non-serializable object can cause writing to throw `NotSerializableException` if that object is actually reached in the serialization graph.
- `ObjectOutputStream` writes class descriptors and object data; `ObjectInputStream` reads according to the protocol and reconstructs shared references/cycles. Do not assume the `Serializable` class's constructor runs as in normal object creation; the accessible no-arg constructor of the first **non-Serializable** superclass is invoked during restoration.
- Declaring `private static final long serialVersionUID = ...L;` on an ordinary serializable class helps control version identity. A mismatched UID can cause `InvalidClassException`; **matching UIDs do not prove every change in the class is compatible**. You must check the class evolution rules in Chapter 5.
- `private writeObject(ObjectOutputStream)`/`private readObject(ObjectInputStream)`, `writeReplace`/`readResolve`, `serialPersistentFields`, and `Externalizable` alter the protocol/serial form; read the exact declaration requirements and execution order in the specification. `Externalizable` is responsible for writing/reading its own data and requires a `public` no-arg constructor for restoration.
- Enums have dedicated serialization rules; serializable records also have dedicated rules. Do not generalize every hook of ordinary classes to enums/records.
- Java serialization is not an ideal general-purpose exchange format for long-lived APIs. When cross-language contracts or independent schema evolution are required, consider a format designed for that purpose.

### 3.3. Compilable Java 17+ example: `transient` and serial form

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

`name` is persisted; `sessionToken` is marked `transient` so its restored value is `null`. The example uses a byte array produced by the program itself and **does not read an untrusted stream**. `@Serial` lets the compiler verify certain serialization-related declarations, without altering security requirements or automatically making data compatible.

### 3.4. Security during deserialization

Do not call `ObjectInputStream.readObject()` on data controlled by an untrusted party just because you have `serialVersionUID`, `transient`, or a post-read type check. Object graph instantiation happens before the cast and can trigger logic from classes on the classpath.

If you must use native Java serialization on a controlled data source, enforce an explicit type allowlist and limit size/depth/complexity with `ObjectInputFilter` (including per-stream filters), while authenticating the source and managing versions. Javadoc warns that deserializing untrusted data is dangerous even with filtering; prefer avoiding this mechanism at untrusted boundaries.

## 4. Providers in Java NIO.2: Who Executes Operations on `Path`?

A `Path` belongs to **a specific `FileSystem`**; that `FileSystem` is supplied by a `FileSystemProvider`. The `Files` utility class typically delegates operations to the `Path`'s corresponding provider. Hence the same `Files` call can have different limitations on the default filesystem, a ZIP filesystem, or a third-party implementation.

Lookup relationship:

```text
Path ──getFileSystem()──> FileSystem ──provider()──> FileSystemProvider
  │                         │                              │
  └── Files.* operations ───┴── implements operations <────┘
```

The default provider usually has the `file` scheme. Other providers have their own schemes (for example, `jar` for ZIP/JAR filesystems when the corresponding module/provider is present). The presence of a provider must be verified on the running JVM; it cannot be inferred merely from a `.zip` extension or the existence of an API class.

### 4.1. APIs for checking capabilities at each level

- `FileSystemProvider.installedProviders()`: lists installed providers discovered by the API; `provider.getScheme()` identifies the URI scheme.
- `path.getFileSystem().provider()`: identifies the provider that actually owns `Path`; `FileSystems.getDefault()` only represents the default filesystem.
- `fileSystem.supportedFileAttributeViews()`: set of view names supported by the **filesystem**, e.g., `basic`, `posix`, `dos`, `acl`, `user` (the actual set depends on the provider).
- `Files.getFileStore(path).supportsFileAttributeView(...)`: checks view support on the **file store** containing the path; `basic` is always supported. Results on certain non-local stores may still not be completely exact.
- `Files.getFileAttributeView(path, PosixFileAttributeView.class)`: returns the view object if available, or `null` if that view type is unsupported.
- Other optional features (atomic move, symbolic/hard links, file locking, watch service, provider-specific options) must be checked in **the corresponding operation's Javadoc** and tested via the real operation with exception handling. There is no single general `isEverythingSupported()` function.

Note: **supported view names do not guarantee permission to perform an operation**. Even if a system supports the POSIX view, changing permissions can still fail due to user privileges or read-only status. Moreover, the `FileStore` holding a specific `Path` may differ from the overall `FileSystem` capabilities.

### 4.2. Runnable Java 17+ example: inspecting provider and file attribute views

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

        System.out.println("Provider của Path: "
                + fs.provider().getScheme());
        System.out.println("Attribute views của FileSystem: "
                + fs.supportedFileAttributeViews());
        System.out.println("FileStore hỗ trợ POSIX: "
                + store.supportsFileAttributeView(PosixFileAttributeView.class));
        System.out.println("POSIX view tại Path khả dụng: "
                + (Files.getFileAttributeView(
                        path, PosixFileAttributeView.class) != null));

        System.out.println("Các provider được cài đặt:");
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

Output will **vary across Windows, Linux, macOS, filesystems, and JDKs**. For paths on the default filesystem, the scheme is typically `file`; the `posix` view is commonly present on POSIX systems, though it should not be assumed always present. The list may include the `jar` provider when the ZIP filesystem provider is available. Do not treat one machine's output as a portability guarantee for all machines.

### 4.3. Deciding by capability and intentional fallback

Suppose you want to move a result file to its target location:

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

This is a **method illustration snippet**, not a standalone program with `main`. The fallback branch accepts **non-atomic** semantics; use it **only when business requirements allow**. If you must publish a file where readers must never observe an intermediate state, this fallback cannot be considered equivalent. When `ATOMIC_MOVE` is requested, handling of an existing target may differ across implementations, so overwrite rules must be designed explicitly. Other `IOException`s must still be propagated or handled; do not catch all errors and guess "provider unsupported".

For POSIX permissions, you can branch only when `Files.getFileAttributeView(path, PosixFileAttributeView.class) != null`, while still handling `IOException` or permission failures at execution time. If a mandatory feature is unsupported by the provider, the right solution may be to **reject the operation and report the limitation clearly** instead of faking guarantees.

### 4.4. When should you read provider-specific documentation?

Read the implementation's documentation whenever the application uses a ZIP/JAR filesystem, library-backed filesystems, network/cloud filesystems, or extended open options and metadata. Verify:

1. URI scheme and how to initialize `FileSystem` (via `FileSystems.newFileSystem`, configuration map, `close()` lifecycle).
2. Path rules, case sensitivity, separators, access permissions, and read-only behavior.
3. File attribute views, symbolic/hard links, atomic move, watch service, and consistency characteristics.
4. Size limits, multithreaded operations, error handling, I/O blocking behavior, and resource closing semantics.

Standard Javadoc describes the common interface; do not project features of the default provider onto a `Path` owned by another provider. When handling multiple `Path` sources, inspect the provider **from each `Path`** before deciding.

## 5. Classifying Errors Accurately When Consulting Docs

| Symptom or exception | What to verify | How to handle |
| --- | --- | --- |
| `NotSerializableException` | Which component in the object graph fails serialization rules? | Inspect field types and reference paths; design an appropriate DTO/serial form. |
| `InvalidClassException` | Are UID, class descriptor, and serial form changes compatible with Chapter 5? | Manage versions, migrations, or a custom format; do not alter UID arbitrarily to "get past the error". |
| `StreamCorruptedException` | Does the stream follow the object stream protocol, or was it truncated/corrupted? | Verify source, framing, and writer; do not treat plain files as object streams. |
| `ProviderNotFoundException` | Is the provider for the scheme/file type installed and discoverable? | Check `FileSystemProvider.installedProviders()`, classpath/modules, and how it is opened. |
| `UnsupportedOperationException` | Is the API/option/view marked optional or unsupported? | Read the exact overload and capabilities; use a valid alternative or report unsupported. |
| `AtomicMoveNotSupportedException` | Is `ATOMIC_MOVE` supported by the target filesystem/store? | Fall back only if losing atomicity is acceptable. |
| `AccessDeniedException` / `IOException` | Permissions, actual path, device, connection, store, or implementation limit? | Log safe context, handle specific I/O errors; do not mistake every `IOException` for a missing capability. |

When distinguishing errors, prefer exceptions declared in Javadoc; do not parse OS-specific error message strings to drive control flow.

## 6. Lookup Workflow from Question to Engineering Decision

**Scenario A — "Read Unicode files correctly across all machines":**

1. Identify the task as text: look up `Files.newBufferedReader(Path, Charset)` or `Files.readString(Path, Charset)`.
2. Read Javadoc for charset, exceptions, and how to close the reader; pass `StandardCharsets.UTF_8` explicitly rather than implicitly relying on the default charset in legacy code.
3. If large files need streaming, prefer `BufferedReader` or streams with `try-with-resources`; do not use `readAllBytes` just for shorter code.
4. Separate encoding errors from provider, permission, and path errors.

**Scenario B — "Persist objects and read them back after deploying a new version":**

1. Check Javadoc for `Serializable`, `ObjectOutputStream`, `ObjectInputStream` to confirm the APIs.
2. Read Serialization Specification Chapters 4–5 and each class's serial form to evaluate changes.
3. Determine whether input data is trustworthy; if not, avoid Java deserialization. If truly necessary, design class filtering and resource limits.
4. Write real compatibility tests: write data with the old version and read with the new version (and vice versa if the product requires it). A single serialize–deserialize round-trip within the same version does not verify upgrade compatibility.

**Scenario C — "Copy/move files across disks, ZIP, or network filesystems":**

1. Check Javadoc for `Files.copy`/`Files.move` and required options; especially atomicity, replacement, links, and attributes.
2. From each `Path`, inspect `FileSystem`/provider, using `FileStore` and attribute views to determine capabilities verifiable upfront.
3. Test mandatory behaviors in the target environment, handle specific exceptions, and verify integrity afterward.
4. Never treat "works on my machine" as proof that another provider behaves identically.

A useful lookup note for every decision follows: **JDK/version → class & overload → Javadoc guarantees → specification clause (if applicable) → provider/capability → failure cases → test results in the target environment**. This lets reviewers trace your reasoning without guessing sources.

## 7. Common Learning Mistakes and Self-Check

- **Reading only method names:** ignoring `Throws`, default options, and partial read/write semantics. Fix: read the exact overload's description completely.
- **Confusing Javadoc with the Serialization Specification:** assuming all compatibility rules live in `writeObject`. Fix: cross-check Chapters 4–5 of the specification.
- **Assuming `Serializable` automatically guarantees safety and compatibility:** those are two separate concerns. Fix: evaluate the object graph, serial form/versioning, and trust boundaries.
- **Treating `serialVersionUID` as a complete schema version:** the UID only participates in compatibility checks and does not replace checking field/hook changes.
- **Assuming Linux/Windows and every `Path` behave alike:** check capabilities on the actual `FileSystem`/`FileStore`/provider.
- **Assuming `supportsFileAttributeView("posix")` guarantees permission for `setPermissions`:** API capability is not execution authorization.
- **Treating atomic move and fallback as equivalent:** the fallback changes guarantees when errors occur or concurrent readers exist.
- **Reading only blog examples on a different JDK:** fix by opening the exact Javadoc/specification for the target version, then using examples to verify.

Self-check: (1) explain why `read(byte[])` must handle the actual byte count read; (2) state why an identical `serialVersionUID` can still break compatibility; (3) distinguish `FileSystem.supportedFileAttributeViews()`, `FileStore.supportsFileAttributeView(...)`, and `Files.getFileAttributeView(...)`; (4) explain when falling back from `ATOMIC_MOVE` is permissible.

## 8. Official Sources for Further Reference

- [Java SE 21 API Javadoc — overview](https://docs.oracle.com/en/java/javase/21/docs/api/index.html)
- [`Files` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [`FileSystem` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html)
- [`FileStore` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileStore.html)
- [`FileSystems` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html)
- [`FileSystemProvider` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html)
- [`Serializable` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html)
- [`ObjectInputFilter` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/)

If your system runs Java 17, open the `/en/java/javase/17/...` documentation tree for the corresponding classes and specification. Do not change API contract conclusions based on articles describing a different JDK.
