# Normalize Does Not Replace Symbolic Link Handling in Java NIO

## 1. Core Problem: A Path That Looks Safe May Not Point to a Safe Resource

When a Java application receives a filename from a user, an API, or extracted archive content, we usually want to restrict all operations to a trusted directory, such as `/srv/app/uploads`. A common step is to use `Path.normalize()` to remove redundant `.` and `..` segments.

However, **`Path.normalize()` is purely an operation on the path name structure**. It **does not open the filesystem, verify that the file exists, check symbolic links, or know where each name component actually points**.

A symbolic link (symlink) is an entry containing a reference to another path. It can make a path **sit inside the allowed directory syntactically**, while the actual I/O operation accesses data **outside**.

~~~text
Filesystem:

/srv/app/uploads/
    public.txt
    latest -> /var/private
              (symbolic link)

/var/private/
    secret.txt

Input: latest/secret.txt
Normalize result:
/srv/app/uploads/latest/secret.txt
            │
            └── STILL has the /srv/app/uploads prefix syntactically

But when the OS follows the symlink:
latest → /var/private
           │
           └── /var/private/secret.txt   (outside uploads)
~~~

**Important conclusion:** `normalize()` helps handle path segments like `a/../b`, but **it does not replace a symbolic link handling policy**, is not sufficient to prevent all forms of path traversal, and does not create a filesystem sandbox mechanism.

This lesson distinguishes between a lexical path and a real path, and explains `toRealPath()`, `NOFOLLOW_LINKS`, containment checks, race conditions, and safe design practices in Java 17+.

## 2. Three Path Operations That Are Easily Confused

### 2.1. `normalize()` — Purely Syntactic Normalization

~~~java
Path p = Path.of("docs", ".", "drafts", "..", "report.txt");
System.out.println(p.normalize());
~~~

The output is typically:

~~~text
docs/report.txt
~~~

`normalize()` removes `.` segments and certain `name/..` pairs according to the provider's path rules. It **does not** access the filesystem, so it still works on non-existent paths.

A special note from the Java contract: if the component immediately before `..` is a symbolic link, removing the `name/..` pair may **change the target resource**, because filesystem symlink resolution is not equivalent to string removal.

Conceptual example:

~~~text
dir/link -> /different/location

Original path: dir/link/../file.txt
After normalize: dir/file.txt

The two paths do not necessarily point to the same real file.
~~~

Therefore, `normalize()` must never be described as "resolving symlinks" or "canonicalizing a filesystem path."

### 2.2. `toAbsolutePath()` — Obtaining an Absolute Path

~~~java
Path absolute = Path.of("reports", "a.txt").toAbsolutePath();
~~~

This method converts a relative path into an absolute path according to the filesystem/provider, usually based on the working directory. It **does not verify that the target exists and does not automatically handle symbolic links**.

`toAbsolutePath().normalize()` is still a path transformed primarily by syntax, **not proof that the actual I/O target lies inside the allowed directory**.

### 2.3. `toRealPath()` — Finding the Real Path of an Existing Entry

~~~java
Path real = path.toRealPath();
~~~

With the default filesystem provider and default options, `toRealPath()` returns the real absolute path to an **existing** entry, removes redundant components, and **follows symbolic links** to find the target. It may throw `IOException` when the entry does not exist, the path is invalid, permissions are insufficient, or an I/O error occurs.

Unlike `normalize()`, `toRealPath()` operates against the actual filesystem state at the time of the call.

| API | Requires entry to exist? | Follows symlinks? | Meaning |
| --- | --- | --- | --- |
| `normalize()` | No | Does not access filesystem | Simplifies path name structure |
| `toAbsolutePath()` | No | Does not verify symlinks itself | Obtains an absolute path |
| `toAbsolutePath().normalize()` | No | Does not verify I/O target | Absolute + lexical normalization |
| `toRealPath()` | Usually yes | Yes, by default | Determines the real path at check time |
| `toRealPath(NOFOLLOW_LINKS)` | Usually yes | Does not follow symlinks per option policy | Not suitable for proving the target after following lies inside root |

The word "usually" acknowledges provider-specific semantics; when designing for safety, you must understand the contract of the filesystem in use. On filesystems with symlinks, this distinction is especially important.

## 3. A Buggy Example: Checking Prefix After Normalize and Assuming Safety

Suppose `trustedRoot` is the directory the application permits reading from:

