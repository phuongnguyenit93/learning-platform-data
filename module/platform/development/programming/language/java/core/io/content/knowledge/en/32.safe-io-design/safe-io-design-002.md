# Path Traversal and Allowed Directory Boundaries in Java IO/NIO.2

An application often lets users download images, view documents, extract files, or read logs via a parameter such as `file=reports/2026.txt`. If the application takes the user-submitted string and joins it directly into a system path, the user may cause the program to access data located **outside the directory they are permitted to use**. This vulnerability is called **path traversal** (directory traversal).

The goal of safe design is to turn “only read/write inside the authorized directory” into an **invariant checked before the IO operation**. In Java, this requires understanding the differences between string representations, syntactic normalization, real paths on the filesystem, symbolic links, and permissions at file-open time.

## 1. What Is Path Traversal?

Suppose a service allows downloading documents under `/srv/app/uploads/alice/` and accepts a relative name:

```text
GET /download?name=invoices/2026.txt
```

Vulnerable code:

```java
Path file = Path.of("/srv/app/uploads/alice").resolve(userInput);
byte[] content = Files.readAllBytes(file);
```

This is an **unsafe illustrative snippet**, not a standalone program. If `userInput` contains `..` components or is an absolute path, the accessed location can lie outside the authorized area. You cannot trust a path string just because the normal UI only displays filenames.

Input sources that must be treated as **untrusted** include HTTP parameters, uploaded filenames (`Content-Disposition`), paths inside ZIP/TAR archives, strings from queues, tenant-editable configurations, and data read back from a DB that originally came from users.

When the vulnerability occurs, consequences may include reading configuration files/secrets, overwriting another user's files, writing files into an executable directory of the application, or accessing another tenant's data. Impact depends on the **OS account privileges running the JVM** and the operation performed: read, create, modify, delete, list, or extract.

## 2. Directory Boundaries: Checking by Path Components

We must distinguish three concepts:

- **Allowed root**: a server-determined root directory, such as a tenant's dedicated directory. Never let the client supply the allowed root. Read/write permissions should also be clearly separated by business logic.
- **User path**: a relative name/path requested by the client under the root; must be parsed as data and validated.
- **Candidate/real path**: the path after combining and verifying the actual location. Only use it when it falls within the allowed boundary.

Key APIs in `java.nio.file`:

| API | What It Does | What It Does Not Guarantee |
| --- | --- | --- |
| `Path.of(text)` | Parses a string according to the filesystem provider/OS | Does not block traversal or verify existence |
| `path.isAbsolute()` | Detects an absolute path according to platform syntax | Does not handle all suspicious path forms such as drive-relative paths on Windows |
| `base.resolve(child)` | Joins paths; if `child` is absolute, the result may discard part or all of `base` | Does not check permissions |
| `path.normalize()` | Removes `.` and collapses `name/..` on the path string | **Does not** access the filesystem or resolve symbolic links |
| `path.toAbsolutePath()` | Produces an absolute path representation | Does not prove the target location is valid |
| `path.toRealPath()` | For an existing path: returns the real path, following symbolic links by default | Non-existent files have no real path; the result can become stale if the filesystem changes after checking |
| `candidate.startsWith(root)` | Matches **path components** according to the filesystem provider | Does not resolve symbolic links or protect against concurrent modification |
| `Files.isRegularFile(path)` | Checks for a regular file (following symlinks by default) | Does not replace authorization or safe file-opening operations |

**Do not use `String.startsWith` for paths.** For example, the string `/srv/app/files-backup/secret` starts with `/srv/app/files`, yet those two directories are siblings, not parent–child. `Path.startsWith` distinguishes path components; however, you should only compare normalized `Path` objects from the same provider and in matching forms (typically absolute/real paths).

