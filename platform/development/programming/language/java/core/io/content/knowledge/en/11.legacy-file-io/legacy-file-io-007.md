# Legacy Java File: mkdir(), mkdirs(), createNewFile(), renameTo(), and delete()

## 1. Objectives and Context

**java.io.File** is the legacy Java API representing an **abstract pathname** to a file or directory on the file system. A File object **does not automatically create a file/directory on disk** just because you call its constructor.

Example:

~~~java
File folder = new File("data/reports");
File report = new File(folder, "daily.txt");
~~~

This is an **illustrative code snippet**, requiring importing **java.io.File**. After these two statements, Java only has two objects representing paths. To actually create the directory or file, you must call APIs such as **mkdir()**, **mkdirs()**, **createNewFile()**.

The five core methods:

| Method | Purpose | Return type | Key point |
| --- | --- | --- | --- |
| **mkdir()** | Creates **one** directory | boolean | Parent directory must exist |
| **mkdirs()** | Creates the target directory **and missing parent directories** | boolean | Returns false when target directory already exists; failure may leave some parent directories created |
| **createNewFile()** | Creates an empty file **only if the name does not yet exist** | boolean, may throw IOException | Existence check and creation are a single atomic operation per API contract |
| **renameTo(File dest)** | Renames or moves source path to destination | boolean | Success depends on the file system; not guaranteed atomic |
| **delete()** | Deletes a file or an **empty directory** | boolean | Does not recursively delete directory trees |

**Biggest rule:** For operations returning **boolean**, you must **check the result**. Returning false does not provide detailed diagnostics on "why it failed." When writing new applications needing accurate error reporting, **java.nio.file.Files** and **Path** are usually more suitable.

## 2. The Path Model of java.io.File

The snippet:

~~~java
File root = new File("workspace");
File child = new File(root, "images");
File image = new File(child, "logo.png");
~~~

represents the relationship:

~~~text
workspace/
└── images/
    └── logo.png
~~~

**However, these paths might not exist on disk.** This is only a pathname model. **File** also does not "open the file," does not hold a stream, and does not guarantee the final resource type: a path may not exist yet, or be a directory, a regular file, or another resource per the file system.

Checks:

~~~java
boolean exists = image.exists();
boolean regularFile = image.isFile();
boolean directory = child.isDirectory();
File parent = image.getParentFile();
~~~

This is an **illustrative code snippet**. **exists()**, **isFile()**, **isDirectory()** observe file system state at a point in time and may be affected by access permissions. Check results **do not lock state**: another actor can create, rename, or delete the path right after the program checks it.

