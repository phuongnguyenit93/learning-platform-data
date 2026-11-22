# Temporary Files, Absolute Paths, and Resources Packaged in JARs

Java applications often work with many types of file resources: external configuration files, temporary files created by the application, data packaged in JARs, and files extracted for use by native libraries or external tools. When bringing an application into CRaC, it is necessary to clearly distinguish these types because a checkpoint saves the process state, while content on the filesystem is still managed by the filesystem and the deployment environment.

A `Path` or `File` still existing in the heap after restore does not prove that the file at that path still exists, still has the same content, or is still accessible. Temporary directories may be cleaned up, containers may be recreated, mounts may change, and access permissions may differ. Conversely, a resource located inside a JAR is not necessarily an independent file on the filesystem that can be opened with `File`.

When designing, answer three questions: where does the file come from, how long does it need to exist, and what will the application do if the file is no longer present after restore? The answers determine whether to read directly from the classpath, create a temporary file, use a configured working directory, or store data in a durable location.

## 1. Distinguishing Filesystem Resources and Resources Inside a JAR

A file on the filesystem has a path that the operating system can resolve, for example `/var/lib/myapp/config.yml` or `C:\\app\\config.yml`. Java can operate on it through `Path`, `Files`, `FileChannel`, and related APIs.

A resource packaged in a JAR is an entry inside an archive, for example:

```text
application.jar
└── BOOT-INF/classes/
    └── templates/
        └── report-template.xlsx
```

The entry `templates/report-template.xlsx` does not necessarily exist as an independent file in the deployment directory. When running the application from an IDE, the resource may reside in `target/classes` or `build/resources/main`, so some access methods appear to work. When running the application from an executable JAR, the resource can be read through the class loader from inside the archive or from a nested JAR structure.

Therefore, you should not assume every classpath resource can be converted into a `File` or `Path`. If you only need to read the content, use `InputStream`:

```java
import java.io.IOException;
import java.io.InputStream;

public final class TemplateReader {

    public byte[] readTemplate() throws IOException {
        try (InputStream input = TemplateReader.class
                .getResourceAsStream("/templates/report-template.xlsx")) {
            if (input == null) {
                throw new IOException("Template resource was not found");
            }
            return input.readAllBytes();
        }
    }
}
```

`getResourceAsStream()` works with resources on the classpath without requiring the resource to be an independent file. A leading `/` in the resource name in `Class.getResourceAsStream()` indicates a path relative to the classpath root. If using `ClassLoader.getResourceAsStream()`, the name usually does not have a leading `/`.

For large data, you can process it directly as a stream instead of reading everything into a `byte[]`, in order to avoid increasing heap memory. You should only extract to the filesystem when the subsequent API strictly requires a file path.

## 2. Relative Paths and Absolute Paths

Relative paths are resolved based on the current working directory of the process. For example:

```java
Path relative = Path.of("data/input.csv");
Path absolute = relative.toAbsolutePath();

System.out.println("user.dir = " + System.getProperty("user.dir"));
System.out.println("relative = " + relative);
System.out.println("absolute = " + absolute);
```

If the application is launched from a different directory, the same relative path can point to a different location. This often happens when switching between an IDE, a local run command, a service manager, a Docker container, or a deployment environment.

`toAbsolutePath()` converts a relative path into an absolute path according to the default filesystem and the working directory of the process. `normalize()` removes `.` and `..` elements according to path syntax rules. These two operations do not prove the file exists, do not check access permissions, and do not guarantee the path can be used on another machine.

```java
Path configured = Path.of("./data/../data/input.csv");
Path absoluteNormalized = configured.toAbsolutePath().normalize();

System.out.println(absoluteNormalized);

if (Files.exists(absoluteNormalized)) {
    Path actual = absoluteNormalized.toRealPath();
    System.out.println("resolved existing path = " + actual);
}
```

`toRealPath()` requires the path to exist and be accessible; it resolves symbolic links according to the options used. Therefore, distinguish:

| API | Meaning | What is not guaranteed |
|---|---|---|
| `Path.of("data/a.txt")` | Creates a path representation | Does not automatically create the file or directory |
| `toAbsolutePath()` | Converts to an absolute path | Does not guarantee the file exists or exists after restore |
| `normalize()` | Normalizes `.` and `..` elements | Does not access the filesystem to verify |
| `toRealPath()` | Resolves an existing path on the filesystem | Does not guarantee the mount or content remains the same in the future |

For data that needs to persist across multiple startups, you should configure an explicit working directory instead of relying on the current directory. For example, get `app.data-dir` from deployment configuration, convert it to an absolute path, and create the directory if permitted:

```java
Path dataDirectory = Path.of(configuredDataDirectory)
        .toAbsolutePath()
        .normalize();

Files.createDirectories(dataDirectory);

Path inputFile = dataDirectory.resolve("input.csv");
```

Absolute paths help reduce dependency on the current working directory, but they are still tied to the environment's filesystem. If restored to another container or host, the same path string may not exist or may point to a mount with different content. For important data, use a managed volume or durable storage and re-verify the path after restore.

## 3. Creating and Managing Temporary Files

Temporary files are suitable for intermediate data that only needs to exist for a period of time, such as extraction results, converted content, data passed to a library that only accepts `File`, or input for a native process.

You should use `Files.createTempFile()` or `Files.createTempDirectory()` instead of manually concatenating file names in `/tmp` or the Windows temporary directory:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TemporaryFiles {

    public Path createWorkFile() throws IOException {
        Path temporaryFile = Files.createTempFile(
                "myapp-job-",
                ".tmp");

        Files.writeString(temporaryFile, "temporary work data");
        return temporaryFile;
    }
}
```

If you need to place the file in a specific directory, pass that directory to the API:

```java
Path workDirectory = Path.of(configuredWorkDirectory)
        .toAbsolutePath()
        .normalize();

Files.createDirectories(workDirectory);

Path temporaryFile = Files.createTempFile(
        workDirectory,
        "conversion-",
        ".bin");