~~~java
Path trustedRoot = Path.of("/srv/app/uploads")
        .toAbsolutePath().normalize();

Path supplied = Path.of("latest/secret.txt");
Path candidate = trustedRoot.resolve(supplied).normalize();

if (!candidate.startsWith(trustedRoot)) {
    throw new SecurityException("Outside root");
}

// Not safe solely based on the check above!
byte[] data = Files.readAllBytes(candidate);
~~~

The snippet above is a **buggy illustrative snippet**, not a standalone runnable program, and `/` is an example on Unix-style path systems.

If `uploads/latest` is a symlink to `/var/private`, `candidate.startsWith(trustedRoot)` **still evaluates to true**, because the comparison examines **the name components of the `Path`**, without necessarily opening the symlink and verifying its target.

The check above partially protects against **purely lexical** traversal such as `../../etc/passwd`, but does not protect against **symlink traversal**.

### Why Use `Path.startsWith` Instead of `String.startsWith`?

Do not replace it with:

~~~java
candidate.toString().startsWith(trustedRoot.toString());
~~~

If the root is `/srv/app/data`, then `/srv/app/database-secret` also starts with the string `/srv/app/data`. `Path.startsWith(Path)` compares **by path components and provider rules**, avoiding that simple text-prefix bug.

However, even `Path.startsWith(Path)` is only meaningful on **the `Path` objects being compared**; if both are still lexical paths, it does not verify symlinks.

## 4. Checking the Real Target of an Existing File

If the policy permits **following symlinks only when the target remains inside the trusted root**, a useful check step is:

~~~java
Path rootReal = trustedRoot.toRealPath();

Path userInput = Path.of(userProvidedName);
if (userInput.isAbsolute()) {
    throw new SecurityException("Absolute paths not allowed");
}

Path candidate = trustedRoot.resolve(userInput).normalize();
Path candidateReal = candidate.toRealPath();

if (!candidateReal.startsWith(rootReal)) {
    throw new SecurityException("Resolved path escapes root");
}

// candidateReal is inside rootReal at check time.
// However, race conditions before opening the file must still be considered.
~~~

This is an **illustrative code snippet**, assuming `trustedRoot` and `userProvidedName` are already declared; `IOException` from the path or filesystem must be handled.

Key points:

1. `rootReal` can serve as the real absolute path of the trusted root directory.
2. `userInput.isAbsolute()` rejects caller-supplied absolute names, avoiding `resolve` logic depending on provider semantics for absolute paths.
3. `candidateReal` is determined after following symlinks along the path at check time.
4. `candidateReal.startsWith(rootReal)` checks containment of the **resolved path**; symlinks pointing outside the root are detected.
5. `toRealPath()` cannot be used directly on a **non-existent** target; creating new files requires a different strategy.
6. This check **does not eliminate Time-of-Check to Time-of-Use (TOCTOU)** if the path or symlink changes after the check.

This is a **defense layer**, not an absolute guarantee that a subsequent call to `Files.newInputStream(candidateReal)` or `Files.readAllBytes(candidate)` will always access the same resource.

### Policy Must Be Explicit: Allow or Reject Symlinks?

Two valid but different policies:

- **Allow internal symlinks:** accept `docs/current.txt -> docs/v2.txt` if the real target still resides within the root; reject links pointing outside.
- **Disallow symlinks:** reject any symlink in the components the application uses to access the resource, even if their target lies inside the root.

The second policy requires inspecting or opening paths using APIs capable of not following symlinks and resisting changes between steps; calling `normalize()` or `toRealPath()` once is not enough.

## 5. Runnable Java 17+ Example: Lexically Inside but Really Outside

The program creates a temporary directory containing a trusted area and a sibling area. Inside the trusted area is `public.txt`. It attempts to create a symlink `redirect` from the trusted area to the outside area; if the system supports it, the program demonstrates:

- The path `trusted/redirect/secret.txt` **lexically `startsWith(trusted)`**.
- The real target of that path **does not `startsWith(trustedReal)`**.
- A path `../outside/secret.txt` after `normalize` is rejected by the lexical check.
- The file `public.txt` genuinely lies inside the trusted area.

Some Windows environments require special privileges to create symbolic links; the code handles the case where privileges or library support are unavailable without assuming every OS behaves identically.

