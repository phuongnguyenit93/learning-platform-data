# Path.startsWith, endsWith, equals, and component-based comparison in Java

`java.nio.file.Path` represents a **path** as a sequence of name elements and, if present, a root component. When checking which directory a path belongs to, what trailing components it has, or whether it equals another path, the three key methods are `startsWith(...)`, `endsWith(...)`, and `equals(...)`.

Core point: **these are comparisons on `Path` structure, not arbitrary string prefix/suffix checks**. For example, the path `docs/api/readme.md` starts with `docs/api`, but does not start with `docs/ap`; the name `readme.md` does not end with `me.md` in the sense of `Path.endsWith(...)`, even though `String.endsWith("me.md")` is `true`.

This lesson uses Java 17+ and favors relative path examples built with `Path.of("a", "b")` to avoid depending on the operating system's `/` or `\` separator. Differences regarding roots, case sensitivity, and providers are addressed separately.

## 1. Path is a structured sequence, not merely a String

A path such as:

~~~text
docs / api / guide.md
  0     1      2
~~~

consists of three name elements: `docs`, `api`, `guide.md`. With `Path path = Path.of("docs", "api", "guide.md")`:

| API | Meaning | Result in the example |
|---|---|---|
| `path.getNameCount()` | Number of name elements | `3` |
| `path.getName(0)` | First name element | `docs` |
| `path.getName(1)` | Second element | `api` |
| `path.getFileName()` | Last name element | `guide.md` |
| `path.getParent()` | Parent path | `docs/api` on Unix; separator may differ on Windows |
| `path.subpath(0, 2)` | Two elements at indices 0 and 1 | `docs/api` per file system syntax |
| `path.getRoot()` | Root part if any | `null` for this relative path |
| `path.isAbsolute()` | Whether it is an absolute path per the file system | `false` |

`Path` also implements `Iterable<Path>`; the loop `for (Path part : path)` iterates over **each name element**, excluding the root as a name element. Indices for `getName(...)` and `subpath(...)` start at **0**.

The string representation from `path.toString()` depends on the file system: the same structure may render as `docs/api/guide.md` on Unix and `docs\api\guide.md` on Windows. Do not write portable Java tests by comparing against a fixed separator when the real intent is comparing `Path` objects.

## 2. startsWith: comparing leading path elements

`boolean startsWith(Path other)` checks whether the current path begins with the **name elements** of `other`, while applying the file system's root compatibility rules.

~~~java
// Illustrative snippet; requires importing java.nio.file.Path.
Path path = Path.of("docs", "api", "guide.md");

boolean a = path.startsWith(Path.of("docs"));          // true
boolean b = path.startsWith(Path.of("docs", "api"));   // true
boolean c = path.startsWith(Path.of("docs", "ap"));    // false
boolean d = path.startsWith(Path.of("doc"));          // false
~~~

Even though the string `"docs/api/guide.md"` starts with the characters `"doc"` and `"docs/ap"`, `Path.startsWith` requires **each corresponding name element to be equal according to the file system's rules**. It does not check character prefixes inside a directory name.

Key points to remember:

1. If `other` has more name elements than the current path, the result is `false`.
2. `path.startsWith(path)` is `true`.
3. Roots must be compatible. A relative path cannot start with an absolute `other` that has a root; between rooted paths, root-matching rules are defined by the file system.
4. If two `Path`s belong to different `FileSystem`s, `startsWith(Path)` returns `false`.
5. `startsWith(String other)` is a convenience overload: the string is converted into a `Path` **using the current path's file system** before comparing. Therefore it is still a component-based comparison, not `toString().startsWith(...)`.

For example on Unix, `/data/reports/a.txt` starts with `/data`, whereas `/database/a.txt` does not start with `/data`. To avoid relying on Unix roots in code running on Windows, construct paths with the `Path` API and test using the same provider.

## 3. endsWith: comparing trailing path elements

`boolean endsWith(Path other)` compares **trailing components by name element**, not the trailing characters of `toString()`.

