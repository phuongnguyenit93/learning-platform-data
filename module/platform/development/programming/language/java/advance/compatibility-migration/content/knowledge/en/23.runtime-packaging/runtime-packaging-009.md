# Paths, File Permissions, Fonts, and Operating System Assumptions

A Java application may run flawlessly inside an IDE on Windows yet fail once packaged into a JAR and deployed to Linux: configuration files cannot be found, temporary directories are not writable, certificates cannot be read, or exported PDF documents lose Vietnamese diacritics. These issues can surface alongside a JDK upgrade, a container image switch, `jlink` usage, or a host migration. However, **not every failure appearing after a Java upgrade stems from Java API changes**; many originate from hidden assumptions about the operating system and packaging.

In **Java Advance Compatibility Migration**, teams must inspect **Java code, bundled application files, filesystems, process permissions, fonts, locales, and runtime images** together. A program compiling cleanly does not prove those conditions exist in production.

This lesson explains how to use `java.nio.file` to handle paths safely, distinguish resources inside a JAR from external files, check permissions per platform, manage fonts in headless/container runs, and build a test matrix to eliminate undeclared OS dependencies.

## 1. Identify the exact layers when an application operates on files

An operation such as "read a template file to generate a report" can pass through multiple layers:

~~~text
Application code
    |
    +-- java.nio.file.Path / Files
    +-- ClassLoader.getResourceAsStream()
    |
Packaging:
    +-- JAR/WAR/resources inside archive
    +-- Configuration files placed outside archive
    +-- Runtime image created by jlink
    |
Operating system:
    +-- Filesystem and mount points
    +-- Paths, case sensitivity, symbolic links
    +-- Ownership, ACL/POSIX permissions
    +-- Charset, locale, timezone, font availability
    |
Deployment:
    +-- Working directory
    +-- Process user/UID
    +-- Container volumes, read-only filesystem
    +-- Java runtime/JDK distribution
~~~

Looking at the diagram above, a `NoSuchFileException` does not necessarily mean "Java does not recognize the file". It may mean the file is being looked up **at a different path**, the resource already resides inside a JAR rather than on a regular filesystem, or the volume has not been mounted. An `AccessDeniedException` usually calls for checking the process account's permissions rather than changing the Java version.

### 1.1. Initial symptom matrix

| Symptom | Cause group to check first | Do not jump to conclusions |
|---|---|---|
| `NoSuchFileException` | Working directory, real path, mounts, filename | New JDK deleted the file |
| `AccessDeniedException` | UID/GID, ACL, owner, directory traversal permission | App must run as root |
| `InvalidPathException` | Path syntax invalid for filesystem provider | Every separator can simply be replaced mechanically |
| Resource readable in IDE but missing when running JAR | Using a path to `src/main/resources` instead of the classpath | Build plugin is always wrong |
| Fonts render as square boxes | Font lacks glyphs, fontconfig, fallback, embedded fonts | UTF-8 charset is definitely wrong |
| UI requires a display when running on server | AWT headless and APIs requiring a display | `java.desktop` was definitely removed |
| Works on Linux, fails to delete file on Windows | Open file handles, differing delete/lock semantics | `Files.delete` is broken in the new JDK |
| Container fails even though local runs fine | File permissions, mounts, minimal images, OS architecture | Just need to increase heap |
| File tests pass on macOS, fail on Linux | Case sensitivity, Unicode normalization, path layout | Source code must not compile |

Always start from the **actual path and actual runtime** recorded in the logs/stack trace, rather than guesswork about the operating system.

## 2. Java Path is a filesystem abstraction, not a raw string

Java NIO.2 provides `Path`, `Files`, and attribute views for file operations. Compared to string concatenation, these APIs represent paths according to the rules of the active filesystem provider.

Recommended usage:

~~~java
import java.nio.file.Path;

Path root = Path.of("/srv/app/data");
Path report = root.resolve("reports").resolve("daily.csv");

System.out.println(report);
~~~

The `Path.of` syntax has existed since Java 11. If a project still must support Java 8, use `Paths.get(...)` accordingly.

Avoid manual concatenation:

~~~java
String report = root + "/" + folder + "\\" + fileName;
~~~

The snippet above mixes separators and assumes `root` and `folder` lack leading/trailing separators. On Windows and Unix, path names are interpreted differently.

### 2.1. Methods to distinguish clearly

| API | Role | Common pitfall |
|---|---|---|
| `Path.of(...)` | Creates a `Path` on the default filesystem | A string valid on one OS may be invalid on another |
| `resolve(other)` | Joins paths according to the `Path` provider rules | If `other` is an absolute path, resolution may ignore the base |
| `normalize()` | Removes redundant `.`, `..` elements syntactically | Does not access the filesystem and does not remove all symlink risks |
| `toAbsolutePath()` | Converts to an absolute path in runtime context | May depend on the working directory |
| `toRealPath()` | Resolves the real path on the filesystem, checking existence | May follow symlinks and fail with permission/I/O errors |
| `relativize(other)` | Computes relative path between two `Path` instances | Usually requires same provider/compatible roots |
| `getFileName()` | Gets the trailing name element | Not a safe filename validation check for uploads |

`Path.normalize()` is syntactic normalization, not a complete security check. In particular, `toRealPath()` and the actual file operation can observe the filesystem at two different points in time.

## 3. Separators, drives, and absolute paths

On Linux and many Unix-like OSes, the path separator is `/`; Windows has drive letters, UNC paths, and its own rules. A string like:

~~~text
C:\services\app\data\report.csv
~~~

makes sense as a Windows path. Passing that string unchanged into a Linux container does not create a "file on drive C". Windows also has root-relative, drive-relative, and UNC forms that code should not attempt to parse with ad-hoc `split` calls.

### 3.1. Configure paths by environment

Instead of hardcoding:

~~~java
Path base = Path.of("C:\\Work\\report-system\\data");
~~~

read the path supplied by deployment:

~~~java
String configured = System.getenv("APP_DATA_DIR");

if (configured == null || configured.isBlank()) {
    throw new IllegalStateException(
            "APP_DATA_DIR must be configured");
}

Path dataDir = Path.of(configured).toAbsolutePath().normalize();
~~~

For Java 8, replace `isBlank()` with an appropriate check. Environment variables are only one way to supply configuration; command-line options or standard framework configuration work too. What matters is **never embedding a developer machine's local path in source code**.

### 3.2. Do not assume the same root across every environment

