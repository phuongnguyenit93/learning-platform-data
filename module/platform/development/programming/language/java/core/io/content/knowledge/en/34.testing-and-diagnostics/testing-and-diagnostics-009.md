# Diagnosing Wrong Working Directory, Charset, and Resource Paths in Java I/O

## 1. Three Distinct Causes That Are Easily Conflated

A Java program that reads data inside an IDE yet fails when run from a terminal, JAR, container, or server typically hits one of three problem categories:

1. **Wrong working directory (CWD)**: relative file paths resolve against the process's working directory, not the directory containing `.java` source files, `.class` files, or the JAR.
2. **Wrong charset**: the right file/resource was opened, yet bytes are decoded into characters using the wrong encoding, causing garbled Vietnamese diacritics, strange symbols, or decoding exceptions.
3. **Wrong resource path**: confusing a filesystem path with a classpath/module resource, or confusing a path relative to a class's package with a path from the classpath root.

Accurate diagnosis must separate **where the file is searched**, **the lookup mechanism**, and **how bytes are interpreted**. Fixing one category does not automatically fix the others.

Java 17+ guide in the I/O module: recognize CWD and `user.dir`, use `Path`/`Files` with an explicit base directory, resolve classpath resources across IDEs and JARs, choose the right charset, reproduce errors with a standalone program, and write environment-independent tests.

## 2. The Working Directory Is Neither the Source Directory Nor the JAR Directory

Example:

~~~java
Path path = Path.of("data/customers.csv");
String csv = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet meant to sit inside a method with imports and `IOException` handling. The string `data/customers.csv` is a **relative filesystem path**. On the default filesystem, it resolves relative to the runtime's current working directory. Java does not automatically search:

- The directory currently holding `.java` source files.
- The build output directory holding `.class` files.
- The directory where the JAR is installed.
- `src/main/resources` inside the source tree.
- JARs or dependencies on the classpath.

Example layout:

~~~text
/work/app/
  data/customers.csv
  build/classes/example/Main.class
  app.jar
~~~

If the command runs from `/work/app`, the relative path resolves to `/work/app/data/customers.csv`. If the same JAR runs when the CWD is `/srv/service`, Java looks for `/srv/service/data/customers.csv`, where the file does not exist.

Running `java -jar /work/app/app.jar` **does not automatically switch CWD to the JAR's directory**. The launcher, shell, IDE, service manager, or container determines the CWD.

### How to inspect CWD in Java

~~~java
System.out.println(System.getProperty("user.dir"));
System.out.println(Path.of("").toAbsolutePath().normalize());
System.out.println(Path.of("data/customers.csv").toAbsolutePath().normalize());
~~~

This snippet is illustrative, not a standalone program. Printing these values at failure time confirms **where Java is actually looking for the file**.

`System.getProperty("user.dir")` typically reflects the working directory set by the runtime at startup. Never call `System.setProperty("user.dir", "...")` as a portable way to change the OS CWD mid-program: mutating a Java property does not mean every API or filesystem provider will treat the process as having changed directories. To change where data is read, **pass an explicit base `Path`** or launch a child process with the desired working directory.

### Absolute path, `normalize`, and `toRealPath`

| Method | Purpose | Notes |
| --- | --- | --- |
| `Path.of("x/y")` | Creates a path via the default provider | Usually relative if lacking a root |
| `path.isAbsolute()` | Checks if path is absolute per provider | Unix and Windows syntaxes differ |
| `path.toAbsolutePath()` | Produces an absolute representation from current context | Does not prove the file exists |
| `path.normalize()` | Resolves `.` and `..` segments syntactically | Does not resolve symbolic links |
| `path.toRealPath()` | Resolves to the real path and checks existence per options | Can throw `IOException`; symlink semantics depend on options |
| `base.resolve(relative)` | Joins paths according to `Path` rules | If `relative` is absolute, behavior must be validated |

If paths come from user input, `normalize()` and `startsWith(base)` alone are insufficient for all security requirements: symbolic links can point outside `base`, and a race can occur between check and open.

## 3. Specify an Explicit Base Directory to Avoid Execution-Context Coupling

When resources are **external application data** such as customer files, logs, output directories, or deployment-specific configs, accept the location via args/config/env and build paths from that base.

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

This is an illustrative method; import `Path` and `IOException`. For untrusted paths, this example checks only lexical traversal and does not address symlinks or TOCTOU races. Apply explicit permissions and filesystem isolation.

