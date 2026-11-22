# Diagnosing Wrong Working Directory, Charset, and Resource Paths in Java I/O

## 1. Three Causes of Errors Easily Conflated

A Java program that reads data inside an IDE yet fails when run from a terminal, JAR, container, or server typically hits one of three problem categories:

1. **Wrong working directory (CWD)**: relative file paths resolve against the process's working directory, not where `.java` source files, `.class` files, or the JAR reside.
2. **Wrong charset**: the right file or resource was opened, yet bytes were converted to characters using a different encoding, causing lost Vietnamese diacritics, garbled symbols, or decoding exceptions.
3. **Wrong resource path**: confusing a filesystem path with a classpath/module resource, or confusing a path relative to a class's package with a path relative to the classpath root.

Accurate diagnosis requires separating **where the file is searched**, **how it is looked up**, and **how bytes are interpreted**. Fixing one category does not automatically fix the others.

This Java 17+ knowledge guide in the I/O module covers: recognizing CWD and `user.dir`, using `Path`/`Files` with an explicit base directory, looking up classpath resources in an IDE/JAR, selecting the right charset, reproducing bugs with standalone programs, and building environment-resilient tests.

## 2. The Working Directory Is Not the Source or JAR Directory

An example:

~~~java
Path path = Path.of("data/customers.csv");
String csv = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet to place inside a method with imports and `IOException` handling. The string `data/customers.csv` is a **relative filesystem path**. On the default filesystem, it resolves against the working directory currently used by the runtime. Java does not automatically search:

- The directory containing `.java` source files.
- The build directory containing `.class` files.
- The directory where the JAR is installed.
- `src/main/resources` in the source tree.
- JARs or dependencies on the classpath.

Example layout:

~~~text
/work/app/
  data/customers.csv
  build/classes/example/Main.class
  app.jar
~~~

If the command runs from `/work/app`, the relative path points to `/work/app/data/customers.csv`. If the same JAR runs when CWD is `/srv/service`, Java looks for `/srv/service/data/customers.csv`, where the file does not exist.

Running `java -jar /work/app/app.jar` **does not automatically switch CWD to the JAR's directory**. The launcher, shell, IDE, service manager, or container determines CWD.

### How to Inspect CWD in Java

~~~java
System.out.println(System.getProperty("user.dir"));
System.out.println(Path.of("").toAbsolutePath().normalize());
System.out.println(Path.of("data/customers.csv").toAbsolutePath().normalize());
~~~

The snippet above is illustrative, not a standalone program. Printing these values when an error occurs confirms **where Java is looking for the file**.

`System.getProperty("user.dir")` normally reflects the working directory configured by the runtime at startup. Never use `System.setProperty("user.dir", "...")` as a portable way to change the OS CWD mid-program: mutating a Java property does not guarantee all APIs or filesystem providers treat the process as having changed directories. To change where data is read from, **pass an explicit base `Path`** or launch a child process with the desired working directory.

### Absolute Path, `normalize`, and `toRealPath`

| Method | Function | Notes |
| --- | --- | --- |
| `Path.of("x/y")` | Creates a path on the default provider | Usually relative if there is no root |
| `path.isAbsolute()` | Checks if the path is absolute per provider | Unix and Windows syntax differ |
| `path.toAbsolutePath()` | Builds an absolute representation from current context | Does not prove the file exists |
| `path.normalize()` | Resolves `.` and `..` syntactically | Does not resolve symbolic links |
| `path.toRealPath()` | Resolves to the real path and checks existence per options | Can throw `IOException`; symlink semantics depend on options |
| `base.resolve(relative)` | Joins paths per `Path` rules | If `relative` is absolute, behavior must be validated |

When a path comes from user input, `normalize()` and `startsWith(base)` alone do not satisfy all security requirements: symbolic links can escape `base`, and races exist between checking and opening the file.

## 3. Specify a Base Directory to Avoid Runtime Context Dependence

If the resource is **external application data** such as customer files, logs, output directories, or deployment-specific configs, accept the location via CLI args, config, or environment variables and construct paths from that base.

~~~java
static Path resolveUnderBase(Path baseDirectory, String relativeName)
        throws IOException {
    Path base = baseDirectory.toAbsolutePath().normalize();
    Path resolved = base.resolve(relativeName).normalize();
    if (!resolved.startsWith(base)) {
        throw new IOException("Path outside configured base");
    }
    return resolved;
}
~~~

