# POSIX Permissions and PosixFileAttributeView in Java NIO.2

A Java application handling files may need to read current permissions, restrict who can read/write a file containing private data, or grant execute permission to a script. On filesystems supporting **POSIX file attributes**, Java NIO.2 provides `PosixFilePermission`, `PosixFilePermissions`, `PosixFileAttributes`, and **`PosixFileAttributeView`** to manipulate these attributes using typed APIs instead of assembling `chmod` shell commands.

However, not every operating system or filesystem supports the POSIX view. Even when available, effective access rights can still be affected by owner, group, ACLs, parent directory permissions, and system security mechanisms. This lesson shows how to **detect support**, **read/write permissions with the proper API**, **handle errors**, and avoid creating access-control vulnerabilities.

## 1. What Are POSIX Permissions?

Basic POSIX-style permissions describe three user groups and three permission types:

- **Owner (`u`):** the owner of the file or directory.
- **Group (`g`):** members of the owning group.
- **Others (`o`):** entities not belonging to either of the two cases above per the system's classification mechanism.
- **Read (`r`):** read permission.
- **Write (`w`):** write permission.
- **Execute (`x`):** execute permission, or directory search/traversal permission depending on the object type.

A common permission string is:

~~~text
rwxr-x---
│││││││││
││││││└┴┴─ others: --- (no r/w/x)
│││└┴┴──── group:  r-x (read + execute)
└┴┴──────── owner:  rwx (read + write + execute)
~~~

The string above has **exactly 9 characters**: the first three for owner, the next three for group, and the last three for others.

Common examples:

| Character Form | Familiar Octal Form | Meaning |
|---|---|---|
| `rw-------` | `0600` | Owner read/write; group and others have no permissions |
| `rw-r-----` | `0640` | Owner read/write; group read-only; others have no permissions |
| `rw-r--r--` | `0644` | Owner read/write; group and others read-only |
| `rwx------` | `0700` | Owner read/write/execute; the other two groups have no permissions |
| `rwxr-x---` | `0750` | Owner full; group read/execute; others have no permissions |
| `rwxr-xr-x` | `0755` | Owner full; group and others read/execute |

Numeric convention: `r = 4`, `w = 2`, `x = 1` within each group; e.g., `rwx = 7`, `r-x = 5`, `--- = 0`. The `PosixFilePermissions.fromString` API takes a **9-character** string, not a string like `"0755"` directly.

### Permissions on Files and Directories Have Different Meanings

| Permission | Regular File | Directory |
|---|---|---|
| `r` | Allows reading file data per system policy | Usually allows listing entry names inside |
| `w` | Allows modifying file content per system policy | Together with `x`, usually allows creating/deleting/renaming entries in the directory |
| `x` | Allows executing the file if format and system support it | Allows **search/traverse**: traversing through the directory to access entries by name |

A file with read permission **does not guarantee** you can open it by full path if traversal permission is missing on a parent directory. Conversely, permission to delete a file is usually governed by **permissions on its containing directory**, not simply by the file's `w` bit.

The table only explains the three basic permission bit triplets. Other mechanisms such as ACLs, sticky bit, setuid/setgid, mount options, and system security policies can cause effective permissions to differ from what these nine characters imply.

## 2. Related Java Classes and Interfaces

Main types in `java.nio.file.attribute`:

| API | Responsibility |
|---|---|
| `PosixFilePermission` | Enum containing 9 permission values for owner, group, others |
| `PosixFilePermissions` | Converts between strings like `rw-r-----` and `Set<PosixFilePermission>`; creates `FileAttribute` to supply permissions at file creation time |
| `PosixFileAttributes` | Bundles POSIX-style file info: `permissions()`, `owner()`, `group()`, plus inherited basic attributes |
| `PosixFileAttributeView` | View to **read and modify** POSIX attributes of a specific file object |
| `Files.getPosixFilePermissions` | Utility method to read the permission set |
| `Files.setPosixFilePermissions` | Utility method to write the permission set |
| `Files.getFileAttributeView` | Obtains a view object if the provider supports the corresponding view type |

`PosixFilePermission` includes the constants:

