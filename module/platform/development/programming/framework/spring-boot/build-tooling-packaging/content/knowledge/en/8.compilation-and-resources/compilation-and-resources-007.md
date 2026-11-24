# Preserving Binary Resources When Filtering or Substituting Content

## 1. The Problem in Spring Boot Build Tooling Packaging

When compiling and packaging a Spring Boot application, resource directories often hold both **text** files that need token substitution (such as `build-info.properties`) and **binary** files that must remain untouched (images, PDFs, fonts, JARs, ZIPs, certificates, keystores, or `.bin` data). A build can succeed and the JAR can still list every filename while the bytes inside are corrupted, rendering images unopenable, documents broken, or resources unreadable by the program.

**Resource filtering** reads resources as text, locates placeholders like `@project.version@`, and substitutes build-time values. **Binary-safe copying** copies bytes directly without decoding, substituting tokens, or re-encoding. These two operations must be separated right in the Maven/Gradle configuration.

You will learn how to:

1. Distinguish byte-for-byte copying from text filtering/content expansion.
2. Explain why misconfigured filtering can corrupt binary files while `mvn package` still reports green.
3. Separate files that need filtering from files that must not be filtered in Maven Resources Plugin configuration.
4. Use Java 17+ and Spring Boot to verify text and binary resources on the runtime classpath.
5. Compare bytes across the source file, `target/classes`, and the entry inside the executable JAR.
6. Recognize `nonFilteredFileExtensions`, escaping, encoding, and collisions between Maven tokens and Spring runtime placeholders.
7. Apply the equivalent principles to Gradle `processResources` and downstream packaging steps.

This lesson belongs to **Compilation and Resources**; the focus is resource handling during the build, not writing parsers for specific binary formats.

## 2. Which Steps Carry Resources from Source to JAR?

In a standard Maven Java project:

~~~text
src/main/java            src/main/resources
     |                           |
     v                           v
Java compilation         process-resources
     |                    copy / filter
     +------------+--------------+
                  |
                  v
            target/classes
                  |
                  v
               package
                  |
                  v
              plain JAR
                  |
                  v
     Spring Boot repackage (if configured)
                  |
                  v
         executable JAR
                  |
                  v
             java -jar
~~~

Maven Resources Plugin typically processes files in `src/main/resources` during the `process-resources` phase, copying resources into `target/classes` along their relative paths. The `package` phase then archives classes and resources. Spring Boot Maven Plugin `repackage` can convert them into an executable archive, placing application resources under `BOOT-INF/classes` in the standard JAR layout and runtime dependencies under `BOOT-INF/lib`.

If a file is already corrupted when copied to `target/classes`, `repackage` cannot restore the original bytes. Conversely, even when `target/classes` is intact, a later step such as a custom `Copy`, shading/assembly, or a deployment script can alter the artifact. Therefore, verify at the **final destination**.

| Step | Input/Output | Criterion |
| --- | --- | --- |
| Verbatim copy | `src/main/resources/assets/logo.png` → `target/classes/assets/logo.png` | Byte-for-byte equality |
| Text filtering | `build-info.properties` with `@project.version@` → actual version value | Replaces intended tokens; preserves other text intentionally |
| Archive packaging | `target/classes/assets/logo.png` → JAR entry `BOOT-INF/classes/assets/logo.png` | **Entry** contents match the source file |
| Deploy and run | Executable JAR/OCI image → live application | File remains at the right path and parses/reads cleanly |

Comparing the SHA-256 of the **entire JAR** against the source image hash is meaningless because a JAR is a container holding many entries. Compare the source resource bytes against the bytes of the **exact entry** extracted from the archive.

## 3. Why Is Text Filtering Dangerous for Binary Data?

A text filter typically performs steps equivalent to:

~~~text
input bytes
   -> decode with charset (e.g. UTF-8)
   -> search for tokens
   -> substitute values
   -> encode back to bytes
   -> write output
~~~

