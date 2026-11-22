# Do Copy, Move, and Delete Affect the Symbolic Link or the Target File?

> **Scope:** Java Core I/O, `java.nio.file` API (Java 17+). This lesson focuses on **symbolic links**, while distinguishing them from **hard links** to avoid wrong assumptions when copying, moving, and deleting files.

## 1. Understanding "Link" and "Target"

Suppose we have the following structure:

~~~text
work/
├── report.txt            # Real file, content: hello
└── shortcut.txt          # Symbolic link -> report.txt
~~~

`report.txt` is **the target/referent object**; `shortcut.txt` is **a separate file system object** containing a path referencing the target. When a program accesses `shortcut.txt`, the file system can follow the link to read data from `report.txt`. However, not every API follows the link.

Three roles must be distinguished:

- **Source (source path):** the first parameter of `Files.copy(source, destination)` or `Files.move(source, destination)`. It can be the path to the symbolic link itself.
- **Destination (destination path):** where the copy is placed or where the entry is moved; another symbolic link may already exist there.
- **Referent/target of the link:** the file or directory pointed to by a symbolic link; distinct from the parameter named `target` in `Files.copy`/`Files.move`.

For example, `Files.copy(shortcut, backup)` has **source as `shortcut`** and **destination as `backup`**, yet by default the actual data is read from **`report.txt`**. Therefore, the question "does the operation act on the link or the target?" must consider **the operation type**, **the link position (source/destination)**, and **the API options**.

### How do symbolic links and hard links differ?

- **Symbolic link:** has a path as its reference content; can point to a directory or a file, and can become *dangling/broken* when the target disappears or the path is no longer valid. Can be checked with `Files.isSymbolicLink(path)` and have its referenced path read with `Files.readSymbolicLink(path)`.
- **Hard link:** two path names referencing **one file object** on the file system. There is no "shortcut file containing a target path" to follow like a symbolic link. Modifying content via either name modifies the shared content; deleting one name does not automatically delete the other name. Java provides `Files.createLink(newLink, existingFile)` if supported by the file system.
- **Limitations:** hard links usually cannot be created for directories and cannot span file stores; availability depends on the operating system and file system. The main examples below use symbolic links.

## 2. Rules Table to Remember

This table assumes direct operations on `Path`, a file system that supports symbolic links, and no permission or I/O errors.

| Operation | When **source/path is a symbolic link** | The file/directory the link points to |
|---|---|---|
| `Files.copy(link, newPath)` | **Follows the link by default**, copying the target data/object to `newPath`; the new copy is usually a regular file/directory | Not modified/deleted |
| `Files.copy(link, newPath, LinkOption.NOFOLLOW_LINKS)` | Copies **the symbolic link itself** to the new name (preserving the path reference) | Not modified/deleted |
| `Files.move(link, newPath)` | Moves/renames **the link itself** | Not moved |
| `Files.delete(link)` | Deletes **the link itself** | Not deleted |
| `Files.deleteIfExists(link)` | Deletes **the link itself** if it exists | Not deleted |
| `Files.readString(link)` or `Files.newInputStream(link)` | Normally follows the link to read content | Read through the link |
| `Files.isSymbolicLink(link)` | Checks the link object itself | Does not need to follow to the target |

**Memory tip:** *copy* by default takes **target content**; *move* and *delete* act on **the symbolic link itself**. `NOFOLLOW_LINKS` changes how **the source is copied**, rather than being a required option for move/delete.

Note that `Files.copy` **does not recursively copy** a directory: when the source is a directory, by default it only creates a new empty directory. If the source is a link pointing to a directory, default copying follows the link, which also does not mean copying the entire directory tree.

## 3. Copy: Separating Source Symbolic Links from Links at the Destination Path

### 3.1. Source is a symbolic link

~~~java
Path link = Path.of("work/shortcut.txt");
Path contentCopy = Path.of("work/content-copy.txt");
Path linkCopy = Path.of("work/link-copy.txt");

Files.copy(link, contentCopy);                        // Follow the source link
Files.copy(link, linkCopy, LinkOption.NOFOLLOW_LINKS); // Copy the source link itself
~~~

This is an **illustrative snippet**, assuming `work/shortcut.txt` is already a valid symbolic link and the two destination paths do not yet exist; the complete runnable code is in Section 6.

After the first statement, `content-copy.txt` has **data independent** of `report.txt`. If `report.txt` is modified afterward, the copy does not automatically change. After the second statement, `link-copy.txt` is **another symbolic link**. When `report.txt` changes content, reading through `link-copy.txt` sees the new content, provided the link still points to the right target.

