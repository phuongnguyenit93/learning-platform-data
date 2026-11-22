# Directory Tree Traversal Order Is Not Automatically Your Desired Order

## 1. The Problem: “Traversable” Does Not Mean “Traversed in the Right Order”

In Java I/O, an application can list files using **`File.list()`/`listFiles()`**, **`Files.list(Path)`**, **`DirectoryStream`**, or walk an entire directory tree with **`Files.walk(Path)`** and **`Files.walkFileTree(...)`**. These APIs **discover and iterate over entries**, yet **do not guarantee ordering by name, modification date, size, file type, or any business order by default**.

For example, consider this tree:

~~~text
project/
├── zeta.txt
├── docs/
│   ├── chapter2.md
│   └── chapter1.md
└── alpha.txt
~~~

An application displaying a menu sorted by name might expect:

~~~text
alpha.txt
docs/
zeta.txt
~~~

However, **`Files.list(project)`** returns only direct entries under **`project`**, with **no alphabetical order guarantee**. On one machine, output may happen to match the desired order; on another machine, or after creating/deleting files or switching filesystems, the order can differ.

Another application may want to **walk the entire tree** branch by branch, or **delete files before deleting their parent directory**. That is a **different ordering problem** from global alphabetical sorting. We must distinguish **listing scope**, **tree-traversal strategy**, and **processing order**.

> Rule: **when order affects program correctness, define the rule explicitly and enforce it in code**. Never rely on whatever order the filesystem happens to return.

## 2. Three Easily Confused Concepts

| Concept | Question | Example |
| --- | --- | --- |
| **Scope** | Direct children only, or the whole tree? | **`Files.list(dir)`** gets direct children; **`Files.walk(root)`** descends into sublevels |
| **Traversal strategy** | Which branch first, parent or child first? | **`Files.walk`** traverses **depth-first**, each directory before entries inside it |
| **Sorting** | Among entries at the same level, which comes first? | Names A–Z, directories before files, ascending timestamp |

Even when an API specifies **depth-first**, that **does not mean** each subdirectory is visited alphabetically. “Depth-first” answers **how the tree structure is navigated**; “alphabetical” answers **how entries are compared**.

Also avoid guessing about filenames containing numbers: **`"file10.txt"`** comes **before `"file2.txt"`** under standard lexicographical character comparison because **`'1'`** precedes **`'2'`**. If natural numeric order is needed, provide a dedicated comparator.

## 3. Return Order of `File.list()` and `File.listFiles()`

Classic **`java.io.File`** API:

~~~java
File dir = new File("project");
String[] names = dir.list();
File[] entries = dir.listFiles();
~~~

This is an **illustrative snippet**, requiring importing **`java.io.File`**. These APIs list only **direct child entries**; they **do not descend into deeper levels**.

Neither method **guarantees the order** of the returned names or `File` objects. Therefore, never write:

~~~java
File[] entries = dir.listFiles();
File first = entries[0]; // Wrong if treated as the first file by name.
~~~

Beyond being unsorted, **`listFiles()` can return `null`** if the path is not a directory or an I/O error occurs; the snippet above could also crash on `null` or an empty array. You should check:

~~~java
File[] entries = dir.listFiles();
if (entries == null) {
    throw new IOException("Không thể liệt kê thư mục: " + dir);
}
Arrays.sort(entries,
        Comparator.comparing(File::getName));
for (File entry : entries) {
    System.out.println(entry.getName());
}
~~~

This is an **illustrative snippet**, requiring imports for **`java.io.File`**, **`java.io.IOException`**, **`java.util.Arrays`**, and **`java.util.Comparator`**. **`Arrays.sort`** imposes ordering by **`getName()`** on the **in-memory array**, without changing how entries are stored on the filesystem.

**Note:** the comparator in this example is case-sensitive and uses Java character ordering. It is not automatically natural-language order or a file manager's “folders first” convention.

## 4. `Files.list(Path)`: One Level, No Guaranteed Order

NIO API:

~~~java
try (Stream<Path> stream = Files.list(directory)) {
    stream.forEach(System.out::println);
}
~~~

This is an **illustrative snippet**, assuming **`directory`** is a `Path` and importing **`java.nio.file.Files`**, **`java.nio.file.Path`**, and **`java.util.stream.Stream`**, while handling `IOException`.

**`Files.list(directory)`** creates a stream of **direct entries** in `directory`. The Javadoc states **element order is not guaranteed**. The stream may be populated lazily; opening it holds a directory resource, so **`try-with-resources`** is required.