Each plugin has its own implementation, yet the core risk is clear: arbitrary binary bytes do not necessarily form valid text. Bytes such as `FF` and `80` are invalid standalone UTF-8 sequences; decoding and re-encoding can fail or alter bytes. If the payload happens to contain `@project.version@`, the filter can even replace that sequence with `1.0.0`, breaking lengths, offsets, checksums, or file signatures.

Imagine a payload containing the bytes:

~~~text
00 FF 80 40 70 72 6F 6A 65 63 74 2E 76 65 72 73 69 6F 6E 40 0A 0D
~~~

In the middle sit the ASCII characters `@project.version@`, yet the file **is not a text template**. Do not try to fix this by switching `UTF-8` to another encoding; the real requirement is **never running text filtering on that file**.

Formats that commonly require protection include `.png`, `.jpg`, `.gif`, `.ico`, `.pdf`, `.zip`, `.jar`, `.woff2`, `.ttf`, `.p12`, `.jks`, `.class`, `.bin`, and custom binary formats. File extensions are not absolute proof: an extensionless file or a `.dat` file can still hold binary data.

## 4. Safe Maven Strategy: Separate Filtered and Unfiltered Sources

The easiest strategy to audit is **allowlisting** the specific text files that need content substitution while copying everything else byte-for-byte.

~~~text
src/main/resources/                  (unfiltered)
  application.yml
  assets/logo.png
  assets/manual.pdf
  assets/payload.bin
  fonts/site.woff2

src/main/resources-filtered/         (selectively filtered)
  build-info.properties
~~~

Declare two resource entries:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/resources-filtered</directory>
            <filtering>true</filtering>
            <includes>
                <include>build-info.properties</include>
            </includes>
        </resource>
    </resources>
</build>
~~~

Binary files are copied via the `filtering=false` branch even if their contents contain token-like byte sequences. Only `build-info.properties` in the second directory is parsed as text. Both branches place resources into the same Maven classpath output, defaulting to `target/classes`.

There is no reason to push every file in `src/main/resources` through filtering just because one text file needs a version substituted. This principle lowers risk whenever someone adds a PDF, keystore, or new format without updating an extension list.

An alternative sharing one directory with two include/exclude entries is presented in section 8. Both approaches are **alternatives**; do not layer them so the same file is copied twice.

## 5. Standalone Lab: Java 17 + Maven + Spring Boot

This lab creates a binary file containing a fake token, filters the version in a text file, packages an executable JAR, and uses Java to prove the binary bytes remain untouched.

**Prerequisites:** JDK 17+, Maven 3.x compatible with Spring Boot 3.3.5, and ability to resolve dependencies. Spring Boot `3.3.5` and Maven Resources Plugin `3.3.1` are **pinned versions for the example**, not a recommendation of the latest releases.

### 5.1. File Structure

~~~text
resource-demo/
  pom.xml
  CreateFixture.java
  CompareArchive.java
  src/
    main/
      java/
        demo/
          Application.java
      resources/
        assets/
          payload.bin             (created in a following step)
      resources-filtered/
        build-info.properties
~~~

The two Java files at the project root are utilities executed with Java's single-file source launcher. They are **not** compiled by Maven into the application JAR because they are outside `src/main/java`. The actual Spring Boot program lives at `demo.Application`.

### 5.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example.learning</groupId>
    <artifactId>resource-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
            <resource>
                <directory>src/main/resources-filtered</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-info.properties</include>
                </includes>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM explanation:

- `<filtering>false</filtering>` ensures `payload.bin` **never passes through the text decoder or token interpolator**.
- `<filtering>true</filtering>` combined with `<includes>` restricts filtering to a single known text file.
- `<delimiter>@</delimiter>` and `<useDefaultDelimiters>false</useDefaultDelimiters>` allow `@project.version@` to be interpolated without treating Spring `${...}` expressions as Maven tokens.
- `<encoding>UTF-8</encoding>` governs the filtered text file; it does **not** force decoding of unfiltered binaries.
- `spring-boot-starter-parent` plus declaring the Spring Boot Maven Plugin enables `repackage` during `mvn package` per the parent configuration.
- `spring-boot-starter` is the core starter without an HTTP server, so the verification program runs and exits cleanly.

