# ProviderMismatchException, FileSystemNotFoundException, and ClosedFileSystemException in Java NIO.2

## 1. Context: a `Path` always belongs to a `FileSystem`

Java NIO.2 (`java.nio.file`) is not limited to a computer's disk: a `FileSystem` can represent the default file system, the contents of a ZIP/JAR (Zip File System), or a virtual file system provided by a library. `FileSystemProvider` is the component that implements access operations; a `Path` is created by a specific `FileSystem` and carries that relationship.

```text
FileSystemProvider (I/O implementation)
        |
        +-- FileSystem (an open instance / access lifecycle)
                |
                +-- Path (a path belonging to that exact FileSystem)
```

For example:

- `Path.of("report.txt")` normally belongs to the default file system, with provider scheme `file`.
- `zipFs.getPath("/report.txt")` belongs to a ZIP/JAR file system opened with `FileSystems.newFileSystem(...)`, with provider scheme `jar`.
- Two `Path` objects looking alike as character strings do not mean they share the same provider or the same file system.
- `FileSystems.getDefault()` retrieves the default file system, managed by the JVM. The default file system cannot be closed; a ZIP or custom-provider file system normally must be closed when finished.

The three exceptions in this lesson have distinct causes: **mixing objects from incompatible providers**; **looking up a file system that does not exist in the access context**; **using a closed file system**. Understanding `Path` origin and `FileSystem` lifecycle helps diagnose them accurately.

## 2. Quick comparison table

| Exception | Exception hierarchy | Typical cause | Proper action |
| --- | --- | --- | --- |
| `ProviderMismatchException` | `IllegalArgumentException` → `RuntimeException` | An API requires `Path` objects from the same provider, yet receives a `Path` created by another provider | Check the `Path` origin; create the auxiliary `Path` using the same `FileSystem`, or use an API that supports transferring data across providers |
| `FileSystemNotFoundException` | `RuntimeException` | A `FileSystem` for a URI is needed, yet no matching instance exists; or URI conversion cannot automatically find/create the file system | Check the URI, provider, and the open/mount step before accessing |
| `ClosedFileSystemException` | `IllegalStateException` → `RuntimeException` | Calling an access operation through a `Path` belonging to a closed `FileSystem` | Ensure access stays within the time the file system is open; do not retain a `Path` for use after the owner closes it |

All three are **unchecked exceptions**: you do not have to declare `throws` in method signatures. They differ from `IOException`, `NoSuchFileException`, and `AccessDeniedException`, which reflect specific I/O or access errors. Do not lump every path-related error together as "file does not exist".

## 3. `ProviderMismatchException`: mixing paths from different providers

### 3.1. When it occurs

`ProviderMismatchException` is thrown when a method operating on an object created by provider A receives an argument created by provider B when that method requires the same provider. A familiar situation is combining a `Path` from the default file system with a `Path` from Zip File System in `resolve(Path)` or `relativize(Path)`.

Conceptual example:

```java
Path hostPath = Path.of("logs");       // Default file provider
Path zipPath = zipFs.getPath("a.txt"); // ZipFS jar provider

hostPath.resolve(zipPath);             // Incompatible providers
```

This is an illustrative snippet inside a method; `zipFs` must be an already-open ZIP `FileSystem`. On the JDK's standard file/ZipFS providers, this `resolve(Path)` call throws `ProviderMismatchException`.

**Do not conclude that every API taking two `Path` objects rejects different providers.** For example, `Files.copy(source, target)` supports copying across providers, although attributes, atomicity, and supported options depend on the providers. You must read the specific API contract.

### 3.2. How to identify it

```java
System.out.println(hostPath.getFileSystem().provider().getScheme());
System.out.println(zipPath.getFileSystem().provider().getScheme());
System.out.println(hostPath.getFileSystem() == zipPath.getFileSystem());
```

Typically the two schemes are `file` and `jar`; identity comparison tells you whether the two `FileSystem` objects are the same instance. **Having the same scheme does not prove two `FileSystem` objects are the same instance**: one provider can manage multiple file systems, such as different ZIP archives.

### 3.3. How to fix it while preserving the intended semantics

