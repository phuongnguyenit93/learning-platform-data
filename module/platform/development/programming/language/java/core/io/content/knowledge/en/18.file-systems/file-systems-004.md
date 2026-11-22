# newFileSystem, getFileSystem, and Resource-Closing Ownership in Java NIO.2

## 1. The problem: What is a FileSystem and who manages its lifecycle?

In Java NIO.2 (`java.nio.file`), a `FileSystem` is an environment that manages `Path` objects, directories, files, and I/O operations according to the rules of a *file system provider*. A file system can be the operating system's default file system, the contents of a ZIP/JAR file, or a virtual file system supplied by a library.

Three objects must be distinguished:

- `FileSystemProvider`: implements the access mechanism for a type of file system and defines how to create/look up it.
- `FileSystem`: an object representing an accessed file system; it can have an `open → close` lifecycle.
- `Path`: a path belonging to **one** specific `FileSystem`. A `Path` does not own or close its `FileSystem` on its own.

For example, the path `/data.txt` inside a ZIP and the path `/data.txt` on disk do not merely differ in location: they belong to two different providers/file systems. Obtain the path to a file inside a ZIP using `zipFs.getPath("/data.txt")`, not `Path.of("/data.txt")`, which belongs to the default file system.

The decisive question when working with this API is: **Did the current code create/open a new `FileSystem`, or did it only receive a reference to a `FileSystem` managed elsewhere?** The answer decides who is allowed to call `close()`.

## 2. Three ways to obtain a FileSystem and their meanings

| API | Role | Typical result | Closing ownership |
| --- | --- | --- | --- |
| `FileSystems.getDefault()` | Gets the JVM's default file system | Same default `FileSystem` across calls | **Do not close**; `close()` on the default FS throws `UnsupportedOperationException` |
| `FileSystems.newFileSystem(uri, env)` | Asks a provider to create/open a new `FileSystem` by URI and configuration | For example, opening a ZIP via URI `jar:file:...` | Code that creates it successfully normally **owns** the `FileSystem` and must close it |
| `FileSystems.getFileSystem(uri)` | Gets a reference to an **existing** `FileSystem` looked up by the provider using URI | With ZipFS, gets a previously opened ZIP instance | Lookup code only **borrows** the reference; do not close it yourself |

`FileSystems.getFileSystem(uri)` **does not create a new instance**, does not ensure the ZIP file on disk has been mounted, and has no mechanism that increments a reference count to keep the file system alive. If no matching instance exists yet, the operation normally throws `FileSystemNotFoundException`. Details of URI lookup and matching are decided by the provider.

For `FileSystems.newFileSystem(URI, Map<String, ?>)`, Java selects a provider by the URI's *scheme*; a provider may reject an unsupported URI, invalid configuration, or a case where a file system with the same identifier already exists. A ZipFS URI uses the `jar` scheme; an ordinary `file` URI is for paths on the default file system. Do not treat these two URI types as equivalent.

Overloads to know in Java 17+:

~~~java
FileSystem a = FileSystems.newFileSystem(uri, env);
FileSystem b = FileSystems.newFileSystem(uri, env, classLoader);
FileSystem c = FileSystems.newFileSystem(path, env);
FileSystem d = FileSystems.newFileSystem(path);
~~~

These are **illustrative calls**, not a standalone program; `uri`, `env`, `classLoader`, and `path` must be defined beforehand. For overloads accepting `Path`, Java can find a provider that understands the file format (for example ZIP/JAR); the search mechanism, provider selection, and ability to open the file depend on the overload/provider. Do not assume all overloads look up the same registry or have identical duplicate-handling policies.

## 3. Runnable example: creating a ZIP FS, borrowing, closing, and reopening

Typical JDKs include the `jdk.zipfs` module, which supports viewing a ZIP/JAR as a file system. The following example uses a new temporary directory, so it does not overwrite existing files. The program creates a ZIP, writes content, obtains a *borrowed* reference to the same ZIP FS, closes it via the owner, and then reopens the ZIP to prove the data was persisted.

Create the file `FileSystemLifecycleDemo.java`:

~~~java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class FileSystemLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path tempDir = Files.createTempDirectory("nio-fs-demo-");
        Path zipFile = tempDir.resolve("example.zip");
        URI zipUri = URI.create("jar:" + zipFile.toUri());

        FileSystem owner;
        try (FileSystem zipFs =
                FileSystems.newFileSystem(zipUri, Map.of("create", "true"))) {
            owner = zipFs;

            Path entry = zipFs.getPath("/hello.txt");
            Files.writeString(entry, "Xin chào từ ZIP\n");

            // getFileSystem only borrows the currently open instance.
            FileSystem borrowed = FileSystems.getFileSystem(zipUri);
            System.out.println("Cùng đối tượng: " + (borrowed == zipFs));
            System.out.println(Files.readString(borrowed.getPath("/hello.txt")).strip());

            // Do not call borrowed.close(): owner is still using it.
        } // The owner closes ZipFS; the ZIP data is finalized.

        System.out.println("Đã đóng: " + !owner.isOpen());

        try {
            FileSystems.getFileSystem(zipUri);
        } catch (FileSystemNotFoundException e) {
            System.out.println("Không tìm thấy ZIP FS đang mở");
        }

        try (FileSystem reopened = FileSystems.newFileSystem(zipUri, Map.of())) {
            System.out.println(
                    "Đọc lại: " + Files.readString(reopened.getPath("/hello.txt")).strip());
        }

        Files.delete(zipFile);
        Files.delete(tempDir);
    }
}
~~~

Compile and run with **JDK 17+ with `jdk.zipfs`**:

~~~bash
javac FileSystemLifecycleDemo.java
java FileSystemLifecycleDemo
~~~

Expected output on a typical JDK:

~~~text
Cùng đối tượng: true
Xin chào từ ZIP
Đã đóng: true
Không tìm thấy ZIP FS đang mở
Đọc lại: Xin chào từ ZIP
~~~

Step-by-step explanation:

1. `Files.createTempDirectory` generates a dedicated directory; `zipFile.toUri()` creates a `file:` URI valid for the running platform. Prepend the `jar:` prefix to pass the URI to ZipFS.
2. `Map.of("create", "true")` is a **ZipFS-specific** configuration: create the archive file if it does not yet exist. For an existing ZIP, you can pass `Map.of()` to open it.
3. `newFileSystem` returns an instance owned by the `try` block. `getPath("/hello.txt")` returns a `Path` **inside the ZIP**.
4. `getFileSystem(zipUri)` returns the open instance; the `==` comparison is `true` in this example. The `borrowed` reference is not closed.
5. At the end of `try-with-resources`, Java calls `zipFs.close()` even if the block body throws an exception. With `jdk.zipfs`, this operation finalizes writing to the archive.
6. After closing, ZipFS no longer keeps an open instance registered for that URI; `getFileSystem(zipUri)` throws `FileSystemNotFoundException`. This is **the behavior of ZipFS in this example**; the API allows other providers to handle post-`close()` lookups differently.
7. `newFileSystem(zipUri, Map.of())` reopens the existing archive; at this point `create` is unnecessary. The reopened instance is also closed via `try-with-resources` before deleting the temporary files.

If you use a runtime image stripped of `jdk.zipfs`, the example may fail to find the `jar` provider. Run it with a full JDK containing that module; do not assume the `FileSystems` API itself supplies every provider.

## 4. Ownership rule: the creator closes, the borrower does not

**Ownership (lifecycle ownership)** is an agreement between classes/methods, not a property that `FileSystem` checks on its own. The API cannot distinguish the `owner` variable from the `borrowed` variable: both can point to **the exact same object**, and calling `close()` through either variable takes effect on that object.

Practical usage rules:

- **Created specifically for a task** via `newFileSystem`: place in `try-with-resources`, and close after all `Path` objects, streams, channels, and tasks using the file system finish.
- **Obtained via `getFileSystem` or `path.getFileSystem()`**: treat as a borrowed reference unless there is an explicit contract transferring ownership. Do not close it inside a utility function.
- **Passed as a parameter or via dependency injection**: by default it is a resource managed by the caller/application; the receiving function does not close it unless required by the contract.
- **Default file system** obtained via `getDefault()`: do not put in `try-with-resources`; `close()` throws `UnsupportedOperationException`.
- **Shared management across components/threads**: place creation/closing in an explicit owning layer (for example a service manager), ensuring no tasks are still using it before closing.

How to write a safe *borrowing* function:

~~~java
import java.io.IOException;
import java.nio.file.FileSystem;
import java.nio.file.Files;

static String readEntry(FileSystem borrowedFs, String entryName) throws IOException {
    // The function borrows FileSystem and only reads data.
    return Files.readString(borrowedFs.getPath(entryName));
    // Do not close borrowedFs here.
}
~~~