This is an illustrative method; import `Path` and `IOException`. For untrusted paths, the example only checks lexical traversal and does not fully handle symlinks or TOCTOU races. Enforce concrete permissions and filesystem isolation policies.

Prefer options with clear contracts:

- `--data-dir=/var/lib/example` passed at startup.
- An environment variable or config containing a validated absolute path.
- `Files.createTempDirectory(...)` for temporary test or job data.
- User home when data truly belongs to a user account.
- A data volume mounted at a documented location inside a container.

Do not keep guessing `../data`, `../../data` until one happens to work in the IDE: that breaks as soon as build layouts or service CWDs change.

## 4. Classpath Resources Are a Different Mechanism from the Filesystem

Packaged assets such as templates, static images, schemas, or default configs may live at:

~~~text
src/main/java/example/App.java
src/main/resources/config/defaults.properties
src/main/resources/templates/message.txt
~~~

Build tools normally copy them into the classpath root or JAR:

~~~text
classes/
  example/App.class
  config/defaults.properties
  templates/message.txt
~~~

**Never hardcode the path `src/main/resources/config/defaults.properties` in production.** The source tree need not exist inside a container or after packaging a JAR.

Read resources properly:

~~~java
try (InputStream in = App.class
        .getResourceAsStream("/config/defaults.properties")) {
    if (in == null) throw new FileNotFoundException("Resource missing");
    String content = new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

This snippet requires importing `InputStream`, `FileNotFoundException`, and `StandardCharsets`, having `App` on the classpath, and placing it inside a method. `getResourceAsStream` returns `null` if the lookup fails to find the resource; always check for `null` before reading.

Resources should generally be treated as **read-only assets**. Never try to write runtime state into `src/main/resources` or into a runtime JAR. To let users customize a default template, copy the resource into an application- or user-owned data directory and edit the copy.

## 5. Slash and Package Rules When Looking Up Resources

Given class `com.example.io.Demo` and resource `config/defaults.properties` at the classpath root:

| Expression | Location Searched |
| --- | --- |
| `Demo.class.getResourceAsStream("/config/defaults.properties")` | From resource root |
| `Demo.class.getResourceAsStream("defaults.properties")` | Relative to package `com/example/io/` |
| `Demo.class.getResourceAsStream("config/defaults.properties")` | `com/example/io/config/defaults.properties` |
| `Demo.class.getClassLoader().getResourceAsStream("config/defaults.properties")` | Classloader root |
| `Demo.class.getClassLoader().getResourceAsStream("/config/defaults.properties")` | Usually wrong due to leading slash |

`Class.getResourceAsStream` accepts a leading slash to indicate the root. `ClassLoader.getResourceAsStream` takes resource names according to classloader rules, typically without a leading slash.

Not every classloader is the same instance: application servers, plugins, modules, or test runners may use separate classloaders. Bootstrap-loaded classes can have `getClassLoader()==null`. If a resource exists yet lookup fails, identify which class and classloader perform the lookup.

### When Multiple JARs Contain a Resource with the Same Name

Two dependencies both containing `config/defaults.properties` can cause a resource with "the right name but wrong content" to be loaded. To diagnose:

~~~java
Enumeration<URL> found =
        Demo.class.getClassLoader().getResources("config/defaults.properties");
while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
~~~

This snippet requires imports for `Enumeration` and `URL` plus `IOException` handling; it is not a complete program. Classloader lookup order can vary by environment. Consider namespacing resource paths by module/library or defining an explicit config override mechanism.

## 6. A Resource Inside a JAR Is Not an Ordinary File Path

After packaging, a resource may have a URL like:

~~~text
jar:file:/opt/app/app.jar!/config/defaults.properties
~~~

Do not treat it as a local file at path `/opt/app/app.jar!/config/defaults.properties`. Code can succeed in an IDE where the URL is `file:/.../classes/config/defaults.properties` and fail when the URL becomes `jar:...`.

Example **not recommended as a general solution**:

~~~java
URL url = Demo.class.getResource("/config/defaults.properties");
Path path = Path.of(url.toURI());
~~~

This is illustrative code lacking imports and exception handling; on a `jar:` URI, converting to `Path` can fail if the corresponding filesystem provider has not been created or is unsupported. To simply **read** a resource, use `getResourceAsStream` and `try-with-resources`.

If a library strictly requires a `Path`, copy the resource to a size-bounded temporary file and manage cleanup, or explicitly open and close a ZIP `FileSystem` where appropriate. Never force every URL into a local file.

With named modules (JPMS), module-level resource access scope and encapsulation rules also apply. If the application runs on the module path instead of the traditional classpath, check `Module.getResourceAsStream` and `opens` directives where applicable.

## 7. Wrong Charset: Reading the Right Bytes Yet Creating the Wrong `String`

`Charset` defines the rules for encoding characters into bytes and decoding bytes into characters. If a file was written in UTF-8 yet read using a different charset, Vietnamese diacritics turn into mojibake.

For example, `Café` encoded in UTF-8 becomes:

~~~text
43 61 66 C3 A9
~~~

Here `C3 A9` are the two bytes representing `é`. Reading the same bytes as ISO-8859-1 produces two different characters instead of `é`.

~~~java
String text = "Caf\u00e9";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
String good = new String(utf8, StandardCharsets.UTF_8);
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
System.out.println(text.equals(good));  // true
System.out.println(text.equals(wrong)); // false
~~~

This is an illustrative snippet inside a method importing `StandardCharsets`. Using a Unicode escape in source keeps a test independent of whether a terminal or source editor displays `é`.

### Defaults Are Not Consistent Across All APIs

Some APIs accept an explicit charset, while some overloads use the JVM's default charset:

- `Files.readString(path, StandardCharsets.UTF_8)`: explicit UTF-8.
- `Files.readString(path)` since Java 11: the no-charset overload **is specified to use UTF-8**.
- `Files.newBufferedReader(path)`: the no-charset overload uses UTF-8.
- `new InputStreamReader(input)`: uses the JVM default charset.
- `new FileReader(file)` without charset: uses the default charset.
- `new OutputStreamWriter(output)` without charset: uses the default charset.
- `text.getBytes()` without charset: uses the default charset.
- `text.getBytes(StandardCharsets.UTF_8)`: independent of default.

On Java 17, the default charset can vary by environment, locale, and system configuration. JEP 400 made UTF-8 the default starting in JDK 18 in standard configurations, but did not make all byte encoding or console behaviors identical.

**Never try to fix this by calling `System.setProperty("file.encoding", "UTF-8")` mid-program.** Mutating that property at runtime is not guaranteed to change already-initialized decoders or I/O APIs. Specify the charset at every data boundary.

## 8. File Charset Differs from Console Charset

Terminal rendering involves at least three layers:

~~~text
File bytes
    └── file decoder (UTF-8, ISO-8859-1, ...)
              └── Java String (Unicode text)
                          └── stdout/console encoder
                                    └── terminal decoder / font
                                               └── displayed characters
~~~

If the Java `String` is already correct while the terminal displays garbage, changing the file reader's charset will corrupt the data. Conversely, if the `String` was already corrupted during decoding, changing the terminal font cannot fix the data.

How to check:

1. Compare the decoded `String` against an expected literal with `equals`.
2. Print hex bytes of a small source slice if the data is safe to log.
3. Print the `String`'s code points when needed instead of relying solely on terminal appearance.
4. Check the upstream writer's charset; the file may have been encoded wrongly at the source.
5. Distinguish JVM default charset, API-mandated encoding, console encoding, and OS encoding.
6. For sensitive data, log size/hash or synthetic samples rather than full contents.

A decoding failure may throw `MalformedInputException` or emit replacement characters, depending on the API and decoder policy. `NoSuchFileException` is a path-lookup problem; switching to UTF-8 will never fix it.

### UTF-8 BOM and Newlines

Some UTF-8 files start with BOM `EF BB BF`, which can appear in a Java `String` as a leading `U+FEFF`. Never assume every parser strips the BOM; applications should define an explicit BOM acceptance/stripping contract.

CRLF vs. LF varies across environments and tools. If a parser requires byte-for-byte reproduction, `BufferedReader.readLine()` strips newline terminators, so pick byte-preserving APIs instead.

If you need to reject invalid UTF-8 bytes instead of silently substituting replacement characters, use a `CharsetDecoder` with `CodingErrorAction.REPORT` and catch `CharacterCodingException`.

## 9. Standalone Java 17+ Example: Running from a Different CWD

The program below tests three data lookup paths and one charset-mismatch scenario:

1. Relative file `input.txt` **does not exist in the runtime CWD**.
2. Input file passed by **absolute path** succeeds.
3. Resource `/sample/message.txt` on the classpath root succeeds.
4. `Café` encoded/decoded in UTF-8 round-trips cleanly, while decoding in ISO-8859-1 yields a different `String`.

Test layout:

~~~text
demo/
  ResourcePathsDemo.java
  classes/
    ResourcePathsDemo.class
    sample/message.txt           (RESOURCE_OK)
  input/input.txt                (FILE_OK)
  runtime/                       (directory where program runs, without input.txt)
~~~

Save as **`ResourcePathsDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class ResourcePathsDemo {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Provide absolute path to input.txt");
        }
        Path relative = Path.of("input.txt");
        System.out.println("Relative input found: " + Files.exists(relative));

        Path explicit = Path.of(args[0]);
        System.out.println("Explicit file: " +
                Files.readString(explicit, StandardCharsets.UTF_8).trim());

        try (InputStream in = ResourcePathsDemo.class
                .getResourceAsStream("/sample/message.txt")) {
            if (in == null) throw new IOException("Classpath resource missing");
            String resourceText = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println("Classpath resource: " + resourceText.trim());
        }

        String text = "Caf\u00e9";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("UTF-8 bytes: " +
                HexFormat.of().withUpperCase().formatHex(utf8));
        System.out.println("UTF-8 roundtrip: " +
                text.equals(new String(utf8, StandardCharsets.UTF_8)));
        System.out.println("Wrong decoding changes value: " +
                !text.equals(new String(utf8, StandardCharsets.ISO_8859_1)));
        Charset systemDefault = Charset.defaultCharset();
        System.out.println("Default charset inspected: " + (systemDefault != null));
    }
}
~~~

### Prepare and Run from a Linux/macOS Terminal

From the `demo/` directory:

~~~bash
mkdir -p classes/sample input runtime
printf 'RESOURCE_OK\n' > classes/sample/message.txt
printf 'FILE_OK\n' > input/input.txt
javac -d classes ResourcePathsDemo.java

CLASSES="$(pwd)/classes"
INPUT="$(pwd)/input/input.txt"
cd runtime
java -cp "$CLASSES" ResourcePathsDemo "$INPUT"
~~~

### Prepare on Windows PowerShell

From the `demo/` directory:

~~~powershell
New-Item -ItemType Directory -Force classes/sample, input, runtime | Out-Null
Set-Content classes/sample/message.txt 'RESOURCE_OK' -Encoding ASCII
Set-Content input/input.txt 'FILE_OK' -Encoding ASCII
javac -d classes ResourcePathsDemo.java

$classes = (Resolve-Path classes).Path
$inputFile = (Resolve-Path input/input.txt).Path
Push-Location runtime
try {
    java -cp $classes ResourcePathsDemo $inputFile
} finally {
    Pop-Location
}
~~~

Sample files contain ASCII only so the data-creation scripts do not depend on PowerShell's default encoding. Real files with Vietnamese text should be saved and read in UTF-8 per contract; the program tests `é` via Java's Unicode escape.

**Verified stdout from compiling and running on JDK 17 from a separate runtime directory:**

~~~text
Relative input found: false
Explicit file: FILE_OK
Classpath resource: RESOURCE_OK
UTF-8 bytes: 436166C3A9
UTF-8 roundtrip: true
Wrong decoding changes value: true
Default charset inspected: true
~~~

**Result explanation:**

- `Path.of("input.txt")` is resolved against the CWD `runtime/`, where no file exists, returning `false` in this test.
- `args[0]` points to `input/input.txt` by absolute path, and `Files.readString(..., UTF_8)` returns `FILE_OK`.
- `ResourcePathsDemo.class.getResourceAsStream("/sample/message.txt")` searches from the classpath root containing `classes/`, requiring no file in CWD.
- `String.getBytes(UTF_8)` on `Café` yields `43 61 66 C3 A9`; decoding with UTF-8 restores the `String`, while decoding with ISO-8859-1 produces a different value.
- The default-charset check does not depend on whether the runtime default is Windows-1252 or UTF-8. Real diagnostic code can inspect `Charset.defaultCharset().name()`.
- The resource stream is closed via `try-with-resources`; the input data reads cleanly because both location and charset are explicit.

**Note:** `Files.exists` can return `false` when existence is indeterminate due to I/O or permission errors, so never treat it as absolute proof a path never existed. In this dedicated test, `runtime/input.txt` was deliberately not created.

## 10. Testing After Packaging a JAR

Once compiled and `classes/sample/message.txt` is in place as above, package the JAR:

~~~bash
jar --create --file demo.jar --main-class ResourcePathsDemo -C classes .
jar --list --file demo.jar
~~~

The entry listing must include `ResourcePathsDemo.class` and `sample/message.txt`. Resource paths inside the archive must not accidentally carry a `classes/` or `src/main/resources/` prefix.

Then run the JAR from a different working directory:

~~~bash
java -jar /absolute/path/to/demo.jar /absolute/path/to/input/input.txt
~~~

Replace both example paths with real absolute paths. If the JAR resource is packaged properly, `getResourceAsStream("/sample/message.txt")` still reads it even from another CWD.

If code worked with `java -cp classes ...` yet failed with `java -jar ...`, check:

- Was the resource file packaged into the JAR?
- Does the entry name differ in letter case from what the code requests?
- Did resource filtering/packaging alter the path or bytes?
- Did code depend on `src/test/resources`, which is only on the test classpath?
- Did code call `new File(getResource(...).toURI())`, which fails when the resource inside a JAR is not a plain file?
- Did the classloader or module setup change in the packaged run?

## 11. Maven/Gradle: Resources Have Their Own Lifecycle

In a standard Maven/Gradle project:

~~~text
src/main/java/...
src/main/resources/templates/email.txt
src/test/java/...
src/test/resources/fixtures/data.txt
~~~

`src/main/resources` is copied to the runtime/JAR output under normal build configurations. `src/test/resources` belongs to the test runtime; it **is not packaged into the production JAR by default**.

If a feature works against a test fixture and later runs classpath lookup in production, it may return `null` because the resource is absent.

Resource filtering can modify contents (such as placeholder expressions, charsets, and line endings). For binary assets like images, JKS/PKCS12 keystores, ZIPs, or certificates, never enable text filtering indiscriminately. When exact bytes matter, verify checksums before and after packaging.

In Gradle/Maven IDE configurations, the Run Configuration's working directory is typically the project root, **but never treat that as a production contract**. Pass explicit absolute paths or use CWD-independent resource lookups.

## 12. Making Tests Independent of a Fixed CWD

For file data, use a temporary directory and explicit UTF-8:

~~~java
Path temp = Files.createTempDirectory("io-test-");
Path file = temp.resolve("unicode.txt");
try {
    String expected = "Caf\u00e9";
    Files.writeString(file, expected, StandardCharsets.UTF_8);
    String actual = Files.readString(file, StandardCharsets.UTF_8);
    if (!expected.equals(actual)) throw new AssertionError("Wrong charset");
} finally {
    Files.deleteIfExists(file);
    Files.deleteIfExists(temp);
}
~~~

This is an illustrative snippet inside a method with imports and exception handling. Real tests can use JUnit `@TempDir` for automatic cleanup.

For resources, place fixtures in test resources and read via `TestClass.class.getResourceAsStream("/fixtures/data.txt")`. To catch packaging bugs, include an integration test that runs the real JAR rather than running tests only against the classes directory.

### Reproducing a Different CWD in a Test Harness

Java does not provide a portable API to change the running JVM's OS working directory per thread. Instead of mutating `user.dir`, launch a **child Java process** via `ProcessBuilder.directory(...)`:

~~~java
ProcessBuilder pb = new ProcessBuilder(
        "java", "-cp", absoluteClasspath, "ResourcePathsDemo", absoluteInput);
pb.directory(otherWorkingDir.toFile());
Process child = pb.start();
int exitCode = child.waitFor();
~~~

This is an illustrative snippet, not standalone: `absoluteClasspath`, `absoluteInput`, and `otherWorkingDir` must be declared, with `IOException`/`InterruptedException` handling. In a real integration test, drain stdout/stderr (to avoid blocked pipes), enforce a timeout, and assert exit code and expected output. Resolve the Java executable from the toolchain instead of assuming `java` is always on `PATH`.

**Goal of the test:** expose hidden dependencies on the project root and confirm resource lookups and explicit inputs work from a different CWD.

## 13. Common Errors and How to Classify Them

| Symptom | Error Category | What to Check / How to Fix |
| --- | --- | --- |
| `NoSuchFileException` | Path does not exist at opened location | Log absolute target and CWD |
| `FileNotFoundException` | File stream could not open path | Check path, file type, and permissions |
| `AccessDeniedException` | Insufficient access permissions | Check account, ACLs, mount mode |
| `InvalidPathException` | Invalid path syntax | Validate path input per OS/provider |
| `getResourceAsStream()==null` | Resource lookup failed | Check leading slash, package, JAR/classloader |
| `FileSystemNotFoundException` converting resource URI to `Path` | Wrong filesystem provider handling | Read via `InputStream` or open proper filesystem provider |
| `MalformedInputException` | Invalid bytes for decoder | Inspect original bytes and charset |
| `UnmappableCharacterException` | Character cannot be represented under policy | Choose explicit charset and error strategy |
| Garbled accents with no exception | Mojibake or decoder replacement | Compare Unicode code points and hex |
| Right resource name, wrong content | Duplicate resource across dependencies | Enumerate resource URLs and check classloader |

Never catch `IOException` broadly and report every failure as "File not found." Doing so hides permission, disk, encoding, provider, and network errors.

## 14. Large Files, Resource Streams, and Other Limits

`Files.readString` and `InputStream.readAllBytes()` load all data into memory; suitable for small configs or resources, but a poor default for multi-GB logs.

For large text files, stream line by line:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        handle(line);
    }
}
~~~

This is an illustrative snippet; `handle` is application-provided, and imports/exception handling are needed. `readLine()` strips newline terminators, so when byte-exact preservation is needed for checksums or signatures, work with bytes instead of reconstructing text.

For binary files such as ZIPs, images, keystores, or compressed resources, avoid decoding into a `String` and re-encoding; that can irreversibly corrupt bytes. Use `InputStream` and proper binary parsers.

When reading untrusted input configurations, bound sizes, allowed paths, nesting depth, and I/O timeouts. Normalizing a resource path does not protect against symlinks or races; choose defenses appropriate to your threat model.

## 15. Diagnostic Checklists by Failure Category

### A. Relative File Path Fails

1. Print/log `Path.of("").toAbsolutePath()`, `user.dir`, and `path.toAbsolutePath().normalize()`.
2. Verify file existence at the real target, permissions, and file type.
3. Compare CWD across IDE, terminal, service manager, Docker `WORKDIR`, or container process.
4. Pass a base directory via args/config instead of assuming the project root.
5. Test running from a different CWD using a child process.

### B. Classpath Resource Returns `null`

1. Check the resource path **inside the build output/JAR**, not just in the source tree.
2. Check the leading slash in `Class.getResourceAsStream` and omit leading slashes in `ClassLoader.getResourceAsStream`.
3. Check package-relative paths, case sensitivity, and classloader/module boundaries.
4. Confirm the file is in main resources rather than test-only resources.
5. If multiple matching resources exist, enumerate URL matches.
6. For resources inside a JAR, use `InputStream` rather than converting to a filesystem `File`.

### C. Vietnamese Text Is Corrupted

1. Confirm the right file or resource was opened.
2. Inspect raw bytes, the producer's charset, and the current decoder's charset.
3. Use explicit `StandardCharsets.UTF_8` when the contract specifies UTF-8.
4. Check for BOMs, malformed sequences, and decoder replacement policies.
5. Distinguish a corrupted Java `String` from terminal rendering issues.
6. Write regression tests verifying `String` equality, code points, and expected bytes.

### D. Works in IDE, Fails in Production

1. Compare CWD, JVM version, default charset, locale, classpath, and module path.
2. Inspect JAR contents and packaged resources.
3. Check environment variables, system properties, and service-account permissions.
4. Verify case-sensitive file names on the target OS.
5. Run integration tests from a different CWD and against the real build artifact.
6. Log all necessary path/charset diagnostics without exposing secrets.

## 16. Characteristic Anti-Patterns

| Anti-Pattern | Why It Fails | Replace With |
| --- | --- | --- |
| `Path.of("src/main/resources/template.txt")` in production | Source tree may not exist | `getResourceAsStream("/template.txt")` |
| Assuming `java -jar` changes CWD | JAR location differs from process CWD | Explicit base directory |
| Calling `getResourceAsStream("config/x.txt")` from a class in another package | Name resolves relative to package | Use leading slash if root-relative |
| Calling `ClassLoader.getResourceAsStream("/config/x.txt")` | Violates classloader resource naming | Remove leading slash |
| Converting a `jar:` URL into a local `File` | JAR entries are not standalone local files | Read via stream |
| Writing runtime data into JAR/classpath | Usually read-only / non-writable | Separate data directory |
| `InputStreamReader(in)` without charset on UTF-8 files | Default charset may differ | `InputStreamReader(in, UTF_8)` |
| `String.getBytes()` for fixed formats | Depends on default charset | `getBytes(UTF_8)` |
| Mutating `user.dir` to "fix" CWD | Not portable across OS/processes | Pass base `Path` or `ProcessBuilder.directory` |
| Checking only `Files.exists` and assuming success | Race and permission errors | Actually open/read and handle exceptions |
| Reporting every `IOException` as "file missing" | Masks the real root cause | Classify by exception and operation |
| Changing file decoder because terminal prints wrong accents | Console may be wrong while `String` is right | Inspect `String` and terminal separately |
| Reading binary bytes as text | Can irreversibly corrupt data | Use byte streams |
| Calling `readAllBytes` on huge files | Risks heap exhaustion / OOME | Streaming and bounded memory |

## 17. Self-Check Questions

1. Does `Path.of("data.txt")` search next to the `.class` file or in CWD? **In the process's CWD**, not the class directory.
2. Does `java -jar /opt/app/app.jar` automatically change CWD to `/opt/app`? **No**.
3. How do you inspect the absolute path an application is actually resolving to? `path.toAbsolutePath().normalize()`.
4. Should you call `System.setProperty("user.dir", ...)` to change the OS working directory at runtime? **No**, it is not portable.
5. Does `src/main/resources` always exist on the server after building? **No**.
6. In `Class.getResourceAsStream("/config/x.txt")`, what does the leading slash mean? **Search from the resource root**.
7. Where does `Class.getResourceAsStream("x.txt")` without a slash search? **Relative to the class's package**.
8. Should `ClassLoader.getResourceAsStream` normally start with a slash? **Normally no**.
9. Can a resource inside a JAR always be converted directly to a `File`? **No**; prefer streaming.
10. Does `Files.readString(path)` in JDK 17 use the default charset? **No**, that overload uses UTF-8.
11. What about `new InputStreamReader(in)` without a charset argument? **Uses the JVM default charset**.
12. What are the UTF-8 bytes of `Café`? **`43 61 66 C3 A9`**.
13. Can decoding UTF-8 bytes as ISO-8859-1 corrupt text without throwing an exception? **Yes**.
14. If a Java `String` is right yet the terminal displays wrong accents, does that prove the file is corrupted? **No**; it may be console encoding or font rendering.
15. Which bytes make up a UTF-8 BOM? **`EF BB BF`**.
16. Does `Files.exists(path)==false` prove with certainty that the file does not exist? **Not absolutely**, due to races and permission/I/O errors.
17. How do you catch an app implicitly depending on the IDE working directory? **Launch from a different CWD in an integration test**.
18. Does a file present only in `src/test/resources` automatically go into the production JAR? **Normally no**.
19. If the classpath has two resources with the same name, is there a risk of reading the wrong one? **Yes**; namespace paths or control the classloader.
20. Should runtime data be written into `src/main/resources` or the JAR? **No**; use an explicit writable data directory.

## Official API Reference

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): relative/absolute paths, `normalize`, `toRealPath`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString`, `newBufferedReader`, `newInputStream`, and I/O errors.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getResource`/`getResourceAsStream` and package-relative lookup.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): looking up and enumerating resources.
- [Java SE 17 — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html) and [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): default charset, UTF-8, and standard charsets.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed bytes and decoder policies.
- [Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): launching a child process with a specified working directory.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): the JDK 18 change and compatibility considerations.
