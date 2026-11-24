# ClassPathResource in Tests and Its Limitations When Packaged

## 1. The problem: tests pass, yet the packaged application fails

In the **Spring Boot - testing** module under **Additional integration**, a common pitfall is code that reads resources from `src/main/resources` or `src/test/resources` and works in the IDE, `gradlew test`, and `bootRun`, yet fails once packaged into a Spring Boot executable JAR.

Anti-pattern:

~~~java
// ANTI-PATTERN: a physical path is not a runtime contract.
Path path = Paths.get("src/main/resources/templates/greeting.txt");
String message = Files.readString(path, StandardCharsets.UTF_8);
~~~

This relies on the *working directory* being the source repository root and the source tree still sitting alongside the running process. Inside a Docker image or when running `java -jar app.jar`, `src/main/resources` may **not exist at all**.

A subtler anti-pattern:

~~~java
// ANTI-PATTERN: may PASS during tests against build/resources/main,
// yet FAIL when the resource is packaged inside an executable JAR.
ClassPathResource resource =
        new ClassPathResource("templates/greeting.txt");
String message = Files.readString(
        resource.getFile().toPath(),
        StandardCharsets.UTF_8
);
~~~

`ClassPathResource` locates the resource on the classpath, yet `getFile()` **demands a real filesystem file**. A resource inside an unexploded JAR has no corresponding `File` path. Spring then throws `FileNotFoundException` when attempting to resolve the resource to a `File`, even though the resource **exists and is readable as a stream**.

The portable approach:

~~~java
ClassPathResource resource =
        new ClassPathResource("templates/greeting.txt");

