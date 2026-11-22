# Building a File Reading Workflow with Input Validation — Java Core Exception

## 1. Objectives and Practice Outcomes

This lesson builds a workflow to **accept a filename from the user, validate the input, read UTF-8 text content, and report meaningful errors** using Java 17+. The focus is on the boundary between **validation errors** and **actual I/O errors**, how to preserve the <code>cause</code>, and how to avoid using prechecks as a false guarantee that the read operation will succeed.

After completing this lesson, you will be able to:

- Diagram the flow from **raw input → validation → resource resolution → file open → read/decode → result or error**.
- Validate <code>null</code>, blank strings, disallowed characters, file extensions, and naming rules.
- Restrict relative filenames to an application-controlled root directory; understand path traversal, symbolic links, and TOCTOU issues.
- Distinguish between <code>IllegalArgumentException</code>, <code>InvalidPathException</code>, <code>NoSuchFileException</code>, <code>AccessDeniedException</code>, <code>CharacterCodingException</code>, <code>IOException</code>, and translated business/domain errors.
- Use <code>try-with-resources</code> to close streams even when reading or decoding fails.
- Enforce a byte-read limit instead of trusting a file-size precheck as sufficient.
- Report errors using stable codes/types, preserve the cause for diagnostics, and avoid sending raw technical messages to users.
- Run a standalone Java 17 example with automatically generated sample data, deterministic stdout, and no pre-prepared files required.
- Design tests for the success branch, invalid input, encoding errors, and simulated I/O errors.

**Security boundary:** the practice program uses a temporary directory created by the program itself and only accepts **a single filename**, with no subdirectories. It validates characters and avoids following symbolic links at the final file component on supported file systems. This is an example for learning exception mechanisms and input validation; **it is not a sandbox against all concurrent operations by an attacker who has permission to modify the root directory**. Cases involving replaced parent directories, mount points, special file providers, and file objects modified between steps require separate advanced security/synchronization design.

## 2. Workflow Requirements

Suppose an application allows the user to select the name of a note file, such as <code>notes.txt</code>, from a directory managed by the application.

Rules for this practice exercise:

1. The user enters only **a single filename**, not a full path, and cannot navigate into subdirectories.
2. Only read files with the exact extension <code>.txt</code>, case-sensitive according to the example contract.
3. The filename starts with an ASCII letter or digit; subsequent characters before the extension may only be letters, digits, dots, underscores, or hyphens.
4. The file must be a regular file, not a directory or a symbolic link at the target location.
5. Each file is read up to a maximum of **1,024 bytes** in the example to bound memory used for content.
6. The content must be **valid** UTF-8, without silently replacing invalid bytes with a replacement character.
7. When an error occurs, the caller receives an exception with a clear <code>code</code>; for errors from the file system or decoder, the <code>cause</code> is preserved.
8. The stream resource must be closed whether reading succeeds or fails.
9. The public presentation layer only uses error codes and safe messages, without exposing raw paths or technical exception messages.

The rules above are **contract decisions for this lesson**, not universal Java rules. Another application may allow multiple subdirectories, Unicode names, larger sizes, or different file formats, provided that corresponding validation and access policies are clearly designed.

## 3. Overall Processing Flow

~~~text
Input String fileName
        |
        v
Check null / blank / extension / allowed characters
        |
        +---- invalid -------------> ReadFailure(INVALID_NAME / UNSUPPORTED_TYPE)
        |
        v
Resolve target = trustedBaseDir.resolve(fileName)
        |
        v
Preliminary file type check, without following symlink on final entry
        |
        +---- directory/symlink ---> ReadFailure(NOT_REGULAR_FILE)
        |
        v
Open stream for reading, try-with-resources
        |
        +---- does not exist ------> ReadFailure(NOT_FOUND, cause)
        +---- permission denied ---> ReadFailure(ACCESS_DENIED, cause)
        +---- other I/O error -----> ReadFailure(READ_FAILED, cause)
        |
        v
Read up to MAX_BYTES + 1
        |
        +---- exceeds limit -------> ReadFailure(TOO_LARGE)
        |
        v
Decode UTF-8 in REPORT mode
        |
        +---- invalid bytes -------> ReadFailure(INVALID_UTF8, cause)
        |
        v
Return String on success
~~~

**Why separate the stages?** Filename input errors are situations that code can detect **before I/O**, whereas a missing file, denied access, or disappearance due to a race condition can only be reliably determined by the actual operation. Each error group requires a different reporting policy.

## 4. Classifying Errors Before Writing Code

| Example error code | Origin | Meaning |
| --- | --- | --- |
| <code>INVALID_NAME</code> | Validation | Filename string is empty or contains paths/characters outside the rules |
| <code>UNSUPPORTED_TYPE</code> | Validation | File extension is not <code>.txt</code> |
| <code>NOT_REGULAR_FILE</code> | Resource policy | Target is known to be a directory, symbolic link, or disallowed type |
| <code>NOT_FOUND</code> | File system | Cannot open file because the path does not exist |
| <code>ACCESS_DENIED</code> | File system | System denies access permission |
| <code>TOO_LARGE</code> | Input limit | Content exceeds the maximum number of bytes allowed to be read |
| <code>INVALID_UTF8</code> | Decoder | Bytes in the file do not form a valid UTF-8 sequence |
| <code>READ_FAILED</code> | File system/stream | Other I/O error not covered by the specific cases above |

**Do not infer:** a file that never existed and a file deleted right before opening can both produce <code>NoSuchFileException</code>. Conversely, an existence check before opening can return stale or inconclusive results. Code must rely on **the contract of the actual operation**.

If a product needs to know the exact state of a resource at a concurrent point in time, it may need a separate versioning/file-handle/transaction mechanism; classifying exceptions alone does not solve that problem.

