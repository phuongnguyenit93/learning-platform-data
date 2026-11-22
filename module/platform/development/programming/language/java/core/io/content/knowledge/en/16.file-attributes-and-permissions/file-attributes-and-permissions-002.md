# Creation, Modification, Access Times, and `FileTime` in Java NIO.2

## Lesson Objectives

A file does not only have a name, size, and content. The filesystem can also store **timestamps**, typically including **creation time**, **last-modified time**, and **last-access time**. In Java NIO.2, `BasicFileAttributes` lets you read these three attributes; `FileTime` is the type representing a point in time used in filesystem APIs.

These timestamps are **not an identical absolute contract across every operating system, storage device, or filesystem**. Some timestamps are not genuinely supported; a value may be a fallback value, rounded to a resolution, delayed in updating, or changed by copy/sync tools.

After this lesson, you can:

- Distinguish `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`, and avoid confusing **Unix ctime** with creation time.
- Read attributes via `Files.readAttributes(..., BasicFileAttributes.class)`, `Files.getLastModifiedTime()`, or `Files.getAttribute()`.
- Use `FileTime.fromMillis(...)`, `FileTime.from(Instant)`, `toMillis()`, `toInstant()`, `to(TimeUnit)`, `compareTo()`.
- Understand that `Instant` is a timezone-independent point in time; timezones only appear during **display**, such as `Asia/Ho_Chi_Minh`.
- Change `lastModifiedTime` with `Files.setLastModifiedTime()` and explore `BasicFileAttributeView.setTimes()` for other timestamps.
- Handle symbolic links with `LinkOption.NOFOLLOW_LINKS`, `IOException` errors, resolution issues, metadata copying, and **TOCTOU**.
- Run the Java 17+ examples and accurately interpret **stable** results versus **filesystem-dependent** results.

## 1. Three Main Types of Time

Suppose a file is created, then written to again, and read:

```text
09:00   Create file "report.txt"
09:15   Modify content of "report.txt"
09:20   Open and read content
            │
            ├─ creationTime       → creation time (if supported by the filesystem)
            ├─ lastModifiedTime   → content modification time per metadata
            └─ lastAccessTime     → access time per metadata
```

This is a **conceptual illustration**, not a guarantee that every system records exactly 09:00, 09:15, and 09:20. On some filesystems, `lastAccessTime` is not updated on every read; `creationTime` may be missing or emulated.

| Timestamp | Java NIO.2 | Question It *Usually* Answers | Notes |
|---|---|---|---|
| **Creation time** | `BasicFileAttributes.creationTime()` | When was the entry/file created? | Not every filesystem stores a "birth time"; may return a provider default value |
| **Last modified time** | `BasicFileAttributes.lastModifiedTime()` | When was the file content most recently modified? | Can be reset by APIs, copy, or restore; not a content checksum |
| **Last access time** | `BasicFileAttributes.lastAccessTime()` | When was the file most recently accessed? | Updates may be disabled or throttled to optimize I/O |

### Is Creation Time Always Reliable?

No. `creationTime()` is the creation time **to the extent provided by the filesystem/provider**. If creation time is not supported, Java allows the provider to return an **implementation-specific default value**, such as the last-modified time. A non-`null` value does not prove it is the file's original creation timestamp.

In addition:

- **Copying** a file can create a new entry while **preserving source metadata** if the application uses an attribute-preserving mechanism.
- **Move/rename** on the same filesystem is usually not equivalent to creating new content, though timestamp semantics depend on the filesystem.
- A file **restored** from backup or an archive may carry the restored timestamp rather than the time it actually appeared at the destination.
- A file can be created and then have its timestamp manually set within what the filesystem permits.

Do not use `creationTime()` as an ID, sole forensic proof, anti-fraud source of truth, or transaction lock.

### Does Last Modified Time Record Every Metadata Change?

Do not assume so. In the POSIX model, a content change typically updates `mtime`; metadata changes such as mode/owner typically relate to `ctime`. **Unix ctime is typically *status-change time*, not creation time**. This is an especially common confusion when seeing the letter "c".

Standard `BasicFileAttributes` has `creationTime`, `lastModifiedTime`, and `lastAccessTime`; it does not define a standard `ctime()` method equivalent to POSIX status-change time. If specialized metadata is needed, check the capabilities of the provider, OS, or corresponding native APIs.

### Does Last Access Time Change After Every `read()`?

**It is not guaranteed.** Many systems employ optimizations such as not writing access time or updating it only under certain conditions (*noatime*, *relatime* in some Unix environments). Certain filesystems, devices, caching mechanisms, or read methods also have their own behavior.

Therefore, do not build an algorithm like "the file with the oldest atime was definitely not used recently" if high accuracy is required by the business logic. For products tracking access counts, record access events managed by the **application**, rather than treating atime as an absolute business log.

