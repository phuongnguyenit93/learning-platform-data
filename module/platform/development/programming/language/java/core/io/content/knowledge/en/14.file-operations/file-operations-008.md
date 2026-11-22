# `Files.exists()`, `Files.notExists()`, and Unknown State

## Lesson Objectives

In Java NIO.2, the two methods `Files.exists(Path, LinkOption...)` and `Files.notExists(Path, LinkOption...)` test **the ability to verify the existence status of a path**. They look symmetric, yet **they are not logical negations of each other in every circumstance**. When status cannot be determined — for instance, due to metadata access errors or a filesystem unable to respond conclusively — **both can return `false` at the same time**.

After this lesson, you will be able to:

- Distinguish `Files.exists(path)`, `Files.notExists(path)`, and the operator `!Files.exists(path)`.
- Correctly interpret **all three states**: *confirmed present*, *confirmed absent*, and *unknown*.
- Understand `LinkOption.NOFOLLOW_LINKS`, valid or broken symbolic links, and the difference between **the link** and **the link's target**.
- Avoid confusing "path exists" with "is a regular file," "has read permission," "stable content," or "opens successfully."
- Avoid **TOCTOU (time-of-check-to-time-of-use)** bugs when checking state before opening, creating, deleting, or modifying a file.
- Know when to use direct operations and exceptions (`Files.readAttributes`, `Files.newInputStream`, `Files.createFile`…) instead of trusting only boolean results.
- Write and run Java 17+ code that handles unknown states without inferring that the file does not exist.

## 1. Foundation: `Path` Does Not Mean a File Already Exists

```java
Path path = Path.of("data", "report.txt");
```

This is an **illustrative snippet** with `import java.nio.file.Path;`. Creating a `Path` only creates **an object representing a path**; it does not create a file, check permissions, or guarantee the file exists. The operating system and filesystem determine whether that path can resolve to an entry when an I/O operation executes.

Elements to distinguish:

- **Path**: representation of a location/pathname within a filesystem.
- **Entry**: the object at that name (regular file, directory, symbolic link, or another type depending on the filesystem).
- **Metadata**: file/entry attributes such as type, size, timestamps, permissions.
- **Filesystem provider**: the class implementing read/write for a filesystem (default provider, ZipFS, third-party provider…).
- **I/O operation**: opening a file, creating a file, reading attributes, deleting, renaming — can throw exceptions and can be affected by concurrent changes.

`Files.exists` and `Files.notExists` inspect existence information **around the time of the call**; they do not lock the entry and do not turn the path into an immutable reference.

## 2. API of `exists` and `notExists`

Two signatures in `java.nio.file.Files`:

```java
public static boolean exists(
    Path path, LinkOption... options);

public static boolean notExists(
    Path path, LinkOption... options);
```

These are **illustrative API signatures**, not code to redefine in your application. `LinkOption` is in `java.nio.file`. If options are omitted, **the methods follow symbolic links by default** when checking.

Usage example:

```java
Path p = Path.of("data.txt");

boolean confirmedPresent = Files.exists(p);
boolean confirmedAbsent = Files.notExists(p);

boolean linkEntryPresent =
    Files.exists(p, LinkOption.NOFOLLOW_LINKS);
```

This is an **illustrative snippet**; it requires `Files`, `Path`, `LinkOption`, and `p` must be meaningful for the active filesystem.

Key interpretations:

| Expression | Only conclude |
|---|---|
| `Files.exists(path) == true` | Verified that the object under the chosen link policy **exists** at check time |
| `Files.notExists(path) == true` | Verified that the object under the chosen link policy **does not exist** at check time |
| `Files.exists(path) == false` | **Could not verify that it exists**; it may not exist **or** its status is unknown |
| `Files.notExists(path) == false` | **Could not verify that it does not exist**; it may exist **or** its status is unknown |
| Both are `false` | **Unknown state** from the two checks |
| `!Files.exists(path)` | Negates the boolean result of one check; **not equivalent** to `Files.notExists(path)` in the unknown case |