~~~java
OWNER_READ
OWNER_WRITE
OWNER_EXECUTE
GROUP_READ
GROUP_WRITE
GROUP_EXECUTE
OTHERS_READ
OTHERS_WRITE
OTHERS_EXECUTE
~~~

The names above are **enum constants**, not standalone variables. When used in Java, they must be qualified by the type or static-imported, e.g., `PosixFilePermission.OWNER_READ`.

Mechanism via view:

~~~text
Path --------------------------> Files.getFileAttributeView(...)
                                      |
                                      v
                              PosixFileAttributeView
                                |       |       |
                                |       |       +-- setGroup(...)
                                |       +---------- setPermissions(...)
                                +------------------ readAttributes()
                                      |
                                      v
                              PosixFileAttributes
                               owner / group / permissions
~~~

A view is **an object for accessing attributes of a path**, not a copy of file contents. When calling `readAttributes()`, the program asks the filesystem to supply an attribute set at read time.

## 3. Converting Permission Strings with `PosixFilePermissions`

Declaring a permission set from a string:

~~~java
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-r-----");
System.out.println(PosixFilePermissions.toString(permissions));
// rw-r-----
~~~

This is an **illustrative snippet** that can be placed inside `main`; it only converts data in memory and **does not change permissions of any file**.

You can also construct the permission set directly:

~~~java
Set<PosixFilePermission> privateReadWrite = Set.of(
        PosixFilePermission.OWNER_READ,
        PosixFilePermission.OWNER_WRITE);
~~~

The `Set` above contains only the two owner permissions, corresponding to `rw-------`. Both representations are equivalent regarding **the nine basic permission bits**.

Invalid examples:

~~~java
// Invalid for fromString: must have exactly 9 rwx/- characters.
PosixFilePermissions.fromString("0644");
PosixFilePermissions.fromString("rwx");
~~~

These are **error-illustration lines** and should not be put into a runnable program. `fromString` throws `IllegalArgumentException` when the string has an invalid structure or characters.

Do not confuse `PosixFilePermissions.toString(permissions)` with `permissions.toString()` from `Set`: one produces the familiar 9-character Unix permission string; the other is just Java's enum-set string representation.

## 4. Checking Whether the System Supports POSIX

`PosixFileAttributeView` is only available when **the file system provider** supports it. Code that runs fine on Linux with a POSIX-supporting filesystem may not work the same way on a default Windows provider or on a specialized filesystem.

Direct check for a path:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;

PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);

if (view == null) {
    System.out.println("Không có POSIX attribute view.");
} else {
    System.out.println("Có thể thử đọc thuộc tính POSIX.");
}
~~~

This is an **illustrative snippet**; `path` must have a valid value. When the provider **does not support** the requested view, `getFileAttributeView` returns `null`. Obtaining a view **does not guarantee** that subsequent permission reads or updates will always succeed: the file could disappear, permissions could be denied, or the provider could encounter an I/O error.

Check capability at the filesystem store level:

~~~java
boolean supported = Files.getFileStore(path)
        .supportsFileAttributeView("posix");
~~~

`IOException` must be handled when accessing the file store. For real operations on a file, obtaining the view directly at the path and handling errors at the read/write step is usually clearer.

**Important portability note:** Do not interpret a filename or operating system as a guarantee of a POSIX view. Custom filesystem providers, network drives, ZIP files, or different filesystem configurations can have support levels differing from the underlying OS.

## 5. Reading Permissions with `Files` or `PosixFileAttributeView`

### Short Way: `Files.getPosixFilePermissions`

~~~java
Set<PosixFilePermission> current =
        Files.getPosixFilePermissions(path);

System.out.println(PosixFilePermissions.toString(current));
~~~

This is an **illustrative snippet** requiring imports for `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.attribute.*`, `java.util.Set`, and `IOException` handling. `Files.getPosixFilePermissions(path)` may throw `UnsupportedOperationException` if the provider does not support POSIX attributes.

### View Way: `readAttributes()`

~~~java
PosixFileAttributeView view =
        Files.getFileAttributeView(path, PosixFileAttributeView.class);

if (view != null) {
    PosixFileAttributes attrs = view.readAttributes();
    Set<PosixFilePermission> permissions = attrs.permissions();
    System.out.println(PosixFilePermissions.toString(permissions));
    System.out.println("Owner: " + attrs.owner().getName());
    System.out.println("Group: " + attrs.group().getName());
}
~~~

