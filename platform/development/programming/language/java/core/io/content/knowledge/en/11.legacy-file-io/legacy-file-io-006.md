# `list()`, `listFiles()`, `FileFilter`, and `FilenameFilter`

## Lesson Objectives

In legacy Java I/O, the `java.io.File` class represents a **path** to a file or directory, not file content or an open file descriptor. To list **direct** entries in a directory, this class provides two families of methods: `list(...)` returns **names** as `String`, while `listFiles(...)` returns `File` objects. The two interfaces `FilenameFilter` and `FileFilter` help select which entries are included in the result.

After this lesson, you will be able to:

- Distinguish the overloads `list()`, `list(FilenameFilter)`, `listFiles()`, `listFiles(FilenameFilter)`, and `listFiles(FileFilter)`.
- Write lambdas/implementations for `FilenameFilter.accept(File dir, String name)` and `FileFilter.accept(File pathname)` with the right parameters.
- Know when you need a **simple name**, when you need a **full path via a `File` object**, and how to combine parent and child.
- Handle `null` results from `list`/`listFiles`, sort when needed, restrict to a single directory level, and handle permission/race condition scenarios.
- Write Java 17+ code using temporary directories to test filters independently of personal machine directories.
- Know when to switch to `java.nio.file.Files.list`, `DirectoryStream`, `Files.walk`, or `Files.walkFileTree` in new code.

## 1. Foundation: `java.io.File` Represents a Path

```java
File directory = new File("data");
File child = new File(directory, "report.txt");
```

This is an **illustrative snippet** requiring `import java.io.File;`. Calling `new File(...)` **does not** create a physical file/directory, does not verify that it exists, and does not automatically open a data stream. `File` only stores a path representation for I/O methods to use.

Commonly used checks:

| Method | Meaning to remember |
|---|---|
| `exists()` | Checks whether the path currently exists as observable by the runtime |
| `isDirectory()` | Checks whether the path currently refers to a directory |
| `isFile()` | Checks whether the path currently refers to a regular file |
| `getName()` | The last name component of the path, excluding the parent |
| `getPath()` | The path string represented by `File` |
| `getAbsolutePath()` | The absolute path form as resolved by the runtime |
| `getCanonicalPath()` | The canonical path form per filesystem rules; may throw `IOException` |
| `toPath()` | Converts to `java.nio.file.Path`, convenient when using NIO.2 |

**Note:** The result of `exists()`, `isFile()`, or `isDirectory()` only describes the state at the moment of the check. Immediately afterward, the file could be renamed, deleted, or replaced by another process; therefore do not use a "check-then-act" sequence as an absolute locking or security mechanism.

A path to a directory is a `File` object; listing a directory is the actual I/O action. The `list` and `listFiles` methods only list **direct children**; they do not automatically traverse subdirectories.

## 2. API Map for `list` and `listFiles`

| Method | Return type | Filter | Result content |
|---|---|---|---|
| `dir.list()` | `String[]` or `null` | None | Names of direct entries in the directory |
| `dir.list(FilenameFilter filter)` | `String[]` or `null` | `accept(File dir, String name)` | Names of entries accepted by the filter |
| `dir.listFiles()` | `File[]` or `null` | None | `File` objects for direct entries |
| `dir.listFiles(FilenameFilter filter)` | `File[]` or `null` | Filter by parent and name | `File` objects corresponding to accepted entries |
| `dir.listFiles(FileFilter filter)` | `File[]` or `null` | `accept(File pathname)` | `File` objects accepted by the filter |

Hypothetical directory example:

```text
data/
├── README.md
├── notes.txt
├── photo.png
└── images/
    └── icon.png
```

If `File dir = new File("data")`:

- `dir.list()` gives an array of direct names: `README.md`, `notes.txt`, `photo.png`, `images` (order is **not guaranteed**).
- `dir.listFiles()` gives `File` objects corresponding to `data/README.md`, `data/notes.txt`, `data/photo.png`, `data/images` (path representation depends on the operating system).
- `icon.png` is **not** in the result of either call above, because it is at a deeper level.
- `list` can return names of **both files and directories**; a name containing an extension does not by itself prove it is a regular file.
- The resulting array can be empty, yet an empty array is **different from `null`**.

These methods do not guarantee any sort order. If presenting results to users, comparing in unit tests, or needing a deterministic processing order, **sort explicitly**.

## 3. `list()`: Getting `String[]` Names