~~~java
// Illustrative snippet; requires importing java.nio.file.Path.
Path path = Path.of("docs", "api", "guide.md");

boolean a = path.endsWith(Path.of("guide.md"));         // true
boolean b = path.endsWith(Path.of("api", "guide.md"));  // true
boolean c = path.endsWith(Path.of("ide.md"));           // false
boolean d = path.endsWith(Path.of("docs", "api"));      // false
~~~

This leads to an important distinction:

~~~java
Path path = Path.of("notes.txt");

// Path component suffix comparison:
boolean pathSuffix = path.endsWith(Path.of(".txt")); // false

// Character suffix comparison within the filename:
boolean extension = path.getFileName().toString()
        .endsWith(".txt");                           // true
~~~

This is an **illustrative snippet**. `Path.endsWith(".txt")` is not a file-extension checking method. It asks whether the last name element is literally `.txt`. To check an extension, obtain the filename and apply string rules suited to your business logic.

For `endsWith(Path other)`, if `other` has no root, it can match the trailing name elements of a longer `Path`. However, if `other` **has a root**, it can only match when both the root and corresponding name parts match; in the typical case, you cannot use an absolute path to test the suffix of another path while ignoring its root.

`endsWith(String other)` likewise converts the string into a `Path` in the same `FileSystem` and compares structure. Paths from different providers are not considered to have equal suffixes merely because their printed strings coincide.

## 4. equals: equal as Path objects, not "the same file"

`path.equals(other)` checks **the equality of two path objects according to the file system's rules**. This is a comparison from the `Path` perspective; it does not look up the disk to ask whether the two paths point to the same file object.

~~~java
// Illustrative snippet.
Path a = Path.of("docs", "api", "guide.md");
Path b = Path.of("docs", "api", "guide.md");
Path c = Path.of("docs", "api", ".", "guide.md");

boolean sameLexicalPath = a.equals(b); // true
boolean containsDot = a.equals(c);    // false on typical default providers
~~~

`a` and `b` consist of matching elements; `c` has an extra `"."` element in its lexical representation. `equals` does not automatically call `normalize()` to strip `"."` elements. On unusual providers, comparison details may be implementation-dependent; do not rely on assuming every `FileSystem` handles dots and letter case identically.

Several things **must not be inferred from `equals`**:

- `docs/../docs/a.txt` may point to the same location as `docs/a.txt` in appropriate circumstances, but the two `Path` objects should not be considered equal before normalization.
- An absolute path and a relative path may point to the same file once interpreted relative to the working directory; `equals` does not convert relative to absolute.
- Two differently named symbolic links or hard links may locate the same physical file, yet `equals` can still return `false`.
- Two `Path`s with identical display strings belonging to different providers/`FileSystem`s are not automatically equal.
- On a case-sensitive file system, `Report.txt` and `report.txt` may be distinct; on some other file systems they may be treated as equivalent. **Do not hard-code** a case-sensitivity policy across all systems.

To check whether **two paths identify the same real file**, use `Files.isSameFile(path1, path2)` when appropriate; this method may access the file system and throw `IOException`. Details are covered in a later section.

## 5. Java 17+ program testing the three comparisons