From this follows one point: **a boolean `false` result does not always carry definitive negative information about the filesystem**.

## 3. Three-State Truth Table: The Core Point

If both checks observe **the same unchanged state** with the same link-following policy, we have:

| Verifiable state | `Files.exists(p)` | `Files.notExists(p)` | Must be understood as |
|---|:---:|:---:|---|
| Verified present | `true` | `false` | **PRESENT** |
| Verified absent | `false` | `true` | **ABSENT** |
| Cannot verify state | `false` | `false` | **UNKNOWN** |
| `true` and `true` | Not a consistent result of an immutable state | | If observed at two different times, may be due to concurrent changes or provider factors |

**Do not write:**

```java
if (!Files.exists(path)) {
    System.out.println("File chắc chắn không tồn tại");
}
```

This is a **counterexample**: this branch also runs when `exists` could not verify the state. If you need to report confirmed non-existence, check `Files.notExists(path)`.

A way to clarify all three states:

```java
if (Files.exists(path)) {
    System.out.println("Đã xác minh tồn tại");
} else if (Files.notExists(path)) {
    System.out.println("Đã xác minh không tồn tại");
} else {
    System.out.println("Không xác minh được trạng thái");
}
```

This is an **illustrative snippet**; `path` is a `Path` and `Files` is imported. **Note:** The two calls happen at **two separate moments**; the file can be created/deleted/renamed in between. Thus this is a reasonable way to **classify an approximate observation**, not an atomic transaction on file state.

### Why Does UNKNOWN Occur?

Some situations where a provider cannot verify definitively:

1. Directory or metadata access permissions are insufficient to query the path.
2. Remote storage or a filesystem provider does not respond and cannot verify state.
3. Filesystem, container environment, mount, or I/O-layer errors prevent metadata lookup from returning a conclusive result.
4. A symbolic link or path whose resolution fails.
5. Specific filesystem/provider situations making existence information unavailable.

**Do not claim absolutely "permission denied always makes both return false"**: on one specific filesystem, metadata may still suffice to conclude existence; on another provider it may return a different value or throw `SecurityException` per security policy. The key is never converting an uncertain case into `ABSENT`.

Per the Java contract, when the result cannot be determined due to a file access failure, `exists` and `notExists` may return `false`; they do not expose all I/O error details through their boolean return type. Certain security checks can lead to an unchecked `SecurityException`.

## 4. Why Is `notExists()` Not `!exists()`?

In ordinary two-valued Boolean logic:

```text
exists = true  → not exists = false
exists = false → not exists = true
```

However, these APIs do not represent only physical state. They represent **the ability to verify** a statement from the filesystem:

```text
                        Status lookup
                              │
               ┌──────────────┼───────────────┐
               ▼              ▼               ▼
        Confirmed yes   Confirmed no      Unverified
               │              │               │
        exists = true    exists = false   exists = false
        notExists = false notExists = true notExists = false
```

Therefore:

```text
!Files.exists(p)        = "did not get a confirmed-yes result"
Files.notExists(p)      = "got a confirmed-no result"
```

The two statements differ when the outcome is **unknown**.

In business code, name variables according to the real information:

```java
boolean isConfirmedMissing = Files.notExists(path);
boolean isConfirmedPresent = Files.exists(path);
```

Avoid naming `!Files.exists(path)` as `missing` if readers might interpret it as confirmed absence.

If a system needs **a single status**, a three-value enum expresses the contract better than two boolean flags, though keep in mind it is still a non-atomic snapshot from multiple checks.

## 5. Java 17 Example: State of an Existing File and a Deleted File

Save **`ExistenceBasicsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExistenceBasicsDemo {
    private static void show(String label, Path path) {
        System.out.println(label
            + " exists=" + Files.exists(path)
            + " notExists=" + Files.notExists(path));
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("exists-demo-", ".txt");

        try {
            Files.writeString(file, "hello", StandardCharsets.UTF_8);
            show("created", file);
        } finally {
            Files.deleteIfExists(file);
        }

        show("removed", file);
    }
}
```