## 2. APIs for Reading Timestamps in Java 17

Common imports:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
```

### 2.1. Reading All Three Times in One Call

```java
BasicFileAttributes attrs = Files.readAttributes(
    path,
    BasicFileAttributes.class
);

FileTime created = attrs.creationTime();
FileTime modified = attrs.lastModifiedTime();
FileTime accessed = attrs.lastAccessTime();
```

This is an **illustrative snippet**; `path` is a valid `Path` and the caller must handle `IOException`.

`BasicFileAttributes` also has methods like `size()`, `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, and `fileKey()`. If you need both the file type and multiple timestamps, fetching `BasicFileAttributes` together clearly expresses "reading a metadata group" and usually avoids three separate metadata calls.

**Do not interpret "reading `BasicFileAttributes` together" as a completely atomic filesystem transaction.** A provider might not gather every attribute in one indivisible operation, and the file can still be modified concurrently.

### 2.2. Reading Last-Modified Time Alone

```java
FileTime modified = Files.getLastModifiedTime(path);
```

This is an **illustrative snippet**; `IOException` must be handled. This API is convenient when the problem only needs one timestamp. By default it **follows symbolic links**; you can pass `LinkOption.NOFOLLOW_LINKS` when you want to read the metadata of the link itself:

```java
FileTime linkModified = Files.getLastModifiedTime(
    path, LinkOption.NOFOLLOW_LINKS
);
```

`NOFOLLOW_LINKS` is meaningful when `path` points to a symbolic link. It does not by itself guarantee that filesystems support all link attributes or eliminate races between operations.

### 2.3. Reading by String Attribute Name

If an API requires an attribute name:

```java
FileTime modified = (FileTime) Files.getAttribute(
    path, "basic:lastModifiedTime"
);
```

This is an **illustrative snippet**; `IOException` must be handled. A provider may support the `basic` attribute view and additional views. When you know in advance that you need the three standard timestamps, the **strongly typed** `BasicFileAttributes` API is usually clearer and avoids mistaken casts.

Multiple attributes can be read with the syntax:

```java
Map<String, Object> values = Files.readAttributes(
    path, "basic:creationTime,lastModifiedTime,lastAccessTime"
);
```

This is an **illustrative snippet** requiring `import java.util.Map` and `IOException` handling. Values have type `Object`, so code must cast appropriately to `FileTime` when retrieving each key. If you are only learning the three basic timestamps, prefer `BasicFileAttributes` so the compiler helps type-check the data.

### 2.4. Following Symbolic Links by Default

Attribute-reading calls can be passed `NOFOLLOW_LINKS` to change the target under inspection. By default, many NIO.2 reads **traverse symbolic links** and fetch the target's information. This directly affects the meaning of "creation time of *what*?": **the link entry** or **the target file**.

## 3. `FileTime`: Representing a Point in Time for the Filesystem

`java.nio.file.attribute.FileTime` is an immutable type representing a point in time in file attribute APIs. Do not confuse it with `java.io.File`; nor should you confuse `FileTime` with `LocalDateTime` (a local date-time without an explicit timezone).

Useful methods:

| API | Meaning |
|---|---|
| `FileTime.fromMillis(long value)` | Creates from milliseconds since the Unix epoch |
| `FileTime.from(long value, TimeUnit unit)` | Creates from a quantity of time units relative to the epoch |
| `FileTime.from(Instant instant)` | Creates from `java.time.Instant` |
| `fileTime.toMillis()` | Converts to milliseconds since the epoch, **may lose precision** |
| `fileTime.to(TimeUnit unit)` | Converts to a value in the corresponding unit |
| `fileTime.toInstant()` | Converts to `Instant`, convenient for calculations and display |
| `fileTime.compareTo(other)` | Compares chronological order |
| `fileTime.equals(other)` | Compares two `FileTime` values per value contract |
| `fileTime.toString()` | String representation of the timestamp per API contract |

`FileTime` is not merely a number of milliseconds; it can represent precisions other than milliseconds. `FileTime.from(Instant)` also lets you work with nanoseconds if the `Instant` contains a nanosecond component.

### Unix Epoch and Precision

The **Unix epoch** is `1970-01-01T00:00:00Z`. Values measured from the epoch can be negative if the point in time is before the epoch. For example:

```java
FileTime epoch = FileTime.fromMillis(0);
FileTime plusOneSecond = FileTime.from(1, TimeUnit.SECONDS);
```

This is an **illustrative snippet** requiring `FileTime` and `TimeUnit` (`java.util.concurrent.TimeUnit`).

Differences:

- `fromMillis(1_000)` and `from(1, TimeUnit.SECONDS)` represent **the same instant**.
- `from(Instant.parse("2025-01-01T00:00:00.123456789Z"))` has finer nanosecond detail than a millisecond value.
- When calling `toMillis()`, the sub-millisecond part **is not retained**; you cannot recover nanoseconds from `long` milliseconds alone.
- Converting to `TimeUnit.SECONDS` also loses sub-second detail.
- For extremely large timestamps exceeding the target type's representable range, conversions may **saturate** at boundary values rather than giving an infinite mathematical result. Do not build algorithms requiring infinite `long` precision.

In other words: **representation precision in Java** differs from **the actual resolution a filesystem can store**. A `FileTime` with 9 decimal fractional digits does not mean the filesystem will always store all 9 digits.

### `FileTime` vs. `Instant`

`Instant` belongs to `java.time` and describes a point on the UTC timeline, making it well-suited for comparisons or computing durations. `FileTime` is the type for interacting with file attributes. When an application needs time logic:

```java
Instant instant = fileTime.toInstant();
Duration age = Duration.between(instant, Instant.now());
```

This is an **illustrative snippet** requiring `Duration`, `Instant`, and a `fileTime` variable of type `FileTime`. `Instant.now()` depends on the clock at execution time; deterministic tests should supply a fixed `Clock` or `Instant` rather than comparing against the system clock.

Do not assume a timestamp "older than 24 hours" is always proof that the file has not changed or been read in 24 hours, because metadata may have been modified or not updated.

## 4. Java 17 Example: Converting `FileTime`, `Instant`, and Timezones

The first example **does not access the filesystem**. It helps test time APIs without interference from device resolution, permissions, or metadata policies.

Save **`FileTimeBasicsDemo.java`**:

```java
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.TimeUnit;

public class FileTimeBasicsDemo {
    public static void main(String[] args) {
        Instant point = Instant.parse(
            "2024-02-29T12:34:56.123456789Z"
        );
        FileTime fileTime = FileTime.from(point);

        System.out.println("instant: " + fileTime.toInstant());
        System.out.println("millis: " + fileTime.toMillis());
        System.out.println("round trip: " +
            fileTime.toInstant().equals(point));

        FileTime twoSeconds = FileTime.from(
            2, TimeUnit.SECONDS
        );
        System.out.println("two seconds: " +
            twoSeconds.toInstant());

        DateTimeFormatter local = DateTimeFormatter
            .ofPattern("uuuu-MM-dd HH:mm:ss")
            .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("Vietnam time: " +
            local.format(fileTime.toInstant()));
    }
}
```

Compile and run:

```bash
javac FileTimeBasicsDemo.java
java FileTimeBasicsDemo
```

Stdout:

```text
instant: 2024-02-29T12:34:56.123456789Z
millis: 1709210096123
round trip: true
two seconds: 1970-01-01T00:00:02Z
Vietnam time: 2024-02-29 19:34:56
```

Explanation:

1. `Instant.parse(...Z)` parses a UTC instant. `FileTime.from(point)` creates the corresponding timestamp value.
2. `toInstant()` preserves the original instant in this normal value case.
3. `toMillis()` returns milliseconds from the epoch; **the `456789` nanoseconds after 123 milliseconds are not retained**.
4. `FileTime.from(2, TimeUnit.SECONDS)` represents two seconds after the epoch.
5. The formatter uses the `Asia/Ho_Chi_Minh` zone to display local time: in Feb 2024 this offset is UTC+07, so `12:34:56Z` becomes `19:34:56`.

The point in time **is not "changed into a different point in time"** when displayed in a timezone; only the presentation of the same point on the timeline changes. When storing state to transmit between systems, `Instant` or epoch time in an agreed-upon unit is usually more appropriate than a local date-time string without a zone.

## 5. Reading Real Timestamps with `BasicFileAttributes`

A real filesystem returns times it manages. Distinguish **what is guaranteed by the type/API** from **concrete environment-dependent values**.

Save **`ReadFileTimesDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class ReadFileTimesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("times-read-", ".txt");

        try {
            BasicFileAttributes attrs = Files.readAttributes(
                file, BasicFileAttributes.class
            );

            System.out.println("regular: " +
                attrs.isRegularFile());
            System.out.println("created available: " +
                (attrs.creationTime() != null));
            System.out.println("modified available: " +
                (attrs.lastModifiedTime() != null));
            System.out.println("accessed available: " +
                (attrs.lastAccessTime() != null));

            // Specific values will differ on each run.
            System.out.println(
                "created value: " + attrs.creationTime());
            System.out.println(
                "modified value: " + attrs.lastModifiedTime());
            System.out.println(
                "accessed value: " + attrs.lastAccessTime());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run:

```bash
javac ReadFileTimesDemo.java
java ReadFileTimesDemo
```

The first part of stdout is **typically**:

```text
regular: true
created available: true
modified available: true
accessed available: true
```

Following that are three lines `created value: ...`, `modified value: ...`, `accessed value: ...`; **there is no fixed timestamp output**, because the temporary file creation time is supplied by the filesystem. The `BasicFileAttributes` API returns `FileTime` objects for the three time methods, but a timestamp may be a **default value** when the filesystem does not store the real attribute; "available" in the program only checks **that the object is non-null**, not proof that "the filesystem supports an exact creation timestamp".

Do not write unit tests asserting **all three timestamps are equal** immediately after `createTempFile`: resolution or metadata updates can make them differ. Nor should you assume creation time behaves the same on Linux as on Windows; that depends on the filesystem and provider.

## 6. Changing `lastModifiedTime`: `Files.setLastModifiedTime`

If business logic must **set the modification time** of a file:

```java
FileTime requested = FileTime.from(
    Instant.parse("2024-01-01T00:00:00Z")
);