```

The temporary file creation API generates a unique name and creates the file in a filesystem operation, helping avoid the bug pattern of manually concatenating a fixed name and having multiple processes write to it simultaneously. You should not construct paths from user data without checking directory scope, because `..` elements or symbolic links can cause the path to escape the intended directory.

### Lifecycle of Temporary Files

Temporary files need a clear owner and deletion time. For short work within a single call, you can use `try/finally`:

```java
Path temporaryFile = Files.createTempFile("myapp-", ".tmp");
try {
    generateIntermediateData(temporaryFile);
    consumeIntermediateData(temporaryFile);
} finally {
    Files.deleteIfExists(temporaryFile);
}
```

For files used by a bean or service throughout the application lifecycle, they must be managed according to the component's lifecycle. You can keep the `Path` in a field, but after restore you must verify that the file still exists and has the right content. If the file is only regenerable data, a simple approach is to delete it before checkpoint and recreate it after restore.

You should not treat `File.deleteOnExit()` as a lifecycle management mechanism for checkpoints. This call registers the file for deletion when the JVM terminates normally; a checkpoint is not a normal shutdown and does not cause file deletion hooks to run at snapshot time. Furthermore, restoring does not automatically restore file content that has been deleted by the filesystem.

### Temporary Files Are Not Durable Storage

System temporary directories can be cleaned up by the operating system, container runtime, cleanup jobs, or the application itself. In some environments, `/tmp` resides on an ephemeral filesystem or is deleted when a container is replaced. A path stored in the heap can remain a valid string while the file has disappeared.

If data is needed to continue business operations after restore, it should not be stored only in temporary files. Store the data in a persistent volume, database, object storage, or a storage system with a managed lifecycle. Temporary files should only contain regenerable data or data that the application can recover from a durable source.

## 4. Checkpoints Save Process State, Not the Filesystem Automatically

CRaC focuses on process state. The content of a regular file still belongs to the filesystem and the operating system's checkpoint/restore mechanism. You should not assume that creating a checkpoint will copy all files the application has read or written into the checkpoint artifact.

For example, the application creates `/tmp/report-123.bin`, stores the `Path` in a field, and then checkpoints. After some time, the system may clean up `/tmp/report-123.bin`. Upon restore, the field still holds the old path, but `Files.exists(path)` may return `false`.

```java
if (Files.exists(temporaryFile)) {
    process(temporaryFile);
} else {
    temporaryFile = regenerateTemporaryFile();
}
```

Checking existence is necessary but sometimes not enough. The file may exist, but its content may have changed, permissions may have changed, or the file may belong to another run. For regenerable data, you should check the checksum, version, or required metadata. For important data, use a durable source of truth and a safe data-writing protocol.

### When Can Files Be Kept Across a Checkpoint?

Files can be kept if the deployment environment guarantees the corresponding filesystem and mount remain available, the content is not unexpectedly modified, and the application has a way to verify it after restore. For example, a file on a stably mounted persistent volume can be kept if the deployment policy guarantees that mount is attached to the restored process.

Even when a file is kept, open handles, file locks, memory mappings, and native library state must be evaluated separately. Follow the guidance of the CRaC JDK, the operating system, and the libraries in use. An existing `Path` does not mean an old `FileChannel` or lock can be safely used after restore.

## 5. Reading Resources Packaged in a JAR

For read-only resources, use the class loader or `Class.getResourceAsStream()`:

```java
try (InputStream input = MyService.class
        .getResourceAsStream("/templates/email.html")) {
    if (input == null) {
        throw new IOException("email.html was not found on the classpath");
    }

    String template = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8);
}
```

This approach works both when the resource is in the classpath directory during development and when it is packaged inside a JAR. It also avoids assuming that a resource URL is always a regular filesystem path.

### Why Can `getResource(...).getFile()` Fail?

In a development environment, the resource URL might look like `file:/.../classes/templates/email.html`. When running from a JAR, the URL might look like `jar:file:/.../application.jar!/templates/email.html` or a URL format provided by a framework's class loader. The `!/templates/email.html` part indicates an entry inside an archive, not a directory on the filesystem.

Therefore, the following code is not general-purpose:

```java
URL resource = MyService.class.getResource("/templates/email.html");
File file = new File(resource.getFile());
```

It may work in an IDE and then fail when the application is packaged. `Paths.get(resource.toURI())` can also only be used directly when the URI belongs to an appropriate filesystem provider, such as the `file` scheme. A `jar` scheme URI does not automatically turn an entry in a JAR into a `Path` of the default filesystem.

Java has a Zip/JAR filesystem provider and can open an archive as a `FileSystem` in some cases, but that approach requires managing the filesystem lifecycle, handling nested archives, and depends on the class loader/packaging method. For applications that need to run across multiple environments, `InputStream` is usually the simpler and more reliable choice.

## 6. When an API Needs a File Path: Extracting Resources from a JAR

Some libraries only accept a file path instead of an `InputStream`. In that case, copy the classpath resource to a temporary file managed by the application:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class ResourceExtractor {

    public Path extractSchema() throws IOException {
        try (InputStream input = ResourceExtractor.class
                .getResourceAsStream("/schemas/customer.schema")) {
            if (input == null) {
                throw new IOException("customer.schema was not found");
            }

            Path extracted = Files.createTempFile(
                    "customer-schema-",
                    ".schema");
            try {
                Files.copy(input, extracted,
                        StandardCopyOption.REPLACE_EXISTING);
                return extracted;
            } catch (IOException exception) {
                Files.deleteIfExists(extracted);
                throw exception;
            }
        }
    }
}
```

After extracting, pass the absolute `Path` to the API that needs the file. Close the `InputStream` immediately after copying so as not to hold the archive handle longer than necessary. If the library uses the file for a long time, determine who owns the file and when it is allowed to be deleted.