If another project does not use the Spring Boot parent, binding `spring-boot:repackage` requires explicit configuration. That is a lifecycle difference unrelated to protecting resource bytes.

### 5.3. Text File with Placeholders

Create `src/main/resources-filtered/build-info.properties`:

~~~properties
build.version=@project.version@
runtime.placeholder=${APP_RUNTIME_VALUE}
~~~

After filtering, expected contents at `target/classes/build-info.properties`:

~~~properties
build.version=1.0.0
runtime.placeholder=${APP_RUNTIME_VALUE}
~~~

The Maven version is substituted from the POM; the runtime placeholder is untouched by text filtering. Secrets such as passwords or API tokens should not be interpolated into packaged files; supply them via runtime environment configuration.

### 5.4. Creating the Binary Fixture with Java

Create `CreateFixture.java` at the root:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateFixture {
    public static void main(String[] args) throws Exception {
        byte[] marker = "@project.version@"
                .getBytes(StandardCharsets.US_ASCII);
        byte[] bytes = new byte[marker.length + 5];
        bytes[0] = 0x00;
        bytes[1] = (byte) 0xFF;
        bytes[2] = (byte) 0x80;
        System.arraycopy(marker, 0, bytes, 3, marker.length);
        bytes[bytes.length - 2] = '\n';
        bytes[bytes.length - 1] = '\r';

        Path file = Path.of("src/main/resources/assets/payload.bin");
        Files.createDirectories(file.getParent());
        Files.write(file, bytes);
        System.out.println("fixture.bytes=" + bytes.length);
    }
}
~~~

Run from the root:

~~~bash
java CreateFixture.java
~~~

Exact output:

~~~text
fixture.bytes=22
~~~

Java 17 supports running a single source file directly via the source-file launcher. The payload has 3 leading bytes `00 FF 80`, the 17 ASCII bytes of `@project.version@`, and 2 trailing bytes `0A 0D`. It is engineered to expose corruption if handled as text.

### 5.5. Spring Boot Application Reading Both Resources

Create `src/main/java/demo/Application.java`:

~~~java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Properties;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    private static byte[] expectedBytes() {
        byte[] marker = "@project.version@"
                .getBytes(StandardCharsets.US_ASCII);
        byte[] result = new byte[marker.length + 5];
        result[0] = 0x00;
        result[1] = (byte) 0xFF;
        result[2] = (byte) 0x80;
        System.arraycopy(marker, 0, result, 3, marker.length);
        result[result.length - 2] = '\n';
        result[result.length - 1] = '\r';
        return result;
    }

    @Bean
    CommandLineRunner checkResources() {
        return args -> {
            Properties p = new Properties();
            try (InputStream in = Application.class
                    .getResourceAsStream("/build-info.properties")) {
                if (in == null) {
                    throw new IllegalStateException("Missing build-info");
                }
                p.load(in);
            }

            byte[] actual;
            try (InputStream in = Application.class
                    .getResourceAsStream("/assets/payload.bin")) {
                if (in == null) {
                    throw new IllegalStateException("Missing binary");
                }
                actual = in.readAllBytes();
            }

            System.out.println("build.version="
                    + p.getProperty("build.version"));
            System.out.println("runtime.placeholder="
                    + p.getProperty("runtime.placeholder"));
            System.out.println("binary.bytes=" + actual.length);
            System.out.println("binary.intact="
                    + Arrays.equals(actual, expectedBytes()));
        };
    }
}
~~~

The code uses `getResourceAsStream` to read files from the **application classpath**, including when packaged inside a Spring Boot executable JAR. `Arrays.equals` checks **every single byte**; checking only the length `22` would not be sufficient.

`Properties.load(InputStream)` uses traditional Java Properties encoding rules. The sample file contains only ASCII, so behavior is deterministic. For properties files containing Vietnamese/Unicode characters read directly with Java APIs, use an explicit encoding mechanism (such as a UTF-8 `InputStreamReader`), and do not confuse text encoding errors with binary filtering issues.