This is an **illustrative snippet**. `readAttributes()` returns a `PosixFileAttributes` object, where `owner()` and `group()` are `UserPrincipal` and `GroupPrincipal` objects, not numeric UIDs/GIDs guaranteed by Java across all providers.

The advantage of a view is reading multiple related attributes at once instead of calling separate methods repeatedly. However, do not treat an attribute snapshot as a file lock: attributes can change after being read.

## 6. Writing Permissions: `Files.setPosixFilePermissions` and `view.setPermissions`

When you want to set basic permissions for a file **owned/managed by the application**, you can call:

~~~java
Set<PosixFilePermission> restricted =
        PosixFilePermissions.fromString("rw-------");

Files.setPosixFilePermissions(path, restricted);
~~~

Or via the view:

~~~java
PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);

if (view == null) {
    throw new UnsupportedOperationException("Không hỗ trợ POSIX");
}
view.setPermissions(restricted);
~~~

The snippets above must be placed in a method with imports and `IOException` handling. `setPermissions` updates the file's **nine basic permission bits**, not an abstract permission mechanism that behaves identically on every system.

Points to understand:

1. `Set<PosixFilePermission>` is the desired permission set, not an instruction to "add individual permissions to the existing set" by default.
2. If you pass a set containing only `OWNER_READ`, all other permission bits in the basic POSIX model can be **removed**. Check your application's requirements before updating.
3. To **add exactly one bit** while keeping the others, you must read the current permissions, create a mutable set, add the corresponding enum, and write it back. This is a read–modify–write sequence that can suffer races when multiple processes update permissions concurrently.
4. Only modify permissions on objects you are authorized to manage; the system may throw `IOException` or `SecurityException` depending on the provider and environment.
5. Do not unconditionally call `setPosixFilePermissions` on Windows/unsupported native providers: `UnsupportedOperationException` is an outcome that must be handled.
6. Setting permissions modifies metadata of an existing object, not file contents; however, it can directly affect other processes' access capabilities.

### Adding a Permission Without Removing Others

~~~java
Set<PosixFilePermission> updated = new HashSet<>(
        Files.getPosixFilePermissions(path));

updated.add(PosixFilePermission.GROUP_READ);
Files.setPosixFilePermissions(path, updated);
~~~

This is an **illustrative snippet** with imports for `java.util.HashSet`, `java.nio.file.*`, and `java.nio.file.attribute.*`. If a program is only testing permission changes as an exercise, use **a temporary file you created yourself**, not configuration files or someone else's real data.

### Setting Owner/Group Is Not the Same as Setting Permissions

`PosixFileAttributeView` also has methods such as `setGroup(GroupPrincipal)` and inherits owner-changing capability via `setOwner(UserPrincipal)`. Changing owner or group usually requires special privileges; you cannot infer that being able to change permissions means you can definitely change owner/group.

**Owner, group, and permission bits are related yet independent attributes.** Changing owner/group can alter effective access rights even when the `rwxr-x---` string does not change.

## 7. Complete Java 17 Example: Changing Permissions Only on a Temporary File

The following program creates **a temporary file**, checks `PosixFileAttributeView`, sets `rw-------` if the view is available, and reads back to verify. It does not touch permissions of any real user file.