If the extracted file is small data, you can read it into a `byte[]` before checkpoint and recreate the file from the byte array after restore. If the data is large, re-read it from the JAR after restore to avoid keeping an extra large copy in the heap. In both cases, ensure the JAR and class loader are still available when the extraction operation takes place.

### Resources Requiring Execute Permissions

Some native libraries or external tools require extracted files to have execute permissions. Files created by `createTempFile()` do not by default have the same permissions as the original file on all operating systems. Set the minimum required permissions per platform, check the operation result, and do not assume POSIX permission APIs are available on Windows. For native libraries, prefer the resource loading mechanism supported by the library; extracting and loading native libraries also has specific constraints regarding architecture, ABI, and the lifecycle of native state during checkpoint/restore.

## 7. Managing Extracted Files Through the CRaC Lifecycle

If an extracted file is only temporary data that can be recreated from a JAR resource, it can be deleted before checkpoint and re-extracted after restore. This avoids depending on whether the temporary directory is preserved.

The example below illustrates a resource that manages an extracted file:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class ExtractedSchema implements Resource {

    private volatile Path file;

    public ExtractedSchema() throws IOException {
        file = extract();
        Core.getGlobalContext().register(this);
    }

    public Path getFile() {
        Path current = file;
        if (current == null || !Files.isRegularFile(current)) {
            throw new IllegalStateException("Schema file is not ready");
        }
        return current;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopUsersAndWait();
        if (file != null) {
            Files.deleteIfExists(file);
            file = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        file = extract();
        resumeUsers();
    }

    private Path extract() throws IOException {
        try (InputStream input = ExtractedSchema.class
                .getResourceAsStream("/schemas/customer.schema")) {
            if (input == null) {
                throw new IOException("customer.schema was not found");
            }

            Path target = Files.createTempFile("customer-schema-", ".schema");
            try {
                Files.copy(input, target,
                        StandardCopyOption.REPLACE_EXISTING);
                return target;
            } catch (IOException exception) {
                Files.deleteIfExists(target);
                throw exception;
            }
        }
    }

    private void stopUsersAndWait() throws Exception {
        // Stop new calls and wait for consumers currently using the file to finish.
    }

    private void resumeUsers() {
        // Allow consumers to use the new file after successful extraction.
    }
}
```

The `stopUsersAndWait()` and `resumeUsers()` methods are integration points with the real application. Before deleting the file, you must ensure no threads are still reading or writing it. If draining fails, the callback needs to report an error so the checkpoint does not proceed in an unsafe state. After restore, only resume consumers once the file has been created and verified successfully.

This example assumes the resource in the JAR can be re-read after restore. If the class loader or archive is no longer available, use a durable source or store appropriate data in memory before checkpoint. If the file must persist across the checkpoint because a native process needs to continue using it, do not delete the file; instead, place it on a filesystem guaranteed to exist, verify its content and permissions after restore, and handle the handles/native state according to the corresponding guidelines.

## 8. Absolute Files, Working Directories, and Container Environments

In a container, an absolute path still only has meaning within the filesystem namespace visible to the container. For example, `/app/data/input.csv` may exist in a current container but not in a new container if that directory is not on a mounted volume. Similarly, `/tmp` is usually suitable for temporary data in a short lifecycle, but should not be used as storage that needs to persist long-term.

Distinguish the following locations:

| Location | Suitable purpose | Considerations on restore |
|---|---|---|
| Classpath/JAR | Read-only resources packaged with the application | Read via class loader; archive must still be available when re-reading is needed |
| System temporary directory | Regenerable intermediate data | May be cleaned up or changed; check and recreate |
| Configured working directory | Application files needing an explicit path | Verify directory, permissions, and mount after restore |
| Persistent volume | Data that needs to persist across process/container replacement | Check that the volume is mounted properly and content is consistent |
| Database/object storage | Business data or durable data | Use access protocols and re-authenticate after restore |

You should not hard-code a path specific to a development machine and expect it to work in a container. Configure the base directory per environment, create directories if appropriate, and verify read/write permissions when the application starts or restores.

## 9. File Handles, Streams, and Memory Mapping

Paths and handles are two different concepts. `Path` describes a location; `InputStream`, `OutputStream`, `FileChannel`, and memory mappings represent open resources or data regions attached to the filesystem.

For example, closing an `InputStream` does not delete the file. Deleting a file does not necessarily close all open handles. On some operating systems, deleting or renaming an open file behaves differently. File locks and memory mappings also depend on the capabilities of the operating system and the checkpoint/restore mechanism.

Before checkpoint:

- Close streams and channels that do not need to be kept.
- Flush data that needs to be durably written.
- Wait for ongoing write operations to complete.
- Release locks if ownership needs to be re-established.
- Check library support for file descriptors, memory mappings, and native handles.

After restore:

- Reopen streams/channels from a verified path.
- Check content and version if the file could have changed externally.
- Re-acquire locks or leases according to the current mechanism.
- Only continue work after the new handle is in a valid state.

You should not assume a `FileChannel` or native handle is still valid just because the Java field holding it was restored. The resource owner needs a strategy to reopen it or use the corresponding CRaC integration.

## 10. Common Mistakes

### Using `getResource().getFile()` with a JAR-packaged application

The resource may be inside an archive or nested JAR, not a separate file. Use `getResourceAsStream()` to read and extract to a temporary file when an API requires a path.

### Using relative paths dependent on the launch directory

The application may run from an IDE, service manager, or container with different working directories. Configure an explicit root directory and resolve paths from that directory.

### Assuming an absolute path guarantees the file exists

An absolute path only removes working directory ambiguity. It does not guarantee the filesystem, mount, content, or access permissions are preserved after restore.

### Using `/tmp` for data that needs to persist long-term

Temporary directories may be cleaned up when the process or container changes. Data that needs recovery must reside in a volume or durable storage.

### Relying on `deleteOnExit()` to delete before checkpoint

A checkpoint is not a normal shutdown. Delete files in the `beforeCheckpoint` callback if that is the appropriate policy, or use a separate observable cleanup mechanism.

### Keeping `Path` in the heap without re-checking after restore

The field may retain the path string while the file has disappeared. Check existence, file type, permissions, and content/version; if regenerable, recreate it.

### Deleting a file while threads are still using it

A consumer may be reading the file while the callback deletes it. Stop accepting new work and drain file users before deleting or closing handles.

## 11. Guide to Choosing a Storage Approach

| Need | Appropriate approach |
|---|---|
| Reading templates or schemas packaged in a JAR | `getResourceAsStream()` |
| Library needs a file path for a resource in a JAR | Extract with `Files.createTempFile()` and manage lifecycle |
| Intermediate data used only within a single operation | Temporary file, delete in `finally` |
| Temporary data used across multiple steps before checkpoint | Resource owns the file; drain, delete/recreate, or verify after restore |
| Files that need to persist across process/container replacement | Persistent volume or durable storage |
| Deployment configuration files | Configured absolute path, re-checked after restore |
| Business data requiring exact recovery | Database, object storage, or workflow store; do not rely solely on heap or `/tmp` |

## 12. Conclusion

Temporary files, absolute paths, and resources in JARs have different lifecycles. Temporary files are suitable for regenerable intermediate data and need to be created/deleted under a clear owner. Absolute paths help avoid depending on the working directory, but do not guarantee the file or mount still exists after restore. Resources packaged in a JAR should be read through the class loader; only extract them to files when the subsequent API actually needs a filesystem path.

In a CRaC application, remember that `Path` state in the heap does not mean file content is packaged in the checkpoint. Before checkpoint, drain file users and close handles that need handling. After restore, verify the filesystem, recreate regenerable temporary files, re-read JAR resources when needed, and only continue processing once the path and content are valid. Data that needs to persist long-term must be stored in a place with durability guarantees.