Prefer options with clear contracts:

- `--data-dir=/var/lib/example` passed at startup.
- An environment variable/config entry holding a validated absolute path.
- `Files.createTempDirectory(...)` for temporary test/job data.
- User home when data truly belongs to a user account.
- A data volume mounted at a documented container path.

Do not keep trying `../data`, `../../data` until one happens to work in your IDE: that breaks as soon as build layouts or service CWDs change.

## 4. Classpath Resources Are a Different Mechanism from the Filesystem

Packaged assets such as templates, static images, schemas, or default files might live in:

~~~text
src/main/java/example/App.java
src/main/resources/config/defaults.properties
src/main/resources/templates/message.txt
~~~

Build tools typically copy them into the classpath root or JAR:

~~~text
classes/
  example/App.class
  config/defaults.properties
  templates/message.txt
~~~

**Never hardcode `src/main/resources/config/defaults.properties` in production.** The source tree might not exist inside a container or after packaging into a JAR.

Reading a resource properly:

~~~java
try (InputStream in = App.class
        .getResourceAsStream("/config/defaults.properties")) {
    if (in == null) throw new FileNotFoundException("Resource missing");
    String content = new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

This snippet requires imports for `InputStream`, `FileNotFoundException`, and `StandardCharsets`, with `App` on the classpath inside a method. `getResourceAsStream` returns `null` if the lookup finds no resource; always check for `null` before reading.

Resources should generally be treated as **read-only assets**. Do not try to write runtime state into `src/main/resources` or into a runtime JAR. To let users customize a default template, copy the resource to a user/application-owned data directory and edit the copy.

## 5. Slash and Package Rules When Resolving Resources

Assume class `com.example.io.Demo` and resource `config/defaults.properties` at the classpath root:

| Expression | Location Searched |
| --- | --- |
| `Demo.class.getResourceAsStream("/config/defaults.properties")` | From resource root |
| `Demo.class.getResourceAsStream("defaults.properties")` | Relative to package `com/example/io/` |
| `Demo.class.getResourceAsStream("config/defaults.properties")` | `com/example/io/config/defaults.properties` |
| `Demo.class.getClassLoader().getResourceAsStream("config/defaults.properties")` | Root of the classloader |
| `Demo.class.getClassLoader().getResourceAsStream("/config/defaults.properties")` | Usually fails due to leading slash |

`Class.getResourceAsStream` supports a leading slash to indicate the root. `ClassLoader.getResourceAsStream` takes a resource name per classloader rules, normally without a leading slash.

Not every classloader is the same instance: app servers, plugins, modules, or test runners may use distinct classloaders. Bootstrap-loaded classes can have `getClassLoader() == null`. If a resource exists yet lookup fails, check which class/classloader performs the lookup.

### When multiple JARs contain resources with the same name

Two dependencies both shipping `config/defaults.properties` can cause a "right name, wrong content" resource to load. To diagnose:

~~~java
Enumeration<URL> found =
        Demo.class.getClassLoader().getResources("config/defaults.properties");
while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
~~~

This is a snippet importing `Enumeration`, `URL`, and handling `IOException`; not a complete program. Classloader lookup order can vary by environment. Consider namespacing resource paths by module/library or defining an explicit config override mechanism.

## 6. Resources Inside a JAR Are Not Ordinary File Paths

Once packaged, a resource can have a URL like:

~~~text
jar:file:/opt/app/app.jar!/config/defaults.properties
~~~

Do not treat it as a local file at path `/opt/app/app.jar!/config/defaults.properties`. Code may pass in an IDE where the URL is `file:/.../classes/config/defaults.properties`, yet fail when the URL becomes `jar:...`.

Example **not to use as a general solution**:

~~~java
URL url = Demo.class.getResource("/config/defaults.properties");
Path path = Path.of(url.toURI());
~~~

This is illustrative code missing imports and exception handling; on a JAR URI, converting to `Path` can fail if the corresponding filesystem provider has not been created or is unsupported. To simply **read** a resource, use `getResourceAsStream` and `try-with-resources`.

If a library strictly requires a `Path`, copy the resource to a size-bounded temp file and manage cleanup, or explicitly open/close a ZIP `FileSystem` when appropriate. Never force every URL into a local file.

With named modules (JPMS), module-level resource visibility and encapsulation rules also apply. If an application runs on the module path instead of the traditional classpath, verify `Module.getResourceAsStream` and `opens` directives where applicable.

## 7. Wrong Charset: Reading the Right Bytes Yet Producing the Wrong `String`

A `Charset` defines how characters map to bytes and bytes decode back to characters. If a file was written as UTF-8 but the app reads it with another charset, Vietnamese diacritics turn into mojibake.

For example, `Café` encoded in UTF-8 is:

~~~text
43 61 66 C3 A9
~~~

Here `C3 A9` are the two bytes representing `é`. Decoding the same bytes as ISO-8859-1 produces two different characters instead of `é`.

~~~java
String text = "Caf\u00e9";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
String good = new String(utf8, StandardCharsets.UTF_8);
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
System.out.println(text.equals(good));  // true
System.out.println(text.equals(wrong)); // false
~~~

This is an illustrative snippet inside a method importing `StandardCharsets`. Using a Unicode escape in source keeps the test independent of whether a terminal or source editor displays `é`.

### Defaults are inconsistent across APIs

Some APIs take an explicit charset, while some overloads use the JVM default charset:

- `Files.readString(path, StandardCharsets.UTF_8)`: explicit UTF-8.
- `Files.readString(path)` since Java 11: the no-charset overload **is specified to use UTF-8**.
- `Files.newBufferedReader(path)`: the no-charset overload uses UTF-8.
- `new InputStreamReader(input)`: uses the JVM default charset.
- `new FileReader(file)` without charset: uses the default charset.
- `new OutputStreamWriter(output)` without charset: uses the default charset.
- `text.getBytes()` without charset: uses the default charset.
- `text.getBytes(StandardCharsets.UTF_8)`: independent of the default.

In Java 17, the default charset varies with environment, locale, and system configuration. JEP 400 makes UTF-8 the default starting in JDK 18 under standard configurations, yet does not make every byte encoding or console behavior identical.

**Do not try to fix this mid-program by calling `System.setProperty("file.encoding", "UTF-8")`.** Changing the property at runtime is not guaranteed to change already-initialized decoders or I/O APIs. Always specify the charset at the data boundary.

## 8. File Charset vs Console Charset

Terminal rendering involves at least three layers:

~~~text
File bytes
    └── file decoder (UTF-8, ISO-8859-1, ...)
              └── Java String (Unicode text)
                          └── stdout/console encoder
                                    └── terminal decoder / font
                                               └── displayed characters
~~~

If the Java `String` is already correct while the terminal renders garbage, changing the file reader's charset will corrupt the data. Conversely, if the `String` was decoded wrongly, changing the terminal font cannot fix the data.

How to check:

1. Compare the decoded `String` against an expected literal using `equals`.
2. Print hex of a small slice of source bytes, if logging the data is permitted.
3. Print `String` code points when needed instead of trusting terminal output alone.
4. Check the upstream writer's charset; the file may have been encoded wrongly at the source.
5. Distinguish JVM default charset, API-specified encoding, console encoding, and OS encoding.
6. For sensitive data, log size/hash or synthetic samples instead of full contents.

A decoding failure may throw `MalformedInputException` or emit replacement characters, depending on the API/decoder policy. `NoSuchFileException` is a path-lookup problem; switching to UTF-8 will not cure it.

### UTF-8 BOM and newlines

Some UTF-8 files begin with BOM `EF BB BF`, which can appear in a Java `String` as a leading `U+FEFF`. Do not assume every parser strips BOMs automatically; applications need an explicit accept/strip BOM contract.

CRLF/LF differs across environments and authoring tools. If a parser needs byte-for-byte reproduction, `BufferedReader.readLine()` strips newline characters, so choose byte-preserving APIs instead.

When you need to reject invalid UTF-8 bytes instead of silently substituting replacement characters, use `CharsetDecoder` with `CodingErrorAction.REPORT` and catch `CharacterCodingException`.

## 9. Standalone Java 17+ Example: Running from a Different CWD

This program tests three data-lookup paths plus a wrong-charset scenario:

1. Relative file `input.txt` **is absent from the runtime CWD**.
2. Input file passed by **absolute path** succeeds.
3. Resource `/sample/message.txt` on the classpath root succeeds.
4. `Café` encodes/decodes accurately in UTF-8, while decoding as ISO-8859-1 yields a different `String`.

Test layout:

~~~text
demo/
  ResourcePathsDemo.java
  classes/
    ResourcePathsDemo.class
    sample/message.txt           (RESOURCE_OK)
  input/input.txt                (FILE_OK)
  runtime/                       (working directory for running, no input.txt)
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

### Prepare and run from a Linux/macOS terminal

From `demo/`:

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

From `demo/`:

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

Sample files use ASCII only so the data-creation scripts do not depend on PowerShell's default encoding. Real files containing Vietnamese should be saved/read as UTF-8 per contract; the program tests `é` via a Java Unicode escape.

**Stdout verified by compiling and running on JDK 17 from an isolated runtime directory:**

~~~text
Relative input found: false
Explicit file: FILE_OK
Classpath resource: RESOURCE_OK
UTF-8 bytes: 436166C3A9
UTF-8 roundtrip: true
Wrong decoding changes value: true
Default charset inspected: true
~~~

**Interpreting the results:**

- `Path.of("input.txt")` checks the CWD `runtime/`, where no file exists, returning `false` in this test.
- `args[0]` points to `input/input.txt` by absolute path and `Files.readString(..., UTF_8)` returns `FILE_OK`.
- `ResourcePathsDemo.class.getResourceAsStream("/sample/message.txt")` searches from the root of the classpath containing `classes/`, without needing the file in CWD.
- `String.getBytes(UTF_8)` of `Café` produces bytes `43 61 66 C3 A9`; decoding with UTF-8 restores the `String`, while decoding with ISO-8859-1 produces a different value.
- The default-charset check does not depend on whether the runtime default is Windows-1252 or UTF-8. Code can inspect the name via `Charset.defaultCharset().name()` during real diagnostics.
- The resource stream closes via `try-with-resources`; the data input succeeds because both location and charset are explicit.

**Note:** `Files.exists` can return `false` when existence cannot be determined due to I/O or permission errors, so never use it as absolute proof a path never existed. In this setup, `runtime/input.txt` was deliberately omitted.

## 10. Testing After Packaging a JAR

Once compiled with `classes/sample/message.txt` copied as above, package a JAR:

~~~bash
jar --create --file demo.jar --main-class ResourcePathsDemo -C classes .
jar --list --file demo.jar
~~~

The entry list must contain `ResourcePathsDemo.class` and `sample/message.txt`. Resource paths inside the archive must not accidentally carry a `classes/` or `src/main/resources/` prefix.

Then run the JAR from a different working directory:

~~~bash
java -jar /absolute/path/to/demo.jar /absolute/path/to/input/input.txt
~~~

Replace both paths in the example with real absolute paths. If the JAR resource is packaged correctly, `getResourceAsStream("/sample/message.txt")` still reads it even when CWD is another directory.

If code runs under `java -cp classes ...` yet fails under `java -jar ...`, check:

- Was the resource packaged inside the JAR?
- Does entry name casing differ from the code?
- Did packaging/resource filtering alter paths or bytes?
- Did it rely on `src/test/resources`, which exists only on the test classpath?
- Did code call `new File(getResource(...).toURI())`, failing because a JAR resource is not an ordinary file?
- Did the runtime classloader/module configuration change?

## 11. Maven/Gradle: Resources Have Separate Lifecycles

In a standard Maven/Gradle project:

~~~text
src/main/java/...
src/main/resources/templates/email.txt
src/test/java/...
src/test/resources/fixtures/data.txt
~~~

`src/main/resources` is copied into runtime/JAR outputs under standard build configs. `src/test/resources` belongs to the test runtime; it is **not packaged into production JARs by default**.

If a feature relies only on a test fixture and later runs a classpath lookup in production, it will get `null` because the resource is absent.

Resource filtering can modify contents (such as placeholder expressions, charsets, and line endings). For binary assets like images, JKS/PKCS12 keystores, ZIPs, or certificates, never enable text filtering blindly. When exact content matters, verify checksums before and after packaging.

In Gradle/Maven IDEs, a Run Configuration's working directory defaults to the project root, yet **you must never treat that as a production contract**. Pass explicit absolute paths or use CWD-independent resource lookups.

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

This is an illustrative snippet inside a method with imports and `throws`/exception handling. Real tests can use JUnit `@TempDir` and verify automatic cleanup.

For resources, place fixtures in test resources and read via `TestClass.class.getResourceAsStream("/fixtures/data.txt")`. To catch packaging bugs, run integration tests against the actual built JAR, not solely against the compiled classes directory.

### Reproducing a different CWD in a test harness

Java offers no portable API to change a running JVM's OS working directory per thread. Instead of mutating `user.dir`, launch a **child Java process** via `ProcessBuilder.directory(...)`:

~~~java
ProcessBuilder pb = new ProcessBuilder(
        "java", "-cp", absoluteClasspath, "ResourcePathsDemo", absoluteInput);
pb.directory(otherWorkingDir.toFile());
Process child = pb.start();
int exitCode = child.waitFor();
~~~

This is a non-standalone illustrative snippet: `absoluteClasspath`, `absoluteInput`, and `otherWorkingDir` must be declared, and `IOException`/`InterruptedException` handled. In real integration tests, drain stdout/stderr (to prevent pipe deadlocks), enforce timeouts, and verify exit code and expected output. Prefer the toolchain's Java executable rather than assuming `java` is on `PATH`.

**Test goal:** expose broken paths that silently depend on the project root and confirm resource lookup and explicit inputs work under any CWD.

## 13. Common Errors and How to Classify Them

| Symptom | Error Category | Check / Resolution |
| --- | --- | --- |
| `NoSuchFileException` | Path does not exist at opened location | Log normalized absolute target and CWD |
| `FileNotFoundException` | File stream could not open path | Check path, entry type, permissions |
| `AccessDeniedException` | Missing access permissions | Check account, ACL, mount mode |
| `InvalidPathException` | Invalid path syntax | Validate input path against OS/provider |
| `getResourceAsStream()==null` | Resource lookup failed | Check leading slash, package, JAR/classloader |
| `FileSystemNotFoundException` when converting resource URI to `Path` | Wrong filesystem provider mechanism | Read via `InputStream` or open proper filesystem provider |
| `MalformedInputException` | Bytes invalid for decoder | Inspect original bytes and charset |
| `UnmappableCharacterException` | Character unrepresentable under policy | Choose explicit charset and error strategy |
| Garbled accents with no exception | Mojibake or decoder replacement | Compare Unicode code points and hex bytes |
| Right resource name, wrong content | Duplicate resource in dependencies | Enumerate resource URLs and control classloader |

Never catch broad `IOException` and report every case as "File not found". Doing so masks permission, disk, encoding, provider, and network errors.

## 14. Large Files, Resource Streams, and Other Limits

`Files.readString` and `InputStream.readAllBytes()` load all data into memory; suitable for small configs or resources, poor defaults for multi-GB logs.

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

This is an illustrative snippet; `handle` is application-provided, with full imports/exception handling needed. `readLine()` strips newline terminators, so if byte-exact preservation is needed for checksums or signatures, work with raw bytes rather than reconstructing text.

For binary files such as ZIPs, images, keystores, or compressed resources, avoid decoding to a `String` and re-encoding; that corrupts bytes. Use `InputStream` and an appropriate binary parser.

When processing untrusted input configurations, bound size, allowed paths, nesting depth, and I/O timeouts. Normalizing a resource path does not protect against symlinks/races; choose defenses suited to the threat model.

## 15. Diagnostic Checklists by Error Category

### A. Relative file path does not work

1. Print/log `Path.of("").toAbsolutePath()`, `user.dir`, and `path.toAbsolutePath().normalize()`.
2. Verify the file exists at the real location, plus permissions and file type.
3. Compare CWDs of the IDE, terminal, service manager, Docker `WORKDIR`, or container process.
4. Pass a base directory via args/config instead of assuming project root.
5. Run from a different CWD using a child process.

### B. Classpath resource returns `null`

1. Check the resource path **inside build output/JAR**, not just in the source tree.
2. Check the leading slash on `Class.getResourceAsStream` and omit it on `ClassLoader.getResourceAsStream`.
3. Check package-relative paths, case sensitivity, and classloader/module boundaries.
4. Confirm main resources rather than test-only resources.
5. If duplicate resources exist, enumerate URL matches.
6. For JAR resources, use `InputStream`—never force them into filesystem `File` objects.

### C. Garbled Vietnamese characters

1. Confirm the right file/resource was opened.
2. Inspect original bytes, the producer's charset, and the current decoder charset.
3. Pass explicit `StandardCharsets.UTF_8` when the contract specifies UTF-8.
4. Check BOMs, malformed sequences, and decoder replacement policies.
5. Distinguish a corrupted Java `String` from a terminal display issue.
6. Add a regression test checking `String` equality, code points, and expected bytes.

### D. Works in IDE, fails in production

1. Compare CWD, JVM version, default charset, locale, classpath, and module path.
2. Inspect JAR contents and packaged resources.
3. Check environment variables, system properties, and service-account permissions.
4. Verify case-sensitive filenames on the target OS.
5. Run integration tests from a different CWD and against the actual build artifact.
6. Log necessary path/charset diagnostics without exposing secrets.

## 16. Characteristic Anti-Patterns

| Wrong Approach | Why It Fails | Use Instead |
| --- | --- | --- |
| `Path.of("src/main/resources/template.txt")` in production | Source tree may not exist | `getResourceAsStream("/template.txt")` |
| Assuming `java -jar` changes CWD | JAR location differs from process CWD | Explicit base directory |
| Calling `getResourceAsStream("config/x.txt")` from a packaged class | Relative to class's package | Use leading root slash when needed |
| Calling `ClassLoader.getResourceAsStream("/config/x.txt")` | Violates classloader resource naming | Drop leading slash |
| Forcing a `jar:` URL into a local `File` | JAR resource is not a standalone local file | Read via stream |
| Saving runtime data into JAR/classpath | Usually read-only / non-writable | Separate data directory |
| `InputStreamReader(in)` without charset on UTF-8 files | Default charset may differ | `InputStreamReader(in, UTF_8)` |
| `String.getBytes()` for fixed formats | Depends on default charset | `getBytes(UTF_8)` |
| Mutating `user.dir` to "fix" CWD | Not portable across OS/process | Pass base `Path` or `ProcessBuilder.directory` |
| Checking only `Files.exists` and assuming safety | Races / permission failures | Open/read directly and handle exceptions |
| Reporting every `IOException` as file missing | Hides the actual root cause | Classify by exception and operation |
| Changing file decoder because terminal prints wrong accents | Console may be wrong while `String` is right | Verify `String` and terminal separately |
| Reading binary bytes as text | Irreversibly corrupts bytes | Use byte streams |
| Using `readAllBytes` on huge files | Heap exhaustion / `OutOfMemoryError` | Streaming and bounded memory |

## 17. Self-Check Questions

1. Does `Path.of("data.txt")` search next to the `.class` file or in CWD? **In the process's CWD**, not the class directory.
2. Does `java -jar /opt/app/app.jar` automatically change CWD to `/opt/app`? **No**.
3. How do you check the absolute path an application is actually resolving? `path.toAbsolutePath().normalize()`.
4. Should `System.setProperty("user.dir", ...)` be used to change OS working directory at runtime? **No**, it is not portable.
5. Does `src/main/resources` always exist on the server after building? **No**.
6. In `Class.getResourceAsStream("/config/x.txt")`, what does the leading slash mean? **Search from the resource root**.
7. Where does `Class.getResourceAsStream("x.txt")` without a slash search? **Relative to the class's package**.
8. Should `ClassLoader.getResourceAsStream` normally start with a slash? **Usually no**.
9. Can a JAR resource always be converted directly to a `File`? **No**; prefer streams.
10. Does `Files.readString(path)` in JDK 17 use the default charset? **No**, that overload uses UTF-8.
11. What about `new InputStreamReader(in)` with no charset argument? **It uses the JVM default charset**.
12. What are the UTF-8 bytes of `Café`? **43 61 66 C3 A9**.
13. Can decoding UTF-8 bytes as ISO-8859-1 corrupt characters without throwing an exception? **Yes**.
14. If a Java `String` is right yet the terminal displays wrong accents, does that prove the file is corrupted? **No**; it may be console encoding/font.
15. Which bytes form the UTF-8 BOM? **EF BB BF**.
16. Does `Files.exists(path) == false` prove with certainty the file does not exist? **Not absolutely**, due to races and permission/I/O errors.
17. How do you catch an app implicitly relying on the IDE working directory? **Launch from a different CWD in an integration test**.
18. Are files only in `src/test/resources` packaged into production JARs automatically? **Normally no**.
19. If the classpath holds two resources with the same name, is there a risk of reading the wrong one? **Yes**, namespace them and control the classloader.
20. Should runtime data be written into `src/main/resources` or the JAR? **No**, use an explicit writable data directory.

## API Reference Documentation

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): relative/absolute paths, normalize, toRealPath.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): readString, newBufferedReader, newInputStream, and I/O errors.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): getResource/getResourceAsStream and package-relative lookup.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): looking up and enumerating resources.
- [Java SE 17 — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html) and [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): default charset, UTF-8, and standard charsets.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed bytes and decoder policies.
- [Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): running a child process with a specified working directory.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): JDK 18 change and compatibility considerations.
