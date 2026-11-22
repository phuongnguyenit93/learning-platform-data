# Line Endings in Java and Cross-Platform Tooling

A line ending is a character or sequence of characters that marks the end of a line in a text file. Windows, Linux, and macOS have different historical conventions; editors, Git, build tools, shells, and Java I/O may read or write those conventions differently.

A Java project operating across multiple operating systems needs to standardize how files are stored in the repository, while also understanding when a program must preserve line endings and when it should write them according to the operating system or protocol standard. Without proper control, a small change can cause hundreds of files to appear in a Git diff, prevent shell scripts from running, cause configuration files to be misread, or corrupt the format of data exchanged with other systems.

## 1. What Are LF, CRLF, and CR?

Three common ASCII characters/sequences:

| Name | Escape in Java | Unicode | Hex | Meaning |
|---|---|---:|---:|---|
| Line Feed (LF) | **\n** | U+000A | **0A** | Moves to a new line |
| Carriage Return (CR) | **\r** | U+000D | **0D** | Moves the cursor to the beginning of the line |
| CRLF | **\r\n** | U+000D U+000A | **0D 0A** | CR followed by LF |

Common conventions:

- Linux and modern macOS: LF.
- Windows: CRLF.
- macOS prior to OS X: single CR, now very rare.

CRLF consists of two characters but is interpreted as a single line terminator. Single CR still appears in some legacy files and is supported by Java when reading text lines.

Example with the same two lines `alpha` and `beta`:

~~~text
LF:    alpha\nbeta\n
CRLF:  alpha\r\nbeta\r\n
CR:    alpha\rbeta\r
~~~

The escape sequences above represent the actual characters in the file. If you see the two characters backslash and `n` in the content instead of a line feed, that is escaped text being printed, not an LF line ending.

### 1.1. Line Endings Are Different from Encoding

Encoding defines how characters are converted into bytes; a line ending is a control character within the content. UTF-8 can contain LF, CR, or CRLF as their corresponding bytes. UTF-16 represents the same characters using 16-bit code units and the appropriate byte order.

You should not assume a file uses LF just because it is UTF-8. Nor should you blindly replace byte `0A` in every file: in UTF-16 or binary files, that byte may be part of other data.

A Byte Order Mark (BOM) is an encoding signature at the beginning of a file, such as the UTF-8 BOM `EF BB BF`. A BOM is not a line ending. Some tools accept a BOM, while some parsers or compilers may handle it differently; standardize whether UTF-8 files have a BOM or not according to your project's format and toolchain.

### 1.2. Trailing Line Ending (Final Newline)

A file may end immediately after the last character or have an additional line terminator at the end:

~~~text
"alpha\nbeta"   // No final newline
"alpha\nbeta\n" // Has final newline
~~~

A final newline does not create an extra empty line in the line count of `String.lines()` or `BufferedReader.readLine()`. It is still part of the file content and can affect diffs, shell scripts, or file-reading tools.

For source code, configuration files, Markdown, and scripts, projects usually choose to include a final newline so that Git diffs and Unix tools behave consistently. For data with its own schema, follow the format of that data.

## 2. Why Do Line Endings Cause Cross-Platform Bugs?

A source file might compile on Windows yet produce a massive diff when opened and saved by an editor on Linux. A shell script with CRLF can cause the interpreter to read the CR at the end of the line as part of the command or the interpreter path. A `.bat` file converted entirely to LF can cause issues with some older Windows tools.

Common scenarios:

- A Windows developer commits a CRLF file; a Linux developer checks it out and their editor saves it as LF; Git reports changes across the entire file.
- A `.sh` file with CRLF causes the shebang or shell to report errors like `bad interpreter` or `^M`.
- A `.bat`/`.cmd` file needs CRLF in the working tree but gets converted to LF.
- Exact string comparison tests fail because the output uses CRLF while the expected value uses LF.
- A parser handles LF but forgets the CRLF or CR cases.
- A CSV or text export file mixes multiple line-ending styles.
- A program writes a file using the current machine's line separator when the output format requires fixed LF.
- An HTTP client manually constructs headers using the OS line separator instead of the protocol-mandated CRLF.