Using **new File(parent, child)** avoids manually concatenating path strings with **/** or **\\**. Relative paths are interpreted against the process's working directory; absolute paths specify the destination, yet still depend on the environment. **File.separator** and **Path.resolve(...)** are more cross-OS compatible ways to represent paths than hardcoding separators.

## 3. mkdir(): Creates Exactly One Directory Level

Signature:

~~~java
public boolean mkdir()
~~~

**mkdir()** asks the system to create a directory right at the File's path. It **does not automatically create missing parent directories**.

Suppose the **project** directory already exists:

~~~text
project/
~~~

Calling:

~~~java
File logs = new File("project/logs");
boolean created = logs.mkdir();
~~~

With write permission and no conflict, the **project/logs** directory is created and **created == true**. Conversely, if you try to directly create **project/archive/2026** when **project/archive** does not exist yet, **mkdir()** does not create **archive**, so it usually returns false.

**Reasons for returning false** include: the directory already exists, the name already exists as a file, missing parent directory, insufficient permissions, or a file system error. Looking at the boolean alone, causes cannot be precisely distinguished.

**Easy-to-miss point:** Calling **mkdir()** a second time on a newly created directory usually returns **false**. False here does not prove the directory is broken: the method only returns true when **that specific call succeeded in creating it**.

## 4. mkdirs(): Creates the Entire Missing Directory Tree

Signature:

~~~java
public boolean mkdirs()
~~~

**mkdirs()** creates the target directory and any missing parent directory levels if needed.

For example, a valid root directory already exists:

~~~text
data/
~~~

With:

~~~java
File output = new File("data/2026/october/reports");
boolean created = output.mkdirs();
~~~

if successful, the result is:

~~~text
data/
└── 2026/
    └── october/
        └── reports/
~~~

The first call **can return true** when successful; a subsequent call on the same path usually **returns false** because the destination already exists. This differs from an "ensure exists" API, which can be called repeatedly without treating pre-existence as a non-creation failure.

### 4.1. mkdir() vs. mkdirs()

| Situation | mkdir() | mkdirs() |
| --- | --- | --- |
| Create **data/logs**, directory **data** already exists | May succeed | May succeed |
| Create **data/a/b**, **a** does not exist yet | Usually **false** | Can create both **a** and **b** |
| Target directory already exists | **false** | **false** |
| A parent directory collides with a regular file name | Fails | Fails |
| Creates part of the tree then hits an error at a later level | Does not create parent levels | **May have created some parent directories** before failing |

Do not think **mkdirs()** is an "all-or-nothing" transaction. The Java documentation notes that if the operation fails, **some parent directories may have already been created**, even though the target directory does not exist.

### 4.2. How Should You Handle an Already-Existing Directory?

If the business goal is "the directory must exist and indeed be a directory," rather than only "this call created the directory," you can write:

~~~java
File directory = new File("data/reports");
if (!directory.isDirectory()) {
    if (!directory.mkdirs() && !directory.isDirectory()) {
        throw new IllegalStateException(
                "Không thể chuẩn bị thư mục: " + directory);
    }
}
~~~

This is an **illustrative snippet**. Checking **isDirectory()** again after mkdirs fails helps identify the case where another process just created the directory, yet it still **does not completely eliminate race conditions** if the resource can be modified concurrently.

In modern code, **Files.createDirectories(path)** is the preferred approach: it creates parents when needed, can be called when the target directory already exists and returns Path upon completion, while I/O errors are typically represented as specific **IOException**s.

## 5. createNewFile(): Creates an Empty File If It Does Not Exist

Signature:

~~~java
public boolean createNewFile() throws IOException
~~~

**createNewFile()** creates an **empty file** at the path when **no file system entry with that name exists yet**.

- **true**: newly created successfully in this call.
- **false**: target path already exists.
- **IOException**: an I/O error occurred such as missing parent directory, inability to create the file object, or a file system error; exact cases depend on the environment.
- **SecurityException**: may occur when the environment's security policy denies the operation.

Example:

~~~java
File folder = new File("data");
if (!folder.isDirectory() && !folder.mkdirs()) {
    throw new IOException("Không tạo được thư mục data");
}

File report = new File(folder, "report.txt");
if (report.createNewFile()) {
    System.out.println("Đã tạo file rỗng");
} else {
    System.out.println("Tên file đã tồn tại");
}
~~~

This is an **illustrative code snippet**, requiring importing **java.io.File** and **java.io.IOException**, and placed inside a method declaring or handling IOException. When the file did not exist and creation succeeds, its initial size is **0 bytes**. **createNewFile() does not automatically write content, does not create parent directories, and does not open an OutputStream for the caller to write data**.

### 5.1. Atomicity of Creation

According to the **createNewFile()** contract, **checking that the path does not exist** and **creating the new file** are performed as **a single atomic operation** with respect to other file system activities that might affect the path.

This is why you should use:

~~~java
boolean created = file.createNewFile();
~~~

instead of:

~~~java
if (!file.exists()) {
    file.createNewFile();
}
~~~

when the goal is **to create only once if not yet present**. Two separate operations (exists then create) leave a window for another process to interfere. You still must check the return value of createNewFile. At the same time, **do not use createNewFile as a reliable file-locking mechanism**; Java documentation recommends **FileLock** for file locking problems.

If you need to **immediately open a write stream and only accept creating a new file**, modern applications can use **Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)**. This enforces the create-new condition at the stream-opening operation instead of creating first and reopening later, avoiding a gap between two separate operations.

## 6. renameTo(File dest): Renames or Moves, Platform-Dependent

Signature:

~~~java
public boolean renameTo(File dest)
~~~

**renameTo(dest)** requests renaming or moving the entry at the source path to the destination path.

Example:

~~~java
File source = new File("data/old.txt");
File destination = new File("data/new.txt");

boolean renamed = source.renameTo(destination);
if (!renamed) {
    System.err.println("Không đổi tên được; cần xử lý lỗi");
}
~~~

This is an **illustrative code snippet**, requiring importing **java.io.File**, and the source data must exist for rename to be able to succeed.

### 6.1. Things That MUST NOT Be Assumed

1. **Not guaranteed to move across two filesystems/drives.** Moving within the same filesystem may succeed, while moving across storage volumes fails.
2. **Not guaranteed to be atomic.** Exact semantics depend on the platform and file system.
3. **Not guaranteed to overwrite when destination path already exists.** Some systems allow it in certain cases, others reject it; do not treat replace as a universal contract.
4. **Not guaranteed to create destination parent directories.** You must prepare parent paths separately.
5. **Does not update the source File object itself.** File is an object representing an immutable pathname: **source** still holds the old name after a successful rename, while **destination** holds the new name.
6. **Does not throw IOException explaining all failure reasons.** For many rename failures, the method only returns **false**; SecurityException may still appear due to permission controls.

If renameTo returns true, you can use the **destination** object to interact with the new path. If it returns false, **do not proceed as if the operation succeeded**; you must check the actual state and handle it per the application's contract.

### 6.2. Alternative API: Files.move(...)

Consider **Files.move(sourcePath, destinationPath)** when you need clearer exceptions:

~~~java
Path sourcePath = Path.of("data", "old.txt");
Path destinationPath = Path.of("data", "new.txt");

Files.move(sourcePath, destinationPath);
~~~

This is an **illustrative snippet**, requiring importing **java.nio.file.Files**, **java.nio.file.Path**, and handling **IOException**. By default, when the destination path already exists, Files.move typically reports an error; when replacement is needed, you can specify **StandardCopyOption.REPLACE_EXISTING** and accept an explicit replacement policy.

If business logic requires an **atomic** rename, you can try **StandardCopyOption.ATOMIC_MOVE**. An unsupported file system may throw **AtomicMoveNotSupportedException**; **do not** assume a move without ATOMIC_MOVE is atomic. Processing order when combining options, open resources, and overwrite rules depends on the specific contract of Files.move and the filesystem, so clarify conditions before deploying.

## 7. delete(): Deletes a File or Empty Directory, Not Recursive

Signature:

~~~java
public boolean delete()
~~~

**delete()** returns true **only if the deletion succeeded**; returns false if it could not be deleted. The path may point to:

- **Regular file**: delete requests deleting the file, subject to permissions and OS rules.
- **Empty directory**: can be deleted.
- **Directory still containing files/subdirectories**: **cannot be deleted via File.delete()**; returns false.
- **Non-existent path**: usually returns false.

Example:

~~~java
File file = new File("data/report.txt");
if (!file.delete()) {
    System.err.println("Chưa xóa được: " + file);
}
~~~

This is an **illustrative code snippet**. Returning false does not clarify whether the file did not exist, was still open on certain operating systems, lacked permissions, or failed for another reason. Cases involving **symbolic links** require attention to the meaning of deleting a path/entry and must not infer that "deleting this entry" deletes all content the symlink points to.

**File.delete() has no recursive mode.** To delete a directory tree, the application must implement a controlled traversal and deletion process, typically in **child-before-parent** order; this is a dangerous operation for user data, so restrict paths and prevent symlink escapes.

### 7.1. Comparison with Files.delete and Files.deleteIfExists

~~~java
Files.delete(path);
~~~

- **Files.delete(path)** deletes the path, potentially throwing **NoSuchFileException** if missing or **DirectoryNotEmptyException** if the directory is non-empty (exact error specificity depends on the file system).
- **Files.deleteIfExists(path)** returns **false** if it does not exist; it can still throw **IOException** for other reasons.
- Neither **turns into recursive deletion automatically**.
- Special care is needed for important data: do not attempt bulk deletion simply because one method returned false.

### 7.2. deleteOnExit() Is Not a Replacement for delete()

**File.deleteOnExit()** registers a deletion request for when the JVM terminates **normally**; it does not delete at the moment of the call. Do not rely on it to guarantee cleanup after a crash or when a process is killed; in long-running applications, the number of registered entries can grow and not be released like normal memory management. For important temporary data, clean up immediately inside **finally** or an appropriate try-with-resources.

## 8. Standalone Java 17+ Example, Creating Inside a Safe Temporary Directory

To avoid deleting real learner files, the program below creates **a new temporary directory** and then demonstrates all five methods. Because the temporary directory name is random, **it does not print concrete paths**. The program only manipulates resources it created itself and includes **finally** cleanup if an error occurs.

Save as **LegacyFileMethodsDemo.java**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public class LegacyFileMethodsDemo {
    public static void main(String[] args) throws IOException {
        File root = Files.createTempDirectory("legacy-file-demo-").toFile();

        File single = new File(root, "single");
        File nested = new File(root, "a/b/c");
        File source = new File(single, "old.txt");
        File destination = new File(single, "new.txt");

        try {
            System.out.println("mkdir=" + single.mkdir());

            // Parent "a/b" does not exist yet: mkdir() only creates 1 level.
            System.out.println("nested.mkdir=" + nested.mkdir());
            System.out.println("nested.mkdirs=" + nested.mkdirs());
            System.out.println("nested.mkdirs again=" + nested.mkdirs());

            System.out.println("createNewFile=" + source.createNewFile());
            System.out.println("createNewFile again=" + source.createNewFile());

            boolean moved = source.renameTo(destination);
            if (!moved) {
                throw new IOException("renameTo thất bại trên filesystem này");
            }
            System.out.println("renameTo=" + moved);

            // Root still has children so it cannot be deleted by delete().
            System.out.println("root.delete nonempty=" + root.delete());

            System.out.println("destination.delete=" + destination.delete());
            System.out.println("single.delete=" + single.delete());
            System.out.println("nested.delete=" + nested.delete());
            System.out.println("b.delete=" + nested.getParentFile().delete());
            System.out.println("a.delete=" +
                    nested.getParentFile().getParentFile().delete());
            System.out.println("root.delete=" + root.delete());
        } finally {
            // Clean up self-created resources if an error leaves some directories behind.
            if (root.exists()) {
                try (Stream<Path> paths = Files.walk(root.toPath())) {
                    for (Path path :
                            paths.sorted(Comparator.reverseOrder()).toList()) {
                        Files.deleteIfExists(path);
                    }
                }
            }
        }
    }
}
~~~

Commands:

~~~bash
javac LegacyFileMethodsDemo.java
java LegacyFileMethodsDemo
~~~

**Stdout on a normal local filesystem**, when creation/deletion permissions are valid and **renameTo** within the same directory succeeds:

~~~text
mkdir=true
nested.mkdir=false
nested.mkdirs=true
nested.mkdirs again=false
createNewFile=true
createNewFile again=false
renameTo=true
root.delete nonempty=false
destination.delete=true
single.delete=true
nested.delete=true
b.delete=true
a.delete=true
root.delete=true
~~~

**The values in stdout above are expected results in a valid environment, not a guarantee that every filesystem always produces the same output**: in particular **renameTo** can fail; the code actively throws IOException instead of printing a fake "success." The temporary directory is uniquely created, so it will not collide with directories from previous runs. Cleanup in **finally** uses Files.walk in reverse order to delete children before parents, only inside the **root** of this run; if a path cannot be deleted, the program can still throw IOException during cleanup. This is a technical example, not a general-purpose deleter for arbitrary user-supplied directories.

Step-by-step analysis:

1. **single.mkdir()** creates a single-level directory under root → true.
2. **nested.mkdir()** fails because **a/b** does not exist yet → false.
3. **nested.mkdirs()** creates **a**, **b**, **c** → true. Calling it again when c already exists → false.
4. **source.createNewFile()** creates an empty file; the second call does not create another → true then false.
5. **source.renameTo(destination)** renames within the same directory; if true, the file resides at the destination path.
6. **root.delete()** while root is non-empty → false.
7. Deleting files and directories from inside out → each call returns true in the successful case.

## 9. When Returning false, How Should You Diagnose and Handle It?

First, do not lump all false results into a single error type. Below are **diagnostic questions to check**, not certain deductions, because file system state can change concurrently.

| Call returning false | Possibilities to check |
| --- | --- |
| **mkdir()** | Does the parent exist? Does the destination already exist? Do you have permission to create directories? |
| **mkdirs()** | Is the destination an existing directory? Is one of the parent levels a regular file? Was part of the tree partially created? |
| **createNewFile()** | Per contract: destination name already exists; other file creation errors typically throw IOException |
| **renameTo()** | Does destination already exist? Moving across filesystems? Platform/permission restrictions? |
| **delete()** | Does the target still exist? Is it a non-empty directory? Missing permission? File locked? |

**Do not call exists() and conclude with certainty why it failed**: between calls, another process may change the state. If diagnostic details are needed, switching to the Files API with specific exceptions is more effective than guessing from booleans.

For each operation, the application should define the **desired postcondition**:

- If the goal is **"the directory must exist,"** verify **isDirectory()** (or use Files.createDirectories).
- If the goal is **"must create a new file without overwriting an existing one,"** rely on **createNewFile()**'s result or use **CREATE_NEW** mode.
- If the goal is **"moved successfully,"** check **renameTo() == true** and then continue with the **new path**; for stricter requirements, use Files.move.
- If the goal is **"deleted successfully,"** check **delete() == true** or use Files.delete and handle IOException.

## 10. java.io.File vs. java.nio.file.Files: Which API to Choose?

**java.io.File** is still very common in legacy codebases, older libraries, and APIs requiring the File type. However, in Java 17, **Path/Files** is usually clearer about errors and options.

| Task | Legacy File | java.nio.file.Files |
| --- | --- | --- |
| Create **one** directory | **file.mkdir()** | **Files.createDirectory(path)** |
| Create directory with missing parents | **file.mkdirs()** | **Files.createDirectories(path)** |
| Create empty file only if absent | **file.createNewFile()** | **Files.createFile(path)** |
| Rename/move | **source.renameTo(dest)** | **Files.move(source, dest, options...)** |
| Delete file/empty directory | **file.delete()** | **Files.delete(path)** |
| Delete if present, no error when missing | Check delete's boolean value, though without distinguishing causes | **Files.deleteIfExists(path)** |
| Convert representation | **file.toPath()** | **path.toFile()** (for Path on a supporting filesystem) |

Illustrative example of the modern approach, assuming **java.nio.file.*** and **java.io.IOException** are imported:

~~~java
Path base = Path.of("data");
Files.createDirectories(base.resolve("reports"));

Path a = Files.createFile(base.resolve("reports").resolve("a.txt"));
Path b = base.resolve("reports").resolve("b.txt");

Files.move(a, b);          // Reports IOException if unsuccessful.
Files.delete(b);           // Reports IOException if unable to delete.
~~~

This is a **code snippet**, not a self-running program: it assumes appropriate access permissions, a working directory containing a "data" location, and that destination file **b.txt** does not exist yet. Rerunning when a.txt/b.txt have different states can yield different results. The example illustrates the API, rather than describing a safe operation to apply to real data without validating destination names.

**Files.createDirectories(...)** is better suited for idempotent directory preparation: when the destination directory already exists with the right type, the call usually completes without treating it as a failure. However, **if a regular file occupies the directory name**, creation still fails. On some platforms, tree creation may partially succeed before failing; do not treat it as transactional.

## 11. Data Safety and Race Conditions

### 11.1. Avoid Check-Then-Act as a Transaction

Unsafe example under concurrency:

~~~java
if (!file.exists()) {
    file.createNewFile();
}
~~~

Another process can create the file right after **exists()**. When unique creation is required, **createNewFile()** performs checking and creation in one operation; if you also need to open the file for writing, consider Files.newOutputStream with **CREATE_NEW**.

Similarly, **isDirectory()** before **mkdir()** or **exists()** before **delete()** is merely a snapshot of state at one moment. You cannot use these checks to claim a path "definitely" won't change in a multi-process application.

### 11.2. Do Not Delete/Rename Based on Unvalidated Paths

For filenames taken from user input, **do not concatenate strings directly and delete**, because components like **..**, absolute paths, symlinks, or mismatches in path normalization can cause the operation to affect places outside the intended scope. Validate access scope at the appropriate layer and avoid arbitrary recursive deletion; if operations must be safe against races/symlinks, consider APIs and designs with real permission-control mechanisms.

For important files, you can write content to a **temporary file on the same filesystem**, complete flush/sync as needed, and then call **Files.move(...)** with the appropriate replacement contract. **Do not claim every system supports atomic moves**; you must handle the unsupported case.

### 11.3. Non-Empty Directories and Open Resources

Some operating systems restrict renaming or deleting files currently held open by another program. Even when the API returns true, post-operation state visibility may be influenced by caching or external races. To prevent data loss, use **try-with-resources** for I/O streams and check the results of file operations.

**SecurityException** is an exception raised by permission-control mechanisms in environments with a SecurityManager/corresponding policy, distinct from **IOException**. A boolean API does not mean no exception will ever be thrown.

## 12. Common Mistakes and How to Avoid Them

1. **Thinking new File(...) creates a file on disk.** The constructor only creates a path object; you must call a creation API.
2. **Using mkdir() for a multi-level path with non-existent parents.** Use mkdirs() or Files.createDirectories.
3. **Treating mkdirs() == false as meaning the directory definitely does not exist.** It is often false when the destination already exists; check the postcondition or use Files.createDirectories.
4. **Believing a failed mkdirs() created nothing.** Part of the tree may have been created, requiring controlled cleanup or recovery.
5. **Calling createNewFile() and assuming data was written.** The new file is empty; write content using OutputStream, Files.write..., etc. if needed.
6. **Writing exists() then createNewFile() as an atomic check.** The exists result may be stale; prefer the atomic create-new contract.
7. **Not checking the boolean from renameTo().** It can be false due to the filesystem or existing destination; never assume rename always succeeds.
8. **Continuing to use the source File after a successful renameTo as if its path updated automatically.** The source File object keeps the old path; use the dest File.
9. **Using renameTo as a cross-platform atomic replacement mechanism.** It is not guaranteed; consider Files.move with explicit options.
10. **Trying file.delete() on a directory containing children.** It can only delete empty directories; delete is not recursive.
11. **Thinking File.delete() will explain failure details.** It usually only returns false; Files.delete has more informative IOExceptions.
12. **Deleting parents before children.** To clean up a self-created tree, delete children before parents, and strictly restrict scope.
13. **Using deleteOnExit() instead of deterministic cleanup.** It is not guaranteed to run when the JVM stops abnormally.
14. **Hardcoding path separators.** Use **new File(parent, child)** or **Path.resolve**.
15. **Not considering rerunning the program.** On the second run, files/directories may already exist; boolean results validly change.
16. **Attempting to delete or rename externally supplied paths without validation.** This can cause data loss or operations outside the allowed area.

## 13. Review Questions

**Q1.** You have directory **data** but not **data/2026**. Which call is better suited to create **data/2026/reports** in one step?  
**Ans:** **mkdirs()**; it creates missing parents as well. **mkdir()** will not create data/2026 itself.

**Q2.** Why does a second **mkdirs()** call usually return false while **Files.createDirectories()** can complete?  
**Ans:** mkdirs returns true when it actually creates the target directory along with needed parents during that call; Files.createDirectories allows the target path to already exist as the right type without treating it as an error.

**Q3.** Does **createNewFile()** returning false mean the file was created without writing data?  
**Ans:** No. Per contract, false means the destination name **already exists**. When newly created successfully, the result is true and the file is initially empty.

**Q4.** Can **renameTo()** always rename/move a file between two drives?  
**Ans:** No. It depends on the platform and filesystem; you must check the boolean or use Files.move for clearer error/option handling.

**Q5.** After **source.renameTo(dest)** succeeds, does **source** automatically point to the new name?  
**Ans:** No. File represents an immutable pathname; **source** still carries the old path, while **dest** represents the destination.

**Q6.** Given a directory containing files, does calling **directory.delete()** delete everything inside?  
**Ans:** No. File.delete is not recursive and can only delete empty directories.

**Q7.** If you want to know why deletion failed, which API should you use?  
**Ans:** **Files.delete(path)** with specific IOExceptions, rather than relying only on File.delete's boolean value.

**Q8.** If you need to create a file only if it does not yet exist **and immediately open it for writing**, which API is worth considering?  
**Ans:** **Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)** to enforce the create-new condition right when opening the stream.

## 14. Summary

- **mkdir()**: creates exactly **one** directory, does not create parents.
- **mkdirs()**: creates **missing parent directories** too, yet may leave a partially created tree upon failure.
- **createNewFile()**: **creates an empty file if not yet present**, returning false if the name already exists; checking and creating are a single atomic operation.
- **renameTo(dest)**: requests renaming/moving, **platform-dependent**, not guaranteed atomic or overwriting; the source File object does not change its path.
- **delete()**: deletes a **file or empty directory**, does not delete recursively; returns false if unable to delete.

In new code, **Path + Files** is usually the preferred choice when comprehensive error handling, explicit options, or safer operations are needed. Regardless of which API is used, check postconditions, avoid deleting data out of scope, and remember that the file system can change concurrently.

### Official References

- [Oracle Java SE 17 — java.io.File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): mkdir, mkdirs, createNewFile, renameTo, delete, deleteOnExit, and boolean results.
- [Oracle Java SE 17 — java.nio.file.Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): createDirectory, createDirectories, createFile, move, delete, deleteIfExists.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE_NEW and file open options.
- [Oracle Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): REPLACE_EXISTING and ATOMIC_MOVE.