Run:

```bash
javac ExistenceBasicsDemo.java
java ExistenceBasicsDemo
```

Output on a normal filesystem, if creation/deletion and metadata lookup all succeed:

```text
created exists=true notExists=false
removed exists=false notExists=true
```

Explanation:

1. `Files.createTempFile` creates a new file on the filesystem and returns its `Path`.
2. `Files.writeString` writes content to the file; writing content does not change the nature of existence checking.
3. Inside `try`, the file exists and is verifiable, so `exists == true`.
4. `Files.deleteIfExists` deletes the file in `finally`; if deletion succeeds, the next check confirms absence.
5. The program **does not prove** the filesystem can always return a definite result when permissions are lost, I/O fails, or state changes concurrently.

The example does not print the temporary filename because the random part differs on each run. There is no need to replace real user filenames with fixed data to get deterministic output; print only the checked state.

## 6. `LinkOption.NOFOLLOW_LINKS`: Checking the Link or the Target?

A symbolic link is an entry representing a path referencing another entry. By default, `Files.exists(link)` and `Files.notExists(link)` **follow symbolic links**. When `LinkOption.NOFOLLOW_LINKS` is passed, Java checks **the link itself** instead of traversing to the target.

Conceptual example:

```text
directory/
├── target.txt                 (real file)
└── shortcut.txt -> target.txt (symbolic link)
```

If `target.txt` still exists, both link-following and non-following checks can confirm an entry exists:

```java
Files.exists(link);                        // usually true
Files.exists(link, LinkOption.NOFOLLOW_LINKS); // true when link is present
```

This is an **illustrative snippet**; `link` is a `Path` pointing to the symbolic link. However, when the target is deleted:

```text
directory/
├── target.txt                  (deleted)
└── shortcut.txt -> target.txt  (link still remains)
```

Two different questions:

- **Follow link (default):** Does the target exist? If the target is verified absent, `Files.exists(link)` is `false` and `Files.notExists(link)` is `true`.
- **Do not follow link:** Does the symbolic link entry itself exist? If present and verifiable, `Files.exists(link, NOFOLLOW_LINKS)` is `true` and `Files.notExists(link, NOFOLLOW_LINKS)` is `false`.

### Symbolic Matrix

| Case | Default follow links | `NOFOLLOW_LINKS` |
|---|---|---|
| Existing regular file | Confirmed present | Confirmed present |
| Symlink exists, target exists | Usually confirmed present | Confirms **link** is present |
| Symlink exists, target gone (*dangling link*) | Usually confirms target absent if verifiable | Confirms **link** is present |
| Path truly has no entry | Confirms absent if verifiable | Confirms absent if verifiable |
| Insufficient info to access metadata | May be UNKNOWN | May be UNKNOWN |

**Key point:** `NOFOLLOW_LINKS` changes **which object is being queried**, rather than guaranteeing the query succeeds or bypassing permission errors.

### When to Use `NOFOLLOW_LINKS`?

- Administrative tools wanting to know whether **the symbolic link entry itself** exists.
- Cleanup routines needing to distinguish "a broken link that still has an entry" from "a completely vacant name."
- Logic that does not want metadata lookups to automatically traverse symlinks.
- Certain workflows needing to inspect the link before deciding whether to delete or rename that entry.

However, **checking with `NOFOLLOW_LINKS` and then opening the file normally does not by itself prevent symlink risks**. Another process can replace the entry after the check. For security requirements, use appropriate open/read APIs, OS permissions, and TOCTOU mitigations.

## 7. Java 17 Example: Checking a Broken Symbolic Link (Supported Environments)

Creating symbolic links is an operation that may be restricted on Windows, inside containers, or with certain filesystem providers. Therefore, the example below **prints deterministic results only when link creation succeeds and the filesystem has standard semantics**; if permission support is lacking, the program does not assume every environment behaves identically.