Files.setLastModifiedTime(path, requested);
```

This is an **illustrative snippet**; `IOException` must be handled and `path` is the `Path` whose attribute is to be updated. `setLastModifiedTime` returns the `Path`, which is convenient for chaining but is not a promise that the filesystem stored **exact nanosecond precision**.

Limitations to keep in mind:

- The operation can fail due to access permissions, a read-only filesystem, an unsupported provider, or an I/O error.
- The filesystem may store time at a **lower resolution** or round/truncate fractional parts.
- If the timestamp is outside the range the filesystem can store, the result may be clamped per the API/provider or throw an error.
- Another process may write to the file right after you set the timestamp, changing last-modified time again.
- Changing mtime does **not** change file contents. Therefore metadata time is **not a checksum** or proof of identical data.

### Java 17 Example: Setting and Reading Back mtime for Verification

Save **`SetModifiedTimeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class SetModifiedTimeDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mtime-demo-", ".txt");
        FileTime requested = FileTime.from(
            Instant.parse("2020-01-01T00:00:00Z")
        );

        try {
            Files.setLastModifiedTime(file, requested);

            FileTime stored = Files.getLastModifiedTime(file);
            System.out.println("requested: " +
                requested.toInstant());
            System.out.println("stored: " +
                stored.toInstant());
            System.out.println("same instant: " +
                requested.toInstant().equals(stored.toInstant()));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run:

```bash
javac SetModifiedTimeDemo.java
java SetModifiedTimeDemo
```

On a filesystem that supports and accurately retains 2020-01-01 00:00:00 UTC at second resolution, stdout will be:

```text
requested: 2020-01-01T00:00:00Z
stored: 2020-01-01T00:00:00Z
same instant: true
```

**This is conditional output.** The filesystem may store a different timestamp due to provider rules/resolution, or `setLastModifiedTime` may throw `IOException`. The program prints both `requested` and `stored` values for **actual observation**, without implicitly claiming they are always equal.

Choosing a timestamp aligned on an exact second makes the example less prone to rounding differences than using a time with nanoseconds. In production code, read back if storing the exact time is a requirement, though even a readback only reflects the state at the moment of observation.

## 7. Setting Multiple Timestamps via `BasicFileAttributeView.setTimes`

Java provides `BasicFileAttributeView` to work with basic file attributes. With a supporting implementation, you can request updates to **mtime**, **atime**, and **creation time**:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
    path, BasicFileAttributeView.class
);

view.setTimes(modified, accessed, created);
```

This is an **illustrative snippet** requiring imports for `java.nio.file.attribute.BasicFileAttributeView`, `Files`, and `FileTime` variables, plus `IOException` handling. Do not assume every provider allows modifying all three timestamps, especially creation time.

Signature:

```java
void setTimes(
    FileTime lastModifiedTime,
    FileTime lastAccessTime,
    FileTime createTime
) throws IOException;
```

This is an **illustrative API signature**, not a new definition. Parameter meanings:

1. `lastModifiedTime`: content modification time.
2. `lastAccessTime`: last access time.
3. `createTime`: creation time.

**Passing `null` for a parameter** means no update is requested for the corresponding attribute, which is very useful when you only want to set one timestamp without altering the other two.

Example requesting only to set access time:

```java
view.setTimes(null, desiredAccessTime, null);
```

This is an **illustrative snippet**. The call may throw `IOException`; the provider might not support setting access time as requested by the application. Depending on the filesystem, an unsupported attribute may be ignored per provider contract or fail to update; you must check the environment's documentation/capabilities.

### Changing the Timestamp of a Symlink Itself

If you need to handle attributes of **the link entry**, not the target, obtain the view with `NOFOLLOW_LINKS`:

```java
BasicFileAttributeView linkView =
    Files.getFileAttributeView(
        link,
        BasicFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS
    );