### 4.1. To Sort Names A–Z: Explicit `sorted()`

~~~java
try (Stream<Path> stream = Files.list(directory)) {
    stream.sorted(
            Comparator.comparing(p -> p.getFileName().toString()))
          .forEach(System.out::println);
}
~~~

This snippet requires importing **`java.util.Comparator`** and assumes the directory exists. It sorts by **child entry name**, not by full path. Since all entries are direct children of the same directory, this is usually the rule wanted for a single-level name listing.

If you only need names:

~~~java
try (Stream<Path> stream = Files.list(directory)) {
    List<String> names = stream
            .map(p -> p.getFileName().toString())
            .sorted()
            .toList();
    System.out.println(names);
}
~~~

This is a **code snippet**, requiring importing **`java.util.List`**. Java 16+ includes **`Stream.toList()`**, so it works on Java 17. Collecting and sorting makes the output independent of arbitrary filesystem order, **provided the entry set does not change during collection**.

**`sorted()` is a stateful operation**: to sort the entire list, it must retain the elements being compared. For directories with millions of files, memory and sorting costs can be substantial.

## 5. `Files.walk(Path)`: Depth-First Traversal, Does Not Visit Children by Name by Default

**`Files.walk(root)`** returns a stream traversing the file tree from `root`. Key contract points:

- Starts at **`root`**.
- Traverses **depth-first**, with **each directory emitted before its child entries** (*pre-order*).
- **Does not guarantee sibling order** within the same directory.
- By default **does not follow symbolic links** pointing to directories when descending; **`FileVisitOption.FOLLOW_LINKS`** is available if explicitly desired, along with cycle and access-boundary risks.
- The stream holds resources for open directories; it must be **closed**. During traversal, I/O errors can surface as **`UncheckedIOException`**.

Example:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.forEach(System.out::println);
}
~~~

This is an illustrative snippet assuming **`root`** is declared as a `Path`, with required imports and `IOException` handling. Never assume a subdirectory named “a” will always be visited before a subdirectory named “z.”

### 5.1. Pre-Order Does Not Mean Global Alphabetical Order

Suppose:

~~~text
root/
├── b.txt
└── docs/
    └── a.txt
~~~

In **pre-order depth-first**, upon choosing to enter **`docs`**, the stream emits **`docs`** before **`docs/a.txt`**; however, **`b.txt`** can appear either before or after the **`docs`** branch because sibling order is not guaranteed.

If you apply:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.sorted().forEach(System.out::println);
}
~~~

that performs a **global sort of `Path`s after traversal**, rather than instructing the filesystem to “walk branches alphabetically.” Both approaches may produce the **same final output sequence** under a given comparator, yet differ in **discovery timing** and do not turn the underlying traversal into a DFS with explicit sibling ordering.

**Traversing and acting immediately** (e.g., printing, copying, or deleting on the fly) differs from **collecting everything, sorting, and acting afterward**. When actions depend on parent/child order, an arbitrary sort cannot replace an appropriate traversal algorithm.

## 6. `Files.walkFileTree` and Pre/Post Directory Order

**`Files.walkFileTree`** invokes **`FileVisitor`** callbacks. Structurally significant callbacks are:

- **`preVisitDirectory(dir, attrs)`**: processes a directory **before** visiting entries inside it.
- **`visitFile(file, attrs)`**: processes a file (and non-directory entries or directories at depth limit).
- **`visitFileFailed(file, exc)`**: handles cases where an entry cannot be accessed.
- **`postVisitDirectory(dir, exc)`**: processes a directory **after** its entries have been visited (or after iteration stops early per contract).

Although callbacks define **before/after semantics per directory**, **the order among sibling children at the same level is still not guaranteed alphabetically**.

Several tasks require structural dependency order:

| Task | Required Order |
| --- | --- |
| Recreating a directory tree elsewhere | Usually **create parent directory before children**, i.e., pre-order for directories |
| Cleaning up a directory tree | **Delete files/children before deleting parent directory**, using `visitFile` + `postVisitDirectory` |
| Exporting a list sorted by name | May need **sibling sorting** or sorting all output names |
| Printing a pretty tree indented by level | **DFS structure + explicit sibling order**, not just a global sort |
| Picking the “newest” file | Sort by **actual timestamp** read from attributes, not by returned position |