Similarly, replacing `"../"` with an empty string or using a regex to block a single pattern is unsafe. Separators `/`/`\`, absolute paths, dots, URL encoding, case sensitivity, and platform-dependent path syntax vary widely. Use `Path` to check structure; apply a simpler filename policy whenever possible.

## 3. Verification Flow When Reading an Existing File

Given a configured root directory and an **existing** file, the basic flow is:

1. Determine the allowed root on the server side; use `toRealPath()` to anchor the root to an existing real location.
2. Require a relative name, rejecting empty names and absolute paths. For applications serving only regular files, reject any `..` component upfront to make the API contract clear.
3. Combine `root.resolve(relative).normalize()` and check that the candidate is a **descendant** of the root via `startsWith`; reject a candidate equal to the root itself if the API only accepts files.
4. Call `candidate.toRealPath()` to follow symbolic links to the physical location; check `real.startsWith(root)` **again** to prevent links leading outside.
5. Check the object type (e.g., regular file) and business authorization; only then read the file. Handle IO errors when the file does not exist, OS permissions deny access, or content changes.

Checking **both the lexical path and the real path** is intentional: the lexical check rejects escaping the root via `..` or absolute paths; the real-path check catches links whose names reside inside the root but point to files elsewhere.

## 4. Runnable Java 17+ Example: Restricting File Read Access

Create the file `SafeFileRead.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SafeFileRead {
    public static String readInside(Path configuredRoot, String userInput)
            throws IOException {
        if (userInput == null || userInput.isBlank()) {
            throw new IllegalArgumentException("Empty file name");
        }

        // Server-managed root, must exist.
        Path root = configuredRoot.toRealPath();
        Path relative = Path.of(userInput);

        // Allow only relative paths and no ".." component.
        if (relative.isAbsolute()) {
            throw new SecurityException("Absolute path is forbidden");
        }
        for (Path part : relative) {
            if (part.toString().equals("..")) {
                throw new SecurityException("Parent traversal is forbidden");
            }
        }

        // Check path structure; do not use String.startsWith.
        Path candidate = root.resolve(relative).normalize();
        if (candidate.equals(root) || !candidate.startsWith(root)) {
            throw new SecurityException("Outside allowed directory");
        }

        // Follow symbolic links to check where the file actually points.
        Path real = candidate.toRealPath();
        if (!real.startsWith(root) || !Files.isRegularFile(real)) {
            throw new SecurityException("Not an allowed regular file");
        }

        // Read UTF-8 content; for binary data, use Files.newInputStream.
        return Files.readString(real, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        Path sandbox = Files.createTempDirectory("path-demo-");
        Path root = Files.createDirectories(sandbox.resolve("allowed"));
        Path docs = Files.createDirectories(root.resolve("docs"));

        Files.writeString(
                docs.resolve("hello.txt"), "Xin chao",
                StandardCharsets.UTF_8);

        System.out.println("OK: " + readInside(root, "docs/hello.txt"));

        try {
            readInside(root, "../private.txt");
        } catch (SecurityException expected) {
            System.out.println("BLOCKED: ..");
        }

        try {
            readInside(root, docs.resolve("hello.txt").toString());
        } catch (SecurityException expected) {
            System.out.println("BLOCKED: absolute");
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 SafeFileRead.java
java SafeFileRead
```

Stdout (the temporary directory has a random name, which is not printed):

```text
OK: Xin chao
BLOCKED: ..
BLOCKED: absolute
```

Meaning of each verification layer:

- `"docs/hello.txt"` has a relative path inside the root, the file exists, and it is a regular file.
- `"../private.txt"` is blocked **before opening the file**, regardless of whether the target file exists.
- `docs.resolve("hello.txt").toString()` is an absolute path, so it is rejected even though it points **to a valid file**. The API rule is that the client may only submit a relative name.
- `toRealPath()` also prevents cases where `allowed/link.txt` is a symbolic link pointing to a file outside the root (assuming check and use observe the same filesystem state).

**Important limitation of the example:** This is a reasonable approach when the directory tree under the root **cannot have symbolic links or parent directories concurrently altered by an adversary**. There is still a window between checking `toRealPath()` and opening via `Files.readString()` (*time-of-check to time-of-use*, TOCTOU). If an attacker has permission to modify the directory structure during that moment, they can swap the path after the check. Section 6 explains how to raise the protection level. Do not treat the example as a guarantee against all filesystem races.

**Recommended additional test:** create a symbolic link **inside** the allowed root pointing to a file **outside**, then verify the application rejects it. Permission to create links on Windows depends on system/configuration, so it is omitted from the example's required stdout.

## 5. Non-Existent Paths: Uploads, File Creation, and Writing Data

For a new file, `candidate.toRealPath()` typically throws `NoSuchFileException` because the file does not exist yet. **Do not skip all checks and write the new file anyway.** You must verify that the real parent directory already exists, restrict the name, and create the file without overwriting.

A simple design for uploads: map `uploadId` to a server-generated filename (such as a UUID), storing the original name only as display metadata. The illustrative snippet below is **part of an upload-handling method**, assuming `configuredRoot` already has dedicated permissions and `bytes` has already been size-checked:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

// Inside a method that throws IOException:
Path root = configuredRoot.toRealPath();
String storedName = UUID.randomUUID() + ".bin";
Path output = root.resolve(storedName).normalize();

if (!output.getParent().equals(root)) {
    throw new SecurityException("Invalid output parent");
}
try (OutputStream out = Files.newOutputStream(
        output, StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(bytes);
}
```

`CREATE_NEW` atomically creates a new file with respect to the condition that **the destination filename does not yet exist** and refuses to overwrite an existing entry (including an existing symlink at the final name). It does not replace permission checks, disk quotas, parent directory protection, or OS sandboxing.

If you must allow clients to choose nested paths, validate every component against policy, reject absolute/parent traversal, constrain to the root with `Path.startsWith`, and verify the real parent directory via `toRealPath()` lies within the root. Ensure the parent directory cannot be replaced with a symbolic link by an attacker after validation. When creating intermediate directories, `Files.createDirectories` does not by itself guarantee the path stays inside the boundary; the entire chain of operations must be controlled.

For **overwrite, delete, rename, and move** operations, the risks are even higher: you must verify permissions on both destination and source resources, handle symlinks, and use atomic operations where supported by the platform. Avoid endpoints that accept direct absolute filesystem paths.

## 6. Symbolic Links and TOCTOU: Why `normalize()` Alone Is Not Enough

Consider this structure:

```text
/srv/app/allowed/
    reports/
    current -> /srv/app/private/
```

Here `current` is a symbolic link. The string `/srv/app/allowed/current/token.txt` looks **lexically** under the root, but after the filesystem resolves the link, it lies in `/srv/app/private/`. `normalize()` does not inspect symlinks at all. `toRealPath()` follows links by default to find the real target.

A harder case:

```text
T1: application checks allowed/reports/file.txt is safe
T2: attacker replaces reports with a symlink pointing outside
T3: application opens allowed/reports/file.txt
```

This is **TOCTOU**: the path validated at time T1 may no longer point to the same resource at T3. Repeating `toRealPath()` right before `Files.readString()` only narrows the race window; it **does not eliminate it completely**.

Practical protection layers:

1. **OS permissions:** do not allow the request submitter to modify parent directories, symlinks, junctions, or mounts beneath the region read by the trusted process. This is usually the essential safeguard.
2. **Isolate storage by user/tenant and operation permissions:** assign the allowed root server-side; user A cannot use a filename to read tenant B even if both sit under one broad root.
3. **Avoid following symlinks when unnecessary:** you can use `LinkOption.NOFOLLOW_LINKS` in APIs that support it (e.g., `Files.isRegularFile(path, NOFOLLOW_LINKS)`, `Files.newByteChannel`); check **every directory component**, not just the final name. Note that using `toRealPath(NOFOLLOW_LINKS)` instead of checking the real target is wrong if the path is still opened by following links afterward.
4. **Open relative to a directory handle:** `SecureDirectoryStream` in Java NIO.2 supports operations relative to an already-open directory stream, reducing races when supported by the filesystem provider. `Files.newDirectoryStream` **is not guaranteed** to return a `SecureDirectoryStream` on every OS/filesystem; check `instanceof`, define a fallback policy, and traverse segment by segment with `NOFOLLOW_LINKS` when needed.
5. **OS-level isolation** for strict requirements: containers/sandboxes, least-privilege accounts, appropriate mount namespaces/chroot, or OS APIs supporting file-descriptor-relative opens. Java `Path` by itself does not form a complete security boundary against a filesystem tree that an attacker can mutate continuously.

Do not rely on Java `SecurityManager` to solve this problem in modern applications. What must be protected are resource access permissions and the stability of path components during IO operations.

### Hard Links, Mounts, and Junctions

`toRealPath()` helps with symbolic links; it does not prove the file contents are “harmless”. Hard links can create additional names pointing to the same inode; mount points or Windows junctions/reparse points depend on the provider. Therefore the protection policy must cover permissions to create links/mounts, ownership, and OS permissions. A valid path under the root can still be rejected by business authorization.

## 7. URL Encoding, Windows Paths, and Uploaded Filenames

Traversal bugs are not limited to directly visible `../` strings.

- **URL decoding:** Percent-encoded strings must be decoded consistently at the HTTP/router layer. Avoid having one layer inspect the **undecoded** string while another layer decodes it again before opening the file. Do not arbitrarily double-decode; place the normalization/decoding rule at a single boundary.
- **Windows:** Besides `/`, there are `\`, drive letters, UNC paths (e.g., `\\server\share`), and drive-relative forms (e.g., `C:folder`). `Path.isAbsolute()` is not enough to turn every other string into a safe filename. If the API only needs a file identifier, it is best to accept only a simple, OS-independent character set and syntax.
- **Linux/macOS:** Backslash is typically a filename character, not necessarily a separator. A filter that only understands one OS's separator may behave differently when deployed on another OS.
- **Uploaded filenames:** Do not use raw `getOriginalFilename()` or a `filename` parameter as the storage path. It may contain a client-supplied path. The display name must be separated from the server-generated physical key; enforce length/character limits, and avoid special names and collisions.
- **Case and Unicode:** Case sensitivity and Unicode normalization depend on the filesystem. Do not use ad-hoc string comparisons to verify roots or user permissions.
- **Control characters and unusual paths:** `Path.of` may throw `InvalidPathException` depending on the platform. Catch it and return a bad-request error; do not leak system paths in HTTP errors.

For an endpoint accepting a **document ID**, a better design is `GET /documents/{id}` → look up ownership in the DB → retrieve the server-managed storage key. The API does not need to expose direct filesystem path manipulation to the client.

## 8. Zip Slip: Traversal in Archive Entry Names

Paths inside a ZIP are also supplied by an untrusted source. With `ZipEntry.getName()`, a name like `../outside.txt` or an absolute path can escape the extraction directory if the code joins it directly to the destination. Validation pattern **before creating directories or writing the entry**:

```java
// Snippet inside a ZipEntry read loop, not a standalone program.
Path root = destinationDirectory.toRealPath();
Path entryPath = Path.of(entry.getName());

if (entryPath.isAbsolute()) {
    throw new SecurityException("Absolute ZIP entry");
}
for (Path part : entryPath) {
    if (part.toString().equals("..")) {
        throw new SecurityException("Parent traversal in ZIP");
    }
}
Path target = root.resolve(entryPath).normalize();
if (!target.startsWith(root)) {
    throw new SecurityException("ZIP entry outside destination");
}
```

This is only **the name-checking part**. A complete extractor must also reject empty/suspicious entries, control parent directories and symlinks, avoid overwriting using `CREATE_NEW` where appropriate, limit entry count/total decompressed size (zip bomb), and handle stream data safely. If extracting through a filesystem with directories an attacker can modify concurrently, apply the race-resistant measures from Section 6.

## 9. Testing Boundary Protection

Do not test only a valid `"file.txt"`. Build a test suite with expected outcomes:

| Input or Scenario | Expectation |
| --- | --- |
| `docs/report.txt` exists inside allowed root | Readable if the user has business authorization |
| `../secret.txt` | Reject traversal |
| `docs/../../secret.txt` | Reject traversal |
| Absolute path pointing inside allowed root | Reject if the API only accepts relative paths |
| Absolute path pointing outside | Reject |
| `files-backup/x.txt` sibling directory to root `files` | Do not accept via string prefix comparison |
| Symlink under root pointing outside | Reject based on real target or NOFOLLOW policy |
| File inside root belonging to another tenant | Reject by authorization, even though containment is valid |
| Non-existent file or missing read permission | Handle error cleanly; do not return content outside root |
| Concurrent swap of symlink/parent directory during open | Prevent attacker from altering trusted directory structure; or use race-resistant open |
| ZIP entry containing parent traversal/absolute path | Reject before creating file |

Run compatibility tests on the actual target deployment platforms (Linux/Windows/containers), because path syntax and symbolic link support differ. For symlink tests, do not silently turn missing symlink-creation privileges into a “security test PASS”; report clearly that the test was skipped and verify it in a supported environment.

Common bugs worth checking during code review: `new File(root, userInput)` with no containment check; `normalize()` only; `String.startsWith(root)`; checking only basename in the UI; letting the client choose the root; calling `toRealPath(NOFOLLOW_LINKS)` and then opening the file by following links; and checking before creating a file while ignoring parent symlinks/races.

## 10. Production Design Rules

1. **Permission model first:** Define which data each user may view, which directories the app can access, and which operations (read/write/delete) are granted. Choose the allowed root on the server according to the tenant and resource permissions.
2. **Reduce input expressiveness:** Prefer an opaque file ID or a single filename; allow nested paths only when the problem genuinely requires them. Reject absolute paths, parent traversal, and ambiguous path forms.
3. **Verify structure and real location:** Use `Path.resolve/normalize/startsWith` and `toRealPath` for existing files; for new files, check the parent and create with `CREATE_NEW` when overwriting is disallowed.
4. **Protect against TOCTOU:** Prevent attackers from altering the trusted directory structure, or use relative opens via directory handle/`SecureDirectoryStream` when appropriate. Combine with least-privilege OS permissions.
5. **Validate data and operational resilience:** Limit file size, time, and total disk usage; handle exceptions; never expose absolute server paths in public responses/logs.
6. **Use attack fixtures/scenarios in testing:** Cover path traversal, symlinks, tenant boundaries, missing files, uploads, delete/overwrite, and archive entries.

The rule to remember is that **`normalize()` resolves path syntax; `toRealPath()` resolves the real target at a point in time; authorization and race-prevention measures maintain the actual permission boundary**. No single string-processing function guarantees safety for all filesystem operations.

**Official reference documentation:** Java SE 17 API `java.nio.file.Path` (`resolve`, `normalize`, `startsWith`, `toRealPath`), `java.nio.file.Files`, `java.nio.file.SecureDirectoryStream`, `java.nio.file.LinkOption`, and `java.nio.file.StandardOpenOption`.