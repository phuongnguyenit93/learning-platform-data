# resolve, resolveSibling, and joining paths in Java Path

`java.nio.file.Path` represents a **path** to a location in a file system. When working with multiple directories, files, and programmatically constructed names, use `Path.resolve(...)`, `Path.resolveSibling(...)`, and `Path.of(...)` to join components instead of manually concatenating `/` or `\` strings.

Remember immediately: **creating or transforming a `Path` does not create directories, does not create files, and does not read content**. Only when calling I/O operations such as `Files.createDirectories`, `Files.writeString`, or `Files.newInputStream` does the program actually interact with data at that path.

## 1. Distinguishing the three main operations

| API | Idea | Relative path example |
| --- | --- | --- |
| `Path.of(first, more...)` | Creates a path from the provided components | `Path.of("data", "2026", "report.txt")` |
| `base.resolve(child)` | Resolves `child` **against `base`**, treating `base` as a directory location in the usual case | `Path.of("data").resolve("report.txt")` |
| `path.resolveSibling(name)` | Replaces the last name with a sibling name, based on the **parent directory** of `path` | `Path.of("data", "old.txt").resolveSibling("new.txt")` |

To visualize easily:

```text
Path.of("reports", "2026")          -> reports/2026
  .resolve("summary.txt")           -> reports/2026/summary.txt

Path.of("reports", "2026", "old.txt")
  .resolveSibling("new.txt")        -> reports/2026/new.txt
                                      ^ keeps parent directory; replaces last name
```

The `/` character in the diagram is only to help the reader visualize. When displaying a path on Windows, the separator is typically `\`. Do not write tests that depend on separator strings if you want the code to run across multiple operating systems.

## 2. `Path.of(...)` creates a path object

`Path.of` is a factory method available since Java 11 for creating a `Path`:

```java
import java.nio.file.Path;

Path file = Path.of("workspace", "docs", "guide.txt");
Path directory = Path.of("workspace", "docs");
Path current = Path.of(".");
```

The lines above are illustrative declarations; they must be placed inside a class/method. They only create path objects: **`workspace` and `docs` do not need to exist**.

`Path.of("workspace", "docs", "guide.txt")` is generally more readable and separator-safe than manually joining `"workspace/" + "docs/" + "guide.txt"`. A few notes:

- Path components must conform to the syntax of the current **filesystem provider**. Invalid names may cause `InvalidPathException` to be thrown when creating the `Path`.
- `Path.of` does not check read/write permissions or file existence.
- `Path` is an object representing a name/location; the object returned by `resolve` or `normalize` is a new result path and does not mutate the original `Path`.
- `Path.of("report.txt")` is a single-component relative path; it **does not itself have a parent directory** within that object: `getParent() == null`.

In Java 7–10, the common approach is `Paths.get(...)`; with Java 17+, `Path.of(...)` is usually clearer.

## 3. `resolve(...)` — moving from a logical base directory to a child location

Example:

```java
Path base = Path.of("storage", "documents");
Path report = base.resolve("2026").resolve("report.txt");
```

The result is equivalent to the path constructed with `Path.of("storage", "documents", "2026", "report.txt")` on the same provider.

`resolve` has two common overloads:

```java
Path child1 = base.resolve("image.png");             // String
Path child2 = base.resolve(Path.of("2026", "data"));  // Path
```

When the argument `other` is a normal **relative** path, the method appends its components to `base`. `resolve` does not read content and does not check whether the child file exists.

### `base` is treated as a directory

Consider:

```java
Path path = Path.of("images", "photo.jpg");
Path unexpected = path.resolve("thumbnail.jpg");
```

In terms of name joining, the result will have components `images/photo.jpg/thumbnail.jpg`. `resolve` **does not know** that `photo.jpg` is a regular file; it simply treats the path on the left as the location under which to place the child path. To get `images/thumbnail.jpg`, use `path.resolveSibling("thumbnail.jpg")` or `path.getParent().resolve("thumbnail.jpg")` after checking that parent exists.

### Absolute arguments and rooted paths

With relative paths, `resolve` produces predictable concatenation results. With an **absolute path** argument, the usual rule is that the result is the passed absolute path itself; cases involving OS- or provider-specific root/drive paths should be handled carefully.

For applications that **only allow relative filenames**, validate with `child.isAbsolute()` before calling `base.resolve(child)`, and also check `..`. Do not treat `resolve` itself as a path traversal defense.

### Empty names and special paths

`Path` can represent an empty path and `.`, `..` components. `resolve` does not necessarily remove all special components automatically; if you want to simplify *syntactically*, call `normalize()`. Syntactic normalization does not confirm that the path exists or is safe against symbolic links.

## 4. `resolveSibling(...)` — sibling paths

`resolveSibling` uses the **parent of the current path** as the base for resolving the supplied path:

```java
Path oldFile = Path.of("reports", "2026", "old.csv");
Path newFile = oldFile.resolveSibling("new.csv");
```

The result is a path with components `reports/2026/new.csv`, i.e., **two sibling files in the `2026` directory**. This is a name-joining operation; it **does not rename the actual file**.

Compare:

```java
Path original = Path.of("reports", "old.csv");