The best solution is to define a standard for each file type and let Git/editors enforce it consistently. At the Java layer, choose the read/write API based on the purpose of the data.

## 3. How Does Java Read Line Endings?

The Java source compiler recognizes LF, CR, and CRLF as line terminators. For Java I/O, `BufferedReader.readLine()` also recognizes all three forms and returns the line content without the terminating characters.

### 3.1. BufferedReader.readLine()

Example:

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

`readLine()` accepts:

- Single LF.
- Single CR.
- CRLF, counted as a single terminator.

The method strips the line terminator when returning the `String`. Therefore, after reading with `readLine()`, you no longer know whether the original line ended with LF, CR, or CRLF.

If the application only needs to process lines one by one, this is usually the desired behavior. If you need to preserve the exact source format, read the entire content or raw bytes before analyzing.

### 3.2. Files.readAllLines()

`Files.readAllLines(path, charset)` reads a file into a `List<String>`. The API accepts CRLF, LF, and CR as delimiters; each element does not include the terminator.

~~~java
List<String> lines =
    Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

This approach is convenient for small files. Do not use it to process very large files because all lines are held in memory. Like `BufferedReader.readLine()`, this API does not preserve the original line-ending style.

### 3.3. String.lines() Since Java 11

`String.lines()` creates a stream of lines and recognizes LF, CRLF, or CR:

~~~java
String content = "alpha\r\nbeta\ngamma\r";
long count = content.lines().count();

System.out.println("LINES=" + count);
~~~

Output:

~~~text
LINES=3
~~~

`String.lines()` does not include the line terminator in each element. If the `String` ends with a line terminator, it does not create an extra empty line after that terminator. An empty string has zero lines.

If using regex, `split("\\R", -1)` can preserve the trailing empty element. Note that `split("\\R")` by default discards trailing empty elements, so its result differs from how `String.lines()` behaves.

### 3.4. When You Need to Preserve Line Endings

Use `Files.readString()` when you need to preserve the entire character sequence, including line separators in the middle and at the end of the file:

~~~java
String raw = Files.readString(path, StandardCharsets.UTF_8);
~~~

`Files.readString()` does not automatically normalize CRLF to LF. If the file has CRLF, the `String` contains CRLF; if the file has LF, the `String` contains LF.

For example, two files with identical visible content can produce two different `String`s:

~~~java
String lf = "alpha\nbeta\n";
String crlf = "alpha\r\nbeta\r\n";

System.out.println(lf.equals(crlf)); // false
~~~

This is important to remember when writing tests that compare files, hash content, create digital signatures, or make byte-for-byte copies.

## 4. How Does Java Write Line Endings?

Java provides two main styles of behavior: writing using the current JVM's line separator or writing an explicitly specified separator string.

### 4.1. System.lineSeparator()

`System.lineSeparator()` returns the OS/JVM-dependent separator:

- Unix/Linux/modern macOS: LF.
- Microsoft Windows: CRLF.

~~~java
String nativeSeparator = System.lineSeparator();
System.out.println(nativeSeparator.equals("\r\n") ? "CRLF" : "LF");
~~~

This value is the initial value of the `line.separator` system property when the JVM starts. Do not use it as a universal standard for every file or every protocol.

### 4.2. BufferedWriter.newLine()

`BufferedWriter.newLine()` writes the OS line separator according to `line.separator`:

~~~java
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("alpha");
    writer.newLine();
    writer.write("beta");
    writer.newLine();
}
~~~

On Windows, the file will contain CRLF; on Linux/modern macOS, the file will contain LF. Use this API when the requirement is to write text lines following the runtime environment's convention.

