# Comparing File Contents with Files.mismatch in Java 17

**Topic:** Java 17 → File I/O and Character Encodings  
**Focus:** Using `Files.mismatch(Path, Path)` to determine whether two files have identical byte contents; understanding return values, differing byte positions, the case where one file is a prefix of the other, and distinguishing byte comparison from text comparison after decoding.

Java 17 includes the `Files.mismatch` method in the `java.nio.file` package. This method compares the contents of two files and returns the position of the first differing byte. If their contents are identical, it returns `-1L`. The API was added in Java 12, so it is a standard API fully available in Java 17.

Crucially, **`Files.mismatch` compares the raw bytes of files**—it does not decode characters, does not normalize line endings, and does not ignore whitespace. If two files contain the same text saved with different charsets or line endings, the method will still report a difference. When the goal is semantic text comparison, decode using an explicit charset and apply appropriate normalization rules before comparing.

## 1. What Does Files.mismatch Do?

Syntax:

~~~java
long position = Files.mismatch(Path path, Path path2);
~~~

The method takes two `Path` objects and finds the first position where the contents of the two files differ.

| Result | Meaning |
| --- | --- |
| `-1L` | Both files have identical byte contents; if they refer to the same file, the result is also `-1L`. |
| `0L` | The very first byte differs. |
| `n > 0` | The byte at offset `n` is the first mismatch; all preceding bytes are identical. |
| `sizeOfSmallerFile` | One file is a complete prefix of the other: every byte in the shorter file matches, while the other file has additional data. |

The position is **0-based** and measured in **bytes**, not characters, lines, or UTF-16 indices. The return type is `long` to support files larger than `int` limits.

Example:

~~~java
Path first = Path.of("first.bin");
Path second = Path.of("second.bin");

long mismatch = Files.mismatch(first, second);

if (mismatch == -1L) {
    System.out.println("Both files have identical byte contents.");
} else {
    System.out.println("First differing byte at offset " + mismatch);
}
~~~

The method throws `IOException` if an I/O error occurs, such as failing to open a file or an error while reading. Therefore, it is typically called in a method declaring `throws IOException` or inside proper exception handling.

## 2. Basic Example: Identical and Differing Files

Suppose we have two files:

**`first.txt`**

~~~text
Java 17
Files API
~~~

**`second.txt`**

~~~text
Java 17
Files API
~~~