```java
File dir = new File("data");
String[] names = dir.list();

if (names == null) {
    System.err.println("Cannot list directory");
} else {
    Arrays.sort(names);
    for (String name : names) {
        System.out.println(name);
    }
}
```

This is an **illustrative snippet**, requiring `import java.io.File;`, `import java.util.Arrays;`, and an existing `data` directory to obtain real data.

Key points:

1. `list()` returns the **name** of each entry, **not** the full path.
2. If you need to open an entry, you must combine the name with the directory: `new File(dir, name)` or `dir.toPath().resolve(name)`.
3. If the directory is empty, the result is normally `new String[0]`, not `null`.
4. If the path **does not point to a directory** or an I/O error occurs while listing, `list()` may return `null`. In addition, the API may throw `SecurityException` when permission checks fail under the relevant environment/security manager; do not assume all errors are only reported via `null`.
5. The value returned by `list()` is only a **snapshot of the listing result for that call**; the filesystem can change immediately afterward.

When you only need to display names, filter extensions, or populate a list of names, `String[]` is very convenient. When you need to check `isFile()`, `length()`, `lastModified()`, or manipulate files, `File[]` usually makes code clearer.

## 4. `listFiles()`: Getting `File[]` Objects

```java
File[] children = dir.listFiles();

if (children == null) {
    System.err.println("Cannot list directory");
} else {
    Arrays.sort(children, Comparator.comparing(File::getName));
    for (File child : children) {
        System.out.println(
            child.getName() + " / isFile=" + child.isFile()
        );
    }
}
```

This is an **illustrative snippet** with `dir` of type `File`; requires importing `java.io.File`, `java.util.Arrays`, `java.util.Comparator`.

Each element of `File[]` represents a path to an entry **inside the directory**. A `File` object does not itself guarantee that the entry still exists when you call `isFile()`; the check result is provided by the operating system at the time of the call.

**Do not confuse `File[]` with open files.** Getting a `File` array does not mean Java is holding an `InputStream` or file descriptor for each entry, and there is no `close()` for plain `File` objects.

### Common Choices

- Want to receive **names** and process them yourself: `list()`.
- Want to check entry types or metadata: `listFiles()`.
- Want both parent and name passed to the callback to decide: `FilenameFilter`.
- Want the callback to receive the pathname object directly: `FileFilter`.

For example, calling `listFiles()` on a regular file instead of a directory can also return `null`, not an array containing that file itself.

## 5. `FilenameFilter`: Receives `dir` and `name`

The `java.io.FilenameFilter` interface is a **functional interface** with one abstract method:

```java
boolean accept(File dir, String name);
```

This is an **illustrative signature**, not a top-level function for standalone compilation.

- `dir`: the directory being listed.
- `name`: the **simple** name of an entry directly inside that directory.
- Returning `true`: includes the entry in the result.
- Returning `false`: excludes the entry from the result.

Example selecting only names ending in `.txt`:

```java
FilenameFilter onlyTxt =
    (parent, name) -> name.endsWith(".txt");

String[] txtNames = dir.list(onlyTxt);
File[] txtEntries = dir.listFiles(onlyTxt);
```

This is an **illustrative snippet**, requiring `import java.io.File` and `import java.io.FilenameFilter`; `dir` is a directory `File`.

Both calls share the same acceptance condition but differ in return type: `String[]` and `File[]`.

If you need to check the entry type while still using `FilenameFilter`:

```java
FilenameFilter onlyTxtFiles = (parent, name) -> {
    File candidate = new File(parent, name);
    return candidate.isFile() && name.endsWith(".txt");
};
```

**Right:** Combine directory and name using `new File(parent, name)`. **Wrong:** `new File(name)` if expecting to check a path inside `parent`: a relative path can be resolved against the JVM's working directory, leading to checking the wrong place.

### Distinguishing Extensions and Real Files

`name.endsWith(".txt")` only inspects the **name string**, so **a directory named `backup.txt` can still be accepted**. If business logic requires a *regular file* with a `.txt` extension, you must combine an `isFile()` check with the name check.

### Case Sensitivity

`name.endsWith(".txt")` does not select `README.TXT`. If the policy allows case-insensitive names:

```java
FilenameFilter caseInsensitiveTxt =
    (parent, name) ->
        name.toLowerCase(Locale.ROOT).endsWith(".txt");
```

This is an **illustrative snippet**, requiring `import java.util.Locale;`. `Locale.ROOT` helps avoid depending on the user's locale for technical name comparison rules. However, that is still only an **application filtering policy**: it does not mean the filesystem on every platform is case-insensitive, and for Unicode there are case-mapping situations that cannot be handled completely with a single `toLowerCase`.