Path child = original.resolve("new.csv");
// reports/old.csv/new.csv : treats original as a directory location.

Path sibling = original.resolveSibling("new.csv");
// reports/new.csv : uses the parent of original.
```

`resolveSibling` is useful when you need to build a "same directory, different name" path, for example:

- Original file `orders.csv` and output file `orders-clean.csv`.
- Configuration file `service.yml` and backup file `service.yml.bak`.
- Temporary file created in the same directory to prepare for replacement.
- Original image `photo.jpg` and thumbnail `photo-thumb.jpg`.

However, actual write/rename/move operations must call the `Files` API; `resolveSibling` alone **does not create or modify** any file.

### Case with no parent

For `Path.of("readme.md")`, `getParent()` returns `null`; by contract, `resolveSibling("other.md")` returns the supplied `other.md` path (instead of throwing `NullPointerException` due to having no parent).

```java
Path file = Path.of("readme.md");
Path renamed = file.resolveSibling("other.md");

System.out.println(renamed.equals(Path.of("other.md"))); // true
```

Therefore, when joining with `getParent()` manually, **you must handle `null` yourself**, whereas `resolveSibling` provides defined behavior for this situation.

## 5. Table illustrating child paths and sibling paths

Suppose:

```java
Path base = Path.of("projects", "demo");
Path file = base.resolve("README.md");
```

| Expression | Result components | Meaning |
| --- | --- | --- |
| `base.resolve("src")` | `projects / demo / src` | Logical subdirectory |
| `base.resolve(Path.of("src", "Main.java"))` | `projects / demo / src / Main.java` | File under `src` |
| `file.resolveSibling("LICENSE")` | `projects / demo / LICENSE` | Another name at the same level as `README.md` |
| `base.resolveSibling("demo-backup")` | `projects / demo-backup` | Sibling path to the **directory** `demo` |
| `file.resolve("LICENSE")` | `projects / demo / README.md / LICENSE` | Not a sibling; easy mistake if `README.md` is a file |

Point to emphasize: `resolveSibling` is not only for files. When called on a **directory path**, it creates a sibling path to that directory within the same parent (according to path logic).

## 6. Complete Java 17+ program: joining paths without creating files

The following example verifies relationships using `Path.equals`, `getFileName`, and `getParent` so that the output **does not depend on the separator character** between Windows/Linux. There are no read, write, or file-creation calls.

Save as **`PathComposeDemo.java`**:

```java
import java.nio.file.Path;

public class PathComposeDemo {