Comparing them:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareFiles {
    public static void main(String[] args) throws IOException {
        Path first = Path.of("first.txt");
        Path second = Path.of("second.txt");

        long mismatch = Files.mismatch(first, second);

        if (mismatch == -1L) {
            System.out.println("Files are identical.");
        } else {
            System.out.println("First mismatch at byte " + mismatch);
        }
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 CompareFiles.java
java CompareFiles
~~~

If both files share the same bytes, the output is:

~~~text
Files are identical.
~~~

If you modify one character in `second.txt`, the result is the offset of the first differing byte. If a differing character is in UTF-8 and spans multiple bytes, the offset is still the index of the first differing byte, not the visible character index.

## 3. Mismatch Position Is a 0-Based Byte Offset

Example with two ASCII payloads:

~~~text
File A: c a t
Offset: 0 1 2

File B: c u t
Offset: 0 1 2
        | ^
        First differing byte at offset 1.
~~~

You can reproduce this case in Java:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path a = Files.createTempFile("compare-a-", ".txt");
Path b = Files.createTempFile("compare-b-", ".txt");

try {
    Files.writeString(a, "cat", StandardCharsets.UTF_8);
    Files.writeString(b, "cut", StandardCharsets.UTF_8);

    System.out.println(Files.mismatch(a, b)); // 1
} finally {
    Files.deleteIfExists(a);
    Files.deleteIfExists(b);
}
~~~

Because the characters in this example are ASCII, each UTF-8 character occupies one byte. The byte at offset 0 (`c`) matches; the bytes at offset 1 (`a` and `u`) differ.

**Do not interpret byte offsets as character counts.** For Vietnamese or other Unicode characters, a single UTF-8 code point can span multiple bytes; the mismatch offset may fall in the middle of a character's encoded byte sequence.

## 4. When One File Is a Prefix of the Other

Two files do not always have a differing byte at an index where both have data. One file ending earlier also counts as a mismatch.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path shortFile = Files.createTempFile("short-", ".txt");
Path longFile = Files.createTempFile("long-", ".txt");

try {
    Files.writeString(shortFile, "Java", StandardCharsets.UTF_8);
    Files.writeString(longFile, "Java 17", StandardCharsets.UTF_8);

    System.out.println(Files.mismatch(shortFile, longFile)); // 4
} finally {
    Files.deleteIfExists(shortFile);
    Files.deleteIfExists(longFile);
}
~~~

The byte content of `shortFile` is a prefix of `longFile`. The first four bytes match; at offset 4, the shorter file ends while the longer file continues with a space and more data. Thus, the result is the byte length of the shorter file: `4L`.

If both files are empty, the result is `-1L`. If one file is empty and the other has data, the result is `0L`.

| File A | File B | Result |
| --- | --- | ---: |
| empty bytes | empty bytes | `-1L` |
| `"A"` | `"A"` | `-1L` |
| `"A"` | `"AB"` | `1L` |
| `"AB"` | `"A"` | `1L` |
| `"cat"` | `"cut"` | `1L` |
| `"cat"` | `"dog"` | `0L` |

## 5. Files.mismatch Compares Bytes, Not Characters

Because this topic falls under **File I/O and Character Encodings**, distinguish clearly between:

- **Byte comparison:** verifying the exact sequence of bytes stored in two files.
- **Text comparison:** decoding bytes into characters with a charset, then comparing according to text rules defined by the application.

`Files.mismatch` performs the first task. It does not know whether a file was created with UTF-8, UTF-16, ISO-8859-1, or another charset.

### 5.1. Same Text, Different Charsets

The character `é` can be encoded into different byte sequences:

- UTF-8: two bytes `C3 A9`.
- ISO-8859-1: one byte `E9`.

Both files can decode to the same character `é` when each is read with its corresponding charset, yet `Files.mismatch` still detects differing bytes.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path utf8 = Files.createTempFile("utf8-", ".txt");
Path latin1 = Files.createTempFile("latin1-", ".txt");

try {
    Files.writeString(utf8, "café", StandardCharsets.UTF_8);
    Files.writeString(latin1, "café", StandardCharsets.ISO_8859_1);

    System.out.println(Files.mismatch(utf8, latin1) >= 0); // true

    String text1 = Files.readString(utf8, StandardCharsets.UTF_8);
    String text2 = Files.readString(latin1, StandardCharsets.ISO_8859_1);

    System.out.println(text1.equals(text2)); // true
} finally {
    Files.deleteIfExists(utf8);
    Files.deleteIfExists(latin1);
}
~~~

`Files.mismatch` reports that the two files differ at the byte level. After decoding each file with its proper charset, the two Java strings are equal. This is not a contradiction: the two comparisons answer different questions.

### 5.2. Same Visible Content, Different Line Endings

Two files can display the exact same two lines:

~~~text
File LF:
Line 1\n
Line 2\n

File CRLF:
Line 1\r\n
Line 2\r\n
~~~

At the byte level, an LF line ending is `0A`; CRLF is two bytes `0D 0A`. Consequently, `Files.mismatch` reports a mismatch at the very first byte of the differing line ending.

If the goal is exact file-content comparison, this result is correct. If the goal is text comparison where LF and CRLF are considered equivalent, normalize line endings after decoding.

### 5.3. BOM and Unicode Normalization

Two files can show identical visible text yet differ in bytes because:

- One file has a BOM (byte order mark) and the other does not.
- One file encodes characters in UTF-8 and the other uses UTF-16.
- A character is represented as a precomposed Unicode form versus a sequence with combining diacritics (*composed/decomposed*).
- Line endings or leading/trailing whitespace differ.

`Files.mismatch` does not automatically strip BOMs, normalize Unicode NFC/NFD forms, or trim whitespace. Any text-equivalence rules must be defined by the application.

## 6. Comparing Text After Decoding

If you need to determine whether two files contain the same text under a specific charset, read them as `String` using an explicit charset:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareTextFiles {
    public static void main(String[] args) throws IOException {
        Path first = Path.of("first.txt");
        Path second = Path.of("second.txt");

        String text1 = Files.readString(first, StandardCharsets.UTF_8);
        String text2 = Files.readString(second, StandardCharsets.UTF_8);

        System.out.println(text1.equals(text2));
    }
}
~~~

`Files.readString(path, charset)` decodes the content using the specified charset. If bytes are invalid for that charset, decoding may throw an error; do not use the machine's default charset to produce non-reproducible comparison results.

### 6.1. Ignoring Line-Ending Differences by Policy

If your application treats CRLF and LF as equivalent, normalize before comparing:

~~~java
static String normalizeLineEndings(String text) {
    return text.replace("\r\n", "\n")
               .replace('\r', '\n');
}
~~~

Usage:

~~~java
String text1 = Files.readString(first, StandardCharsets.UTF_8);
String text2 = Files.readString(second, StandardCharsets.UTF_8);

boolean sameText = normalizeLineEndings(text1)
    .equals(normalizeLineEndings(text2));
~~~

Only normalize line endings when the application contract permits it. If CRLF and LF carry distinct meaning (such as byte-exact test fixtures, digital signatures, or protocol formats), do not erase that difference.

### 6.2. Unicode Normalization When Canonical Equivalence Is Required

In Unicode, an accented character can be represented by multiple canonically equivalent code point sequences. When business logic should treat those canonical forms as equal, use `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

static String normalizeUnicode(String text) {
    return Normalizer.normalize(text, Normalizer.Form.NFC);
}
~~~

After decoding with the proper charset, you can normalize to NFC before comparing. Do not automatically apply Unicode normalization to all data types; the decision depends on your application's definition of equality.

## 7. Using Files.mismatch for Binary Files

For binary files such as images, archives, PDFs, or application-generated binary payloads, byte comparison is usually exactly what you want. Never decode such data into a `String`.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareBinaryFiles {
    static boolean sameContent(Path first, Path second)
            throws IOException {
        return Files.mismatch(first, second) == -1L;
    }

    public static void main(String[] args) throws IOException {
        Path original = Path.of("image-original.png");
        Path downloaded = Path.of("image-downloaded.png");

        if (sameContent(original, downloaded)) {
            System.out.println("Binary content matches.");
        } else {
            System.out.println("Binary content differs.");
        }
    }
}
~~~

An advantage of `Files.mismatch` is that the application does not have to read both entire files into two byte arrays just to compare them. The API can compare contents without loading everything into memory. Implementation details and performance depend on the filesystem/provider; do not assume a fixed speed across every environment.

## 8. Files.mismatch vs. Arrays.equals and Hashing

Another simple approach is reading the full contents:

~~~java
byte[] firstBytes = Files.readAllBytes(first);
byte[] secondBytes = Files.readAllBytes(second);

boolean same = java.util.Arrays.equals(firstBytes, secondBytes);
~~~

`Arrays.equals` compares every byte in both arrays accurately, but `readAllBytes` loads the entire contents of each file onto the heap. For large files, this can consume excessive memory or trigger `OutOfMemoryError`.

| Approach | Exact Byte Comparison? | Application Memory | Notes |
| --- | --- | --- | --- |
| `Files.mismatch(path1, path2)` | Yes | No need to hold both entire files in application byte arrays | Dedicated API for finding the mismatch offset. |
| `Files.readAllBytes` + `Arrays.equals` | Yes | Proportional to total data read | Useful for small files or when bytes are also needed afterward. |
| Comparing hashes/checksums | Cannot conclude absolute byte equality from hashes alone | Typically smaller than holding full content | Matching hashes provide strong practical evidence depending on the algorithm, though collisions remain theoretically possible. |

If the final goal is verifying that two files are byte-identical, `Files.mismatch` gives a direct answer with no hash-collision concern.

### 8.1. When Should You Use Checksums?

Checksums or cryptographic hashes are useful when you need to:

- Store a file fingerprint for later verification.
- Transmit a digest over the network instead of the entire file.
- Verify received data against a published digest.

However, two matching hashes are not an absolute mathematical proof that two files have identical bytes. When comparing two local paths directly, `Files.mismatch` is the straightforward choice. If you need origin authentication or tamper resistance against an adversary, use hashes/MACs/signatures under an appropriate security model; `Files.mismatch` only compares content and does not authenticate origin.

## 9. Handling I/O Errors

`Files.mismatch` declares `throws IOException`. Common errors include:

| Error | Scenario |
| --- | --- |
| `NoSuchFileException` | One of the paths does not exist. |
| `AccessDeniedException` | The process lacks permission to read a file. |
| `FileSystemException` | Specific error from the filesystem or provider. |
| `IOException` | Other read/open error. |
| `NullPointerException` | Either `Path` argument is null. |

Handling example:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareWithErrorHandling {
    public static void main(String[] args) {
        Path first = Path.of("first.dat");
        Path second = Path.of("second.dat");

        try {
            long mismatch = Files.mismatch(first, second);

            if (mismatch == -1L) {
                System.out.println("Identical");
            } else {
                System.out.println("Mismatch at byte " + mismatch);
            }
        } catch (IOException e) {
            System.err.println("Cannot compare files: " + e.getMessage());
        }
    }
}
~~~

In production applications, do not merely log a message and continue as though the files matched. Return an explicit status result or propagate the exception to the caller for business-level handling.

### 9.1. Paths and File Types

`Files.mismatch` accepts `Path`, so it works with the corresponding filesystem provider. In typical applications, pass paths to **regular files**. By API contract, behavior when one or both paths do not refer to regular files is implementation-specific; do not rely on specific results for directories, devices, or special filesystems.

Pre-checking can provide clearer error messages:

~~~java
if (!Files.isRegularFile(first) || !Files.isRegularFile(second)) {
    throw new IllegalArgumentException("Both paths must be regular files");
}
long mismatch = Files.mismatch(first, second);
~~~

`Files.isRegularFile` follows symbolic links by default. Pre-checking does not eliminate all race conditions: files may be modified or replaced after the check. In environments where multiple concurrent processes edit files, manage ownership, locking, or snapshotting at the application layer.

### 9.2. No Automatic Transactional Snapshot

`Files.mismatch` reads contents from both paths during execution. It does not guarantee an immutable transactional snapshot if another process modifies either file concurrently. If you need a stable, meaningful comparison result:

1. Ensure no writer modifies either file during comparison.
2. Compare copies/snapshots that have already been created and finalized.
3. Use file locking or versioning if multiple processes operate concurrently.

Do not treat `Files.mismatch` as a filesystem synchronization primitive.

## 10. Complete Example: Comparing Two Paths from the Command Line

Create the file **`FileMismatchCli.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileMismatchCli {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java FileMismatchCli <file1> <file2>");
            return;
        }

        Path first = Path.of(args[0]);
        Path second = Path.of(args[1]);

        long position = Files.mismatch(first, second);

        if (position == -1L) {
            System.out.println("IDENTICAL");
        } else {
            System.out.println("DIFFERENT");
            System.out.println("First mismatch byte offset: " + position);
        }
    }
}
~~~