## 6. `FileFilter`: Receives a `File` Path

The `java.io.FileFilter` interface is also a **functional interface**:

```java
boolean accept(File pathname);
```

This is an **illustrative signature**, not a standalone program.

Unlike `FilenameFilter`, the callback directly receives a `File` object representing the entry; this is very convenient for checking **regular file**, **directory**, **size**, **modification time**, or path-related conditions.

```java
FileFilter onlyRegularFiles = File::isFile;
FileFilter directoriesOnly = File::isDirectory;
FileFilter nonEmptyLogs = file ->
    file.isFile()
        && file.getName().endsWith(".log")
        && file.length() > 0L;

File[] regular = dir.listFiles(onlyRegularFiles);
File[] folders = dir.listFiles(directoriesOnly);
File[] logs = dir.listFiles(nonEmptyLogs);
```

This is an **illustrative snippet**, requiring `java.io.File` and `java.io.FileFilter`, with `dir` pointing to a directory. Check for `null` after each call before iterating over the results.

**Method difference:** `FileFilter` is used with `listFiles(FileFilter)`; **there is no `list(FileFilter)` overload**. If you only want a name array yet the condition needs to check file type, use `list(FilenameFilter)` and build a `File` from `parent/name`, or use `listFiles(FileFilter)` and map `File::getName`.

### What If the Callback Is Expensive?

A `FileFilter` calling `isFile()` or `length()` may incur extra metadata queries to the filesystem for each entry. In very large directories or on remote storage, that can be time-consuming. If you only need to filter by name, a simple `FilenameFilter` is usually sufficient and avoids unnecessary metadata queries.

Do not rely on the count or invocation order of the `accept` callback as a stable contract for performing side effects (writing/deleting/renaming files). A filter should be **side-effect-free**, deciding quickly and consistently from the needed information.

## 7. Comparing `FilenameFilter` and `FileFilter`

| Criterion | `FilenameFilter` | `FileFilter` |
|---|---|---|
| Method | `accept(File dir, String name)` | `accept(File pathname)` |
| Direct arguments | Parent directory + child name | `File` representing child path |
| `list(FilenameFilter)` | Yes | No `list(FileFilter)` |
| `listFiles(...)` | Yes | Yes |
| Suited for | Filtering names, patterns, file extensions | Filtering by file type, attributes, and path |
| Checking `isFile()` | Construct `new File(dir, name)` yourself | Call on `pathname` |
| Two-parameter lambda | `(dir, name) -> ...` | No |
| One-parameter lambda | No | `file -> ...` |

Example comparing the same condition, selecting regular `.csv` files:

```java
FilenameFilter a = (parent, name) ->
    name.endsWith(".csv")
        && new File(parent, name).isFile();

FileFilter b = pathname ->
    pathname.isFile()
        && pathname.getName().endsWith(".csv");

File[] usingA = dir.listFiles(a);
File[] usingB = dir.listFiles(b);
```

This is an **illustrative snippet**, requiring importing `File`, `FileFilter`, `FilenameFilter`. Both express the same intent provided the filesystem does not change and the check conditions are equivalent. They do not guarantee identical results if the directory changes **between the two calls**.

### Two `listFiles` Overloads Can Cause Confusion

There are two overloads with the same name: `listFiles(FilenameFilter)` and `listFiles(FileFilter)`. With lambdas, the parameter count normally lets the compiler disambiguate:

```java
dir.listFiles((parent, name) -> name.endsWith(".txt"));
dir.listFiles(file -> file.isFile());
```

This is an **illustrative snippet**; the two-parameter lambda corresponds to `FilenameFilter`, and the one-parameter lambda corresponds to `FileFilter`.

**Watch out:** Calling `dir.listFiles(null)` can be **ambiguous at compile time** because both overloads accept a reference type and neither overload is more specific. If you genuinely want no filtering, use `dir.listFiles()` instead of passing `null`.

## 8. Complete Java 17 Example: Five Listing Methods and Sorting

The program creates a temporary directory itself with three files and one subdirectory. All output is sorted so it does not depend on the filesystem's listing order.

Save **`FileListingDemo.java`**:

```java
import java.io.File;
import java.io.FileFilter;
import java.io.FilenameFilter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;

public class FileListingDemo {
    private static String sorted(String[] names) {
        if (names == null) {
            return "<null>";
        }
        Arrays.sort(names);
        return Arrays.toString(names);
    }

    private static String sorted(File[] files) {
        if (files == null) {
            return "<null>";
        }
        Arrays.sort(files, Comparator.comparing(File::getName));
        String[] names = Arrays.stream(files)
            .map(File::getName)
            .toArray(String[]::new);
        return Arrays.toString(names);
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("file-list-");

        try {
            Files.writeString(
                root.resolve("notes.txt"),
                "note",
                StandardCharsets.UTF_8
            );
            Files.writeString(
                root.resolve("photo.png"),
                "not a real image",
                StandardCharsets.UTF_8
            );
            Files.writeString(
                root.resolve("readme.md"),
                "readme",
                StandardCharsets.UTF_8
            );
            Files.createDirectory(root.resolve("sub"));

            File directory = root.toFile();
            FilenameFilter txt = (parent, name) ->
                name.endsWith(".txt");
            FilenameFilter markdown = (parent, name) ->
                name.endsWith(".md");
            FileFilter regular = File::isFile;
            FileFilter folders = File::isDirectory;

            System.out.println(
                "list(): " + sorted(directory.list()));
            System.out.println(
                "listFiles(): " + sorted(directory.listFiles()));
            System.out.println(
                "list(txt): " + sorted(directory.list(txt)));
            System.out.println(
                "listFiles(markdown): " +
                    sorted(directory.listFiles(markdown)));
            System.out.println(
                "listFiles(regular): " +
                    sorted(directory.listFiles(regular)));
            System.out.println(
                "listFiles(folders): " +
                    sorted(directory.listFiles(folders)));

            File missing = root.resolve("absent").toFile();
            System.out.println(
                "missing list() is null: " +
                    (missing.list() == null));
        } finally {
            Files.deleteIfExists(root.resolve("notes.txt"));
            Files.deleteIfExists(root.resolve("photo.png"));
            Files.deleteIfExists(root.resolve("readme.md"));
            Files.deleteIfExists(root.resolve("sub"));
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac FileListingDemo.java
java FileListingDemo
```

Stdout when filesystem operations succeed and no other process modifies the temporary directory:

```text
list(): [notes.txt, photo.png, readme.md, sub]
listFiles(): [notes.txt, photo.png, readme.md, sub]
list(txt): [notes.txt]
listFiles(markdown): [readme.md]
listFiles(regular): [notes.txt, photo.png, readme.md]
listFiles(folders): [sub]
missing list() is null: true
```

Explanation:

1. `list()` and `listFiles()` receive the four **direct children**.
2. `list(txt)` returns `String[]` containing only `notes.txt`.
3. `listFiles(markdown)` returns `File[]` containing only `readme.md`.
4. `listFiles(regular)` excludes the `sub` directory; `listFiles(folders)` selects only `sub`.
5. The path `absent` does not exist, so `missing.list() == null`.
6. The `sorted(...)` helper sorts results before printing; **you must not claim** the API itself always returns that exact order.

The example uses `Files.createTempDirectory` and `Files.writeString` to set up the fixture; the main explanation remains the **legacy** APIs of `java.io.File`. `Files.writeString` has been available since Java 11+, fitting the Java 17 requirement. The dummy file `photo.png` merely illustrates that **a file extension does not prove content format**.

The `finally` block deletes entries by fixed names. If creating a file fails before reaching the listing section, `deleteIfExists` helps clean up already-created items; cleanup errors can throw `IOException`. In production code, you need a temporary-file cleanup mechanism that preserves the original failure cause when that matters. Do not run automatic deletion code on directories containing user data.

## 9. Java 17 Example: Same Name Suffix, Different Entry Type

Sometimes using just `name.endsWith(".csv")` is not enough. The following program creates two files with a `.csv` suffix and a **directory** also ending in `.csv`, then compares name-based filtering with metadata-based filtering.

Save **`FileFilterVsFilenameFilterDemo.java`**:

```java
import java.io.File;
import java.io.FileFilter;
import java.io.FilenameFilter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class FileFilterVsFilenameFilterDemo {
    private static String names(File[] files) {
        if (files == null) {
            return "<null>";
        }
        String[] values = Arrays.stream(files)
            .map(File::getName)
            .sorted()
            .toArray(String[]::new);
        return Arrays.toString(values);
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("filter-demo-");

        try {
            Files.writeString(root.resolve("empty.csv"), "");
            Files.writeString(root.resolve("filled.csv"), "id\n1\n");
            Files.createDirectory(root.resolve("archive.csv"));

            File directory = root.toFile();

            FilenameFilter bySuffix =
                (parent, name) -> name.endsWith(".csv");

            FileFilter realCsvFiles = file ->
                file.isFile()
                    && file.getName().endsWith(".csv");

            FileFilter nonEmptyCsvFiles = file ->
                file.isFile()
                    && file.getName().endsWith(".csv")
                    && file.length() > 0;

            System.out.println("suffix: " +
                names(directory.listFiles(bySuffix)));
            System.out.println("regular: " +
                names(directory.listFiles(realCsvFiles)));
            System.out.println("nonempty: " +
                names(directory.listFiles(nonEmptyCsvFiles)));
        } finally {
            Files.deleteIfExists(root.resolve("empty.csv"));
            Files.deleteIfExists(root.resolve("filled.csv"));
            Files.deleteIfExists(root.resolve("archive.csv"));
            Files.deleteIfExists(root);
        }
    }
}
```

Run:

```bash
javac FileFilterVsFilenameFilterDemo.java
java FileFilterVsFilenameFilterDemo
```

Stdout when directory creation/reading succeeds:

```text
suffix: [archive.csv, empty.csv, filled.csv]
regular: [empty.csv, filled.csv]
nonempty: [filled.csv]
```

Explanation of each filter:

- `bySuffix` checks only the **name**, so the `archive.csv` directory is also accepted.
- `realCsvFiles` requires `isFile()`, so it excludes the directory.
- `nonEmptyCsvFiles` additionally requires `length() > 0`; since `filled.csv` contains `id\n1\n`, only it is selected.

`File.length()` is meaningful for regular files, yet cannot replace a file-content verification process. If the file changes between filtering and opening, its size or entry type may differ; `isFile()` and `length()` are **point-in-time state queries**, not atomic transactions.

### Filtering by Name Does Not Equal Filtering Content

A file named `report.csv` can still contain malformed binary data that is not valid CSV. If the application must process real CSV, after listing you need to open and parse the content with an appropriate parser, checking charset, schema, escaping, and handling errors.

## 10. Returning `null`, Empty Arrays, and Permission Errors

The most error-prone aspect of the `list` family is that **the result is not always a valid array**.

| Case | Reasonable expectation |
|---|---|
| Directory exists, accessible, no entries | `String[0]` or `File[0]` |
| Directory exists, has n entries and listing succeeds | Array of n elements (or fewer with a filter) |
| Path does not exist | `null` |
| Path points to a file, not a directory | `null` |
| I/O error while listing | May return `null` |
| Runtime security permission violation | May throw `SecurityException` |
| Permissions or filesystem change unexpectedly | Neither `null` nor stale results can serve as sole diagnostics |

**`null` does not state the exact cause.** Do not turn `null` into "empty directory." Wrong example:

```java
for (File f : dir.listFiles()) {
    System.out.println(f.getName());
}
```

This is a **counterexample**: if `listFiles()` returns `null`, the for-each loop will throw `NullPointerException`.

A minimal safeguard:

```java
File[] entries = dir.listFiles();
if (entries == null) {
    throw new IllegalStateException(
        "Cannot list directory: " + dir);
}
for (File entry : entries) {
    System.out.println(entry.getName());
}
```

This is an **illustrative snippet**; the variable `dir` is a `File`. Throwing `IllegalStateException` works for a simple example, yet does not preserve the underlying `IOException` cause, which the `listFiles()` API does not directly expose. If detailed error handling is an important requirement, consider NIO.2 APIs such as `Files.newDirectoryStream()` or `Files.list()`, which report errors more clearly.

### Should You Call `isDirectory()` First?

You can write:

```java
if (!dir.isDirectory()) {
    System.err.println("Not a readable directory: " + dir);
    return;
}
File[] entries = dir.listFiles();
if (entries == null) {
    System.err.println("Listing failed: " + dir);
    return;
}
```

This is **illustrative code inside a method returning `void`**; if placed elsewhere, adjust the `return`. However, `isDirectory()` returning `true` **does not guarantee** `listFiles()` will succeed; the filesystem may change and access permissions may differ. Handling `null` after the call is still mandatory.

## 11. Element Order and How to Sort

The JDK **does not specify the return order** of `list` or `listFiles`. Do not build logic relying on assumptions like "creation order," "name order," or "newest first."

Sorting names:

```java
String[] names = dir.list();
if (names != null) {
    Arrays.sort(names);
}
```

Sorting `File[]` by name:

```java
File[] files = dir.listFiles();
if (files != null) {
    Arrays.sort(files, Comparator.comparing(File::getName));
}
```