| Environment | Example sensible path | Source that must be managed |
|---|---|---|
| Windows developer | `C:\work\app\data` | User-local config |
| Linux VM | `/srv/app/data` | Service deployment |
| Container | `/var/lib/app/data` | Image, volume, and mount |
| macOS developer | Subdirectory under user home | User-local config |
| CI | Temporary/checkout directory provided by runner | Pipeline/workspace config |

The paths above are examples only. There is no need to force Windows and Linux to share identical path strings; the goal is **identical configuration semantics**.

## 4. The working directory is not the directory containing the JAR

The following snippet depends on the working directory:

~~~java
Path config = Path.of("config", "application.properties");
String text = java.nio.file.Files.readString(config);
~~~

When launched from the project root, the program may locate `config/application.properties`. If a service manager starts from `/` or a container sets `WORKDIR /app`, the outcome differs.

Observe:

~~~java
System.out.println(
        "user.dir = " + System.getProperty("user.dir"));

System.out.println(
        "working path = " +
        Path.of(".").toAbsolutePath().normalize());
~~~

Do not rely on `java -jar /path/to/app.jar` automatically switching the working directory to the folder holding the JAR. The Java launcher makes no such guarantee.

### 4.1. Durable design patterns

- **Fixed application resources:** package onto the classpath/JAR and read via resource streams.
- **Deployment configuration:** paths/files/secrets supplied by the environment with a clear contract.
- **Writable business data:** persistent volumes or managed storage.
- **Temporary files:** use the supplied temp directory and `Files.createTempFile`.
- **User-facing exports:** output directories selected by the application/workflow, not reliant on CWD.

Do not force one mechanism onto all five categories.

## 5. Resources in a JAR are not files on the external filesystem

A frequent mistake when moving from IDE runs to packaged JARs:

~~~java
Path template =
        Path.of("src/main/resources/templates/invoice.txt");
~~~

This can work inside a project checkout. After `gradle jar` or `mvn package`, resources typically reside **inside the JAR**, no longer at that source tree path.