If you want to compute a child path **inside the ZIP**, use a `Path` created by the ZIP:

```java
Path zipBase = zipFs.getPath("/docs");
Path zipChild = zipBase.resolve("lesson.txt");  // resolve(String) using zipBase's provider
```

If you need a `Path` on the default filesystem, create it with `Path.of(...)`, `FileSystems.getDefault().getPath(...)`, or `hostBase.resolve("name")`. Do not use `Path.toString()` followed by `Path.of(...)` to "convert" a file inside a ZIP into a real file: the string `/docs/lesson.txt` is just a path name, containing neither the ZIP content nor its context.

If you want to **move data** between file systems, consider `Files.copy(zipEntry, hostFile)` or `Files.newInputStream(zipEntry)` combined with an output stream at the destination, based on data requirements and I/O exceptions. If you want to **relativize** two paths, ensure they belong to the same file system and satisfy root constraints before calling `relativize`.

## 4. `FileSystemNotFoundException`: unable to find the file system to access

### 4.1. Difference between "missing file" and "file system not yet open"

`FileSystemNotFoundException` is not a message saying `docs/report.txt` was deleted. It concerns **locating a file system**, for example when calling:

```java
FileSystems.getFileSystem(uri);
```

`getFileSystem(URI)` only **looks up an existing file system** recognized by the provider through the URI's scheme. It is not responsible for creating a new file system. For ZipFS, if the file system for that URI has not been opened yet, the standard ZIP provider throws `FileSystemNotFoundException`.

```java
URI zipFsUri = URI.create("jar:file:///path/to/archive.zip");

// Before calling FileSystems.newFileSystem(zipFsUri, ...):
FileSystems.getFileSystem(zipFsUri); // May throw FileSystemNotFoundException
```

The path `jar:file:///path/to/archive.zip` illustrates URI format, not a portable path across all OSes. In real code, construct the URI from `archive.toUri()` to avoid invalid characters, spaces, or Windows separator issues.

`Path.of(URI)` has its own rules: it delegates to a provider to convert the URI into a `Path`, and may throw `FileSystemNotFoundException` when a file system cannot be found or auto-created, **or when there is no provider for the scheme**. Meanwhile, `FileSystems.getFileSystem(URI)` may throw `ProviderNotFoundException` if the corresponding provider is not installed. Different APIs and conditions should not be lumped together.

### 4.2. `getFileSystem`, `newFileSystem`, `getDefault`

| API | Meaning | Notes |
| --- | --- | --- |
| `FileSystems.getDefault()` | Gets the JVM's default file system | Not an API for mounting ZIP/JAR archives |
| `FileSystems.getFileSystem(uri)` | Finds an existing file system by URI | Does not auto-create; when none exists, may throw `FileSystemNotFoundException` |
| `FileSystems.newFileSystem(uri, env)` | Asks a provider to create/open a file system by URI | May throw `IOException`, `ProviderNotFoundException`, `FileSystemAlreadyExistsException`, or configuration errors |
| `Path.of(uri)` | Converts a URI into a `Path` via a provider | Some providers allow auto-creating the file system; some require mounting first |
| `Files.exists(path)` | Checks a specific path | `false` does not mean the file system provider does not exist |

If you want to use a URI to an item inside a ZIP after the file system is opened, `Path.of(jarEntryUri)` is sometimes suitable, though URI syntax is provider-specific. A clearer approach in code managing ZipFS is to keep the `FileSystem` object and use `zipFs.getPath("/inside.txt")`.

### 4.3. Do not "fix" it by unconditionally reopening repeatedly

`newFileSystem` is also not an idempotent "ensure a file system exists" function: if a file system for that URI already exists and the provider allows only one instance, it may throw `FileSystemAlreadyExistsException`. When an application has multiple components sharing a ZIP FS, clearly specify **who creates, who holds, and who closes** it. Avoid "fixes" that catch every exception and call `newFileSystem` or close an object owned by another component.

## 5. `ClosedFileSystemException`: using a file system after closing

A `FileSystem` is open when created. For closable file systems such as ZIP FS, calling `close()` releases that instance's resources. After closing, access operations through associated `Path` objects may throw `ClosedFileSystemException`.

Common error pattern:

```java
Path saved;
try (FileSystem zipFs = FileSystems.newFileSystem(zipUri, Map.of())) {
    saved = zipFs.getPath("/report.txt");
}
// zipFs is already closed: saved is still a Path object
Files.readString(saved); // ClosedFileSystemException with standard ZipFS
```

This snippet illustrates resource scope; it assumes `zipUri` points to an existing ZIP. The fact that `Path` is still reachable **does not prove its file system is still open**. `toString()` or syntactic name access on `Path` will not necessarily throw an exception, whereas I/O operations require an active file system.

**You cannot "reopen" a closed instance via `isOpen()`.** You may have to create a new `FileSystem` instance through the provider (if supported) and reconstruct `Path` objects from the new instance. Do not keep using old `Path` objects obtained from the old instance.

### 5.1. The try-with-resources trap

Wrong context:

```java
static Path locate(FileSystem zipFs) {
    return zipFs.getPath("/data.txt");
}
```

The function above only returns a `Path`; the caller must ensure `zipFs` stays alive until I/O finishes. If code closes `zipFs` before the caller uses the result, the bug lies in **lifecycle management**, not in `locate` or path syntax.

An easier-to-control design is to open and process content in the same scope:

```java
static String readEntry(FileSystem zipFs) throws IOException {
    return Files.readString(zipFs.getPath("/data.txt"));
}
```

`readEntry` still requires the caller to keep `zipFs` open during the call. Another option is for the component owning ZipFS to perform all I/O and then return content or data detached from the ZipFS lifecycle. Avoid returning long-lived streams, iterators, or `Path` objects without documenting their lifecycle.

### 5.2. Default and custom providers

`FileSystems.getDefault().close()` is not used to "refresh": the default file system cannot be closed. With custom providers, rules for sharing, caching, reopening, and closing may differ, yet the closed-file-system contract remains important. Do not confuse `ClosedFileSystemException` with `ClosedWatchServiceException`, because a watch service has its own lifecycle.

## 6. Runnable Java 17+ example: all three exceptions in one program

This program uses the **ZIP File System** included in JDK distributions containing the `jdk.zipfs` module. It creates a new ZIP in a temporary directory; tries looking it up before mounting; mounts it and mixes `Path` objects from two providers; closes ZipFS and tries reading the old entry. The example cleans up the resources it creates.

Create the file `FileSystemExceptionsDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.ClosedFileSystemException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderMismatchException;
import java.util.Map;

public class FileSystemExceptionsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-provider-");
        Path archive = dir.resolve("sample.zip");

        // Create a jar: URI from the normalized URI of the real ZIP file.
        URI zipUri = URI.create("jar:" + archive.toUri());
        Path zipEntry = null;

        try {
            // Case 1: this new ZIP file system has not been opened yet.
            try {
                FileSystems.getFileSystem(zipUri);
                System.out.println("already mounted");
            } catch (FileSystemNotFoundException ex) {
                System.out.println("before mount: FileSystemNotFoundException");
            }

            // Open the ZIP; try-with-resources will close ZipFS at the end of the block.
            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                zipEntry = zipFs.getPath("/lesson.txt");
                Files.writeString(zipEntry, "Hello ZIP");
                System.out.println("zip content: " + Files.readString(zipEntry));

                // Case 2: default Path + ZipFS Path in resolve(Path).
                Path hostDir = Path.of("local");
                Path zipRelative = zipFs.getPath("relative.txt");
                try {
                    hostDir.resolve(zipRelative);
                    System.out.println("resolved unexpectedly");
                } catch (ProviderMismatchException ex) {
                    System.out.println("mixed resolve: ProviderMismatchException");
                }

                System.out.println("zip open: " + zipFs.isOpen());
            }

            // Case 3: Path still exists in memory, but ZipFS has closed.
            try {
                Files.readString(zipEntry);
                System.out.println("read unexpectedly");
            } catch (ClosedFileSystemException ex) {
                System.out.println("after close: ClosedFileSystemException");
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

Compile and run from the directory containing the source file:

```bash
javac FileSystemExceptionsDemo.java
java FileSystemExceptionsDemo
```

Expected output on a standard JDK 17+ with `jdk.zipfs`, temporary directory write permission, and no concurrent interference:

```text
before mount: FileSystemNotFoundException
zip content: Hello ZIP
mixed resolve: ProviderMismatchException
zip open: true
after close: ClosedFileSystemException
```

Timeline explanation:

1. The `jar:` URI identifies the file system for the new ZIP file; `getFileSystem` only searches for an already-open instance, so it reports `FileSystemNotFoundException`.
2. `newFileSystem(..., Map.of("create", "true"))` opens ZipFS and creates the archive; `Files.writeString` and `Files.readString` perform I/O through a valid `zipEntry`.
3. `hostDir.resolve(zipRelative)` receives a `Path` belonging to the `jar` provider while `hostDir` belongs to the `file` provider, resulting in `ProviderMismatchException` in the JDK's file + ZipFS implementations.
4. Leaving `try` closes the ZIP. `zipEntry` still exists as a Java object, yet `Files.readString(zipEntry)` accesses the closed ZipFS and reports `ClosedFileSystemException`.
5. The `finally` block cleans up the ZIP and temporary directory after releasing ZipFS. Environment errors such as insufficient permissions, missing `jdk.zipfs` module, or I/O corruption can cause the program to throw another exception and not print all lines above.

**Note:** the example uses the same ZIP FS on a single thread. If multiple threads or libraries operate on a ZIP concurrently, define ownership so one component does not close a file system while another is still reading.

## 7. Same symptom, three different fixes

Suppose code processes ZIPs across multiple service layers:

```text
Request -> URI or Path -> select FileSystem -> read entry
                           |                   |
                           |                   +-- already closed -> ClosedFileSystemException
                           +-- not mounted / wrong lookup -> FileSystemNotFoundException
         +-- mixed host Path with zip Path -> ProviderMismatchException