### 4.3. PrintWriter.println()

`PrintWriter.println()` also terminates lines with the OS line separator:

~~~java
try (PrintWriter writer =
         new PrintWriter(
             Files.newBufferedWriter(path, StandardCharsets.UTF_8))) {
    writer.println("alpha");
    writer.println("beta");

    if (writer.checkError()) {
        throw new IOException("Could not write output");
    }
}
~~~

`PrintWriter` has one caveat: its write methods do not throw `IOException` in the usual way; check `checkError()` when you need to detect write failures.

Do not call `println()` if the format requires fixed LF and you are running on Windows. In that case, use an explicit separator.

### 4.4. Writing Fixed LF

If a file needs LF on every OS, write LF directly:

~~~java
String content = "alpha\nbeta\n";
Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

`Files.writeString()` writes the exact characters in the `CharSequence`, including any line separators already in the string; the API does not automatically convert LF to CRLF.

Another option:

~~~java
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("alpha\n");
    writer.write("beta\n");
}
~~~

Do not use `writer.newLine()` in this snippet if the goal is to always produce LF on every operating system.

### 4.5. Files.write() with a List of Lines

`Files.write(path, lines, charset)` takes a list of lines and terminates each element with the platform's line separator:

~~~java
Files.write(
    path,
    List.of("alpha", "beta"),
    StandardCharsets.UTF_8
);
~~~

If you need byte-for-byte accuracy or a fixed line ending, build the string yourself with the chosen separator and use `Files.writeString()`, or write bytes explicitly. `Files.write()` with an `Iterable` is a convenience API for native text output.

### 4.6. Choosing the Right API for Your Requirements

| Requirement | Suitable API |
|---|---|
| Read line by line without needing the original separator | `BufferedReader.readLine()` |
| Read a small file into a list of lines | `Files.readAllLines()` |
| Split a `String` into a stream of lines | `String.lines()` |
| Preserve separators in the file | `Files.readString()` |
| Write native line endings | `BufferedWriter.newLine()` or `PrintWriter.println()` |
| Write fixed LF | `Files.writeString()` with LF |
| Write fixed CRLF | `Files.writeString()` with CRLF |
| Write exact bytes | `Files.write()` with a byte array |

## 5. File Line Endings vs. Protocol Line Endings

Not all multiline data should use the operating system's separator. A source file in Git may use fixed LF; a network protocol may require CRLF; user-facing output may use native line endings.

For example, HTTP/1.1 requires CRLF to terminate lines in message framing. If implementing a protocol manually, you must follow the spec strictly; do not replace CRLF with `System.lineSeparator()` because a program running on Linux would produce LF. In regular applications, use an HTTP client/server library so the library manages framing.

Other examples:

- `.sh` files: usually require LF and a shebang on the first line.
- `.bat`/`.cmd` files: may require CRLF depending on the project's Windows toolchain.
- `.java`, `.kt`, `.gradle`, `.xml`, `.properties`, `.yml` files: usually standardized on LF in the repository.
- CSV/text exports: choose a fixed standard according to the receiving system and integration documentation.
- SMTP or line-based protocols: follow the protocol specification, not the OS.
- Binaries such as `.jar`, `.class`, `.png`, `.zip`: never apply line-ending conversion.

When interacting with external processes via `ProcessBuilder`, remember that script interpreters have their own rules. A shell script running on Linux should have LF; a batch script on Windows should follow the format supported by the command processor and related tools.

## 6. Normalizing Line Endings in Git

Git can normalize text files to LF in the repository/index, and then convert them to LF or CRLF in the working tree based on configuration. This is the standard way to prevent contributors on Windows, Linux, and macOS from generating diffs solely due to different operating systems.

### 6.1. .gitattributes

You should define per-file policies in `.gitattributes` at the repository root:

~~~gitattributes
# Detect text files and normalize their content in the Git index.
* text=auto