Save **`SymlinkExistenceDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class SymlinkExistenceDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("link-demo-");
        Path link = dir.resolve("shortcut.txt");

        try {
            try {
                Files.createSymbolicLink(
                    link, Path.of("missing-target.txt"));
            } catch (UnsupportedOperationException
                     | SecurityException
                     | IOException ex) {
                System.out.println("Symlink unavailable");
                return;
            }

            System.out.println(
                "follow exists=" + Files.exists(link));
            System.out.println(
                "follow notExists=" + Files.notExists(link));
            System.out.println(
                "nofollow exists=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println(
                "nofollow notExists=" +
                    Files.notExists(link, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run:

```bash
javac SymlinkExistenceDemo.java
java SymlinkExistenceDemo
```

When symbolic link creation is supported, the link exists, and the target is missing, typical output is:

```text
follow exists=false
follow notExists=true
nofollow exists=true
nofollow notExists=false
```

If the environment does not allow creating symlinks, the program prints `Symlink unavailable` and exits after running `finally`. When the filesystem cannot resolve the target, the follow pair can both be `false`; thus **the output above is a conditional expectation**, not a cross-provider guarantee.

The code uses the relative target `missing-target.txt` to create a dangling symlink; it does not need to create the real target file. When deleting `link`, `Files.deleteIfExists(link)` deletes **the link entry** without requiring the target to exist. If delete permissions are restricted or the directory is modified concurrently, cleanup can throw `IOException` — the example does not try to hide this error.

## 8. Unknown State: How to Represent It Clearly in Code

Because the two methods return booleans, an application may want to wrap the status into an enum. Example:

```java
enum Existence {
    PRESENT, ABSENT, UNKNOWN
}
```

The enum code above is an **illustrative definition snippet** for a Java class or file; the enum only describes the observed status and does not make the filesystem atomic.

### Java 17 Example: Classifying Three States

Save **`ExistenceStateDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class ExistenceStateDemo {
    enum State {
        PRESENT, ABSENT, UNKNOWN
    }

    static State probe(Path path, LinkOption... options) {
        if (Files.exists(path, options)) {
            return State.PRESENT;
        }
        if (Files.notExists(path, options)) {
            return State.ABSENT;
        }
        return State.UNKNOWN;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("state-demo-", ".dat");
        try {
            System.out.println("present: " + probe(file));
        } finally {
            Files.deleteIfExists(file);
        }
        System.out.println("absent: " + probe(file));
    }
}
```

Run:

```bash
javac ExistenceStateDemo.java
java ExistenceStateDemo
```

Stdout when the filesystem creates/deletes and queries normally:

```text
present: PRESENT
absent: ABSENT
```

**Do not try to simulate UNKNOWN by changing permissions on a temporary directory** and assert a specific outcome. On Windows, Unix, containers, or when running with elevated privileges, permission operations can yield different states; existence may even still be verifiable without permission to read contents. To test the UNKNOWN branch deterministically, **decouple classification logic from filesystem APIs** and supply probe outcomes through a mockable abstraction.

Example testing approach:

```text
probe.exists = true,  probe.notExists = false  → PRESENT
probe.exists = false, probe.notExists = true   → ABSENT
probe.exists = false, probe.notExists = false  → UNKNOWN
```

That is a logical state fixture, **not** a claim that the OS produced all three states in a single run.

### Limitation: Two Consecutive Lookups Are Not an Atomic Snapshot

In `probe`, `exists` and `notExists` are two separate queries. If the entry is created/deleted between them, the enum result reflects only logic over two observations, **not a guaranteed state at one single instant**. The function is useful for UI reporting/diagnostics, yet is not a safe synchronization protocol for deciding whether to create/delete files under contention.

## 9. `Files.exists` Does Not Mean the File Can Be Read or Written

A path may exist yet:

- It is a **directory**, symbolic link, FIFO, device node, or another entry type.
- The file denies read/write permissions.
- The file exists now, yet is immediately deleted, modified, or renamed by another process.
- The filesystem/provider encounters an I/O error when opening.
- The file is a symlink pointing to a modified path or outside a safe root.
- Remote storage drops connection right after returning metadata.

Therefore:

```java
if (Files.exists(path)) {
    try (var input = Files.newInputStream(path)) {
        // ...
    }
}
```

This is an **illustrative snippet**, with `path` as a `Path` and handling `IOException`. An initial existence check does not guarantee `newInputStream` succeeds. In real code, if the goal is to read a file, **trying to open the file directly** and handling exceptions is usually more reliable than pre-checking with `exists`.

| Question | Corresponding API / strategy |
|---|---|
| Can we confirm the entry currently exists? | `Files.exists(path, options)` |
| Can we confirm the entry does not exist? | `Files.notExists(path, options)` |
| Can we read from this path right now? | Try `Files.newInputStream`, read, and handle errors |
| Can we write a new file without overwriting an old one? | `Files.createFile` or open with `CREATE_NEW` |
| Is the entry a regular file? | `Files.isRegularFile` or `BasicFileAttributes.isRegularFile()` |
| Can we read metadata or know why it failed? | `Files.readAttributes` with `try/catch` |
| Does the file have accurate/validly formatted data? | Open, read, parse, and validate contents |
| Is the file durable after power loss? | Requires separate sync/commit design, not inferred from `exists` |

Methods like `Files.isRegularFile`, `Files.isDirectory`, `Files.isReadable`, and `Files.isWritable` can also return `false` when the condition cannot be verified. Do not automatically interpret `false` from any predicate as definitive proof of a single cause.

## 10. When You Need to Diagnose Why: `Files.readAttributes` and Exceptions

`exists`/`notExists` express a simple question as a boolean yet **intentionally do not propagate all I/O errors as checked exceptions**. If you need to distinguish a nonexistent path from an access error, consider an API that performs the required operation and allows catching exceptions.

Example:

```java
BasicFileAttributes attributes = Files.readAttributes(
    path,
    BasicFileAttributes.class,
    LinkOption.NOFOLLOW_LINKS
);
```

This is an **illustrative snippet**, requiring importing `java.nio.file.Files`, `java.nio.file.LinkOption`, `java.nio.file.attribute.BasicFileAttributes`, and handling `IOException`. On success, you receive `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `size()`, etc. On failure, the API may throw `NoSuchFileException`, `AccessDeniedException`, or other `IOException` types depending on the provider.