## 5. Checking null, blank, and Filenames

### 5.1. Null Is Not the Same as an Empty String

~~~java
if (fileName == null || fileName.isBlank()) {
    throw new IllegalArgumentException("Tên file không được trống");
}
~~~

This is **illustrative code** inside a method that has a <code>fileName</code> variable of type <code>String</code>. The <code>||</code> operator uses short-circuit evaluation, so it does not call <code>isBlank()</code> when <code>fileName == null</code>.

Inputs to consider include:

- <code>null</code>.
- <code>""</code>, <code>"   "</code>, or strings containing only whitespace characters.
- <code>"notes.txt"</code> (valid).
- <code>"../secret.txt"</code> using a parent directory component.
- <code>"sub/notes.txt"</code> containing a multi-segment relative path.
- <code>"C:\\private\\notes.txt"</code> Windows-style path.
- <code>"notes.csv"</code> wrong file type according to the exercise policy.
- Very long strings, or strings containing control characters or characters invalid for the file system.

The example chooses a filename **allowlist** rather than trying to enumerate every dangerous character. This may exclude some filenames that are completely valid on the operating system; that is an intentional consequence of the practice rules.

### 5.2. Validation Does Not Turn an Arbitrary Path into a "Safe" One

A simple but dangerous idea:

~~~java
Path target = baseDir.resolve(userInput);
~~~

This is **illustrative code**, requiring <code>import java.nio.file.Path</code>. If <code>userInput</code> contains <code>..</code> or is an absolute path, the result may no longer reside inside the intended directory. Path normalization and boundary checks must be designed from the start.

For an exercise that only needs **a single filename**, allowing characters within a strict pattern is usually simpler than handling arbitrary path components:

~~~java
if (!fileName.matches("[A-Za-z0-9][A-Za-z0-9._-]*\\.txt")) {
    throw new IllegalArgumentException("Tên file không hợp lệ");
}
~~~

This is **illustrative code**. The rule above accepts <code>note_01.txt</code> and rejects forward slashes, backslashes, and cases with parent directory components. If Unicode filenames are needed, explicitly define the new character set and limits rather than simply removing all checks.

### 5.3. Check Order Affects the Error Code

If the name is <code>notes.csv</code>, the example wants to return <code>UNSUPPORTED_TYPE</code>. If the name is <code>../secret.txt</code>, the example wants to return <code>INVALID_NAME</code>. Therefore, the pipeline chooses:

1. Check null/blank.
2. If the name does not end with <code>.txt</code>, report unsupported type.
3. If the name has the <code>.txt</code> extension but fails the allowlist, report invalid name.

This documented classification makes tests deterministic; other applications may decide to report a generic <code>INVALID_NAME</code> for all invalid inputs to reduce policy leakage.

## 6. Handling Path and InvalidPathException

Java NIO provides <code>Path.of(...)</code> or <code>Paths.get(...)</code>. For strings containing characters that are invalid for the file system, creating a path can throw <code>InvalidPathException</code>, which is an unchecked exception.

~~~java
try {
    Path supplied = Path.of(rawInput);
} catch (InvalidPathException e) {
    throw new IllegalArgumentException("Đường dẫn không hợp lệ", e);
}
~~~

This is **illustrative code** with imports <code>java.nio.file.Path</code> and <code>java.nio.file.InvalidPathException</code>. Catching this type is not necessary in a demo with a very strict filename allowlist, but in an API that accepts free-form path strings, it should be classified as an input error per the contract rather than returning the raw internal message to the user.

### normalize and startsWith

For applications that allow multi-segment relative paths, for example:

~~~java
Path root = baseDir.toAbsolutePath().normalize();
Path supplied = Path.of(rawInput);

if (supplied.isAbsolute()) {
    throw new IllegalArgumentException("Chỉ cho phép đường dẫn tương đối");
}

Path target = root.resolve(supplied).normalize();

if (!target.startsWith(root)) {
    throw new IllegalArgumentException("Đường dẫn vượt thư mục gốc");
}
~~~

This is an **illustrative snippet**, assuming <code>baseDir</code> and <code>rawInput</code> are already provided. <code>Path.startsWith(Path)</code> checks by path components, not simple character string comparison.

**Important limitation:** checking the normalized path only addresses part of the *lexical traversal* risk. A symbolic link can point to a location outside even when the apparent path is inside root. Furthermore, a file or symlink can be replaced between the check time and the open time. A service receiving paths from untrusted sources must add symbolic link and race-condition handling appropriate to its environment, rather than claiming <code>normalize()</code> is a "sandbox".

In the demo below, the filename has only a single component, so it cannot contain slashes or standalone <code>..</code> segments. This is **reducing the risk surface through the input contract**, not proof against all file system attacks.

## 7. Why Not Just Use Files.exists Before Reading?

A snippet that looks safe:

~~~java
if (Files.exists(path)) {
    return Files.readString(path);
}
return "";
~~~

This is **illustrative code**, requiring <code>import java.nio.file.Files</code> and an appropriate <code>IOException</code> handler. It has several problems:

- The file can be deleted or renamed between <code>exists</code> and <code>readString</code>.
- Access permissions can change.
- <code>exists</code> returning false does not necessarily prove the file permanently does not exist: metadata queries can be inconclusive under certain conditions.
- <code>readString</code> can still fail due to encoding, memory, device, permissions, or other I/O errors even if the precheck just succeeded.
- Returning an empty string for "does not exist" conflates it with a file that actually exists and has empty content.

The proper approach is to treat **the read operation** as the source of truth for success/failure, catching the specific exceptions that the caller needs to distinguish. Prechecks like <code>Files.isRegularFile</code> can serve UX/policy purposes, but **do not replace** error handling on open.