# Keep source, build files and Unix scripts as LF in the working tree.
*.java text eol=lf
*.kt text eol=lf
*.gradle text eol=lf
*.gradle.kts text eol=lf
*.properties text eol=lf
*.xml text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.sh text eol=lf

# Use CRLF in Windows command scripts in the working tree.
*.bat text eol=crlf
*.cmd text eol=crlf

# Binary files must never be normalized as text.
*.jar binary
*.class binary
*.png binary
*.jpg binary
*.zip binary
~~~

Meaning:

- `text=auto`: Git automatically detects text files and normalizes line endings in the index.
- `text`: explicitly marks files as text and enables conversion.
- `eol=lf`: working tree uses LF.
- `eol=crlf`: working tree uses CRLF.
- `binary` or `-text`: disables text conversion for binary files.

When `text` is enabled, Git normalizes text file line endings to LF in the index on `add`. On `checkout`, `eol` determines the line ending in the working tree. For example, a `.bat` file can be stored in the index with LF yet checked out as CRLF on Windows according to the configuration above.

Never apply `text` to archives, images, executables, or other binary files. If Git misidentifies a binary file as text, conversion can corrupt its contents.

### 6.2. core.autocrlf and core.eol

Git has per-user settings:

~~~bash
git config --global core.autocrlf true
~~~

On Windows, `true` typically creates CRLF in the working tree and normalizes on `add`. On macOS/Linux, many users set:

~~~bash
git config --global core.autocrlf input
~~~

`input` normalizes CRLF to LF on `add` and does not convert LF to CRLF on `checkout`. `core.eol` accepts `lf`, `crlf`, and `native` to choose line endings for text files on checkout when that configuration applies.

`core.autocrlf` is a contributor's environment setting. `.gitattributes` is a policy stored in the repository that controls each file type. Cross-platform projects should use `.gitattributes` as the primary source of truth rather than requiring each developer to remember a different global setting.

### 6.3. Checking What Git Is Applying

View line endings of files in the index and working tree:

~~~bash
git ls-files --eol
~~~

The output typically looks like:

~~~text
i/lf    w/crlf  attr/text eol=crlf  script.bat
i/lf    w/lf    attr/text eol=lf    src/Main.java
~~~

Where:

- `i/lf`: index contains LF.
- `w/crlf`: working tree contains CRLF.
- `attr/...`: Git attributes applied to the file.

Check attributes by path:

~~~bash
git check-attr text eol -- src/Main.java script.bat
~~~

Check effective configuration and its origin:

~~~bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
~~~

Use `git diff --ignore-space-at-eol` to view content changes while ignoring end-of-line differences during diagnosis. Do not use this option to hide a real content bug during review.

### 6.4. Normalizing a Repository with Existing Legacy Files

When adding or modifying `.gitattributes`, already-tracked files may not yet be normalized in the index. On a separate branch, after ensuring the working tree has saved any needed changes:

~~~bash
git add --renormalize .
git status
git diff --cached --stat
~~~

`git add --renormalize .` reapplies clean filters/line-ending conversions to tracked files. Carefully review the list of changed files and verify that binary files are untouched before committing.

If the diff only changes line endings, reviewers can use `git diff --ignore-space-at-eol` to inspect actual content changes. Avoid performing normalization while having unsaved work or on a branch containing unrelated changes.

## 7. Standardizing Editors with EditorConfig

`.gitattributes` controls Git. EditorConfig instructs editors to save files using the same convention. The two mechanisms complement each other.

Create `.editorconfig` at the repository root:

~~~ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.bat]
end_of_line = crlf

[*.cmd]
end_of_line = crlf
~~~

Properties:

- `charset = utf-8`: standardizes encoding.
- `end_of_line = lf` or `crlf`: selects the line ending when the editor saves.
- `insert_final_newline = true`: appends a newline at the end of the file.
- `trim_trailing_whitespace = true`: removes trailing whitespace at the end of lines.
- `root = true`: stops searching for EditorConfig files in parent directories.

