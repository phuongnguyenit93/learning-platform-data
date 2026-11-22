# `normalize()` Does Not Replace Symbolic Link Handling in Java NIO

## 1. The Core Problem: A Path That Looks Safe May Not Point to a Safe Resource

When a Java application receives a filename from a user, an API, or archive extraction, we usually want to confine all operations within a trusted directory, such as `/srv/app/uploads`. A familiar step is calling `Path.normalize()` to remove redundant `.` and `..`.

However, **`Path.normalize()` only operates on the syntactic structure of the path name**. It **does not open the filesystem, does not verify that the file exists, does not check symbolic links, and does not know where each name component actually points**.

A symbolic link (symlink) is an entry containing a reference to another path. It can make a path **appear syntactically inside the allowed directory**, while the actual I/O operation accesses data **outside**.

~~~text
Filesystem:

/srv/app/uploads/
    public.txt
    latest -> /var/private
              (symbolic link)

/var/private/
    secret.txt

Input: latest/secret.txt
normalize() result:
/srv/app/uploads/latest/secret.txt
            │
            └── STILL has the /srv/app/uploads prefix syntactically

But when the OS follows the symlink:
latest → /var/private
           │
           └── /var/private/secret.txt   (outside uploads)
~~~

**Key conclusion:** `normalize()` helps clean up path segments like `a/../b`, but it **does not replace a symbolic link handling policy**, is not sufficient to prevent all forms of path traversal, and does not create a filesystem sandbox.

This lesson distinguishes lexical paths from real paths, explains `toRealPath()`, `NOFOLLOW_LINKS`, containment checks, race conditions, and safe design practices in Java 17+.

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

`normalize()` removes `.` segments and some `name/..` pairs according to the provider's path rules. It **does not** access the filesystem, so it still works on paths that do not exist yet.

A special note from the Java contract: if the component immediately preceding `..` is a symbolic link, removing the `name/..` pair can **change the resource pointed to**, because filesystem symlink resolution is not equivalent to string removal.

Conceptual example:

~~~text
dir/link -> /different/location

Original path: dir/link/../file.txt
After normalize: dir/file.txt

The two paths do not necessarily point to the same real file.
~~~

Therefore, never describe `normalize()` as "resolving symlinks" or "canonicalizing a filesystem path".

### 2.2. `toAbsolutePath()` — Obtaining an Absolute Path

~~~java
Path absolute = Path.of("reports", "a.txt").toAbsolutePath();
~~~

This method converts a relative path into an absolute path according to the filesystem/provider, typically based on the working directory. It **does not verify that the target exists and does not automatically handle symbolic links**.

`toAbsolutePath().normalize()` is still a path transformed primarily by syntax, **not proof that the real I/O target resides inside the allowed directory**.

### 2.3. `toRealPath()` — Finding the Real Path of an Existing Entry

~~~java
Path real = path.toRealPath();
~~~

With the default filesystem provider and default options, `toRealPath()` returns the real absolute path to an **existing** entry, eliminating redundant components and **following symbolic links** to find the target. It can throw `IOException` when the entry does not exist, the path is invalid, permissions are insufficient, or an I/O error occurs.

Unlike `normalize()`, `toRealPath()` operates against the actual filesystem state at the time of the call.

| API | Requires Entry to Exist? | Follows Symlinks? | Meaning |
| --- | --- | --- | --- |
| `normalize()` | No | Does not access the filesystem | Simplifies path name structure |
| `toAbsolutePath()` | No | Does not verify symlinks | Obtains an absolute path |
| `toAbsolutePath().normalize()` | No | Does not verify I/O target | Absolute + lexical normalization |
| `toRealPath()` | Usually yes | Yes, by default | Determines the real path at the time of check |
| `toRealPath(NOFOLLOW_LINKS)` | Usually yes | Does not follow symlinks per option policy | Not suitable for proving the target after following lies inside the root |

The word "usually" notes provider-specific semantics; when designing safely, you must understand the contract of the filesystem in use. On filesystems with symlinks, this distinction is especially critical.

## 3. A Buggy Example: Checking the Prefix After `normalize()` and Assuming Safety

Suppose `trustedRoot` is a directory the application is allowed to read:

~~~java
Path trustedRoot = Path.of("/srv/app/uploads")
        .toAbsolutePath().normalize();

