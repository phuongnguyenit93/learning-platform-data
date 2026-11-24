# Classpath Resources When Running from Class Directories or from a JAR

During Spring Boot application development, a file placed in `src/main/resources` can usually be read easily. Yet after packaging into an executable JAR and running with `java -jar`, some code unexpectedly fails with `FileNotFoundException` or `FileSystemNotFoundException`. A common cause is that the code confuses a **classpath resource** with a **physical file on the filesystem**.

This distinction matters in the **Run and Package** chapter. When running from an IDE or a Maven/Gradle development task, classes and resources usually reside in **output directories** such as `target/classes` or `build/resources/main`. When packaged by Spring Boot tooling, resources are placed **inside the JAR**, typically under `BOOT-INF/classes`. A resource can still be read through a classloader or Spring's `Resource` API, though it no longer necessarily maps to a standalone `java.io.File`.

**Practical rule:** if data only needs to be read, open it with an `InputStream` through `ClassPathResource`, `ResourceLoader`, or `ClassLoader.getResourceAsStream(...)`. Do not construct paths directly to `src/main/resources`, and do not assume you can call `resource.getFile()` for a resource located inside a JAR.

This lesson moves from the classpath mechanism, the differences between running from class directories and an executable JAR, resource reading APIs, scenarios that require a physical file, a complete Spring Boot example, post-packaging testing, to common deployment pitfalls.

## 1. What Is a Classpath Resource?

In Java, the **classpath** is the set of locations that a classloader uses to find classes and resources. Those locations can be directories, JARs, or locations managed by specialized classloaders.

Suppose a project has:

~~~text
catalog-app/
└── src/
    └── main/
        ├── java/
        │   └── com/example/catalog/
        │       ├── CatalogApplication.java
        │       └── CatalogReader.java
        └── resources/
            ├── application.yml
            └── data/
                ├── catalog.json
                └── messages.txt
~~~

During build, Maven or Gradle typically places the files under `src/main/resources` into output resources visible to the runtime classpath.

The logical resource path is:

~~~text
data/catalog.json
~~~

When using Spring's prefix:

~~~text
classpath:data/catalog.json
~~~

The `classpath:` prefix does not mean the resource must sit in a physical directory named `classpath`. It means **search for this relative path across the locations managed by the classloader**.

### 1.1. The Source Directory Is Not the Runtime Location

`src/main/resources` is where resources live in the **source tree**. It is not a path guaranteed to exist after the application is built.

If code writes:

~~~java
Path path = Path.of("src/main/resources/data/catalog.json");
String json = Files.readString(path);
~~~

this snippet accesses a **filesystem path relative to the process's working directory**. It does not use the classpath.

While developing at the project root, the snippet may work because the `src/main/resources` directory actually exists there. When deploying the JAR to another machine, the source tree is usually gone, so that path may fail.

### 1.2. Resources vs. Classes

A `.class` file is bytecode loaded by the JVM as a class. Files such as `catalog.json`, `logo.png`, `schema.sql`, and `messages.txt` can also reside on the classpath even though they are not Java classes.

The classloader helps locate or open these resources without needing to know whether they sit inside a directory or an archive.

### 1.3. "Classpath Resource" Does Not Mean "Any File on the Machine"

If an operator mounts a file under:

~~~text
/opt/catalog/config/custom-rules.yml
~~~

that file is not automatically on the classpath. It can be read with filesystem APIs or a Spring `file:` resource, rather than queried with `classpath:` unless the launch configuration actually adds that location to the classpath.

## 2. When Running from Class Directories: Where Are Resources Located?

When running from an IDE or a development task, the classpath usually consists of output directories instead of a single executable JAR.

### 2.1. With Maven

Common output layout:

~~~text
target/
├── classes/
│   ├── com/
│   │   └── example/catalog/
│   │       ├── CatalogApplication.class
│   │       └── CatalogReader.class
│   ├── application.yml
│   └── data/
│       ├── catalog.json
│       └── messages.txt
└── test-classes/
    └── ...
~~~

When `target/classes` is a classpath root, looking up `data/catalog.json` corresponds to:

~~~text
target/classes/data/catalog.json
~~~

In this case, the resource may be an individual physical file on disk, so APIs such as `getFile()` may return a valid `File`.

### 2.2. With Gradle

Typical output:

~~~text
build/
├── classes/
│   └── java/main/
│       └── com/example/catalog/
│           ├── CatalogApplication.class
│           └── CatalogReader.class
└── resources/
    └── main/
        ├── application.yml
        └── data/
            ├── catalog.json
            └── messages.txt
~~~

The development classpath can combine `build/classes/java/main` with `build/resources/main` alongside other dependency JARs.

Thus **classes and resources do not have to live in the same directory**, as long as their respective classpath roots are added to the runtime classpath.

### 2.3. With an IDE

IntelliJ IDEA, Eclipse, VS Code, or Java extensions may use their own output layouts, or delegate building/running to Maven/Gradle.

Do not hard-code `target/classes` or `build/resources/main` in Java source code. Output paths are an implementation detail of the build tool and run configuration.

Use the classpath abstraction so the same code works even if the IDE changes output roots.

### 2.4. Path Flow Pattern

~~~text
src/main/resources/data/catalog.json
                |
                | processResources / copy resources
                v
        runtime classpath directory
                |
                +-- Maven: target/classes/data/catalog.json
                |
                +-- Gradle: build/resources/main/data/catalog.json
                |
                v
      classpath:data/catalog.json
                |
                v
         InputStream for reading
~~~

For a file to appear at runtime, it must be properly copied or included into a classpath root. Having the file in the source tree alone does not guarantee the runtime sees the latest copy.

## 3. When Packaging a Spring Boot Executable JAR

The Spring Boot Maven Plugin and Gradle Plugin can package an executable JAR, often called a "fat JAR" or "Boot JAR", to run via:

~~~bash
java -jar catalog-app.jar
~~~

A common JAR layout:

~~~text
catalog-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   ├── com/example/catalog/
    │   │   ├── CatalogApplication.class
    │   │   └── CatalogReader.class
    │   └── data/
    │       ├── catalog.json
    │       └── messages.txt
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   └── other-dependency.jar
    └── classpath.idx
~~~

This is an illustrative layout: dependency names, launcher classes, and auxiliary files depend on the Spring Boot version, plugins, and build configuration. The `classpath.idx` file is optional metadata and is not required in every JAR.

### 3.1. Why Is There `BOOT-INF/classes`?

`BOOT-INF/classes` holds the application's classes and resources. When the executable JAR runs via Boot's launcher, its contents are exposed as corresponding classpath resources.

For example, the resource still has the **logical classpath name**:

~~~text
data/catalog.json
~~~

even though its location inside the archive is:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Therefore, the code:

~~~java
new ClassPathResource("data/catalog.json")
~~~

does not need to be changed to:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

The `BOOT-INF/classes` prefix is an archive layout detail handled by the launcher, not part of a path that should be hard-coded in resource-consuming source code.

### 3.2. How Are Dependency JARs Handled?

Dependency JARs typically live in `BOOT-INF/lib`. The Spring Boot launcher includes a mechanism to load classes and resources from that archive structure.

A resource can come from:

- Application classes and resources in `BOOT-INF/classes`.
- A dependency JAR in `BOOT-INF/lib`.
- Other classpath locations actually exposed by the launcher or classloader.

This explains why two resources with the same name can exist in multiple dependencies and why `ClassLoader.getResource(...)` does not necessarily return "all copies".

### 3.3. When Running the JAR, `src/main/resources` No Longer Exists

Suppose you copy only the single file:

~~~text
catalog-app.jar
~~~

to a server and run:

~~~bash
java -jar catalog-app.jar
~~~

You do not need to copy `src/main/resources` alongside the JAR file for **packaged resources** bundled in the archive to work.

If code still depends on:

~~~text
src/main/resources/data/catalog.json
~~~

then it depends on a path in the source tree rather than relying properly on the classpath.

### 3.4. Do Not Manually Parse Nested JAR Paths

A resource URL inside an executable JAR may use a URL/protocol provided by the launcher rather than a plain `file:/...` URL. The exact URL structure can vary across Boot versions.

Do not split URL strings with `split("!")` to build a filesystem path for a nested JAR. Let the classloader or `Resource.getInputStream()` handle it.

## 4. Comparing Class Directories and JARs

| Criterion | Running from output directory | Running from Boot executable JAR |
| --- | --- | --- |
| Application classes | Individual `.class` files | Inside `BOOT-INF/classes` |
| Application resources | Files under output resources | Entries in `BOOT-INF/classes` |
| Dependencies | JARs on runtime classpath | Typically inside `BOOT-INF/lib` |
| `getResourceAsStream` | Readable | Readable |
| `ClassPathResource.getInputStream` | Readable | Readable |
| `ClassPathResource.getFile` | May work | Should not be expected to work |
| `Paths.get("src/main/resources/...")` | May work by accident at project root | Usually fails after deployment |
| Writing back to resources | Can modify output files, though discouraged | Cannot treat a JAR entry as a regular writable file |
| What it relies on | Output folders | Launcher, JAR layout, and classloader |
| Logical path in code | `classpath:data/catalog.json` | **Identical** |

Code resilience comes from accessing resources through the **classpath abstraction**, not from knowing which physical file structure holds the resource.

## 5. Approach 1: Reading with `ClassLoader.getResourceAsStream`