These are **illustrative snippets**, requiring imports for `Arrays`, `Comparator`, `File`.

- `Arrays.sort(names)` compares Unicode strings according to `String.compareTo`; that is not equivalent to culturally aware alphabetical sorting (e.g., Vietnamese collation).
- If language/locale-appropriate ordering is needed, consider `Collator` with an explicitly declared locale.
- If you only need a deterministic order in tests, a name comparator is sufficient since names are unique within a single directory.
- Sorting huge arrays consumes extra memory/time; for listings with millions of entries, consider streaming pipelines/limiting input.

Do not compare the actual result of `listFiles()` against an expected array by **index** unless both have been sorted.

## 12. Not Automatically Recursive: You Must Actively Traverse Subdirectories

Given the structure:

```text
root/
├── top.txt
└── child/
    └── nested.txt
```

`new File("root").listFiles()` only gives `top.txt` and the `child` directory; it does **not** give `nested.txt`.

A conceptual recursive example:

```java
static void visit(File directory) {
    File[] children = directory.listFiles();
    if (children == null) {
        return; // Needs an application-appropriate error-reporting policy.
    }
    for (File child : children) {
        if (child.isDirectory()) {
            visit(child);
        } else if (child.isFile()) {
            System.out.println(child.getPath());
        }
    }
}
```

This is an **illustrative snippet**, not a standalone program. It is intentionally simplified and **unsuitable for use as-is on untrusted trees**, because:

- A symlink to a directory can cause loops or escape outside the root if the implementation follows links and the application does not guard against them.
- Deep trees can cause `StackOverflowError`.
- Directories can change during traversal; `listFiles()` can return `null` which the example silently ignores.
- Listing millions of elements allocates large arrays.
- Permissions, remote filesystems, device nodes, or special paths may require dedicated policies.

For production code needing deep traversal, look at `Files.walkFileTree` with `FileVisitor`, depth limits, `FOLLOW_LINKS` policy, error handling, and cycle detection. If you only need one level, do not use recursion.

## 13. Security Concerns: Symlinks, Race Conditions, and User Data

`File.isFile()`, `isDirectory()`, and `listFiles()` observe **mutable** state. If an application scans a directory that untrusted users can modify, do not conclude that a pathname always points to the same object across steps:

```text
T1: listFiles() sees "upload.txt"
T2: isFile() returns true
T3: another process replaces "upload.txt" with another link/target
T4: application opens and processes that path
```

This is an example of **TOCTOU** (*time of check to time of use*). The check at T2 does not lock the object for the operation at T4.

Design-level precautions:

1. Do not trust filenames from uncontrolled sources; validate path constraints according to your system.
2. Do not rely solely on `getCanonicalPath()`, `isFile()`, or string `startsWith` to solve all symlink races. Checking and opening can still be two separate steps.
3. Use APIs and open flags per your desired policy: NIO.2 provides `LinkOption.NOFOLLOW_LINKS` for appropriate operations and `SecureDirectoryStream` on supporting providers; do not assume it is available on every filesystem.
4. Restrict allowed root access, OS permissions, depth, entry count, time, and processing resources.
5. When an application only analyzes ordinary data inside a directory it creates and controls itself, simple filters are usually enough; avoid overcomplicating if the threat model does not require it.

**`FileFilter` is not a security mechanism.** It is a callback deciding whether an entry appears in the listing result; it does not prevent other processes from modifying the directory and does not protect the subsequent file-open operation.

## 14. Legacy `java.io.File` Compared to NIO.2

APIs introduced in Java 7 in `java.nio.file` make error handling and directory traversal more flexible. This lesson focuses on `File`, yet you should know the migration path when writing new code.

| Need | `java.io.File` | Common NIO.2 |
|---|---|---|
| List direct children | `File.listFiles()` | `Files.list(Path)` |
| List children with filter | `listFiles(FileFilter)`, `listFiles(FilenameFilter)` | `Files.newDirectoryStream(Path, filter)` |
| Match filename glob only | `FilenameFilter` with condition | `Files.newDirectoryStream(dir, "*.txt")` |
| Walk directory tree | Manual recursion | `Files.walk` / `Files.walkFileTree` |
| Clearer `IOException` reporting | `listFiles()` may return `null` | `Files.list`/`DirectoryStream` report errors via exceptions |
| Listing lifecycle management | Arrays are not resources to close | Stream/directory stream needs `close()` |
| Modern filesystem features | Limited API | `Path`, `Files`, attributes, link options |

