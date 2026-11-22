# DOS Attributes on Windows in Java NIO.2

On Windows, files and directories have a familiar group of attribute flags: **Read-only**, **Hidden**, **System**, and **Archive**. Java NIO.2 provides the `DosFileAttributes` and `DosFileAttributeView` interfaces to read and modify these flags on filesystems that support them, commonly seen on FAT/NTFS formats on Windows.

Key point: **DOS attributes are filesystem metadata, not file content, not filename extensions, and not equivalent to full Windows ACL or POSIX access permissions**. A file with the `hidden` flag can still be read if a program has permission; a file with `readonly` does not automatically mean "nobody can edit or delete it" in every scenario.

This lesson uses Java 17+, presenting how to read/modify flags using strongly typed APIs or string attribute names, how to detect unsupported providers, common errors, symbolic links, and safe examples creating temporary files.

## 1. The Four DOS Attributes to Remember

| Attribute | In Java | Common Meaning | What **Not** to Infer |
|---|---|---|---|
| **Read-only** | `isReadOnly()` / `setReadOnly(boolean)` | Marks the file as DOS-style read-only | Not equivalent to full ACL permission policy, not a guarantee of immutability |
| **Hidden** | `isHidden()` / `setHidden(boolean)` | Marks the entry to be hidden from normal display interfaces | Not encryption, not access control |
| **System** | `isSystem()` / `setSystem(boolean)` | Marks the entry as system-related | Does not make the file a valid operating system component |
| **Archive** | `isArchive()` / `setArchive(boolean)` | Suggests a state indicating archiving/backup may be needed | Does not guarantee a backup has occurred or will occur |

Flags can be combined. A file can be both `hidden` and `readonly`; updating one flag does not mean all remaining flags must be reset.

Java only provides the access model for these flags. **Support availability and enforcement level** are still determined by the file-system provider, operating system, storage drive type, and process privileges.

### Comparing with File Explorer

On Windows, these attributes are commonly seen in File Explorer's **Properties** dialog or via the `attrib` command-line tool. However, certain flags like System/Archive are not necessarily presented the same way as Read-only/Hidden in simple UI dialogs, and how File Explorer handles directories may differ from files.

Do not replace reading metadata from Java with guesses based on Explorer UI, leading dots in names, or file extensions.

## 2. Two Core Interfaces

Both reside in the package:

~~~java
import java.nio.file.attribute.DosFileAttributes;
import java.nio.file.attribute.DosFileAttributeView;
~~~

### `DosFileAttributes`: Attribute Snapshot for **Reading**

`DosFileAttributes` extends `BasicFileAttributes`. In addition to its four specific methods `isReadOnly()`, `isHidden()`, `isSystem()`, and `isArchive()`, it also has the basic methods:

- `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `isOther()`.
- `size()` for the size reported by the provider (bytes for regular files).
- `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`.
- `fileKey()` if the provider supplies an identifier key.

A `DosFileAttributes` object is **a read result at a point in time**; it does not auto-update when someone changes flags afterward. To get the latest state, call `Files.readAttributes(...)` or `view.readAttributes()` again.

### `DosFileAttributeView`: Interface for **Reading and Updating**

`DosFileAttributeView` extends `BasicFileAttributeView` and provides the methods:

~~~java
DosFileAttributes readAttributes() throws IOException;
void setReadOnly(boolean value) throws IOException;
void setHidden(boolean value) throws IOException;
void setSystem(boolean value) throws IOException;
void setArchive(boolean value) throws IOException;
~~~

These are **illustrative signatures**; using them requires a `DosFileAttributeView` bound to a `Path`. This view's name per the Javadoc is `"dos"`, used in dynamic access calls such as `"dos:hidden"`.

Note: not every flag update is an atomic operation with respect to other filesystem activities. The `DosFileAttributeView` documentation permits implementations to read existing flags first before updating; scenarios where multiple processes modify attributes concurrently must be designed and tested separately.

## 3. Reading DOS Attributes with Typed APIs

There are two main approaches.

### Approach A: `Files.readAttributes`

~~~java
// Illustrative snippet: path is the Path of the entry to read.
DosFileAttributes attrs =
        Files.readAttributes(path, DosFileAttributes.class);

boolean readOnly = attrs.isReadOnly();
boolean hidden = attrs.isHidden();
boolean system = attrs.isSystem();
boolean archive = attrs.isArchive();
~~~

If the filesystem does not support the requested attribute type, `readAttributes(path, DosFileAttributes.class)` can throw `UnsupportedOperationException`. Path access errors can produce `IOException`; security policies can produce `SecurityException`.

### Approach B: `Files.getFileAttributeView`

~~~java
// Illustrative snippet: path is a valid Path.
DosFileAttributeView view =
        Files.getFileAttributeView(path, DosFileAttributeView.class);

if (view == null) {
    // The provider does not supply this view.
} else {
    DosFileAttributes attrs = view.readAttributes();
    System.out.println(attrs.isHidden());
}
~~~

`Files.getFileAttributeView(...)` returns `null` when the view type is unavailable. This is a convenient path if you want to **check support before reading or updating**.

**Do not confuse:** obtaining a view does not guarantee every read/write operation will definitely succeed: the file may no longer exist, permissions may be insufficient, the drive may fail, or the provider may reject the operation. When using a view, `IOException` must still be handled.

## 4. Detecting Support Instead of Checking Operating System Name

You should not write a rule like:

~~~java
// Snippet that should NOT be used to determine DOS view capability.
boolean supported =
        System.getProperty("os.name").contains("Windows");
~~~

The OS name does not fully reflect the features of **the filesystem where `Path` resides**. The same Windows machine can access network drives, ZIP filesystems, or other providers; a `FileSystem` provider on another platform might also provide the DOS model.

APIs for detecting support:

~~~java
// Illustrative snippet.
boolean providerAdvertises =
        path.getFileSystem()
                .supportedFileAttributeViews().contains("dos");

boolean storeSupports =
        Files.getFileStore(path)
                .supportsFileAttributeView(DosFileAttributeView.class);

DosFileAttributeView view =
        Files.getFileAttributeView(path, DosFileAttributeView.class);
boolean viewAvailable = view != null;
~~~

Differences:

- `supportedFileAttributeViews()` is the set of view names advertised by the **FileSystem**; it may not fully describe restrictions specific to an individual file store.
- `FileStore.supportsFileAttributeView(...)` queries **the file store**; even when reported as supported, environment- or resource-specific errors can still occur. With the default provider, results on non-local storage devices can have accuracy limitations per Javadoc.
- `getFileAttributeView(...)` obtains a view object for `Path`; if absent it returns `null`, yet only the actual operation afterward confirms access succeeds.
- `Files.getFileStore(path)` can also throw `IOException` if the file store cannot be located.

A solid practice is **obtaining the view and checking for `null`, then handling errors upon use**. If the program runs cross-platform, explicitly define the branch when the DOS view is unsupported instead of casting or attempting attribute access at all costs.

## 5. Java 17+ Example: Reading Flags on a Temp File and Detecting Unsupported Systems

Create the file **`DosFlagsProbe.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.DosFileAttributes;

public class DosFlagsProbe {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("dos-probe-", ".txt");