Compile:

~~~shell
javac --release 17 FileMismatchCli.java
~~~

Run:

~~~shell
java FileMismatchCli first.bin second.bin
~~~

The program outputs one of two statuses suited for scripting:

- `IDENTICAL`: byte contents match.
- `DIFFERENT` and the offset: a byte differs or one file is a prefix of the other.

If a path does not exist or cannot be read, the program throws `IOException` and terminates with an error. In an end-user CLI, you can catch the exception to print a friendly message and exit with a non-zero status code.

## 11. Comparing Content Is Not Comparing Metadata

`Files.mismatch` focuses strictly on byte content. It does not compare:

- File names.
- File paths.
- Modification timestamps.
- Permissions or owners.
- Physical disk block allocation.
- Other filesystem attributes.

Two files with different names and metadata but identical bytes still return `-1L`. Conversely, two files with identical sizes and timestamps that differ by a single byte return the mismatch offset.

If you need to compare metadata, use dedicated APIs such as `Files.size`, `Files.getLastModifiedTime`, or `Files.readAttributes`; do not use `Files.mismatch` as a full filesystem state check.

## 12. Choosing Byte Comparison or Text Comparison?

| Goal | Suitable Approach |
| --- | --- |
| Verify two binary copies match byte-for-byte | `Files.mismatch(path1, path2) == -1L` |
| Verify a downloaded file matches the original | `Files.mismatch`, or verify a trusted digest per system requirements |
| Compare two UTF-8 files requiring exact byte equality | `Files.mismatch` |
| Compare text content after decoding UTF-8 | `Files.readString(path, UTF_8)` followed by `String.equals` |
| Treat CRLF and LF as equivalent | Decode and normalize line endings per agreed rules |
| Treat Unicode NFC/NFD forms as equivalent | Decode and normalize using `Normalizer` |
| Compare very large files semantically as text | Use `Reader`/`BufferedReader` or a streaming parser with an explicit charset |
| Compare names, permissions, and timestamps too | Read metadata separately; `Files.mismatch` does not check them |