The editor must support EditorConfig natively or have the corresponding plugin installed. After adding the file, reopen a file in the editor and check the line-ending status shown in the status bar. EditorConfig does not automatically fix all existing files; some editors only apply it when a file is opened or saved.

If certain formats have their own conventions, create a specific section for that extension. Ensure `.editorconfig` and `.gitattributes` do not conflict for the same file type.

## 8. Distinguishing Line Endings from Encoding and BOM in Java

When reading text files, specify the charset explicitly to avoid results depending on the machine's default configuration:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

`Files.readString(path, charset)` reads line separators as well and preserves them in the `String`. `Files.readAllLines(path, charset)` splits lines and strips terminators.

If a UTF-8 file has a BOM, a standard UTF-8 decoder may return the BOM as the `U+FEFF` character at the start of the `String`. A BOM does not turn into a newline. If the format requires stripping the BOM, handle it intentionally at the beginning of the content; do not strip `U+FEFF` everywhere, as that character could be valid data.

Example:

~~~java
if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
    text = text.substring(1);
}
~~~

Only perform this step when the input format allows/requires stripping the UTF-8 BOM. Do not use `trim()` to remove line endings because `trim()` also strips leading/trailing whitespace and may cause data loss.

## 9. Java 17+ Practice: Reading and Writing Multiple Line-Ending Styles

The following example creates LF, CRLF, CR, and mixed-ending files, then verifies how Java reads and writes them. The program runs standalone on Java 17 or later.