```

This is an **illustrative snippet**, with `link` of type `Path`. A filesystem may not allow modifying a symbolic link's timestamps via this view, or may behave differently when privileges are lacking. Do not call `setTimes` when `linkView == null` (if the provider does not support the requested attribute view); usually the default filesystem has a basic view, but code targeting arbitrary providers should check capability.

**Note on other metadata:** Setting mtime/atime does not mean all other metadata remains immutable. The filesystem may update status-change timestamps or internal administrative info; programs should not over-assert about attributes outside the Java NIO.2 contract.

## 8. Java 17 Example: Requesting Only an Access Time Change

To clearly see how `setTimes` works with `null` and how provider differences are handled, use the following program.

Save **`SetAccessTimeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class SetAccessTimeDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("atime-demo-", ".txt");

        try {
            BasicFileAttributeView view =
                Files.getFileAttributeView(
                    file, BasicFileAttributeView.class);

            if (view == null) {
                System.out.println("Basic view unavailable");
                return;
            }

            FileTime desired = FileTime.from(
                Instant.parse("2020-01-01T00:00:00Z")
            );

            try {
                view.setTimes(null, desired, null);
                BasicFileAttributes attrs = view.readAttributes();

                System.out.println("requested: " +
                    desired.toInstant());
                System.out.println("observed: " +
                    attrs.lastAccessTime().toInstant());
            } catch (IOException | UnsupportedOperationException ex) {
                System.out.println(
                    "Access-time update unavailable");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run:

```bash
javac SetAccessTimeDemo.java
java SetAccessTimeDemo
```

On a filesystem supporting changing atime as requested, the two observed lines are typically:

```text
requested: 2020-01-01T00:00:00Z
observed: 2020-01-01T00:00:00Z
```

Some environments may display a different `observed` timestamp, print `Access-time update unavailable`, or not supply the requested view. The purpose of the example is to **execute and observe** the call, not to assert a single outcome across all filesystems.

In particular, **reading metadata** is not the same as reading file contents. However, providers can have their own access-time update policies, so do not rely on a single experiment to conclude that all subsequent operations will leave atime unchanged.

## 9. Timezones, UTC, and How to Display Timestamps

`FileTime` timestamps represent **a point in time**, not a date/time pair tied to the viewer's timezone. To display appropriately for users, convert to `Instant`, then use `ZoneId` and `DateTimeFormatter`:

```java
DateTimeFormatter fmt = DateTimeFormatter
    .ofPattern("uuuu-MM-dd HH:mm:ss z")
    .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(
    fmt.format(fileTime.toInstant())
);
```

This is an **illustrative snippet** requiring imports for `java.time.ZoneId`, `java.time.format.DateTimeFormatter`, and a `fileTime` variable.

**Do not** interpret `toMillis()` as milliseconds in Vietnam time or local machine time: epoch milliseconds are the number of milliseconds on the UTC timeline. Converting to GMT+7 only affects presentation.

An easy-to-confuse situation:

- Java prints timestamp `2024-02-29T12:34:56Z`.
- The file manager on a machine in Vietnam may display `19:34:56`.
- Both values can refer to **the exact same instant**, not a file modified twice.

When exchanging timestamps between services, specify an unambiguous instant format such as ISO-8601 with offset/UTC or epoch milliseconds; do not send a bare `"29/02/2024 19:34:56"` without specifying a timezone if the system spans multiple geographic regions.

### `LocalDateTime` Is Not `Instant`

`LocalDateTime` is a date-time **without a zone/offset**; `Instant` is a point in time with absolute meaning. Do not do:

```java
LocalDateTime local = LocalDateTime.parse("2024-02-29T19:34:56");
// Cannot infer a unique Instant without specifying a zone/offset.
```

This is an **illustrative snippet** requiring an import for `LocalDateTime`. The same local date-time can correspond to different instants around the world, and in some timezones with DST transitions there are even repeated or non-existent local intervals.

## 10. Resolution, Rounding, and Consistency

Not every filesystem stores timestamps accurately to the nanosecond. A theoretical example:

```text
Java requests mtime:
2024-01-01T00:00:00.123456789Z

Filesystem A can store:
2024-01-01T00:00:00.123456789Z

Filesystem B might only store:
2024-01-01T00:00:00.123Z

Filesystem C might store at a coarser step:
2024-01-01T00:00:00Z
```

This is an **illustration**, not claiming any specific filesystem always uses one of these exact three levels.

Consequences:

1. **Do not compare `FileTime` down to the nanosecond** in portable integration tests after setting/reading timestamps, unless the environment has a documented resolution contract.
2. When checking "whether a file changed", an equal mtime does **not** guarantee identical content. Two writes can land within the same timestamp tick or mtime could have been reset.
3. When checking "whether mtime differs", backup/restore/copy operations themselves can alter timestamps without changing content.
4. `Files.readAttributes` on a network filesystem may reflect cached metadata; do not assume values always update instantaneously across all machines.
5. `FileTime.toMillis()` drops sub-millisecond parts; avoid converting via milliseconds if business logic requires high precision and both source and destination genuinely support it.
6. File age calculations using `Instant.now()` are also affected by clock skew or system clock adjustments; do not treat mtime as a monotonic clock.

If you want to measure **how long a task takes to run**, use `System.nanoTime()` or an appropriate monotonic clock, **do not use file modification time** as a performance timer.

### Using mtime for Caching or Incremental Scans

A file scanner commonly does:

```text
Previous run: store (path, mtime, size)
Next run: fetch fresh metadata, if different → reprocess
```

This is an **optimization heuristic**, not cryptographic proof that a file is unchanged if metadata matches. For strong integrity, you may need a content hash or a consistently managed version/commit ID system. Hashing must also be computed from properly read data, while the file might be modified concurrently; strict systems may require snapshots or storage transaction mechanisms.

## 11. Copying, Moving, and Timestamps

Copying a file does not necessarily preserve all source timestamps. `Files.copy` has the option `StandardCopyOption.COPY_ATTRIBUTES` to **attempt to copy metadata** when supported by the provider:

```java
Files.copy(
    source,
    target,
    StandardCopyOption.COPY_ATTRIBUTES
);
```

This is an **illustrative snippet**, with `source` and `target` of type `Path`, `Files`/`StandardCopyOption` imported, and `IOException` handled. Some attributes cannot be copied accurately or are restricted by the provider; the exact level of support depends on the filesystem. Simply requesting `COPY_ATTRIBUTES` **does not let you conclude** that creation/modified/access times of the target file match the source identically in every environment.

Questions that must be decided by business requirements:

- Is the target file a **historical copy** and should it keep the source's mtime?
- Is the target file a **newly generated document**, and should it have the current timestamp?
- When restoring, which metadata must be restored? Are privileges sufficient to set creation time?
- If the goal uses mtime for cache invalidation, could copying while preserving mtime cause a cache to skip different content?

**Move/rename** can also affect timestamps under rules different from copy. With `ATOMIC_MOVE`, the option focuses on the atomicity of the move operation at the provider-supported level, not a promise that all timestamps remain immutable and crash-durable.

## 12. Symbolic Links and Object Identity

When working with symlinks:

```text
root/
├── target.txt          (actual content)
└── shortcut.txt -> target.txt
```

There are at least two metadata groups of interest:

- Metadata of **target.txt**.
- Metadata of **shortcut.txt** itself as a symbolic link entry.

`Files.readAttributes(link, BasicFileAttributes.class)` normally follows the link and reads the target's attributes; `Files.readAttributes(link, BasicFileAttributes.class, NOFOLLOW_LINKS)` reads the link entry's attributes if supported by the provider.

```java
BasicFileAttributes targetAttributes = Files.readAttributes(
    link, BasicFileAttributes.class
);

BasicFileAttributes linkAttributes = Files.readAttributes(
    link, BasicFileAttributes.class,
    LinkOption.NOFOLLOW_LINKS
);
```

This is an **illustrative snippet**; `link` is a `Path`, requiring corresponding imports and `IOException` handling.

If it is a **dangling link** (the target was deleted), the follow-link call can fail or fail to resolve the target, whereas `NOFOLLOW_LINKS` can read the metadata of the still-existing link entry. A link having a different mtime from its target is normal; you cannot infer link state from the target's mtime or vice versa.

### Do Not Use Timestamps as Durable IDs

Two files can have the same mtime; one file can be replaced by another file **with the same name, same size, and same mtime**. If object identification is needed, `BasicFileAttributes.fileKey()` can help on some providers, but **is not guaranteed to be non-null or persistent across all operations/restarts**. Depending on the goal, you need a database ID, content hash, version, or a safely opened handle.

## 13. Error Handling When Reading and Setting Timestamps

Metadata APIs can throw:

| Error/Situation | Interpretation |
|---|---|
| `NoSuchFileException` | The path no longer exists at operation time (if the provider reports this subtype) |
| `AccessDeniedException` | Insufficient permissions for the corresponding operation |
| `FileSystemException` | Specific filesystem error, possibly with a reason |
| `IOException` | General I/O error or provider error |
| `UnsupportedOperationException` | Operation/attribute/option not supported per API/provider |
| `SecurityException` | Runtime security check denied per environment |
| Default timestamp result | Not always an error; the provider may not support real timestamps |

Do not catch every `IOException` and print "file does not exist". Permission errors, device errors, and missing paths require different retry/error-reporting policies.

A handling snippet:

```java
try {
    BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class
    );
    System.out.println(attrs.lastModifiedTime());
} catch (NoSuchFileException ex) {
    System.err.println("Path missing: " + path);
} catch (AccessDeniedException ex) {
    System.err.println("Access denied: " + path);
} catch (IOException ex) {
    System.err.println("Metadata I/O error: " + ex.getMessage());
}
```

This is an **illustrative snippet** requiring `Files`, `Path`, `BasicFileAttributes`, and the `java.nio.file` exception subtypes.

With multi-provider filesystems, exception subtypes are not always identical. In applications that need to control retry/backup, log context, distinguish transient errors from definitive errors, and avoid deleting/updating files just because metadata could not be read.

## 14. TOCTOU: Newly Read Metadata Can Already Be Stale

A piece of code:

```java
if (Files.getLastModifiedTime(path).toMillis() < cutoff) {
    Files.delete(path);
}
```

This is a **dangerous anti-pattern if the directory is modified concurrently**. After the check, another process can overwrite or replace the entry. Deleting by pathname afterward may cause the program to delete **the new file**, not the old file the metadata just described.

Timeline:

```text
T1  Scanner reads mtime of report.txt → "old"
T2  Another process replaces report.txt with a new version
T3  Scanner calls Files.delete(report.txt)
T4  The new version is deleted unintentionally
```

This is a form of **time-of-check-to-time-of-use**. A `readAttributes` call does not hold a filesystem lock after the method returns.

Environment-dependent ways to reduce risk:

- Restrict write permissions on the scanned directory; avoid letting untrusted processes modify it concurrently.
- Use an appropriate version/snapshot/lock workflow or store state through application transactions.
- For directory operations needing protection against path races, consider `SecureDirectoryStream` if supported by the provider.
- If you must delete only files definitely belonging to a specific version, design a protocol with IDs/versions; do not rely solely on `mtime`/filename.
- Re-checking right before deletion can reduce race probability, but **does not eliminate** the window between check and operation.

**Timestamps are not a security or synchronization mechanism.**

## 15. `java.io.File.lastModified()` vs. NIO.2

Traditional Java I/O has the methods:

```java
File f = new File("report.txt");
long modifiedMillis = f.lastModified();
boolean changed = f.setLastModified(
    1_700_000_000_000L
);
```

This is an **illustrative snippet** requiring `import java.io.File`. There are two notable limitations:

- `File.lastModified()` returns `long` milliseconds; **0L can also be the value indicating information could not be obtained** per contract, creating ambiguity with the real epoch timestamp.
- `File.setLastModified(long)` returns a `boolean` indicating success/failure, providing less rich error information than `Files.setLastModifiedTime` and checked exceptions.

NIO.2 usually expresses this more accurately:

```java
Path path = f.toPath();
FileTime mtime = Files.getLastModifiedTime(path);
Files.setLastModifiedTime(
    path, FileTime.fromMillis(1_700_000_000_000L)
);
```

This is an **illustrative snippet** requiring imports for `Files`, `Path`, `FileTime`, and `IOException` handling.

If the goal is **creation/access time**, `BasicFileAttributes` and `BasicFileAttributeView` are the appropriate general-purpose APIs. Do not try to read "creation time" from `File.lastModified()` because those are two different attributes.

## 16. Common Mistakes

1. **Confusing Unix `ctime` with creation time.** On many Unix systems, `ctime` refers to metadata status changes, not "birth time".
2. **Believing `creationTime()` is always the real creation timestamp.** Providers may return a fallback value if unsupported.
3. **Believing `lastAccessTime()` always changes after every read.** Policies like noatime/relatime, caching, and providers affect updates.
4. **Comparing timestamps using local date-time strings.** Use `Instant`/`FileTime` to compare instants; use a timezone when presenting.
5. **Assuming `FileTime.toMillis()` preserves nanoseconds.** It only represents milliseconds; smaller fractions are lost.
6. **Setting mtime with arbitrary nanoseconds and asserting 100% identical readback.** Filesystems may round or have lower resolution.
7. **Treating files with the same mtime as having identical content.** Add version/hash verification if required by business logic.
8. **Treating a different mtime as proof of different content.** Metadata can be changed via copy/restore or time-setting APIs.
9. **Confusing symlink timestamps with target timestamps.** Choose link-following or `NOFOLLOW_LINKS` based on the question.
10. **Ignoring `IOException` when setting times.** Permissions, read-only filesystems, and providers can reject updates.
11. **Forgetting `null` in `BasicFileAttributeView.setTimes`.** `null` means do not request setting that timestamp, not "set to epoch".
12. **Calling `Files.exists()` before every operation and thinking races are avoided.** The check result can be stale; the main operation still needs error handling.
13. **Using mtime as a file ID.** Timestamps are not unique and can be forged or preserved when a file is replaced.
14. **Failing to distinguish `FileTime` from `LocalDateTime`.** `FileTime` is a filesystem instant; `LocalDateTime` lacks a zone/offset.
15. **Assuming the Java API always flushes metadata durably to disk.** A successful time update is not a crash-durability guarantee on every device.
16. **Interpreting `Files.copy(..., COPY_ATTRIBUTES)` as preserving every timestamp perfectly.** Metadata copying capability depends on the provider and storage.
17. **Failing to test on the actual target filesystem.** Local development, network mounts, containers, and production may have different timestamp behaviors.

## 17. API Selection Table by Scenario

| Need | Recommended API/Design |
|---|---|
| Inspect a file's modification time | `Files.getLastModifiedTime(path)` |
| Inspect creation/modification/access together | `Files.readAttributes(path, BasicFileAttributes.class)` |
| Need metadata of the symbolic link itself | Pass `LinkOption.NOFOLLOW_LINKS` when supported by the API |
| Set mtime | `Files.setLastModifiedTime(path, fileTime)` |
| Request setting atime/creation time | `BasicFileAttributeView.setTimes(...)` and check provider |
| Store/transmit a point in time | `Instant` or epoch millis with an agreed unit |
| Display in Vietnam time | `fileTime.toInstant()` + `ZoneId.of("Asia/Ho_Chi_Minh")` |
| Compare two timestamps | `FileTime.compareTo` or `Instant.compareTo` |
| Strong check for content changes | Hash/version and appropriate synchronization, not mtime alone |
| Track business-level access | Application-managed access logs/events |
| Need clear I/O error reporting | NIO.2 APIs with `IOException`/subtypes |
| Create/delete by state to avoid races | Direct operation APIs, versions/transactions instead of check-then-act |

## 18. Self-Check Questions

**Question 1.** What are the three key time methods of `BasicFileAttributes`?

**Answer:** `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`; they return `FileTime`.

**Question 2.** Is `creationTime()` always equal to the moment the file first appeared on disk?

**Answer:** No. The filesystem may not support a true creation timestamp, the provider may return a default value; copy/restore/metadata-setting operations can also alter the meaning of the timestamp.

**Question 3.** Is Unix `ctime` the creation time?

**Answer:** Typically no. Unix `ctime` is the inode/metadata status-change time; it differs from birth/creation time.

**Question 4.** Do `FileTime.from(Instant)` and `toMillis()` always preserve nanoseconds?

**Answer:** `FileTime` can represent high precision, but `toMillis()` drops sub-millisecond precision. Actual filesystems also have their own resolution.

**Question 5.** Why is `lastAccessTime()` unsuitable as a reliable read-access history?

**Answer:** The OS/filesystem may not update atime on every read or may use optimization policies and caching; timestamps can also be reset.

**Question 6.** To set only mtime via `BasicFileAttributeView.setTimes`, what arguments do you pass?

**Answer:** `view.setTimes(desiredModified, null, null)`. The two `null`s mean no update is requested for atime and creation time.

**Question 7.** To read metadata of a symlink rather than its target, how do you do it?

**Answer:** `Files.readAttributes(link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)` when supported by the provider.

**Question 8.** Can you conclude a file's content is unchanged when mtime and size are unchanged?

**Answer:** No. Mtime can be rounded or reset; content can change while size remains the same. It is only a heuristic.

**Question 9.** Does a successful `Files.setLastModifiedTime` guarantee reading back the exact nanosecond timestamp?

**Answer:** No. Resolution, time range, permissions, and filesystem/provider behavior can cause differences; if critical, read back and verify per environment.

**Question 10.** Is reading mtime and deleting the file if mtime is too old safe when other processes also write to that directory?

**Answer:** Not necessarily. This is TOCTOU: the file could be replaced before deletion. Use versioning, locks/snapshots, or an appropriate API/design.

**Question 11.** Why can legacy `File.lastModified()` be less clear than `Files.getLastModifiedTime()`?

**Answer:** `File.lastModified()` returns long milliseconds and 0 can indicate inability to obtain info; NIO.2 uses `FileTime` and richer checked `IOException`s.

**Question 12.** To display the same instant to users in two different timezones, do you need to modify the file's timestamp?

**Answer:** No. Use the same `Instant` and format it with the respective `ZoneId`; the underlying timestamp does not change.

## Summary

- **Creation**, **last modified**, and **last access** are three distinct timestamp types that may be missing or not strictly exact depending on the filesystem.
- `BasicFileAttributes` reads the three timestamps as `FileTime`; `Files.getLastModifiedTime` is convenient when only mtime is needed.
- `FileTime` is an instant that can be converted to `Instant` for comparison/formatting; `toMillis()` does not retain sub-millisecond precision.
- `Files.setLastModifiedTime` and `BasicFileAttributeView.setTimes` allow **requesting** metadata updates within provider capabilities; they do not guarantee every timestamp can be set or stored verbatim.
- **Symlinks**, **timezones**, **resolution**, **copy/restore**, **access permissions**, and **concurrent operations** all affect how timestamps are read and interpreted.
- When business logic requires strong integrity, synchronization, or access history, do not treat filesystem timestamps as the sole source of truth.