### 5.1. Use Class.getResourceAsStream

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class TemplateLoader {
    public static String load() throws IOException {
        try (InputStream stream =
                     TemplateLoader.class.getResourceAsStream(
                             "/templates/invoice.txt")) {
            if (stream == null) {
                throw new IOException(
                        "Missing classpath resource: templates/invoice.txt");
            }
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

This example uses `InputStream.readAllBytes()` (Java 9+). When supporting Java 8, read from the stream accordingly.

Note the differences:

- `SomeClass.class.getResourceAsStream("/path")`: a leading `/` denotes an absolute path in the classpath/resource namespace.
- `SomeClass.class.getResourceAsStream("path")`: relative to the class's package.
- `SomeClass.class.getClassLoader().getResourceAsStream("path")`: typically takes a resource name without a leading `/`.

### 5.2. Do not convert every resource URL into a Path

An error-prone pattern:

~~~java
var url = TemplateLoader.class.getResource("/templates/invoice.txt");
Path path = Path.of(url.toURI());
~~~

When running from a classes directory, the URL may use the `file:` scheme and `Path` works. Once the resource lives inside a JAR, the URL typically carries the `jar:` scheme; `Path.of(URI)` is not guaranteed to read inside archives via the default filesystem provider.

For read-only resources, **prefer `InputStream`**. If an external library strictly requires a `Path`, copy the resource to a managed temporary file and delete it when done—or use a ZIP filesystem provider when appropriate while managing the filesystem's lifecycle.

## 6. Configuration files and data outside the JAR

If operators must modify a file without rebuilding the artifact, do not embed it as an immutable resource inside the JAR.

Example:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

Path configPath = Path.of(
        System.getenv("APP_CONFIG_FILE"));

String config = Files.readString(
        configPath, StandardCharsets.UTF_8);
~~~

Production code must handle missing environment variables and file read permissions as shown earlier. For secrets, avoid dumping entire file contents to logs. External files can be managed via ConfigMaps, Secret mounts, service managers, or appropriate infrastructure tooling.

### 6.1. Being able to read a file does not mean it is the right version

A container might mount the wrong environment's config by mistake. Verify:

- Does a file exist at the declared path?
- Do owner/permissions match the service account?
- What config schema/version does the content follow?
- What is the encoding?
- Are any mandatory fields missing?
- Are credentials supplied through a secret store rather than baked into the image?

Never treat `Files.exists(path)` as complete validation.

## 7. Case sensitivity: filename mismatches often appear only on Linux

Filesystems differ in case sensitivity. A project containing:

~~~text
src/main/resources/Templates/Invoice.html
~~~

while code requests:

~~~java
getResourceAsStream("/templates/invoice.html")
~~~

may work under some case-insensitive filesystem configurations yet fail on case-sensitive Linux. Likewise, Git may record case-only renames differently across machines depending on the local filesystem and config.

### 7.1. Prevention

- Use accurate spelling and casing for path names from the start.
- Establish consistent naming conventions for files and resources.
- Run clean checkouts and packaging builds on Linux when production runs on Linux.
- Inspect packaged contents inside the JAR, not just the source tree.
- When renaming files solely by letter case, verify Git actually recorded the rename on your filesystem.

Do not try to "fix" this by scanning directories for case-insensitive matches: doing so can shadow unintended files and produce non-deterministic results.

## 8. Unicode in filenames differs from Unicode in file contents

Using UTF-8 for file contents does not guarantee every filesystem handles filenames identically. A Vietnamese name with diacritics can be represented by different Unicode sequences that look visually similar—such as precomposed characters versus a base character followed by combining marks.

Across OSes and filesystems, normalization, case-folding, and path-encoding rules can vary. Never assume two `String` values that look identical always address the same file.

### 8.1. Designing stable filenames

For business data or uploads:

- Use stable IDs or filenames normalized according to application rules.
- Never use user-supplied display names as unique storage keys.
- Store `originalFilename` separately as metadata if needed for the UI.
- Reject invalid or colliding names after normalization and case folding.
- Test names containing Vietnamese diacritics, emojis, spaces, and combining characters.
- Avoid assuming a single filename length limit across all filesystems.

**Do not** rely on `Normalizer.normalize()` as the sole protection for paths; character normalization and traversal prevention are separate concerns.

## 9. Valid filenames differ across operating systems

Some names or characters permitted on one filesystem are rejected on another. For example, Windows reserves device names (such as `CON`, `NUL`), specific separators, and trailing dot/space rules. Linux primarily forbids `/` and NUL bytes at the filename level, though higher layers and filesystems impose further rules.

An upload service must never take the raw filename and join it directly onto a directory path:

~~~java
Path target = uploadRoot.resolve(userProvidedName);
~~~

Beyond invalid characters, the string may include `../` or an absolute path. Enforce controlled naming rules, validate file types by content/policy, cap lengths, and keep uploaded data outside executable or config directories.

### 9.1. Common approach: system-assigned storage names

~~~java
String storageName = java.util.UUID.randomUUID().toString();
Path destination = uploadRoot.resolve(storageName + ".bin");
~~~

This illustrates avoiding direct use of user-supplied filenames. Production also requires file-type validation, access authorization, quotas, malware scanning where needed, and accompanying metadata.

## 10. Path traversal and symbolic links: syntactic normalization is not enough

When an API accepts a relative path from a client, this snippet blocks basic lexical traversal:

~~~java
Path root = Path.of("/srv/app/uploads")
        .toAbsolutePath()
        .normalize();

Path requested = root.resolve(relativePath)
        .normalize();

if (!requested.startsWith(root)) {
    throw new SecurityException(
            "Path escapes the allowed directory");
}
~~~

However, **this is purely syntactic checking**. If a symbolic link inside `root` points outward, `startsWith(root)` can still pass while the OS accesses an out-of-bounds file. An attacker can swap a symlink or parent directory between the check and the file open—a classic time-of-check/time-of-use (TOCTOU) race.

### 10.1. Layered controls to combine

- Only use system-managed root directories with least-privilege permissions.
- Prevent untrusted users from modifying entries or symlinks inside sensitive directory trees.
- Block absolute paths, traversal segments, and filenames invalid under the business contract.
- When race resistance is required, consider `SecureDirectoryStream` or controlled file-access designs supported by the filesystem provider rather than split check/open steps.
- When using `NOFOLLOW_LINKS`, understand exactly which operations honor it and which parent path components can still follow links.
- Enforce OS/container permissions to limit blast radius if application checks are bypassed.

`Files.isSymbolicLink(path)` or `toRealPath()` can aid investigation, but a one-off check does not eliminate races. For security-sensitive file handling, storage layout and permissions matter more than stacking another check.

## 11. Files.exists, isReadable, and isWritable do not guarantee the next operation succeeds

Java provides:

~~~java
Files.exists(path);
Files.isReadable(path);
Files.isWritable(path);
Files.isDirectory(path);
~~~

They are useful for pre-flight checks or clearer error messages. However, filesystem state can change immediately afterward; POSIX/ACL permissions, mounts, network filesystems, or security contexts can also diverge from what pre-checks report.

The reliable pattern is to **perform the actual operation and handle `IOException`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public static String readConfig(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}
~~~

To differentiate failures, catch specific exceptions such as `NoSuchFileException`, `AccessDeniedException`, and other `FileSystemException` subclasses; when logging, avoid exposing secrets or sensitive paths beyond permitted scopes.

## 12. File permissions: POSIX permissions, Windows ACLs, and filesystem reality

File access permissions **are not represented identically across operating systems**.

| System/model | Common mechanism | What to keep in mind |
|---|---|---|
| Linux/Unix POSIX | Owner, group, other; read/write/execute | Directories require traverse (`x`) permission to reach files inside |
| Windows NTFS | Access Control Lists (ACLs) and identities | Cannot be modeled completely via `chmod` |
| Linux container | Process UID/GID, image files, mounted volumes | Container process user may differ from file owner |
| Network filesystem | Permissions, ACLs, server-side policies, mount options | Local checks may differ from server enforcement |
| Read-only mount | Read-only filesystem or volume | Writes still fail even when mode bits appear writable |
| Custom runtime image | Image and launcher file permissions | May lack shells/utilities for debugging |

Never infer from `Files.isWritable(path) == true` that writing will definitely succeed. Moreover, write failures can stem from quotas, full disks, file locks, or read-only mounts rather than ACLs alone.

### 12.1. Directory execute/traverse permission

In POSIX, the `x` bit on a **directory** permits traversing paths through it when paired with appropriate permissions; it does not mean executing a program file.

For instance, even if a file is `rw-------`, lacking traverse permission on any parent directory still causes access denial. Always inspect ownership and modes on **every directory along the path**, not solely the target file.

## 13. Java NIO file attribute views

Java offers filesystem-conditional attribute views:

- `BasicFileAttributeView`: basic metadata.
- `PosixFileAttributeView`: owner/group/POSIX permission bits on compatible filesystems.
- `AclFileAttributeView`: access control lists when supported by the provider.
- `DosFileAttributeView`: attributes such as read-only/hidden on applicable filesystems.
- `FileOwnerAttributeView`: owner metadata per provider capability.

The right pattern is to check capability support and handle `UnsupportedOperationException` when an attribute view is unavailable.

### 13.1. Reading POSIX permissions where supported

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Set;

public static void showPermissions(Path file) throws Exception {
    Set<PosixFilePermission> permissions =
            Files.getPosixFilePermissions(file);

    System.out.println(permissions);
}
~~~

This works on POSIX filesystems, but must not be used unconditionally as the sole portable approach: Windows or other providers may not support the POSIX view.

### 13.2. Feature detection

~~~java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;

FileStore store = Files.getFileStore(path);
boolean posix =
        store.supportsFileAttributeView(
                PosixFileAttributeView.class);

System.out.println("POSIX view supported: " + posix);
~~~

Support depends on the **filesystem/provider at that path**, not just the OS name. An application running on Linux can still touch network mounts or custom providers whose semantics differ from the root filesystem.

## 14. Create files with least privilege from the start

For secrets or sensitive data, never create a file with broad permissions and tighten them later, as a window exists where the file can be exposed unexpectedly.

Where the filesystem supports POSIX, supply file attributes at creation time:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.EnumSet;
import java.util.Set;

Path secretFile = Path.of("/secure/app/token.data");

Set<PosixFilePermission> permissions = EnumSet.of(
        PosixFilePermission.OWNER_READ,
        PosixFilePermission.OWNER_WRITE);

Files.createFile(
        secretFile,
        PosixFilePermissions.asFileAttribute(permissions));
~~~

This snippet assumes the parent directory already exists, the process holds creation privileges, and the filesystem supports POSIX attributes. On other platforms, apply the appropriate permission/ACL mechanism; never fall back automatically to world-readable permissions.

Production file creation must also account for name collisions, existing files, symbolic links, and directory permissions. Do not treat this snippet as a full upload API.

### 14.1. Why is chmod 777 a dangerous fix?

Running `chmod -R 777 /srv/app` may let the program write, yet it grants read/write/execute permissions across many accounts—including on secrets or artifacts—and masks misconfigured UID/GID ownership.

The proper remedy is identifying the **process identity**, data owner/group, mount policy, and minimal required permissions. If write access is missing on an output folder, grant exact permissions to the approved service account or group rather than opening up the entire filesystem.

## 15. UID/GID in containers and mounted volumes

Containers typically run under the user/UID configured in the image or via Kubernetes `securityContext`. A mounted volume can carry an owner different from the process user.

Example:

~~~text
Image filesystem:
  /app/app.jar           readable by app process
  /app/templates/        read-only

Persistent volume:
  /var/lib/app/data      owned by UID 1000
Running process:
  UID 2000
~~~

If process UID 2000 lacks required permissions, creating files on the volume can throw `AccessDeniedException`. On a dev machine running under another user or root, the failure never appears.

### 15.1. Do not solve this by running as root by default

Check:

1. Which `USER` does the image declare?
2. Does the pod/service override user/group settings?
3. Who owns the persistent volume and subdirectories?
4. Are appropriate group permissions or ACLs present?
5. Is the volume mounted read-only?
6. Does cluster security policy restrict `chown` or ownership changes?
7. Which directories does the application genuinely need to write to?

A durable solution is provisioning the volume with the right owner/group/permissions or using mechanisms like `fsGroup` where supported by the cluster/driver, rather than elevating privileges for the whole process.

## 16. Read and write files using explicit UTF-8

Charset differences frequently trigger bugs when moving from Windows to Linux or changing JDKs. Java 18 made UTF-8 the default charset under **JEP 400** across many standard APIs, whereas older JDKs/environments could rely on a platform-dependent default charset. Never assume **all historical data** is UTF-8 simply because newer JDKs default to it.

### 16.1. Specify charset explicitly on reads and writes

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("reports", "status.txt");

Files.writeString(
        file,
        "Báo cáo hoàn thành",
        StandardCharsets.UTF_8);

String content = Files.readString(
        file,
        StandardCharsets.UTF_8);
~~~

`Files.writeString` and `Files.readString` date from Java 11. For Java 8 compatibility, use `Files.newBufferedReader`, `newBufferedWriter`, or streams with an explicit charset.

### 16.2. Do not confuse content charset with font glyphs

If a Java string already holds proper Vietnamese Unicode characters yet an exported PDF shows boxes, the culprit is usually **missing font glyphs** or missing fonts in the runtime image—not UTF-8.

Conversely, if reading input immediately yields replacement characters (�), inspect the input encoding first; installing more fonts will not repair an incorrectly decoded string.

## 17. Newlines and file formats across Windows and Linux

Windows typically uses CRLF (`\r\n`), while Unix-like OSes use LF (`\n`). Java provides:

~~~java
String localNewline = System.lineSeparator();
~~~

However, newline selection should follow the **file contract**, not blindly track the host OS:

- Config files or protocol formats requiring LF: write `\n` explicitly.
- Local OS display text: `System.lineSeparator()` may fit.
- CSV/JSON/XML exports with format rules: use proper serializers/specs rather than manual concatenation.
- Golden test files: normalize newlines intentionally only if the contract allows it, without hiding meaningful diffs.

On Windows, Git can convert line endings based on local config; a shell script committed with CRLF may fail to execute on Linux. That is a packaging/source-control issue, not a JVM API bug.

## 18. File locks, open handles, and delete/rename behavior

An application may finish reading data yet keep an `InputStream`, `FileChannel`, or memory mapping open. OS differences emerge during deletion or renaming:

- Many Unix-like filesystems allow unlinking an open file; existing handles continue accessing its content.
- On Windows, a file held open under incompatible sharing modes often cannot be deleted or renamed.
- File locking and atomic moves carry differing guarantees across local vs. network filesystems.

### 18.1. Close resources explicitly

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (InputStream input = Files.newInputStream(path)) {
    // Process file content within the resource lifetime.
}
~~~

Never rely on the garbage collector to "close files promptly". In Java NIO, try-with-resources is the standard construct for streams and channels.

### 18.2. Atomic writes apply only under supported conditions

One pattern for writing config files writes to a temp file in the same directory and renames it:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path target = Path.of("/srv/app/config/result.txt");
Path parent = target.getParent();

Path tmp = Files.createTempFile(
        parent, "result-", ".tmp");

try {
    Files.writeString(tmp, "new content",
            StandardCharsets.UTF_8);

    Files.move(
            tmp,
            target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Decide explicitly whether a non-atomic fallback is acceptable.
    throw unsupported;
} finally {
    Files.deleteIfExists(tmp);
}
~~~

This example targets filesystems supporting atomic moves with an existing parent directory. Combining `ATOMIC_MOVE` with replacement options, behavior when targets already exist, and true atomicity all depend on the provider. Critical files also need proper fsync/durability and rollback handling; atomic rename alone does not guarantee data has been flushed durably to storage across power loss.

### 18.3. Do not treat all filesystems as identical

Network filesystems, object-store providers, volume mounts, overlay filesystems, and local disks can differ in locking, move, and caching semantics. Test real operations on the storage class used in production.

## 19. Temporary directories: /tmp is not standard across all OSes

A common bug:

~~~java
Path temp = Path.of("/tmp/output.pdf");
~~~

`/tmp` does not map the same way on Windows, and containers may mount temp locations read-only, enforce tight quotas, or run cleanup policies.

Java offers:

~~~java
Path tempFile = Files.createTempFile(
        "report-", ".tmp");

try {
    // Write and process the temporary file.
} finally {
    Files.deleteIfExists(tempFile);
}
~~~

With Java NIO, temporary files are placed in the JVM's temp directory with collision-resistant names. Keep in mind:

- `java.io.tmpdir` can differ across JDKs, OSes, and containers.
- Temp files may hold secrets or customer data and require proper permissions.
- Test environments may designate isolated temp directories.
- Never assume temp files survive restarts.
- Enforce size caps and cleanup policies.
- When third-party libraries require file paths, manage those files' full lifecycles.

Under heavy data volumes, temporary mounts can run out of space and fail writes even with ample heap.

## 20. Fonts are more than family names in Java

Applications generating images, barcodes, PDFs, reports, or server-rendered HTML may use `java.awt.Font`, `Graphics2D`, PDF libraries, or external renderers. Calling `new Font("Some Font", ...)` **does not guarantee a physical font of that name exists at runtime**.

Java defines **logical fonts** such as `Serif`, `SansSerif`, `Monospaced`, `Dialog`, and `DialogInput`, mapped to physical fonts depending on the JVM, OS, and font config. Physical font names like `Arial` or `Times New Roman` may exist on Windows yet be absent in minimal Linux containers.

### 20.1. Font migration symptoms

| Symptom | Cause to check |
|---|---|
| Vietnamese text loses diacritics or shows boxes | Font lacks glyphs, improper fallback |
| PDF/PNG line lengths shift | Different font substitution and metrics |
| Report table rows clip or wrap | Line height/kerning/glyph metrics changed |
| Configured font selects a different look | Physical font missing, logical font fallback |
| `Fontconfig`/font manager errors on Linux | Missing fontconfig or proper font data |
| Application demands X11/display | GUI API called in a headless environment |
| Local render works, container render breaks | Differing font packages, runtime image, locale, native libs |

Font and encoding issues both impact output readability, yet require separate diagnosis. UTF-8 cannot conjure glyphs absent from a physical font.

## 21. Inspecting which fonts are actually available

When `java.desktop` is present in the runtime image, `GraphicsEnvironment` can inspect available families:

~~~java
import java.awt.GraphicsEnvironment;
import java.util.Arrays;

public final class FontInventory {
    public static void main(String[] args) {
        GraphicsEnvironment environment =
                GraphicsEnvironment.getLocalGraphicsEnvironment();

        System.out.println(
                "Headless: " +
                GraphicsEnvironment.isHeadless());

        String[] fontFamilies =
                environment.getAvailableFontFamilyNames();

        Arrays.stream(fontFamilies)
                .limit(30)
                .forEach(System.out::println);
    }
}
~~~

This example prints only the first 30 font families, not a full inventory. Nor does `getAvailableFontFamilyNames()` prove a font covers every Vietnamese glyph. Always test concrete sample text against the actual font and rendering engine.

### 21.1. Checking glyphs a font can display

~~~java
import java.awt.Font;

Font font = new Font("SansSerif", Font.PLAIN, 14);

String sample = "Tiếng Việt: Đường dẫn và quyền tệp";

int firstMissing = font.canDisplayUpTo(sample);

if (firstMissing >= 0) {
    System.out.println(
            "Font cannot display character index " +
            firstMissing);
}
~~~

This is a helpful font-level check, though it does not replace snapshot/rendering tests. Final appearance can still vary due to fallbacks, text shaping, PDF library behavior, and font embedding.

If `Font.canDisplayUpTo` returns -1, that font reports support for displaying the string under this check; it is not a promise that every downstream renderer produces identical layout.

## 22. AWT headless mode and the java.desktop module

Servers generally lack GUI displays. Java provides headless mode for environments without keyboard, mouse, or display hardware.

Check it via:

~~~java
import java.awt.GraphicsEnvironment;

boolean headless =
        GraphicsEnvironment.isHeadless();

System.out.println("Headless: " + headless);
~~~

Configure the JVM when appropriate:

~~~bash
java -Djava.awt.headless=true -jar application.jar
~~~

However:

- **Headless** does not mean **omitting the `java.desktop` module**.
- Several image/font rendering APIs work cleanly in headless mode.
- APIs genuinely needing windows or displays throw `HeadlessException`.
- Enabling headless mode does not install fonts, fontconfig, or native libraries.
- Specific image/report generators have their own runtime and font-rendering prerequisites.

### 22.1. jlink can strip java.desktop

When building a custom runtime image via `jlink`, teams may inadvertently drop modules required by `java.awt.Font` or `javax.imageio`.

Illustrative example:

~~~bash
jlink \
  --add-modules java.base,java.desktop \
  --output runtime-with-desktop
~~~

For real applications, analyze all module dependencies with `jdeps` or build tools and declare required modules explicitly. The command above does not represent a complete runtime image for arbitrary Java apps.

If `java.desktop` is missing from the runtime image, adding fonts to the container **will not restore missing Java classes**. Conversely, having `java.desktop` without physical fonts can still break Unicode rendering.

## 23. Bundling fonts with the application for consistent output

One strategy for report-generating apps is bundling an **appropriately licensed** font inside application resources, loading it from a stream, and rendering explicitly with it. This reduces reliance on OS-installed fonts.

Example:

~~~java
import java.awt.Font;
import java.awt.FontFormatException;
import java.io.IOException;
import java.io.InputStream;

public final class ReportFonts {
    public static Font loadBodyFont()
            throws IOException, FontFormatException {

        try (InputStream stream =
                     ReportFonts.class.getResourceAsStream(
                             "/fonts/report-body.ttf")) {

            if (stream == null) {
                throw new IOException(
                        "Missing report font resource");
            }

            return Font.createFont(
                    Font.TRUETYPE_FONT,
                    stream).deriveFont(12f);
        }
    }
}
~~~

This snippet assumes `report-body.ttf` is a valid font licensed for redistribution with the app. Never bundle or distribute commercial fonts without license authorization.

### 23.1. Bundling a font does not guarantee proper PDF embedding

Many PDF or reporting engines maintain separate font registries. `Font.createFont` creates an object for Java2D; PDF libraries often require explicit **register/embed font** calls via their own APIs.

For Vietnamese-language PDFs, check:

- Does the font include all necessary Unicode glyphs?
- Is the font embedded properly into the PDF (if required by product specs)?
- Does font substitution happen on different PDF viewers?
- Are there glyph shaping or combining-mark issues?
- Can users copy and search Unicode text accurately?
- Does the license allow PDF embedding and distribution?

Never verify only "renders fine in my IDE" and assume PDFs will look identical on a Linux server.

### 23.2. Fontconfig on Linux

Some Java runtimes depend on OS font infrastructure (such as fontconfig and installed font packages). Minimal container images often lack them. If your renderer relies on OS fonts, ensure the image includes required packages/fonts with pinned versions or digests for reproducibility.

On Linux environments equipped with font utilities, you can inspect:

~~~bash
fc-list
fc-match sans-serif
~~~

These commands are **not Java APIs** and may be absent in minimal containers. Their absence alone does not prove the JVM lacks font support; examine the actual runtime setup and rendering library.

## 24. Packaging: JAR/WAR, resource directories, and custom runtime images

A deployable artifact layout may include several parts:

~~~text
app/
  app.jar                    # application bytecode
  lib/                       # external dependencies, if packaging requires it
  config/                    # deployment configuration files (may be mounted)
  fonts/                     # physical font assets, if needed and licensed
  native/                    # shared libraries per OS/architecture
  data/                      # persistent volume, not necessarily inside image
  logs/                      # writable output, if design uses file logs
~~~

Not every application needs this exact structure. In executable fat JARs, resources may live inside the archive; in WAR deployments, the servlet container manages classloaders and resources; with `jlink`, JVM modules may be trimmed down.

### 24.1. File matrix: embed or mount?

| Artifact/file | Embed in artifact | Mount/supply from environment | Notes |
|---|---|---|---|
| Immutable templates | Usually suitable | Optional if customization needed | Read via classpath stream when embedded |
| Per-environment config | Usually no | Suitable | Validate schema and access permissions |
| Secrets/private keys | Avoid embedding | Secret mechanism | Never log or commit values |
| Redistributable fonts | Optional | Optional via OS/image | Verify Unicode coverage, license, version |
| User uploads | No | Persistent storage | Enforce quotas, ACLs, traversal checks |
| Logs/runtime temp | No | Writable volume/stdout/temp | Apply rotation and caps |
| Native libraries | Possible per OS-specific artifact | Possible inside image | Verify OS/architecture/ABI compatibility |

Whether files are embedded or mounted, their paths and lifecycles must stay explicit. Switching from an exploded WAR to an executable JAR can break code expecting physical filesystem paths for resources.

## 25. Native libraries and OS/architecture assumptions

Beyond paths and fonts, apps may load native libraries or Java agents requiring platform-specific binaries:

- Linux: typically `.so`.
- macOS: typically `.dylib`.
- Windows: typically `.dll`.

Loading a `libcodec.so` built for x64 on ARM64, or linked against an incompatible libc version, can trigger `UnsatisfiedLinkError` or native crashes.

Do not attempt to fix this by swapping `/` with `\` or tweaking `java.library.path` if the binary itself is incompatible. Check:

1. OS and CPU architecture.
2. ABI and libc/native dependencies.
3. Read/execute permissions on both the binary and parent directories.
4. How the library is packaged or unpacked.
5. Target JDK native-access restrictions where applicable.
6. Error logs, vendor support matrices, and artifact checksums.

Path portability and native binary portability are two independent verification layers.

## 26. OS boundaries in ProcessBuilder and external tools

Some applications invoke `wkhtmltopdf`, `ffmpeg`, `git`, or shell scripts. Executable paths, environment variables, quoting, and shell syntax differ between Windows and Linux.

Use `ProcessBuilder` with explicit argument lists rather than concatenating untrusted inputs into a single shell command string:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

Path executable = Path.of(
        System.getenv("REPORT_RENDERER"));

ProcessBuilder builder = new ProcessBuilder(
        List.of(
                executable.toString(),
                "--output",
                "/srv/app/out/report.pdf"));

Process process = builder.start();
int exitCode;

try {
    exitCode = process.waitFor();
} catch (InterruptedException interrupted) {
    process.destroyForcibly();
    Thread.currentThread().interrupt();
    throw interrupted;
}

if (exitCode != 0) {
    throw new IOException(
            "Report renderer failed: " + exitCode);
}
~~~

This snippet illustrates `ProcessBuilder` usage only; it omits stdout/stderr draining, timeouts, executable validation, missing env checks, and output management. Production code must prevent stream-buffer deadlocks, enforce timeouts, and never pass raw user input unsafely to shells.

Crucially, **never assume Linux commands exist on Windows** or vice versa. If an external binary is a runtime dependency, declare, install, and verify it for every target environment.

## 27. Inspecting the environment from Java without OS-specific shells

A small diagnostic probe can help investigate deployed environments:

~~~java
import java.awt.GraphicsEnvironment;
import java.nio.charset.Charset;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.util.Locale;

public final class EnvironmentProbe {
    public static void main(String[] args) {
        System.out.println("Java version: " +
                System.getProperty("java.version"));
        System.out.println("Java vendor: " +
                System.getProperty("java.vendor"));
        System.out.println("OS: " +
                System.getProperty("os.name"));
        System.out.println("OS arch: " +
                System.getProperty("os.arch"));
        System.out.println("File separator: " +
                FileSystems.getDefault().getSeparator());
        System.out.println("Working directory: " +
                Path.of(".").toAbsolutePath().normalize());
        System.out.println("Temp directory: " +
                System.getProperty("java.io.tmpdir"));
        System.out.println("Default charset: " +
                Charset.defaultCharset());
        System.out.println("Default locale: " +
                Locale.getDefault());
        System.out.println("Headless: " +
                GraphicsEnvironment.isHeadless());
    }
}
~~~

This probe uses `java.desktop` for the headless check. If your runtime image omits that module, remove the `GraphicsEnvironment` call or supply the module if required by your app.

In production, never expose full host properties or internal paths on public endpoints. Restrict diagnostics behind authorization with proper log redaction.

### 27.1. Why record both JDK and OS?

Running the same Java 21 release across two platforms can still differ in:

- File path syntax and case sensitivity.
- Font availability and substitution.
- Native library availability.
- Permission models and file sharing.
- Local charset/timezone/locale settings.
- Container mounts/cgroups and user identities.
- Filesystem provider support for attribute views.

That is why a bug reported "after upgrading Java" may actually stem from shifting deployment from Windows hosts to Linux containers in the same release window.

## 28. Writing unit and integration tests for these assumptions

Do not stop at testing `Path.of("a", "b")`. Tests should reflect the actual contracts at every layer likely to vary.

### 28.1. Unit tests for path handling

- Relative vs. absolute paths.
- Invalid filenames and special characters.
- Unicode, spaces, and Vietnamese diacritics.
- `.`, `..`, and traversal attempts.
- Case-insensitive matching when required by business rules.
- Missing files and invalid inputs.
- Correct vs. missing URLs/resource names inside JARs.

JUnit 5 example using a temporary directory:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FileStoreTest {
    @TempDir
    Path tempDir;

    @Test
    void readsUtf8Text() throws Exception {
        Path file = tempDir.resolve("bao-cao.txt");
        Files.writeString(
                file,
                "Đường dẫn hợp lệ",
                StandardCharsets.UTF_8);

        assertEquals(
                "Đường dẫn hợp lệ",
                Files.readString(
                        file, StandardCharsets.UTF_8));
    }
}
~~~

This snippet assumes JUnit Jupiter dependencies and Java 11+. Using `@TempDir` beats hardcoding `/tmp/my-test`, though CI filesystem behavior and permissions still matter.

### 28.2. Integration tests for file permissions

Include cases covering:

- Process holds read access without write access.
- Process lacks traverse/access rights on parent directories.
- Read-only output directories.
- Missing volume mounts.
- Pre-existing or locked files.
- Quota/disk-full constraints in test environments where needed.
- Proper packaging/mounting of native binaries and font assets.

Never run destructive permission or disk-filling tests against production. Use isolated environments with controlled test quotas.

### 28.3. Snapshot/golden tests for fonts

To catch font differences after image or JDK updates, verify:

- Strings with Vietnamese diacritics: `Đường dẫn, quyền tệp, ảnh hưởng môi trường`.
- Combining marks and non-ASCII characters.
- Bold/italic styles, numerals, and punctuation.
- Varying page sizes or image dimensions.
- Behavior when physical fonts are unavailable.
- Text copy/search accuracy in generated PDFs if required by contract.

Rendered images can vary subtly across anti-aliasing engines, renderers, or JDKs, so set realistic comparison tolerances and pin fonts/runtimes when pixel-identical output is required.

## 29. Environment-based test matrix

A suggested matrix for apps developed locally yet deployed in Linux containers:

| Environment | Paths/resources | Permissions | Fonts/headless | Packaging/runtime |
|---|---|---|---|---|
| Windows developer | Drive paths, case, IDE resources | ACLs, file locks | Local physical fonts | IDE/CLI JDK |
| Linux CI | Case-sensitive paths, clean JAR | Non-root user, temp dir | Font availability/Unicode | Clean build + test |
| Linux container staging | Volume mounts, absolute config paths | UID/GID, read-only rootfs | fontconfig, headless, render | Same image lineage as production |
| macOS developer (if supported) | Unicode normalization, path casing | POSIX ACLs/provider | macOS fonts | Local toolchain |
| Production | Actual persistent storage | Real service account | Approved font set | Exact JDK/image digest |

Do not assume every project must support all three OSes equally. If production runs exclusively on Linux, the test matrix should still cover Linux CI and containers while documenting gaps between dev laptops and supported targets.

### 29.1. Mandatory checks on the packaged JAR

Execute the **actual packaged artifact**, not solely inside the IDE:

- Can resource streams locate files packaged inside the JAR?
- Are external files outside the JAR loaded from the exact configured path?
- Do output directories exist with proper write permissions?
- Are report fonts loaded and rendered properly inside headless images?
- Does the runtime image include `java.desktop` if needed?
- Are native library paths valid?
- Are logs, dumps, and temp files written inside permitted locations?
- Are file handles closed before delete or move calls?

Many bugs surface only once resources are archived or once processes run unprivileged.

## 30. Migration plan from Windows/VM to Linux containers

This scenario frequently coincides with upgrading Java 8 to 17/21 while modernizing deployments.

### Step 1: Inventory OS dependencies

Locate hardcoded path strings, shell commands, font names, file encodings, temp directories, native binaries, registry/env references, and assumptions around locks or case sensitivity.

### Step 2: Classify file categories

Separate artifact-bundled resources, external configs, secrets, persistent data, temp files, logs, and native/font assets. Give each category clear ownership and deployment rules.

### Step 3: Standardize Java Path/Files

Replace manual string joining with `Path.resolve`; adopt `Files` and streams properly. Handle `IOException` explicitly and drop working-directory assumptions.

### Step 4: Fix resource loading

Read immutable templates and classpath resources via `getResourceAsStream`. If external APIs require physical paths, manage temporary copies carefully; never access `src/main/resources` at runtime.

### Step 5: Design permissions prior to deployment

Specify user/UID/GID, mounts, ownership, ACL/mode settings, writable directories, and temp storage. Never default to root or `chmod 777`.

### Step 6: Package fonts and native assets deliberately

Choose appropriately licensed fonts with full glyph support; bundle them or pin OS font packages. Verify OS-native libraries and `java.desktop` if required.

### Step 7: Set explicit charset, newline, locale, and timezone

Use UTF-8 wherever UTF-8 contracts apply; match newlines to file specs; never infer business dates/times from default timezones when explicit zones are required.

### Step 8: Test real artifacts in real images

Run under an unprivileged service account with production-like mounts, read-only filesystems, and staging resources.

### Step 9: Run negative tests

Exercise missing configs, read-only folders, invalid filenames, missing fonts, symlinks/traversal attempts, and bad resource paths.

### Step 10: Capture evidence and roll out

Archive OS/JDK/build/image digests, permission models, mounts, font packages, rendered artifacts, and logs. Deploy only with documented residual risks and verified rollback paths.

## 31. Case study A: resource resides in JAR while code reads from disk

**Symptom:** `src/main/resources/templates/invoice.html` loads fine in the IDE. After packaging an executable JAR and running in a container, logs report `NoSuchFileException`.

**Cause:** Code targets a source-checkout filesystem path rather than a classpath resource.

**Resolution:** Move immutable templates to `getResourceAsStream("/templates/invoice.html")`; verify the template exists inside the packaged JAR; if a renderer requires a physical file, copy the stream to a managed temporary file with proper cleanup.

**Evidence:** Automated check reading the resource directly from the packaged artifact, not only from IDE tests.

## 32. Case study B: file writes fail when container runs non-root

**Symptom:** `Files.writeString` succeeds locally, yet containers throw `AccessDeniedException` on `/var/lib/app/data/report.txt`.

**Possible causes:** Volume ownership mismatches the process UID, a parent folder lacks traverse permission, the mount is read-only, or filesystem policy blocks access.

**Resolution:** Inspect runtime UID/GID, directory owner/mode/ACLs, and mount flags; provision writable paths with proper permissions while preserving least privilege.

**Avoid:** Running containers as root or executing `chmod -R 777` blindly; both weaken security boundaries without addressing the underlying design gap.

**Evidence:** Integration test creating, reading, and deleting files on the mounted volume under the actual production identity.

## 33. Case study C: PDF reports lose Vietnamese diacritics

**Symptom:** With identical input `"Đường dẫn và quyền tệp"`, PDFs render fine on Windows yet drop diacritics inside a minimal Linux container image.

**Possible causes:** Requested fonts do not exist in the container, fallback substitutes another typeface, glyphs are missing, fontconfig/`java.desktop` setup is incomplete, or upstream decoding corrupted the text beforehand.

**Resolution:**

1. Confirm the Java string holds valid Unicode prior to rendering.
2. Check `java.desktop` presence and headless mode.
3. Verify resolved physical fonts and glyph support.
4. Bundle properly licensed fonts or install required OS font packages.
5. Configure PDF library font registration, embedding, and fallback APIs.
6. Run render tests inside the actual container image, checking both visuals and text copy/search behavior per contract.

**Evidence:** Screenshots or golden PDFs containing Vietnamese diacritics paired with recorded JDK and image versions.

## 34. Case study D: files fail to delete on Windows

**Symptom:** Tests create and delete files cleanly on Linux CI yet hit access/locking errors on Windows.

**Possible causes:** An unclosed `InputStream`, `FileChannel`, or lazy library retains an open file handle; OS file-sharing and deletion rules differ.

**Resolution:** Enforce try-with-resources, verify streams and lazy parsers/renderers close handles cleanly, and isolate external processes holding files; adjust OS-specific delete/move contracts and tests if semantics genuinely differ.

**Avoid:** Unbounded retry loops masking handle leaks. Bounded retries with backoff, timeouts, and telemetry fit only proven transient locks.

## 35. Common misconceptions

**"Java runs everywhere, so every path is portable."** Java offers cross-platform APIs, yet filesystem semantics, permissions, and packaging still differ.

**"`/` and `\` are freely interchangeable in every path."** No. Use `Path` and filesystem providers rather than ad-hoc string parsing.

**"`java -jar` sets the working directory to the JAR's folder."** No such guarantee exists.

**"Files under `src/main/resources` always exist on disk in production."** No. They typically live inside the packaged JAR/WAR.

**"`Path.normalize()` blocks all traversal attacks."** No. Symbolic links, filesystem races, and authorization require additional safeguards.

**"`Files.exists()` and `isWritable()` guarantee subsequent operations succeed."** No. Filesystem state can change concurrently and depends on many factors.

**"Linux permissions work like Windows ACLs."** No. Inspect provider-supported attribute views; avoid calling POSIX APIs unconditionally.

**"Switching to root or running chmod 777 is a fast, safe permission fix."** No. It widens exposure and hides broken ownership or mount configs.

**"Valid UTF-8 text guarantees fonts render Vietnamese cleanly."** No. Fonts need matching glyphs and renderers must select/embed them properly.

**"Enabling headless eliminates all font issues."** No. Headless mode neither installs fonts nor replaces `java.desktop`.

**"Having `java.desktop` guarantees Arial or Times New Roman is present."** No. Installed physical fonts depend on the OS, image, and config.

**"The GC will close file handles in time."** Never rely on GC for resource cleanup; use try-with-resources.

**"`ATOMIC_MOVE` behaves identically on every filesystem."** No. Support and semantics depend on the provider, mount, and operation.

**"Tests passing in the IDE prove packaging is sound."** No. Validate the packaged artifact on the target runtime.

**"Upgrading the JDK broke fonts or permissions, so we should downgrade."** First separate Java runtime changes from differences in container images, OSes, configs, and process permissions.

## 36. Pre-deployment checklist

- [ ] Recorded source/target JDK feature/update/vendor, OS/architecture, and container images.
- [ ] Inventoried bundled resources, external configs, secrets, persistent data, temp files, logs, and native assets.
- [ ] Removed hardcoded developer-specific absolute paths.
- [ ] Used `Path.resolve` and appropriate NIO APIs without manual separator concatenation.
- [ ] Verified working directory behavior and any remaining relative paths.
- [ ] Read classpath resources via streams when packaged inside JAR/WAR artifacts.
- [ ] Verified clean builds and execution directly from packaged artifacts.
- [ ] Checked case sensitivity, Unicode normalization, and filename restrictions on the target OS.
- [ ] Prevented path traversal and addressed symlink/TOCTOU risks for untrusted input.
- [ ] Distinguished POSIX permissions, ACLs, ownership/groups, and filesystem providers.
- [ ] Verified service/container UID/GID and volume access permissions.
- [ ] Applied least-privilege permissions instead of running as root or using `chmod 777`.
- [ ] Tested read/write/delete/move workflows and verified handle closure.
- [ ] Handled atomic writes according to filesystem capability and durability requirements.
- [ ] Used dedicated temp directories with explicit quotas and cleanup.
- [ ] Specified explicit charsets and newline formats matching data contracts.
- [ ] Verified actual fonts, Unicode glyphs, font fallbacks, and licensing.
- [ ] Checked `java.desktop`, headless mode, and custom runtime images.
- [ ] Verified OS/architecture compatibility for native libraries and external tools.
- [ ] Executed unit, integration, and negative tests under the actual service identity.
- [ ] Tested against container images and volume setups matching production.
- [ ] Archived artifact digests, config paths, rendered samples, logs, and test scope.
- [ ] Established owners, rollout steps, and rollback/roll-forward plans.

## 37. Reference resources

When implementing on a real project, consult API docs and JDK manuals matching your target release:

- **Java NIO `Path` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html
- **Java NIO `Files` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- **`PosixFilePermissions`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- **`GraphicsEnvironment`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/GraphicsEnvironment.html
- **`Font` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/Font.html
- **JEP 400 — UTF-8 by Default (JDK 18):** https://openjdk.org/jeps/400
- **Java Platform Module System:** https://openjdk.org/projects/jigsaw/spec/

These references clarify API semantics; file permissions, font availability, and filesystem behavior must still be verified against **the actual OS, container, and runtime deployed**. When targeting a JDK other than Java 21, inspect docs for that specific release to verify option and API support.

## Conclusion

**Paths, file permissions, fonts, and OS assumptions are part of the operational contract during a Java upgrade.** An application can be completely source-compatible and binary-compatible with a newer JDK yet still fail inside a JAR, WAR, `jlink` image, or container because the working directory shifted, resources are no longer physical files, the process lacks permissions, the filesystem behaves differently, or the image lacks fonts.

A durable migration classifies every file type, uses `Path` and `Files` under clear contracts, reads JAR resources via streams, configures permissions for real users and filesystems, bundles fonts or `java.desktop` when required, handles Unicode/charsets/newlines deliberately, and **tests the packaged artifact under production-like runtime and process identities**. Once every OS assumption is explicit and backed by evidence, upgrading a JDK no longer relies on conditions that merely happened to work on a developer machine.