Create the file **`PathComparisonDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathComparisonDemo {
    public static void main(String[] args) {
        Path path = Path.of("docs", "api", "guide.md");
        Path prefix = Path.of("docs", "api");
        Path lookAlike = Path.of("docs", "apix");

        System.out.println("startsWith(prefix)="
                + path.startsWith(prefix));
        System.out.println("startsWith(lookAlike)="
                + path.startsWith(lookAlike));
        System.out.println("endsWith(suffix)="
                + path.endsWith(Path.of("api", "guide.md")));
        System.out.println("endsWith(partialName)="
                + path.endsWith(Path.of("ide.md")));
        System.out.println("equals(same)="
                + path.equals(Path.of("docs", "api", "guide.md")));
        System.out.println("equals(extraDot)="
                + path.equals(Path.of("docs", "api", ".", "guide.md")));
        System.out.println("nameCount=" + path.getNameCount());
        System.out.println("subpathEqualsPrefix="
                + path.subpath(0, 2).equals(prefix));

        for (Path name : path) {
            System.out.println("part=" + name);
        }
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac -encoding UTF-8 PathComparisonDemo.java
java PathComparisonDemo
~~~

Typical stdout on the Java default file system:

~~~text
startsWith(prefix)=true
startsWith(lookAlike)=false
endsWith(suffix)=true
endsWith(partialName)=false
equals(same)=true
equals(extraDot)=false
nameCount=3
subpathEqualsPrefix=true
part=docs
part=api
part=guide.md
~~~

Because the name components in the program are all simple, the output does not need to print OS directory separators. For the Unix/Windows default provider, comparison keeps the `"."` element distinct until `normalize()` is called, so `equals(extraDot)` is `false`.

Note the loop iterating over each name component in order. `subpath(0, 2)` takes name elements 0 and 1, excluding element 2; the end index is **exclusive**.

## 6. Root, absolute, and relative paths

Paths can differ not only in directory names but also in **root**:

- **Relative:** `Path.of("work", "notes.txt")` has no root and is interpreted relative to the file system context.
- **Absolute:** `Path.of("work").toAbsolutePath()` binds to an absolute path per the default file system.
- **Root:** `getRoot()` returns the root component if present; `null` for a relative path without a root.

On Unix, the root is typically `/`. On Windows, roots and path syntax may involve drives or UNC. Therefore, avoid using `Path.of("/data")` as a portable absolute example across all platforms; use `toAbsolutePath()` or a path source properly defined for the target system.

The following pair **must not be equated**:

~~~java
// Illustrative snippet: performs no I/O.
Path relative = Path.of("docs", "api");
Path absolute = relative.toAbsolutePath();

boolean same = relative.equals(absolute); // false on typical default FS
~~~

Why can they point to the same directory yet have `equals` return different results? Because one side has the root and name parts of an absolute path, while the other has only relative name parts; `equals` compares `Path` representations according to the file system, rather than verifying the physical file.

If an application wants to compare paths in the same context, it must explicitly define a policy to convert **both**: such as `toAbsolutePath().normalize()` for lexical comparison, or `toRealPath()` when verifying an object on the real file system with appropriate access permissions.

## 7. normalize(): removing "." elements and resolving ".." lexically

`Path.normalize()` produces a new `Path` that removes redundant elements such as `"."` and directory-name/`".."` pairs that can be cancelled syntactically. It **is not a disk-access command** and does not verify whether the file exists.

Example:

~~~text
docs / api / . / guide.md
             |
             +---- normalize() ----> docs / api / guide.md

docs / api / .. / notes.txt
                   |
                   +---- normalize() ----> docs / notes.txt
~~~

Importantly, `normalize()` does not always preserve the **physical** path if the route contains symbolic links. For instance, `link/../target` may not be physically equivalent to `target` when `link` is a symbolic link pointing elsewhere; therefore use normalize only for lexical tasks whose context is well understood.

To validate path structure, combine appropriately with `resolve(...)`, `toAbsolutePath()`, and `startsWith(...)` once both objects are in the same frame of reference:

~~~java
// Illustrative snippet: establish base at a trusted location.
Path base = Path.of("workspace").toAbsolutePath().normalize();

Path candidate = base.resolve(Path.of("reports", "..", "notes.txt"))
        .normalize();

boolean lexicalInside = candidate.startsWith(base);
~~~

`resolve` joins path components; if the argument is already **absolute**, the result is typically that absolute path itself per the provider contract. Therefore, you must normalize and validate after resolving, and decide whether to accept absolute paths from untrusted sources.

## 8. Java 17+ example: comparing before and after normalize

Create the file **`PathNormalizationDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathNormalizationDemo {
    public static void main(String[] args) {
        Path clean = Path.of("root", "docs", "note.txt");
        Path raw = Path.of("root", "docs", ".", "note.txt");

        System.out.println("rawEqualsClean=" + raw.equals(clean));
        System.out.println("normalizedEqualsClean="
                + raw.normalize().equals(clean));

        Path base = Path.of("sandbox", "home")
                .toAbsolutePath().normalize();
        Path good = base.resolve(
                Path.of("reports", "..", "summary.txt")).normalize();
        Path escape = base.resolve(
                Path.of("..", "outside.txt")).normalize();

        System.out.println("goodUnderBase=" + good.startsWith(base));
        System.out.println("escapeUnderBase=" + escape.startsWith(base));
    }
}
~~~