Java provides a standard API for opening classpath resources:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class CatalogTextLoader {

    public String loadCatalog() throws IOException {
        ClassLoader classLoader =
                Thread.currentThread().getContextClassLoader();

        try (InputStream input =
                     classLoader.getResourceAsStream(
                             "data/catalog.json")) {

            if (input == null) {
                throw new IOException(
                        "Classpath resource not found: data/catalog.json"
                );
            }

            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Key points:

1. The resource name has no `classpath:` prefix because this is the Java `ClassLoader` API.
2. With `ClassLoader.getResourceAsStream`, the path is interpreted relative to the **classpath root**.
3. If the resource is not found, the method can return `null`; always check for it.
4. Close the stream using `try-with-resources`.
5. Use an explicit encoding, such as UTF-8.

### 5.1. Do Not Add a Leading `/` with the `ClassLoader` API

Use:

~~~java
classLoader.getResourceAsStream("data/catalog.json");
~~~

Do not prepend a leading `/` out of habit from `Class.getResourceAsStream`:

~~~java
classLoader.getResourceAsStream("/data/catalog.json");
~~~

For the `ClassLoader` API, resource names normally do not begin with a slash.

### 5.2. The Context ClassLoader Is Not Always Required

You can use the class's own classloader:

~~~java
InputStream input =
        CatalogTextLoader.class.getClassLoader()
                .getResourceAsStream("data/catalog.json");
~~~

The context classloader is often helpful in frameworks that use specialized classloaders to load modules. In a straightforward application, the classloader of the executing class may be sufficient.

However, avoid mixing multiple classloaders arbitrarily when working with plugin architectures or executable JARs; the choice of classloader can affect which resources are found.

## 6. Approach 2: `Class.getResourceAsStream` and the Leading `/`

Java also offers:

~~~java
InputStream getResourceAsStream(String name);
~~~

on `Class<?>`.

Example:

~~~java
try (InputStream input =
             CatalogTextLoader.class.getResourceAsStream(
                     "/data/catalog.json")) {

    if (input == null) {
        throw new IOException("Resource is missing");
    }

    // Read the stream...
}
~~~

With `Class.getResourceAsStream`:

- A name starting with `/` is an absolute path **from the classpath root**.
- A name not starting with `/` is a path **relative to the class's package**.

Suppose `CatalogTextLoader` belongs to package:

~~~text
com.example.catalog
~~~

When calling:

~~~java
CatalogTextLoader.class.getResourceAsStream(
        "data/catalog.json"
);
~~~

Java looks up the resource relative to the package, corresponding to:

~~~text
com/example/catalog/data/catalog.json
~~~

Whereas when calling:

~~~java
CatalogTextLoader.class.getResourceAsStream(
        "/data/catalog.json"
);
~~~

Java looks up the resource from the classpath root:

~~~text
data/catalog.json
~~~

### 6.1. Table Distinguishing the Three Paths

| API | Path | Search starting point |
| --- | --- | --- |
| `ClassLoader.getResourceAsStream` | `data/catalog.json` | Classpath root |
| `SomeClass.class.getResourceAsStream` | `/data/catalog.json` | Classpath root |
| `SomeClass.class.getResourceAsStream` | `data/catalog.json` | Package containing `SomeClass` |

This is a common reason code returns `null` even when the file is present in the artifact. Before suspecting packaging, check which API you are using and whether the path is absolute or relative.

### 6.2. Do Not Pass `classpath:` to the Java `ClassLoader` API

The following usually does not work the way newcomers expect:

~~~java
classLoader.getResourceAsStream(
        "classpath:data/catalog.json"
);
~~~

`classpath:` is a prefix understood by Spring's `ResourceLoader`; Java's `ClassLoader.getResourceAsStream` does not handle that prefix automatically.

## 7. Approach 3: Spring's `ClassPathResource`

Spring Framework provides the `Resource` abstraction. For classpath resources, the familiar implementation is `ClassPathResource`:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
~~~

Example:

~~~java
public String loadCatalog() throws IOException {
    Resource resource =
            new ClassPathResource("data/catalog.json");

    try (InputStream input = resource.getInputStream()) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
    }
}
~~~

`ClassPathResource` spares your code from having to check `null` from `ClassLoader.getResourceAsStream` as in the plain Java example; when the resource cannot be opened, the operation can throw an appropriate `IOException`.

### 7.1. `Resource` Describes a Location, Not Always a `File`

`Resource` has several methods:

~~~java
resource.exists();
resource.isReadable();
resource.getFilename();
resource.getDescription();
resource.getInputStream();
resource.getURL();
resource.getURI();
resource.getFile();
~~~

That does not mean **every implementation supports every method with the same semantics**.

For example, `getInputStream()` is appropriate for reading a resource inside a JAR. `getFile()` is only suitable if the resource can actually be represented as a physical file.

### 7.2. Need to Inspect a `ClassPathResource`'s Source?

Example:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

System.out.println(resource.getDescription());
~~~

`getDescription()` is helpful during diagnostics because it describes the resource location. However, do not rely on the description string to extract a filesystem path or business identifier.

### 7.3. Can `ClassPathResource` Be Used in Both Modes?

Yes, as long as the resource is genuinely on the runtime classpath and found by the classloader. The exact same code can read:

~~~text
target/classes/data/catalog.json
~~~

or:

~~~text
catalog-app.jar!/BOOT-INF/classes/data/catalog.json
~~~

The `jar!/...` notation here is merely an illustration of the location inside the archive, not a `File` path that can be opened directly.

## 8. Approach 4: `ResourceLoader` in a Spring Boot Bean

In a Spring Boot application, `ResourceLoader` can be injected as an infrastructure dependency:

~~~java
package com.example.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CatalogReader {

    private final ResourceLoader resourceLoader;

    public CatalogReader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String read() throws IOException {
        Resource resource = resourceLoader.getResource(
                "classpath:data/catalog.json"
        );

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Here the `classpath:` prefix is syntax for Spring's `ResourceLoader`. Spring selects the appropriate implementation, typically `ClassPathResource` for this prefix.

### 8.1. Why Inject `ResourceLoader`?

- No need to instantiate `ClassPathResource` repeatedly throughout the codebase.
- Easy to choose locations from application configuration.
- Can read resources from either the classpath or the filesystem using the same abstraction.
- Reduces coupling to classloader details inside services.
- Integrates cleanly with Spring's bean lifecycle.

### 8.2. Not Every Location Should Be User-Controlled

Suppose a service calls:

~~~java
resourceLoader.getResource(location);
~~~

If `location` is taken directly from a user HTTP request, the application could be tricked into reading sensitive `file:` resources.

Only use resource locations configured from trusted sources or enforce a strict prefix/directory allowlist. `ResourceLoader` is a resource-access tool, not an authorization mechanism.

## 9. Approach 5: Injecting a `Resource` with `@Value`

Spring also supports binding a resource location directly into a dependency:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class BannerReader {

    private final Resource banner;

    public BannerReader(
            @Value("classpath:data/messages.txt") Resource banner) {
        this.banner = banner;
    }
}
~~~

Then:

~~~java
public String readBanner() throws IOException {
    try (InputStream input = banner.getInputStream()) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
    }
}
~~~

This approach fits well when the resource location is fixed.

If the location changes per environment, you can combine `@ConfigurationProperties` or a property specifying the resource location, and load it via `ResourceLoader`. Avoid scattering the same path string across many services.

### 9.1. `Resource` Differs from Content String

`@Value("classpath:data/messages.txt") Resource banner` gives you a **resource object**—it does not automatically read the entire file into a string.

You still need to open the stream or pass it to an appropriate parser.

## 10. Why Does `Resource.getFile()` Often Fail After Packaging?

This is a classic bug:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

File file = resource.getFile();
String content = Files.readString(file.toPath());
~~~

During development, `resource.getFile()` may return:

~~~text
.../target/classes/data/catalog.json
~~~

After packaging, the resource is merely an entry inside an executable JAR:

~~~text
catalog-app.jar
└── BOOT-INF/classes/data/catalog.json
~~~

An entry inside a JAR is not a standalone physical file that `java.io.File` can point to directly. Consequently, `getFile()` may throw an error such as:

~~~text
java.io.FileNotFoundException:
class path resource [data/catalog.json]
cannot be resolved to absolute file path
because it does not reside in the file system
~~~

The exact message depends on the Spring version and resource type.

### 10.1. Proper Fix: `InputStream`

Instead of:

~~~java
File file = resource.getFile();
String json = Files.readString(file.toPath());
~~~

use:

~~~java
try (InputStream input = resource.getInputStream()) {
    String json = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

For JSON files, if the parser supports `InputStream`, pass the stream directly rather than forcing an intermediate read into a `String`.

### 10.2. `getURL()` Does Not Imply `getFile()`

A resource can provide a valid `URL`:

~~~java
URL url = resource.getURL();
~~~

yet the URL may point to an archive resource using a specialized protocol. You should not immediately do:

~~~java
Path path = Paths.get(url.toURI());
~~~

and assume a filesystem provider understands that URI. `Paths.get(...)` can fail on URIs that do not belong to the default filesystem or an archive mounted with an appropriate provider.

If the goal is simply reading content, `InputStream` is simpler and less environment-dependent.

### 10.3. `File#getPath` and `URL#getFile` Are Two Different Concepts

The method name `URL.getFile()` can be misleading. It returns the file/path portion of the URL according to `URL` semantics; it does **not** return a `java.io.File` verified by the operating system to exist.

Do not use `new File(url.getFile())` as a recipe for reading a classpath resource packaged inside a JAR. That pattern also breaks easily when paths contain spaces, Unicode characters, or URL encoding.

## 11. What If a Library Strictly Requires a `File` or `Path`?

Some older APIs only accept `File` or `Path` and do not accept `InputStream`. In those cases, you may need to **copy the resource to a temporary file**, then pass that file to the library.

Example:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public final class LegacyFileAdapter {

    public void process() throws IOException {
        Resource source =
                new ClassPathResource("data/catalog.json");

        Path temporary = Files.createTempFile(
                "catalog-",
                ".json"
        );

        try {
            try (InputStream input = source.getInputStream()) {
                Files.copy(
                        input,
                        temporary,
                        StandardCopyOption.REPLACE_EXISTING
                );
            }

            LegacyParser.parse(temporary.toFile());
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

`LegacyParser` is a hypothetical class that only accepts a file. In real code, substitute the API of the library you are using.

### 11.1. Do Not Delete the File While the Library Still Uses It

The example above assumes `LegacyParser.parse(...)` processes the file **synchronously** and finishes before the method returns.

If the library retains the `Path` and processes it asynchronously, you must not delete the file immediately in `finally`. You need to manage the temporary file's lifecycle according to its actual usage duration, with a cleanup strategy and access-permission controls.

### 11.2. File Naming, Permissions, and Disk Space

When copying a resource to a temporary file:

- Use a safe creation API such as `Files.createTempFile`.
- Do not construct filenames from untrusted input without validation.
- Control access permissions if the contents are sensitive.
- Pay attention to disk usage and cleanup policies.
- Do not assume temporary files survive across restarts or container recreation.

### 11.3. When Should You Switch APIs?

If a library supports both `File` and `InputStream`, choose `InputStream` for resources packaged inside a JAR. Do not copy to disk just because an older example used `File`.

## 12. A Packaged Resource Cannot Be Treated as Runtime Writable Storage

A file `src/main/resources/data/catalog.json` is usually packaged into the artifact as **data bundled with the application**. Inside an executable JAR, that entry is not a writable file that can be overwritten like an external config file.

Code such as:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

Files.writeString(
        resource.getFile().toPath(),
        "updated"
);
~~~

may happen to work during development if the resource resides on disk. After deployment, file access may fail; and even if modifying a file in an output directory succeeds, that change does not become part of the managed source artifact.

### 12.1. Distinguishing Packaged Defaults from Mutable Data

A common design:

- **Classpath resources:** default samples, schemas, templates, small seed data, configuration files packaged with the release.
- **External files:** data that may change per environment or per user.
- **Database/object storage:** business data or data requiring durable storage and synchronization across multiple instances.

If the application must persist processing output or let operators modify a file without rebuilding, use a directory outside the artifact.

### 12.2. Example Writing to an External Directory

~~~java
Path outputDirectory = Path.of("/var/lib/catalog/export");

Files.createDirectories(outputDirectory);

Path destination = outputDirectory.resolve("catalog-export.json");

Files.writeString(
        destination,
        "{ \"status\": \"exported\" }",
        StandardCharsets.UTF_8
);
~~~

The path above merely illustrates a Linux/container environment. In a real application, use configuration properties to choose the directory, check write permissions, handle I/O errors, and avoid unintended overwrites.

### 12.3. Container Images and Filesystems

When running in Docker/Kubernetes, resources packaged inside the JAR or image remain readable via the classpath, whereas data to be persisted should reside on a volume or appropriate storage service.

Do not expect modifications to a classpath resource inside an image to persist after a Pod is replaced.

## 13. Complete Example: Reading JSON via `InputStream`

Suppose there is a file:

~~~text
src/main/resources/data/catalog.json
~~~

Contents:

~~~json
{
  "version": 1,
  "items": [
    { "id": "A100", "name": "Notebook" },
    { "id": "B200", "name": "Pen" }
  ]
}
~~~

There are two ways to read it: reading into a string or letting Jackson parse directly from the stream.

### 13.1. Reading into a UTF-8 String

~~~java
@Service
public class CatalogTextService {

    private final ResourceLoader loader;

    public CatalogTextService(ResourceLoader loader) {
        this.loader = loader;
    }

    public String getJson() throws IOException {
        Resource resource =
                loader.getResource("classpath:data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

For small files, this approach is simple enough. For large files, `readAllBytes()` can consume significant heap by loading the entire content into memory.

### 13.2. Parsing Directly with Jackson

If the project includes Jackson Databind:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CatalogJsonService {

    private final ResourceLoader loader;
    private final ObjectMapper objectMapper;

    public CatalogJsonService(
            ResourceLoader loader,
            ObjectMapper objectMapper) {
        this.loader = loader;
        this.objectMapper = objectMapper;
    }

    public JsonNode load() throws IOException {
        Resource resource =
                loader.getResource("classpath:data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            return objectMapper.readTree(input);
        }
    }
}
~~~

`ObjectMapper` can be auto-configured by Spring Boot when Jackson is present and appropriately configured. If a project only includes the basic `spring-boot-starter` without Jackson, declare the corresponding JSON dependency or register a parser yourself.

### 13.3. Why Passing `InputStream` Is Better Than `Path`

Jackson provides an API taking `InputStream`, so the same logic runs whether the resource is in `target/classes`, `build/resources/main`, inside an executable JAR, or inside a dependency JAR.

There is no need to care about URL schemes, mounted filesystems, or temporary paths.

### 13.4. If the File Is Missing from the Classpath

`resource.getInputStream()` can throw `IOException`. This is a signal to handle explicitly:

- If the catalog is required: fail fast on startup or report a meaningful error.
- If the catalog is optional: supply a predefined fallback.
- If the filename comes from configuration: log the normalized location without exposing secrets.

Do not silently swallow exceptions and return empty data when the data is mandatory for the application to function properly.

## 14. Spring Boot Example: `ApplicationRunner` Reading a Resource at Startup

Here is a self-contained illustrative application.

### 14.1. Project Structure

~~~text
catalog-app/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/catalog/
    │   │   ├── CatalogApplication.java
    │   │   └── CatalogStartupReader.java
    │   └── resources/
    │       └── data/
    │           └── catalog.json
    └── test/
        └── java/com/example/catalog/
            └── CatalogResourceTest.java
~~~

### 14.2. Maven Dependencies and Plugin

Assume the project already uses a suitable Spring Boot parent or dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

This snippet shows what to add to a `pom.xml` that already has a valid project/parent section, rather than a standalone POM.

### 14.3. Startup Class

`CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 14.4. Reader Running When the Context Is Ready for Runners

`CatalogStartupReader.java`:

~~~java
package com.example.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;

@Component
public class CatalogStartupReader implements ApplicationRunner {

    private final ResourceLoader resourceLoader;

    public CatalogStartupReader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    @Override
    public void run(ApplicationArguments args) throws IOException {
        Resource resource =
                resourceLoader.getResource(
                        "classpath:data/catalog.json"
                );

        try (InputStream input = resource.getInputStream()) {
            String json = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            System.out.println("Source: " + resource.getDescription());
            System.out.println("Catalog JSON: " + json);
        }
    }
}
~~~

If the resource is missing, the runner fails with an error rather than letting the application pretend startup succeeded with empty data.

### 14.5. Running During Development

With Maven:

~~~bash
mvn spring-boot:run
~~~

Or run the main class from your IDE.

In typical development mode, `catalog.json` sits in output resources. The reader opens the stream and prints the content.

### 14.6. Packaging and Running the JAR

~~~bash
mvn package
java -jar target/catalog-app-0.0.1-SNAPSHOT.jar
~~~

The JAR filename is an example: substitute the actual artifact produced by your build.

When running from the JAR, the code requires no modification:

~~~java
resourceLoader.getResource(
        "classpath:data/catalog.json"
);
~~~

remains the correct logical path if the build included the resource in the archive.

### 14.7. Inspecting with `jar tf`

After building, run:

~~~bash
jar tf target/catalog-app-0.0.1-SNAPSHOT.jar
~~~

An expected output line:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

If it is missing, the problem may lie in the resource packaging step rather than in Spring's `ResourceLoader` itself.

### 14.8. Why Does the Example Avoid `getFile`?

Because the goal is **the exact same code working properly in both environments**. `getInputStream()` fulfills that goal, whereas `getFile()` forces the resource to be representable as a physical file.

## 15. Packaging with Gradle: `processResources` and `bootJar`

In a project with the Spring Boot Gradle plugin and Java plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
~~~

Plugin versions and dependency management are defined in the actual project's build script/settings; the snippet above only illustrates plugin IDs.

For a default resource:

~~~text
src/main/resources/data/catalog.json
~~~

the Gradle Java plugin normally copies the resource to:

~~~text
build/resources/main/data/catalog.json
~~~

via the `processResources` task; Spring Boot `bootJar` can package it into:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Common commands:

~~~bash
./gradlew bootRun
./gradlew bootJar
java -jar build/libs/catalog-app-0.0.1-SNAPSHOT.jar
~~~

The JAR name and task contents depend on the current configuration.

### 15.1. Distinguishing `jar` and `bootJar`

The regular Gradle `jar` task may produce a plain JAR that does not include runtime dependencies in the same manner as an executable Boot JAR. `bootJar` is designed by the Spring Boot plugin for packaging an executable archive.

Therefore, if resources are read properly yet `java -jar` complains about a missing main class or dependencies, verify that you are running the **right artifact** and the right packaging task, rather than only checking resource paths.

### 15.2. Custom Resource Filtering

If the build uses resource filtering or customizes `sourceSets`/`processResources`, certain files may be excluded or have their contents transformed before packaging.

When diagnosing, inspect all three:

~~~text
src/main/resources/data/catalog.json
build/resources/main/data/catalog.json
BOOT-INF/classes/data/catalog.json
~~~

Do not assume the source file is byte-for-byte identical to the copy inside the JAR if the build applies transformation steps.

## 16. Reading Resources in Dependency Libraries

Not every resource is owned by the application. A library may package its own templates or metadata.

Example dependency:

~~~text
reporting-support.jar
└── templates/
    └── default-report.html
~~~

Application code can read:

~~~java
Resource template =
        new ClassPathResource(
                "templates/default-report.html"
        );

try (InputStream input = template.getInputStream()) {
    // Read the template content...
}
~~~

The condition is that the dependency is present on the runtime classpath and the resource genuinely exists under that exact name.

### 16.1. Resource Name Collisions Across Multiple Dependencies

If two JARs both contain:

~~~text
templates/default-report.html
~~~

then `ClassLoader.getResource(...)` or `ClassPathResource` usually resolves a single resource based on classloader search order. Do not rely on that as a stable business-priority override mechanism.

If you need all copies sharing the same name, use `ClassLoader.getResources(...)` or Spring's `ResourcePatternResolver` with `classpath*:`.

### 16.2. Avoid Overly Generic Names in Libraries

For libraries built for reuse, organize resources under a stable namespace:

~~~text
META-INF/com-example-reporting/
└── templates/
    └── default-report.html
~~~

This reduces the chance of colliding with other libraries and makes pattern scanning cleaner.

### 16.3. Do Not Hard-Code `BOOT-INF/lib`

A library might be loaded as a JAR during development, as a nested JAR inside a Boot executable archive, or through another classpath mechanism.

The path used for reading should be the logical classpath path published by the library, not a manually constructed `BOOT-INF/lib/<dependency>.jar!/....` path in application code.

## 17. Finding Multiple Resources vs. Reading a Single Resource

When you know the exact filename:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");
~~~

is the straightforward approach.

When you want to locate multiple JSON files:

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
        "classpath*:data/**/*.json"
);
~~~

Imports:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
~~~

### 17.1. `classpath:` and `classpath*:`

- `classpath:` normally resolves a single classpath location or pattern from a chosen root.
- `classpath*:` searches across all matching locations on the runtime classpath, including inside dependency JARs accessible to the resolver.

However, wildcard scanning depends on how the classloader and archives expose directories/entries. When designing a library requiring discovery, place resources in a fixed subdirectory such as `META-INF/myapp/schemas/` and avoid wildcard scanning at the JAR root.

### 17.2. Each Resource Is Still Read via a Stream

Even when the resolver returns multiple `Resource` items, keep the reading pattern the same:

~~~java
for (Resource resource : resources) {
    try (InputStream input = resource.getInputStream()) {
        // Parse each resource...
    }
}
~~~

Do not convert them into `File` objects just because you are iterating over multiple resources.

### 17.3. Do Not Rely on Returned Order

When scanning across multiple classpath roots, resource order may depend on the classloader and archive ordering. If rule application order matters, the application needs an explicit priority policy.

## 18. Distinguishing Classpath Resources from External Configuration

Spring Boot also provides **externalized configuration**. Files like `application.yml` can be loaded from multiple locations according to Config Data and property source rules.

That applies to **application configuration**; it does not mean every resource read with `ClassPathResource` automatically inherits `application.yml` precedence rules.

For example:

~~~java
new ClassPathResource("data/catalog.json");
~~~

only reads the resource at logical path `data/catalog.json`. It does not automatically search `/etc/catalog` for a replacement file simply because the filename matches.

### 18.1. When to Choose the Classpath?

Use the classpath for data that should be tied to the artifact version:

- Default JSON schemas.
- Templates bundled with the release.
- Structural mappings that operators do not need to modify frequently.
- Seed data used during development/testing or initialization.
- Static assets published alongside the application.

### 18.2. When to Choose an External File?

Use an external file when values must change without rebuilding:

- Environment-specific configuration files.
- Certificates/keys mounted from a secret store.
- Datasets updated by operators.
- Output exported by the application.
- Input files supplied by external systems.

Spring `ResourceLoader` example:

~~~java
Resource resource =
        resourceLoader.getResource(
                "file:/opt/catalog/config/custom-rules.yml"
        );
~~~

Or Java NIO:

~~~java
Path path = Path.of("/opt/catalog/config/custom-rules.yml");
try (InputStream input = Files.newInputStream(path)) {
    // ...
}
~~~

In production systems, validate read permissions, paths, encoding, file sizes, and how the location is configured.

### 18.3. Avoid Implicit Undocumented Fallbacks

If an application prefers an external file and falls back to a classpath default, express it explicitly:

~~~java
Resource external =
        resourceLoader.getResource(
                "file:/opt/catalog/config/catalog.json"
        );

Resource selected = external.exists()
        ? external
        : resourceLoader.getResource(
                "classpath:data/catalog-default.json"
        );
~~~

This example only selects the source; you still must handle I/O errors when reading. For critical files, consider failing fast if an external file is specified yet unreadable rather than silently falling back.

## 19. Web Application Resources: `static` and `templates`

Spring Boot web applications commonly place resources under:

~~~text
src/main/resources/
├── static/
│   ├── css/site.css
│   └── images/logo.png
└── templates/
    └── invoice.html
~~~

When packaged into an executable JAR, these files are likewise placed inside `BOOT-INF/classes` following the corresponding resource layout.

### 19.1. Static Resources

A static resource can be served by Spring MVC through static resource handling when appropriately configured, for example:

~~~text
GET /css/site.css
GET /images/logo.png
~~~

This **does not require files to sit in a public filesystem directory next to the JAR**. The framework can read resources through the classpath abstraction.

### 19.2. Templates

Thymeleaf and several other template engines usually look up templates under `classpath:/templates/` under default configuration or their own resolver.

There is no need to call `new File("src/main/resources/templates/invoice.html")` for the engine to render a template. Let the template resolver handle resource locations.

### 19.3. HTTP URLs Are Not Classpath URLs

A static file may be accessed over HTTP such as:

~~~text
https://example.test/images/logo.png
~~~

yet the HTTP URL is a public route served by the web framework. The underlying classpath resource may be:

~~~text
classpath:/static/images/logo.png
~~~

These are two different identifier layers: one is a client URL, and the other is a server resource location.

## 20. Testing Resources in the Development Environment

A small test can verify that a resource is built onto the test/runtime classpath.

JUnit 5 example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

class CatalogResourceTest {

    @Test
    void catalogIsAvailableOnClasspath() throws IOException {
        Resource resource =
                new ClassPathResource("data/catalog.json");

        assertThat(resource.exists()).isTrue();

        try (InputStream input = resource.getInputStream()) {
            String json = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            assertThat(json).contains("\"items\"");
        }
    }
}
~~~

This test uses `ClassPathResource` and reads a stream; it does not require `getFile()`. Thus its logic fits both output-directory resources and resources inside a JAR.

### 20.1. Are `src/test/resources` Included in the Production JAR?

Normally, resources inside:

~~~text
src/test/resources/
~~~

are placed on the **test classpath**, not into the production executable JAR.

If a test finds a resource yet deployment cannot find it, check whether the file was placed only in `src/test/resources`.

Resources required at production runtime must reside in a properly packaged runtime source set or dependency, typically `src/main/resources`.

### 20.2. Pure Classpath Tests Do Not Prove Packaged Runtime Correctness

A unit test or `@SpringBootTest` running in the IDE usually runs against output directories. Passing tests do not prove every piece of code works when resources reside inside an executable JAR.

In particular, code calling `getFile()` can pass IDE tests and fail after packaging.

Therefore, include at least one **post-packaging** check when the application has important resource-loading requirements.

## 21. Testing After Packaging the JAR

A smoke test workflow can consist of:

1. Building the artifact.
2. Verifying the resource file is present inside the JAR.
3. Running `java -jar` from a directory other than the project root.
4. Observing the application read the resource successfully.
5. Confirming no code depends on `src/main/resources`.

With Maven:

~~~bash
mvn package
jar tf target/catalog-app-0.0.1-SNAPSHOT.jar
java -jar target/catalog-app-0.0.1-SNAPSHOT.jar
~~~

With Gradle:

~~~bash
./gradlew bootJar
jar tf build/libs/catalog-app-0.0.1-SNAPSHOT.jar
java -jar build/libs/catalog-app-0.0.1-SNAPSHOT.jar
~~~

The JAR file paths are illustrative. Replace them with the actual artifact.

### 21.1. Why Is Running from Another Directory Helpful?

If code contains:

~~~java
Path.of("src/main/resources/data/catalog.json");
~~~

it can accidentally work when the working directory is the project root.

When you launch the JAR from a clean directory holding only the artifact, that relative path no longer exists. This is a practical way to catch code that confused a classpath location with a filesystem path.

### 21.2. Checking JAR Contents

Run:

~~~bash
jar tf catalog-app.jar
~~~

and look for the entry:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

`jar tf` lists archive entries; it does not verify that your business parser reads the content properly. Combine it with an actual runtime test.

### 21.3. Do Not Only Inspect the Manifest

The manifest/launcher tells how the artifact boots. A JAR with a valid manifest can still lack resources if the build configuration excludes the source resource directory.

## 22. How Do `java -cp` and `java -jar` Differ?

These two startup modes use the classpath via different mechanisms.

### 22.1. When Running Classes Directly

For example, if `target/classes` holds the main class and dependencies are configured externally:

~~~bash
java -cp target/classes com.example.catalog.CatalogApplication
~~~

The command above only illustrates the structure; a real Spring Boot application requires dependency JARs on the classpath. With only `target/classes` and missing Spring Boot dependencies, the app cannot start completely.

With a complete development classpath, resources directly under the output root typically resolve as file URLs.

### 22.2. When Running an Executable JAR

~~~bash
java -jar catalog-app.jar
~~~

The JVM runs the launcher declared in the manifest; the Spring Boot launcher sets up an internal classpath exposing `BOOT-INF/classes` and nested dependencies.

Hence simply taking the executable JAR and running `java -cp catalog-app.jar com.example.catalog.CatalogApplication` is not necessarily equivalent to `java -jar`. Class paths under `BOOT-INF/classes` are not the root of a plain JAR classpath in that mode.

### 22.3. No Need to Change Resource Names per Launcher

Despite different startup modes, once the classloader is set up properly:

~~~java
new ClassPathResource("data/catalog.json");
~~~

still describes the same logical resource name.

## 23. Docker and Kubernetes: Resources Stay Inside the Artifact

In a container image, the application may run via:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY catalog-app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

If `catalog.json` is already inside the JAR, there is no need to copy `src/main/resources` separately into the image.

The resource is opened with:

~~~java
new ClassPathResource("data/catalog.json")
        .getInputStream();
~~~

### 23.1. `WORKDIR` Does Not Alter Logical Classpath Resources

`WORKDIR /app` sets the process's default working directory; it does not turn `data/catalog.json` into `/app/data/catalog.json` when using `ClassPathResource`.

Conversely, `Path.of("data/catalog.json")` is a relative filesystem path and resolves against the working directory, which may be `/app/data/catalog.json`.

### 23.2. Mounting Configuration Outside the Application

If a Kubernetes environment mounts config under:

~~~text
/etc/catalog/config.yml
~~~

that is an external file, not automatically a classpath resource.

Use `file:/etc/catalog/config.yml` or Java NIO, or configure Spring Boot Config Data loading accordingly if the file supplies application configuration.

### 23.3. Testing Resources Against the Exact Artifact

To eliminate differences between testing and production, run smoke tests on the exact executable JAR or container image being deployed. Do not rely solely on testing classes/resources compiled separately inside an IDE.

## 24. Avoiding Encoding and Path Pitfalls

Even after using the classpath correctly, reading resources still carries pitfalls:

### 24.1. Do Not Rely on the Default Charset

Avoid writing:

~~~java
new String(input.readAllBytes());
~~~

if the document requires consistent UTF-8 across environments. Use:

~~~java
new String(
        input.readAllBytes(),
        StandardCharsets.UTF_8
);
~~~

or a parser configured with the appropriate encoding.

### 24.2. Do Not Manually Decode Resource URLs to Build File Paths

URLs may contain percent-encoding, spaces, Unicode, or JAR-specific protocols. Slicing URL strings manually to construct `new File(...)` is fragile.

If you do not need a physical path, do not convert the URL to a `File`.

### 24.3. Resource Names Are Case-Sensitive

Some development filesystems are case-insensitive, whereas archive entries and runtime environments can be case-sensitive. Use the exact name:

~~~text
data/catalog.json
~~~

rather than:

~~~text
data/Catalog.json
~~~

Keep filename and path casing consistent across source, tests, and deployment.

### 24.4. Forward Slashes

In classpath resource names, use `/` following Java URL/path conventions, even when developing on Windows:

~~~text
data/catalog.json
~~~

Do not hard-code paths with `\\` like a Windows filesystem path.

### 24.5. Large Resources

`input.readAllBytes()` works well for small files. For large CSV/JSON files, consider streaming parsers or chunked reads to avoid unnecessary heap pressure and startup delays.

## 25. Common Errors and How to Fix Them

### 25.1. `FileNotFoundException` After Running `java -jar`

**Symptom:** runs fine from the IDE, yet the JAR reports that the resource cannot be resolved to an absolute file path.

**Common cause:** code calls `ClassPathResource.getFile()`.

**Fix:** use `getInputStream()`; if a library strictly requires `File`, copy to a lifecycle-managed temporary file.

### 25.2. `NoSuchFileException` with `src/main/resources`

**Symptom:** the program reports it cannot find `src/main/resources/data/catalog.json` on the server.

**Cause:** code uses a relative filesystem path pointing to the source tree.

**Fix:** read `classpath:data/catalog.json` if the data is packaged, or move explicitly to a clearly configured external file.

### 25.3. Resource Exists in the JAR but `ClassLoader` Returns `null`

**Possible causes:**

- Wrong name or wrong letter casing.
- Using a leading `/` with `ClassLoader.getResourceAsStream`.
- Passing the `classpath:` prefix to the Java `ClassLoader` API.
- The resource sits at a different path inside the archive.
- The classloader in use cannot see the resource.

**Fix:** inspect entries with `jar tf`, normalize the name, and verify `ClassPathResource` inside the actual runtime.

### 25.4. Resource Exists in Tests but Not in Production

**Cause:** the file resides only in `src/test/resources`.

**Fix:** move runtime-needed files to `src/main/resources` or provide them via a runtime dependency.

### 25.5. Works in IDE but Fails in Docker

**Possible causes:** code uses a working-directory path, an external file outside the JAR wasn't copied/mounted, differing permissions, or case-sensitive paths.

**Fix:** distinguish packaged resources from external files; check the image/volumes and use the API matching the source type.

### 25.6. `java -jar` Reports Missing Classes or Dependencies

**Cause:** running a plain JAR instead of an executable Spring Boot JAR, or misconfigured packaging plugins.

**Fix:** check `repackage`/`bootJar` plugins, the manifest, and the actual artifact. This is a packaging issue, not necessarily a resource path bug.

### 25.7. Able to Read URL, but `Paths.get(url.toURI())` Fails

**Cause:** the URI points to an archive/protocol unsupported by the default filesystem or lacking a matching filesystem provider.

**Fix:** use `InputStream`; convert to `Path` only when a valid filesystem path truly exists.

### 25.8. Resource Is Packaged, but Contents Are Stale

**Cause:** build didn't copy updated resources, build cache, custom filtering, or running a different artifact than just built.

**Fix:** check output resources, archive entries in the JAR, and the exact artifact name being run.

### 25.9. Two Dependencies Have Resources with the Same Name

**Cause:** the classloader picks one resource by search order; code mistakenly expects automatic merging.

**Fix:** place library resources in a library namespace; if all copies are needed, use `getResources`/`ResourcePatternResolver` with clear duplicate-handling rules.

### 25.10. Application Attempts to Write Back to a Classpath Resource

**Cause:** confusing packaged resources with writable runtime data files.

**Fix:** use a filesystem directory, volume, or storage designed for writes; keep classpath resources as artifact-versioned bundled data.

### 25.11. Converting `getResource` URL to `new File`

**Cause:** code assumes every URL is a `file:` URL.

**Fix:** read the stream directly without depending on the URL scheme/protocol.

### 25.12. Resource Missing When Switching Runtime Environments

**Cause:** differing `sourceSets`, differing artifact packaging, differing dependency scopes, or specialized classloaders.

**Fix:** inspect the actual runtime classpath and packaged artifact instead of guessing from the IDE folder tree.

## 26. Process for Designing Resilient Resource Access

When adding a resource for a Spring Boot feature:

1. **Choose the source type:** immutable release-bundled data or an externally changeable file?
2. **For release-bundled data, place it in `src/main/resources`** or a well-structured runtime dependency.
3. **Choose a stable logical classpath name:** e.g., `data/catalog.json` or `META-INF/myapp/defaults.yml`.
4. **Use `ResourceLoader`, `ClassPathResource`, or the `ClassLoader` API** to open the resource.
5. **Read via `InputStream`**, without depending on `getFile()`.
6. **Close streams** and handle `IOException`/parser errors explicitly.
7. **Specify explicit encoding** for text data.
8. **Never write back to packaged resources**; choose dedicated storage for mutable data.
9. **Verify the resource appears in runtime output/JAR** if the build customizes `sourceSets` or resource filtering.
10. **Test from both the IDE and the executable JAR** to catch code accidentally tied to filesystem paths.
11. **Prevent name collisions** when resources exist across multiple libraries.
12. **Restrict accessible inputs and locations** if resource paths come from external configuration or users.

If code only works when the project is opened at the source directory, that is a clear sign to revisit the boundary between the **source tree**, the **runtime classpath**, and the **external filesystem**.

## 27. Hands-On Practice

### Exercise A: Running from Class Directories

Create `src/main/resources/data/hello.txt` with contents:

~~~text
Hello from classpath!
~~~

Write an `ApplicationRunner` using `ClassPathResource("data/hello.txt")` and `getInputStream()` to read it. Run from your IDE or with `mvn spring-boot:run`.

Observe that the resource is found even though the code never mentions `src/main/resources`.

### Exercise B: Running from an Executable JAR

Package the application using `mvn package` or `./gradlew bootJar`. Inspect the `BOOT-INF/classes/data/hello.txt` entry with `jar tf`.

Run `java -jar` and confirm the runner reads the exact same content with zero code changes.

### Exercise C: Reproducing the `getFile` Error

In a test setup, change:

~~~java
resource.getInputStream();
~~~

to:

~~~java
resource.getFile();
~~~

Observe the difference between running from output directories and from an executable JAR. Explain why `File` cannot represent an archive entry.

Restore stream-based reading once you have observed the failure.

### Exercise D: Distinguishing `ClassLoader` and `Class` Paths

Given a class in package `com.example.catalog`, compare:

~~~java
SomeClass.class.getResourceAsStream(
        "/data/hello.txt"
);
~~~

~~~java
SomeClass.class.getResourceAsStream(
        "data/hello.txt"
);
~~~

~~~java
SomeClass.class.getClassLoader()
        .getResourceAsStream(
                "data/hello.txt"
        );
~~~

Record the path searched by each call and explain the leading `/`.

### Exercise E: Changing the Working Directory

Run the JAR from a directory outside the project root. Compare the outcome of:

~~~java
Path.of("src/main/resources/data/hello.txt");
~~~

and:

~~~java
new ClassPathResource("data/hello.txt");
~~~

Only the second accurately describes a packaged classpath resource.

### Exercise F: Resource from a Dependency JAR

Create a library module containing:

~~~text
META-INF/myapp/messages/default.txt
~~~

Package it and add it as a runtime dependency of the application. Use `ClassPathResource` to read that file from the application.

Observe that you do not need to know the library's `BOOT-INF/lib` path.

### Exercise G: Scenario Requiring an External File

Keep a default file on the classpath and a custom file in a directory outside the application.

Design a rule: if the external file exists and is readable, use it; if not and fallback is allowed, use the classpath default. Clearly specify when execution should fail rather than silently ignoring an error.

### Exercise H: Passing a Resource to a Library Requiring `File`

Create a mock API `LegacyParser.parse(File)`. Use `getInputStream()` to copy the resource to a temp file, call the parser, and clean up safely.

Explain why you must not delete the temp file prematurely if the API processes asynchronously.

### Exercise I: Distinguishing `main` and `test` Resources

Place a file solely in `src/test/resources`. Write a unit test that reads it successfully, then run the production JAR and observe that it is absent under default packaging.

Move the file required for production into `src/main/resources` and try again.

## 28. Self-Check Questions

**1. How is a resource in `src/main/resources` used at runtime?**

The build typically copies or packages it onto the runtime classpath, where the classloader/`ResourceLoader` can look it up by logical name.

**2. With Maven, what is the typical development classpath output?**

Typically `target/classes` for classes and main resources, along with dependency JARs.

**3. With Gradle, where are main classes and resources typically placed?**

Typically in `build/classes/java/main` and `build/resources/main`, though actual layout can vary by build configuration.

**4. In an executable Spring Boot JAR, where do application classes and resources usually sit?**

In `BOOT-INF/classes` under the standard Boot JAR layout.

**5. Does Java code reading a resource need to prepend `BOOT-INF/classes` after packaging?**

No. You still use the logical classpath name such as `data/catalog.json`.

**6. Why might `Resource.getFile()` work in the IDE yet fail from a JAR?**

Because when running from output directories the resource may be an actual file, whereas inside a JAR it is an archive entry with no standalone `File`.

**7. Which API should be used to read resources across both modes?**

`InputStream` from `ClassPathResource`/`ResourceLoader` or `ClassLoader.getResourceAsStream`.

**8. Does `ClassLoader.getResourceAsStream` use the `classpath:` prefix?**

No. It accepts a classpath resource name such as `data/catalog.json`.

**9. Where does `SomeClass.class.getResourceAsStream("data/x.txt")` search from?**

Relative to the package of `SomeClass`; add a leading `/` to search from the classpath root.

**10. Does `URL.getFile()` return a valid `java.io.File`?**

No. It returns the path portion of the URL and does not guarantee an accessible physical file.

**11. If a library only accepts `File`, what should you do with a resource in a JAR?**

Copy its contents via `InputStream` to a temporary file, manage the file lifecycle, and pass that file to the library.

**12. Can you write back to a file inside an executable JAR using `Files.writeString`?**

Packaged resources should not be treated as writable targets. Use external files, volumes, or appropriate storage.

**13. Why is a passing unit test reading a resource not enough to prove deployment works?**

Tests usually run against output directories; packaged JARs have a different layout and classloader. Smoke-test the actual artifact.

**14. Are files in `src/test/resources` automatically included in the production executable JAR?**

Normally no. They belong only to the test classpath.

**15. Is `java -cp app.jar MainClass` always equivalent to `java -jar app.jar` for a Spring Boot executable JAR?**

No. A Boot executable JAR has its own launcher and internal layout; run it properly according to Boot packaging.

## 29. Conclusion

**A classpath resource is a resource found by a classloader via a logical path, not necessarily a physical file sitting next to the application.** When running from an IDE, Maven, or Gradle, resources usually reside in output directories; when packaged into a Spring Boot executable JAR, they usually sit in `BOOT-INF/classes` or dependency JARs. Packaging changes, yet the logical classpath name such as `data/catalog.json` can stay identical.

Therefore, when you only need to read data, use `ClassPathResource`, `ResourceLoader`, or Java's `ClassLoader.getResourceAsStream` and process content through `InputStream`. Do not assume `getFile()` is always supported, do not hard-code `src/main/resources`, and do not convert resource URLs into filesystem paths unless an actual physical file exists.

Clearly separate artifact-bundled resources from external files that require modification or runtime writes. Finally, test both development output and the packaged executable JAR to catch deployment-only bugs early. Designing around the classpath abstraction allows the same Spring Boot application to read resources reliably across class directories, JARs, containers, and other deployment environments.