        try {
            DosFileAttributeView view =
                    Files.getFileAttributeView(
                            file, DosFileAttributeView.class);

            if (view == null) {
                System.out.println("dosView=unsupported");
            } else {
                DosFileAttributes attrs = view.readAttributes();

                System.out.println("dosView=available");
                System.out.println("regularFile=" + attrs.isRegularFile());
                System.out.println("readonly=" + attrs.isReadOnly());
                System.out.println("hidden=" + attrs.isHidden());
                System.out.println("system=" + attrs.isSystem());
                System.out.println("archive=" + attrs.isArchive());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 DosFlagsProbe.java
java DosFlagsProbe
~~~

If the provider **does not support** it:

~~~text
dosView=unsupported
~~~

If the provider supports it and reading succeeds, output looks like:

~~~text
dosView=available
regularFile=true
readonly=<boolean>
hidden=<boolean>
system=<boolean>
archive=<boolean>
~~~

In the block above, `<boolean>` is an **explanatory placeholder**, not fixed stdout: Java actually prints `true` or `false`. Initial flag values depend on the filesystem and how the file was created; therefore **do not invent a single set of values for every machine**. This example is designed to select its branch automatically depending on the environment.

The file is created with `Files.createTempFile` and deleted in `finally`. If permission/device read errors occur, the program can throw `IOException` — which is normal behavior for filesystem access tasks.

## 6. Updating the Four Flags with DosFileAttributeView

After confirming the view is available, use the setters:

~~~java
// Illustrative snippet affecting a real file: requires permissions and clear policy.
view.setReadOnly(true);  // Enable Read-only flag.
view.setHidden(true);    // Enable Hidden flag.
view.setArchive(true);   // Enable Archive flag.
view.setSystem(true);    // Enable System flag.
~~~

Pass `false` to clear the corresponding flag. However, **do not enable System or Read-only arbitrarily on real files**: other applications may depend on these flags; depending on the platform, deleting/editing the file can be denied once read-only is enabled. Moreover, "System=true" does **not** mean the operating system recognizes the file as a valid system component.

When operating on real data:

1. Read the prior state to decide whether a change is needed.
2. Verify the program has permission and actually owns the resource.
3. Modify **only the desired flag**.
4. Re-read attributes to verify the result.
5. Handle `IOException`/`SecurityException` and avoid infinite retries.
6. If the change is only temporary, restore the original state upon completion.

Do not use `Files.setAttribute(...)` or view setters to experiment directly on system configuration files, the Windows directory, or user data without authorization.

## 7. Java 17+ Example: Toggling Hidden on a Temp File and Restoring

Create the file **`DosHiddenRoundTrip.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;

public class DosHiddenRoundTrip {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("dos-hidden-", ".txt");

        try {
            DosFileAttributeView view =
                    Files.getFileAttributeView(
                            file, DosFileAttributeView.class);

            if (view == null) {
                System.out.println("dosView=unsupported");
            } else {
                boolean original = view.readAttributes().isHidden();

                try {
                    view.setHidden(!original);
                    boolean updated =
                            view.readAttributes().isHidden();
                    System.out.println("changed=" + (updated != original));
                } finally {
                    // Restore the original flag on the temporary file itself.
                    view.setHidden(original);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DosHiddenRoundTrip.java
java DosHiddenRoundTrip
~~~

On an **unsupported** provider:

~~~text
dosView=unsupported
~~~

On a **supported provider where the update succeeds**:

~~~text
changed=true
~~~

If the filesystem supports the view yet forbids modifying flags, the setter call can throw `IOException`; **that is not a stable output** and must be handled according to the real application. In the example, the initial Hidden state is saved and restored in `finally`; afterward only the temp file is deleted.

Attribute changes through Java execute on the real filesystem, not merely changing a Java variable. If an application runs concurrent tasks or external actors also modify flags, this simple example does not guarantee preserving other actors' changes. For private files created by the program itself, this risk is easier to control.

## 8. Dynamic API: "dos:readonly", "dos:hidden", "dos:system", "dos:archive"

Besides typed interfaces, Java supports reading/updating attributes by view name and string attribute name:

~~~java
// Illustrative snippet; path is a Path on a DOS-supporting file system.
Object hidden = Files.getAttribute(path, "dos:hidden");
Files.setAttribute(path, "dos:hidden", Boolean.TRUE);
Files.setAttribute(path, "dos:readonly", Boolean.FALSE);
~~~

The four dynamic attribute names defined in Javadoc:

| Full Name | Type When Read | Corresponding Setter |
|---|---|---|
| `"dos:readonly"` | `Boolean` | `setReadOnly(boolean)` |
| `"dos:hidden"` | `Boolean` | `setHidden(boolean)` |
| `"dos:system"` | `Boolean` | `setSystem(boolean)` |
| `"dos:archive"` | `Boolean` | `setArchive(boolean)` |

**Note the naming:** the dynamic key is `readonly` in one lowercase word, **not** `readOnly`, `read-only`, or `ReadOnly`. Do not confuse the attribute name with the Java method name `isReadOnly()`.

Reading multiple attributes at once:

~~~java
// Illustrative snippet; requires importing java.util.Map.
Map<String, Object> flags = Files.readAttributes(
        path, "dos:readonly,hidden,system,archive");
Boolean isHidden = (Boolean) flags.get("hidden");
~~~

The map contains short keys like `"readonly"`, `"hidden"`, `"system"`, and `"archive"`, **without** requiring the `"dos:"` prefix on each key. On unsupported providers, the operation can throw `UnsupportedOperationException`; file access errors can still throw `IOException`.

When using the typed API, the compiler checks method names. The dynamic API is useful when building a general-purpose metadata viewer, but is prone to typos in names and casting errors. For the four fixed DOS flags, using `DosFileAttributes`/`DosFileAttributeView` is usually clearer.

## 9. Runnable Example: Consistency Between Typed and Dynamic APIs

Create the file **`DosAttributeApiComparison.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.DosFileAttributes;
import java.util.Map;

public class DosAttributeApiComparison {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("dos-compare-", ".txt");

        try {
            DosFileAttributeView view =
                    Files.getFileAttributeView(
                            file, DosFileAttributeView.class);

            if (view == null) {
                System.out.println("dosView=unsupported");
                return;
            }

            DosFileAttributes typed = view.readAttributes();
            Map<String, Object> dynamic = Files.readAttributes(
                    file, "dos:readonly,hidden,system,archive");

            boolean equal =
                    typed.isReadOnly() == (Boolean) dynamic.get("readonly")
                    && typed.isHidden() == (Boolean) dynamic.get("hidden")
                    && typed.isSystem() == (Boolean) dynamic.get("system")
                    && typed.isArchive() == (Boolean) dynamic.get("archive");

            System.out.println("sameFlags=" + equal);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DosAttributeApiComparison.java
java DosAttributeApiComparison
~~~

If the DOS view is unsupported:

~~~text
dosView=unsupported
~~~

If the view is supported and no actor concurrently alters attributes between the two reads:

~~~text
sameFlags=true
~~~

The two reads are performed **non-atomically**, so the result above models a temporary file not modified by external actors; if a change happens between the two reads, the comparison value could differ. The goal is to demonstrate **the four dynamic names corresponding** to the four typed getters.

## 10. DOS Attributes Differ from Windows ACL and POSIX Permissions

This is the easiest area to misunderstand when building file management software.

### DOS Read-only Does Not Replace ACLs

The `readonly` flag is commonly used as a marker to discourage updates, yet the `DosFileAttributes` Javadoc explicitly states **whether an enforcement mechanism exists to prevent modification/deletion is implementation-dependent**. On Windows, NTFS also has **ACLs** determining which accounts or groups have permissions to read, write, delete, change permissions, etc.

Therefore:

- `attrs.isReadOnly() == false` does **not** prove the process has write permission on the file.
- `attrs.isReadOnly() == true` is **not** absolute proof that the file cannot be altered in any context.
- `Files.isWritable(path)` reflects writability from the current JVM's perspective, yet also has limitations and can become stale immediately after the check.
- To read/modify ACLs, look at `AclFileAttributeView` when supported by the provider, and always apply proper OS permission policies.

Do not build access control for sensitive data solely on DOS Read-only or Hidden.

### DOS Hidden Differs from Leading-Dot Filenames on Unix

`Files.isHidden(path)` has **platform/provider-dependent** rules. Per Javadoc:

- On Windows, whether an entry is considered hidden is typically based on the **DOS hidden flag**.
- On Unix, names starting with a dot `.` are typically considered hidden.
- A file named `.secret` on Windows **does not automatically have the DOS Hidden flag just because its name starts with a dot**.
- A file with the DOS Hidden flag does not need a `.` prefix in its name.

Thus `Files.isHidden(path)` is a relatively portable API if the goal is **"does this OS consider the file hidden?"**. If the goal is **specifically reading/modifying the DOS flag**, use `DosFileAttributes.isHidden()` or `DosFileAttributeView.setHidden(...)`.

### DOS Differs from POSIX Permissions

On Unix/Linux, familiar permissions like `rwxr-x---` are managed by `PosixFilePermissions`/`PosixFileAttributeView`. They do not map one-to-one with the four DOS flags. A program designed to run on both Windows and Linux must choose an appropriate abstraction or write capability-based branches rather than assuming both models are identical.

## 11. Symlinks, NOFOLLOW_LINKS, and Target-Substitution Risks

The `Files.getFileAttributeView(...)` and `Files.readAttributes(...)` APIs accept `LinkOption...`. By default they **follow symbolic links** to the final target if the provider supports links:

~~~java
// Illustrative snippet; requires importing LinkOption.
DosFileAttributes targetAttrs = Files.readAttributes(
        link, DosFileAttributes.class);

DosFileAttributes linkAttrs = Files.readAttributes(
        link, DosFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
~~~

`NOFOLLOW_LINKS` requests examining **the link object** without following to the final target, when supported by the provider. However, there is no guarantee every provider offers a DOS view on symbolic links themselves. Some filesystems may not support reading/modifying a DOS flag on a link or may have specific rules.

Similarly for views used to modify attributes:

~~~java
// Illustrative snippet.
DosFileAttributeView linkView = Files.getFileAttributeView(
        link, DosFileAttributeView.class, LinkOption.NOFOLLOW_LINKS);
~~~

Do not treat `getFileAttributeView(..., NOFOLLOW_LINKS)` as preventing all race attacks: a link or path can change between obtaining the view and updating. In applications operating on untrusted paths, control ownership, permissions, links, and filesystem mutability.

For user-supplied paths, even a seemingly small operation like enabling Hidden is **a state change on a real resource**. Restrict permissions and only modify files managed by the application.

## 12. Flag Update Order and Consistency Issues

Suppose an application wants to enable both `hidden` and `archive`:

~~~java
// Illustrative snippet on a view with modification permissions.
view.setHidden(true);
view.setArchive(true);
~~~

These two calls **are not guaranteed to form a transaction**. Enabling Hidden could succeed while enabling Archive fails, leaving the file in a partially updated state. Furthermore, between the two calls, another thread or process could read or modify flags.

When business logic requires a consistent state:

1. Determine which attributes genuinely need modification; do not arbitrarily alter System/Archive on every file.
2. Account for the possibility that part of the operation completed.
3. Re-read state after modification.
4. Consider coordination mechanisms among processes authorized to modify the same file.
5. Design failure handling so it does not wipe out valid changes made by another process.

Do not assume `Files.readAttributes(...)` is always a completely atomic snapshot relative to all concurrent operations; Javadoc states that atomicity of bulk reads is **implementation-dependent**.

### The Archive Flag Is Not a Backup System

`archive` is a traditional flag often used by backup software to suggest data has changed or needs archiving. Note the following:

- It does not mean Windows or Java has backed up the file.
- Different backup tools may use or ignore this flag.
- Some write/modify operations may update the flag according to filesystem rules.
- Do not use `archive=false` as definitive proof that data has been safely backed up.

If the system has disaster-recovery requirements, maintain an actual backup policy, verify snapshots, and test real restores.

## 13. Common Errors and Handling

| Scenario | Behavior / Interpretation | Appropriate Handling |
|---|---|---|
| `getFileAttributeView(..., DosFileAttributeView.class)` returns `null` | DOS view unavailable for path/provider | Use fallback branch or report unsupported |
| `Files.readAttributes(..., DosFileAttributes.class)` throws `UnsupportedOperationException` | Requested view is unsupported | Avoid assuming every OS supports it |
| Setter throws `IOException` | Permission error, I/O failure, missing path, or provider rejection | Preserve error context, avoid infinite retries |
| `Files.setAttribute(path, "dos:readOnly", ...)` | Wrong dynamic attribute name | Use `"dos:readonly"` |
| `Files.setAttribute(path, "dos:hidden", "true")` | Value is a string, not `Boolean` | Use `Boolean.TRUE` or `true` |
| Changing `readonly` and forgetting to restore | May affect subsequent write/delete operations | Edit flags on owned files, save old state |
| Treating `hidden` as content security | Hidden is only metadata/display | Use permissions/ACLs, encryption, or real security mechanisms |
| Assuming leading `.` equals DOS Hidden | Rules differ between Unix/Windows | Distinguish `Files.isHidden` and DOS view |
| Reading once and assuming `attrs` updates live | `DosFileAttributes` is a snapshot result | Call `readAttributes()` again |
| Updating multiple flags and expecting atomicity | No default transaction | Design handling for partial updates |
| Opening a path with a link and assuming no follow | Many APIs follow symlinks by default | Explicitly decide `NOFOLLOW_LINKS` and check support |
| Using `archive` to verify backup completion | Archive flag is not a backup certificate | Verify the actual backup system |

### Exceptions to Anticipate

- `IOException`: file access error, path no longer exists, device or provider failure.
- `UnsupportedOperationException`: attribute view unsupported; common on providers without DOS attributes.
- `IllegalArgumentException`: invalid/improper dynamic attribute name, depending on the API.
- `ClassCastException`: passing a wrong value type to the dynamic `Files.setAttribute(...)` API.
- `SecurityException`: Java/implementation security policy denies the operation.

Before handling exceptions, distinguish between **a technical error** and **a feature inherently unsupported on the platform**. For cross-platform applications, do not crash the entire program merely because displaying a DOS flag is unavailable if business logic allows skipping it.

## 14. Which API Should You Choose When?

| Need | Recommended API | Reason |
|---|---|---|
| Check whether the OS considers a file hidden | `Files.isHidden(path)` | Provides platform-aware abstraction |
| Read all four DOS flags accurately | `Files.readAttributes(path, DosFileAttributes.class)` | Strongly typed, reads multiple attributes |
| Read and then modify flags | `Files.getFileAttributeView(path, DosFileAttributeView.class)` | Check `null` and use getters/setters |
| Fetch a single flag dynamically | `Files.getAttribute(path, "dos:hidden")` | Convenient when building a metadata viewer |
| Modify a single flag dynamically | `Files.setAttribute(path, "dos:hidden", true)` | Clear attribute-name contract |
| Check actual JVM write capability | `Files.isWritable(path)` paired with handling actual write operations | DOS readonly cannot replace ACLs |
| Manage Windows ACLs | `AclFileAttributeView` (if supported) | ACLs are a distinct permission model |
| Manage Unix permissions | `PosixFileAttributeView` (if supported) | Separate POSIX permission bits |
| Applications running across multiple providers | Capability check + graceful fallback | Do not hard-code `os.name` |

Choosing between `DosFileAttributes` and `DosFileAttributeView` is also choosing between **reading a snapshot** and **having an object capable of mutating attributes**. Do not grant metadata-writing capabilities to a module that only needs to observe.

## 15. Safe Practice Checklist

1. Create `Path` on the right provider; do not infer DOS view support just because the OS is Windows.
2. Obtain `DosFileAttributeView` and check `null`, or call `Files.readAttributes` and handle `UnsupportedOperationException`.
3. When you only need to read, use getters; do not mutate flags just to "test whether it is supported" on real files.
4. When updates are needed, modify only the requested flag and remember setters can throw `IOException`.
5. If changing temporarily, save the old flag and attempt restoration in `finally`; test on temporary files.
6. Understand the proper role of Read-only, Hidden, System, and Archive instead of turning them into homemade security mechanisms.
7. Clarify symbolic link handling; use `NOFOLLOW_LINKS` if needed and supported by the provider.
8. Re-read `attrs` if post-edit state is needed; do not treat old `DosFileAttributes` objects as live.
9. When accessing multiple files or changing multiple flags, account for races and partial updates; do not promise atomicity beyond the API contract.
10. For important data, distinguish DOS flags, file permissions, ACLs, and real backup strategies.

## 16. Key Takeaways

- **DOS attributes on Windows** comprise four flags: `readonly`, `hidden`, `system`, `archive`.
- **`DosFileAttributes`** is for reading (including `BasicFileAttributes` properties); **`DosFileAttributeView`** is for reading and updating.
- **`Files.getFileAttributeView(...)` may return `null`** if the view is unavailable; do not assume every filesystem supports DOS.
- **`Files.getAttribute/setAttribute`** use names like `"dos:hidden"`, `"dos:readonly"`, etc.
- **Hidden is not security; Read-only does not replace ACLs; Archive does not confirm a backup occurred.**
- Always handle I/O errors, symbolic links, provider differences, and state changes between operations.

### Official References

- [Java SE 17 — DosFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributes.html)
- [Java SE 17 — DosFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributeView.html)
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