~~~bash
javac -encoding UTF-8 PathNormalizationDemo.java
java PathNormalizationDemo
~~~

Stdout on Unix/Windows default file systems:

~~~text
rawEqualsClean=false
normalizedEqualsClean=true
goodUnderBase=true
escapeUnderBase=false
~~~

Explanation:

1. `raw` contains a `"."` element, so it does not equal `clean` under the default provider's lexical comparison; `normalize()` removes that element.
2. `base` is converted to an absolute path and normalized, and the candidates are processed the same way.
3. `good`, after collapsing `reports/..`, becomes `base/summary.txt`, so it starts with `base`.
4. `escape` contains `..` which shifts the path up to the parent directory of `base`; after normalize, `startsWith(base)` is `false`.

The example checks **path structure**. It **does not create directories** and does not guarantee that an application reading files through symbolic links cannot escape the trusted directory.

## 9. equals() differs from Files.isSameFile() and toRealPath()

These three operations answer three distinct questions:

| Operation | Question | Accesses the file system? |
|---|---|---|
| `a.equals(b)` | Are the two `Path` objects considered equal per the provider? | Normally no |
| `a.toAbsolutePath().normalize().equals(b.toAbsolutePath().normalize())` | Do the two paths have the same syntactically normalized absolute representation? | Does not verify objects on disk |
| `Files.isSameFile(a, b)` | Do the two paths locate **the same file object**? | May require disk access and may throw `IOException` |
| `a.toRealPath()` | What is the real path of an existing object according to the file system's rules? | Yes; resolves symbolic links by default and checks existence |

`Files.isSameFile(a, b)` has a notable contract exception: **if the two `Path` objects are already `equals`, the method may return `true` immediately without checking whether the file actually exists**. Therefore, do not use `Files.isSameFile(path, path)` as an existence check.

### Java 17+ example: two lexically different paths for the same file

