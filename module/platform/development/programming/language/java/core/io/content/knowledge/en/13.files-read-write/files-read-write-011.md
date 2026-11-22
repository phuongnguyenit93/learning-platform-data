# `Files.mismatch` and Comparing the Contents of Two Files in Java I/O

## 1. When Are Two Files Considered Identical?

When verifying backups, synchronizing data, detecting file modifications, or validating export results, the critical question is often: **do two files contain the exact same sequence of bytes in the exact same order?**

Two files can:

- Have **different names** yet identical bytes.
- Have the **same size** yet one or more differing bytes.
- Have different **modification times** while byte content is unchanged.
- Contain visually identical text yet differ in bytes due to charset, BOM, Unicode normalization form, or line-ending style.
- Contain the same logical value yet differ in binary representation, such as metadata embedded inside the file structure.

Since Java 12, `java.nio.file.Files` provides **`Files.mismatch(Path path, Path path2)`** to find the **position of the first differing byte** between two files. This is the right API when the goal is comparing byte content rather than names, sizes, or timestamps.

**Foundational mental model:** `Files.mismatch` checks *binary equality*; it does not check whether two files have "the same meaning" as text, JSON, images, or documents.

## 2. Method Signature and Return Value Semantics

Method in `java.nio.file.Files`:

```java
public static long mismatch(Path path, Path path2) throws IOException
```

Where:

- `path` and `path2` are the two `Path`s pointing to the files to compare.
- The **`long`** return value is the **0-based offset of the first differing byte**.
- Returns **`-1L`** when no differing byte is found and both files have the same length.
- If one file is an exact byte prefix of the other yet **shorter**, the result is the **byte size of the shorter file**, because at that offset one side has run out of bytes.
- File access/read errors can raise **`IOException`**; the method never returns a special numeric code to represent an I/O error.

Byte sequence examples:

```text
File A: 10 20 30 40
File B: 10 20 30 40     -> -1  (equal)
File C: 10 20 99 40     ->  2  (differs at third byte)
File D: 10 20           ->  2  (D ends before A)
File E: 99 20 30 40     ->  0  (differs at very first byte)
File F: [empty]         ->  0  (F is an empty prefix of A)
```

Offsets are **0-based**, not 1-based: the first byte is at offset `0`, the third byte is at offset `2`. A result of `0` **does not mean the two files are identical**; only `-1L` represents no mismatch.

Lookup table:

| Result | Interpretation |
| ---: | --- |
| `-1L` | Both files have the same length and the same byte at every position |
| `0L` | Differs at the first byte, or one file is empty while the other is not |
| `k >= 0` | First mismatching byte is at offset `k` |
| `IOException` thrown | Could not complete the comparison due to an I/O error |

The method does not modify file contents under normal usage contracts; its job is reading and comparing.

## 3. Complete Java 17+ Example: Comparing Equal, Differing, and Prefix Files

This example uses a temporary directory and known bytes so output is verifiable. Create **`FilesMismatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilesMismatchDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("files-mismatch-");
        Path base = folder.resolve("base.bin");
        Path same = folder.resolve("same.bin");
        Path different = folder.resolve("different.bin");
        Path shorter = folder.resolve("shorter.bin");
        Path first = folder.resolve("first.bin");
        Path empty = folder.resolve("empty.bin");

        try {
            Files.write(base, new byte[]{10, 20, 30, 40});
            Files.write(same, new byte[]{10, 20, 30, 40});
            Files.write(different, new byte[]{10, 20, 99, 40});
            Files.write(shorter, new byte[]{10, 20});
            Files.write(first, new byte[]{99, 20, 30, 40});
            Files.write(empty, new byte[0]);

            System.out.println("same=" + Files.mismatch(base, same));
            System.out.println("different="
                    + Files.mismatch(base, different));
            System.out.println("shorter="
                    + Files.mismatch(base, shorter));
            System.out.println("first=" + Files.mismatch(base, first));
            System.out.println("empty=" + Files.mismatch(base, empty));
            System.out.println("self=" + Files.mismatch(base, base));
        } finally {
            Files.deleteIfExists(base);
            Files.deleteIfExists(same);
            Files.deleteIfExists(different);
            Files.deleteIfExists(shorter);
            Files.deleteIfExists(first);
            Files.deleteIfExists(empty);
            Files.deleteIfExists(folder);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FilesMismatchDemo.java
java FilesMismatchDemo
```