### Java 17 Example: Reading Metadata with Contextual Error Reporting

Save **`ReadAttributesStatusDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class ReadAttributesStatusDemo {
    static String describe(Path path) {
        try {
            BasicFileAttributes attrs = Files.readAttributes(
                path,
                BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS
            );
            if (attrs.isRegularFile()) {
                return "regular file";
            }
            if (attrs.isDirectory()) {
                return "directory";
            }
            if (attrs.isSymbolicLink()) {
                return "symbolic link";
            }
            return "other entry";
        } catch (NoSuchFileException ex) {
            return "missing";
        } catch (AccessDeniedException ex) {
            return "access denied";
        } catch (IOException ex) {
            return "I/O unknown";
        } catch (SecurityException ex) {
            return "security denied";
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("attr-demo-", ".txt");
        try {
            System.out.println("created: " + describe(file));
        } finally {
            Files.deleteIfExists(file);
        }
        System.out.println("removed: " + describe(file));
    }
}
```

Compile and run:

```bash
javac ReadAttributesStatusDemo.java
java ReadAttributesStatusDemo
```

Stdout on a filesystem supporting basic attributes and operating normally:

```text
created: regular file
removed: missing
```

Points to note:

- `NoSuchFileException` gives different context from `AccessDeniedException`; `Files.exists` does not return a corresponding exception object to the caller.
- `NOFOLLOW_LINKS` makes `readAttributes` describe **the link entry** if the target is a symbolic link.
- A provider error may be a `FileSystemException` or another `IOException` subtype, not always one of the first two branches.
- In real use cases, do not "check existence first then read attributes" if a single `readAttributes` call already meets the goal; adding an extra query can introduce an unnecessary race.
- Even metadata just read can become stale before the next operation.

## 11. TOCTOU: Check-Then-Act Is Not Atomic