### 5.6. Building and Running

From the directory containing `pom.xml`:

~~~bash
java CreateFixture.java
mvn clean package
java -jar target/resource-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

If using a Maven Wrapper, replace `mvn` with `./mvnw` on Linux/macOS or `.\mvnw.cmd` in PowerShell.

The four lines **printed by the application itself**, in exact order, are:

~~~text
build.version=1.0.0
runtime.placeholder=${APP_RUNTIME_VALUE}
binary.bytes=22
binary.intact=true
~~~

`mvn clean package` generates its own plugin and dependency-resolution logs; those are not part of the stdout emitted by `Application`. Because the example uses only the core Spring Boot starter, no HTTP port is opened.

If `binary.intact=false`, the build may still have exited green while the resource no longer matches the source. Inspect the resource copy/filtering steps and archive packaging.

## 6. Proving Byte Preservation at Every Stage

### 6.1. Comparing Source with target/classes

After `mvn clean package`:

~~~text
src/main/resources/assets/payload.bin
target/classes/assets/payload.bin
target/classes/build-info.properties
target/resource-demo-1.0.0.jar
~~~

On Linux/macOS:

~~~bash
cmp src/main/resources/assets/payload.bin target/classes/assets/payload.bin
sha256sum src/main/resources/assets/payload.bin target/classes/assets/payload.bin
~~~

When both files are identical, `cmp` exits with status `0` and prints nothing. Both `sha256sum` lines must produce the same digest despite different file paths.

On Windows PowerShell:

~~~powershell
Get-FileHash .\src\main\resources\assets\payload.bin -Algorithm SHA256
Get-FileHash .\target\classes\assets\payload.bin -Algorithm SHA256
~~~

Compare the `Hash` property in both outputs. Hashing provides display-independent verification; even a single-byte difference changes the digest with overwhelming probability.

### 6.2. Comparing Bytes of the JAR Entry

A step after `process-resources` can still corrupt data. To verify the **final executable JAR**, create `CompareArchive.java` at the root:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class CompareArchive {
    public static void main(String[] args) throws Exception {
        Path original = Path.of(
                "src/main/resources/assets/payload.bin");
        Path archive = Path.of(
                "target/resource-demo-1.0.0.jar");
        String resource = "BOOT-INF/classes/assets/payload.bin";

        try (ZipFile zip = new ZipFile(archive.toFile())) {
            ZipEntry entry = zip.getEntry(resource);
            if (entry == null) {
                throw new IllegalStateException(
                        "Missing entry: " + resource);
            }
            try (InputStream in = zip.getInputStream(entry)) {
                byte[] source = Files.readAllBytes(original);
                byte[] packaged = in.readAllBytes();
                System.out.println("jar.binary.intact="
                        + Arrays.equals(source, packaged));
            }
        }
    }
}
~~~

Run after `mvn clean package` completes:

~~~bash
java CompareArchive.java
~~~

Exact output when preserved intact:

~~~text
jar.binary.intact=true
~~~

`ZipFile` reads the exact entry packaged under `BOOT-INF/classes`, and `Arrays.equals` compares its bytes against the source file. This is far stronger evidence than merely listing filenames with `jar tf`.

For very large files, avoid `readAllBytes` across entire artifacts; instead compute a streaming SHA-256 over both the source file and the entry stream, then compare digests. If data is **intentionally** compressed or transformed by a dedicated pipeline, QA assertions will differ and must be defined separately.

### 6.3. The First Mismatched Stage Pinpoints the Investigation

~~~text
source bytes
    |
    +--> target/classes bytes
               |
               +--> plain JAR entry
                         |
                         +--> executable JAR entry
                                     |
                                     +--> container/deploy resource
~~~