Output when all temporary file operations succeed:

```text
same=-1
different=2
shorter=2
first=0
empty=0
self=-1
```

Explanation:

1. `same` and `base` have equal bytes despite being **two separate paths** and two separately created files.
2. `different` has the same size, but the byte at index `2` is `99` instead of `30`.
3. `shorter` matches the first two bytes and then ends, so the mismatch is at index `2`.
4. `first` differs immediately at index `0`.
5. `empty` has no bytes to match `base`, so index `0` is the first differing position.
6. Comparing a file with itself returns `-1`.

The program attempts to delete temporary files in `finally`; if the system disallows creating/reading/deleting files, operations may throw `IOException`. In production code, handle cleanup errors carefully so they do not mask primary errors, and never automatically delete user files.

## 4. Logical Algorithm: Comparing Bytes Until a Difference Is Found

You can visualize `Files.mismatch(a, b)` with the following algorithm:

```text
offset = 0
Loop:
    read next byte from A and B
    if both at EOF: return -1
    if only one side at EOF: return offset
    if the two bytes differ: return offset
    offset = offset + 1
```

This is a **semantic model**, not the official JDK implementation source code. Java may optimize reading, buffering, and comparison strategies, yet the API outcome must reflect the first mismatch position.

If two files differ at the very first byte, there is no need to inspect later bytes to determine the result. If two files are completely identical, the system must verify content across the entire compared range. Do not rely on fixed assumptions about how much RAM the API uses, what block size it reads, or how many syscalls it makes: those are implementation details.

Because the offset is `long`, the API can represent positions larger than `int` limits, making it suitable for very large files.

## 5. Comparing Content vs. `Files.size`, Name, and Modification Time

Different APIs answer **different questions**:

| API/property | What does it tell you? | Does it prove identical content? |
| --- | --- | --- |
| `Files.mismatch(a, b) == -1L` | Bytes in both files match at comparison time | **Yes**, assuming stable sources during the check |
| `Files.size(a) == Files.size(b)` | Both byte sizes are equal | **No** |
| `Files.getLastModifiedTime(path)` | Timestamp provided by the filesystem | **No** |
| `a.equals(b)` | Both `Path` objects are equal in representation per provider | **No** if they are two different paths; it does not compare bytes |
| `Files.isSameFile(a, b)` | Two paths resolve to the **same file entity** | Does not compare contents of two distinct files |
| Comparing filenames or extensions | Metadata or naming conventions | **No** |

Example:

```text
A.bin = 01 02 03 04   -> size = 4
B.bin = 01 02 99 04   -> size = 4

Files.size(A) == Files.size(B)       -> true
Files.mismatch(A, B)                 -> 2
```

**Simple optimization:** If you only need to know **whether they are equal**, you can check sizes first. If the two sizes differ, the two files are definitely not byte-identical, so you need not call `mismatch`. If sizes match, you still must compare content. However, if the goal is **finding the first mismatch offset**, never use size alone as the offset: two files can differ in size **and** differ in an earlier byte.