Save as **`PosixPermissionsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixPermissionsDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("posix-demo-", ".txt");

        try {
            PosixFileAttributeView view = Files.getFileAttributeView(
                    file, PosixFileAttributeView.class,
                    LinkOption.NOFOLLOW_LINKS);

            if (view == null) {
                System.out.println("POSIX view available: false");
            } else {
                System.out.println("POSIX view available: true");

                Set<PosixFilePermission> requested =
                        PosixFilePermissions.fromString("rw-------");
                view.setPermissions(requested);

                PosixFileAttributes attrs = view.readAttributes();
                System.out.println("Requested: "
                        + PosixFilePermissions.toString(requested));
                System.out.println("Read back: "
                        + PosixFilePermissions.toString(attrs.permissions()));
                System.out.println("Exact match: "
                        + attrs.permissions().equals(requested));

                Set<PosixFilePermission> viaFiles =
                        Files.getPosixFilePermissions(file);
                System.out.println("Files getter agrees: "
                        + viaFiles.equals(attrs.permissions()));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 PosixPermissionsDemo.java
java PosixPermissionsDemo
~~~

On a standard POSIX-supporting filesystem, when the runner has permission to modify permissions and the provider accepts the request, expected output is:

~~~text
POSIX view available: true
Requested: rw-------
Read back: rw-------
Exact match: true
Files getter agrees: true
~~~

If the provider **does not support** `PosixFileAttributeView`, the program prints:

~~~text
POSIX view available: false
~~~

Permission errors, I/O errors, or special filesystems may cause the program to throw an exception instead of printing all lines of the supported branch. That behavior must be handled in real applications; it should not be hidden by silently ignoring security issues.

**Explanation:**

1. `Files.createTempFile` creates a new file and returns a path to it. The example only modifies permissions on this new file.
2. `Files.getFileAttributeView(file, PosixFileAttributeView.class, NOFOLLOW_LINKS)` requests the view to operate on **the path itself** without following symbolic links during attribute lookup. Because the file just created by the program is a regular file, no symlink branch is involved.
3. If the view is absent, the program **does not attempt to call `setPermissions`**.
4. If present, `fromString("rw-------")` creates a set containing exactly `OWNER_READ` and `OWNER_WRITE`, and `view.setPermissions` requests the permission update.
5. `view.readAttributes().permissions()` reads back the permission set, converts it to a string, and compares via `Set.equals`.
6. `Files.getPosixFilePermissions(file)` is the utility method for reading POSIX permissions. On a file not modified concurrently in the example, the result matches the view.
7. The `finally` block deletes the temporary file whether the processing branch succeeds or throws an exception. If deleting the file also fails, Java may report an `IOException` for the cleanup step; this is a factor to monitor in production code.

**Testing note:** the program only verifies that the provider **reports having stored the requested permission bits**. It does not test actual user/group access behavior, and does not guarantee every system enforces access control identically.

## 8. `PosixFileAttributeView` and Symbolic Links

A symbolic link is a filesystem entry pointing to another entry. If `link` is a symlink pointing to `target`, you must decide whether you want to manipulate attributes of **the target** or **the link itself**.

By default, many `Files` calls read attributes **following symbolic links** to the target. `LinkOption.NOFOLLOW_LINKS` lets you request **not following links**:

~~~java
PosixFileAttributeView noFollowView = Files.getFileAttributeView(
        link,
        PosixFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);
~~~

This is an **illustrative snippet**, where `link` is an existing `Path`. Some filesystems **do not allow reading/changing permissions of a symlink itself in the same way as a target file**; do not infer that `NOFOLLOW_LINKS` makes all `setPermissions` operations on symlinks supported.

If you do not intend to change permissions of **the target file**, define your link policy before calling. This is a security issue: someone else could replace the link between the time the application checks the path and when it changes permissions or opens the file (**time-of-check/time-of-use**). `NOFOLLOW_LINKS` at one step does not automatically eliminate races at other steps.

When handling paths supplied by untrusted users, define allowed root directories, access permissions, and safe file-opening strategies at the platform level. **Do not turn permission modification into an automatic "fix all access errors" mechanism**.

## 9. Initial Permissions at File Creation and `umask`

A common issue is creating a file first and only afterward calling `setPosixFilePermissions`. If sensitive data is written before tightening permissions, there can be a window where the file has broader permissions than intended.

When the provider supports POSIX, Java allows specifying permissions **right in the creation operation** via `FileAttribute`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

FileAttribute<Set<PosixFilePermission>> privateFile =
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rw-------"));

Path newFile = Files.createFile(path, privateFile);
~~~

This is an **illustrative snippet**; `path` must point to a file that does not yet exist and the caller handles `IOException`. This option is useful when **security at creation time** is required. If the file already exists, `Files.createFile` does not overwrite it and instead fails.

Similarly, `Files.createTempFile` has an overload accepting file attributes, and `asFileAttribute` can be used per your policy. However:

- Creating a file with POSIX attributes on an unsupported provider can fail.
- Actual permissions upon creation may be restricted by filesystem policy and the environment's **umask**; re-read attributes if the application requires verification.
- Specifying permissions at creation does not replace checking owner/group, ACLs, parent directory permissions, or other sensitive-data protections.
- Do not write passwords/private data into a "default-permission temporary file", tighten permissions only at the last step, and assume there was no window of exposure.

**Umask** is a POSIX mechanism commonly used to mask off requested permission bits at creation time. For example, umask `022` can cause newly created files to receive fewer permissions than a broader request. Do not treat umask as an attribute that `PosixFilePermission` automatically models inside its 9-enum set.

## 10. POSIX Permissions, ACLs, and Effective Access Rights

The nine `rwxrwxrwx` bits are only the basic model. An application may encounter:

- **POSIX ACLs:** additional/overriding permission entries per user or group, depending on the filesystem and effective permission evaluation.
- **Windows ACLs:** a different permission model, which should not be forced into a 9-character string as if complete.
- **Sticky bit** on certain directories; **setuid/setgid** on files or directories; not represented within the nine values of `Set<PosixFilePermission>` itself.
- **Root/superuser privileges**, capabilities, or mandatory security policies that affect opening, reading, modifying, or deleting.
- **Parent directory attributes** and mount state (e.g., read-only filesystem) affecting operations even if the file is `rw-------`.
- **Caching and concurrent modifications** causing previously read attributes to no longer reflect state at time of use.

On providers supporting `AclFileAttributeView`, other APIs can inspect ACL information. Do not conclude "no permission" or "definitely has permission" from a single check while ignoring errors when actually opening or writing data.

`Files.isReadable(path)`, `Files.isWritable(path)`, and `Files.isExecutable(path)` are convenience checks, not immutable security barriers; the file or its permissions can change immediately after checking. Prefer attempting the real operation inside business-appropriate error handling rather than relying solely on pre-checks.

## 11. Error Handling and Portability in Real Applications

| Scenario | Likely Outcome | Proper Response |
|---|---|---|
| POSIX view unavailable | `getFileAttributeView` returns `null` | Avoid dereferencing; take a compatible branch or report unsupported |
| Accessing POSIX attributes via `Files` API on unsupported provider | `UnsupportedOperationException` | Do not force permission edits; use the provider's supported mechanism |
| File missing or deleted concurrently | `IOException`, e.g., `NoSuchFileException` | Report error or perform controlled retry |
| Lacking permission to read/edit attributes | `IOException` or `SecurityException` depending on environment | Clearly report permission issue; do not recklessly broaden permissions |
| Malformed permission string | `IllegalArgumentException` from `fromString` | Validate exact 9 characters using only `rwx-` |
| Operating on a symlink | May follow or not follow link depending on options | Explicitly determine whether the target file or link should be modified |
| `FileStore` has view but path fails | Specific attribute errors can still occur | Execute operation inside `try/catch` and handle real errors |
| Changing permissions across two processes | Updates may be lost in read–modify–write sequence | Coordinate when the application has concurrent writers |

Helper pattern checking the view before reading:

~~~java
static String permissionText(Path file) throws IOException {
    PosixFileAttributeView view = Files.getFileAttributeView(
            file, PosixFileAttributeView.class);
    if (view == null) {
        throw new UnsupportedOperationException(
                "POSIX attributes are unavailable for " + file);
    }
    return PosixFilePermissions.toString(
            view.readAttributes().permissions());
}
~~~

This is an **illustrative method** in a Java class with imports `java.io.IOException`, `java.nio.file.*`, `java.nio.file.attribute.*`. The caller receives a 9-character string on success; otherwise, the error is surfaced distinctly instead of returning a fake value like `rwxrwxrwx`.

A cross-platform system can provide an **application-level abstraction**: if POSIX is available, use the permission view; if not, choose the provider's appropriate permission API or halt with a clear message. Never silently turn a file-protection requirement into "skip setting permissions" on an unsupported platform if that security level is mandatory.

## 12. Common Mistakes

| Misconception | Consequence | Correct Approach |
|---|---|---|
| Assuming `PosixFileAttributeView` exists on every machine running Java | `null`/unsupported on incompatible providers | Check support and provide an alternative strategy |
| Passing `"755"` to `fromString` | Invalid API format | Use `"rwxr-xr-x"` |
| Thinking `getPosixFilePermissions` modifies permissions | Only reads metadata | Use `setPosixFilePermissions` or `view.setPermissions` |
| Thinking `setPermissions` means "add new permissions" | Can wipe out bits omitted from the new set | Build the full permission set before setting |
| Setting `rwxrwxrwx` to "fix access denied errors" | Dangerously broad permissions, may not even solve the error | Check owner/group, parent directories, ACLs, and actual requirements |
| Treating directory `r` as permission to traverse the directory | On POSIX, traversing by name usually requires `x` | Distinguish `r/w/x` meanings for files vs. directories |
| Forgetting symlink policy | Modifying the wrong file's permissions | Choose follow/nofollow appropriately and guard against races |
| Believing view availability guarantees `set` will succeed | Permission changes can still be forbidden | Catch I/O errors and do not guess |
| Writing secrets first and tightening permissions later | Exposure window with broad permissions | Specify attributes at creation time when needed |
| Believing 9 bits fully describe effective permissions | ACLs and system mechanisms also apply | Combine actual checks and policies |
| Failing to distinguish file permissions from parent directory permissions | Access may fail even if file has `r/w` | Inspect path and directory traversal |
| Catching and silencing all errors | Application falsely believes data is protected | Report errors and stop if security is mandatory |

## 13. Self-Check Questions

**Question 1.** What does the string `rw-r-----` mean? What is its octal equivalent?

> Owner can read and write, group can only read, others have no permissions. That corresponds to `0640` in familiar octal notation.

**Question 2.** Why can `Files.getFileAttributeView(file, PosixFileAttributeView.class)` return `null`?

> Because the file's filesystem provider does not support the POSIX view. You must check the result before calling `readAttributes` or `setPermissions`.

**Question 3.** Which method reads current permissions from `PosixFileAttributes`? What is used to change permissions?

> Use `view.readAttributes().permissions()` to get the permission set. To change permissions, use `view.setPermissions(set)` or `Files.setPosixFilePermissions(file, set)`.

**Question 4.** A file currently has `rw-r-----`. If you call `setPermissions(fromString("rw-------"))`, is `GROUP_READ` still present?

> **No** in the basic nine-permission set: the new set specifies only owner read/write. `GROUP_READ` is no longer in the applied set.

**Question 5.** When creating a secret file, why is passing `PosixFilePermissions.asFileAttribute` to `Files.createFile` better than adjusting permissions after writing data?

> Because appropriate permissions can be requested **right at creation time**, avoiding the gap between creation/writing and tightening permissions. You still must account for provider, umask, ACLs, and system policies.

**Question 6.** In a directory, you have `r` permission but lack `x`. Is the application guaranteed to open a child file by filename path?

> No. `x` permission on a directory is typically needed for traversing/looking up entries by name. Directory `r` does not replace `x`.

**Question 7.** Does `NOFOLLOW_LINKS` make every operating system allow changing permissions of a symbolic link?

> No. It only requests not following the symbolic link during attribute access; whether metadata of the link itself can be read/modified still depends on the provider/filesystem.

**Question 8.** Having `rw-------` on a file—does that guarantee the application can write to the file in every situation?

> No. Effective permissions also depend on process identity, parent directory permissions, ACLs, filesystem state, mount policies, and concurrent changes. Errors must be handled when performing I/O.

## Key Takeaways

- **`PosixFilePermission`** is the enum for the nine owner/group/others × read/write/execute permissions.
- **`PosixFilePermissions`** converts between `"rwxr-x---"` and `Set<PosixFilePermission>`, or supplies attributes at file creation time.
- **`PosixFileAttributeView`** enables reading POSIX attributes and updating permissions, owner, and group when supported by the system and permitted for the caller.
- **`Files.getPosixFilePermissions` / `Files.setPosixFilePermissions`** are two utility methods for common operations.
- **Never assume POSIX is always available**; check the view, handle `IOException` / `UnsupportedOperationException`, and respect provider capabilities.
- **Nine permission bits are not the entire security model**. Understand file/directory permissions, ACLs, symbolic links, umask, and environment privileges before acting.

**References:** [Java SE 17 — `PosixFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html), [`PosixFilePermission`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermission.html), [`PosixFilePermissions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html), [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