The snippet above is an **illustrative method**, which must be placed inside a class and have permission to read the desired entry. The caller retains responsibility for closing `FileSystem` if the caller created it. The read function does not hold a live reference beyond the duration of the call.

A dangerous anti-pattern:

~~~java
static String badRead(FileSystem sharedFs) throws IOException {
    try (sharedFs) {
        return Files.readString(sharedFs.getPath("/hello.txt"));
    }
}
~~~

`try (sharedFs)` is valid syntax in Java 9+ if the variable is *effectively final*, yet it is still **wrong regarding ownership** when `sharedFs` is a borrowed reference. Exiting the function closes the file system that the caller or other threads still need. Syntactic validity does not mean having the right to close a resource.

## 5. FileSystem, Path, and resources with different lifecycles

A `Path` can be stored in a variable, placed in a collection, or returned from a method, but it does not keep the file system open. Once the parent `FileSystem` has closed, read/write operations on an associated `Path` may throw `ClosedFileSystemException`. Example illustrating the error:

~~~java
Path entry;
try (FileSystem zipFs = FileSystems.newFileSystem(zipUri, Map.of())) {
    entry = zipFs.getPath("/hello.txt");
}
Files.readString(entry); // ClosedFileSystemException: ZipFS is already closed
~~~

This is only an **illustrative snippet**, assuming `zipUri` points to a valid archive. The fix is to process the content while `FileSystem` is still open, or return the read data (`String`/`byte[]`) instead of returning a `Path` whose lifecycle outlives the underlying resource.

Closing a `FileSystem` closes its associated channels, directory streams, watch services, and closeable objects per the API contract; nonetheless, local resources should still be closed immediately when finished to control errors and resource hold times. For streams from `Files.lines(...)` or `Files.walk(...)`, use a separate `try-with-resources` to close the `Stream` at the right time. Avoid closing the parent file system while streams are still running I/O operations.

Example of proper closing order (child resource closes before parent):

~~~java
try (FileSystem zipFs = FileSystems.newFileSystem(zipUri, Map.of())) {
    try (var lines = Files.lines(zipFs.getPath("/log.txt"))) {
        lines.forEach(System.out::println);
    }
} // Close ZipFS after the Stream has closed.
~~~

This illustrative snippet assumes the ZIP exists and contains `/log.txt`. When multiple errors occur inside `try-with-resources`, an error in `close()` may appear as a *suppressed exception* on the primary error; do not swallow close errors because ZipFS may need to finalize data.

## 6. Common scenarios and how to handle them

| Scenario | Behavior to understand | How to proceed |
| --- | --- | --- |
| Want to create a new ZIP | `newFileSystem(jarUri, Map.of("create", "true"))` | The owner closes it after finishing writes |
| Want to open an existing ZIP | `newFileSystem(jarUri, Map.of())` | Use `try-with-resources` within the task's scope |
| ZIP FS is already opened by another component | `getFileSystem(jarUri)` gets the open instance | Borrow and obey the owning component's lifecycle |
| No instance exists yet, but `getFileSystem` is called | `FileSystemNotFoundException` | Open with `newFileSystem` in the place assigned ownership |
| Same URI already open and `newFileSystem(URI, ...)` is called again | With ZipFS, normally throws `FileSystemAlreadyExistsException` | Organize a single clear owner; clients take borrowed references |
| Closing FS while another place is using it | Paths/I/O may encounter `ClosedFileSystemException` | Only the owner closes once all tasks have finished |
| Attempting to `close()` the default FS | `UnsupportedOperationException` | Do not close `FileSystems.getDefault()` |
| Writing to a read-only FS | `ReadOnlyFileSystemException` | Check `isReadOnly()` and the mode/provider |
| Unable to find the `jar` provider | Provider/module is missing or not loaded | Check that the JDK/runtime includes `jdk.zipfs` |
| Creating/opening a ZIP with invalid URI or config | May encounter `IllegalArgumentException`, `ProviderNotFoundException`, or `IOException` depending on API/provider | Use the right URI, config, provider, and inspect the root cause |

Do not write patterns like "if `getFileSystem` fails then call `newFileSystem`" across multiple shared call sites without synchronization. Two threads can both observe that it does not exist yet and both try to create it; one thread can receive `FileSystemAlreadyExistsException`. Moreover, obtaining a reference does not guarantee another owner will not close it immediately afterward. Resource management design must address both **ownership** and **usage lifetime**.