try (InputStream input = resource.getInputStream()) {
    String message = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

This snippet requires importing `java.io.InputStream`, `java.nio.charset.StandardCharsets`, and `org.springframework.core.io.ClassPathResource`; the complete example appears below.

**Target outcomes:** distinguish `Resource` from `File`; understand test vs. main classpaths and Spring Boot JAR structure; use `getInputStream()`, `ResourceLoader`, and `@Value Resource` properly; recognize the limits of `getFile()`, `getURL()`, and `classpath*:`; write JUnit tests building a real JAR to catch bugs hidden by the IDE; and add a packaged smoke test with `bootJar` and `java -jar`.

## 2. `Resource` is an abstraction, not `java.io.File` by default

Spring Framework provides `org.springframework.core.io.Resource` to represent readable data from multiple sources.

| Resource implementation | Typically represents | Key caveat |
| --- | --- | --- |
| `ClassPathResource` | Resource located via classloader/classpath | May reside in a **directory or a JAR** |
| `FileSystemResource` | File on a real filesystem | Appropriate when the app needs a filesystem path |
| `UrlResource` | `file:`, `https:`, and supported URLs | Not every URL converts to a `File` |
| `ByteArrayResource` | In-memory byte array | Great for unit tests without I/O |
| `InputStreamResource` | An already-open stream | Usually **single-use**, not repeatable by default |
| `ServletContextResource` | Resource via `ServletContext` | Depends on web environment; not guaranteed to be a `File` |

Core `Resource` operations:

- `exists()`: checks whether the resource can be resolved; `false` for missing resources.
- `getInputStream()`: opens a stream for reading; the caller must **close** it via `try-with-resources`.
- `getURL()`: represents the resource location as a URL if supported; may be `file:`, `jar:`, or a Spring Boot classloader URL.
- `getURI()`: resource URI, **not synonymous** with a `Path` readable by the default filesystem provider.
- `getFile()`: safe only when the resource actually has a filesystem path; JAR entries typically **do not**.
- `contentLength()`: size metadata; may incur I/O, so do not assume it is always a free cached value.
- `getFilename()`, `getDescription()`: useful for diagnostics; do not prove a `File` exists.
- `createRelative(...)`: resolves a relative resource path according to that `Resource` type's rules.

Spring documentation stresses that `ClassPathResource` can be resolved to a `File` **only when the resource resides on the filesystem**, whereas resources inside a JAR are accessible via URL/stream. `getFile()` failing does not mean the JAR is corrupt.

## 3. Classpath vs. source directories and working directory

Under the standard Gradle Java layout:

~~~text
project/
  src/main/java/           Java production source
  src/main/resources/      Production resource source
  src/test/java/           Java test source
  src/test/resources/      Test-only resource source

  build/classes/java/main/
  build/resources/main/
  build/classes/java/test/
  build/resources/test/
  build/libs/
~~~

Under Gradle defaults:

- `processResources` copies `src/main/resources` to `build/resources/main`.
- `processTestResources` copies `src/test/resources` to `build/resources/test`.
- `test` runs with a classpath combining `test` source set outputs **and** required `main` outputs plus test dependencies.
- `bootJar` packages **application/main artifacts** and runtime dependencies; test sources and resources are **excluded from the default production JAR**.
- `bootRun` runs the application classpath, not the full test runtime classpath.
- `java -jar ...` loads resources from the executable archive via Spring Boot's loader without needing the source tree.

Consequences:

| Resource | `gradlew test` | `gradlew bootRun` | `java -jar bootJar` |
| --- | --- | --- | --- |
| `src/main/resources/templates/greeting.txt` | Present | Present | Present, under `BOOT-INF/classes` |
| `src/test/resources/fixtures/test-only.txt` | **Present** | **Absent by default** | **Absent by default** |
| `src/main/resources/com/example/.../anchored.txt` | Present | Present | Present |
| External file referenced by absolute path | Machine-dependent | Machine-dependent | Deployment/mount-dependent |

If a Spring Boot test **only succeeds because it reads a test fixture**, never assume production can read it. Conversely, if the test classpath shadows a same-named resource from `main` or a dependency, the packaged app may resolve a different resource.

## 4. Spring Boot executable JAR changes the physical layout

A standard Spring Boot executable JAR has the layout:

~~~text
portable-resources-demo-0.0.1-SNAPSHOT.jar
  META-INF/
    MANIFEST.MF
  org/springframework/boot/loader/...
  BOOT-INF/
    classes/
      com/example/portable/ResourceApp.class
      com/example/portable/ResourceReader.class
      templates/greeting.txt
      com/example/portable/anchored.txt
    lib/
      spring-core-...jar
      spring-boot-...jar
      ...
~~~

This is an **illustrative layout**; dependency JAR filenames under `BOOT-INF/lib` vary by version. Libraries are stored as **nested JARs**, not always unpacked into real directories. Spring Boot's loader builds a classloader capable of loading classes and resources from this packaging format.

The logical resource name remains:

~~~text
templates/greeting.txt
~~~

**Not**:

~~~text
src/main/resources/templates/greeting.txt
BOOT-INF/classes/templates/greeting.txt
~~~

when calling `new ClassPathResource(...)`. The `BOOT-INF/classes` prefix is an **internal archive layout**, not part of the logical classpath path passed by application code.

**Rule:** test classpath resources via `Resource.getInputStream()` instead of computing `File` paths from the executable JAR's physical location. Never open the application's own JAR to manually extract entries just to read a line of text; the classloader already handles that.

## 5. Comparing `getInputStream`, `getURL`, and `getFile`

| API | Test on expanded directory | Test with plain JAR | Spring Boot executable JAR |
| --- | --- | --- | --- |
| `resource.exists()` | May be true | May be true | May be true |
| `resource.getInputStream()` | **Readable** | **Readable** | **Readable** with Boot's loader |
| `resource.getURL()` | `file:...` URL | `jar:...` URL | Boot-aware URL; scheme/layout may be special |
| `resource.getFile()` | Usually works | **Fails** while entry stays in JAR | **Fails** for unexploded JAR entries |
| `Files.readString(resource.getFile().toPath())` | May work | **Error** | **Error** |
| `Paths.get(resource.getURI())` | Works for `file:` URI | Cannot assume FS path | Not portable |
| `new File(resource.getURL().getFile())` | May work by accident | Broken for `jar:` and encoded URLs | Not portable |

`ClassPathResource#getFile()` is **not** safe simply because Gradle tests currently pass. Once packaged into a JAR, the resource URL becomes archive-backed and resolving it to a `File` fails.

Regarding `getURL()`: it is useful when calling APIs that accept a `URL`, but **never** call `new File(url.getPath())`. Spaces and Unicode characters may be URL-encoded, and `jar:...!/entry` URLs are not filesystem paths. For native filesystem APIs requiring a `Path`, copy the resource to a temporary file first.

## 6. Two right ways to read: `InputStream` and `ResourceLoader`

**First approach — `ClassPathResource` directly:**

~~~java
Resource resource = new ClassPathResource(
        "templates/greeting.txt"
);

try (InputStream in = resource.getInputStream()) {
    return new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

This snippet belongs inside a method returning `String` with matching imports. Identical code works on both expanded classpaths and packaged JARs.

**Second approach — `ResourceLoader` with Spring location prefixes:**

~~~java
Resource resource =
        resourceLoader.getResource(
                "classpath:templates/greeting.txt"
        );

try (InputStream in = resource.getInputStream()) {
    return new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

In this snippet, `resourceLoader` has type `org.springframework.core.io.ResourceLoader`. `classpath:` is a **classpath location prefix**, not a literal directory name.

**Third approach — injecting a `Resource` via `@Value`:**

~~~java
@Value("classpath:templates/greeting.txt")
private Resource greeting;
~~~

This field snippet requires `@Value` and `Resource` imports on a Spring-managed bean. `@Value`/`ResourceLoader` decouple source code from physical path details; never inject a `String` path and coerce it to a `File` when the abstraction already fits.

### Closing streams is mandatory

`getInputStream()` opens a stream that must be closed. For large files, `readAllBytes()` is inappropriate because it buffers everything on the heap; use `BufferedReader`, `InputStream.transferTo`, or a streaming parser instead. For images, ZIPs, PDFs, or binary files, never convert arbitrary bytes into a `String` via a charset.

## 7. Root paths, `ClassLoader`, and class-relative paths

`ClassPathResource` offers several constructors:

~~~java
new ClassPathResource("templates/greeting.txt");
new ClassPathResource("/templates/greeting.txt");
new ClassPathResource(
        "templates/greeting.txt",
        someClassLoader
);
new ClassPathResource(
        "anchored.txt",
        ResourceReader.class
);
~~~

These are illustrative expressions assuming appropriate variables and types. Note the differences:

1. Passing a `ClassLoader` resolves paths from the **classpath root**, and any leading slash is stripped.
2. Passing a `Class<?>` with a path **without a leading slash** resolves relative to **that class's package**.
3. Passing a `Class<?>` with a path starting with `/` resolves from the **classpath root**.
4. `ClassPathResource` does not take OS filesystem paths; always use `/` in logical classpath paths on every OS, including Windows.

For example, `ResourceReader.class` is in package `com.example.portable`. With the file:

~~~text
src/main/resources/com/example/portable/anchored.txt
~~~

then:

~~~java
new ClassPathResource("anchored.txt", ResourceReader.class);
~~~

locates that exact file. Meanwhile:

~~~java
new ClassPathResource("templates/greeting.txt", ResourceReader.class);
~~~

looks for `com/example/portable/templates/greeting.txt`, **not** `templates/greeting.txt` at the root.

Tests should verify path resolution matching the actual constructor used. Other common bugs include passing Windows backslashes `\\` or prepending `src/main/resources` to the logical name.

## 8. Test-only resources: never ship fixtures to production

`src/test/resources` is the right home for:

- JSON/XML/CSV fixtures for specific test cases.
- Input files simulating malformed payloads.
- **Test-only** truststores/certificates (never production keys or secrets).
- Versioned snapshots managed by tests.
- Golden files that application runtime does **not** need.

`src/main/resources` is for:

- Templates and default configs needed at runtime.
- Static assets served by the application.
- Localization bundles; schema/migration scripts if part of the runtime contract.
- Resources that must exist inside the executable artifact.

A test successfully reading `fixtures/test-only.txt` only proves it sits on the **test runtime classpath**. Never make a production service depend on it without moving the asset to `src/main/resources` or configuring an external filesystem resource.

**Security warning:** test resources are excluded from `bootJar` by default, yet that does not make them a safe place for production credentials; CI artifacts and source control can still expose them. Never place real tokens or passwords in either main or test resources.

## 9. A runnable project testing both test classpath and packaged JAR

The sample project uses **Java 17 / Spring Boot 3.5.16 / Gradle Groovy DSL**. Boot 3.5.16 is chosen as a consistent illustrative version; for new production apps, pick a supported Spring Boot line matching your organization's upgrade policy.

Exact directory layout:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/portable/
    ResourceApp.java
    ResourceReader.java
src/main/resources/
    templates/greeting.txt
    com/example/portable/anchored.txt
src/test/java/com/example/portable/
    ResourceReaderTest.java
    ResourceAppSmokeTest.java
src/test/resources/
    fixtures/test-only.txt
~~~

**Test scope:**

- `ResourceReaderTest`: unit tests with main/test resources, a real file in `@TempDir`, and a **JAR created on the fly inside the test** proving streams work while `getFile()` fails.
- `ResourceAppSmokeTest`: Spring integration test verifying `@Value("classpath:...")` and `ResourceLoader`.
- `java -jar`: packaged smoke test printing `MAIN_RESOURCE=...` and `TEST_ONLY_PRESENT=false`, proving main assets remain readable without the source tree.

No web server, database, Docker, broker, or external network is needed at runtime. Gradle may need network access on the first run to fetch dependencies.

## 10. `settings.gradle` and `build.gradle`

**`settings.gradle`:**

~~~groovy
rootProject.name = 'portable-resources-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` brings in Spring Core `Resource` and minimal auto-configuration; `spring-boot-starter-test` brings in JUnit Jupiter and AssertJ. Java 17 includes `InputStream.readAllBytes()`, `StandardCharsets.UTF_8`, and JUnit `@TempDir`.

Gradle produces both a plain `jar` and a `bootJar` under the Boot plugin; the **executable JAR** used for packaging verification is the `bootJar` output, not a thin/plain JAR missing dependencies.

## 11. `ResourceApp`: running and printing packaged resource signals

**`src/main/java/com/example/portable/ResourceApp.java`:**

~~~java
package com.example.portable;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

@SpringBootApplication
public class ResourceApp {

    public static void main(String[] args) {
        SpringApplication.run(ResourceApp.class, args);
    }

    @Bean
    ApplicationRunner printResourceProbe(
            ResourceReader reader
    ) {
        return args -> {
            Resource main = new ClassPathResource(
                    "templates/greeting.txt"
            );

            System.out.println(
                    "MAIN_RESOURCE="
                    + reader.readUtf8(main).strip()
            );
            System.out.println(
                    "TEST_ONLY_PRESENT="
                    + new ClassPathResource(
                            "fixtures/test-only.txt"
                    ).exists()
            );
        };
    }
}
~~~

Here `ApplicationRunner` runs after the Spring Boot application context is ready. It reads the **main resource via stream**, not `getFile()`. Printing the test-only fixture check is solely for learning about **classpath visibility**, not production logic to keep.

When launching the app from the **executable JAR** built with default configuration, expect these two lines:

~~~text
MAIN_RESOURCE=Hello from main
TEST_ONLY_PRESENT=false
~~~

Spring Boot may print banners or startup logs before or after those lines, so **never** claim this is the entire stdout. During `@SpringBootTest`, `TEST_ONLY_PRESENT` may be `true` because the test runtime classpath includes `src/test/resources`. Do not assert on test console output to prove packaged behavior.

**If the main resource is missing:** `getInputStream()` throws an exception and `ApplicationRunner` aborts startup. Failing fast is far better than silently picking up a file from the working directory outside the package.

## 12. `ResourceReader`: a portable reader service

**`src/main/java/com/example/portable/ResourceReader.java`:**

~~~java
package com.example.portable;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class ResourceReader {

    public String readUtf8(Resource resource)
            throws IOException {
        try (InputStream stream = resource.getInputStream()) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }

    public String readClasspath(String classpathPath)
            throws IOException {
        return readUtf8(
                new ClassPathResource(classpathPath)
        );
    }
}
~~~

This class is **complete and independent of filesystem paths**. Passing any `Resource` works across `ClassPathResource`, `FileSystemResource`, `ByteArrayResource`, and any implementation returning an input stream.

Usage:

~~~java
String text = reader.readClasspath(
        "templates/greeting.txt"
);
~~~

This snippet runs inside a method with `reader` of type `ResourceReader`. Remember that `classpathPath` must be a **contract-controlled path**—never feed untrusted HTTP user input directly into it to avoid unintended disclosure of sensitive classpath resources.

### Why not decode Strings using the default encoding?

`new String(bytes)` and `FileReader` without an explicit encoding depend on the runtime's default charset (especially across platforms on Java 17). The example uses `StandardCharsets.UTF_8` to preserve Unicode consistently across CI runners and developer machines.

`readAllBytes()` fits **small** text resources only. For images, ZIPs, PDFs, or large files, use streaming APIs and never turn binary payloads into Strings.

## 13. Resource contents in `src/main/resources`

**`src/main/resources/templates/greeting.txt`:**

~~~text
Hello from main
~~~

**`src/main/resources/com/example/portable/anchored.txt`:**

~~~text
Package-anchored resource
~~~

In `templates/greeting.txt`, any trailing newline added by an editor is removed via `.strip()` before assertions/display. Never rely on IDE LF/CRLF differences to conclude resource content differs; when byte-for-byte output is part of the contract, assert bytes/charset and normalize fixtures.

Keep logical resource paths using `/` and simple lowercase filenames to avoid case-sensitivity discrepancies between Windows and Linux. For example, `Templates/Greeting.txt` might resolve on a case-insensitive IDE filesystem yet FAIL inside a case-sensitive JAR entry lookup.

## 14. Test-only fixture content

**`src/test/resources/fixtures/test-only.txt`:**

~~~text
Test-only fixture
~~~

The test runtime classpath finds `fixtures/test-only.txt`, whereas `bootJar` under default settings does not package it.

If a production service genuinely needs `fixtures/test-only.txt`, revisit the requirement: either it is a **runtime asset** belonging in main resources, or it is **external config/data** that should be provided via mounted paths, a database, or object storage. Never copy all test resources into `BOOT-INF/classes` as a "fix" without auditing fixture contents and sensitive data.

## 15. Unit tests: classpath root, package anchor, and missing files

**`src/test/java/com/example/portable/ResourceReaderTest.java`:**

~~~java
package com.example.portable;

import java.io.FileNotFoundException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ResourceReaderTest {

    private final ResourceReader reader =
            new ResourceReader();

    @Test
    void mainClasspathResourceCanBeReadAsUtf8()
            throws Exception {
        String text = reader.readClasspath(
                "templates/greeting.txt"
        );
        assertThat(text.strip())
                .isEqualTo("Hello from main");
    }

    @Test
    void testOnlyFixtureIsVisibleInTestRuntime()
            throws Exception {
        String text = reader.readUtf8(
                new ClassPathResource(
                        "fixtures/test-only.txt"
                )
        );
        assertThat(text.strip())
                .isEqualTo("Test-only fixture");
    }

    @Test
    void leadingSlashWithClassLoaderIsRootRelative()
            throws Exception {
        ClassPathResource resource =
                new ClassPathResource(
                        "/templates/greeting.txt"
                );

        assertThat(resource.exists()).isTrue();
        assertThat(reader.readUtf8(resource).strip())
                .isEqualTo("Hello from main");
    }

    @Test
    void classRelativePathUsesTheClassPackage()
            throws Exception {
        ClassPathResource anchored =
                new ClassPathResource(
                        "anchored.txt",
                        ResourceReader.class
                );

        ClassPathResource root =
                new ClassPathResource(
                        "/templates/greeting.txt",
                        ResourceReader.class
                );

        ClassPathResource wrongRelative =
                new ClassPathResource(
                        "templates/greeting.txt",
                        ResourceReader.class
                );

        assertThat(anchored.exists()).isTrue();
        assertThat(reader.readUtf8(anchored).strip())
                .isEqualTo("Package-anchored resource");

        assertThat(root.exists()).isTrue();
        assertThat(reader.readUtf8(root).strip())
                .isEqualTo("Hello from main");

        assertThat(wrongRelative.exists()).isFalse();
    }

    @Test
    void missingClasspathResourceIsNotTheSameAsMissingFile()
            throws Exception {
        ClassPathResource missing =
                new ClassPathResource(
                        "missing/unknown.txt"
                );

        assertThat(missing.exists()).isFalse();
        assertThatThrownBy(
                () -> missing.getInputStream()
        ).isInstanceOf(FileNotFoundException.class);
    }

    @Test
    void realFileSystemResourceSupportsFilePath(
            @TempDir Path temp
    ) throws Exception {
        Path file = temp.resolve("on-disk.txt");
        Files.writeString(
                file,
                "On the filesystem",
                StandardCharsets.UTF_8
        );

        FileSystemResource resource =
                new FileSystemResource(file);

        assertThat(resource.exists()).isTrue();
        assertThat(resource.getFile().toPath())
                .isEqualTo(file);

        assertThat(reader.readUtf8(resource))
                .isEqualTo("On the filesystem");
    }

    @Test
    void jarEntrySupportsInputStreamButNotGetFile(
            @TempDir Path temp
    ) throws Exception {
        Path jarFile = temp.resolve("demo-fixture.jar");

        // Create a real JAR containing a single text entry.
        try (JarOutputStream jar =
                     new JarOutputStream(
                             Files.newOutputStream(jarFile)
                     )) {
            jar.putNextEntry(
                    new JarEntry("packed/inside.txt")
            );
            jar.write(
                    "Content inside JAR".getBytes(
                            StandardCharsets.UTF_8
                    )
            );
            jar.closeEntry();
        }

        // Use only that JAR as the classpath for the resource.
        try (URLClassLoader isolatedLoader =
                     new URLClassLoader(
                             new URL[] {
                                     jarFile.toUri().toURL()
                             },
                             null
                     )) {
            ClassPathResource resource =
                    new ClassPathResource(
                            "packed/inside.txt",
                            isolatedLoader
                    );

            assertThat(resource.exists()).isTrue();
            assertThat(reader.readUtf8(resource))
                    .isEqualTo("Content inside JAR");

            // The resource still exists, yet there is no
            // filesystem file for an entry inside a JAR.
            assertThatThrownBy(
                    () -> resource.getFile()
            ).isInstanceOf(FileNotFoundException.class);
        }
    }
}
~~~

### What do these tests actually prove?

- **Tests 1–3:** main and test resources sit on the test classpath and decode as UTF-8; a leading slash with the `ClassLoader` constructor still resolves from the logical root.
- **Test 4:** the `Class<?>` constructor distinguishes package-relative from classpath-root paths.
- **Test 5:** missing resources report `exists=false` and throw `FileNotFoundException` on `getInputStream`.
- **Test 6:** `FileSystemResource` for a real `@TempDir` file returns a `File`.
- **Test 7:** builds a **plain JAR** right inside JUnit and loads the entry via `URLClassLoader`; **streaming succeeds while `getFile()` throws `FileNotFoundException`**.

Test 7 is the centerpiece: it prevents **IDE/Gradle runs from hiding the bug** where `ClassPathResource.getFile()` accidentally works on expanded directories. It needs no Docker or production JAR to prove the fundamental archive-resource rule.

**Limitation:** Test 7 uses a JDK plain JAR and `URLClassLoader`. A Spring Boot executable JAR uses a **nested JAR classloader**; hence the packaged `bootJar` smoke test below is still needed. Do not treat a plain JAR test alone as covering every behavior of Boot's loader across all deployment layouts.

## 16. Spring integration test: `@Value Resource` and `ResourceLoader`

**`src/test/java/com/example/portable/ResourceAppSmokeTest.java`:**

~~~java
package com.example.portable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ResourceApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ResourceAppSmokeTest {

    @Autowired
    ResourceReader reader;

    @Autowired
    ResourceLoader resourceLoader;

    @Value("classpath:templates/greeting.txt")
    Resource greeting;

    @Test
    void springInjectsResourceFromClasspathLocation()
            throws Exception {
        assertThat(greeting.exists()).isTrue();
        assertThat(reader.readUtf8(greeting).strip())
                .isEqualTo("Hello from main");
    }

    @Test
    void resourceLoaderReadsWithoutAssumingFileSystem()
            throws Exception {
        Resource resolved = resourceLoader.getResource(
                "classpath:templates/greeting.txt"
        );

        assertThat(resolved.exists()).isTrue();
        assertThat(reader.readUtf8(resolved).strip())
                .isEqualTo("Hello from main");

        assertThat(new ClassPathResource(
                "fixtures/test-only.txt"
        ).exists()).isTrue();
    }
}
~~~

These two Spring integration cases verify:

1. `ResourceReader` is Spring-managed; `@Value("classpath:...")` resolves to a `Resource`.
2. `ResourceLoader` understands the `classpath:` prefix.
3. During **test runtime**, fixtures from `src/test/resources` are visible—expected in tests, not in the executable JAR.

`ResourceApp` runs an `ApplicationRunner` that prints probes on context startup, so during `@SpringBootTest` you may see `TEST_ONLY_PRESENT=true`. That does not contradict `TEST_ONLY_PRESENT=false` under `java -jar`; the two runs use different classpaths.

There are **9 JUnit test methods** total: 7 in `ResourceReaderTest` and 2 in `ResourceAppSmokeTest`. The suite never asserts a filesystem path on `ClassPathResource`; it tests `FileSystemResource.getFile` only for files created in `@TempDir`.

## 17. Packaging and verifying with `bootJar`

From the project directory with Gradle Wrapper and JDK 17+:

~~~bash
./gradlew clean test bootJar
~~~

The build succeeds when all nine tests PASS and the executable JAR is created. Afterward, run:

~~~bash
java -jar build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

Lesson-relevant output (amid Spring Boot logs):

~~~text
MAIN_RESOURCE=Hello from main
TEST_ONLY_PRESENT=false
~~~

This output is **expected based on source** and source-set rules, not real stdout collected while authoring the article. Nothing in the code requires extra CLI flags or environment variables.

### Inspecting archive contents with `jar tf`

~~~bash
jar tf build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

Look for entries:

~~~text
BOOT-INF/classes/templates/greeting.txt
BOOT-INF/classes/com/example/portable/anchored.txt
~~~

**Should NOT appear**:

~~~text
BOOT-INF/classes/fixtures/test-only.txt
~~~

Do not assert entry ordering in `jar tf` or exact dependency filenames in `BOOT-INF/lib` unless required by contract. `bootJar` may sort or make archive layouts reproducible per Gradle/Boot settings.

### PowerShell on Windows

~~~powershell
.\gradlew.bat clean test bootJar

java -jar .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar

jar tf .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar |
    Select-String "BOOT-INF/classes/(templates/greeting.txt|fixtures/test-only.txt)"
~~~

`Select-String` shows the main entry is packaged while the test-only fixture is absent. To automate the absence check in CI, read the `jar tf` output and assert it **does not** contain `fixtures/test-only.txt`; visual grepping alone is not an automated assertion.

**Never claim** `./gradlew test` alone tests the packaged JAR. Test runtimes normally use exploded directories; `bootJar + java -jar` exercises actual executable archive behavior.

## 18. Key differences between `test`, `bootRun`, and `java -jar`

| Property | `gradlew test` | `gradlew bootRun` | `java -jar` |
| --- | --- | --- | --- |
| Runtime classpath | `main` + `test` outputs/deps | Typically `main` runtime classpath | Spring Boot executable archive |
| Main resources | Present | Present | Present |
| Test resources | **Present** | Absent by default | Absent by default |
| Physical classpath resource | Usually `build/resources` directories | Usually `build/resources` directories | `BOOT-INF/classes` inside JAR |
| `ClassPathResource.getFile` | May PASS | May PASS | Typically **FAILS** on JAR entries |
| `Resource.getInputStream` | PASSES if asset exists | PASSES if asset exists | PASSES if packaged/loaded properly |
| Working directory | Per test task/IDE | Per Gradle run | Per command/service/container |
| URL scheme | Usually `file:` | Usually `file:` | Archive-aware URL; do not force into `File` |
| Verifies test-only resources excluded | **No** | Observable | **Yes** |

This table describes **defaults** and does not apply when projects customize source sets, shadow JARs, exploded layers, `bootRun.classpath`, or manually copy fixtures into runtime artifacts. With custom builds, use `jar tf` and packaged smoke tests to confirm actual packaging.

## 19. What if a legacy API strictly requires a `File` or `Path`?

Some legacy libraries accept only `File` or `Path` rather than `InputStream`/`Reader`. **Never blindly call `getFile()` on a classpath resource.** Two better options:

1. **Prefer changing the adapter** so the library accepts `InputStream` or `Resource` if its API supports it.
2. When a `File` is unavoidable, **copy the resource to a temporary file or managed working directory**, then pass the materialized `Path`/`File`.

**Standalone** helper example:

~~~java
package com.example.portable;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.core.io.Resource;

public final class ResourceMaterializer {

    private ResourceMaterializer() {
    }

    public static Path copyToTempFile(
            Resource resource,
            String prefix,
            String suffix
    ) throws IOException {
        Path temp = Files.createTempFile(prefix, suffix);

        boolean ok = false;
        try (InputStream in = resource.getInputStream()) {
            Files.copy(
                    in,
                    temp,
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING
            );
            ok = true;
            return temp;
        } finally {
            if (!ok) {
                Files.deleteIfExists(temp);
            }
        }
    }
}
~~~

This is an **optional class** you can add when integrating a legacy library; it is not required to run the 9 main tests. The caller owns cleanup:

~~~java
Path temp = ResourceMaterializer.copyToTempFile(
        new ClassPathResource("templates/greeting.txt"),
        "greeting-",
        ".txt"
);
try {
    // Pass temp.toFile() to an API that strictly requires File.
} finally {
    Files.deleteIfExists(temp);
}
~~~

This is a **usage snippet** assuming proper imports and a real library call in production code. In tests, prefer `@TempDir` so JUnit handles cleanup. Production code must manage size limits, disk space, permissions, lifecycles, and crashes rather than leaking temp files forever.

**Never write back** to resources inside a JAR. Packaged resources must be treated as **read-only**; mutable runtime data belongs in an external filesystem, volume, database, or object storage.

## 20. `ResourceLoader` and dependency injection make tests flexible

When a service depends on a template, inject `Resource` to make unit testing straightforward:

~~~java
public final class TemplateService {
    private final Resource template;

    public TemplateService(Resource template) {
        this.template = template;
    }

    public String load() throws IOException {
        try (InputStream in = template.getInputStream()) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

This is an illustrative skeleton needing `Resource`, `InputStream`, `IOException`, and `StandardCharsets` imports. Unit tests can pass `new ByteArrayResource("hello".getBytes(UTF_8))` without booting Spring or creating real files.

Production wiring can inject:

~~~java
@Bean
TemplateService templateService(
        @Value("classpath:templates/greeting.txt")
        Resource resource
) {
    return new TemplateService(resource);
}
~~~

This is an illustrative `@Bean` method needing imports. Tests using `ByteArrayResource` verify business logic; integration tests with `ClassPathResource` verify wiring/paths; packaged smoke tests verify the asset actually ships in the JAR. Each layer catches a different class of defects.

**Note:** `ByteArrayResource` and `ClassPathResource` both implement `Resource`, yet neither guarantees `getFile()` works; avoid assuming a `File` path inside consumers of the interface.

## 21. Classpath patterns: `classpath:` vs. `classpath*:`

`ClassPathResource` resolves **a single logical location**, not a wildcard scanner for `*.json`. To gather multiple resources matching a pattern across JARs and classpath roots, use Spring's `ResourcePatternResolver`.

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] rules = resolver.getResources(
        "classpath*:rules/*.json"
);

for (Resource rule : rules) {
    try (InputStream in = rule.getInputStream()) {
        // Parse JSON from the stream.
    }
}
~~~

This is an illustrative snippet, not a runnable project file; required imports:

~~~java
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
~~~

Distinction:

- `classpath:rules/example.json`: a single classpath location, usually picking the first matching resource.
- `classpath*:rules/example.json`: finds **all matching classpath locations** where supported by the resolver, useful when multiple JARs provide the same path.
- `classpath*:rules/*.json`: pattern scan across multiple files, though scanning JAR/directory roots, classloaders, and module paths has caveats documented by Spring.
- `new ClassPathResource("rules/*.json")`: does **not** scan files; it looks up the literal path.

**Do not list "files in a resource directory" via `getFile().listFiles()`.** Once packaged in a JAR, directory entries are not necessarily OS directories. When listing files is a strict contract, use `ResourcePatternResolver` backed by real JAR tests, or package an explicit resource index/manifest for reliable lookup.

## 22. Duplicate resource names across JARs and classloader order

The classpath may contain:

~~~text
dependency-a.jar!/config/defaults.properties
dependency-b.jar!/config/defaults.properties
BOOT-INF/classes/config/defaults.properties
~~~

`new ClassPathResource("config/defaults.properties")` normally returns **one** resource chosen by the active classloader's lookup order. Never assume it always resolves from JAR A, JAR B, or the application if resource paths collide and classpath ordering shifts between the IDE, `bootRun`, and `java -jar`.

When merging multiple sources:

- Use library-specific namespaces such as `META-INF/my-library/rules.json`.
- Use `ResourcePatternResolver` with `classpath*:` when you truly must collect multiple resources.
- Define an explicit ordering/override policy and sort deterministically before merging when order matters.
- Test with resources packaged inside dependency JARs too.
- Never log secrets from resources just to debug classloader paths.

`ClassLoader#getResource` returns the first URL, while `getResources` enumerates multiple URLs. Enumeration order and classpath ordering are loader/runtime details; **never rely on accidental ordering as a business contract**.

## 23. Why passing unit tests still fail to guarantee packaged runtime

Checklist of causes:

1. **Resource is in test runtime, missing from main JAR.** Cause: misplaced in `src/test/resources`.
2. **`getFile()` works because Gradle copies files to a directory.** Cause: code depends on `File` instead of streams.
3. **`src/main/resources/...` path works in the repo.** Cause: working directory / source tree is still present.
4. **Classpath resource collides with a dependency.** Cause: classpath order changes when packaged.
5. **Case mismatch** (`File.txt` vs. `file.txt`). Cause: Windows/macOS filesystems are often case-insensitive while JARs/Linux are case-sensitive.
6. **File contains Unicode** while code reads with default charset. Cause: OS/JVM default encodings differ.
7. **JAR layout changes** from expanded/layered to nested, breaking code that parses URL strings into `File`.
8. **Absolute filesystem path hardcoded in config** without a mount in the container.
9. **Writing runtime files under the classpath** in local dev; JAR resources are read-only and unwriteable.
10. **`@SpringBootTest` still sees test fixtures**, masking production code reading an unshipped asset.

Therefore, gather **three layers of evidence**:

| Layer | What it verifies | Example |
| --- | --- | --- |
| Unit test | Resource parsing/reading and stream semantics | `ResourceReaderTest`, jar-only test |
| Spring wiring test | `@Value Resource`, `ResourceLoader`, classpath roots | `ResourceAppSmokeTest` |
| Packaged smoke test | App runs via `java -jar`, main asset present, test-only fixture absent | `bootJar` + CLI |

A JUnit test building a plain JAR is very helpful, yet **does not replace** an executable archive smoke test when deploying via Docker, OCI layers, or custom classloaders.

## 24. Diagnosing `getFile` / missing resource errors

| Error or symptom | Common cause | Fix |
| --- | --- | --- |
| `FileNotFoundException ... cannot be resolved to absolute file path` | Resource is an entry inside a JAR | Use `getInputStream()`, not `getFile()` |
| `FileNotFoundException ... does not exist` | Wrong logical path or asset missing from classpath | Check path, source set, `jar tf` |
| `exists=true` yet `getFile` FAILS | No filesystem path even though stream is readable | Normal behavior for JAR resources |
| IDE PASSES, `java -jar` FAILS | Uses `src/main/resources` path or `getFile` | Streams + packaged smoke test |
| Test PASSES, production missing fixture | File exists only in `src/test/resources` | Move to main resources or external config |
| Resource exists in `BOOT-INF/classes`, lookup fails | Passed `BOOT-INF/classes` prefix to logical path | Use root-relative `templates/...` |
| Path with `\\` on Windows | Passed OS path as classpath name | Use `/` in classpath paths |
| Wrong casing in resource name | FS vs. JAR/Linux case sensitivity | Normalize casing, test on Linux/JAR |
| Vietnamese/Unicode bytes corrupted | Read with default charset | Explicit UTF-8 |
| `NoSuchFileException` in container | File lives on host, not mounted in container | Explicit volume/path config |
| `Paths.get(jarUri)` fails | URI not backed by default filesystem provider | Read via stream |
| `new File(url.getFile())` contains `%20` | URL-encoded or `jar:` scheme | Do not convert URLs to `File` manually |
| `getFile().listFiles()` returns null/fails after packaging | No filesystem directory for JAR entries | `ResourcePatternResolver` or manifest |
| Duplicate resource in two dependencies | Classloader picks one by lookup order | Namespace or `classpath*:` + merge policy |
| Test writes under resources, missing in prod | JAR resources are not writable storage | Use external directory or DB |
| Large file causes `OutOfMemoryError` | `readAllBytes()` on oversized resource | Stream / `BufferedReader` |
| Spring context fails to load required resource | File absent from packaged classpath | Check path, imports, build outputs |
| Custom build omits resources | Customized `processResources`/`sourceSets` | Inspect tasks, outputs, `jar tf` |
| Test matches fixture yet serves wrong locale | Wrong classpath path or charset | Organize locale files, test lookup |
| Different classloader in plugin/app server | TCCL vs. class-anchored loader differs | Pass explicit loader when needed, test target runtime |

Never "fix" `FileNotFoundException` from `getFile()` by catching it and falling back to a hardcoded absolute path on a developer's machine. That destroys portability. Only convert to `File` when a library genuinely demands a filesystem file, materializing a managed temporary file.

## 25. Resources in containers/Docker and native images

### Docker with executable JAR

Suppose a Docker image contains:

~~~text
/app/app.jar
~~~

A resource at `BOOT-INF/classes/templates/greeting.txt` is still read via the classloader even with no `/app/src/main/resources` or `/app/BOOT-INF/classes` directory on disk.

If the application needs to read **files modified after deployment**, such as `/etc/my-service/templates/greeting.txt`, configure a `FileSystemResource` or `UrlResource` pointing at a volume mount instead of packaging the resource and attempting to overwrite it.

Example splitting location via configuration:

~~~properties
app.template-location=classpath:templates/greeting.txt
~~~

And in Spring-managed code:

~~~java
public TemplateService(
        ResourceLoader loader,
        @Value("${app.template-location}")
        String location
) {
    this.template = loader.getResource(location);
}
~~~

This constructor snippet assumes `Resource template`, imports, and a service class. Production deployments can override it with `app.template-location=file:/etc/my-service/greeting.txt`. Tests should cover both the default classpath location and an optional mounted external location.

**Security:** never let user requests supply arbitrary `file:///etc/...` or internal classpath paths without allowlists and authorization; `ResourceLoader` is a powerful abstraction, not a security filter.

### Native images and AOT

Native images do not automatically embed **all** arbitrary classpath resources the way a JVM/JAR does. When building a GraalVM native image, supply resource hints/metadata so resources are included if not auto-detected by the framework. Spring Boot provides AOT resource hints and `RuntimeHints`.

Illustrative snippet:

~~~java
hints.resources().registerPattern(
        "templates/greeting.txt"
);
~~~

This snippet lives inside `RuntimeHintsRegistrar.registerHints(...)` with an appropriate `hints` parameter; it is **not** part of the runnable project. If shipping a native executable, add dedicated native build and smoke tests rather than treating `bootJar` results as proof of native-image inclusion.

## 26. Verifying packaging when resources come from dependencies

In starters or third-party libraries, resources may reside in `some-library.jar` under `BOOT-INF/lib` rather than the app's `BOOT-INF/classes`. Spring Boot's loader still resolves them through the appropriate classloader.

Scenarios worth testing:

- Asset lives in the **library's** `src/main/resources` and is packaged into the library JAR before consumption.
- App and library share an identical logical resource name.
- Resource filtering/copying runs during `processResources`; verify build-time placeholders were expanded.
- Library test source set holds fixtures that the published JAR excludes.
- Library resources live in a folder-like path requiring `classpath*:` pattern scanning.
- Upgrading Boot Loader or changing Docker layering preserves stream lookup.

Never hardcode `BOOT-INF/lib/library.jar!/path` in business code. That is an internal layout, not a `Resource` contract; use logical classpath paths and test from the packaged artifact.

## 27. Review checklist: Java 17 + Spring Boot resource tests

- [ ] Are all runtime assets placed in `src/main/resources` or external storage?
- [ ] Are test-only fixtures kept in `src/test/resources` and unreferenced by production code?
- [ ] Does code accept logical classpath paths instead of joining `src/main/resources` as an OS path?
- [ ] Does code avoid `ClassPathResource.getFile()` just to read bytes or text?
- [ ] Is every stream from `getInputStream()` closed via `try-with-resources`?
- [ ] Is text decoded with an explicit charset, preferring UTF-8?
- [ ] Are binary/large resources streamed rather than loaded blindly with `readAllBytes`?
- [ ] Do `Class<?>` constructors properly distinguish package-relative vs. leading-slash root paths?
- [ ] Are `ClassLoader`/TCCL handled accurately when custom loaders are involved?
- [ ] Are `ResourceLoader` or `@Value Resource` used instead of assuming `File` paths?
- [ ] When a real file is required, is `FileSystemResource` or a copy into `@TempDir`/managed temp used?
- [ ] Are JAR-packaged resources tested with `URLClassLoader` and `JarOutputStream`?
- [ ] Is there a Spring context smoke test for `@Value` and `ResourceLoader`?
- [ ] Have you built `bootJar` and launched `java -jar` to observe packaged behavior?
- [ ] Does `jar tf` include main resources under `BOOT-INF/classes`?
- [ ] Does `jar tf` exclude `src/test/resources` fixtures?
- [ ] Do you avoid claiming `gradlew test` is equivalent to packaged deployment?
- [ ] Have duplicate logical resource paths and classpath ordering been considered?
- [ ] When scanning folders/patterns, is `ResourcePatternResolver` used instead of `getFile().listFiles()`?
- [ ] Does code avoid converting `jar:` URLs into OS `File`/`Path` objects?
- [ ] Does code avoid trying to write into archive-backed resources after deployment?
- [ ] Are external Docker resource files mounted with explicit paths and permissions?
- [ ] Are real secrets kept out of both test and main resource artifacts?
- [ ] Are filename case sensitivity, encodings, and line endings tested per contract?
- [ ] If shipping GraalVM native images, are resource hints and native smoke tests included?
- [ ] Are source code and CLI commands clearly distinguished from **expected** stdout, never claiming unrun tests executed?

## 28. Run commands and expected behavior

From a project with Gradle Wrapper, Java 17+, and dependencies:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
jar tf build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar
jar tf .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

### Expected outcome from the 9 test methods

| Test | Expected |
| --- | --- |
| `mainClasspathResourceCanBeReadAsUtf8` | `Hello from main` |
| `testOnlyFixtureIsVisibleInTestRuntime` | `Test-only fixture` |
| `leadingSlashWithClassLoaderIsRootRelative` | Root resource resolved |
| `classRelativePathUsesTheClassPackage` | Package resource found, wrong relative path absent |
| `missingClasspathResourceIsNotTheSameAsMissingFile` | `exists=false` and `FileNotFoundException` |
| `realFileSystemResourceSupportsFilePath` | `FileSystemResource.getFile` succeeds |
| `jarEntrySupportsInputStreamButNotGetFile` | `InputStream` readable; `getFile` throws `FileNotFoundException` |
| `springInjectsResourceFromClasspathLocation` | `@Value Resource` readable |
| `resourceLoaderReadsWithoutAssumingFileSystem` | `ResourceLoader` readable; test fixture present |

### Expected packaged output

~~~text
MAIN_RESOURCE=Hello from main
TEST_ONLY_PRESENT=false
~~~

**These expectations are derived from source-set structure and code**; they are not actual Gradle/JUnit/`java -jar` outputs collected while writing this lesson. Running requires a Gradle Wrapper and JDK, and runtime prints additional Spring startup logs. JUnit tests alone do not prove the packed JAR runs cleanly; for complete evidence, CI should run a **dedicated packaged smoke step** after `bootJar`.

**Summary:** `ClassPathResource` is an abstraction for reading classpath data, **not a guarantee of a `File` path**. Unit tests in the IDE can mask `getFile()` bugs because resources sit in directories; after packaging, resources live inside a JAR. Use `Resource.getInputStream()`, keep reading logic independent of working directories, distinguish main vs. test source sets, and pair JAR-entry unit tests with a packaged executable smoke test. When a `File` is genuinely needed, materialize a temporary file with a managed lifecycle instead of forcing a JAR entry into a `File`.

### Official references

- [Spring Framework — Resources, `ClassPathResource`, and `Resource` interface](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Framework — `ClassPathResource` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/ClassPathResource.html)
- [Spring Framework — `ResourcePatternResolver` and `classpath*:`](https://docs.spring.io/spring-framework/reference/core/resources.html#resources-app-ctx)
- [Spring Boot — Executable JAR Format and Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/)
- [Gradle — Java Plugin source sets and `processResources`](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Managing Resources](https://docs.gradle.org/current/userguide/building_java_projects.html#sec:java_resources)
- [JUnit Jupiter — `@TempDir` temporary directories](https://docs.junit.org/current/user-guide/#writing-tests-built-in-extensions-TempDirectory)
- [Java SE 17 — `InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [Java SE 17 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)