# `Path.toAbsolutePath()` differs from `Path.toRealPath()` in Java

In Java NIO.2, both statements below can produce an **absolute** path, yet they **do not do the same thing**:

~~~java
Path absolute = path.toAbsolutePath();
Path real = path.toRealPath();
~~~

`toAbsolutePath()` primarily converts the path representation into an **absolute form**; the resulting path **does not need to point to an existing file**. `toRealPath()` goes further: it determines the **real path of an existing object in the file system**, typically removing redundant components and **resolving symbolic links by default**. Because it must query the file system, it can throw `IOException`.

Confusing these two methods easily leads to bugs such as displaying a path and assuming the file exists, checking access permissions in the wrong place, or comparing two paths without realizing one passes through a symbolic link.

## 1. Foundation: `Path` describes a path, not an open file

`java.nio.file.Path` is an object representing a location in a file system. You can create a `Path` regardless of whether the corresponding object exists:

~~~java
import java.nio.file.Path;

Path relative = Path.of("data", "report.txt");
Path missing = Path.of("not-created-yet.txt");
~~~

These two statements only create **path objects**; they do not automatically create files or verify whether files exist. Operations on `Path` such as `resolve()`, `getParent()`, `getFileName()`, `startsWith()`, and `normalize()` generally operate on path structure; only APIs that actually require interacting with the file system carry semantics like opening, reading metadata, or determining the real path.

Distinguish:

- **Relative path:** has no absolute root; e.g., `docs/guide.txt` on Unix systems.
- **Absolute path:** contains enough information to be interpreted from a file system root; e.g., `/home/app/docs/guide.txt` on Unix or a path with an appropriate drive/root on Windows.
- **Real path:** an absolute path derived by referencing an actual object in the file system, with rules for resolving links and redundant components.

An absolute path can still be **wrong, nonexistent, access-denied, or contain `..`**. The word "absolute" describes **path form**, not a certification of file state.

## 2. What does `toAbsolutePath()` actually do?

Syntax:

~~~java
Path absolute = path.toAbsolutePath();
~~~

According to the `Path` contract in Java 17:

- Returns a `Path` representing an **absolute** path.
- If `path` is already an absolute path, the method returns that path object itself per the API contract.
- For a relative path on the default provider, the path is typically **resolved against the file system's default directory / working directory**.
- **Does not automatically check whether the file exists.**
- **Does not automatically normalize** to strip all `.` or `..` components.
- **Does not automatically resolve symbolic links** to the target's path.
- The conversion is `FileSystemProvider`-dependent in certain details, so do not manually concatenate strings with `/` or `\\` in place of the API.

Example assuming the working directory is `/app` on a Unix system:

~~~text
Path.of("docs", "..", "report.txt")
    .toAbsolutePath()

Typical result:
    /app/docs/../report.txt

Not necessarily:
    /app/report.txt
~~~

Here `/app/docs/../report.txt` is already **absolute**, yet still contains `docs/..`. And whether `/app/report.txt` exists or not **does not affect the ability to create the absolute `Path` object**.

`toAbsolutePath()` can still fail per the provider contract (for example `IOError` or `SecurityException` in some configurations), so you should not state unconditionally that it "can never fail". The main distinction is that **verifying file existence is not required to construct an absolute path**.

### When do you need `toAbsolutePath()`?

It is suitable when you want to:

1. Log or display a full path so the user knows where the application is interpreting a relative path from.
2. Build an absolute path for a **not-yet-existing output file**, such as the path of a report that will be created later.
3. Prepare a path for an operation at the next layer, when you **do not yet need** to query the file system.
4. Compare path structure by custom convention, accepting that the comparison is solely syntactic.

If you want to strip `.`/`..` parts syntactically, you can call `normalize()` separately:

~~~java
Path lexical = path.toAbsolutePath().normalize();
~~~

However, do not misunderstand: **`normalize()` does not access the filesystem to check the real structure**. In an environment with symbolic links, simplifying `link/../file` via pure path transformation may **not preserve the referenced object**. This is why lexical processing is distinguished from real path lookup.

## 3. What does `toRealPath()` actually do?

Syntax:

~~~java
import java.io.IOException;
import java.nio.file.Path;

Path real = path.toRealPath(); // May throw IOException.
~~~

`toRealPath(LinkOption... options)` returns the real path of **an existing file/directory** as defined by the provider. In the normal default case:

1. If the input is relative, first determine the absolute path.
2. Check and process the path through the file system.
3. Remove redundant components in the result; exact rules may depend on the provider.
4. **By default, follow symbolic links** to determine the final target.
5. May reflect the actual casing of the file/directory name on the file system when supported by the provider.
6. Return an **absolute** `Path` locating the real object, or throw `IOException` if the object does not exist/is inaccessible or an I/O error occurs.

In the case where a path points to an existing file:

~~~text
input:     /app/docs/../report.txt
              |
              | toRealPath()
              v
result:    /app/report.txt   (if docs exists and the file system has the matching structure)
~~~

Conversely, when `docs` does not exist, do not assume `toRealPath()` will treat every `docs/..` as unconditionally droppable; the actual lookup may fail depending on the provider and how path components are interpreted.

**Important:** `toRealPath()` does not open a file handle for your subsequent use and does not "lock" the object at that location. It is a lookup result **at the time of the call**. If the file or symbolic link is changed immediately afterward, a subsequent file-open operation may observe a different state.

## 4. Direct comparison table

| Criterion | `toAbsolutePath()` | `toRealPath()` |
|---|---|---|
| Goal | Obtain a path in **absolute form** | Determine the **real path** of a file system object |
| Requires file/directory to exist? | **No** | **Yes**, per the real-path resolution contract |
| Is the result absolute? | Yes | Yes |
| Automatically removes `.`, `..`? | Not its goal; does not auto-`normalize` | Typically removes redundant components when resolving the real path, per provider |
| Automatically resolves symbolic links? | No | **Yes by default** |
| `NOFOLLOW_LINKS` | Has no such option parameter | Yes, to alter symbolic link handling |
| Can throw `IOException`? | Does not declare `throws IOException`; runtime errors possible per provider | **Yes**, declares `throws IOException` |
| Must access file state? | Does not need to confirm existence | Yes, must resolve an existing file object |
| Suitable for an uncreated output file? | Yes | No, until the object exists |
| Suitable for an existing path passing through a symlink? | Produces absolute path without knowing the symlink target | Used to obtain the real path; can resolve symlinks |

An expression that commonly causes confusion:

~~~java
path.toAbsolutePath().normalize()
~~~

**is not generally equivalent to**:

~~~java
path.toRealPath()
~~~

Although many simple examples without symlinks yield the same result, the semantics and guarantees of the two approaches are different.

## 5. Standalone Java 17 example, independent of machine paths

To avoid guessing the working directory on the learner's machine, the example creates a real temporary directory, a `nested` subdirectory, and a file `info.txt`. It creates a `Path` containing `nested/../info.txt`, then compares the absolute path, the purely syntactically normalized path, and the real path.

Save as **`AbsoluteVsRealPathDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class AbsoluteVsRealPathDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("real-path-demo-").toRealPath();

        try {
            Path nested = Files.createDirectory(root.resolve("nested"));
            Path file = Files.writeString(
                    root.resolve("info.txt"), "OK", StandardCharsets.UTF_8);

            Path candidate = root.resolve(Path.of(
                    "nested", "..", "info.txt"));

            Path absolute = candidate.toAbsolutePath();
            Path normalized = absolute.normalize();
            Path real = candidate.toRealPath();

            System.out.println("Absolute? " + absolute.isAbsolute());
            System.out.println("Absolute keeps ..? "
                    + !absolute.equals(normalized));
            System.out.println("Normalized equals file path? "
                    + normalized.equals(file.toAbsolutePath().normalize()));
            System.out.println("Real equals file real path? "
                    + real.equals(file.toRealPath()));

            Path absent = root.resolve("missing.txt");
            System.out.println("Missing can be absolute? "
                    + absent.toAbsolutePath().isAbsolute());

            try {
                absent.toRealPath();
                System.out.println("Missing real lookup succeeded");
            } catch (IOException ex) {
                System.out.println("Missing real lookup failed");
            }
        } finally {
            Files.deleteIfExists(root.resolve("info.txt"));
            Files.deleteIfExists(root.resolve("nested"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 AbsoluteVsRealPathDemo.java
java AbsoluteVsRealPathDemo
~~~

Expected output on a normal default file system where permissions allow creating/deleting temporary directories:

~~~text
Absolute? true
Absolute keeps ..? true
Normalized equals file path? true
Real equals file real path? true
Missing can be absolute? true
Missing real lookup failed
~~~

### Output analysis

- `Files.createTempDirectory(...)` creates a real directory. We take `toRealPath()` of that directory to establish a real root and use it as the base.
- `Files.createDirectory(root.resolve("nested"))` creates a real subdirectory. Placing `nested/..` in `candidate` illustrates the difference without depending on the working directory name.
- `toAbsolutePath()` produces an absolute path while **retaining the `..` component**, so `absolute.equals(absolute.normalize())` is `false`.
- `normalize()` removes `nested/..` syntactically. Because `nested` exists and has no symlinks in this example, the normalized path matches the location of `info.txt`.
- `candidate.toRealPath()` verifies the file exists, returns the real path, and equals `file.toRealPath()`.
- `missing.txt`, which has not been created yet, can still have an absolute `Path`, but calling `toRealPath()` cannot resolve a real path; the example catches `IOException`.
- The `finally` block attempts to delete the items created by the program. If another actor touches the temp directory concurrently or the environment restricts I/O, the code may encounter `IOException`; this example demonstrates behavior under normal conditions without trying to mask file system errors.

**Note:** `Path.equals()` compares two `Path` objects under the provider's contract; two `Path` objects being equal in representation is not a foolproof mechanism proving two future file operations will access the same entity when the filesystem can change.

## 6. Symbolic links are a critical differentiator

A **symbolic link** is a filesystem entry referencing another target. Visualize on Unix:

~~~text
/work/assets/logo.png       (real file)
/work/public/logo.png  ----> /work/assets/logo.png
        ^ symlink path
~~~

If `Path link = Path.of("/work/public/logo.png")` represents a valid symlink:

~~~java
Path a = link.toAbsolutePath();
Path b = link.toRealPath();
~~~

- `a` represents an **absolute path to the symlink location itself**; it does not resolve the file the symlink points to.
- `b` **resolves the symlink** by default, so it can become `/work/assets/logo.png`.
- Paths written through multiple symlinks can point to the same real file using paths with very different representations.
- In the presence of symlinks, `toAbsolutePath().normalize()` still only normalizes **syntax**, so it cannot replace resolving actual links.

### `toRealPath(LinkOption.NOFOLLOW_LINKS)`

When you want to determine the real path **without following symbolic links**, the API supports `LinkOption.NOFOLLOW_LINKS`:

~~~java
import java.nio.file.LinkOption;

Path withoutFollowing = link.toRealPath(LinkOption.NOFOLLOW_LINKS);
~~~

This is an **illustrative snippet**; `link` must already be a declared `Path`, and the corresponding filesystem object must satisfy the provider's contract.

With `NOFOLLOW_LINKS`, the API does not resolve symbolic links to their targets as in default mode. Still, **do not oversimplify this as "just always take toAbsolutePath().normalize()"**: the `toRealPath` contract remains filesystem/provider-dependent, and handling of `..` around symlinks may differ to avoid altering the referenced object.

On Windows systems, creating symbolic links may depend on privileges or system policy; therefore the program in section 5 intentionally avoids creating symlinks so it does not require special privileges. The symlink example above is a **mental model**, not a path guaranteed to exist on the learner's machine.

## 7. `normalize()`, `toAbsolutePath()`, and `toRealPath()` are not interchangeable

Three easily confused operations:

### `normalize()`: lexical normalization

~~~java
Path p = Path.of("a", "b", "..", "c");
Path n = p.normalize(); // Representation typically simplifies to a/c.
~~~

`normalize()` removes `.` components or `name/..` component pairs according to lexical rules. It **does not check whether `a` or `b` exists**. Therefore it is not filesystem verification. On some paths containing symbolic links, dropping `link/..` can cause the resulting path to point to a **different location** if actually accessed.

### `toAbsolutePath()`: converting to absolute form

~~~java
Path absolute = Path.of("a", "b", "..", "c")
        .toAbsolutePath();
~~~

`absolute` is an absolute path, but `..` is not necessarily removed, and the file might not exist yet.

### `toRealPath()`: finding the real path

~~~java
Path real = Path.of("a", "b", "..", "c")
        .toRealPath(); // throws IOException
~~~

`real` only succeeds when the file system can resolve the object according to contract. It carries information about the filesystem, not merely a string operation.

**Study tip:** normalize = *simplify expression*, absolute = *anchor to root*, real = *verify against filesystem*. This tip helps memory, but when handling symbolic links and differing providers, always prioritize the API contract.

## 8. Which method should you choose for each scenario?

| Requirement | Approach | Reason |
|---|---|---|
| Log the expected location of an uncreated output file | `path.toAbsolutePath()` | Does not require the file to exist |
| Display a path with `.`/`..` removed for readability | `path.toAbsolutePath().normalize()` | Purely syntactic normalization, no verification |
| Obtain the real location of an existing file | `path.toRealPath()` | Verifies and resolves links by default |
| Keep the symlink without following to its target when getting real path | `path.toRealPath(NOFOLLOW_LINKS)` | Adjusts the link-handling contract |
| Want to open the file right afterward | `Files.newInputStream(path)` / `Files.newByteChannel(...)` | Opening methods actually supply the handle; `toRealPath` does not pre-open |
| Want to know if two paths currently point to the same file? | `Files.isSameFile(a, b)` where appropriate | API designed for checking file identity; not just string comparison |
| Check whether a file object exists | `Files.exists(path)` in simple contexts | However, `false` may mean status could not be determined; does not replace main I/O operations |
| Handle user input inside a permitted directory | Design path policies and safe file opening | Calling normalize/real path alone **is not enough** to prevent races or traversal |

Some code snippets inadvertently conflate two tasks at once:

~~~java
Path target = userInput.toAbsolutePath().normalize();
if (Files.exists(target)) {
    // ...
}
~~~

This snippet **is not equivalent** to having a trustworthy real path, nor does it hold the file fixed between checking and using. If a security policy is needed, do not rely on a simple comparison as the sole safety barrier.

## 9. Handling `toRealPath()` errors properly

Because it queries the filesystem, `toRealPath()` declares `throws IOException`. Common failure scenarios:

- **Object not found:** `NoSuchFileException` (a subtype of `IOException`) may be thrown.
- **Insufficient permissions:** `AccessDeniedException` or another I/O exception may occur, depending on OS/provider.
- **Broken link or link loop:** symbolic link resolution may fail.
- **Filesystem unavailable:** paths on network filesystems or removable devices may fail.
- **Concurrent modification:** the file/directory may be altered or deleted during lookup.

Example handling in a method:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class RealPathLookup {
    static Path resolveExisting(Path input) throws IOException {
        try {
            return input.toRealPath();
        } catch (NoSuchFileException ex) {
            throw new IOException("Đường dẫn không tồn tại: " + input, ex);
        }
    }
}
~~~

This is a **compilable Java class** without `main()`; the `Files` import in the example merely illustrates the `java.nio.file` context and is not needed by the method body.

**Do not catch every `IOException` and arbitrarily fall back to `toAbsolutePath()`** if the application requires confirming the file exists: such a fallback changes the contract from "real existing object" to "absolute-form path", potentially masking permission errors or broken links. If the application intentionally allows nonexistent paths, express that as an explicit business branch.

Do not infer from `Files.exists(path) == false` that the file is definitely absent: Java may be unable to determine status due to errors or access permissions. For real tasks, error handling when **opening/reading/writing** is what truly matters.

## 10. Real paths and application security

A common situation is an application permitted to access files only inside directory `base`, yet receiving a relative path from a user. A syntactic check:

~~~java
Path candidate = base.resolve(userSupplied).normalize();
if (!candidate.startsWith(base.normalize())) {
    throw new IllegalArgumentException("Outside allowed directory");
}
~~~

This is an **illustrative snippet for lexical checking** (requiring `base` and `userSupplied` of type `Path`), **not a complete filesystem protection mechanism**. If `base` or `candidate` contains a symbolic link, a path that appears to lie under `base` may lead outside.

If the object **already exists**, comparing real paths can detect many cases where symlinks alter the location:

~~~java
Path realBase = base.toRealPath();
Path realTarget = candidate.toRealPath();
if (!realTarget.startsWith(realBase)) {
    throw new SecurityException("File outside permitted root");
}
~~~

The code above is **illustrative**, applicable only when the paths currently exist and with `IOException` handled. `Path.startsWith(Path)` checks by path components according to provider rules, **not character-prefix matching**.

However, understand the limitation: between `toRealPath` and opening the file, another party could replace a symlink or replace the file, creating a **time-of-check to time-of-use (TOCTOU)** condition. Therefore, **never claim that `toRealPath` by itself gives absolute protection against path traversal or symlink attacks**. Security-sensitive tasks require platform-appropriate directory-based opening and link-control APIs/operations (such as `SecureDirectoryStream` when supported by the provider), along with proper file permission policies.

For an output file that **does not yet exist**, `toRealPath()` on that file itself will generally fail. If secure output routing is required, design around a controlled parent directory/handle and appropriate file-creation operations; do not create a "dummy" file just to pass a real-path check.

## 11. Common mistakes to avoid

| Misconception | Why is it wrong? | How to fix |
|---|---|---|
| "`toAbsolutePath()` tells you the file exists." | Creating an absolute `Path` does not require a real file. | Use filesystem APIs when you need to verify the file. |
| "`toAbsolutePath()` automatically removes `..`." | Does not perform lexical normalization by default. | Use `normalize()` if you genuinely want syntactic simplification. |
| "`normalize()` is the same as `toRealPath()`." | Normalize does not query the filesystem or resolve symlinks. | Choose the right operation per requirement and contract. |
| "`toRealPath()` is for uncreated output files." | Requires the object to exist per contract. | Use an absolute path to prepare the target location, then create via Files API. |
| "Two identical `toAbsolutePath()` values prove they are the same file." | Paths can change, and hard links/symlinks and providers have distinct semantics. | Consider `Files.isSameFile` when checking an existing file. |
| "`toRealPath()` does not follow symlinks." | By default it resolves symlinks to the target. | Use `NOFOLLOW_LINKS` when required not to follow links. |
| "`NOFOLLOW_LINKS` is identical to `normalize()`." | Rules for preserving targets when `..` and symlinks interact are subtler. | Read the `toRealPath` and provider contracts. |
| "Catch `IOException` and use the absolute path as if checked." | Accidentally ignores access permission errors or missing files. | Separate existing-file and nonexistent-file logic clearly. |
| "`toRealPath()` returns a locked handle." | It only returns a `Path`; the file can change afterward. | Use Files/Channel APIs to open and manage lifecycle. |
| "Checking the real path once suffices against races." | The filesystem can change after the check. | Use opening/control strategies matching security requirements. |
| "The same path string has the same meaning on every OS." | Roots, separators, case sensitivity, and providers differ. | Use `Path.of`, `resolve`; do not manually assemble OS syntax. |

## 12. Self-check questions

**Question 1.** The file `missing.txt` does not exist yet. What happens when calling both methods?

> `Path.of("missing.txt").toAbsolutePath()` can still return an absolute path. `toRealPath()` needs to resolve an existing object, so it will fail with `IOException` when the file does not exist.

**Question 2.** How does `/work/a/../b.txt` differ when processed with `toAbsolutePath()` versus `toAbsolutePath().normalize()`?

> `toAbsolutePath()` keeps the absolute path as given; `normalize()` can lexically simplify it to `/work/b.txt`. Neither method by itself proves that the file exists or inspects real symlinks.

**Question 3.** There is a symlink `alias.txt` pointing to `/data/original.txt`. When do `toRealPath()` and `toRealPath(NOFOLLOW_LINKS)` differ?

> Default mode resolves the symlink to find the real path of the target. With `NOFOLLOW_LINKS`, the API does not follow the symlink to the target; the resulting path corresponds to preserving the link per the contract/provider.

**Question 4.** If a file exists yet the application lacks permission to resolve its real path, does `toAbsolutePath()` returning successfully prove sufficient access permissions?

> No. An absolute path only speaks to representational form. `toRealPath` can throw `IOException` due to permissions or filesystem errors; read/write operations still require separate checking and error handling.

**Question 5.** Should you replace every use of `toRealPath()` with `normalize()` to avoid catching `IOException`?

> No. These are two different requirements: `normalize()` only processes syntax; `toRealPath()` must consult the filesystem and can resolve symlinks. Skipping the exception means losing necessary business verification.

**Question 6.** Why is checking `target.toRealPath().startsWith(base.toRealPath())` helpful yet still not a complete security barrier?

> It can detect that `target` currently points outside the directory via a symlink, but the filesystem can be modified **after the check**. Appropriate file-opening strategies and system permissions are required if attack resistance is needed.

## Remember

- **`toAbsolutePath()`:** yields an **absolute path**, does not require the file to exist, does not auto-normalize or resolve symlinks.
- **`toAbsolutePath().normalize()`:** yields a **syntactically simplified absolute path**, still does not verify the real file.
- **`toRealPath()`:** obtains the **real path of an existing file/directory**, typically removes redundant parts and **resolves symbolic links by default**; may throw `IOException`.
- **`toRealPath(LinkOption.NOFOLLOW_LINKS)`:** obtains the real path **without following symbolic links**, under appropriate provider rules.
- **`toRealPath` does not lock the file and does not eliminate all risks of concurrent modification**.

The deciding question before picking an API is: **"Do I only need a full path representation, or do I need to resolve a real object currently existing in the filesystem?"** Answering that question helps you use `Path` properly for both ordinary I/O and paths involving links.

**References:** [Java SE 17 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html), [`java.nio.file.LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html), [`java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).