If source differs from `target/classes`, check `process-resources` and filtering config. If `target/classes` is right while the JAR entry differs, check jar/repackage/shading/assembly. If the JAR entry is right yet the app cannot read it, check the classpath lookup path, reading library, and runtime environment. Comparing stage by stage isolates the root cause instead of treating symptoms.

## 7. Maven nonFilteredFileExtensions: An Extra Safeguard

Apache Maven Resources Plugin provides the `nonFilteredFileExtensions` parameter, listing extensions that the plugin **skips during filtering** even when `<filtering>true</filtering>` is enabled on a resource entry.

Example fragment inside `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <nonFilteredFileExtensions>
            <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
            <nonFilteredFileExtension>zip</nonFilteredFileExtension>
            <nonFilteredFileExtension>bin</nonFilteredFileExtension>
            <nonFilteredFileExtension>woff2</nonFilteredFileExtension>
            <nonFilteredFileExtension>p12</nonFilteredFileExtension>
        </nonFilteredFileExtensions>
    </configuration>
</plugin>
~~~

In Maven Resources Plugin **3.3.1**, official docs list several extensions skipped by default: `jpg`, `jpeg`, `gif`, `bmp`, `png`. Do not extrapolate that **all** binary files are protected by default, or assume defaults in other plugin versions are identical.

`nonFilteredFileExtensions` has limits: it relies on file extensions and affects only the configured plugin. Files without extensions, files with uncommon extensions, custom scripts, or another `replace` step can still corrupt data. In section 5's example, we **did not need** extension guards because the binary sat in a `filtering=false` branch.

Prioritize in order: **allowlist text files → unfiltered copy for everything else → extension guards when broad filtering is unavoidable → byte verification in the final artifact**.

## 8. When Text and Binaries Share src/main/resources

A legacy project might not want to split out `src/main/resources-filtered`. In that case, use two resource declarations **pointing to the same directory**, with **non-overlapping file sets**:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>build-info.properties</include>
            </includes>
        </resource>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>build-info.properties</exclude>
            </excludes>
        </resource>
    </resources>
</build>
~~~

This is an **alternative** to the `<resources>` block in the example POM, not an XML block to paste alongside it. Move `build-info.properties` back to `src/main/resources` if using this setup. The filtered entry covers only the selected text file; the unfiltered entry covers every other file.

Avoid letting two resource entries target the same output file with different filtering modes: copy order or overwrite behavior can make the result unpredictable. With multiple text templates, expand `includes` only to exact names or narrow patterns such as `build-*.properties`, rather than `**/*`.

## 9. Spring Boot Maven Placeholders and Collision Risks

A Spring Boot `application.properties` or `application.yml` file often contains runtime expressions:

~~~properties
service.url=${SERVICE_URL:http://localhost:8080}
~~~

If Maven filtering also recognizes `${...}`, this value can be replaced wrongly at **build time**. The Spring Boot Maven parent configures resource filtering for application properties/YAML files using `@...@` delimiters to avoid colliding with Spring's `${...}` syntax.

Section 5's example makes the rule explicit:

~~~xml
<delimiters>
    <delimiter>@</delimiter>
</delimiters>
<useDefaultDelimiters>false</useDefaultDelimiters>
~~~

This means:

- `@project.version@`: Maven may substitute it at build time.
- `${SERVICE_URL:...}`: left intact for Spring Boot to resolve at runtime when that file is an application config.
- Binary files are never filtered even if they contain `@project.version@`.

If the project does not use the Spring Boot parent or uses a corporate parent, do not guess delimiters: check the effective POM and Maven Resources Plugin configuration. Never enable filtering to bake environment-specific endpoints or secrets; embedding secrets in artifacts risks leaks and forces per-environment rebuilds.

**Even text files should not be filtered blindly.** An HTML, JavaScript, or SQL template may intentionally contain `${...}`, `@...@`, or another engine's syntax. A PEM key/certificate looks like text yet altering newlines or escaping corrupts the format. Filter based on each file's explicit contract, not merely its `.txt` or `.properties` extension.

### Encoding and Escaping

For selected text files, set a consistent encoding, usually `UTF-8`. Maven Resources Plugin provides `encoding` and, in supported versions, `propertiesEncoding` for `.properties` files. `escapeString` can prevent a specific token from interpolating, though it is not a mechanism for protecting a binary directory.

If a file does not need token substitution, keeping `filtering=false` is the right approach. Regardless of the encoding chosen, running a text decoder over binary bytes is fundamentally wrong.

## 10. Gradle processResources: Same Protection Principles

The Gradle Java plugin provides the `processResources` task, which typically copies files from `src/main/resources` to `build/resources/main`. Default copying does not substitute text. Risk arises when a build script applies `expand` or `filter` to the entire task or copy spec.

**Error-prone configuration when a directory contains binaries:**

~~~groovy
tasks.named('processResources') {
    expand(project.properties)
}
~~~

`expand` evaluates file contents as Groovy templates, affecting both binaries and runtime placeholders. Never apply it across every file just because a single `build-info.properties` needs a version.

**Scoping to the right file** in `build.gradle` (Groovy DSL):

~~~groovy
version = '1.0.0'
def buildVersion = project.version.toString()

tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(version: buildVersion)
    }
}
~~~

`src/main/resources/build-info.properties` for the Gradle example uses:

~~~properties
build.version=${version}
~~~

After `./gradlew processResources`, the contents of `build/resources/main/build-info.properties` are:

~~~properties
build.version=1.0.0
~~~

`filesMatching` invokes `expand` only on the **selected text file**. Remaining binaries pass through the default byte copy path. Gradle's token syntax here is Groovy's `${version}`, differing from Maven's `@project.version@`. If a file must preserve `${...}` runtime placeholders too, escape them or separate the files; `expand` will otherwise try to evaluate undefined expressions.

With the Spring Boot Gradle plugin's `bootJar`, resource outputs usually land in `BOOT-INF/classes` of the executable JAR; still compare bytes of the final entry. If Gradle uses custom `Copy` tasks, transform plugins, or `processTestResources`, inspect the specific tasks responsible for each resource root.

## 11. Test Resources, Generated Resources, and Other Packaging Steps

- **Test resources:** `src/test/resources` in Maven/Gradle often contains binary test fixtures such as PDFs, images, or keystores. They require byte-safe copying. `testResources` or `processTestResources` settings may differ from production.
- **Generated resources:** files produced by `generate-resources` or custom tasks may be added as resources and filtered a second time. If a generated output is binary, prevent text transforms downstream of generation.
- **WAR/assembly/shading:** Spring Boot executable WARs usually place resources in `WEB-INF/classes`, while Maven WAR, shade, and assembly plugins can have their own filtering/merging rules. Inspect the actual artifact.
- **Container images:** a valid JAR does not guarantee files were copied cleanly into an image or that the container launches the right artifact. Confirm the exact artifact name and runtime path executed.
- **Runtime resource paths:** `ClassLoader.getResourceAsStream` loads resources from the classpath; `Files.readAllBytes("src/main/resources/...")` reads from the filesystem. Source folders normally do not exist on deployment hosts, so never hardcode source paths for runtime reads.

When **intentionally** transforming binaries (compression, signing, image optimization, protobuf descriptor generation), use format-aware tools or byte APIs with dedicated QA checks. `sed`, regex replacements, and text template engines are not general-purpose tools for editing archives, keystores, or class files.

## 12. Common Errors Table

| Symptom | Possible cause | Diagnostic steps |
| --- | --- | --- |
| PNG/PDF in JAR cannot be opened | Binary was filtered or a packaging step altered bytes | Compare SHA-256/bytes: source → `target/classes` → JAR entry |
| `.bin` changes size after `process-resources` | Tokens replaced or decoder/encoder altered bytes | Move file to a `filtering=false` branch; run a clean build |
| Source `.p12` keystore works, but app fails to load it | File was filtered or path/copy was wrong | Compare hashes, verify classpath lookup path and secret loading |
| `@project.version@` is not replaced | Include pattern or delimiter mismatch, or filtering disabled | Inspect POM, target path, and Resources Plugin config |
| Spring placeholder `${DB_URL}` replaced at build time | Maven/Gradle filtering is processing runtime tokens | Use separate delimiters; limit to specific text files and verify output |
| Works locally, fails in CI | Different tool/plugin versions, encoding, cache, or CI task | Print versions, effective POM/task graph, and hashes in the failing job |
| File exists in `target/classes`, missing in JAR | Packaging exclude/shade/assembly or wrong module | Run `jar tf`, find exact entry, and check the deployed archive |
| Source and class-output hashes match, JAR entry differs | `repackage` or custom packaging transformed the entry | Trace stage by stage where bytes changed |
| Text resources garble Vietnamese diacritics | Charset mismatch across filtering and runtime reading | Set UTF-8 consistently for text; verify properties reading API |
| Duplicate target file from two resource entries | Filtered/unfiltered entries overlap | Disjoint includes/excludes so two branches never write the same path |

**Do not rely on a green build or matching file sizes alone.** A single-byte change can break a signed file; two files with identical byte counts can still differ in contents. Byte equality or cryptographic hashes provide conclusive proof when preservation is the goal.

## 13. Pre-Release Verification Workflow

1. Identify which resources are true **text templates** with build-time tokens to replace.
2. Classify all remaining files as **byte-for-byte copies**, especially binaries and strict-format files.
3. In Maven, use a separate source directory or two resource entries with non-overlapping includes/excludes. In Gradle, scope `expand` with `filesMatching`.
4. Verify delimiters, encoding, and Spring runtime placeholders; never bake secrets into artifacts.
5. When broad filtering is unavoidable, add `nonFilteredFileExtensions` for your **active plugin version**, without treating it as your sole safeguard.
6. Run a clean build and check files in the output classpath.
7. Compare source and output binaries with `cmp`, `Get-FileHash`, `Files.mismatch`, or SHA-256.
8. Inspect the **exact entry** inside the packaged JAR/WAR and compare its bytes against the source file.
9. Run a smoke test confirming the application loads and uses the resource properly.
10. Add CI checks for critical binary artifacts when regression risk is significant.

### Self-Check

**Question A:** Maven built the JAR and `logo.png` appears in `jar tf`. Can you conclude the image is intact?

**Answer:** Not yet. You must compare the JAR entry bytes against the source bytes or open/parse the image format.

**Question B:** The Maven plugin skips some image extensions by default. Is `cert.p12` guaranteed to be protected?

**Answer:** No. Check the plugin version and configuration; best practice is copying it via a `filtering=false` branch.

**Question C:** Why shouldn't `<build><outputDirectory>` be used to avoid binary filtering?

**Answer:** `outputDirectory` changes where outputs are written, not the filtering mode. Update `<resources>` and `<filtering>` or include/exclude rules instead.

**Question D:** Source and `target/classes` match, yet the executable JAR entry is corrupted. Which step should you inspect?

**Answer:** Inspect `package`/`repackage`/`shade` or downstream copy tasks; compare the JAR entry bytes against the source.

**Question E:** Why is filtering only `build-info.properties` with Gradle `filesMatching` safer than applying `expand` to all of `processResources`?

**Answer:** Because transformation is scoped strictly to the chosen text file; binaries bypass the text template engine.

## 14. Official Documentation

- Maven — Guide to Filtering Resources: https://maven.apache.org/guides/mini/guide-filtering-resources.html
- Maven Resources Plugin — Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html
- Maven Resources Plugin — Binaries Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/binaries-filtering.html
- Maven Resources Plugin 3.3.1 — resources:resources parameters: https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/resources-mojo.html
- Spring Boot 3.3 — Using Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Gradle — ProcessResources task: https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html
- Gradle — CopySpec API: https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html

**Takeaway:** Apply text filtering only to explicitly selected text files. Keep binaries on a byte-safe copy path, and verify against the **resource entry actually packaged inside the archive**, not merely the source file or a green build status.