### Distinguishing exceptions by purpose

- `FileSystemNotFoundException`: lookup cannot find a matching file system/provider; common with `getFileSystem(uri)` when the ZIP is not yet open.
- `FileSystemAlreadyExistsException`: request to create a new instance collides with an existing file system per the provider's rules; common with `newFileSystem(URI, ...)` for the same already-open ZIP.
- `ClosedFileSystemException`: the file system is already closed, yet an operation needs to use it.
- `ProviderNotFoundException`: no suitable provider exists on certain creation/open paths; different from having a provider without an instance yet.
- `IOException`: actual error when accessing, opening, writing, flushing, or closing data; must be handled per I/O logic while preserving cause information.

Do not catch broad `RuntimeException` to mask three distinct categories of issues: **not yet open**, **already open**, and **already closed**.

## 7. Choosing an API based on practical questions

Suppose a feature needs to read a `config.json` file located inside `settings.zip`:

1. If the feature is itself responsible for opening the archive for a single read pass, create the `FileSystem` via `newFileSystem(...)`, read the data inside `try`, and close it. The method contract should return the content or data object, not return a `Path` belonging to a closed ZIP.
2. If the application already has a long-lived service managing the ZIP FS, the reading feature accepts a `FileSystem` or uses `getFileSystem(uri)` per the service's contract. Do not close it after one small request.
3. If ordinary machine paths are needed, use `Path.of(...)`/`Files...` with the default FS; do not create or close a new `FileSystem`.
4. If clients must use the ZIP file from multiple threads, the owner closes it only after all work completes; a borrowed reference is not a "lease" that automatically guards against `close()`.

Define right at the API boundary: **who creates, who borrows, how long the resource lives, and who may close it**. A helper's contract documentation should state this explicitly. If a method *returns a new `FileSystem` to the caller*, state clearly that the caller is responsible for closing it; if a method *returns a shared instance*, state clearly that the caller must not close it.

## 8. Common mistakes to avoid

- **Thinking `getFileSystem` is an open-ZIP operation**: it only looks up an existing instance; the archive existing on disk is not enough.
- **Forgetting `close()` after `newFileSystem`**: the ZIP may continue holding resources and changes may not be properly finalized in its lifecycle.
- **Closing a borrowed object**: accidentally closing the same instance that the owner and other threads are still using.
- **Closing the default FS**: `FileSystems.getDefault().close()` is unsupported.
- **Keeping a `Path` after the ZIP FS has closed**: the path cannot be used for I/O when the backing file system is no longer open.
- **Confusing `jar:` with `file:` or paths inside the ZIP**: `jar:file:/.../archive.zip` identifies the ZIP FS for ZipFS; `zipFs.getPath("/entry.txt")` identifies an entry inside that FS.
- **Manually building machine paths with hardcoded strings**: prefer `Path.toUri()` to preserve proper escaping and OS separators.
- **Relying on the provider registry as a concurrency management mechanism**: obtaining a reference does not grant ownership and does not prevent another owner from closing it.
- **Using try-with-resources indiscriminately**: use it only on a `FileSystem` that the code block owns or is contractually required to close.

## 9. Self-check questions

1. A method calls `FileSystems.getFileSystem(uri)` and gets a `FileSystem` back. Is that method allowed to close it? **Normally no**: it only borrows the reference; closing authority must be confirmed by contract.
2. A ZIP exists on disk but has never been opened with ZipFS; can `getFileSystem(jarUri)` read it right away? **No**: with ZipFS, no instance exists yet, so it normally results in `FileSystemNotFoundException`.
3. Why is returning a `Path` inside a ZIP out of a `try (FileSystem fs = ...)` block dangerous? Because the `Path` references a closed FS; subsequent I/O operations may throw `ClosedFileSystemException`.
4. When should you use `try-with-resources` with a `FileSystem`? When the code scope **owns** the newly created/opened file system and needs to guarantee closing after finishing its work.
5. Can `getDefault()` be treated like `newFileSystem(...)` to be closed at the end of a task? **No**: the default FS is a JVM-level resource, and closing it is unsupported.

## Official reference documentation

- [Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): overload signatures, provider lookup, and exceptions.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): lifecycle, `close()`, `isOpen()`, default file system.
- [Java SE 17 — jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): `jar` scheme, `create` configuration, and ZIP/JAR provider.