Create the file **`PathSameFileDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathSameFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("path-demo-", ".txt");

        try {
            Path alias = file.getParent()
                    .resolve(".")
                    .resolve(file.getFileName());

            System.out.println("equals=" + file.equals(alias));
            System.out.println("normalizedEquals="
                    + file.normalize().equals(alias.normalize()));
            System.out.println("isSameFile="
                    + Files.isSameFile(file, alias));
            System.out.println("realPathEquals="
                    + file.toRealPath().equals(alias.toRealPath()));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 PathSameFileDemo.java
java PathSameFileDemo
~~~

Stdout on Unix/Windows default file systems:

~~~text
equals=false
normalizedEquals=true
isSameFile=true
realPathEquals=true
~~~

The program creates a unique temporary file, then builds the `alias` path by inserting a `"."` element between the parent directory and the filename. The two lexical representations are not equal initially, yet after `normalize()` they are equal; the file system confirms both locate the same file. The `finally` block deletes the temporary file without touching any user-supplied files.

In real programs, `toRealPath()` or `isSameFile(...)` may fail due to missing permissions, the file being deleted during the check, broken symbolic links, or a provider not supporting a particular feature. Do not treat the output of the example above as a guarantee across every virtual file system.

## 10. startsWith/endsWith and String.startsWith/endsWith: use the right level

Despite sharing method names, the two API sets have completely different purposes.

| Need | Appropriate API |
|---|---|
| Path is within the `docs` directory tree by name elements | `path.startsWith(Path.of("docs"))` |
| Path has the last two elements `images/icon.png` | `path.endsWith(Path.of("images", "icon.png"))` |
| Filename has string suffix `.png` | `path.getFileName().toString().endsWith(".png")` |
| Filename starts with string `report-` | `path.getFileName().toString().startsWith("report-")` |
| Do two paths have the same lexical representation? | `path1.equals(path2)`, after normalization if required |
| Do two paths point to the same real file? | `Files.isSameFile(path1, path2)` |
| Does a path have a name element at a specific index? | `getName(i)`, `subpath(from, to)` |

**Note on filenames**: `getFileName()` can return `null` if the path contains only a root. When checking extensions safely, handle this case:

~~~java
// Illustrative snippet: path is any Path.
Path fileName = path.getFileName();
boolean isJavaFile = fileName != null
        && fileName.toString().endsWith(".java");
~~~

This is a character suffix check, not content-type validation. A file named `malware.java` is not guaranteed to be valid Java source code merely because of its suffix, and case-sensitivity policy must be decided by the application.

## 11. Why is startsWith(String) still not a string check?

`Path.startsWith(String other)` essentially converts `other` into a `Path` via `getFileSystem().getPath(other)` and then calls `startsWith(Path)`. Example:

~~~java
Path p = Path.of("alpha", "beta");

boolean a = p.startsWith("alpha");          // true
boolean b = p.startsWith("alp");            // false
boolean c = p.toString().startsWith("alp"); // true
~~~

This is an **illustrative snippet**. The receiver is still a `Path`, so the `startsWith(String)` overload parses `"alpha"` as a name element. Calling `toString().startsWith("alp")`, on the other hand, only checks the first three characters, unaware that `alpha` is a complete directory name.

Similarly, `Path.endsWith("txt")` only checks whether the last name element is `txt`, whereas `path.toString().endsWith("txt")` can return `true` for `notes.txt`. For code operating on directory structure, use `Path`; for filename/extension rules, **explicitly extract the file name** and then use string operations.

Also note: the string converted to `Path` must be valid for that provider; the `String` overload can throw `InvalidPathException` if the string cannot form a valid path. Do not pass a path string from a different system and assume Java will parse it the same way.

## 12. Case-sensitive comparison and providers

A `Path` may be supplied by the default file system, a ZIP file system, or other providers. Contracts regarding **how names are compared**, case sensitivity, and roots are specific to the file system. For example:

- Some systems distinguish `data` and `Data`.
- Some systems use case-insensitive comparison.
- Root and separator interpretation also differs across Unix, Windows, and specialized providers.
- `Path.equals`, `startsWith`, and `endsWith` do not provide an **environment-independent** string/Unicode comparison mechanism.

Do not try to work around this by calling `path.toString().toLowerCase()` and comparing arbitrarily: lowercasing does not reproduce the file system's naming rules, can break special character semantics, and easily introduces security bugs at path boundaries.

If an application requires system-independent rules, define an explicit logical path structure, normalize input data according to protocol, and verify against the real file system at the access boundary. Never use filename comparison as absolute verification of resource identity.

### compareTo and sort order

`Path` implements `Comparable<Path>`, and `compareTo(...)` serves to **order paths according to the provider**, not to compare for file identity. A negative/positive result does not indicate whether two files have a parent–child relationship. If you need a component-based prefix check, `startsWith(...)` expresses that intent properly.

Comparing `Path`s belonging to different providers may be unsupported or throw an exception in `compareTo`; do not use it as a universal comparator across arbitrary file system sources.

## 13. Checking child paths: understand the security limits

A common problem: allowing a user to access a file inside a root directory `base`.

**Wrong:** using `inputString.startsWith(baseString)`. The string `/srv/app-data-secret` also starts with the characters `/srv/app-data`, yet does not lie inside that directory.

A better **lexical** check:

~~~java
// Illustrative snippet, insufficient as protection against symlinks/TOCTOU.
Path base = Path.of("safe-root").toAbsolutePath().normalize();
Path userPath = Path.of(userInput);
Path candidate = base.resolve(userPath).normalize();

if (!candidate.startsWith(base)) {
    throw new SecurityException("Path escapes allowed directory");
}
~~~

The mechanism above fixes the **string prefix** bug and many syntactic `..` cases. However, it **is not sufficient to protect against symbolic links, junctions, mounts, concurrent file system changes, or link-following operations**. For example, if `safe-root` contains a symbolic link leading outside, `candidate` can satisfy `startsWith(base)` syntactically while actual file access leaves the intended tree.

With untrusted input, you must also define explicit policies for **absolute paths, links, path existence, access permissions, and open operations**; in cases needing protection against time-of-check/time-of-use races, examine `SecureDirectoryStream` or an equivalent file system opening mechanism when available. Do not build filesystem security solely out of `normalize().startsWith(...)` and declare it completely safe.

If the requirement is simply organizing logical paths, `toAbsolutePath().normalize()` and `startsWith` are the right tools; if the requirement is **real file access control**, a stronger strategy is needed.

## 14. Common mistakes

| Mistake | Why it is wrong | Correct approach |
|---|---|---|
| Expecting `Path.of("docs2", "a").startsWith(Path.of("docs"))` to be `true` | `docs2` is not the `docs` element | Compare by name element |
| Using `path.endsWith(".java")` to check extension | `endsWith` compares name elements, not trailing characters | `getFileName().toString().endsWith(".java")` |
| Using `path.equals(other)` to conclude two files are definitely different | Two aliases/links can point to the same file | Use `Files.isSameFile` if checking the real file |
| Expecting `path.normalize()` to verify symlinks | Normalize is lexical; it does not access the file system | Use appropriate real-path/file-access mechanisms |
| Comparing `relative.equals(absolute)` and assuming two different physical targets | Two representations in different frames of reference | Bring to a consistent path standard or use `isSameFile` |
| Using `toString().startsWith(...)` to block traversal | Character prefixes do not recognize component boundaries | Compare properly processed `Path`s, plus link/race protection |
| Assuming `equals` is always case-sensitive | Provider defines comparison rules | Check target behavior, avoid platform assumptions |
| Assuming `startsWith` auto-normalizes `.` or `..` | No automatic normalization guarantee | Explicitly `normalize()` as intended |
| Using `compareTo` instead of `startsWith` | Ordering is not a parent–child relationship | Use the API expressing the exact question |
| Manually joining paths with `"/"` or `"\\"` | May not be portable | Use `Path.of(...)`, `resolve(...)` |
| Assuming `getFileName()` is never null | A root-only path may have no trailing name element | Check for `null` before using |
| Treating lexical containment as protection against malicious links | Links can point outside; files can change between check and open | Design protection at actual file-operation time |

## 15. Quick application checklist

1. Identify whether the requirement is **component prefix/suffix**, **filename string suffix**, **Path equality**, or **same real file**.
2. Use `startsWith(Path)` for component prefixes and `endsWith(Path)` for component suffixes.
3. Use `getFileName()` + `String` operations if checking a `.txt` extension or `report-` prefix of a **filename**.
4. Use `equals` for lexical comparison per provider; do not use it to conclude two different paths cannot point to the same file.
5. Consider `toAbsolutePath()`, `normalize()`, and `toRealPath()` per goal; each API solves a different problem.
6. For untrusted input data, treat `startsWith(base)` as just one layer in path traversal defense, not a complete solution against symlinks/races.
7. Write tests covering paths with **matching character prefixes but different components**, paths with `. / ..`, relative/absolute paths, and file system differences when deploying across environments.

## 16. Summary

**`Path.startsWith` and `Path.endsWith` operate on the path's name elements rather than slicing arbitrary character strings. `Path.equals` compares paths according to provider rules and does not verify that they refer to the same physical file.** To resolve `. / ..`, use `normalize()` when meaningful; to determine whether paths refer to the same real resource, use `Files.isSameFile(...)` or `toRealPath()`, while handling I/O errors. For access control problems, never treat lexical comparison as a complete security check.

### Official references

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Java SE 17 — Files.isSameFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path))
- [Oracle Java Tutorials — Path Operations](https://docs.oracle.com/en/java/javase/tutorial/essential/io/pathOps.html)