Before writing code, answer: **Does "equal" mean byte-for-byte identical, or equal in content after decoding and normalization?** Picking the wrong comparison yields technically accurate results that violate business semantics.

## 13. Common Mistakes

| Mistake | Cause | How to Avoid |
| --- | --- | --- |
| Treating the return value as a character count | The API returns a byte offset. | Treat it as a byte position/offset, not a character index. |
| Comparing UTF-8 and UTF-16 files expecting `-1L` for the same text | Different encodings produce different bytes. | Decode each file with its proper charset when comparing text. |
| Assuming LF and CRLF are identical | Line-ending bytes differ. | Normalize line endings only when business rules allow it. |
| Thinking `-1L` means two paths have the same filename | It indicates identical byte contents (or the same file), not identical names. | Use `Files.isSameFile` when checking file identity. |
| Thinking equal file sizes mean equal content | A byte can differ even when sizes match. | Use `Files.mismatch` or an appropriate digest. |
| Reading large files via `readAllBytes` just to compare | Memory usage scales with file size. | Use `Files.mismatch` for byte comparisons. |
| Ignoring `IOException` and treating files as equal | Unreadable files do not imply matching content. | Represent errors separately from equal/different results. |
| Calling it on directories or special files | Behavior is not always specified like regular files. | Restrict to regular files or define custom handling. |
| Trusting results while another writer modifies a file | No transactional snapshot is taken. | Lock, snapshot, or ensure sources do not change during comparison. |

