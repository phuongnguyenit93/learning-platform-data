# Source encoding with javac

Source encoding is the way bytes in a source code file are interpreted into Unicode characters that the Java compiler can read. When the file's encoding and the encoding used by javac do not match, the program may report an illegal character error or compile successfully while Vietnamese strings end up with corrupted diacritics (mojibake).

With javac, the clear and reliable approach is to save source code as UTF-8 and pass the **-encoding UTF-8** option when compiling. This option tells the compiler how to decode source files; it does not convert the file's bytes, nor does it determine the encoding of data that the program writes to the terminal or to a file.

## 1. At which step does encoding happen?

A **.java** file on disk is a sequence of bytes. Before parsing, javac needs to decode that byte sequence according to a character set to obtain a sequence of characters. The general processing flow is:

1. An editor or tool creates the file and saves characters as bytes using an encoding, such as UTF-8.
2. javac reads the bytes and decodes them using the encoding specified by **-encoding**; if not specified, the compiler uses the default charset of the environment/JDK.
3. After decoding, the compiler performs Unicode character processing, lexical analysis, parsing, type checking, and bytecode generation.
4. At runtime, the JVM reads the string constants already stored in the class file. The source encoding is no longer used to re-decode the .java file.

Key point to remember: **source file encoding is a compile-time decision**. A compiled application does not need to retain the original encoding of the .java file to display strings.

## 2. The -encoding option of javac

Syntax:

~~~bash
javac -encoding <encoding> <source-files>
~~~

Example:

~~~bash
javac -encoding UTF-8 Chao.java
~~~

The **-encoding** option specifies the character set that javac uses to read source files in a compilation run. Charset names are usually case-insensitive. Some common names:

| Encoding | Use case |
|---|---|
| UTF-8 | Recommended choice for new Java projects; supports Unicode and is well compatible across operating systems |
| windows-1252 | Some legacy Windows/Western Europe source code |
| Shift_JIS | Some legacy Japanese systems |
| GBK | Some legacy Chinese systems |
| ISO-8859-1 | Legacy projects or data using Latin-1 |

Only choose an encoding that matches the actual bytes of the file. You cannot fix a file saved in Windows-1252 just by changing the encoding name in the configuration if the bytes have not been converted.

You can view the compiler options with:

~~~bash
javac --help
~~~

The **-encoding** option can be used together with other options such as **-d**, **-classpath**, **--release**, and **-Xlint**:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:all -d out src/Chao.java
~~~

In this example, **--release 17** selects the Java 17 API and language/bytecode compatibility level; **-encoding UTF-8** is independent of the release choice and controls how source files are read.

## 3. Default charset changes by JDK version

If **-encoding** is not passed, javac uses the default charset of the Java environment. This can cause compilation results to differ across machines.

- Before JDK 18, the default charset usually depended on the operating system, locale, and machine configuration. A Windows machine might use a local code page while a Linux machine used UTF-8.
- Starting in JDK 18, per JEP 400, UTF-8 became Java's default charset across most standard runtime environments. A compatibility mode exists to preserve the legacy default behavior in certain cases.
- Even when using JDK 18 or later, specifying **-encoding UTF-8** still makes the project's intent explicit in the build command and avoids depending on environment configuration.

You should not rely on the default charset to determine source code encoding. Explicit configuration ensures that the IDE, CI machine, developer machines, and release build machines all read the exact same content.

## 4. Practical example with Vietnamese

Create the file **Chao.java** and save it as UTF-8:

~~~java
public class Chao {
    public static void main(String[] args) {
        String greeting = "Xin chào, thế giới!";
        String vietnamese = "Tiếng Việt có đủ dấu: ă â đ ê ô ơ ư";
        System.out.println(greeting);
        System.out.println(vietnamese);
    }
}
~~~

Compile:

~~~bash
javac -encoding UTF-8 Chao.java
~~~

Run:

~~~bash
java Chao
~~~

Stdout on a terminal capable of displaying UTF-8:

~~~text
Xin chào, thế giới!
Tiếng Việt có đủ dấu: ă â đ ê ô ơ ư
~~~