A common design mistake:

```java
if (Files.notExists(path)) {
    Files.writeString(path, "new content");
}
```

This is a **counterexample**. Even when `notExists` returns `true`, another process can create a file at `path` **after the check and before the write**. By default, `Files.writeString` can create or truncate a file according to its default open options, causing unintended overwriting. **Never** use a prior existence check as a substitute for atomic file creation.

Diagram:

```text
Process A                          Process B
---------                          ---------
Files.notExists(p) → true
                                   Creates p
Files.writeString(p, ...)
→ may affect p                     (race!)
```

The right technique when requiring "create file if absent and do not overwrite":

```java
try {
    Files.createFile(path);
    // Created successfully.
} catch (FileAlreadyExistsException ex) {
    // Name already exists, handle non-overwrite policy.
}
```

This is an **illustrative snippet**, with `path` as a `Path`; requires importing `Files`, `FileAlreadyExistsException`, and handling other `IOException` errors. By the `Files.createFile` contract, **checking existence and creating the file is an atomic operation** with respect to other filesystem activity affecting the directory, subject to provider support. If creation fails due to permissions or other faults, the API throws a different exception — never convert all errors into "file already exists."

Another option when you want to **create and write**, while refusing to overwrite an existing file:

```java
try (var out = Files.newOutputStream(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(payload);
}
```

This is an **illustrative snippet**; `payload` is `byte[]`, requiring importing `Files`, `StandardOpenOption`, and handling `IOException`. `CREATE_NEW` targets "create only if the file does not yet exist"; if an entry already exists, opening/creating fails instead of silently truncating the old file. Provider-specific rules and symlink handling still follow the actual method's contract.

### Do You Need `exists` Before Deleting a File?

No:

```java
Files.deleteIfExists(path);
```

This is an **illustrative snippet**; `path` is a `Path` and `IOException` is handled. `deleteIfExists` performs "delete if present" in **one API**, instead of writing:

```java
if (Files.exists(path)) {
    Files.delete(path);
}
```

This is an **unnecessary counterexample** because it introduces a race and a redundant check. Note that `deleteIfExists` can still throw `IOException` if deletion hits an error; `false` typically indicates nothing was deleted, not a permanent guarantee that the name remains absent. Nor does the API automatically resolve all symlink/permission risks in untrusted environments.

## 12. `exists`, `notExists`, and `Files.isRegularFile`

A path can exist without being a **regular file**:

```text
project/
├── config.json   (file)
├── cache/        (directory)
└── latest -> config.json (symlink)
```

When distinguishing types:

```java
if (Files.isRegularFile(path)) {
    System.out.println("regular file");
} else if (Files.isDirectory(path)) {
    System.out.println("directory");
} else if (Files.isSymbolicLink(path)) {
    System.out.println("symbolic link");
} else {
    System.out.println("other or cannot determine");
}
```

This is an **illustrative snippet**; `path` is a `Path` and `Files` is imported.

Notes:

- `isRegularFile` and `isDirectory` **follow symbolic links** by default, so if a link points to a regular file, `isRegularFile(link)` can be `true`.
- `isSymbolicLink` checks the link entry in the API's sense, not "what file it points to."
- If all predicates return `false`, do not assume the path is definitely an "other" entry type; it could also be **unverifiable**.
- When you want a related set of attributes read together in one call, use `Files.readAttributes(..., BasicFileAttributes.class, options)` where appropriate.
- Do not assume `exists == true` implies `isReadable == true`, or that `isRegularFile == true` guarantees the file still exists by the next open call.

## 13. Relative Paths and Access Permissions

`Path.of("report.txt")` is a relative path; it is interpreted according to the filesystem and the process's **working directory** when resolving an operation. If run from an IDE, terminal, service, or container with different working directories, the exact same path string can point to different entries.

```java
Path relative = Path.of("report.txt");
System.out.println(relative.toAbsolutePath());
```

This is an **illustrative snippet**; the absolute result depends on the environment.