For example, A has bytes `01 02 03` and B has `01 99 03 04`. The mismatch is `1`, **not** `3` (the shorter file's size).

## 6. `mismatch` Counts Bytes, Not Characters, Lines, or Code Points

Java `String` and text-reading APIs operate on Unicode characters, whereas `Files.mismatch` compares **raw file bytes**. There is no `Charset` parameter and no implicit text normalization step.

In UTF-8, accented characters can take multiple bytes. For example:

```text
"café" encoded in UTF-8:
63 61 66 C3 A9
          ^^
index: 0  1  2  3  4

"cafe\u0301" encoded in UTF-8:
63 61 66 65 CC 81
          ^^
index: 0  1  2  3  4  5
```

Two strings can **look identical** because one uses the precomposed `é` character (`U+00E9`) while the other uses `e` plus a combining acute accent (`U+0065` and `U+0301`). Yet the first differing byte is at **offset 3**.

Similarly, two files that look like the same lines—where one uses `LF` (byte `0A`) and the other uses `CRLF` (bytes `0D 0A`)—will mismatch right at the first line break.

**Differences often missed when viewing in a text editor:** UTF-8 BOM at the start of a file, trailing spaces, tabs vs. spaces, Unicode NFC/NFD forms, line endings, charset, and whether the end of the file has a trailing newline.

If an application wants to ask "is the text identical after normalization?", that is a different **semantic text comparison** problem, not the job of `Files.mismatch`.

## 7. Runnable Example: Visually Similar Text with Different Bytes

Create **`TextBytesMismatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;

public class TextBytesMismatchDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("text-mismatch-");
        Path composed = dir.resolve("composed.txt");
        Path decomposed = dir.resolve("decomposed.txt");
        Path lf = dir.resolve("lf.txt");
        Path crlf = dir.resolve("crlf.txt");

        try {
            Files.writeString(composed, "caf\u00E9", StandardCharsets.UTF_8);
            Files.writeString(decomposed, "cafe\u0301",
                    StandardCharsets.UTF_8);
            Files.writeString(lf, "A\nB", StandardCharsets.UTF_8);
            Files.writeString(crlf, "A\r\nB", StandardCharsets.UTF_8);

            System.out.println("unicode-offset="
                    + Files.mismatch(composed, decomposed));
            System.out.println("newlines-offset="
                    + Files.mismatch(lf, crlf));

            String left = Normalizer.normalize(
                    Files.readString(composed, StandardCharsets.UTF_8),
                    Normalizer.Form.NFC);
            String right = Normalizer.normalize(
                    Files.readString(decomposed, StandardCharsets.UTF_8),
                    Normalizer.Form.NFC);
            System.out.println("normalized-text-equal="
                    + left.equals(right));
        } finally {
            Files.deleteIfExists(composed);
            Files.deleteIfExists(decomposed);
            Files.deleteIfExists(lf);
            Files.deleteIfExists(crlf);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run on Java 17:

```bash
javac -encoding UTF-8 TextBytesMismatchDemo.java
java TextBytesMismatchDemo
```

Output:

```text
unicode-offset=3
newlines-offset=1
normalized-text-equal=true
```

This is not a contradiction. `Files.mismatch` answers **"are the bytes identical?"**, whereas `Normalizer.Form.NFC` followed by `String.equals` answers **"do the normalized strings have the same UTF-16 code units?"**.

When comparing text, define the contract upfront: should case, whitespace, blank lines, line order, or other formatting details be ignored? Every difference you ignore changes the **definition of equality**. Never normalize arbitrarily if your goal is backup or exact file verification.

## 8. Writing a Utility Method Answering "Are Two Files Identical?"

If you only need a boolean and want errors thrown to the calling layer to handle, use:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileContentEquality {
    private FileContentEquality() {
    }

    public static boolean sameBytes(Path first, Path second)
            throws IOException {
        return Files.mismatch(first, second) == -1L;
    }
}
```

Create **`FileContentEquality.java`** and compile:

```bash
javac FileContentEquality.java
```

This is a utility class that **compiles cleanly but has no `main`**, so it is not run directly with `java FileContentEquality`. It is meant to be integrated into another program:

```java
if (FileContentEquality.sameBytes(source, copy)) {
    System.out.println("Nội dung byte giống nhau");
} else {
    System.out.println("Nội dung byte khác nhau");
}
```

This is an illustrative snippet: `source` and `copy` must be declared as `Path`; the calling method handles `IOException`.

**Do not catch `IOException` and unconditionally return `false`** if `false` means "checked and definitely different". There are at least three states to distinguish:

- Checked, bytes **match**.
- Checked, bytes **differ**.
- **Could not check** due to an I/O error.

You can use `boolean` + `throws IOException` as above, or a richer result type if the application needs to distinguish errors, check time, and mismatch offset.

## 9. Command-Line Tool Example Checking Two Files

File **`CompareFilesCli.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareFilesCli {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java CompareFilesCli <first> <second>");
            return;
        }

        Path first = Path.of(args[0]);
        Path second = Path.of(args[1]);

        try {
            long offset = Files.mismatch(first, second);

            if (offset == -1L) {
                System.out.println("Hai tệp giống hệt nhau theo byte.");
            } else {
                System.out.println("Byte khác đầu tiên tại offset " + offset);
                System.out.println("Kích thước A = " + Files.size(first));
                System.out.println("Kích thước B = " + Files.size(second));
            }
        } catch (IOException ex) {
            System.err.println("Không thể so sánh: " + ex.getMessage());
        }
    }
}
```

Compile and invoke with **two real paths**:

```bash
javac -encoding UTF-8 CompareFilesCli.java
java CompareFilesCli first.bin second.bin
```

There is no fixed output: the result depends on the two files passed and filesystem state. If a file does not exist or cannot be read, `Files.mismatch` can throw `IOException` (such as `NoSuchFileException`), and the program reports that comparison failed rather than claiming the two files differ.

For CLI tools used in automation, define distinct **exit codes** for equal, different, and error cases; the example above simply prints messages to illustrate the API without defining custom exit codes.

## 10. When to Choose `Files.mismatch`, `Arrays.equals`, String Comparison, or Hashing?

### Direct Byte-by-Byte Comparison of Two Files

`Files.mismatch(a, b)` is the clear choice when you want the first differing byte position. It does not require the application to manually load both files into two byte arrays.

### `Files.readAllBytes` + `Arrays.equals`

```java
boolean equal = Arrays.equals(
        Files.readAllBytes(first),
        Files.readAllBytes(second));
```

This is an **illustrative snippet** with `Path first` and `second` declared, requiring imports for `java.util.Arrays`, `java.nio.file.Files` and `IOException` handling. It is easy to read and useful for **small** files, yet allocates byte arrays holding the entire contents of both files in RAM; for large files this risks excessive memory consumption. `Arrays.equals` only returns equal/not-equal and **does not return the first mismatch offset**.

If both byte arrays are already in RAM from an earlier step, `Arrays.equals` can be more direct than writing temporary files just to call `mismatch`.

### `Files.readString` + `String.equals`

```java
boolean sameText = Files.readString(first, StandardCharsets.UTF_8)
        .equals(Files.readString(second, StandardCharsets.UTF_8));
```

This is an **illustrative snippet** requiring imports and `IOException` handling. This approach compares text after **UTF-8 decoding**, without normalizing Unicode, newlines, or whitespace. It also needs memory to hold both strings.

Because it decodes to characters, this differs from byte comparison: different byte sequences can yield the same text representation after certain processing steps. If a file contains bytes invalid for the charset, text reading may fail.

### Hash/Checksum

For verifying many files, distributed systems, or repeated checks on large data, hashes like **SHA-256** can produce content fingerprints. However:

- The same hash comes deterministically from identical bytes; differing hashes prove differing bytes.
- Matching hashes imply **extremely small collision probability** with strong algorithms, though not an absolute mathematical proof that all bytes match.
- Hashing does not directly report the **mismatch offset**.
- Pre-stored hashes are only trustworthy if the hash source and computation pipeline are trusted; proving origin or tamper resistance also requires digital signatures or appropriate message authentication codes.

When you simply need to compare **two local files on hand**, `Files.mismatch` usually avoids writing custom hashing loops or loading everything into RAM.

## 11. Performance: Early Difference vs. Identical Files

Finding a mismatch near the start of a file can finish much sooner than verifying gigabytes of identical content. Still, speed depends heavily on:

- File size and the position of the first differing byte.
- Storage type: SSD, HDD, network filesystem, cloud mount...
- OS/JVM buffers and whether data is already cached.
- File opening, permissions, and metadata operations.
- Concurrent changes to the files while reading.

**Do not guess** runtime from filename length or metadata size. If performance matters, benchmark with realistic sizes and environments.

One reasonable optimization when only asking for a boolean:

```java
static boolean equalWithSizeHint(Path a, Path b)
        throws IOException {
    if (Files.size(a) != Files.size(b)) {
        return false;
    }
    return Files.mismatch(a, b) == -1L;
}
```

This is an **illustrative method** requiring imports for `Path`, `Files`, and `IOException`, placed inside a class. Checking size is only an **early filter**, not a substitute for content checking when sizes match. If a file is modified concurrently between the two calls, `size` and `mismatch` can reflect two different points in time; thus this does not certify an immutable snapshot.

If you need to report the **first offset**, just call `Files.mismatch` and use its result directly instead of checking size first.

## 12. Exceptions and Resources: Distinguishing "Different" from "Unreadable"

`Files.mismatch` declares `throws IOException`; failures can occur because:

- A path does not exist or was renamed during the operation.
- Read permission is missing on one source.
- The storage device or network filesystem fails.
- Source data is altered during comparison, so the result no longer represents a consistent snapshot.
- A source does not behave like a regular file per provider rules.

**Never use `-1L` or `0L` as an "error" sentinel in a catch block.** Both values already carry valid success semantics in the comparison algorithm.

Handling pattern:

```java
try {
    long mismatch = Files.mismatch(left, right);
    if (mismatch == -1L) {
        // Success: identical bytes
    } else {
        // Success: differing byte at mismatch
    }
} catch (IOException ex) {
    // Could not complete comparison; preserve the error for handling
}
```

This is an **illustrative snippet**; `left`/`right` must be `Path`, requiring imports for `Files` and `IOException`.

`Files.mismatch` manages reading internally per API; you **do not need**—and **should not**—open an `InputStream` for each file just to pass into `mismatch`, because the method takes `Path`s. If you need to inspect bytes around the first differing offset, that is a separate task using `SeekableByteChannel` or `FileChannel`, remembering to close resources you open with `try-with-resources`.

## 13. Important Limitations of Comparison

### Concurrent Modifications and Consistency

Two files can be modified by other processes while `mismatch` is running. This method is **not a transaction** and does not guarantee both files are compared from immutable point-in-time snapshots.

If you need to verify reliable backups or artifacts:

1. Ensure each file has finished writing and its writer has been closed.
2. Use snapshots or locking/write-coordination mechanisms where supported and consistency is required.
3. Compare stable sources; if inputs are still being written, defer verification until after the commit point.
4. For data needing long-term verification, store checksums/hashes and metadata using an appropriate workflow.

### Symbolic Links and File Identity

`Path` represents a path; two paths can point to the very same file through hard links, symbolic links, or filesystem rules. To ask **"are these the exact same file entity?"**, check `Files.isSameFile`. To ask **"do the bytes match?"**, check `Files.mismatch`.

Do not confuse content equality with identity equality. Two copies in different folders can have completely identical bytes yet still be two independent files.

### Does Not Validate File Format Integrity

Two ZIP, PDF, JSON, or image files can have identical bytes while both are corrupted. `Files.mismatch` does not confirm a file can be opened by its corresponding application. Conversely, two visually identical images encoded differently will still be reported as byte-different.

**Byte comparison**, **structural comparison**, and **semantic comparison** are three distinct requirements; pick tools matching the level of guarantee you need.

## 14. Real-World Scenario: Verifying a Copy After Writing

Suppose an application just copied a file and wants to verify content at check time:

```java
Path source = Path.of("source.dat");
Path backup = Path.of("backup.dat");

Files.copy(source, backup,
        StandardCopyOption.REPLACE_EXISTING);

long mismatch = Files.mismatch(source, backup);
if (mismatch != -1L) {
    throw new IOException("Bản sao khác từ offset " + mismatch);
}
```

This is an **illustrative snippet** requiring imports for `Path`, `Files`, `StandardCopyOption`, and `IOException`, and should only run with user-approved paths/overwrites. `Files.copy` can replace the target file, and copying itself is not guaranteed to be atomic; if a mid-copy error happens, the target file may be incomplete. After copying succeeds, `mismatch` re-checks the bytes of both files.

**Important:** A `-1` result does not guarantee the backup has been **fsynced** to storage, will survive power loss, or cannot be altered right after the check. Data durability and tamper resistance require additional measures at the filesystem and operational levels.

For strict backup workflows, write to a temporary file, verify content, and then publish under the official backup name.

## 15. Common Mistakes

| Mistake | Why it is wrong | Correct practice |
| --- | --- | --- |
| Thinking `mismatch == 0` means equal | Offset 0 is the first differing byte | Only `mismatch == -1L` means equal |
| Treating the offset as a line or character index | API returns **byte** offset | Compute line/char only after proper decoding and mapping |
| Assuming two files of equal size are identical | Same size can still differ in bytes | Use `Files.mismatch` or compare contents |
| Using shorter size as mismatch whenever sizes differ | Two files can differ in a byte before the shorter file ends | Use the actual result from `mismatch` |
| Using `Path.equals` to verify a copy | Compares path representations, not bytes | Use `Files.mismatch` |
| Using `Files.isSameFile` instead of content comparison | Checks file identity | Compare bytes when proving identical content |
| Catching `IOException` and returning `false` | Unreadable files get reported as definitely different | Propagate errors or return an explicit error status |
| Reading huge files with `readAllBytes` | Wastes RAM unnecessarily | Use `Files.mismatch` when comparing file to file |
| Expecting `mismatch` to ignore BOM/newlines/whitespace | Performs no text normalization | Choose a dedicated text-comparison approach |
| Using a hash as a mismatch offset | A hash is only a content fingerprint | Use `Files.mismatch` to get the offset |
| Comparing a file still being written and treating result as permanent | Source changes during and after reading | Verify against snapshots or stable sources |
| Treating `mismatch == -1` as "permanently safely saved" | Byte equality does not equal durability | Manage flush, fsync/force, storage, and commits |

## 16. Checklist and Self-Practice Exercises

**Before comparing:**

- [ ] Decide clearly: do you need identical **bytes**, **normalized text**, **logical content**, or the **same file entity**?
- [ ] Verify both paths point to the intended targets and have read permissions.
- [ ] Ensure sources are completely written and stable if reliable conclusions are needed.
- [ ] If only a boolean is needed, remember the sole value representing equality is `-1L`.
- [ ] If you need the first differing position, use the returned `long` offset, starting from 0.
- [ ] Handle `IOException` separately; never turn errors into byte-mismatch results.
- [ ] For large files, avoid loading everything into RAM unnecessarily.
- [ ] For text, document charset and normalization rules if the problem is not pure byte comparison.

**Exercise 1 — offset:** File A contains `00 11 22 33 44`, file B contains `00 11 FF 33 44`. Predict the result of `Files.mismatch` and create both files with `Files.write` to verify. Answer: offset **`2`**.

**Exercise 2 — prefix:** File A contains `41 42` (two ASCII bytes "AB"), file B contains `41 42 43` ("ABC"). Why is the mismatch `2` instead of `-1`? Because at offset 2, file A has ended while B still has one more byte.

**Exercise 3 — equal length:** File A contains `01 02 03`, file B contains `01 FF 03`. Both are 3 bytes long; demonstrate that size alone is insufficient to establish content equality. `mismatch` must return **`1`**.

**Exercise 4 — Unicode:** Create two UTF-8 files containing what looks like "café" in NFC and NFD forms. Compare with `Files.mismatch`, then read with `Files.readString`, normalize with `Normalizer.Form.NFC`, and compare with `equals`. Explain why the two comparisons give different answers.

**Remember:** **`Files.mismatch(a, b)`** (Java 12+) returns **`-1L` when two files are byte-identical**, or the **0-based `long` offset** of the first differing byte; if one file is a prefix of the other, the offset is the shorter file's size. The method does not compare metadata or semantic content, does not guarantee snapshots/durability, and can throw `IOException`.