    public static void main(String[] args) {
        Path base = Path.of("workspace", "reports");
        Path report = base.resolve("2026").resolve("summary.txt");
        Path joined = Path.of(
                "workspace", "reports", "2026", "summary.txt");

        Path sibling = report.resolveSibling("metrics.csv");
        Path directorySibling = base.resolveSibling("archive");
        Path normalized = base.resolve("drafts")
                .resolve("..")
                .resolve("final.txt")
                .normalize();

        System.out.println("Resolve equals Path.of: "
                + report.equals(joined));
        System.out.println("Report name: " + report.getFileName());
        System.out.println("Sibling name: " + sibling.getFileName());
        System.out.println("Sibling keeps parent: "
                + sibling.getParent().equals(report.getParent()));
        System.out.println("Directory sibling name: "
                + directorySibling.getFileName());
        System.out.println("Normalize result matches: "
                + normalized.equals(base.resolve("final.txt")));
        System.out.println("No-parent sibling: "
                + Path.of("note.txt")
                    .resolveSibling("done.txt")
                    .equals(Path.of("done.txt")));
        System.out.println("Original base unchanged: "
                + base.equals(Path.of("workspace", "reports")));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 PathComposeDemo.java
java PathComposeDemo
```

**Exact stdout:**

```text
Resolve equals Path.of: true
Report name: summary.txt
Sibling name: metrics.csv
Sibling keeps parent: true
Directory sibling name: archive
Normalize result matches: true
No-parent sibling: true
Original base unchanged: true
```

Explanation:

1. `Path.of("workspace", "reports", "2026", "summary.txt")` and the chain `resolve("2026").resolve("summary.txt")` produce the same components.
2. `resolveSibling("metrics.csv")` only changes the last name component, so sibling's parent remains equal to report's parent.
3. `base.resolveSibling("archive")` creates a path to `archive` as a sibling of `reports`, rather than placing `archive` inside `reports`.
4. `normalize()` syntactically collapses the `drafts/..` segment; it does not need a real file/directory.
5. `Path.of("note.txt")` has no parent recorded in the path, yet `resolveSibling` still returns the new name properly.
6. The original `Path` remains unchanged; the methods construct new result objects.

The example **does not check `Files.exists`** because the lesson demonstrates path transformations independently of whether files actually exist.

## 7. `normalize()` and `toAbsolutePath()` do not open files

`resolve` is often used together with `normalize`:

```java
Path input = Path.of("data", "staging", "..", "reports", ".", "a.txt");
Path cleaned = input.normalize();
```

The `staging/..` and `.` components are processed according to lexical rules; the result has components `data/reports/a.txt` in normal situations. `normalize()` **does not perform I/O**. In particular, with symbolic links, a normalized path does not necessarily lead to the same real location as the original path, because `..` may have a different meaning after traversing a link.

`toAbsolutePath()` creates an absolute representation based on provider/working directory rules:

```java
Path relative = Path.of("data", "report.txt");
Path absolute = relative.toAbsolutePath();
```

It **does not prove the file exists**. You should also not rely on `toAbsolutePath().toString()` as fixed stdout in lessons because machines and working directories differ.

`toRealPath(...)` differs in that it generally needs to access the file system to find an existing path and can resolve symbolic links according to options; this method can throw `IOException`. Do not confuse the three concepts:

- **`normalize()`:** simplifies the path syntactically.
- **`toAbsolutePath()`:** creates an absolute path without requiring the file to exist.
- **`toRealPath()`:** retrieves the real path according to the capabilities of the provider/file system; requires handling I/O errors.

## 8. When do real file system operations begin?

Joining paths does not bring any new file or directory into existence:

```java
Path root = Path.of("out");
Path output = root.resolve("daily").resolve("report.txt");
```

To **create and write**, you must call `Files` methods:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void writeReport(Path root) throws IOException {
    Path output = root.resolve("daily").resolve("report.txt");

    Files.createDirectories(output.getParent());
    Files.writeString(output, "Kết quả", StandardCharsets.UTF_8);
}
```

This is an **illustrative method** that must be placed inside a class, not a standalone program. In the example:

1. `resolve` creates the path in memory.
2. `Files.createDirectories(...)` is what requests creating the required parent directories.
3. `Files.writeString(...)` is what actually writes content; with default options, the method may create a new file or **truncate an existing file**.

If overwriting is not allowed, pass an appropriate option such as `StandardOpenOption.CREATE_NEW` and handle `FileAlreadyExistsException`. Do not call a write operation just to "test a path".

To **actually rename/move a file**, you need `Files.move(source, target, ...)`:

```java
Path source = Path.of("reports", "old.csv");
Path target = source.resolveSibling("new.csv");
// Files.move(source, target);  // Execute only when intending an actual move.
```

`resolveSibling` merely computes the target; **`Files.move` is what performs the move**. `Files.move` can fail due to permissions, an existing target, crossing filesystems, or provider constraints; you must handle `IOException`.

## 9. Joining paths from user input: `..` and path traversal

If the filename is supplied by a user, calling `base.resolve(userInput)` **is not enough to restrict access within `base`**. Example:

```java
Path base = Path.of("uploads");
Path unsafe = base.resolve("../secrets.txt");
Path normalized = unsafe.normalize();
```

After normalization, the result can **escape outside the uploads directory**. Simply because the first operation was `resolve` does not mean the file stays within the allowed area.

To validate a path **syntactically**, a common step is:

```java
Path root = Path.of("uploads").toAbsolutePath().normalize();
Path relative = Path.of(userInput); // String supplied by the user.

if (relative.isAbsolute()) {
    throw new IllegalArgumentException("Không chấp nhận đường dẫn tuyệt đối");
}

Path candidate = root.resolve(relative).normalize();
if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Đường dẫn vượt khỏi thư mục cho phép");
}
```

This is an **illustrative snippet**, requiring an existing `userInput` variable and execution inside a class/method. The `startsWith(Path)` check compares **path components**, unlike `String.startsWith`: the path `/data-old` is not considered under `/data` just because of a matching character prefix.

**Technical warning:** normalize and startsWith only check lexical paths; symbolic links can point outside, and directory state can change between check time and open time (TOCTOU). If you are implementing a system that handles untrusted paths, you must account for real paths, symlinks, access permissions, safe provider-level opening operations, and races. Do not treat the snippet above as a complete security check.

If the application only needs a single filename, you can explicitly restrict the name component (disallowing separators, `.`, `..`, or names outside an allowed set) before joining. The policy depends on format and business rules.

## 10. Common mistakes to avoid

| Mistake | Why is it wrong? | Correct approach |
| --- | --- | --- |
| Manually joining paths with `base + "/" + name` | Easy to get separators/Path types and provider rules wrong | `base.resolve(name)` or `Path.of(parts...)` |
| Using `file.resolve("new.txt")` for a sibling rename | Treats `file` as a directory location | `file.resolveSibling("new.txt")` |
| Calling `file.getParent().resolve("new.txt")` without checking | `getParent()` can be `null` for a single-component path | Use `resolveSibling` or check parent |
| Thinking `resolve` creates files/directories | `Path` is only a path representation | `Files.createDirectories`/`Files.write*` perform I/O |
| Thinking `resolveSibling` renames the real file | Only computes the new target path | `Files.move` to operate on the real file |
| Thinking `normalize` checks existence | Only simplifies syntactically | `Files.exists` or real I/O with exception handling |
| Thinking `toAbsolutePath` is canonical/real path | Only creates an absolute representation | `toRealPath` when querying the real path |
| Processing absolute input without checking | May ignore/alter the intended base root | Check `isAbsolute()` and naming policy |
| Using `String.startsWith` to check root directory | Character prefixes are not component boundaries | Use `Path.startsWith` plus additional safety measures |
| Relying only on normalize to prevent access outside a directory | Does not fully handle symbolic links and races | Validate and open according to system security policy |
| Comparing result strings against fixed `/` | Poor portability across operating systems | Compare `Path` objects or path components |
| Assuming `.txt` extension proves existence/content | Filename does not determine real state or format | Use proper metadata and content APIs when needed |

## 11. Self-check questions

1. **Has `Path.of("data").resolve("a.txt")` created the file `a.txt` yet?** No; it only constructs the path.
2. **Given `Path.of("data", "old.txt")`, what should you use to get `data/new.txt`?** `resolveSibling("new.txt")`.
3. **Does `Path.of("data", "old.txt").resolve("new.txt")` produce `data/new.txt`?** No; it appends a child component onto `old.txt`.
4. **Why is `resolveSibling` useful for `Path.of("readme.md")`?** Because the `null` parent case has defined behavior: it returns the passed path.
5. **Does `normalize()` create files or inspect real symlinks?** No; it only transforms syntactically.
6. **Does `toAbsolutePath()` guarantee the file exists?** No.
7. **What must you call to create a file after resolving?** An API with I/O effect such as `Files.writeString` or `Files.createFile`; remember to check the overwrite policy.
8. **Can `resolveSibling` replace `Files.move`?** No; it only constructs the target path.
9. **Can you achieve absolute safety with `root.resolve(input).normalize().startsWith(root)`?** No; you must address symbolic links, races, permissions, and access policies.
10. **What approach should you choose to join path components without depending on `/` or `\`?** `Path.of("a", "b")` or `base.resolve("b")`.

**Practical rule:** use `Path.of(...)` to initialize a path from components; use `resolve(...)` to append a **child path**; use `resolveSibling(...)` to build a **sibling path**. These are all operations on path representations; actual create/read/write/move effects belong to I/O APIs such as `Files`.