**`Files.list(Path)` returns a `Stream<Path>` that must be closed**; do not forget try-with-resources. The listing stream also does not guarantee order automatically; if output ordered by name is needed, sort explicitly. During traversal, late I/O errors can surface via `UncheckedIOException`.

`DirectoryStream<Path>` is often suitable when you want to iterate entries lazily/in batches without materializing the entire `File[]` at once. However, it does not sort automatically, does not recurse automatically, needs closing, and still faces mutable filesystem state issues.

### Java 17 Example: Comparing `listFiles` and `Files.list`

Save **`FileAndNioListingDemo.java`**:

```java
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FileAndNioListingDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nio-list-");

        try {
            Files.writeString(root.resolve("b.txt"), "b");
            Files.writeString(root.resolve("a.txt"), "a");

            File[] oldApi = root.toFile().listFiles();
            if (oldApi == null) {
                throw new IOException("Legacy listing failed");
            }
            String legacy = Arrays.stream(oldApi)
                .map(File::getName)
                .sorted()
                .collect(Collectors.joining(", "));

            String modern;
            try (Stream<Path> entries = Files.list(root)) {
                modern = entries
                    .map(path -> path.getFileName().toString())
                    .sorted()
                    .collect(Collectors.joining(", "));
            }

            System.out.println("File: " + legacy);
            System.out.println("NIO: " + modern);
        } finally {
            Files.deleteIfExists(root.resolve("a.txt"));
            Files.deleteIfExists(root.resolve("b.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Run:

```bash
javac FileAndNioListingDemo.java
java FileAndNioListingDemo
```

Stdout when file operations succeed:

```text
File: a.txt, b.txt
NIO: a.txt, b.txt
```

What this demonstrates: both APIs can list the same **direct entries**. The difference lies in the **return type and lifecycle mechanism**: `File[]` is an already-materialized array, whereas `Files.list` creates a `Stream<Path>` that must be closed to release resources. Do not use this example to conclude NIO sorts automatically; both branches call `sorted()`.

## 15. When to Use `list(FilenameFilter)` and When `listFiles(FileFilter)`?

### Case A — Selecting Configuration Names

Requirement: "List files named `config-*.properties` for display." If you only need names and naming rules, `list(FilenameFilter)` is concise:

```java
String[] configs = dir.list((parent, name) ->
    name.startsWith("config-") && name.endsWith(".properties")
);
```

This is an **illustrative snippet**. If you only want regular files, add `new File(parent, name).isFile()`; if you need complex patterns, consider globs from NIO.2.

### Case B — Selecting Log Files Larger Than 1 MiB

Requirement: "Only regular `.log` files larger than 1 MiB."

```java
FileFilter largeLogs = file ->
    file.isFile()
        && file.getName().endsWith(".log")
        && file.length() > 1024L * 1024L;