~~~java
try {
    return Files.readString(path, StandardCharsets.UTF_8);
} catch (NoSuchFileException e) {
    throw new DocumentNotFoundException("Không tìm thấy tài liệu", e);
} catch (IOException e) {
    throw new DocumentReadException("Không thể đọc tài liệu", e);
}
~~~

This is **illustrative code**; the two custom exception types must be defined in the project. Using a constructor that accepts <code>Throwable cause</code> preserves the original error.

## 8. Checking File Type and Symbolic Links

Java NIO provides:

- <code>Files.isRegularFile(path)</code>: normally follows symbolic links.
- <code>Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)</code>: requests not following a symbolic link at the target when retrieving file type info.
- <code>Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)</code>: distinguishes directories in the corresponding way.
- <code>Files.isSymbolicLink(path)</code>: checks whether the entry is a symbolic link.
- <code>Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)</code>: on file system providers that support the option, avoids following a symbolic link at the file entry being opened.

Each metadata check above is **not a lock**. If another party has permission to modify the file system, the entry can change after the check. In environments exposed to race/symlink attacks, you must evaluate binding file-open APIs, OS permissions, root directory safety, and possibly use <code>SecureDirectoryStream</code> when the provider supports it.

In the practice program, the directory is a privately created temp directory with no other actors modifying it, so checking the file type before opening is mainly used to produce **clear error codes** such as <code>NOT_REGULAR_FILE</code>. The code must still catch <code>IOException</code> from the actual open.

### A Symlink Is Not a Regular File

A symbolic link can point to a real file outside root. You should not call the default <code>Files.readString</code> on a user-controlled name and assume that checking <code>target.startsWith(root)</code> guarantees the data stays under root.

In the example, with a single filename and no user-supplied parent, <code>NOFOLLOW_LINKS</code> is used when opening. In a service that allows subpaths and where parent directories could be replaced, **preventing follow only on the final entry is not enough**: parent path components must also be protected.

## 9. Reading UTF-8: Replace Invalid Bytes by Default or Report an Error?

A file with a <code>.txt</code> extension **does not guarantee** the content is valid UTF-8. If a system declares "all content must be valid UTF-8", encountering invalid bytes must become a data error, not silently converted into replacement characters and treated as success.

With the Java NIO Charset API:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String content = decoder.decode(ByteBuffer.wrap(bytes)).toString();
~~~

This is **illustrative code**; it requires imports from <code>java.nio</code> and <code>java.nio.charset</code>, and a <code>bytes</code> variable of type <code>byte[]</code> already allocated. <code>REPORT</code> mode causes malformed encoded data to throw <code>CharacterCodingException</code> (for example <code>MalformedInputException</code>) instead of silently substituting the U+FFFD character.

Some high-level text-reading APIs such as <code>Files.readString(path, StandardCharsets.UTF_8)</code> can also throw <code>IOException</code> on invalid UTF-8 data. The demo uses an explicit decoder to **make the contract clear** and combine it with the byte-read limit.

### Byte Limit Differs from Character Limit

UTF-8 uses from one to multiple bytes per Unicode code point. Therefore:

- A 1,024-byte file does not necessarily contain 1,024 Java characters.
- The number of Java characters (UTF-16 code units) is also not the number of code points.
- If limiting by **bytes** to protect reading/memory, check **bytes**, not only the length after decoding.
- If the product also needs a character limit, check it after defining the character/Unicode policy.

The demo sets <code>MAX_BYTES = 1024</code> and reads at most <code>MAX_BYTES + 1</code>. When 1,025 bytes are received, it concludes the limit was exceeded. It does not rely solely on <code>Files.size()</code>, which is only a metadata snapshot that can change.

## 10. Try-with-resources: Closing Streams on Every Path

Example:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    byte[] bytes = input.readNBytes(1025);
    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
~~~

This is **illustrative code** inside a method with appropriate variables and exception contracts. The <code>try-with-resources</code> syntax calls <code>close()</code> when exiting the block, including when:

- Reading finishes normally.
- <code>readNBytes</code> throws <code>IOException</code>.
- The decoder throws <code>CharacterCodingException</code>.
- The code itself throws an exception because the limit was exceeded.
- Internal processing returns early.

If both the primary operation and closing the stream fail, Java preserves the close error in the primary exception's <code>getSuppressed()</code> list per the try-with-resources contract. When translating to an application-layer exception, preserve the cause so this information is not accidentally lost.

**Do not use a <code>finally</code> block that can throw a new unchecked/unmanaged exception** and mask the original error. Try-with-resources manages the relationship between primary and close errors more reliably when the resource is <code>AutoCloseable</code>.

## 11. Complete Java 17+ Program: ValidatedFileReadDemo

This program:

1. Creates a dedicated temporary directory.
2. Creates a valid UTF-8 file, an empty file, a file containing invalid UTF-8 bytes, an oversized file, and a directory named with a <code>.txt</code> extension.
3. Attempts to read valid/invalid inputs and prints clear error codes.
4. Preserves the cause when errors come from the file system or decoder.
5. Deletes test data after running.