Create `LineEndingProbe.java`:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class LineEndingProbe {
    private static String classify(String separator) {
        if ("\r\n".equals(separator)) return "CRLF";
        if ("\n".equals(separator)) return "LF";
        if ("\r".equals(separator)) return "CR";
        throw new IllegalStateException("Unexpected line separator");
    }

    private static int count(String value, String token) {
        int result = 0;
        for (int i = 0; i <= value.length() - token.length();) {
            if (value.startsWith(token, i)) {
                result++;
                i += token.length();
            } else {
                i++;
            }
        }
        return result;
    }

    private static void inspect(Path file, String expected, int expectedLines)
            throws IOException {
        Files.writeString(file, expected, StandardCharsets.UTF_8);
        String raw = Files.readString(file, StandardCharsets.UTF_8);

        if (!raw.equals(expected)) {
            throw new AssertionError("Files.readString changed line separators");
        }

        int crlf = count(raw, "\r\n");
        int lf = count(raw, "\n") - crlf;
        int cr = count(raw, "\r") - crlf;

        long streamLines = raw.lines().count();
        List<String> readerLines = new ArrayList<>();

        try (BufferedReader reader =
                 Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                readerLines.add(line);
            }
        }

        List<String> allLines =
            Files.readAllLines(file, StandardCharsets.UTF_8);

        if (streamLines != expectedLines
                || readerLines.size() != expectedLines
                || allLines.size() != expectedLines) {
            throw new AssertionError("Line count mismatch for " + file.getFileName());
        }

        System.out.println(file.getFileName()
                + ": CRLF=" + crlf
                + " LF_ONLY=" + lf
                + " CR_ONLY=" + cr
                + " LINES=" + streamLines);
        System.out.println("  READ_LINES=" + String.join("|", readerLines));
    }

    public static void main(String[] args) throws Exception {
        Path dir = Path.of(args[0]);
        Files.createDirectories(dir);

        System.out.println(
            "SYSTEM_LINE_SEPARATOR=" + classify(System.lineSeparator())
        );

        inspect(dir.resolve("lf.txt"), "one\ntwo\n", 2);
        inspect(dir.resolve("crlf.txt"), "one\r\ntwo\r\n", 2);
        inspect(dir.resolve("cr.txt"), "one\rtwo\r", 2);
        inspect(dir.resolve("mixed.txt"), "one\r\ntwo\nthree\rfour", 4);

        Path fixedLf = dir.resolve("fixed-lf.txt");
        Files.writeString(fixedLf, "one\ntwo\n", StandardCharsets.UTF_8);
        String fixed = Files.readString(fixedLf, StandardCharsets.UTF_8);

        if (!fixed.equals("one\ntwo\n")) {
            throw new AssertionError("Fixed LF changed");
        }
        System.out.println("FILES_WRITE_STRING_PRESERVES_LF=true");

        Path nativeWriter = dir.resolve("native-writer.txt");
        try (BufferedWriter writer =
                 Files.newBufferedWriter(nativeWriter, StandardCharsets.UTF_8)) {
            writer.write("one");
            writer.newLine();
            writer.write("two");
            writer.newLine();
        }

        String nativeText = Files.readString(nativeWriter, StandardCharsets.UTF_8);
        String expectedNative = "one" + System.lineSeparator()
            + "two" + System.lineSeparator();

        if (!nativeText.equals(expectedNative)) {
            throw new AssertionError("BufferedWriter.newLine mismatch");
        }
        System.out.println(
            "BUFFERED_WRITER_NEWLINE=" + classify(System.lineSeparator())
        );

        Path printWriterFile = dir.resolve("print-writer.txt");
        try (PrintWriter writer = new PrintWriter(
                Files.newBufferedWriter(printWriterFile, StandardCharsets.UTF_8))) {
            writer.println("one");
            writer.println("two");
            if (writer.checkError()) {
                throw new IllegalStateException("PrintWriter error");
            }
        }

        String printText = Files.readString(printWriterFile, StandardCharsets.UTF_8);
        if (!printText.equals(expectedNative)) {
            throw new AssertionError("PrintWriter.println mismatch");
        }
        System.out.println(
            "PRINT_WRITER_PRINTLN=" + classify(System.lineSeparator())
        );

        Path bomFile = dir.resolve("utf8-bom.txt");
        byte[] bomText = {
            (byte) 0xEF, (byte) 0xBB, (byte) 0xBF, 'x', '\n'
        };
        Files.write(bomFile, bomText);

        String withBom = Files.readString(bomFile, StandardCharsets.UTF_8);
        if (withBom.isEmpty() || withBom.charAt(0) != '\uFEFF') {
            throw new AssertionError("UTF-8 BOM was not preserved");
        }
        System.out.println("UTF8_BOM_FIRST_CHAR_UFEFF=true");
        System.out.println("LINE_ENDING_TEST=PASS");
    }
}
~~~

Compile and run:

~~~powershell
$JdkHome = "C:\path\to\jdk-17"

& "$JdkHome\bin\javac.exe" --release 17 -d out LineEndingProbe.java
& "$JdkHome\bin\java.exe" -cp out LineEndingProbe data
~~~

Verified output on Windows with Amazon Corretto 17.0.15+6-LTS:

~~~text
SYSTEM_LINE_SEPARATOR=CRLF
lf.txt: CRLF=0 LF_ONLY=2 CR_ONLY=0 LINES=2
  READ_LINES=one|two
crlf.txt: CRLF=2 LF_ONLY=0 CR_ONLY=0 LINES=2
  READ_LINES=one|two
cr.txt: CRLF=0 LF_ONLY=0 CR_ONLY=2 LINES=2
  READ_LINES=one|two
mixed.txt: CRLF=1 LF_ONLY=1 CR_ONLY=1 LINES=4
  READ_LINES=one|two|three|four
FILES_WRITE_STRING_PRESERVES_LF=true
BUFFERED_WRITER_NEWLINE=CRLF
PRINT_WRITER_PRINTLN=CRLF
UTF8_BOM_FIRST_CHAR_UFEFF=true
LINE_ENDING_TEST=PASS
~~~