Path supplied = Path.of("latest/secret.txt");
Path candidate = trustedRoot.resolve(supplied).normalize();

if (!candidate.startsWith(trustedRoot)) {
    throw new SecurityException("Outside root");
}

// Not safe solely because of the check above!
byte[] data = Files.readAllBytes(candidate);
~~~

The snippet above is a **buggy illustrative fragment**, not a standalone runnable program, and `/` is an example on systems using Unix-style paths.

If `uploads/latest` is a symlink to `/var/private`, `candidate.startsWith(trustedRoot)` **still evaluates to true**, because the comparison inspects **the name components of the `Path`**, without requiring opening symlinks or verifying the target.

The check above partially protects against **purely lexical** traversal like `../../etc/passwd` but does not protect against **symlink traversal**.

### Why Must You Use `Path.startsWith` Instead of `String.startsWith`?

Do not replace it with:

~~~java
candidate.toString().startsWith(trustedRoot.toString());
~~~

If the root is `/srv/app/data`, then `/srv/app/database-secret` also starts with the string `/srv/app/data`. `Path.startsWith(Path)` compares **by path components and provider rules**, avoiding that simple text-prefix bug.

Yet even `Path.startsWith(Path)` is only meaningful for **the `Path` objects being compared**; if both remain lexical paths, it does not verify symlinks.

## 4. Checking the Real Target of an Existing File

If the policy allows **following symlinks only when the target stays inside the trusted root**, a useful verification step is:

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

// candidateReal is inside rootReal at the time of check.
// However, race conditions before opening the file must still be considered.
~~~

This is an **illustrative snippet**, with `trustedRoot` and `userProvidedName` already declared; `IOException` from the path or filesystem must be handled.

Key points:

1. `rootReal` can be the real absolute path of the trusted root directory.
2. `userInput.isAbsolute()` rejects caller-supplied absolute names; avoid letting `resolve` logic depend on provider semantics for absolute paths.
3. `candidateReal` is determined after following symlinks in the path at the time of check.
4. `candidateReal.startsWith(rootReal)` checks containment of the **resolved path**; symlinks pointing outside the root will be detected.
5. `toRealPath()` cannot be used directly for targets that **do not exist yet**; creating new files requires a different strategy.
6. This check **does not eliminate Time-of-Check to Time-of-Use (TOCTOU)** if paths or symlinks change after the check.

This is a **defense layer**, not an absolute guarantee that a subsequent `Files.newInputStream(candidateReal)` or `Files.readAllBytes(candidate)` call will always access the same resource.

### Policy Must Be Clear: Allow or Reject Symlinks?

Two valid but different policies:

- **Allow internal symlinks:** accept `docs/current.txt -> docs/v2.txt` if the real target remains inside the root; reject links pointing outside.
- **Disallow all symlinks:** reject any symlink on components the application uses to access resources, even when their target lies inside the root.

The second policy requires inspecting or opening paths with APIs capable of not following symlinks and resisting changes between steps; calling `normalize()` or `toRealPath()` once is not enough.

## 5. Runnable Java 17+ Example: Lexical Inside, Real Outside

The program creates a temporary directory containing a trusted area and a sibling area. Inside the trusted area is `public.txt`. It attempts to create a symlink `redirect` from the trusted area to the outside area; if supported by the system, the program proves:

- The path `trusted/redirect/secret.txt` **lexically startsWith(trusted)**.
- The real target of that path **does not startsWith(trustedReal)**.
- A path `../outside/secret.txt` after `normalize` is rejected by the lexical check.
- The file `public.txt` genuinely lies inside the trusted area.

Some Windows environments require special privileges to create symbolic links; the code handles lack of privilege/unsupported environments without assuming all operating systems behave identically.

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
                // Symlink unavailable or not permitted.
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

If symbolic links cannot be created, valid alternative stdout is:

~~~text
normal lexical inside=true
normal real inside=true
dotdot lexical inside=false
symlink demo=unavailable
~~~

Analysis:

1. `trusted` and `outside` are sibling directories. `trustedReal` serves as the containment root after real resolution.
2. `normal` is a regular file inside the root: both the syntactic check and the real-target check return `true`.
3. `traversal` after `normalize()` points to the `outside` directory, so the lexical `startsWith(trusted)` check returns `false`.
4. `redirect`, if created successfully, is a symlink located **inside** `trusted` yet pointing to `outside`.
5. `redirected` has a lexical name starting with `trusted`, so `symlink lexical inside` is `true`.
6. `redirected.toRealPath()` follows the symlink and leads to `outside/secret.txt`, outside the trusted root, so `symlink real inside` is `false`.
7. The `finally` block deletes the symbolic link as an entry; deleting a link does not delete its target file. Test files/directories are cleaned up in child-to-parent order.

**Takeaway:** the example lets you observe the difference in **path resolution**. It does not claim that `toRealPath()` plus `startsWith()` alone creates a sandbox immune to every race condition or an attacker with permissions to modify the filesystem.

## 6. Symbolic Links Can Appear at Multiple Positions in a Path

At least three patterns must be distinguished:

### 6.1. The Target File Itself Is a Symlink

~~~text
trusted/report.txt -> /outside/report.txt
~~~

`Files.isSymbolicLink(trusted.resolve("report.txt"))` can detect that the final entry is a symbolic link at the time of the call. However, if another process has permission to replace that entry, the check result can become stale before opening.

### 6.2. An Intermediate Parent Directory Is a Symlink

~~~text
trusted/archives -> /outside
trusted/archives/2026.txt
~~~

`Files.isSymbolicLink(trusted.resolve("archives/2026.txt"))` only checks the final entry `2026.txt`; it does not tell you that `archives` is a symlink. Even though `2026.txt` is a regular file, the path still passes through a symlink in a parent component.

A policy forbidding symlinks must examine **the entire traversal path**, not just the final name.

### 6.3. Symlinks Combined with `..`

~~~text
trusted/jump -> /outside/folder
trusted/jump/../target.txt
~~~

Syntactically removing `jump/..` can turn the path name into `trusted/target.txt`, which is not necessarily equivalent to how the OS resolves `jump` and then ascends to the parent of the real target. Therefore, even the statement "`normalize` always preserves the physical target" is **false** when symbolic links are involved.

### Broken Symlinks and Symlink Cycles

A symbolic link can point to a non-existent path (broken) or create a cycle when following multiple links. `toRealPath()` can throw `IOException`/`FileSystemException` in those situations. Do not treat every exception as "safe path" or "file does not exist so allow creation"; handle errors conservatively according to policy.

## 7. What Does `NOFOLLOW_LINKS` Do and What Can It Not Do?

`java.nio.file.LinkOption.NOFOLLOW_LINKS` is an option telling certain APIs to operate on the **symbolic link entry itself** instead of following the link to its target.

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
- `toRealPath(NOFOLLOW_LINKS)` requests not following symbolic links when determining the path per provider semantics; **do not use this result to prove that opening a path with default behavior will stay inside the root**.
- File-opening APIs supporting `NOFOLLOW_LINKS` can reject a symbolic link at the **final entry**. That does not automatically guarantee parent directory components are not symbolic links or have not been swapped.

An example requiring opening the final entry without following symlinks:

~~~java
try (SeekableByteChannel channel = Files.newByteChannel(
        candidate,
        Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
    // Read bytes through the opened channel.
}
~~~

The snippet requires importing `java.nio.channels.SeekableByteChannel`, `java.nio.file.*`, and `java.util.Set`; `candidate` is a `Path`.

If the final file is a symbolic link, the call can be rejected depending on policy/provider. **However, the parent path can still contain symbolic links**, so you must not claim this snippet is sufficient to enforce containment under a root an attacker can modify.

Summary:

| Approach | Blocks Lexical Traversal Like `../`? | Detects Symlinks? | Prevents Races When Path Changes? |
| --- | --- | --- | --- |
| `normalize()` + `startsWith` | Partially, on path name | No | No |
| `toRealPath()` then check `rootReal` | Detects real target at check time | Follows symlinks by default | Not guaranteed |
| `isSymbolicLink()` then `open()` | Incomplete | Checks at a single point in time | No |
| `NOFOLLOW_LINKS` when opening final entry | Can reject final link | Works where supported by API | Does not necessarily protect ancestors |
| Directory-relative secure operations | Greatly reduces risk of path changes between steps | Can inspect every component | Better when supported by provider and used properly |

## 8. TOCTOU: A Correct Check Can Still Open the Wrong File

TOCTOU stands for **Time of Check to Time of Use**: the filesystem state can change between the check and the use.

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

Even if `toRealPath()` and `startsWith(rootReal)` just returned a good result, that only describes the filesystem **at one point in time**. It does not lock the filename or entry against replacement.

Race-prone pattern:

~~~java
if (!Files.isSymbolicLink(candidate)
        && candidate.toRealPath().startsWith(rootReal)) {
    return Files.readAllBytes(candidate);
}
~~~

If another process has permission to replace directory entries, the actual open time may no longer match the check time.

Security documentation should never state "already canonicalized, so definitely immune to symlink attacks". More accurately: canonicalization is a useful check, **but you also need an open/traversal mechanism that does not rely on a replaceable path name**.

## 9. `SecureDirectoryStream`: Operating Relative to an Already-Open Directory

Java NIO provides the `java.nio.file.SecureDirectoryStream` interface for providers capable of operating **relative to an open directory stream**, reducing the risk when filesystem entries are replaced concurrently.

One strategy:

1. Identify and open a root directory whose write permissions are trusted and controlled by the application.
2. If the returned `DirectoryStream` supports `SecureDirectoryStream`, perform operations relative to the opened directory instead of repeatedly resolving a new absolute path string.
3. For each subdirectory to enter, open it with `secure.newDirectoryStream(child, LinkOption.NOFOLLOW_LINKS)` when policy forbids symlinks.
4. For the final file, use `secure.newByteChannel(relativeName, options)` and pass `NOFOLLOW_LINKS` where appropriate.
5. Access data through the **opened channel**, rather than repeating check-then-open by global path name.

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

**Do not assume `SecureDirectoryStream` is always available** on every provider/OS/filesystem. If the application has strict security requirements, when the provider does not support it, **fail closed** or use stronger isolation rather than silently falling back to a race-prone check-then-open model.

The example only opens **one direct child name**. If the input has multiple components, traverse each directory component using a new `SecureDirectoryStream`, checking `.`/`..`, links, and permissions; never pass an unchecked path containing `../` and expect a root-level handle to automatically act as a sandbox.

`SecureDirectoryStream` offers stronger guarantees than pure path checks, but it does not replace permission design, ownership, trustworthiness of the initial root, or file access policies. Nor does it prevent sensitive data leakage inside an opened file if the application lets users choose the wrong file in the first place.

## 10. Creating New Files: `toRealPath()` Cannot Check a Non-Existent Target

A common case is uploading a new file:

~~~text
trusted/
    users/
       new-image.png   (does not exist yet)
~~~

`target.toRealPath()` will fail if `new-image.png` does not exist yet. Do not see the error and blindly allow creation while skipping ancestor checks.

With a policy allowing **new file** creation inside a trusted directory, you must:

- Verify that the root and parent directory path **already exist**.
- Determine that the target falls within the policy-permitted structure.
- If the root/subdirectory could be modified by an attacker, use safe directory-relative operations if supported by the provider.
- Create with `CREATE_NEW` when you want to fail if the final entry already exists; avoid overwriting someone else's file.
- Use `NOFOLLOW_LINKS` or a non-following mechanism on the final entry if supported by the API/provider and required by policy.
- If the filename comes from the user, reject absolute paths, `..`, and special components per policy; use a validated basename or a server-side ID whenever possible.
- Set appropriate access permissions/ownership and staging areas. `Files.createDirectories()` is not a symlink-race defense when parent directories are untrusted.

For example, saving uploads using a server-generated name instead of the raw path from the HTTP request is usually simpler and safer. Do not let clients choose deep subdirectories if business requirements do not need it.

### What Does `CREATE_NEW` Do?

`StandardOpenOption.CREATE_NEW` requires creating a new file and fails if the destination entry already exists; the check-and-create operation at the final entry is defined as atomic relative to other creation operations per the API contract. This is useful for avoiding accidental overwrites of an existing entry, but it **does not replace protecting the entire parent directory** if ancestors can be swapped.

## 11. Defense in Depth and Trust Boundaries

No single `normalize()` call replaces filesystem security design. A system handling paths from untrusted sources can apply the following layers:

| Defense Layer | Role |
| --- | --- |
| API accepting only server-generated IDs/filenames | Avoids letting users supply arbitrary paths |
| Checking absolute paths and `..` components | Eliminates direct traversal forms |
| `Path.normalize()` and `Path.startsWith()` | Checks lexical structure of the constructed path |
| `toRealPath()` against the real root | Detects symlink escapes at check time for existing entries |
| `NOFOLLOW_LINKS` and/or `SecureDirectoryStream` | Restricts symlink following and reduces check/use races |
| OS permissions and application-controlled directories | Prevents attackers from swapping links/entries inside trusted areas |
| Least-privilege process account | Limits damage if a logic bug occurs |
| Sandboxing / containers / mount policies | Adds an operating-system boundary |
| Logging and symlink-race tests | Verifies abuse scenarios |

Distinguish **path guarantees** from **user authorization**. Even if a file lies inside a policy-compliant root, that does not mean any user may read it. The application must still verify access rights for the target object and user identity.

### Do Not Rely on Strings and Separators

`String.startsWith` does not understand component boundaries. Manual string concatenation like `root + "/" + filename` also depends on separators, absolute paths, Windows drive letters, and providers. Use `Path`/`FileSystem` consistently; then apply real-path containment policies when needed.

If multiple filesystems/providers exist (`zipfs`, network filesystems, etc.), comparing paths from different providers may not mean the same thing as paths on the same filesystem. Only compare when you understand `Path.getFileSystem()` and provider semantics.

## 12. Scenarios That Commonly Cause Confusion

### Scenario A: Lexical Check Passes, but Symlink Points Outside

~~~text
trusted/aliases -> /private
trusted/aliases/account.db
~~~

`normalize().startsWith(trusted)` may return true, but `toRealPath()` (which follows by default) points to `/private/account.db`. This is the core case highlighted by this lesson.

### Scenario B: Symlink Points to Another File Still Inside the Root

~~~text
trusted/latest.txt -> trusted/v2.txt
~~~

If the policy **allows internal symlinks**, it may be accepted after verifying real containment. If the policy **forbids all symlinks**, it must still be rejected. Security is not merely “does the link point outside or not”; it is a concrete policy.

### Scenario C: Symlink in an Ancestor

~~~text
trusted/data -> /private
trusted/data/info.txt
~~~

`Files.isSymbolicLink(trusted/data/info.txt)` does not check `data`. A `NOFOLLOW_LINKS` API on the final file can still traverse the link in the parent directory unless traversal steps are protected.

### Scenario D: Verified Path Is Swapped Afterward

~~~text
Check: trusted/config.txt is a real file.
Race: attacker replaces it with a symlink.
Use: application opens by the old name.
~~~

`toRealPath()` and `isSymbolicLink()` inspect at call time; they do not place an immutable lock on the filename. Use handle-based access and filesystem permissions to reduce risk.

### Scenario E: Target File Does Not Exist Yet

`toRealPath()` cannot verify containment of a non-existent file by calling it directly on the target. Protect parent directories, create the new entry with a consistent policy, and prefer server-generated names.

### Scenario F: Traversing Directories with `Files.walk`

`Files.walk(...)` does not follow symbolic links as directories by default when `FOLLOW_LINKS` is not enabled. However, scanning a tree does not make all subsequent operations safe; the tree can still change during or after traversal, especially in directories writable by others.

## 13. Safe File Access Design Checklist

When writing an API to read or upload from a user-supplied name:

1. **Identify the trusted root**: a directory whose ownership and write permissions are controlled by the application.
2. **Define the symlink policy**: forbid completely or allow links whose real target is internal?
3. **Reduce path selection power**: prefer server-generated IDs/basenames over arbitrary relative paths.
4. **Validate path syntax**: absolute paths, `..`, special characters/paths per provider.
5. **Use lexical `normalize()` as a secondary step**: helpful, but never treat it as a sandbox.
6. **If the entry exists**, use `toRealPath()` to verify real containment per policy where appropriate.
7. **Address races**: do not assume check-then-open is atomic; use `SecureDirectoryStream`/handle access or appropriate isolation.
8. **For new file creation**, protect parents, use `CREATE_NEW` when overwrites are unwanted, and avoid following links arbitrarily.
9. **Do not give the process excessive OS privileges**: even if a traversal bug occurs, access scope should remain limited.
10. **Test negative cases too**: `../`, absolute paths, similar root prefixes, symlink at final file, symlink at ancestor, broken links, replace-during-open, permission denied.
11. **Manage fallbacks**: if the filesystem lacks required security primitives, return an error instead of silently downgrading.
12. **Evaluate application authorization**: a file inside the root does not prove the caller is authorized to view its contents.

## 14. Common Mistakes and Fixes

**Mistake 1 — Equating `normalize()` with canonicalization.** `normalize()` only transforms syntax; it does not follow symbolic links. Use `toRealPath()` to find the real target **at check time**, while still accounting for races.

**Mistake 2 — Checking `startsWith(root)` on a lexical path and opening arbitrarily.** A symlink inside the root can point outside. You need a policy and a safe resolve/open mechanism.

**Mistake 3 — Using `String.startsWith(rootString)`.** Text prefixes lack component boundaries, easily accepting `data-secret` when the root is `data`. Use `Path.startsWith(Path)` properly.

**Mistake 4 — Calling `isSymbolicLink` only on the final file.** A symlink can reside in any ancestor. With a no-symlink policy, control every traversal step and mitigate TOCTOU.

**Mistake 5 — Thinking `NOFOLLOW_LINKS` on the final file blocks all symlinks.** It does not automatically prevent ancestor symlinks. You need safe directory-relative traversal control.

**Mistake 6 — Checking `realPath` and then reopening by an unprotected name.** An attacker can swap a symlink between check and use. Prefer directory/file-handle operations and filesystem permissions.

**Mistake 7 — Treating every `toRealPath` failure as proof the target “does not exist and is therefore safe”.** Failures can stem from broken symlinks, permissions, or link cycles. Never fail open.

**Mistake 8 — Allowing user-supplied absolute paths.** `root.resolve(userInput)` with an absolute path can lead to unintended locations. Reject absolute inputs and check policy before use.

**Mistake 9 — Believing a file in the trusted root is automatically readable.** Per-user and per-data authorization is still required.

**Mistake 10 — Relying on `SecureDirectoryStream` without checking support.** Not every provider supports it; applications with strong requirements should fail closed when needed primitives are missing.

## 15. Self-Check

1. Does `Path.normalize()` automatically read symbolic links? **No**. It processes name components syntactically.
2. Does `toAbsolutePath().normalize()` verify that a file exists? **No**.
3. How does `toRealPath()` handle symbolic links by default? **It follows symlinks** to find the real path of an existing entry, according to provider semantics.
4. Does `candidate.normalize().startsWith(root.normalize())` returning true guarantee opening will not escape the root? **No**.
5. Why should you use `Path.startsWith` instead of `String.startsWith`? Because it compares **path components**, not just text prefixes.
6. Does `Files.isSymbolicLink(candidate)` returning false mean no parent is a symlink? **No**.
7. Does `NOFOLLOW_LINKS` on the final file automatically block links in parents? **Not guaranteed**.
8. Does calling `toRealPath()` before `Files.readAllBytes()` eliminate races when directory entries are replaced? **Not completely**; that is TOCTOU.
9. Can a non-existent file succeed with `toRealPath()` for checking? **Usually no**; you need a safe file-creation strategy based on parents.
10. Is `SecureDirectoryStream` always provided by every filesystem? **No**.
11. Should a symlink `trusted/latest -> trusted/v2` be allowed or not? **Depends on policy**: allow internal links or forbid all symlinks.
12. Does a file inside a policy-compliant root prove the user is authorized to view it? **No**; authorization must be checked.
13. If sensitive data must be protected even when path logic has a bug, what external layers outside Java help? **Least-privilege OS permissions, root ownership, sandbox/container/mount policies**, and data isolation.
14. Which model is better when an attacker can modify directories between check and open? **Safe handle/directory-relative operations with per-component no-follow**, combined with a clear policy.

**Remember:** `Path.normalize()` removes redundant name components, but it **does not know where symbolic links point**. To verify an existing target, understand `toRealPath()` and containment on real paths. To prevent paths from being swapped between check and open, you need mechanisms like `SecureDirectoryStream` when supported by the provider, together with filesystem permissions and trusted ownership management. **Never treat a syntactic normalization call as the security boundary of your application.**