Save **all** of the following to <code>ValidatedFileReadDemo.java</code>:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class ValidatedFileReadDemo {
    private static final int MAX_BYTES = 1024;

    enum Code {
        INVALID_NAME,
        UNSUPPORTED_TYPE,
        NOT_REGULAR_FILE,
        NOT_FOUND,
        ACCESS_DENIED,
        TOO_LARGE,
        INVALID_UTF8,
        READ_FAILED
    }

    static final class ReadFailure extends Exception {
        private final Code code;

        ReadFailure(Code code, String message) {
            super(message);
            this.code = code;
        }

        ReadFailure(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        Code code() {
            return code;
        }
    }

    static String readText(Path trustedRoot, String name)
            throws ReadFailure {
        if (name == null || name.isBlank()) {
            throw new ReadFailure(
                    Code.INVALID_NAME, "Tên file không được trống");
        }
        if (!name.endsWith(".txt")) {
            throw new ReadFailure(
                    Code.UNSUPPORTED_TYPE, "Chỉ hỗ trợ .txt");
        }
        if (!name.matches("[A-Za-z0-9][A-Za-z0-9._-]*\\.txt")) {
            throw new ReadFailure(
                    Code.INVALID_NAME, "Tên file có ký tự không hợp lệ");
        }

        Path target = trustedRoot.resolve(name);

        // Convenience classification check only; does not replace open().
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)
                && !Files.isRegularFile(
                        target, LinkOption.NOFOLLOW_LINKS)) {
            throw new ReadFailure(
                    Code.NOT_REGULAR_FILE, "Đích không phải file thường");
        }

        try (InputStream input =
                Files.newInputStream(target, LinkOption.NOFOLLOW_LINKS)) {
            byte[] bytes = input.readNBytes(MAX_BYTES + 1);
            if (bytes.length > MAX_BYTES) {
                throw new ReadFailure(
                        Code.TOO_LARGE, "File vượt giới hạn byte");
            }

            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new ReadFailure(
                    Code.INVALID_UTF8, "File không phải UTF-8 hợp lệ", e);
        } catch (NoSuchFileException e) {
            throw new ReadFailure(
                    Code.NOT_FOUND, "Không tìm thấy file", e);
        } catch (AccessDeniedException e) {
            throw new ReadFailure(
                    Code.ACCESS_DENIED, "Không có quyền đọc file", e);
        } catch (IOException e) {
            throw new ReadFailure(
                    Code.READ_FAILED, "Không thể đọc file", e);
        }
    }

    static void show(Path root, String name) {
        String label = name == null ? "<null>" : "\"" + name + "\"";

        try {
            String content = readText(root, name);
            System.out.println(label + " -> OK ["
                    + content.strip() + "]");
        } catch (ReadFailure error) {
            System.out.println(label + " -> " + error.code());
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("file-read-practice-");

        try {
            Files.writeString(
                    root.resolve("ok.txt"),
                    "Xin chào\n",
                    StandardCharsets.UTF_8);
            Files.writeString(
                    root.resolve("empty.txt"),
                    "",
                    StandardCharsets.UTF_8);
            Files.write(
                    root.resolve("invalid.txt"),
                    new byte[] {(byte) 0xC3, (byte) 0x28});
            Files.write(
                    root.resolve("big.txt"),
                    new byte[MAX_BYTES + 1]);
            Files.createDirectory(root.resolve("folder.txt"));

            show(root, "ok.txt");
            show(root, "empty.txt");
            show(root, "missing.txt");
            show(root, "folder.txt");
            show(root, "invalid.txt");
            show(root, "big.txt");
            show(root, "note.csv");
            show(root, "../secret.txt");
            show(root, null);
        } finally {
            Files.deleteIfExists(root.resolve("ok.txt"));
            Files.deleteIfExists(root.resolve("empty.txt"));
            Files.deleteIfExists(root.resolve("invalid.txt"));
            Files.deleteIfExists(root.resolve("big.txt"));
            Files.deleteIfExists(root.resolve("folder.txt"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac -encoding UTF-8 ValidatedFileReadDemo.java
java ValidatedFileReadDemo
~~~

**Expected stdout on a standard file system supporting the test operations:**

~~~text
"ok.txt" -> OK [Xin chào]
"empty.txt" -> OK []
"missing.txt" -> NOT_FOUND
"folder.txt" -> NOT_REGULAR_FILE
"invalid.txt" -> INVALID_UTF8
"big.txt" -> TOO_LARGE
"note.csv" -> UNSUPPORTED_TYPE
"../secret.txt" -> INVALID_NAME
<null> -> INVALID_NAME
~~~

### 11.1. Why Is the Output Order Deterministic?

Every call to <code>show(...)</code> executes sequentially from <code>main</code>, without using a thread pool or asynchronous execution. No input file depends on the runner's working directory, because all test data is created inside the temp directory before testing.

On a standard file system that can create/delete files, allows opening temp files, and supports <code>NOFOLLOW_LINKS</code>, the results above are predictable. **Do not claim** this is the output when the OS denies creating a temp directory, the disk is full, the provider does not support the option, or another process intentionally modifies the directory while the program is running. Those situations are infrastructure failures outside normal test scenarios.

### 11.2. What Does Each Line Show?

- <code>"ok.txt"</code>: valid name, openable file, small size, valid UTF-8. <code>strip()</code> in <code>show</code> only strips leading/trailing whitespace **for demo display**; <code>readText</code> still returns the original content including the newline character.
- <code>"empty.txt"</code>: an existing empty file is still a **successful read**, not confused with <code>NOT_FOUND</code>.
- <code>"missing.txt"</code>: allowed name, but the file is absent; opening the stream throws <code>NoSuchFileException</code>, which is translated to <code>NOT_FOUND</code>.
- <code>"folder.txt"</code>: entry exists, but is a directory; checking <code>isRegularFile(..., NOFOLLOW_LINKS)</code> leads to <code>NOT_REGULAR_FILE</code>.
- <code>"invalid.txt"</code>: byte sequence <code>C3 28</code> is invalid UTF-8; the decoder in REPORT mode produces <code>CharacterCodingException</code>, translated to <code>INVALID_UTF8</code>.
- <code>"big.txt"</code>: has 1,025 bytes while the allowed limit is 1,024, so it returns <code>TOO_LARGE</code> before decoding.
- <code>"note.csv"</code>: fails at file-type validation without attempting to read.
- <code>"../secret.txt"</code>: has the .txt extension but does not match the allowlist, so it fails before constructing target.
- <code>null</code>: fails at null validation without accessing the file system.

### 11.3. The Byte Limit Is Checked After Opening

The method uses:

~~~java
byte[] bytes = input.readNBytes(MAX_BYTES + 1);
if (bytes.length > MAX_BYTES) {
    throw new ReadFailure(Code.TOO_LARGE, "File vượt giới hạn byte");
}
~~~

This is an **illustrative snippet extracted from the program**. It does not merely read <code>Files.size()</code> metadata and assume the size will not change. With the goal of bounding the amount of data **accumulated into the array**, reading up to one extra byte allows detecting the limit-exceeded case.

This limit is not a quota for all system resources: opening files, other allocations, internal buffers, and concurrent load still consume resources. When handling large files, streaming, timeouts, cancellation, per-request quotas, and concurrent request management must be additionally designed.

### 11.4. Symbolic Link Rejection in the Example Has Limits

- The allowlist prevents the user from entering subdirectories or path traversal using slashes.
- Checking <code>isRegularFile(..., NOFOLLOW_LINKS)</code> can reject a symbolic link at the target when the check observes it.
- <code>newInputStream(target, NOFOLLOW_LINKS)</code> is used to request not following a symlink at the target on open, depending on provider support.
- However, <code>trustedRoot</code> must genuinely be a directory controlled by the application. If another party can replace the root or file system namespace, the anti-race/symlink policy must be stricter.

**Do not use the demo code as a complete security sandbox** for a service where untrusted users are allowed to create/modify symlinks within the directory structure.

## 12. Preserving the Cause and Not Exposing Raw Technical Errors to Clients

In the program, when opening fails because the file is missing:

~~~java
} catch (NoSuchFileException e) {
    throw new ReadFailure(
            Code.NOT_FOUND, "Không tìm thấy file", e);
}
~~~

This is an **illustrative snippet within the catch chain**. Because the <code>ReadFailure(..., Throwable cause)</code> constructor calls <code>super(message, cause)</code>, upper layers can use:

~~~java
ReadFailure error = ...;
Throwable cause = error.getCause();
~~~

This is **illustrative code**; the <code>error</code> variable must be obtained from a catch block or an appropriate test result. <code>getCause()</code> may be null for validation errors, and non-null for read errors translated from Java NIO exceptions.

### Three Groups of Data to Distinguish

| Component | Purpose | Can it be sent directly to the user? |
| --- | --- | --- |
| <code>ReadFailure.code()</code> | Stable classification for callers | Yes, if part of the public contract |
| <code>ReadFailure.getMessage()</code> | Application-layer error phrasing | Only when the content has been approved as safe |
| <code>ReadFailure.getCause()</code> | Technical error diagnostics, stack trace | Usually no; must follow access/logging policy |
| <code>target Path</code> | Actual file on the system | Not automatically; can leak directory structure |
| <code>requestId</code> | Incident lookup for support | Yes, if the format contains no secrets/PII |

A real-world API might map to:

~~~json
{
  "code": "FILE_UNAVAILABLE",
  "message": "Không thể đọc tệp lúc này. Vui lòng thử lại sau.",
  "requestId": "RQ-1234"
}
~~~

This is **illustrative JSON**, not an HTTP server runnable from the example. Public messages do not include OS paths, hostnames, stack traces, or tokens extracted from original exception messages.

### Do Not Collapse All Errors into "Not Found"

If reading a file fails due to denied permissions or invalid encoding, returning <code>NOT_FOUND</code> can cause users/applications to make wrong decisions. Detailed internal classification does not require exposing all technical details publicly, but it helps logging and proper program handling.

Some systems intentionally do not distinguish <code>NOT_FOUND</code> and <code>ACCESS_DENIED</code> in **public responses** to avoid leaking resource existence information. That is a security boundary decision; internally, causes still need to be distinguished where appropriate.

## 13. Testing Without Relying on the Real File System to Simulate IOException

The example in section 11 is suitable for an **integration smoke test** with the file system. However, when you need to accurately test exception-translation logic, trying to change permissions on a real file on a CI runner can be unstable:

- Windows, Linux, and different file systems handle permissions differently.
- The test process might run with administrator privileges and not be blocked as expected.
- Antivirus, backup agents, race conditions, or unusual mounts can affect the result.
- You should not manipulate real user files just to run tests.

Instead, abstract the I/O operation behind a mockable/fakeable interface to test cause preservation and error classification.

### Standalone Java 17 Example: Fake Reader Throwing a Deterministic IOException

Save the file **ReadFailureCauseDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.NoSuchFileException;

public class ReadFailureCauseDemo {
    interface Reader {
        String read(String name) throws IOException;
    }

    enum Code {
        NOT_FOUND,
        READ_FAILED
    }

    static final class LoadFailure extends Exception {
        private final Code code;

        LoadFailure(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        Code code() {
            return code;
        }
    }

    static String load(Reader reader, String name) throws LoadFailure {
        try {
            return reader.read(name);
        } catch (NoSuchFileException e) {
            throw new LoadFailure(
                    Code.NOT_FOUND, "Không tìm thấy tài liệu", e);
        } catch (IOException e) {
            throw new LoadFailure(
                    Code.READ_FAILED, "Không thể đọc tài liệu", e);
        }
    }

    static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Exception contract failed");
        }
    }

    public static void main(String[] args) {
        NoSuchFileException original =
                new NoSuchFileException("missing.txt");
        Reader missing = name -> {
            throw original;
        };
        Reader working = name -> "CONTENT";

        try {
            load(missing, "missing.txt");
            throw new AssertionError("Expected LoadFailure");
        } catch (LoadFailure e) {
            require(e.code() == Code.NOT_FOUND);
            require(e.getCause() == original);
            System.out.println("Missing code: " + e.code());
            System.out.println("Same original cause: "
                    + (e.getCause() == original));
        }

        try {
            System.out.println("Working result: "
                    + load(working, "ok.txt"));
        } catch (LoadFailure e) {
            throw new AssertionError("Unexpected failure", e);
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ReadFailureCauseDemo.java
java ReadFailureCauseDemo
~~~

**Exact stdout:**

~~~text
Missing code: NOT_FOUND
Same original cause: true
Working result: CONTENT
~~~

Explanation:

- <code>Reader</code> describes a read operation that can throw <code>IOException</code>.
- Fake <code>missing</code> throws **the exact pre-created** <code>NoSuchFileException</code> instance.
- <code>load</code> translates it to <code>LoadFailure</code> while preserving the original cause.
- The test uses <code>==</code> to verify identity; in JUnit 5, the corresponding assertion is <code>assertSame(original, e.getCause())</code>.
- Fake <code>working</code> illustrates the success branch without creating a real file.
- This is an example for learning **exception translation**, not a replacement for the filename and byte/encoding validation of the main demo.

## 14. Required Test Cases

| Input/scenario | Expected | Test objective |
| --- | --- | --- |
| <code>null</code> | <code>INVALID_NAME</code> | Null guard runs before other operations |
| Empty or blank string | <code>INVALID_NAME</code> | Do not open I/O for meaningless names |
| Name with <code>../</code> | <code>INVALID_NAME</code> | Reject traversal via filename |
| Name with slash/backslash | <code>INVALID_NAME</code> if ending in .txt | Reject subdirectories per policy |
| <code>note.csv</code> | <code>UNSUPPORTED_TYPE</code> | Distinguish wrong file extension |
| Non-existent <code>.txt</code> file | <code>NOT_FOUND</code> | Classify NoSuchFileException |
| Empty file | Empty string <code>""</code> success | Do not equate empty with not found |
| Valid UTF-8 file | Exact string, preserving newlines | Read and decode properly |
| File with invalid UTF-8 bytes | <code>INVALID_UTF8</code> | Decoder uses REPORT mode |
| File exceeding 1,024 bytes | <code>TOO_LARGE</code> | Do not accumulate unboundedly |
| A directory ending in .txt | <code>NOT_REGULAR_FILE</code> in demo environment | Do not treat a directory as a text file |
| Symlink at target file | Rejected per policy and provider | Do not accidentally follow symlinks |
| Permission denied | <code>ACCESS_DENIED</code> when API throws AccessDeniedException | Do not misreport as NOT_FOUND |
| Other I/O error | <code>READ_FAILED</code> | Have a fallback branch preserving cause |
| Layer translation error | Cause identity preserved | Do not just copy the message |
| Stream close error | Close error is not silently lost | Effect of try-with-resources |

### Illustrative JUnit 5

Inside a JUnit 5 test class with appropriate imports and test fixture data:

~~~java
ReadFailureCauseDemo.Reader failing = name -> {
    throw original;
};

ReadFailureCauseDemo.LoadFailure error =
        assertThrows(ReadFailureCauseDemo.LoadFailure.class,
                () -> ReadFailureCauseDemo.load(failing, "missing.txt"));

assertEquals(ReadFailureCauseDemo.Code.NOT_FOUND, error.code());
assertSame(original, error.getCause());
~~~

This is **non-standalone illustrative code**, requiring an <code>original</code> variable that is a <code>NoSuchFileException</code> created in the test. Use the corresponding JUnit Jupiter assertions. Do not rely on OS messages or stack trace line numbers when you only need to check the code and cause.

A validation test can use a fake that records the read count to assert that invalid input **triggers no I/O**. However, write assertions against the validation layer's contract rather than depending on implementation details that callers do not need.

## 15. Separating Validation Logic from Read Logic for Extensibility

As the code grows, it can be organized as:

~~~text
FileNameValidator
    -> ValidatedName
    -> FileRepository (reads content)
    -> FileReadService (translates errors / enforces contract)
    -> API or CLI response mapper
~~~

This is a **suggested component diagram**; creating these exact classes is not mandatory for a small exercise.

A structure with clear responsibilities:

1. **Validation:** knows only naming/file-type rules, not disk errors.
2. **Repository:** receives a valid name / internal Path and performs open/read/close, reporting technical exceptions.
3. **Service:** enforces size/encoding policies and translates exceptions according to the feature's contract.
4. **Adapter/API:** turns error codes into safe responses, logs correlation IDs or controlled logs.

Four classes are not always necessary: they can be combined in a small program while keeping **conceptual responsibility boundaries**.

### Distinguishing Pre-I/O Validation Errors from Errors Detected During Reading

For example, "empty filename" can be determined solely from the input string. However, "file exists and is readable" requires operating on the file system. An API that wants to report a specific state when a file is concurrently modified must handle that as a real runtime condition rather than relying on earlier checks.

## 16. Charset and Content Decisions

UTF-8 is a common choice, but it must be **explicitly documented**. If the actual content is written by another system using a different charset, reading as UTF-8 can fail or produce corrupted text.

Scenarios to consider:

- Files with or without a BOM.
- Line endings like <code>\n</code>, <code>\r\n</code>, or <code>\r</code>.
- Strings with Vietnamese diacritics and non-ASCII Unicode characters.
- Invalid UTF-8 bytes.
- Byte limits versus character limits.
- Very large files that must be read via streaming instead of a single array.
- Binary data disguised with a <code>.txt</code> extension.
- Strings containing control characters that the domain rejects even if UTF-8 is valid.

**The main example only checks for well-formed UTF-8**, without enforcing a specific content grammar. A valid UTF-8 string can still be business-invalid, such as a configuration file missing a required field. If you need to parse CSV/JSON or line formats, add a **post-decode content validation** step with its own exceptions/error codes.

### Do Not Automatically Trim Original Content

In the demo, <code>show</code> calls <code>strip()</code> for compact printing, while <code>readText</code> returns the original decoded string. If a service arbitrarily trims, it can lose meaningful whitespace or newlines. Only normalize line endings, spaces, or BOM if required by the data contract.

## 17. When to Use Files.readString vs. Streaming?

### Small, Trusted Data Without Strict Byte Quotas

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is **illustrative code**, which can be simple and readable if size is controlled at the architecture/trusted-source level. However, it may need to allocate memory proportional to file size, making it unsuitable if users can pass an extremely large file into the read path.

### Data with Clear Resource Limits

In the demo, <code>InputStream.readNBytes(MAX_BYTES+1)</code> guarantees that content exceeding the threshold is not accumulated by this read operation. It fits small files that need to be loaded completely into memory.

### Large Files or Line-by-Line Processing

You can use <code>BufferedReader</code> or streaming:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

This is **illustrative code**, requiring imports for <code>java.io.BufferedReader</code>, <code>Files</code>, <code>StandardCharsets</code>, and a definition of <code>process</code>. If there are limits on total bytes, line count, or single-line length, you must still **actively enforce those quotas**; merely using <code>BufferedReader</code> does not automatically enforce all quotas.

If you need to block symlinks, choose an open API that supports that policy or manage file descriptors/paths with an appropriate mechanism. Do not simply switch from <code>newInputStream</code> to <code>newBufferedReader</code> and assume all permissions/symlink options remain identical.

## 18. Safe Logging and Error Messages

A file-reading workflow should not use:

~~~java
catch (IOException e) {
    System.out.println("Lỗi: " + e);
    return "";
}
~~~

This is **intentionally non-recommended illustrative code**:

- Returning <code>""</code> causes confusion with an actually empty file.
- Printing technical exceptions directly can leak internal paths if stdout is exposed to users.
- The caller no longer knows that the operation failed.
- File system messages may be unstable across OS/JDK versions and may contain sensitive information.

It is better to preserve <code>ReadFailure</code> with a stable code and cause, and let a presentation layer decide:

~~~java
String publicMessage(Code code) {
    return switch (code) {
        case INVALID_NAME -> "Tên tệp không hợp lệ.";
        case UNSUPPORTED_TYPE -> "Chỉ hỗ trợ tệp .txt.";
        case TOO_LARGE -> "Tệp vượt dung lượng được phép.";
        case INVALID_UTF8 -> "Tệp không đúng định dạng UTF-8.";
        case NOT_FOUND -> "Không tìm thấy tệp.";
        case NOT_REGULAR_FILE -> "Tài nguyên không phải tệp hợp lệ.";
        case ACCESS_DENIED, READ_FAILED ->
                "Không thể đọc tệp lúc này.";
    };
}
~~~

This is **illustrative code** using the <code>Code</code> enum from the main example. Real systems may intentionally group certain error types into a generic message to protect resource information. If the user can correct the input, a helpful message is better than returning a technical stack trace.

### Which Fields Should Go into Logs?

- Stable error code and operation name.
- Safe request ID / correlation ID.
- Timestamp, component, duration.
- Throwable/cause type for authorized engineers.
- Resource name if permitted to be logged under data policy.

Do not log tokens, passwords, private data, or raw file content just because an exception occurred. Do not repeat the same stack trace at every layer if it adds no new information.

## 19. Input Handling and Practical Security Boundaries

Components commonly needing review when building a production service:

**Path restriction.** Ideally, the user supplies a **file ID** or an allowlisted name; the server maps the ID to a location it manages. Do not allow clients to pass arbitrary absolute paths to sensitive system areas.

**Access permissions.** A valid filename can still point to a resource the user is not authorized to read. Syntax validation does not replace authorization.

**Symlinks.** Lexical normalize/startsWith does not prevent symlink escapes. <code>NOFOLLOW_LINKS</code> on the final entry does not protect parent directories if users are allowed to manipulate parents. Environments exposed to attacks must open files using stricter mechanisms, such as descriptor/directory control and <code>SecureDirectoryStream</code> where available.

**TOCTOU.** Metadata checks and open are separate operations; an attacker can swap the entry between the two points in time. Depending on requirements, use post-open checks or OS/API mechanisms that support corresponding atomicity.

**Resources.** Limit bytes, concurrent requests, read rate, timeouts, memory, and do not log unbounded files. A small file size does not guarantee the content is safe to parse, render, or execute.

**Format.** The <code>.txt</code> extension is only a filename policy. If the application requires specific content, validate the content itself; do not treat the file extension as absolute proof.

**File system errors.** Specific error codes depend on the OS/provider; the same business cause may be represented differently by different providers. A general <code>READ_FAILED</code> handling path is still necessary, rather than catching only one subtype.

**User-facing messages.** Do not expose absolute paths, exception classes, stack traces, or file bytes without authorization. For debugging, use a safe reference code to correlate with logs.

## 20. Common Mistakes

1. **Checking only <code>fileName != null</code>:** blank strings and path traversal still slip through.
2. **Concatenating path strings directly:** easy to get separators wrong and accidentally allow access outside root.
3. **Believing <code>normalize()</code> blocks all symlinks:** it only processes lexical path form, not actual file targets.
4. **Using <code>Files.exists</code> as a guarantee that open will succeed:** susceptible to races, permission changes, and other I/O errors.
5. **Returning an empty string for all errors:** fails to distinguish empty files, missing files, invalid UTF-8, or access denied.
6. **Catching <code>Exception</code> and returning a default:** swallows bugs and can mask errors that should not be treated as validation failures.
7. **Catching <code>IOException</code> before specific subtypes:** in Java, catching a subtype after its superclass is invalid/unreachable.
8. **Dropping the cause when translating errors:** makes it impossible to inspect the original exception or diagnose the root cause.
9. **Forgetting to close the stream if the decoder throws:** use try-with-resources.
10. **Relying only on <code>Files.size()</code>:** metadata can change and does not itself bound the number of bytes read.
11. **Assuming UTF-8 is always valid because of the .txt extension:** must decode using the declared charset.
12. **Silently replacing invalid bytes with replacement characters:** can hide corrupted data when strict UTF-8 is required.
13. **Using <code>String.length()</code> as a byte limit:** UTF-8 and UTF-16 count units differently.
14. **Reading entire files into memory without limits:** risks exhausting resources.
15. **Trimming content outside the contract:** can strip important whitespace or newlines.
16. **Failing to distinguish input errors from infrastructure errors:** clients may retry inappropriately or blame the user.
17. **Sending <code>IOException.getMessage()</code> to clients:** can leak paths, hostnames, and OS details.
18. **Using real files/real permissions to unit-test mappers:** easily becomes flaky across environments.
19. **Not testing empty files:** easily turns the result into a "not found" error.
20. **Not testing race/symlink scenarios under an applicable threat model:** filename validation does not replace security design.
21. **Testing only error codes without testing cause identity:** wrappers may copy the message while losing the original exception.
22. **Assuming every FileSystemProvider supports options identically:** must test on the target runtime/file system.
23. **Using relative paths against an uncontrolled working directory:** the program may read the wrong file depending on where it is launched.
24. **Deleting test files outside the created area:** cleanup must be restricted to the temp directory owned by the program.

## 21. File Reading Workflow Review Checklist

- Is the input specified as a **file ID, single filename, or relative path**?
- Are null/blank/characters/file type checked according to the contract?
- If multi-segment relative paths are allowed, are appropriate controls in place for root, traversal, and symlinks?
- Are validation and authorization clearly separated?
- Do you avoid treating metadata prechecks as a guarantee that open will succeed?
- When opening the file, are important <code>IOException</code> subtypes caught before the general catch?
- Is the stream closed on all branches: success, decode failure, or oversized?
- Are **actual bytes read** bounded rather than only checking size beforehand?
- Is the charset explicit and is malformed input behavior documented?
- Is an empty file distinguished from a non-existent file?
- Do errors have appropriate codes and preserve the I/O/decoder cause?
- Do public responses omit sensitive details while still offering actionable guidance?
- Do tests cover invalid names, empty files, missing files, directories, oversized files, malformed UTF-8, and success?
- Do cause tests use fakes to verify the exact same exception instance without OS dependencies?
- If untrusted parties can concurrently modify the file system, does the solution address TOCTOU and symlinks per the actual threat model?

## 22. Extension Exercises

### Exercise A — Limit Character Count After Decoding

Add the rule "content must not exceed 500 characters" and define whether "character" means a UTF-16 code unit or a Unicode code point. Test with emojis, Vietnamese text, and strings containing combining characters. Do not replace the byte limit with a character limit if the goal is still to control read volume.

### Exercise B — Multi-line Files

Use <code>BufferedReader</code> and process up to a specific number of lines. Define behavior for very long lines, Windows/Unix newlines, blank lines, and empty files. Ensure the reader is closed if the parser throws an exception.

### Exercise C — Result Structure Without Checked Exceptions

Design a <code>sealed interface ReadResult</code> with <code>Success(content)</code> and <code>Failure(code, message)</code>, then compare it with the checked exception style in the demo. Determine where an internal Throwable should be kept and where only an error code is needed for display.

### Exercise D — Validate a File ID Instead of a Filename

Allow the user to enter a <code>documentId</code> and map it to a server-managed file. Do not let callers dictate OS paths. Write tests proving that an invalid ID does not open any file and a valid ID only reads the authorized file.

### Exercise E — Race Between Check and Open

Diagram a scenario where another party deletes a file after <code>Files.isRegularFile()</code> but before <code>Files.newInputStream()</code>. Explain why <code>NoSuchFileException</code> is still a valid case that must be caught. Propose control mechanisms if the system requires a more consistent file state.

## 23. Summary

A reliable file-reading workflow must check **the right conditions at the right layer**:

- **Validation** checks input names and types without depending on I/O.
- **Path/resource policy** decides which data may be accessed; allowlists simplify this but do not replace file system security.
- **Open/read** is an operation that can fail; handle actual exceptions instead of relying on prechecks.
- **Byte limits** protect resources within defined bounds.
- **Explicit UTF-8 decoding** prevents silently accepting invalid bytes.
- **Try-with-resources** guarantees stream closure and preserves suppressed errors properly.
- **Exception translation** produces meaningful error codes and preserves the original cause for diagnostics.
- **Testing** must cover invalid data, truly empty files, corrupted files, oversized files, and simulated system errors.
- **Security boundaries** must consider path traversal, symlinks, TOCTOU, access permissions, and documented data limits.

**Most importantly:** input validation reduces predictable errors, but it cannot "prove" that a file read operation will succeed. The file system is a mutable environment; a program must both **validate what it controls** and **properly handle errors that occur during I/O**, while keeping a clear boundary between internal diagnostic details and user-facing messages.