On Linux/modern macOS, `SYSTEM_LINE_SEPARATOR`, `BUFFERED_WRITER_NEWLINE`, and `PRINT_WRITER_PRINTLN` will be `LF`. The files `lf.txt`, `crlf.txt`, `cr.txt`, and `mixed.txt` still preserve the exact separators written by the program.

## 10. Inspecting and Fixing Line-Ending Issues

When a file unexpectedly appears in a Git diff, check its line endings before making manual edits.

### 10.1. Detecting Files with Mixed Line Endings

Using Git:

~~~bash
git ls-files --eol
~~~

Or using PowerShell to count CRLF/LF/CR bytes in a UTF-8 file without BOM:

~~~powershell
$bytes = [IO.File]::ReadAllBytes("src\Main.java")
$text = [Text.Encoding]::UTF8.GetString($bytes)
$cr = [char]13
$lf = [char]10

$crlf = [regex]::Matches($text, [regex]::Escape([string]$cr + [string]$lf)).Count
$crCount = ($text.ToCharArray() | Where-Object { $_ -eq $cr }).Count
$lfCount = ($text.ToCharArray() | Where-Object { $_ -eq $lf }).Count
$lfOnly = $lfCount - $crlf
$crOnly = $crCount - $crlf

"CRLF=$crlf LF_ONLY=$lfOnly CR_ONLY=$crOnly"
~~~

The PowerShell command above assumes the file is UTF-8 without BOM and is decoded as UTF-8. For UTF-16 or binary files, use tools that understand those encodings/formats; do not apply this byte-counting approach directly.

### 10.2. Changing Line Endings in an Editor

In VS Code, the `LF` or `CRLF` status typically appears in the status bar. Click that indicator to change the line-ending style of the open file, then save. IntelliJ IDEA provides a line separator selector in the status bar or under the File menu depending on the version.

After saving, run:

~~~bash
git diff --check
git diff -- src/Main.java
git ls-files --eol
~~~

Verify whether the diff contains real content changes or only line-ending differences.

### 10.3. Avoiding Accidental Normalization of Binary Files

If Git reports a binary file as modified after adding `text=auto`, check its attributes:

~~~bash
git check-attr text eol -- path/to/file
~~~

Mark binary files with `binary` or `-text` in `.gitattributes`. Do not run `git add --renormalize .` before verifying the patterns and the scope of affected files.

## 11. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| Git diff shows the entire file even when only one line changed | Working tree uses CRLF while index uses LF, or vice versa | Add `.gitattributes`, check `git ls-files --eol` |
| `.sh` reports `bad interpreter` or `^M` | Script has CRLF on the shebang line | Set `*.sh text eol=lf`, convert file to LF |
| `.bat`/`.cmd` line endings keep changing | Editor or Git is applying LF to batch files | Set `*.bat text eol=crlf` and `*.cmd text eol=crlf` |
| `equals` test fails on Windows | Expected LF, actual CRLF | Normalize data per contract or compare line by line if separators are not significant |
| Parser only reads Linux files | Code only searches for LF | Use `BufferedReader.readLine()`, `String.lines()`, or a parser that handles CRLF/CR |
| `readLine()` reads fine, but written file is altered | Reading strips terminators and writing uses `newLine()` | Choose target separator explicitly; do not expect round-trip preservation |
| File's trailing empty line is lost | `String.lines()` does not create an empty line after a final terminator; `split()` drops trailing empty strings by default | Use an appropriate parser or `split("\\R", -1)` when trailing empty elements must be kept |
| File has a strange character at the start of content | BOM was preserved as `U+FEFF` | Handle BOM according to format, only at the start of the file |
| Binary file is corrupted after `add` | Git mistakenly applied text conversion | Mark as `binary`/`-text` and restore the binary from a clean source |
| Windows and Linux produce different output | Used `System.lineSeparator()`/`println()` for a format requiring a fixed separator | Write LF or CRLF explicitly according to the specification |
| Hand-built HTTP request fails | Used LF/native separator instead of protocol CRLF | Use an HTTP library or build framing with proper CRLF |
| File still has mixed endings after fixing | Some lines were not normalized or a tool rewrote it differently | Run a full-file check and normalize via editor/Git |