Save as `NormalizeVsSymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class NormalizeVsSymlinkDemo {

    public static void main(String[] args) throws IOException {
        Path workspace = Files.createTempDirectory("path-security-");
        Path trusted = workspace.resolve("trusted");
        Path outside = workspace.resolve("outside");
        Path publicFile = trusted.resolve("public.txt");
        Path secretFile = outside.resolve("secret.txt");
        Path link = trusted.resolve("redirect");

        try {
            Files.createDirectory(trusted);
            Files.createDirectory(outside);
            Files.writeString(publicFile, "public",
                    StandardCharsets.UTF_8);
            Files.writeString(secretFile, "private",
                    StandardCharsets.UTF_8);

            Path trustedReal = trusted.toRealPath();

            Path normal = trusted.resolve("public.txt");
            System.out.println("normal lexical inside="
                    + normal.toAbsolutePath().normalize()
                            .startsWith(trusted.toAbsolutePath().normalize()));
            System.out.println("normal real inside="
                    + normal.toRealPath().startsWith(trustedReal));

            Path traversal = trusted.resolve("../outside/secret.txt")
                    .normalize();
            System.out.println("dotdot lexical inside="
                    + traversal.startsWith(trusted.toAbsolutePath().normalize()));

            boolean linkCreated = false;
            try {
                Files.createSymbolicLink(link, outside.toAbsolutePath());
                linkCreated = true;
            } catch (UnsupportedOperationException
                    | IOException | SecurityException ex) {
                // Symlink is unavailable or not permitted.
            }

            if (!linkCreated) {
                System.out.println("symlink demo=unavailable");
            } else {
                System.out.println("symlink demo=available");
                Path redirected = trusted.resolve("redirect/secret.txt");
                System.out.println("symlink lexical inside="
                        + redirected.toAbsolutePath().normalize()
                                .startsWith(trusted.toAbsolutePath().normalize()));
                System.out.println("symlink real inside="
                        + redirected.toRealPath().startsWith(trustedReal));
            }
        } finally {
            // Delete the symlink as an entry, not the target it points to.
            Files.deleteIfExists(link);
            Files.deleteIfExists(publicFile);
            Files.deleteIfExists(secretFile);
            Files.deleteIfExists(trusted);
            Files.deleteIfExists(outside);
            Files.deleteIfExists(workspace);
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac NormalizeVsSymlinkDemo.java
java NormalizeVsSymlinkDemo
~~~

When the default filesystem supports creating symbolic links in the temporary directory, stdout is:

~~~text
normal lexical inside=true
normal real inside=true
dotdot lexical inside=false
symlink demo=available
symlink lexical inside=true
symlink real inside=false
~~~

If symlinks cannot be created, valid alternative stdout:

~~~text
normal lexical inside=true
normal real inside=true
dotdot lexical inside=false
symlink demo=unavailable
~~~

Analysis:

1. `trusted` and `outside` are two sibling directories. `trustedReal` serves as the containment root after real resolution.
2. `normal` is a regular file inside the root: both lexical and real-target checks return `true`.
3. `traversal` after `normalize()` points to the `outside` directory, so the lexical `startsWith(trusted)` check returns `false`.
4. `redirect`, if successfully created, is a symlink located **inside** the `trusted` directory pointing to `outside`.
5. `redirected` has a lexical name starting with `trusted`, so `symlink lexical inside` is `true`.
6. `redirected.toRealPath()` follows the symlink and leads to `outside/secret.txt`, outside the trusted root, so `symlink real inside` is `false`.
7. The `finally` block deletes the symbolic link as an entry; deleting the link does not delete the target file. Test files and directories are cleaned up in child-to-parent order.

**Key takeaway:** the example lets you observe the difference in **path resolution**. It does not claim that `toRealPath()` plus `startsWith()` alone creates a sandbox against all race conditions or an attacker with permissions to modify the filesystem.

## 6. Symbolic Links Can Appear in Multiple Positions in a Path

At least three cases must be distinguished:

### 6.1. The Target File Itself Is a Symlink

~~~text
trusted/report.txt -> /outside/report.txt
~~~

`Files.isSymbolicLink(trusted.resolve("report.txt"))` can detect that the final entry is a symbolic link at the time of the call. However, if another process has permission to replace that entry, the check result may become stale before opening.

### 6.2. An Intermediate Parent Directory Is a Symlink

~~~text
trusted/archives -> /outside
trusted/archives/2026.txt
~~~

`Files.isSymbolicLink(trusted.resolve("archives/2026.txt"))` only checks the final entry `2026.txt` and does not tell you that `archives` is a symlink. Even though `2026.txt` is a regular file, the path still traverses a symlink in a parent component.

A policy forbidding symlinks must examine **the entire traversal path**, not just the final name.

### 6.3. Symlink Combined With `..`

~~~text
trusted/jump -> /outside/folder
trusted/jump/../target.txt
~~~

Syntactically removing `jump/..` can turn the path name into `trusted/target.txt`, which is not necessarily equivalent to how the OS resolves `jump` and then moves up to the parent directory of the real target. Therefore, even the statement "`normalize` always preserves the physical target" is **false** when symbolic links are involved.

### Broken Symlinks and Symlink Cycles

A symbolic link can point to a non-existent path (broken) or form a cycle when following multiple links. `toRealPath()` may throw `IOException`/`FileSystemException` in those situations. Do not turn every exception into "safe path" or "file does not exist so allow creation"; handle errors conservatively according to policy.

## 7. What Does `NOFOLLOW_LINKS` Do and Not Do?

`java.nio.file.LinkOption.NOFOLLOW_LINKS` is an option telling certain APIs to operate on the **symbolic link entry itself** rather than following the link to its target.

Example:

~~~java
boolean link = Files.isSymbolicLink(path);

boolean regularWithoutFollowing =
        Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS);

Path lexicalLikeReal =
        path.toRealPath(LinkOption.NOFOLLOW_LINKS);
~~~

These are illustrative snippets assuming an existing `Path path` variable and the corresponding imports.

Meaning:

- `Files.isSymbolicLink(path)` checks the final path entry at the time of the call. It is not a safe traversal of the entire tree.
- `Files.isRegularFile(path, NOFOLLOW_LINKS)` generally does not treat the final symbolic link itself as a regular file, even when the link's target is a regular file.
- `toRealPath(NOFOLLOW_LINKS)` requests not following symbolic links when determining the path per provider semantics; **do not use this result to prove that opening a path by default will not escape the root**.
- File-opening APIs supporting `NOFOLLOW_LINKS` can reject a symbolic link at the **final entry**. They do not automatically guarantee that parent directory components are not symbolic links or cannot be changed.

An example requiring opening the final entry without following symlinks:

~~~java
try (SeekableByteChannel channel = Files.newByteChannel(
        candidate,
        Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
    // Read bytes through the opened channel.
}
~~~

This snippet requires importing `java.nio.channels.SeekableByteChannel`, `java.nio.file.*`, and `java.util.Set`, with `candidate` as a `Path`.

If the final file is a symbolic link, the call may be rejected according to policy/provider. **However, the parent path can still contain symbolic links**, so you must not claim this snippet alone is sufficient to enforce containment under a root that an attacker can modify.

Summary:

| Approach | Blocks lexical `../` traversal? | Detects symlinks? | Prevents races when path is mutated? |
| --- | --- | --- | --- |
| `normalize()` + `startsWith` | Partially, on path names | No | No |
| `toRealPath()` then check `rootReal` | Detects real target at check time | Follows symlinks by default | Not guaranteed by itself |
| `isSymbolicLink()` then `open()` | Incomplete | Checks at a single point in time | No |
| `NOFOLLOW_LINKS` when opening final entry | May reject final link | Effective where supported by the API | Does not necessarily protect ancestors |
| Directory-relative secure operations | Can greatly reduce path-swap risk between steps | Can control each component | Better when supported by provider and used properly |

## 8. TOCTOU: A Valid Check Can Still Open the Wrong File

TOCTOU stands for **Time of Check to Time of Use**: the filesystem state can change between the time of checking and the time of use.

Example:

~~~text
Thread A / application                  Process B / attacker

candidate.toRealPath()
→ /trusted/public.txt
                                        replaces public.txt with a symlink
                                        → /outside/secret.txt

Files.readAllBytes(candidate)
→ OS follows the new symlink
→ reads file outside root
~~~

Even if `toRealPath()` and `startsWith(rootReal)` just returned a good result, they only describe the filesystem **at a single point in time**. They do not lock the filename or entry against being swapped.

Race-prone pattern:

~~~java
if (!Files.isSymbolicLink(candidate)
        && candidate.toRealPath().startsWith(rootReal)) {
    return Files.readAllBytes(candidate);
}
~~~

If another process has permission to change directory entries, the actual open time may no longer match the check time.

Security documentation should never state "already canonicalized so definitely immune to symlink attacks." More accurately: canonicalization is a useful check, **but it must be paired with open/traversal mechanisms that do not rely on a mutable path name**.

## 9. `SecureDirectoryStream`: Operations Relative to an Open Directory

Java NIO provides the `java.nio.file.SecureDirectoryStream` interface for providers capable of operating **relative to an already-open directory stream**, helping reduce risk when filesystem entries are concurrently replaced.

A strategy:

1. Identify and open a root directory that the application trusts and controls write permissions on.
2. If the returned `DirectoryStream` supports `SecureDirectoryStream`, perform operations relative to the open directory rather than repeatedly resolving a new absolute path string.
3. For each subdirectory to enter, open it via `secure.newDirectoryStream(child, LinkOption.NOFOLLOW_LINKS)` when the policy forbids symlinks.
4. For the final file, use `secure.newByteChannel(relativeName, options)` and require `NOFOLLOW_LINKS` when appropriate.
5. Access data through the **opened channel**, rather than repeating check-then-open by global name.

Illustrative Java snippet reading a direct child file:

~~~java
Path baseReal = trustedRoot.toRealPath();

try (DirectoryStream<Path> opened = Files.newDirectoryStream(baseReal)) {
    if (!(opened instanceof SecureDirectoryStream<?>)) {
        throw new UnsupportedOperationException(
                "Provider does not support SecureDirectoryStream");
    }

    @SuppressWarnings("unchecked")
    SecureDirectoryStream<Path> secure =
            (SecureDirectoryStream<Path>) opened;

    Path childName = baseReal.getFileSystem().getPath("public.txt");

    try (SeekableByteChannel file = secure.newByteChannel(
            childName,
            Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
        // Perform read operations through the opened file channel.
    }
}
~~~

This is an **illustrative snippet**, not a standalone program. It requires importing `java.nio.file.*`, `java.nio.channels.SeekableByteChannel`, and `java.util.Set`, along with a trusted `Path trustedRoot`.

**Do not assume `SecureDirectoryStream` is always available** on every provider/OS/filesystem. If the application has mandatory security requirements, when the provider does not support it you should **fail closed** or use stronger isolation rather than silently falling back to a race-prone check-then-open model.

The example only opens **one direct child name**. If the input has multiple components, each directory component must be traversed using a new `SecureDirectoryStream`, controlling `.`/`..`, links, and permissions; never pass an unchecked path containing `../` and expect a root-level handle to create a sandbox on its own.

`SecureDirectoryStream` offers stronger benefits than pure path checking, but it does not replace permission design, ownership, initial root trustworthiness, or file access policies. Nor does it protect sensitive data inside an already-opened file if the application lets users choose the wrong file in the first place.

## 10. Creating a New File: `toRealPath()` Cannot Check a Non-Existent Target

A common case is uploading a new file:

~~~text
trusted/
    users/
       new-image.png   (does not exist yet)
~~~

`target.toRealPath()` will fail if `new-image.png` does not exist yet. You must not see that error and blindly allow creation while skipping ancestor checks.

For a policy permitting creation of a **new file** inside a trusted directory, you need to:

- Verify that the root and parent directory path **already exist**.
- Determine that the target lies within the policy-permitted structure.
- If the root/subdirectory can be altered by an attacker, use safe directory-relative operations if supported by the provider.
- Create using `CREATE_NEW` when you want to fail if the final entry already exists, avoiding overwriting someone else's file.
- Use `NOFOLLOW_LINKS` or a non-following mechanism on the final entry if supported by the API/provider and required by policy.
- If the filename comes from a user, reject absolute paths, `..`, and special components per policy; use a validated basename or a server-side ID whenever possible.
- Set appropriate access permissions/ownership and staging area. `Files.createDirectories()` is not a symlink-race protection mechanism when parent directories are untrusted.

For example, saving uploads using server-generated names instead of the raw path from an HTTP request is usually simpler and safer. Do not let clients choose deep subdirectories if business requirements do not need it.

### What Does `CREATE_NEW` Do?

`StandardOpenOption.CREATE_NEW` requires creating a new file and failing if the target entry already exists; the check-and-create operation on the final entry is defined as atomic relative to other creation operations under the API contract. This is useful for avoiding accidental overwrites of an existing entry, but **does not replace protecting the entire parent directory** if ancestors can be modified.

## 11. Defense in Depth and Trust Boundaries

No single `normalize()` statement replaces filesystem security design. A system handling paths from untrusted sources can apply the following layers:

| Defense Layer | Role |
| --- | --- |
| API accepts only server-generated IDs/filenames | Prevents users from supplying arbitrary paths |
| Check absolute paths and `..` components | Eliminates direct traversal forms |
| `Path.normalize()` and `Path.startsWith()` | Checks lexical structure of the constructed path |
| `toRealPath()` with real root | Detects symlink escape at check time for existing entries |
| `NOFOLLOW_LINKS` and/or `SecureDirectoryStream` | Restricts following symlinks and reduces check/use races |
| OS permissions and application-controlled directories | Prevents attackers from swapping links/entries in the trusted region |
| Least-privilege process account | Limits damage if a logic bug occurs |
| Sandboxing / containers / mount policy | Provides additional OS-level boundaries |
| Logging and symlink-race testing | Verifies exploitation scenarios |

**Path guarantees** must be distinguished from **user authorization**. Even if a file lies inside a policy-compliant root, that does not mean any user is allowed to read it. The application still must verify access permissions for the user object/identity.

### Do Not Rely on Strings and Separators

`String.startsWith` does not understand component boundaries. Manual string concatenation like `root + "/" + filename` also depends on separators, absolute paths, Windows drive letters, and providers. Use `Path`/`FileSystem` consistently, then apply real-path containment policies when needed.

If multiple filesystems/providers exist (`zipfs`, network filesystems, etc.), comparing paths across different providers may not have the same semantics as paths on the same filesystem. Only compare when you clearly understand `Path.getFileSystem()` and provider semantics.

## 12. Commonly Confused Scenarios

### Scenario A: Lexical Check Passes, but Symlink Points Outside

~~~text
trusted/aliases -> /private
trusted/aliases/account.db
~~~

`normalize().startsWith(trusted)` can be true, yet `toRealPath()` (following by default) points to `/private/account.db`. This is the exact case this lesson emphasizes.

### Scenario B: Symlink Points to Another File Still Inside the Root

~~~text
trusted/latest.txt -> trusted/v2.txt
~~~

If policy **allows internal symlinks**, this can be accepted after verifying real containment. If policy **forbids all symlinks**, it must still be rejected. Security is not just "whether a link points outside or not"; it is a concrete policy.

### Scenario C: Symlink in an Ancestor

~~~text
trusted/data -> /private
trusted/data/info.txt
~~~

`Files.isSymbolicLink(trusted/data/info.txt)` does not check `data`. A `NOFOLLOW_LINKS` API on the final file may still traverse the link in the parent directory if traversal steps are not protected.

### Scenario D: Verified Path Swapped Afterward

~~~text
Check: trusted/config.txt is a real file.
Race: attacker replaces it with a symlink.
Use: application opens using the old name.
~~~

`toRealPath()` and `isSymbolicLink()` inspect at the time of the call and do not grant an immutable lock on the filename. Use handle-based access and filesystem permissions to reduce risk.

### Scenario E: Target File Does Not Exist Yet

`toRealPath()` cannot guarantee containment of a non-existent file by calling it directly on the target. Protect parent directories, create new entries with a consistent policy, and prefer server-generated names.

### Scenario F: Traversing Directories With `Files.walk`

`Files.walk(...)` by default does not follow symbolic links as directories unless `FOLLOW_LINKS` is enabled. However, scanning a tree does not make all subsequent operations safe; the tree can still change during or after traversal, especially in directories writable by others.

## 13. Secure File Access Design Checklist

When writing a read or upload API from user-supplied names:

1. **Identify the trusted root:** directory whose owner and write permissions are controlled by the application.
2. **Define the symlink policy:** forbid completely or allow links whose real targets are internal?
3. **Restrict path selection:** prefer server-generated IDs/basenames over arbitrary relative paths.
4. **Check path syntax:** absolute paths, `..`, and provider-specific special characters/paths.
5. **Use lexical `normalize` as a secondary step:** useful, but never treat it as a sandbox.
6. **If the entry already exists**, use `toRealPath()` to verify real containment per policy when appropriate.
7. **Handle races:** do not assume check-then-open is atomic; use `SecureDirectoryStream`/handle access or suitable isolation.
8. **For creating new files**, protect the parent, use `CREATE_NEW` if overwriting is disallowed, and do not follow links arbitrarily.
9. **Do not give the process excessive OS privileges:** even if a traversal bug happens, access scope remains bounded.
10. **Test negative cases too:** `../`, absolute paths, similar root prefixes, symlink on final file, symlink in ancestor, broken links, replace-during-open, and permission denied.
11. **Manage fallbacks:** if the filesystem lacks required security primitives, return an error rather than silently downgrading.
12. **Evaluate application permissions:** a file inside the root is not sufficient to prove the caller is authorized to view its content.

## 14. Common Mistakes and Fixes

**Mistake 1 — Equating `normalize` with canonicalize.** `normalize()` only transforms syntax and does not follow symbolic links. Use `toRealPath()` to find the real target **at check time**, while still accounting for races.

**Mistake 2 — Checking `startsWith(root)` on a lexical path and opening arbitrarily.** A symlink inside the root can point outside. A policy and safe resolve/open mechanism are needed.

**Mistake 3 — Using `String.startsWith(rootString)`.** Text prefixes lack component boundaries and easily accept `data-secret` when the root is `data`. Use `Path.startsWith(Path)` appropriately.

**Mistake 4 — Calling `isSymbolicLink` only on the final file.** A symlink can be in any ancestor. Under a no-symlink policy, each traversal step must be managed and TOCTOU mitigated.

**Mistake 5 — Thinking `NOFOLLOW_LINKS` on the final file blocks all symlinks.** It does not automatically prevent ancestor symlinks. Safe directory-relative traversal control is required.

**Mistake 6 — Checking `realPath` then reopening by an unprotected name.** An attacker can swap a symlink between check and use. Prefer operations based on directory/file handles and filesystem permissions.

**Mistake 7 — Treating every `toRealPath` error as proof the target "does not exist so it is safe."** Errors can be caused by broken symlinks, permissions, or link loops. Do not fail open.

**Mistake 8 — Allowing user-supplied absolute paths.** `root.resolve(userInput)` with an absolute path can lead to an unintended location. Reject absolute inputs and check policy before use.

**Mistake 9 — Assuming files inside the trusted root are automatically authorized to read.** Per-user and per-data-type authorization is still required.

**Mistake 10 — Relying on `SecureDirectoryStream` without checking support.** Not all providers support it; applications with strict requirements should fail closed if the required primitive is missing.

## 15. Self-Check

1. Does `Path.normalize()` read symbolic links automatically? **No.** It processes name components syntactically.
2. Does `toAbsolutePath().normalize()` verify that a file exists? **No.**
3. How does `toRealPath()` handle symbolic links by default? **It follows symlinks** to find the real path of an existing entry, per provider semantics.
4. Does `candidate.normalize().startsWith(root.normalize())` returning true guarantee opening will not escape the root? **No.**
5. Why use `Path.startsWith` instead of `String.startsWith`? Because it compares **path components**, not just a text prefix.
6. Does `Files.isSymbolicLink(candidate)` returning false mean no parent is a symlink? **No.**
7. Does `NOFOLLOW_LINKS` on the final file automatically block links in parents? **Not guaranteed.**
8. Does `toRealPath()` before `Files.readAllBytes()` eliminate races when directory entries can be swapped? **Not completely**; that is TOCTOU.
9. Can `toRealPath()` succeed on a non-existent file to verify it? **Usually no**; a safe file-creation strategy based on the parent is needed.
10. Is `SecureDirectoryStream` always provided by every filesystem? **No.**
11. Should symlink `trusted/latest -> trusted/v2` be allowed or not? **Depends on policy:** allow internal links or forbid all symlinks.
12. Does a file inside a policy-compliant root prove the user is authorized to view it? **No**; authorization must be checked.
13. If sensitive data must be protected even if path logic has bugs, what external layer outside Java helps? **Least-privilege OS permissions, root ownership, sandbox/container/mount policies**, and data isolation.
14. Which model is better when an attacker can modify directories between check and open? **Safe handle/directory-based operations with no-follow per component**, combined with an explicit policy.

**Remember:** `Path.normalize()` strips redundant name components but **does not know where symbolic links point**. To inspect existing targets, understand `toRealPath()` and containment over real paths. To resist path changes between check and open, mechanisms such as `SecureDirectoryStream` when supported by the provider, along with filesystem permissions and trusted ownership management, are needed. **Never treat a syntactic normalization call as an application security boundary.**