A `Files.notExists(relative)` result is meaningful only for **the location the runtime currently resolves**, not proof that no file named `report.txt` exists anywhere on the machine.

For serious applications:

1. Define an explicit root working directory or configured path.
2. Use `Path.resolve` to join parent/child properly.
3. Control `normalize()`/canonicalization and symlinks according to your threat model.
4. Do not use `Files.exists` to determine real access permissions without handling errors on open.
5. If filenames come from users, guard against path traversal using appropriate filesystem access mechanisms, not merely existence checks.

### `SecurityException` vs. I/O Errors

Depending on environment and provider, `Files.exists`/`notExists` calls may undergo security permission checks and **throw `SecurityException`** instead of merely returning `false`. Never treat the absence of checked `IOException` in the signature as a guarantee of "no errors."

If business logic requires logging exact causes, call an API with proper exceptions (such as `readAttributes` or an open operation) and classify errors by filesystem semantics rather than retrying `Files.exists` until it returns true.

## 14. Common Mistakes and How to Fix Them

| Wrong approach | Problem | Better approach |
|---|---|---|
| `!Files.exists(p)` means file definitely absent | UNKNOWN also produces `false` from `exists` | `Files.notExists(p)` when needing confirmed absence |
| `Files.exists(p) \|\| Files.notExists(p)` is always true | Both can be false | Handle the UNKNOWN branch |
| On UNKNOWN, create file as if definitely vacant | May already exist without verification permission | Use `CREATE_NEW` or appropriate atomic create operation |
| Check `notExists` then write with default open | Race and risk of truncating newly created file | Create with `Files.createFile` or `CREATE_NEW` |
| Check `exists` then delete | Adds TOCTOU and redundant work | Use `deleteIfExists` per policy |
| Only check existence then read without catching errors | File can change or lack read permission | Try opening/reading directly and handle `IOException` |
| `exists == true` ⇒ regular file | Directories/links also exist | Use `isRegularFile` or attributes |
| `exists == false` ⇒ `notExists == true` | False when status cannot be verified | Maintain three separate states |
| Using `NOFOLLOW_LINKS` thinking it checks target | It checks the link entry itself | Choose an explicit link policy |
| Using only follow-links on a dangling symlink and concluding entry is gone | Target is gone yet link still exists | Use `NOFOLLOW_LINKS` when querying the entry |
| Confusing all query errors with `NoSuchFileException` | Permission/I/O errors and providers vary | Catch appropriate `IOException` subtypes |
| Testing UNKNOWN with chmod and asserting fixed output | Permission behavior varies by OS/user | Fake abstraction or conditional integration tests |
| Forgetting state changes between two calls | Non-atomic snapshot | Avoid pre-checks before operations when possible |
| Passing relative paths into a service without checking root | Working directory varies | Enforce configured root/paths |
| Using `exists` result as a security check | Does not prevent traversal/symlinks/TOCTOU | Use OS mechanisms and appropriate open APIs |
| Trusting `Files.exists` to validate checksum/content | Only relates to existence verification | Open, read, and validate actual contents |

## 15. Decision Workflow by Problem

### A. Only Need to Display Status in UI

You can use:

```java
if (Files.exists(p)) {
    status = "Present";
} else if (Files.notExists(p)) {
    status = "Absent";
} else {
    status = "Unknown";
}
```

This is an **illustrative snippet**; `p` is a `Path` and `status` is a `String` variable. The UI should preserve the ability to show **Unknown**. Do not attach a red "missing" label to every `false`.

### B. Need to Create a New File If Absent, Strictly Never Overwrite

Prefer `Files.createFile(p)` or opening with `StandardOpenOption.CREATE_NEW`. Catch `FileAlreadyExistsException` separately from other errors. **Do not** make `notExists` the sole condition.

### C. Need to Read File If Present, Skip If Missing

Try opening and reading directly:

```java
try (var in = Files.newInputStream(p)) {
    // Read data.
} catch (NoSuchFileException ex) {
    // Per application policy, skip if file does not exist.
} catch (IOException ex) {
    // Permission, filesystem, or other I/O error: report or handle appropriately.
}
```

