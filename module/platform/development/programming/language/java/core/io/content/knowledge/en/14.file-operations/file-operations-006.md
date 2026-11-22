# Handling Existing Target Files and Non-Empty Directories in Java I/O

## 1. The Real-World Problem

When creating, copying, moving, or deleting files in Java, two situations arise very frequently:

1. **The target path already exists**: you want to create **report.txt**, yet a file or directory is already there. Is overwriting allowed? Should you reject, pick a new name, append, or replace?
2. **A non-empty directory**: you want to delete **reports/**, yet files or subdirectories remain inside. Does a single direct delete call wipe the entire tree? How do you avoid accidental deletion?

The answer must come from **business rules**. Java provides the legacy **java.io.File** API and the modern **java.nio.file.Files** API, yet neither API knows on its own whether you are authorized to destroy old data.

> Safety rule: **reject overwriting or recursive deletion by default unless explicitly required**. Only use replacement options or tree cleanup once scope, permissions, error handling, and concurrent modification risks have been defined.

This lesson focuses on **an existing target file** during create/copy/move/write operations and **a non-empty directory** during deletion. Code examples use Java 17+.

## 2. Distinguishing "Path Exists" from "Right Resource Type"

A **Path** may represent:

- A regular file.
- A directory, which may be empty or non-empty.
- A symbolic link, if the filesystem supports it.
- A special resource or a path that does not yet exist.

Example:

~~~java
Path destination = Path.of("data", "report.txt");

boolean exists = Files.exists(destination);
boolean regular = Files.isRegularFile(destination);
boolean directory = Files.isDirectory(destination);
~~~

This is an **illustrative snippet**; it requires importing **java.nio.file.Files** and **java.nio.file.Path**.

**Files.exists(path)** is insufficient to decide "safe to overwrite": a path might be a directory rather than a regular file; a symlink might point elsewhere; access permissions might prevent the check from concluding definitively. With **Files.exists** or **Files.notExists**, both can return false when status is unknown due to permissions or I/O errors.

More importantly, **check-then-act** is not an atomic transaction:

~~~text
Process A: Files.exists(target) → false
Process B: creates target
Process A: begins writing target → risk of colliding with newly created data
~~~

This is a **TOCTOU** (*time of check to time of use*) race condition. If the requirement is to create a new file only when the name does not yet exist, use the **CREATE_NEW** option on the write operation or **Files.createFile**, rather than trusting a previously checked `exists` result.

## 3. Policies for Handling an Existing Target File

| Policy | When to choose | Suitable API |
| --- | --- | --- |
| **Reject** if target already exists | Avoid losing user files; create unique reports | **Files.createFile**, **CREATE_NEW**, or default **Files.copy** |
| **Replace** old target file | Authorized to update and backup/recovery policy exists | **Files.copy(..., REPLACE_EXISTING)**, **Files.move(..., REPLACE_EXISTING)**, or truncate write |
| **Append** | Logs/records that can be concatenated without altering old data | **Files.writeString(..., CREATE, APPEND)** or **Files.newOutputStream(..., APPEND)** |
| **Use a different name** | Keep both old and new versions | Generate another target name; **CREATE_NEW** to claim creation atomically |
| **Replace via temp file** | Reduce risk of old copy getting corrupted by partial write | Write to temp + **Files.move** with appropriate options and filesystem |

Do not equate **overwriting** with **appending**. Overwriting normally discards old content or replaces the file; appending places new data after existing data. For structured file formats (PDF, ZIP, images), arbitrary appending usually produces a corrupted file.

## 4. Creating a New File: Files.createFile and CREATE_NEW

### 4.1. Files.createFile Does Not Silently Overwrite

~~~java
Path path = Path.of("output.txt");
Files.createFile(path);
~~~

This is a **snippet** requiring importing Files/Path and handling **IOException**.

**Files.createFile(path)** creates a new empty file if the path does not yet exist. If a filesystem entry already occupies that name, the API typically throws **FileAlreadyExistsException** (a subclass of **IOException**) instead of overwriting old data. Checking non-existence and creating the file are required to execute atomically within the API/provider contract.

**Do not use** the check-then-create pattern:

~~~java
if (!Files.exists(path)) {
    Files.createFile(path);
}
~~~

The **exists()** result may be stale by the time the file creation call actually runs. Calling **createFile** directly and handling **FileAlreadyExistsException** is clearer.

### 4.2. To Open a File for Writing, Use CREATE_NEW

If the goal is **create a file and write content immediately**, you can use:

~~~java
Files.writeString(
        path,
        "Nội dung mới",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
~~~

This is a **snippet** requiring importing **StandardCharsets** and **StandardOpenOption**. If the name already exists, the operation will not open under an overwrite policy. This avoids the gap between "create empty file" and "open file for writing."

Note: **CREATE_NEW does not turn writing thousands of bytes into an atomic transaction**. If disk space runs out or I/O fails mid-way, the new file may have been created with incomplete content. You must handle or mark incomplete files according to application rules.

### 4.3. Comparison with java.io.File.createNewFile

~~~java
File legacy = new File("output.txt");
boolean created = legacy.createNewFile();
~~~

This is a **snippet** requiring importing **java.io.File** and handling IOException. **created == true** means the call created an empty file; **false** means that name already existed. Unlike Files.createFile, a `false` result provides no exception specifically describing the already-exists case.

**File.createNewFile()** also has an atomic check-and-create contract, yet if you need to write immediately with a "do not replace" policy, **CREATE_NEW** integrated directly into the open/write operation usually expresses intent better.

## 5. Files.copy: Rejects by Default, REPLACE_EXISTING When Permitted

Common usage signatures:

~~~java
Files.copy(source, target);
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

These snippets assume **source** and **target** are Paths and **Files**, **StandardCopyOption** are imported.

### 5.1. Without REPLACE_EXISTING

With **different** source and target files, if **target already exists**, **Files.copy(source, target)** typically throws **FileAlreadyExistsException**. This is a good default when you do not want to destroy target data.

~~~text
source.txt = "NEW"
target.txt = "OLD"

Files.copy(source, target)
    → FileAlreadyExistsException
target.txt still contains "OLD" (in the already-exists failure case)
~~~

### 5.2. With REPLACE_EXISTING

Once replacement is confirmed as intended:

~~~java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING);
~~~

The API attempts to replace the destination so a copy of the source data appears at **target**. However:

- **Does not guarantee the copy operation is atomic.** If an error happens mid-way, target's state may no longer be intact.
- **Does not preserve all source metadata by default.** To attempt copying supported attributes, consider **COPY_ATTRIBUTES**, though not every attribute can be copied.
- **Do not use REPLACE_EXISTING as a command to wipe any directory tree.** If target is a **non-empty directory**, the provider may be unable to replace it; **DirectoryNotEmptyException** or a related IOException can occur.
- If **source is a directory**, calling Files.copy on a directory **does not mean recursively copying all child contents**. A separate algorithm is required if you genuinely want to copy the whole tree.
- Differing states of symlinks, filesystems, or open files can affect the outcome; do not guess based on filename extensions.

**Postcondition to verify**: if copying completes, target must satisfy the content and attribute requirements defined by the application. For critical data, compare sizes/hashes or use **Files.mismatch(source, target)** after copying while both files remain stable.

## 6. Files.move: Existing Target and Atomicity

Name/location move command:

~~~java
Files.move(source, target);
~~~

By standard rules, **if target already exists**, a move without REPLACE_EXISTING fails (typically **FileAlreadyExistsException**); exceptions depend on the provider and the case where source/target paths point to the same file. Therefore do not rely on out-of-contract behavior for special resources.

If policy permits replacement:

~~~java
Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

**Do not treat REPLACE_EXISTING as a guarantee to overwrite every kind of target**. For instance, a target that is a **non-empty directory** may not be replaceable; files in use, different filesystems, access permissions, or operating systems can also cause moves to fail.

### 6.1. REPLACE_EXISTING and ATOMIC_MOVE Address Two Different Goals

- **REPLACE_EXISTING**: expresses **the desire to replace an existing target object** if the provider and situation support it.
- **ATOMIC_MOVE**: requests **an atomic move as a single filesystem operation**, if the provider supports it.

Example:

~~~java
Files.move(
        temporary,
        target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

This is an **illustrative snippet** (temporary and target are Paths). With **ATOMIC_MOVE**, the API contract specifies that other options may be ignored and **behavior when target already exists is implementation-dependent**. Hence **do not deduce** that combining both options yields a portable "atomic replace" across every provider.

If atomic move is unsupported, **AtomicMoveNotSupportedException** may be thrown. The application must have a **fallback policy**: reject the update, accept a non-atomic move as permitted, or choose another storage mechanism. Never silently drop the ATOMIC_MOVE option in a workflow where atomicity is mandatory.

### 6.2. Write to a Temporary File, Then Move

To update an important configuration file, a common strategy is:

1. Create a **new temporary file** in the target's directory or at least on the same filesystem, using unique creation so it does not overwrite another file.
2. Write the full content and close resources; sync data/metadata to the required durability level if needed by the application.
3. If format validation or checksums exist, run them before replacing the target.
4. Attempt to move to target with an explicit atomic/replacement policy and handle cases where the filesystem does not support it.
5. On error, clean up the temp file you created but **do not accidentally delete the old target copy**.

**Writing a temporary file does not automatically turn every workflow into a power-loss-durable transaction**. Consider FileChannel.force, directory syncing, and filesystem contracts if the application has very strict durability requirements.

## 7. Files.writeString and Files.newOutputStream: Why Did the File Lose Its Old Content?

Example:

~~~java
Files.writeString(path, "NEW");
~~~

**Files.writeString** defaults to UTF-8 and, when no options are passed, opens with a policy equivalent to **CREATE + TRUNCATE_EXISTING + WRITE**. For an existing file, old content is truncated before writing new content. This is an intentional **overwrite** by the API, unlike default Files.copy which rejects an existing target.

Similarly:

~~~java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(new byte[] {1, 2, 3});
}
~~~

This is a **snippet** requiring importing **java.io.OutputStream** and **java.nio.file.Files**; IOException must be handled. With the default options of Files.newOutputStream, an existing file is typically truncated to write anew.

To **append** instead of truncating:

~~~java
Files.writeString(
        path,
        "\nNEW",
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
~~~

The example requires importing **StandardOpenOption**. The newline **\n** is explicitly inserted by code, not added automatically by APPEND. Across multiple processes writing concurrently, APPEND **does not replace record-level synchronization/locking design**.

**Contrast to remember:**

| Operation | When target file already exists |
| --- | --- |
| **Files.createFile(path)** | Typically **throws FileAlreadyExistsException** |
| **Files.copy(source, target)** | Typically **throws FileAlreadyExistsException** |
| **Files.move(source, target)** | Typically fails, does not replace by default |
| **Files.writeString(path, text)** | By default **truncates then rewrites** |
| **Files.newOutputStream(path)** | By default **truncates to write anew** |
| **Files.writeString(..., CREATE_NEW, WRITE)** | Rejects if target name already exists |
| **Files.writeString(..., CREATE, APPEND)** | Appends at the end |

Do not conclude "every Files method avoids overwriting by default" or "every Files method overwrites": **each method's contract differs**.

## 8. Non-Empty Directories: Why Does delete() Fail?

Suppose:

~~~text
reports/
├── 2026/
│   └── october.csv
└── notes.txt
~~~

**reports/** is a non-empty directory. Calling:

~~~java
Files.delete(Path.of("reports"));
~~~

will not automatically delete all child files. On a normal filesystem, the operation throws **DirectoryNotEmptyException** (an IOException); many other systems may throw a different IOException.

Similarly, using the legacy API:

~~~java
File directory = new File("reports");
boolean deleted = directory.delete();
~~~

**File.delete()** only deletes an **empty** directory under standard rules and returns **false** if it cannot delete, without providing detailed diagnostics like Files.delete.

### 8.1. Files.delete vs. Files.deleteIfExists

| API | If target does not exist yet | If target is a non-empty directory |
| --- | --- | --- |
| **Files.delete(path)** | Typically throws **NoSuchFileException** | Throws **DirectoryNotEmptyException** or related IOException |
| **Files.deleteIfExists(path)** | Returns **false** | **Still throws IOException**; does not clean tree automatically |
| **new File(...).delete()** | Typically returns **false** | Typically returns **false**, less informative |

**deleteIfExists** only ignores **the missing target name error**, **not** "delete if present regardless of what is inside." For a non-empty directory, the method can still throw an error.

### 8.2. Deleting an Empty Directory

If you genuinely want to delete a directory known to be empty:

~~~java
Files.delete(directoryPath);
~~~

If the directory has children, **report an error and require an explicit decision** before choosing to delete contents. Never secretly turn directory deletion into recursive deletion because that can destroy unintended user data.

## 9. When Business Rules Actually Require Deleting an Entire Directory Tree

Recursive deletion is a **dangerous** task: users might supply the wrong path; a symbolic link might lead to resources outside scope; another process might create additional files during traversal. **java.nio.file.Files** has no general **deleteTree(path)** function guaranteed safe in every case.

Principles when genuinely permitted:

1. Confirm the root path belongs to **a scope owned by the program**, not a system directory or user data outside policy.
2. Explicitly define symbolic link handling; never automatically **follow** links into other trees.
3. Traverse the tree and delete **files/children first, parent directories afterward**.
4. Handle **IOException**, permissions, open files, and cases where an entry appears/disappears during traversal.
5. Record how far deletion progressed. Do not treat recursive deletion as a rollbackable transaction.
6. For security risks or concurrently changing filesystems, design around directory handles/appropriate mechanisms (e.g., **SecureDirectoryStream** when the provider supports it), rather than trusting path concatenation alone.

Example strictly for **a temporary tree created by the program itself**, never substituting a user-entered path:

~~~java
Path ownedTemp = Files.createTempDirectory("owned-tree-");
Path child = Files.createDirectories(ownedTemp.resolve("nested"));
Files.writeString(child.resolve("example.txt"), "example");

try (var paths = Files.walk(ownedTemp)) {
    for (Path entry :
            paths.sorted(java.util.Comparator.reverseOrder()).toList()) {
        Files.delete(entry);
    }
}
~~~

This is an **illustrative snippet**, requiring importing **Files**, **Path**, and handling IOException. **Files.walk** by default **does not follow symbolic links** when FOLLOW_LINKS is not passed. Sorting paths in reverse order typically places child paths before parent paths in the illustrative tree. For general tree-deletion programs, **Files.walkFileTree** using FileVisitor, **visitFile**, and **postVisitDirectory** expresses ordered traversal more clearly and supports per-entry error handling; do not use a short snippet like the above as an arbitrary directory-wiping tool.

In real production software, if any file cannot be deleted, it may be necessary to stop and report a partially deleted state rather than swallowing the error and continuing as if there were no risk.

## 10. Standalone Runnable Java 17+ Example: Handling Existing Targets and Non-Empty Directories

The following program creates a **dedicated temporary directory** for each run without touching user files. It demonstrates no-overwrite policy, intentional overwrite, moving, CREATE_NEW, non-empty directory failure, and ordered cleanup.

Save as **ExistingTargetDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class ExistingTargetDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("target-demo-");
        Path source = root.resolve("source.txt");
        Path target = root.resolve("target.txt");
        Path exclusive = root.resolve("exclusive.txt");
        Path folder = root.resolve("folder");
        Path child = folder.resolve("keep.txt");

        try {
            Files.writeString(source, "NEW", StandardCharsets.UTF_8);
            Files.writeString(target, "OLD", StandardCharsets.UTF_8);

            // Default copy rejects an existing target file.
            try {
                Files.copy(source, target);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("copy-existing=blocked");
            }

            // REPLACE_EXISTING: permitted to replace target content.
            Files.copy(source, target,
                    StandardCopyOption.REPLACE_EXISTING);
            System.out.println("copy-replaced=" +
                    Files.readString(target));

            // Default move rejects an existing target.
            Files.writeString(source, "MOVE", StandardCharsets.UTF_8);
            try {
                Files.move(source, target);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("move-existing=blocked");
            }

            // Replace only when contract permits.
            Files.move(source, target,
                    StandardCopyOption.REPLACE_EXISTING);
            System.out.println("move-replaced=" +
                    Files.readString(target));
            System.out.println("source-gone=" +
                    Files.notExists(source));

            // CREATE_NEW: attempt to recreate an existing name.
            Files.writeString(exclusive, "FIRST",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            try {
                Files.writeString(exclusive, "SECOND",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("create-new-existing=blocked");
            }
            System.out.println("exclusive=" +
                    Files.readString(exclusive));

            // Non-empty directory: direct delete is refused.
            Files.createDirectory(folder);
            Files.writeString(child, "KEEP", StandardCharsets.UTF_8);
            try {
                Files.delete(folder);
            } catch (DirectoryNotEmptyException ex) {
                System.out.println("nonempty-directory=blocked");
            }

            // Delete child first, empty directory afterward.
            Files.delete(child);
            Files.delete(folder);
            System.out.println("folder-gone=" +
                    Files.notExists(folder));
        } finally {
            // Clean up only paths created by this demo itself.
            Files.deleteIfExists(child);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(exclusive);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Run:

~~~bash
javac ExistingTargetDemo.java
java ExistingTargetDemo
~~~

On a normal local filesystem permitting the test operations, expected stdout:

~~~text
copy-existing=blocked
copy-replaced=NEW
move-existing=blocked
move-replaced=MOVE
source-gone=true
create-new-existing=blocked
exclusive=FIRST
nonempty-directory=blocked
folder-gone=true
~~~

**Note:** Some providers may have different rules for move operations and exception reporting; the description above applies to typical local filesystems. If a provider does not throw **FileAlreadyExistsException** or **DirectoryNotEmptyException** specifically and instead throws another **IOException**, the program may halt and report an error instead of printing all lines. The demo does not force every filesystem to produce identical output.

Explanation:

- **Files.copy(source,target)** without REPLACE_EXISTING rejects target containing "OLD". The target name is not overwritten by the failed already-exists copy step.
- **Files.copy(..., REPLACE_EXISTING)** replaces target with "NEW" data.
- Next, source is written "MOVE"; move without options is rejected because target exists. Move with REPLACE_EXISTING updates target and leaves source absent at the old path.
- **CREATE_NEW** does not overwrite "FIRST" with "SECOND" when the target name already exists.
- **Files.delete(folder)** with child inside is refused; deleting child then folder succeeds.

The **finally** block attempts to clean up all temporary paths owned by the demo. If the file system fails during cleanup, an IOException may be thrown; the program should not assert cleanup succeeded when it actually failed.

## 11. Error Handling: Do Not Rely Solely on Exception Names

Common exceptions in **java.nio.file**:

| Exception | Typical situation |
| --- | --- |
| **FileAlreadyExistsException** | Create/copy/move when target name already exists |
| **DirectoryNotEmptyException** | Deleting a directory still containing child entries |
| **NoSuchFileException** | Missing required source/target path |
| **AccessDeniedException** | System denied access permissions |
| **AtomicMoveNotSupportedException** | Requested ATOMIC_MOVE but provider does not support it |
| **IOException** | Other I/O errors, including cases where provider reports errors using the general type |

Specific exception types **are not always thrown identically by every file system**; Javadoc treats specific exception types as optional in many contracts. Always include handling for general **IOException**, or let it propagate to a higher layer to handle.

An explicit policy:

~~~java
try {
    Files.copy(source, target); // Overwrite-rejection policy.
} catch (FileAlreadyExistsException ex) {
    // Notify user: rename target or confirm replacement.
} catch (IOException ex) {
    // Log/diagnose other I/O errors; do not treat as "file already exists".
    throw ex;
}
~~~

This is an **illustrative snippet**, not a standalone program. Even when choosing REPLACE_EXISTING, still catch IOException; never implicitly assume every overwrite succeeds.

## 12. Postcondition Verification and Operational Safety Rules

### 12.1. Compare Contents Instead of Just Paths

After copying, if byte equality must be ensured, you can use:

~~~java
long mismatch = Files.mismatch(source, target);
if (mismatch != -1L) {
    throw new IOException(
            "File đích khác nguồn tại byte: " + mismatch);
}
~~~

This is a **snippet**, used when both source and target are readable regular files and are not being modified concurrently. **Files.mismatch** (Java 12+) returns -1 if no differing byte is detected. Comparing only sizes or relying solely on filenames is insufficient.

### 12.2. Do Not Delete First Then Copy If Keeping the Old Version Matters

A risky pattern:

~~~java
Files.delete(target);
Files.copy(source, target);
~~~

If the copy step fails, the old version is already lost. Nor should you use Files.deleteIfExists(target) followed by copy as a default "preparation" step. When replacement is authorized, consider **copying to a temporary file, verifying, then moving**, while explicitly assessing atomic move capability and provider support.

### 12.3. Do Not Assume exists() Confirms Permission or Safety

A workflow like:

~~~java
if (Files.exists(target)) {
    Files.delete(target);
}
Files.move(source, target);
~~~

still has a race condition across check/delete/move. It is especially dangerous if target can be changed by others or points to a symlink. Use **options** to express conditions directly and operate only within permitted paths.

### 12.4. Protecting User Data

Do not accept arbitrary paths directly and invoke recursive deletion or replacement. When receiving filenames from users, normalize and validate scope within permitted directories, handling absolute paths, **..**, symbolic links, and access permissions. In adversarial environments, ordinary path checks can still race; use directory-handle/permission mechanisms or an appropriate safe storage service.

In destructive data operations, distinguish "**target name owned by the application**" from "**target content allowed to be destroyed**." An application-owned directory can still hold user data that must not be deleted.

## 13. Self-Check Questions

**Question 1.** Target file already exists; what happens when calling **Files.copy(source,target)** without options?  
**Answer:** Typically throws **FileAlreadyExistsException**; does not replace old data by default.

**Question 2.** Does **REPLACE_EXISTING** allow Files.copy to replace a non-empty directory with a file?  
**Answer:** Do not assume so. A non-empty directory target may not be replaceable; DirectoryNotEmptyException/IOException may occur.

**Question 3.** Does **Files.writeString(path, "X")** reject an existing file by default like Files.copy?  
**Answer:** No. With default options, it creates the file if missing or **truncates** an existing file and writes the content.

**Question 4.** Does **Files.deleteIfExists(directory)** automatically delete all child files?  
**Answer:** No. It only allows ignoring a missing path; a non-empty directory still cannot be deleted directly.

**Question 5.** Why doesn't **Files.exists(target)** followed by **Files.createFile(target)** replace CREATE_NEW?  
**Answer:** A race window exists between check and creation; CREATE_NEW/createFile binds the non-existence condition directly at creation time.

**Question 6.** Are **REPLACE_EXISTING** and **ATOMIC_MOVE** the same?  
**Answer:** No. REPLACE_EXISTING specifies the desire to replace the target; ATOMIC_MOVE requests an atomic move if supported by the provider, and when combined with ATOMIC_MOVE other options may be ignored.

**Question 7.** To delete a non-empty directory safely, what must be done first?  
**Answer:** Define **the authorized deletion scope**, understand the data tree and symlinks, choose a child-before-parent traversal solution with error handling; never automatically run recursive deletion on untrusted paths.

**Question 8.** To avoid losing the old target copy if updating fails mid-way, which approach is better?  
**Answer:** Create a separate temporary file, write and verify completely, then move under a supported atomic/replacement policy. Failure handling is still required and atomic support must not be assumed across all filesystems.

## 14. Summary

**An existing target file** is not a problem with a single fix: you must choose **reject**, **replace**, **append**, **rename to a new name**, or **update via a temporary file**. APIs carry different defaults: **Files.copy/move** usually reject an existing target, whereas **Files.writeString/newOutputStream** can truncate an existing file by default. **CREATE_NEW** creates newly without overwriting; **REPLACE_EXISTING** expresses a replacement policy yet guarantees neither atomic copy/move nor replacing non-empty directories.

**A non-empty directory** is not deleted by **Files.delete**, **Files.deleteIfExists**, or **File.delete** as a recursive delete. Cleaning a tree requires clear ownership scope and a well-defined traversal/deletion strategy handling symlinks, permissions, races, and partial failures.

When operating on critical data, **do not treat booleans, options, or Files calls as transactional guarantees**. Verify postconditions and design so failures do not turn into data loss.

### Official References

- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): Files.copy, Files.move, Files.createFile, Files.delete, Files.deleteIfExists, Files.writeString, and Files.walk.
- [Oracle Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): REPLACE_EXISTING, COPY_ATTRIBUTES, ATOMIC_MOVE.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE_NEW, CREATE, TRUNCATE_EXISTING, APPEND.
- [Oracle Java SE 17 — DirectoryNotEmptyException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryNotEmptyException.html): directory with child entries.
- [Oracle Java SE 17 — FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html): target path name already occupied.
- [Oracle Java SE 17 — java.io.File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): createNewFile, delete, and renameTo in the legacy API.