When you only need order for **deleting children before parents**, **`walkFileTree`** with **`postVisitDirectory`** is far more suitable than assuming `Files.walk` can simply be reversed arbitrarily.

## 7. Complete Java 17+ Example: Same Tree, Sorted Explicitly for Determinism

The following program creates its own temporary directory so every run has a consistent data structure. It:

1. Creates **`a.txt`**, **`b.txt`**, directory **`docs`**, and **`docs/intro.txt`**, in an intentional creation order while **not relying on creation order when listing**.
2. Lists **one level** with `Files.list` and sorts by name.
3. Walks the **whole tree** with `Files.walk`, converts paths to relative paths so output contains no random temp directory name, and sorts for deterministic output.
4. Cleans up the tree **children before parent** using `FileVisitor`.

Save as **`TraversalOrderDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.List;
import java.util.stream.Stream;

public class TraversalOrderDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("traversal-order-");

        try {
            Files.writeString(root.resolve("b.txt"), "B");
            Path docs = Files.createDirectory(root.resolve("docs"));
            Files.writeString(docs.resolve("intro.txt"), "Intro");
            Files.writeString(root.resolve("a.txt"), "A");

            try (Stream<Path> stream = Files.list(root)) {
                List<String> children = stream
                        .map(path -> path.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("children=" + children);
            }

            try (Stream<Path> stream = Files.walk(root)) {
                List<String> tree = stream
                        .map(path -> {
                            String relative = root.relativize(path)
                                    .toString().replace('\\', '/');
                            return relative.isEmpty() ? "." : relative;
                        })
                        .sorted()
                        .toList();
                System.out.println("tree=" + tree);
            }
        } finally {
            // Delete only the temporary tree created by the program; do not follow links.
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.delete(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) {
                        throw exc;
                    }
                    Files.delete(dir); // Children were already visited/deleted first.
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac TraversalOrderDemo.java
java TraversalOrderDemo
~~~

Output when no external process interferes with the temporary directory:

~~~text
children=[a.txt, b.txt, docs]
tree=[., a.txt, b.txt, docs, docs/intro.txt]
~~~

**Why is the output deterministic?**

- **`children`** gets direct children and sorts by `String` filename, so **`a.txt`** comes before **`b.txt`**, then **`docs`**.
- **`tree`** converts absolute paths to relative names and normalizes separators to **`/`** before sorting: the root path is represented as **`"."`**; lexicographical order is **`.`**, **`a.txt`**, **`b.txt`**, **`docs`**, **`docs/intro.txt`**.
- Creating **`b.txt` before `a.txt`** does not affect the sorted results.
- The **`finally`** block does not rely on alphabetical order for deletion: `FileVisitor` deletes each file in **`visitFile`** and each directory in **`postVisitDirectory`**, ensuring children are processed before parents during successful traversal.

**Example limitations:** if an I/O error, permission conflict, or concurrent modification by another process occurs during traversal, the program may throw `IOException` instead of printing both lines; the filesystem itself does not create an automatic immutable snapshot just because `Files.list`/`Files.walk` was called.

## 8. To Traverse Each Branch by Name: Sort Siblings Before Recursing

Sorting all results of **`Files.walk(root).sorted(...)`** works well when you only need a **final list**. However, if you must **traverse and perform actions on the fly in per-directory order**, sort the **direct children** before recursing into each branch.

Java method pattern:

~~~java
static void visitByName(Path root, Path current) throws IOException {
    System.out.println(root.relativize(current));

    try (Stream<Path> entries = Files.list(current)) {
        List<Path> children = entries
                .sorted((left, right) -> left.getFileName().toString()
                        .compareTo(right.getFileName().toString()))
                .toList();

        for (Path child : children) {
            if (Files.isDirectory(child,
                    java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                visitByName(root, child);
            } else {
                System.out.println(root.relativize(child));
            }
        }
    }
}
~~~

This is an **illustrative method**, not standalone runnable code: it must be placed in a class with imports for **`java.nio.file.Files`**, **`java.nio.file.Path`**, **`java.util.List`**, **`java.util.stream.Stream`**, and **`java.io.IOException`**. When called with a directory `root`, it performs a depth-first traversal with **child entries sorted by name**.

If you want to display **directories before files**, use a comparator comparing entry type first, then name:

~~~java
Comparator<Path> foldersFirst = Comparator
        .comparing((Path p) -> !Files.isDirectory(
                p, LinkOption.NOFOLLOW_LINKS))
        .thenComparing(p -> p.getFileName().toString());
~~~

This is an **illustrative snippet** requiring imports for **`java.util.Comparator`**, **`java.nio.file.Files`**, **`java.nio.file.LinkOption`**, and **`java.nio.file.Path`**. Boolean **`false`** (directory) sorts before **`true`** (non-directory). If grouping by type is required, do not expect a bare **`String` sort** to do it automatically.

**Warning:** checking **`Files.isDirectory`** inside a comparator can observe changing state if the directory is modified concurrently; for data requiring consistency, collect metadata into record objects first and sort the snapshot, while handling access errors explicitly. On trees with symlinks, decide whether to **follow symlinks** or treat symlinks as entries. The pattern above does not descend into symlinked directories because it uses `NOFOLLOW_LINKS`.

## 9. Ordering by Name, Number, Time, or Size: Choose a Comparator by Requirement

| Requirement | Appropriate Approach | Notes |
| --- | --- | --- |
| Names A–Z by Java characters | **`Comparator.comparing(p -> p.getFileName().toString())`** | Case-sensitive; no “natural number order” |
| Case-insensitive names | **`String.CASE_INSENSITIVE_ORDER`**, plus tie-breaker on original name | Avoids input-dependent ties when two names differ only in case |
| UI sorted by user's language | **`Collator`** with explicit `Locale` | Language, accent, and equivalence rules differ from `compareTo`; add a tie-breaker if determinism is required |
| Most recently modified files first | Read **`Files.getLastModifiedTime`**, sort descending | Timestamps can tie—add a tie-breaker; metadata may change while reading |
| Largest files first | Read **`Files.size`**, sort descending | `Files.size` may fail or not reflect a simultaneous snapshot |
| Directories first, files second | Comparator by **entry type**, then name | Use `NOFOLLOW_LINKS` if symlinks should not be treated as directories |
| Numeric names with “file2” before “file10” | Custom **natural numeric comparator** under your control | Not the default order of `String.compareTo` |
| Custom domain order | Map names to **priority** then sort, with secondary order | Specify fallback rules for unlisted names |

### 9.1. Comparators Need a Tie-Breaker for Deterministic Output

If two entries are treated as **equal** by a comparator (for example, case-insensitive sorting on **`a.txt`** and **`A.txt`**), a stable sort **preserves the original relative order** of equal elements. Because the input order from `Files.list` is unguaranteed, **the final output can still vary**. Add a tie-breaker:

~~~java
Comparator<String> byName = String.CASE_INSENSITIVE_ORDER
        .thenComparing(Comparator.naturalOrder());
~~~

This snippet requires importing **`java.util.Comparator`**. It compares case-insensitively first, and on ties compares the original `String`s. That establishes a deterministic order even when the filesystem returns names in different orders.

Similarly, when sorting by modification time and two files share the same timestamp, sort secondarily by name for a stable rule.

### 9.2. Sorting by Metadata: Separate Reading From Comparing

With modification time or size, reading file attributes can throw `IOException`; never hide `IOException` by returning a fallback default inside a comparator. A cleaner design:

1. List the target paths.
2. Read the attributes of interest for each path, handling errors explicitly.
3. Construct records containing `Path` + read attributes.
4. Sort the list of records with a comparator having primary/secondary criteria.
5. Process the resulting order.

An in-memory metadata snapshot still does not **lock the filesystem**: if a file changes after attributes are read, actual contents may differ. When an action depends on current metadata, re-verify or handle concurrency at the appropriate layer.

## 10. Listing Multiple Times Is Not a Stable Snapshot

Even on the **same machine and same directory**, never assume two **`Files.list`** calls will always yield the same order or same entry set:

- Another program may create, delete, or rename files between calls.
- The filesystem may reorganize internal directory structures after mutations.
- Different filesystem providers (local disk, network share, archive, cloud mount) have different behaviors.
- System path-matching rules (case-sensitive/case-insensitive) differ from standard Java `String` sorting.
- Some listing APIs are **weakly consistent** and do not lock an atomic snapshot against concurrent modifications.

**Sorting solves ordering**, not **consistency of the file set**. If you must process an immutable set accurately, define a domain workflow (such as freezing the source, capturing the list with metadata and re-verifying, or using filesystem locks/snapshots if available).

In particular, never write:

~~~java
Path first = Files.list(directory).findFirst().orElseThrow();
~~~

to select “the first file by name.” Aside from **not closing the stream** in that snippet, no name criterion is applied, so the chosen file is nondeterministic. Instead, specify an explicit comparator and use `try-with-resources`.

## 11. Performance, Memory Limits, and Tree Depth

**`Files.list`** can enumerate a large directory lazily; **`Files.walk`** can traverse an entire tree without building the full list in RAM. However, once you add **`sorted()`**, sorting usually has to **collect all elements** before emitting results. With millions of entries, the memory footprint of `Path` objects, strings, metadata, and sorting can be huge.

If you need **alphabetical DFS**, you can sort **each directory's sibling set** before recursing, holding only one directory's list per recursion level. That avoids sorting the whole tree globally, though a single directory with huge fan-out still holds many entries; deep recursion can also cause **`StackOverflowError`** if unbounded Java recursion is used. For very deep trees, use an **explicit stack** or an alternative traversal design.

**`Files.walk(root, maxDepth)`** bounds the depth to read when you do not want to walk the whole tree. **`maxDepth = 0`** emits only `root`; level 1 includes `root` and direct children (if readable). **`Files.walkFileTree`** offers overloads accepting options and `maxDepth`. Bounding depth differs from sorting; choose both according to requirements.

When both filtering and sorting are needed, filter by logic first, then sort only the surviving elements. Still, when seeking “the first item in sorted order,” **`sorted().findFirst()`** generally must inspect every input element—it is not as cheap as taking the first element returned by the filesystem.

## 12. Traversing to Act: Dependency Order Matters, Not Just Name Order

### 12.1. Creating or Copying a Tree: Parents Before Children

When copying a directory tree to another location, the destination parent directory must exist before writing child files. You can use **`walkFileTree`** with **`preVisitDirectory`** to create destination directories before processing files.

**Do not sort `Files.walk` and assume every parent directory gets created automatically**: path order after sorting depends on the comparator; your code must define explicit parent-creation rules, or call **`Files.createDirectories(parent)`** intentionally where appropriate.

### 12.2. Deleting a Tree: Children Before Parents

When deleting a tree **you own and are authorized to delete**, a parent directory cannot be deleted while it still contains files or subdirectories. Use **`visitFile`** to delete files and **`postVisitDirectory`** to delete directories once finished.

**Do not rely on A–Z name order to infer safe deletion order.** A sorted list of paths does not guarantee “all children deleted before parent” if the wrong comparator is chosen. **`Files.walkFileTree`** expresses structural dependencies clearly; even so, deletion can still fail due to newly created files, missing permissions, or concurrent state.

### 12.3. Ordering Does Not Replace Error Handling

**`walkFileTree`** allows implementing **`visitFileFailed`** and handling errors delivered to **`postVisitDirectory`**. In strict pipelines, never swallow errors and report “fully traversed” or “cleanly deleted” when only partial work succeeded. Define a stop-or-continue policy and record failed entries.

## 13. Notes on Symbolic Links, Permissions, and Concurrent Modifications

Traversing an untrusted filesystem carries more risks than ordering alone:

1. **Symbolic links** can point outside root if the application enables `FOLLOW_LINKS`; by default `Files.walk`/`walkFileTree` do not follow links, though provider behavior must be understood.
2. **Link cycles** can occur with `FOLLOW_LINKS`. Java detects cycles and reports errors such as **`FileSystemLoopException`** when encountered.
3. Another user can **swap a symlink or path after you check it**. Checking a `Path` and then opening/deleting it is a TOCTOU race.
4. **`Files.isDirectory`** and **`Files.exists`** are not locks. An observed state is not guaranteed to hold until the next step.
5. Permissions can vary per branch; traversal tools must handle `IOException` and `UncheckedIOException`.
6. When traversing **to delete**, never substitute arbitrary user input as root in a cleanup snippet. In adversarial environments, consider handle-based directory operations or **`SecureDirectoryStream`** where supported.

Examples only delete **temporary directories created by the program itself**, keeping educational demos separate from arbitrary path-deletion tools.

## 14. Common Mistakes

1. **Assuming `File.listFiles` returns alphabetical names.** Not guaranteed by contract; sort explicitly.
2. **Relying on disk creation order.** Creation order and listing order are not a universal contract.
3. **Confusing `Files.list` with `Files.walk`.** `list` covers one level; `walk` can traverse the whole tree.
4. **Thinking `Files.walk` is alphabetical because it uses depth-first search.** DFS defines branch navigation, not sibling order.
5. **Printing `Files.walk` and then calling `.sorted()` on the same stream.** A consumed stream cannot be reused; assemble the pipeline in the right order before the terminal operation.
6. **Forgetting to close the `Stream` from `Files.list` / `Files.walk`.** Directory resources can remain held until closed.
7. **Using `sorted()` without understanding the comparator.** `String` sorting is case-sensitive and does not perform natural numeric or locale-aware sorting automatically.
8. **Lacking a tie-breaker when a comparator treats two names as equal.** Results may inherit the unspecified initial order.
9. **Using `Files.size` or `getLastModifiedTime` inside a comparator while swallowing `IOException`.** Can produce wrong order and hide errors; fetch metadata with proper error handling first.
10. **Assuming `sorted()` is free.** It buffers data, consuming CPU/RAM on huge directories.
11. **Using name order to delete a tree.** Deletion must follow children-before-parents dependency, not merely alphabetical order.
12. **Following symbolic links without bounding scope.** Can escape root or hit cycles.
13. **Ignoring filesystem mutations during traversal.** Sorting does not provide a consistent snapshot.
14. **Omitting depth or volume limits on untrusted trees.** Risks unbounded time, RAM, file count, and recursion depth.
15. **Treating `null` from `File.listFiles` as an empty array.** `null` can indicate a non-directory or an I/O error; distinguish them.
16. **Failing to separate sorting for display from ordering for operations.** Different tasks may require different algorithms.

## 15. Self-Check Questions

**Question 1:** Does `Files.list(dir)` guarantee the first file has the smallest name?  
**Answer:** No. To order by name, apply **`sorted(Comparator...)`** or collect and sort.

**Question 2:** How does `Files.walk(root)` traverse, and does it guarantee alphabetical order among siblings?  
**Answer:** It traverses **depth-first**, directories before their child entries, yet **does not guarantee alphabetical sibling order**.

**Question 3:** Why is `sorted()` on a `Files.walk` `Stream` different from “traversing each sorted branch”?  
**Answer:** `sorted()` orders the **global output list** after discovery; sorting siblings by name imposes order **before descending into each branch**. They differ in timing, memory usage, and side-effect ordering.

**Question 4:** Can `File.listFiles()` return `null`?  
**Answer:** Yes, if the `File` is not a directory or an I/O error occurs. Never call `Arrays.sort` directly without checking.

**Question 5:** When sorting names case-insensitively for a UI, how do you keep output deterministic when `"A.txt"` and `"a.txt"` tie?  
**Answer:** Add **`thenComparing(Comparator.naturalOrder())`** on the original name as a secondary criterion.

**Question 6:** When deleting an entire tree, should the parent directory be deleted in `preVisitDirectory` or `postVisitDirectory`?  
**Answer:** **`postVisitDirectory`**, after all children have been processed, paired with `visitFile`.

**Question 7:** Does sorting by `Files.getLastModifiedTime` create an atomic snapshot of the whole filesystem?  
**Answer:** No. Attributes can change while reading or traversing; design according to real consistency requirements.

**Question 8:** How many levels does `Files.walk(root, 0)` traverse?  
**Answer:** Only **`root`**. With `maxDepth` 1, it includes `root` and direct children when readable.

## 16. Conclusion

The order a filesystem returns when listing is not your business order. **`File.listFiles`**, **`Files.list`**, and **`DirectoryStream`** do not promise alphabetical order; **`Files.walk`** and **`walkFileTree`** provide ways to traverse a tree, yet **do not enforce sibling ordering by name**.

If the goal is an **A–Z list**, sort with an explicit comparator. If you need **DFS in A–Z sibling order**, collect and sort each level **before recursing**. If the task is **creating or deleting a tree**, prioritize **parent/child dependency order**, such as `preVisitDirectory` or `postVisitDirectory`. When results must be reproducible, also use tie-breakers, consistent charset/name comparison rules, and controls for source data mutations.

### References

- [Oracle Java SE 17 — File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): `list` and `listFiles` unguaranteed order, `null` return values, and direct children.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `list`, `walk`, `walkFileTree`, symlink handling, and resources.
- [Oracle Java SE 17 — FileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html): `preVisitDirectory`/`visitFile`/`postVisitDirectory` callbacks.
- [Oracle Java SE 17 — Stream.sorted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): sorting, ordering, stateful operations, and cost.
- [Oracle Java SE 17 — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): primary and secondary sorting criteria.