File[] result = dir.listFiles(largeLogs);
```

This is an **illustrative snippet**; `dir` is a `File`, requiring imports for `File` and `FileFilter`. `FileFilter` can read `File.length()` directly, yet the result is still a transient state; it does not replace checks during actual file opening/reading.

### Case C — Listing Only Subdirectories

```java
File[] directories = dir.listFiles(File::isDirectory);
```

This is an **illustrative snippet**. Java infers `FileFilter` from the one-parameter method reference. You must check for `null` like with any `listFiles` call.

### Case D — Wanting Only `.txt` Suffix and a `File[]` Result

```java
File[] texts = dir.listFiles(
    (parent, name) -> name.endsWith(".txt")
);
```

This is an **illustrative snippet**; the two-parameter lambda selects `FilenameFilter`, yet the return type is still `File[]`. Do not mistakenly believe "using `FilenameFilter` forces you to receive `String[]`": **the method you call** determines the return type.

## 16. Common Mistakes and How to Fix Them

1. **Not checking for `null` before iterating.** `list()`/`listFiles()` can fail; distinguish `null` from an empty array.
2. **Thinking `list()` returns full paths.** It returns child names; when opening, use `new File(parent, name)`.
3. **Using `new File(name)` inside `FilenameFilter` to inspect an entry.** This may check the wrong working directory; use `new File(dir, name)`.
4. **Thinking a `.txt` name is definitely a file.** A directory can also be named `archive.txt`; check the type when needed.
5. **Thinking `FileFilter` and `FilenameFilter` are interchangeable across every overload.** There is no `list(FileFilter)`; the two `listFiles` overloads accept different callback types.
6. **Assuming the result is already sorted.** The API makes no guarantee; sort results with an explicit comparator.
7. **Thinking `listFiles()` is recursive.** Direct children only; for recursion, design a traversal.
8. **Trusting `isDirectory()` before listing is enough.** The directory can vanish or permissions can change; still handle the result.
9. **Ignoring restricted permission cases.** The legacy API sometimes only returns `null` without detailed cause; use NIO.2 when specific error reporting is needed.
10. **Filtering by name and assuming content/format is also valid.** A file extension does not prove valid data; validate content when processing.
11. **Putting side effects inside `accept()`.** Filters should be pure inspection functions; avoid deleting/moving entries while listing.
12. **Using simple recursion on trees with uncontrolled symlinks.** Can cause loops, escaping root, or stack overflow; consider NIO.2 with a link policy.
13. **Ignoring TOCTOU.** `listFiles()` results do not guarantee the file still exists or was not replaced at open time.
14. **Reading a huge directory into `File[]` without considering memory.** At large scale, `DirectoryStream` and streaming traversal can be better.
15. **Forgetting to close `Files.list`/directory streams.** Unlike `File[]` arrays, these APIs hold resources that must be closed via TWR.
16. **Treating name comparison with `equalsIgnoreCase` as identical to filesystem semantics.** Each filesystem has its own path/case/Unicode comparison rules; an explicit application policy is required.
17. **Misunderstanding `FileFilter` as a security filter.** It only selects listing results, does not lock access permissions, and does not prevent concurrent entry modification.

## 17. Self-Check Exercises

**Q1.** What is the difference between `File.list()` and `File.listFiles()`?

**Answer:** `list()` returns `String[]` of entry names; `listFiles()` returns `File[]` representing entry paths. Both list direct children only and can return `null`.

**Q2.** Does `FilenameFilter.accept(File dir, String name)` receive `name` as a full path or a child name?

**Answer:** Child name. If you need to query the file, construct `new File(dir, name)`.

**Q3.** How do you filter `.csv` **files** while excluding directories also ending in `.csv`?

**Answer:** Use `FileFilter file -> file.isFile() && file.getName().endsWith(".csv")`, or `FilenameFilter` combined with `new File(dir, name).isFile()`.

**Q4.** Does `listFiles((parent, name) -> ...)` return `String[]` or `File[]`?

**Answer:** `File[]`. The two-parameter lambda selects the `FilenameFilter` overload; the method name `listFiles` determines the return type.

**Q5.** Does `listFiles()` returning `null` mean the directory is empty?

**Answer:** No. An empty directory normally returns a length-0 array; `null` can indicate it is not a directory or an I/O error. You must report an error instead of assuming empty.

**Q6.** Does the API guarantee files are returned in alphabetical name order?

**Answer:** No. You must sort yourself if a deterministic order is required.

**Q7.** Does `File.listFiles()` automatically fetch files in all nested subdirectories?

**Answer:** No. It only lists direct entries; you must actively traverse the tree or use NIO.2 traversal.

**Q8.** Why does checking `file.isFile()` and then calling `Files.readString(file.toPath())` still carry risk?

**Answer:** The file can be replaced/deleted between checking and reading (TOCTOU). Filter results do not lock file identity or state.

**Q9.** If you need to list a very large directory and get clearer error information, which API should you look at?

**Answer:** `Files.newDirectoryStream(Path)` or `Files.list(Path)`; use try-with-resources to close. For multi-level traversal, `Files.walk` or `Files.walkFileTree` as required.

**Q10.** When is filtering by name alone enough, and when should metadata be checked?

**Answer:** If the task only displays/selects names by pattern, a simple `FilenameFilter` is usually sufficient. When requiring regular files, directories, sizes, or attributes, `FileFilter` is more suitable; remember that metadata can still change during the actual operation.

## Summary

- `list()` and `list(FilenameFilter)` return **`String[]` of child names**.
- `listFiles()`, `listFiles(FilenameFilter)`, and `listFiles(FileFilter)` return **`File[]` of child paths**.
- `FilenameFilter` receives **`(dir, name)`**; `FileFilter` receives **`File pathname`**.
- Both API families list only **one level**, **do not guarantee order**, can return **`null`**, and do not prevent the filesystem from changing during processing.
- When you need sorting, entry type checks, deep traversal, TOCTOU mitigation, or better error handling, choose the appropriate API/approach—typically `Path` and NIO.2 for new code.

Understanding the differences between **name**, **path**, **entry type**, and **listing result** will help you use the legacy `java.io.File` class properly and avoid subtle I/O bugs.