```

For `ProviderMismatchException`, the first step is checking `path.getFileSystem()` and `path.getFileSystem().provider()` on each argument. If the intent is syntactic path manipulation inside the ZIP, create the argument via ZIP FS. If the intent is copying content, use a data-transfer API specified to support differing providers.

For `FileSystemNotFoundException`, inspect the URI `scheme`, mounting timing, container path, and whether `FileSystems.getFileSystem` uses the exact URI passed to `newFileSystem`. Do not immediately "fix" it with `Files.createFile`: a file entry and a file system are two different layers.

For `ClosedFileSystemException`, identify the `close()` call, `try-with-resources`, or cache eviction component that ran before I/O. Do not merely catch the exception and retry with the same `Path`: it still points to the closed instance.

## 8. Distinguishing from easily confused exceptions

| Other exception | When to suspect it | Distinction |
| --- | --- | --- |
| `NoSuchFileException` | Target path does not exist during an I/O operation | The file system may be open and working; only the file entry is missing |
| `ProviderNotFoundException` | No provider exists for the URI scheme in a provider lookup/open API | Different from having the provider installed without creating a file system instance |
| `FileSystemAlreadyExistsException` | Opening a new file system for a URI already mounted when the provider forbids duplicate instances | Opposite of looking up an absent file system; does not mean an entry already exists |
| `FileSystemException` | File system error during a specific operation | An `IOException` that may carry file, otherFile, and reason; not synonymous with closed/mismatch |
| `IllegalArgumentException` / `InvalidPathException` | Invalid URI or path syntax | Formatting/precondition error; validate input data |
| `ClosedWatchServiceException` | Using a closed `WatchService` | Watch service lifecycle differs from `FileSystem` lifecycle |

Notably, **`ProviderMismatchException` is a subclass of `IllegalArgumentException`**. If you want to handle mismatch cases separately, place `catch (ProviderMismatchException)` before `catch (IllegalArgumentException)` (if both are needed); otherwise Java reports an unreachable catch block.

## 9. Designing a service that accesses multiple file systems

### 9.1. Defining ownership

For a feature that reads documents from a ZIP, you can choose:

- Each operation opens the ZIP, reads all required data, and closes it before returning the result.
- One dedicated component manages a shared ZIP FS; everyone uses it through that component, and only this component closes it when no tasks remain.
- The API returns independent data such as `byte[]`, `String`, or a DTO after finishing reads; if returning a stream or `Path`, specify who keeps the resource open and when it closes.

Use `try-with-resources` for instances created by that scope itself, but **do not arbitrarily close** a file system passed in by a caller. Avoid storing ZipFS `Path` objects in a singleton longer than the ZipFS lifecycle.

### 9.2. Keeping `Path` origins consistent

A method accepting paths inside a ZIP should take a `FileSystem` or a ZIP `Path` as the root; create children with `root.resolve("name")` to keep the same provider. If an external target outside the ZIP is needed, pass a separate host `Path` and invoke a cross-provider-capable operation instead of mechanically calling `host.resolve(zipPath)`.

Avoid using `toString()` to infer a provider or `Path.of(...)` to convert arbitrarily. `Path.toUri()` carries more context than a name string, yet the URI still must be handled through an appropriate provider/file system; it is not a universal "switch provider" trick.

### 9.3. Separating layers when logging

When an error occurs, useful diagnostic fields include: operation name, provider scheme, URI identifying the file system (if present and appropriate), `isOpen()` state, `Path` argument type, and stack trace. Avoid logging sensitive details or verbatim secret paths at public log levels. Only call `Files.exists()` to diagnose an entry if genuinely needed; it does not replace checking file system state.

## 10. Troubleshooting checklist

1. **Which API is being called?** `resolve`/`relativize`, `getFileSystem`/`Path.of(URI)`, or a read/write operation like `Files.readString`?
2. **Where was the `Path` created?** Host `Path.of`, `zipFs.getPath`, or another provider library?
3. **Do both arguments belong to the same provider?** If not, verify whether the API allows cross-provider usage.
4. **Is the provider installed?** If a scheme is missing, check `ProviderNotFoundException` or the called method's contract.
5. **Has the file system been created/mounted yet?** `getFileSystem` does not auto-create; an appropriate `newFileSystem` step is required.
6. **Has the file system been closed?** Check `isOpen()` while still holding a reference and audit ownership/`try-with-resources`.
7. **Is there a race with another thread?** State can change after checking; ensure usage duration does not overlap with closing time.
8. **Does the fix match the requirement?** If data must be copied from ZIP to host, use copy; if building paths inside the ZIP, create children via the ZIP FS itself; if lookup is needed, ensure the mount exists.

## 11. Comprehension check exercises

**Exercise 1.** Two `Path` objects both print as `"/a.txt"`. Can they be passed into any `resolve(Path)` call?

**Answer:** No. Identical string representations do not prove they share the same provider; check `getFileSystem()`/provider and the API contract.

**Exercise 2.** A real `archive.zip` file exists on disk, yet `FileSystems.getFileSystem(zipUri)` throws `FileSystemNotFoundException`. Why?

**Answer:** An existing ZIP file does not mean a ZipFS instance for that URI is currently mounted. `getFileSystem` looks up an instance; `newFileSystem` is the API that creates/opens it.

**Exercise 3.** After `try (FileSystem fs = ...)`, the variable `Path p = fs.getPath("/x")` is still non-`null`. Can `Files.readString(p)` be called?

**Answer:** You cannot expect success because `p` is bound to a closed file system; standard ZipFS throws `ClosedFileSystemException`.

**Exercise 4.** Can `Files.copy(zipEntry, hostTarget)` succeed when the two `Path` objects belong to different providers?

**Answer:** Yes; `Files.copy` is specified to support differing providers. You still must handle `IOException`, options that may be unsupported or have different semantics, and ensure ZipFS stays open throughout the operation.

**Exercise 5.** If `newFileSystem(uri, env)` encounters `FileSystemAlreadyExistsException`, should you immediately close the existing instance?

**Answer:** No. You must determine the owner and sharing policy; closing it could break ongoing operations in another component.

## Official references

- Java SE 21, `ProviderMismatchException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ProviderMismatchException.html
- Java SE 21, `FileSystemNotFoundException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystemNotFoundException.html
- Java SE 21, `ClosedFileSystemException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ClosedFileSystemException.html
- Java SE 21, `FileSystems`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html
- Java SE 21, `FileSystem`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html
- Java SE 21, `Path`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html