## 12. Standard Workflow for Java Teams

A simple workflow you can adopt in a cross-platform project:

1. Choose LF for Java source, build scripts, configuration, and documentation in the repository.
2. Choose CRLF for `.bat`/`.cmd` if your project's Windows toolchain requires it.
3. Explicitly mark binary files with `binary` or `-text`.
4. Commit `.gitattributes` so Git normalizes the index and working tree per file type.
5. Commit `.editorconfig` so editors automatically save with the right line endings and encoding.
6. Use `BufferedReader.readLine()`/`String.lines()` for line-processing logic.
7. Use `Files.readString()` if you need to preserve separators; use `Files.writeString()` with LF or CRLF when fixed output is required.
8. Use `System.lineSeparator()`, `BufferedWriter.newLine()`, or `println()` when you genuinely want native line endings.
9. For protocols, strictly follow the line terminator defined by the protocol.
10. After adding a new policy, check `git ls-files --eol`, review the diff, and only then commit the normalization.

Do not mass-change line endings on a branch with unsaved changes. If the repository already has many files with mixed styles, create a separate normalization change so it is easy to review and does not get mixed with logic refactoring.

## 13. Pre-Completion Checklist

- [ ] Distinguished between LF, CRLF, and CR.
- [ ] Distinguished line endings from encoding and BOM.
- [ ] Decided on a final newline policy.
- [ ] Chosen standards for source, config, scripts, data, and binaries.
- [ ] `.gitattributes` has appropriate `text`/`eol` rules for each file type.
- [ ] `.editorconfig` has `charset`, `end_of_line`, and `insert_final_newline`.
- [ ] Java reads lines using APIs that accept LF/CRLF/CR when needed.
- [ ] Java writes native or fixed line endings as required.
- [ ] Tests do not assume a single OS's separator when the format does not require it.
- [ ] Shell scripts use LF and batch scripts use a supported line ending.
- [ ] Network protocols use proper CRLF when required by the specification.
- [ ] Git binary files are excluded from text conversion.
- [ ] Verified with `git ls-files --eol` and `git diff --check`.
- [ ] Carefully reviewed the diff after `git add --renormalize .`.

## 14. Key Takeaways

LF is `U+000A`, CR is `U+000D`, and CRLF is the two-character sequence CR followed by LF, treated as a single line terminator. Windows typically uses CRLF; Linux and modern macOS use LF. Encoding and BOM are separate concerns regarding text representation.

Java's `BufferedReader.readLine()`, `Files.readAllLines()`, and `String.lines()` accept LF, CRLF, and CR, but strip the separator when returning lines. `Files.readString()` preserves separators; `Files.writeString()` writes the exact characters in the string. `BufferedWriter.newLine()` and `PrintWriter.println()` use the operating system's line separator.

In cross-platform projects, use `.gitattributes` to normalize files in Git, `.editorconfig` to align editors, and choose Java APIs based on the data's purpose. Never use native separators for files or protocols with fixed requirements; always inspect diffs and formatting after changing policies.

References:

- [Git — gitattributes: End-of-line conversion](https://git-scm.com/docs/gitattributes)
- [Git — core.autocrlf and core.safecrlf](https://git-scm.com/docs/git-config)
- [GitHub Docs — Configuring Git to handle line endings](https://docs.github.com/en/get-started/git-basics/configuring-git-to-handle-line-endings)
- [EditorConfig Specification](https://spec.editorconfig.org/)
- [BufferedReader — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [BufferedWriter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [PrintWriter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [System.lineSeparator — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Files — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [String.lines — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java Language Specification — Line Terminators](https://docs.oracle.com/javase/specs/jls/se17/jls17.pdf)