**Relative paths can break a copied link:** if `shortcut.txt -> report.txt`, the internal reference string is `report.txt`, which is resolved **relative to the directory containing the link**. Copying the link to another directory with `NOFOLLOW_LINKS` preserves that reference; it may point to a different file or become a dangling link. Java does not automatically convert a relative path into an absolute path to preserve the original meaning.

If the source is a **dangling symbolic link**, `Files.copy(link, newPath)` by default usually fails when it cannot open the target; `Files.copy(link, newPath, NOFOLLOW_LINKS)` can copy the link entry itself even if the target does not exist (if the provider permits link creation).

### 3.2. Destination path is already a symbolic link

Do not confuse the behavior of a **source link** with a **link sitting at the destination**:

~~~text
work/
├── important.txt          # Target of existing-link.txt
└── existing-link.txt -> important.txt
~~~

- `Files.copy(source, existingLink)` **without** `REPLACE_EXISTING`: fails because a symbolic link already exists at the destination path.
- `Files.copy(source, existingLink, StandardCopyOption.REPLACE_EXISTING)`: **replaces the symbolic link entry** named `existing-link.txt` with the copy. The file `important.txt` that the old link pointed to **is not overwritten through the link**.
- If `source` is also a symbolic link, how source content is obtained still follows its own rules: by default it follows the link; with `NOFOLLOW_LINKS`, it copies the link itself. `REPLACE_EXISTING` does not mean "do not follow the source link".
- If the destination is a **non-empty directory**, `REPLACE_EXISTING` does not allow arbitrary replacement; the operation may report `DirectoryNotEmptyException`.

`COPY_ATTRIBUTES` requests attempting to copy supported attributes (such as modification time). When copying **the symbolic link itself** with `NOFOLLOW_LINKS`, whether link attributes can be copied depends on the provider, and `COPY_ATTRIBUTES` may be ignored.

## 4. Move/Rename: Moves the Link, Not the Referent

~~~java
Path link = Path.of("work/shortcut.txt");       // -> report.txt
Path renamed = Path.of("work/renamed-link.txt");

Files.move(link, renamed);                       // Rename the symbolic link entry
~~~

Result: `shortcut.txt` is gone; `renamed-link.txt` is still a symbolic link; `report.txt` remains in its original place. If `renamed-link.txt` is a relative link and stays in the same directory, it usually continues pointing correctly to `report.txt`.

If you move the link from `work/shortcut.txt -> report.txt` to `archive/shortcut.txt`, the reference path `report.txt` is interpreted inside the `archive` directory. **The link after moving may become broken**, even though `report.txt` in `work` still exists. You must decide whether to recreate the link with an appropriate target.

When the destination path already exists:

- By default, `Files.move(source, destination)` usually fails if the destination already exists.
- With `StandardCopyOption.REPLACE_EXISTING`, if the destination is a symbolic link, **the destination link itself is replaced**, not its referent. A non-empty directory cannot be arbitrarily replaced.
- With `StandardCopyOption.ATOMIC_MOVE`, an atomic operation is requested; if unsupported, it throws `AtomicMoveNotSupportedException`. When using this option, other options are ignored, and behavior when the destination already exists is implementation-dependent. Do not assume an atomic move can span different file stores.

**Moving the target file itself is completely different from moving the link.** If you move `report.txt` to another name without adjusting the reference `shortcut.txt -> report.txt`, the old link may become broken. That is a consequence of relocating the referent, not of `Files.move(link, ...)`.

## 5. Delete: Deleting a Link Does Not Delete the Target

~~~java
Path link = Path.of("work/shortcut.txt");
Files.delete(link);                     // Deletes shortcut.txt
// report.txt remains if it existed previously.
~~~

- `Files.delete(link)` deletes the symbolic link entry even when the link points to a directory **containing data**. It does not enter the target directory to delete files inside.
- `Files.deleteIfExists(link)` behaves similarly, but returns `false` when the entry itself does not exist; `Files.delete(link)` may throw `NoSuchFileException` in that case.
- If you delete **the real file path itself** with `Files.delete(targetPath)`, the real file is deleted. Any symbolic links still pointing to that path become dangling links (unless another object appears at that path).
- If the program's goal is to delete an entire directory tree, `Files.delete(dir)` can only delete an empty directory. You need a controlled tree traversal, typically using `Files.walkFileTree`, and a clearly defined link-following policy.

**Be careful with "deleting the link's target":** `Files.delete(link)` *does not* do this. If you genuinely want to delete the referent, you must **explicitly determine** the target path (for example `link.toRealPath()` when the target exists) and then delete that path. Resolving and deleting are two separate operations, so in an environment with concurrent modifications you must still account for race conditions and access permissions. Never use it blindly on untrusted input.