## 14. Frequently Asked Questions

**Which Java version introduced `Files.mismatch`?**  
The API was added in Java 12, so it is available in Java 17.

**Does `Files.mismatch` return `-1` or `-1L`?**  
The return type is `long`; the sentinel value is `-1L`. Comparing against `-1L` makes the type explicit.

**Is the mismatch offset 0-based or 1-based?**  
0-based. The first byte is at offset 0.

**What if one file is shorter and all of its bytes match the start of the other file?**  
The result is the byte size of the shorter file—that is, the offset where that file ends.

**Does `Files.mismatch` load entire files into RAM?**  
The application does not need to load both files into byte arrays. The API is designed to compare without retaining full contents in memory; exact implementation details depend on the provider.

**Why do two files showing identical text return a mismatch?**  
They may differ in charset, BOM, line endings, Unicode normalization, or whitespace. `Files.mismatch` performs an exact byte comparison.

**Does `Files.mismatch` compare names and modification times?**  
No. It compares file content only; metadata must be checked with other APIs.

**Should I use hashes instead of `Files.mismatch`?**  
Hashes are suited for storing or transmitting fingerprints. If you need to verify directly whether two available files have identical bytes, `Files.mismatch` answers directly without hash collision concerns.

## 15. Official References

- [Java SE 17 API — Files.mismatch(Path, Path)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path)): describes return values, byte offsets, same-file behavior, and I/O exceptions.
- [Java SE 17 API — Files.readString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readString(java.nio.file.Path,java.nio.charset.Charset)): reading and decoding text using a specified charset.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charsets such as UTF-8 and ISO-8859-1.
- [Java SE 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): normalizing Unicode strings using NFC, NFD, NFKC, or NFKD.
- [Java SE 17 API — Files.readAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readAttributes(java.nio.file.Path,java.lang.Class,java.nio.file.LinkOption...)): reading metadata when comparing attributes beyond content.

**Guiding rule:** Use `Files.mismatch` when you need to know whether two files are byte-for-byte identical and locate the first differing byte offset. When the task asks for "the same text," decode with an explicit charset and decide whether to normalize line endings, Unicode forms, or whitespace. Byte equality and text equality are two separate contracts.