This is an **illustrative snippet**, requiring importing `Files`, `NoSuchFileException`, `IOException`. Depending on the provider, not every missing-file case uses this exact subtype; consult the active I/O contract. Never swallow all `IOException` errors and turn them into "file missing."

### D. Need to Inspect Symlinks or Check Entries for Cleanup

Use `Files.exists(path, LinkOption.NOFOLLOW_LINKS)` and/or `Files.readAttributes(..., NOFOLLOW_LINKS)` if metadata is needed. When acting on the real entry, still handle races/permissions and `delete`/`move` errors.

### E. Need to Inventory Many Files on Remote Storage

One `exists` call per file can incur costly round-trips and produce an inconsistent snapshot. Consider dedicated listing/batch APIs from the provider, design retry/backoff, and represent **unknown** status explicitly when unreachable. Never treat "no response" as "does not exist."

## 16. Self-Check Exercises

**Question 1.** If `Files.exists(p) == false`, does the file definitely not exist?

**Answer:** No. The state could be ABSENT or UNKNOWN. Understand `Files.notExists(p)` as the check confirming absence.

**Question 2.** When do both `Files.exists(p)` and `Files.notExists(p)` return `false`?

**Answer:** When the provider cannot verify the state; for example, certain permission, metadata, or filesystem errors. That is UNKNOWN, not a logical contradiction in the API.

**Question 3.** Is `Files.notExists(p)` always equal to `!Files.exists(p)`?

**Answer:** No. In the UNKNOWN state, `notExists` is `false` whereas `!exists` is `true`.

**Question 4.** Why shouldn't you write `if (Files.notExists(p)) Files.writeString(p, data)` to prevent overwriting?

**Answer:** TOCTOU exists: a file can be created between the two statements. Use `CREATE_NEW` or `Files.createFile` to require non-overwriting creation.

**Question 5.** A symbolic link remains on disk while its target was deleted. What does default `exists(link)` ask?

**Answer:** It follows links by default, so it asks about the resolved target; it may be false when the target is gone. To ask about the symbolic link entry itself, use `NOFOLLOW_LINKS`.

**Question 6.** Does `Files.exists(path) == true` guarantee the file can be opened for reading?

**Answer:** No. The path may be a directory, lack read permission, or change after the check. Open/read and handle errors directly.

**Question 7.** If an application must distinguish nonexistent paths from access denied, what should it choose?

**Answer:** An API that queries metadata or performs the real operation with `IOException`/subtypes (e.g., `Files.readAttributes`), rather than relying solely on the `exists` boolean.

**Question 8.** What does `Files.deleteIfExists(p)` solve?

**Answer:** Combines the delete-if-present goal into one operation, avoiding unnecessary check-then-delete loops. It can still throw errors; it creates no permanent guarantee about state.

**Question 9.** Why are consecutive `exists` and `notExists` reads not an atomic snapshot?

**Answer:** The filesystem can change between the two calls; results are observed at different instants.

**Question 10.** Does `NOFOLLOW_LINKS` automatically protect against path traversal and symlink races?

**Answer:** No. It only changes which object is checked; safety requires proper root design, permissions, and direct operation APIs.

## Summary

- `Files.exists(p)` **confirms existence** when possible.
- `Files.notExists(p)` **confirms non-existence** when possible.
- If **both are false**, the state is **UNKNOWN**, and must not be forced into ABSENT.
- Both checks are **non-atomic**, do not replace actual open/create/delete operations, and do not guarantee permissions, content, or data durability.
- For symlinks, distinguish **following the link** from **`NOFOLLOW_LINKS`**; a dangling symlink can exist even when its target does not.
- When contextual errors are needed, choose an API returning `IOException` and handle appropriate subtypes; when creating a file without overwriting, use `CREATE_NEW` or `Files.createFile`.
- When writing Java 17 applications, represent **PRESENT / ABSENT / UNKNOWN** transparently and always control TOCTOU, ownership, filesystem providers, and security policies.