If the compiler reads a UTF-8 file using an incompatible charset, two kinds of problems can occur:

- The compiler reports an error such as unmappable character or malformed input when a byte sequence is invalid under the selected charset.
- The compiler still decodes the bytes, but into different characters. In that case, the source code may compile successfully, yet the strings in the program are already corrupted right at compile time.

For example, if the UTF-8 bytes of the word **chào** are interpreted as another single-byte encoding, the string may turn into mojibake such as **chÃ o**. This is a source decoding error, not a System.out.println error.

## 5. Distinguishing source encoding from output encoding

The following three things are independent of one another:

| Component | What does it control? | Common way to configure |
|---|---|---|
| Source encoding | How javac reads the bytes of .java files | javac -encoding UTF-8 |
| Runtime file/resource encoding | How the program reads or writes file/resource contents | Specify Charset in I/O APIs |
| Terminal/console encoding | How the terminal displays stdout bytes | Terminal, locale, and runtime environment settings |

Therefore, a program can be compiled correctly with **-encoding UTF-8** yet the terminal still displays garbled text if the console does not decode output as UTF-8. Conversely, a UTF-8 terminal cannot fix a string that javac already decoded incorrectly from the source file.

When writing files, you should specify the charset explicitly instead of relying on the default:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WriteUtf8 {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("message.txt");
        Files.writeString(output, "Xin chào từ Java", StandardCharsets.UTF_8);
    }
}
~~~

Here **StandardCharsets.UTF_8** controls the encoding of the file written at runtime. It does not replace the **javac -encoding UTF-8** option.

## 6. Unicode in Java source code

Java supports Unicode in string literals, character literals, comments, and identifiers according to the rules of the language. With UTF-8 source files, characters can be written directly:

~~~java
String city = "Hồ Chí Minh";
char letter = 'đ';
~~~

Java also has Unicode escape syntax in the form **\\uXXXX**, where XXXX is four hexadecimal digits representing a UTF-16 code unit. For example:

~~~java
String cafe = "Caf\u00E9";
System.out.println(cafe);
~~~

Stdout:

~~~text
Café
~~~

Unicode escapes are processed during the source character translation phase before tokenization. Because of this, escapes can produce syntactically meaningful characters, even in ways the author did not expect. You should not use escapes arbitrarily as a substitute for standardizing on UTF-8.

For characters outside the Basic Multilingual Plane, Java represents them in UTF-16 using a surrogate pair. UTF-8 source files allow storing those characters directly; when you need to process by Unicode code point, use APIs such as **String.codePoints()** instead of assuming each visible character corresponds to a single char value.

## 7. Setting encoding in the build process

It is important to configure encoding where javac is actually invoked. If you only configure the editor to save as UTF-8 while CI runs the compiler with a different default encoding, the build can still fail.

### Compiling directly from the command line

Suppose the directory structure is:

~~~text
project/
  src/
    Chao.java
  out/
~~~

Linux/macOS:

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out src/Chao.java
java -cp out Chao
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/Chao.java
java -cp out Chao
~~~

The **out** directory is where javac writes class files. The **-d** option is unrelated to source encoding.

### Maven

In Maven, declare the encoding at the project and compiler plugin levels so the configuration is explicit:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**project.build.sourceEncoding** is the standard property commonly used by Maven plugins to process source content and resources. The **encoding** configuration in maven-compiler-plugin explicitly sets the charset that the compiler uses for source files. In a real project, use the plugin version standardized and managed by your organization.

Run the build:

~~~bash
mvn clean compile
~~~

### Gradle Groovy DSL

In **build.gradle**:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

### Gradle Kotlin DSL

In **build.gradle.kts**:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

The configuration above applies to Java compilation tasks. If the project has multiple modules, place it in a convention plugin or shared configuration so modules do not accidentally use different encodings.

## 8. Diagnosing encoding errors

### Case 1: Compiler reports unmappable character

The common cause is that the file was saved using one charset while javac is decoding it using another.

How to resolve:

1. Check the actual encoding of the file in the editor.
2. Verify which **-encoding** the build command is using or how the build tool sets **options.encoding**.
3. If the project standardizes on UTF-8, convert the file to UTF-8 using the editor or a controlled conversion tool.
4. Recompile with **-encoding UTF-8**.
5. Check any other source files read by the compiler in the same build run.

Do not simply change the configuration to an arbitrary charset just to silence the error message. Determine the actual encoding first; otherwise you may turn a clear error into corrupted data that still compiles.

### Case 2: Compilation succeeds but Vietnamese diacritics are corrupted

This is the case where the compiler decoded bytes into valid characters, but those characters are not the intended content.

How to resolve:

1. Open the source file and verify that the content displays properly in the editor.
2. Check the file's encoding status, such as UTF-8.
3. Check the encoding in the javac command or Maven/Gradle configuration.
4. Delete old compilation outputs and rebuild to be sure the class file is generated from the corrected source.
5. Run the program in a terminal configured to display UTF-8.

If the terminal output is wrong while the source and class file contents are already correct, check the console encoding separately instead of continuing to change the source encoding.

### Case 3: Works on a developer machine but fails on CI

A common cause is that the local machine and CI have different default charsets, or CI uses a different build command than the IDE.

How to resolve:

- Standardize on one source file encoding in the repository, preferably UTF-8.
- Set the compiler encoding explicitly in Maven/Gradle or on the command line.
- Ensure CI uses the same build script as developers.
- Perform a clean build in the CI environment.
- Check whether individual modules or compilation tasks have overriding configurations.

### Case 4: Error at the very first character of the file

If the compiler reports an illegal character right at the beginning of the file, check whether the file has a byte order mark (BOM) or an invisible character at the start. Inspect it using an editor or byte viewer, then save it again using the encoding prescribed by the project. Avoid mechanically deleting leading bytes without first identifying the file format.

## 9. Process for standardizing source encoding in a project

An easy-to-maintain workflow:

1. Choose one consistent encoding for source code; for new projects, choose UTF-8.
2. Configure editors and formatters to save Java files as UTF-8.
3. Configure the compiler with **-encoding UTF-8**, or the equivalent configuration in Maven/Gradle.
4. Convert legacy files to UTF-8 in one pass, and review the diff to catch unexpected character changes.
5. Configure CI to run a clean build and use the same build script as local development.
6. Check terminal and file I/O encodings separately when the program reads or writes text data.
7. Document the encoding convention in the project documentation so new members use the same configuration.

Avoid mixing multiple encodings within a single javac invocation whenever possible. The **-encoding** option is a single setting applied to all source files read in that compilation run. If a repository contains legacy source code in multiple encodings, convert them to a single standard or separate the build process in a controlled way before merging.

## 10. Common misconceptions

| Misconception | Reality |
|---|---|
| JDK 18+ always makes -encoding unnecessary for every project | The UTF-8 default charset reduces environment differences, but explicit configuration still makes builds more reproducible |
| -encoding converts source files to UTF-8 | It only specifies how javac decodes bytes; to convert files, use an editor or conversion tool |
| A UTF-8 terminal guarantees javac reads source files correctly | The terminal only affects how output is displayed; javac has its own source decoding step |
| Successful compilation means the encoding is correct | Bytes can decode into valid characters that are still the wrong content |
| --release 17 selects the encoding corresponding to Java 17 | --release selects the language/API/bytecode level; -encoding controls the source charset |
| Strings in a class file need to know the encoding of the original .java file | The JVM uses data already written into the class file by the compiler; source encoding is not used again at runtime |

## 11. Takeaways

- Save Java source code as UTF-8 and set **javac -encoding UTF-8** in the build process.
- Source file encoding, runtime file I/O encoding, and terminal encoding are three separate configurations.
- JDK 18 and later default to UTF-8 per JEP 400; prior to that, the default usually depended on the environment.
- If the compiler reports an unmappable character, check the file's actual encoding and compiler configuration before converting.
- If compilation succeeds but Vietnamese diacritics are corrupted, check source decoding, stale class output, and the terminal.
- Use Maven/Gradle configuration so local builds and CI compile according to the same convention.
- Unicode escapes are Java syntax; for modern projects, saving UTF-8 source files is usually easier to read and maintain.