## 6. Runnable Java 17+ Program

The program creates a temporary directory, a real file, and a **relative symbolic link**, then demonstrates each operation individually. It cleans up the entries created by the program in the `finally` block.

Save the file as **`SymbolicLinkOperationsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class SymbolicLinkOperationsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("symlink-ops-");
        Path target = dir.resolve("data.txt");
        Path link = dir.resolve("alias.txt");
        Path contentCopy = dir.resolve("content-copy.txt");
        Path linkCopy = dir.resolve("link-copy.txt");
        Path movedLink = dir.resolve("moved-alias.txt");

        try {
            Files.writeString(target, "hello");
            // data.txt is resolved relative to the directory containing alias.txt.
            Files.createSymbolicLink(link, Path.of("data.txt"));

            Files.copy(link, contentCopy);
            Files.copy(link, linkCopy, LinkOption.NOFOLLOW_LINKS);
            System.out.println("copy default: file="
                    + Files.isRegularFile(contentCopy)
                    + ", data=" + Files.readString(contentCopy));
            System.out.println("copy nofollow: link="
                    + Files.isSymbolicLink(linkCopy)
                    + ", points=" + Files.readSymbolicLink(linkCopy));

            Files.move(link, movedLink);
            System.out.println("move: oldLinkExists="
                    + Files.exists(link, LinkOption.NOFOLLOW_LINKS)
                    + ", newLink=" + Files.isSymbolicLink(movedLink)
                    + ", targetExists=" + Files.exists(target));

            Files.delete(movedLink);
            System.out.println("delete: movedLinkExists="
                    + Files.exists(movedLink, LinkOption.NOFOLLOW_LINKS)
                    + ", targetExists=" + Files.exists(target));
        } finally {
            Files.deleteIfExists(movedLink);
            Files.deleteIfExists(link);
            Files.deleteIfExists(linkCopy);
            Files.deleteIfExists(contentCopy);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run in the directory containing the source:

~~~bash
javac SymbolicLinkOperationsDemo.java
java SymbolicLinkOperationsDemo
~~~

**Stdout when the system supports symlink creation and operations succeed:**

~~~text
copy default: file=true, data=hello
copy nofollow: link=true, points=data.txt
move: oldLinkExists=false, newLink=true, targetExists=true
delete: movedLinkExists=false, targetExists=true
~~~

Line-by-line explanation:

1. Default copy produces a **regular file** containing `hello`, because Java followed `alias.txt` to `data.txt`.
2. Copy with `NOFOLLOW_LINKS` produces **a new symbolic link**, still recording the relative reference `data.txt`.
3. Move removes the old link name and creates the new link name, while the `data.txt` file is not moved.
4. Delete removes the newly moved link name; `data.txt` remains.

**Portability:** on some Windows machines, creating symbolic links may require privileges/Developer Mode; some file systems do not support symbolic links. In that case, `Files.createSymbolicLink` may throw `UnsupportedOperationException`, `IOException`, or a permission error; the program will not produce the exact stdout above. Run on a system/account that allows symbolic links to observe the full experiment. On operating systems that restrict deleting open files, programs holding files open may need to be closed.

## 7. Separate Case: Hard Links

Suppose you create:

~~~java
Path original = Path.of("work/report.txt");
Path hardLink = Path.of("work/also-report.txt");
Files.createLink(hardLink, original);  // Two names pointing to one file object
~~~

This is an illustrative snippet, requiring `original` to exist and the provider to support hard links.

- **Copy:** `Files.copy(hardLink, anotherPath)` normally creates **an independent copy of the file data**, without automatically creating another hard link. To create another hard link, use `Files.createLink(...)`.
- **Move:** `Files.move(hardLink, newPath)` changes the location/name of the `hardLink` entry; the `original` name can still access the shared data.
- **Delete:** `Files.delete(hardLink)` deletes **one name**; `original` remains accessible. On Unix-style file systems, the data is usually only freed when no hard links remain (and no open handles hold the file object), though details depend on the file system/operating system.
- **Identification:** `Files.isSymbolicLink(hardLink)` returns `false` because a hard link is not a symbolic link. When supported and both exist, `Files.isSameFile(original, hardLink)` can confirm that the two paths point to the same file object.

Do not confuse `Files.createLink` with `Files.createSymbolicLink`: they represent two completely different relationships.

## 8. Broken Links, Tree Traversal, and Common Pitfalls

### 8.1. `exists` follows links by default

If `alias.txt -> missing.txt` and `missing.txt` does not exist:

~~~java
Files.isSymbolicLink(link);                         // true
Files.exists(link);                                 // false: target does not exist
Files.exists(link, LinkOption.NOFOLLOW_LINKS);      // true: link entry remains
Files.readSymbolicLink(link);                       // returns the referenced path
Files.deleteIfExists(link);                         // deletes the dangling link
~~~

This is an illustrative snippet, assuming `link` is a dangling symbolic link. Therefore, **do not rely solely on `Files.exists(link)` to decide whether a link needs to be deleted**. The result of `exists` can also be affected by missing permissions or I/O errors, so when you need to know the exact cause, use an API that throws appropriate exceptions.

### 8.2. Directory traversal for recursive copy/delete

- `Files.walkFileTree(root, visitor)` **does not follow symbolic links by default**. When encountering a link, the visitor usually processes the entry itself; if it deletes that entry, the referent outside/inside the tree is not deleted through the link.
- Enabling `FileVisitOption.FOLLOW_LINKS` means allowing symbolic links to be followed during traversal; this can take the program into directories outside the intended scope, or encounter link cycles and `FileSystemLoopException`. You must clearly define boundaries and handle errors, especially with user-supplied paths.
- `Files.walk(root)` also does not follow symbolic links by default; it only follows them when `FOLLOW_LINKS` is supplied. Do not treat traversal + deletion as atomic; directory contents can change between inspection and execution.

### 8.3. Misconceptions to avoid

| Misconception | Reality |
|---|---|
| "`Files.copy(link, x)` always creates a new link" | Copies the **referent** by default; to copy the link, you must specify `NOFOLLOW_LINKS`. |
| "`NOFOLLOW_LINKS` is an option meant for `move`/`delete`" | Those two operations **already act on the symbolic link itself** when the input path is a link. |
| "`REPLACE_EXISTING` overwrites the file that the destination link points to" | It replaces **the destination link entry**, not the referent of that link. |
| "Moving a link to another directory always keeps working as before" | A relative link may point to the wrong place after changing its containing directory. |
| "Deleting a link to a directory deletes the target directory tree" | `Files.delete(link)` deletes only the link; the real directory tree remains intact. |
| "`Files.exists(link) == false` guarantees there is no link entry" | A dangling symbolic link may still exist; use `NOFOLLOW_LINKS` when you need to check the entry. |
| "Hard links are like file shortcuts" | A hard link is an additional name for the same file object, not an object storing a target path string. |

## 9. Choosing the Operation for Your Requirement

1. **Want an independent copy of the data:** `Files.copy(link, copy)` if you want to follow the referent, and confirm that is the required behavior.
2. **Want to duplicate a symbolic link:** `Files.copy(link, newLink, LinkOption.NOFOLLOW_LINKS)`; then verify `Files.readSymbolicLink(newLink)` and relative paths.
3. **Want to rename or relocate a shortcut:** `Files.move(link, destination)`; re-verify the referent if changing directories.
4. **Want to remove a shortcut while keeping the original file:** `Files.delete(link)` or `Files.deleteIfExists(link)`.
5. **Want to delete the original file:** specify the exact **path of the original file** after verifying permissions, scope, and target identity; accept that symbolic links pointing to it may become dangling.
6. **Want to delete/copy an entire directory tree:** design an explicit traversal pass and only enable `FOLLOW_LINKS` if truly needed, with safeguards against cycles and out-of-scope access.

**Self-check questions:**

- `alias -> data.txt`. After `Files.copy(alias, snapshot)` and then editing `data.txt`, does `snapshot` change as well? **No**: the default copy produces independent data.
- After `Files.copy(alias, alias2, NOFOLLOW_LINKS)` and then editing `data.txt`, what might be seen when reading via `alias2`? **The new content of `data.txt`**, if `alias2` still points correctly.
- After `Files.move(alias, archive/alias)`, does `data.txt` automatically move into `archive`? **No**. The link's relative reference may become broken.
- After `Files.delete(alias)`, is `data.txt` deleted? **No**.
- `destination` is currently a symbolic link pointing to an important file. What does `Files.copy(source, destination, REPLACE_EXISTING)` affect? **Replaces the link entry at `destination`**; it does not follow the destination link to overwrite the important file.

### References

- [Java SE 17 — `Files` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): specifications for `copy`, `move`, `delete`, `createLink`, `createSymbolicLink`, `walkFileTree`.
- [Dev.java — Manipulating Files and Directories](https://dev.java/learn/api/io/java-io/file-system/move-copy-delete/): file/directory copy, move, and delete operations.
- [Java SE 17 — `LinkOption.NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): meaning of not following symbolic links.
