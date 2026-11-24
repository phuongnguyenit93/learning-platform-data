# Distinguishing Classpath, Working Directory, and File Paths

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** File Discovery and Loading

## 1. Why Distinguish These Three Concepts?

A Spring Boot application often needs to read two categories of data: **resources packaged with the application** (email templates, default JSON files, public certificates, sample data) and **files outside the application** (deployment configuration, import/export data, user-uploaded files). These two groups can be accessed in completely different ways.

The three commonly confused concepts are:

- **Classpath**: the set of locations that the Java ClassLoader uses to find classes and resources at runtime. Resources may reside in directories or inside JARs.
- **Working directory**: the current directory of the Java process, typically represented by `user.dir`. A relative path like `data/input.csv` is normally resolved against this directory when using `Path`/`File` APIs.
- **File path (filesystem path)**: the address of an item on the filesystem, which may be an absolute path (`/opt/app/data/a.csv`) or a relative path (`./data/a.csv`).

**Key takeaway:** `classpath:...` and `file:...` point to two different source types in Spring's `Resource` abstraction. A resource may be discoverable on the classpath while **not existing at all as a standalone file** on the filesystem once the application is packaged as an executable JAR.

## 2. An Illustrative Project Structure

Suppose a project has the structure:

~~~text
catalog-service/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/catalog/
│       │   └── CatalogApplication.java
│       └── resources/
│           ├── application.yml
│           └── templates/
│               └── welcome.txt
├── config/
│   └── overrides.yml
└── data/
    └── incoming.csv
~~~

During development in an IDE, the following three files may all exist on disk:

1. `src/main/resources/templates/welcome.txt`: a source resource that will be placed onto the **classpath** after building; inside the JAR, it usually no longer retains the `src/main/resources` prefix.
2. `config/overrides.yml`: a file outside `src/main/resources`, read only when the application is given the proper filesystem path or loading configuration.
3. `data/incoming.csv`: a data file outside the application; `Path.of("data/incoming.csv")` accesses it based on the process's working directory.

After packaging, it might be deployed as:

~~~text
/opt/catalog/
├── catalog-service.jar
├── config/
│   └── application.yml
└── data/
    └── incoming.csv
~~~

Inside the JAR, `templates/welcome.txt` remains a classpath resource. Meanwhile, `/opt/catalog/config/application.yml` and `/opt/catalog/data/incoming.csv` are filesystem files outside the JAR.

## 3. Classpath: Resources Found by the ClassLoader

### 3.1. `src/main/resources` is a development-time source directory

With Maven or Gradle, the contents of `src/main/resources` are typically copied into the build's resources output and then packaged into the JAR.

For example, the file:

~~~text
src/main/resources/templates/welcome.txt
~~~

is normally accessed at runtime using the classpath path:

~~~text
classpath:templates/welcome.txt
~~~

Do not use `classpath:src/main/resources/templates/welcome.txt`. After building, classpath paths must be resolved from the **classpath root**, not from the repository root.

The classpath is not synonymous with a single directory. It can include multiple directories, multiple dependency JARs, and locations managed by the class loader; a Spring Boot executable JAR also has its own packaging layout (typically `BOOT-INF/classes` and `BOOT-INF/lib`).

### 3.2. Reading a classpath resource with Spring `Resource`

Example using Spring's `ResourceLoader`:

~~~java
package com.example.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class WelcomeTemplateService {

    private final ResourceLoader resourceLoader;

    public WelcomeTemplateService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String loadTemplate() throws IOException {
        Resource resource = resourceLoader.getResource(
                "classpath:templates/welcome.txt");

        try (InputStream stream = resource.getInputStream()) {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

A resource can be injected directly:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class TemplateResourceHolder {
    private final Resource template;

    public TemplateResourceHolder(
            @Value("classpath:templates/welcome.txt") Resource template) {
        this.template = template;
    }

    public Resource template() {
        return template;
    }
}
~~~

When you need the content, call `template.getInputStream()` and close the stream after use. This approach generally works in both the IDE and an executable JAR.

### 3.3. Why can `getFile()` work in the IDE but fail when running the JAR?

An error-prone example:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:templates/welcome.txt");

// Do not assume a classpath resource always corresponds to a File on disk.
File file = resource.getFile();
~~~

In the IDE, the resource may live under a directory like `target/classes` or `build/resources/main`, so this call sometimes succeeds. When packaged in a JAR, the resource is **inside an archive** and no longer corresponds to a standalone `java.io.File`. At that point `getFile()` can throw `FileNotFoundException` or a similar error.

To **read** a packaged resource, prefer `getInputStream()`. Only use `getFile()` when business requirements and deployment guarantees ensure the resource is truly a file outside an archive.

### 3.4. ClassLoader API in plain Java

Without Spring, Java can also read resources:

~~~java
try (InputStream in = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("templates/welcome.txt")) {

    if (in == null) {
        throw new IllegalStateException("Could not find welcome.txt");
    }

    String content = new String(
            in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

`ClassLoader.getResourceAsStream(...)` takes a resource name without the `classpath:` prefix and usually without a leading `/`. `Class.getResourceAsStream(...)` has different rules: a name without a leading `/` is relative to the class's package; a name starting with `/` is resolved from the classpath root. Choose a clear naming convention to avoid path mistakes.

Spring also supports `classpath*:` in APIs that find **multiple** resources, such as `ResourcePatternResolver`; this is not a filesystem path and does not mean exactly one resource will be returned.

## 4. Working Directory: The Current Directory of the Java Process

### 4.1. `user.dir` is not the JAR's directory by default

The working directory typically depends on **where and how the process is started**: where the terminal is located, the IDE's Run/Debug configuration, `WORKDIR` in Docker, `workingDir` in Kubernetes, or the service manager's working directory.

For example, the same JAR run in different ways:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar
~~~

Here, the relative path `./data/incoming.csv` is normally resolved to `/opt/catalog/data/incoming.csv`.

If you run:

~~~bash
cd /tmp
java -jar /opt/catalog/catalog-service.jar
~~~

then `./data/incoming.csv` normally points to `/tmp/data/incoming.csv`, **not** `/opt/catalog/data/incoming.csv`. The location of the JAR file does not automatically determine the working directory.

In Java:

~~~java
import java.nio.file.Path;

Path workingDirectory = Path.of("")
        .toAbsolutePath()
        .normalize();

System.out.println("user.dir = " + System.getProperty("user.dir"));
System.out.println("Working directory = " + workingDirectory);
~~~

These two values usually reflect the process's working directory at startup. They are helpful for diagnostics, but should not be relied upon as a fixed assumption about deployment.

### 4.2. Reading a relative path with `java.nio.file`

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExternalFileReader {

    public String loadIncomingCsv() throws IOException {
        Path path = Path.of("data", "incoming.csv");

        // The actual path the application is trying to open.
        Path resolved = path.toAbsolutePath().normalize();

        System.out.println("Reading from: " + resolved);
        return Files.readString(path, StandardCharsets.UTF_8);
    }
}
~~~

`Path.of("data", "incoming.csv")` does not use a ClassLoader. It describes a file on the filesystem according to the OS rules and the working directory. If the file does not exist at the resolved location, reading will fail even if a resource with the same name exists on the classpath.

To reduce the risk of bugs caused by a changing working directory, obtain the data directory from explicit configuration and combine it with the file name:

~~~properties
catalog.storage-dir=/var/lib/catalog
~~~

~~~java
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogPaths {

    private final Path storageDir;

    public CatalogPaths(@Value("${catalog.storage-dir}") String value) {
        this.storageDir = Path.of(value).toAbsolutePath().normalize();
    }

    public Path incoming() {
        return storageDir.resolve("incoming.csv");
    }
}
~~~

The path `/var/lib/catalog` is just a Unix/Linux example; on Windows or other environments, use an appropriate path. `toAbsolutePath().normalize()` normalizes the syntax, but does not check whether the file exists or eliminate all security risks when joining paths from untrusted input.

## 5. File Paths: Absolute and Relative

| Form | Example | Meaning |
| --- | --- | --- |
| Relative | `data/input.csv` | Resolved against the working directory when using `Path`/`File` |
| Relative with `./` | `./config/application.yml` | Same principle; `./` emphasizes starting from the current directory |
| Absolute on Linux | `/etc/catalog/application.yml` | Full location on the Linux filesystem; independent of working directory |
| Absolute on Windows | `C:\apps\catalog\config\application.yml` | Windows filesystem location; not a cross-OS path |
| URI in Spring | `file:./config/application.yml` | Spring `Resource` reading a file relative to the working directory |
| URI in Spring | `file:/opt/catalog/config/application.yml` | Spring `Resource` reading a file at the corresponding absolute location |
| URI in Spring | `classpath:application.yml` | Spring finding a resource on the classpath; not a filesystem path |

In a Java string literal, the `\` character in a Windows path must be escaped, e.g., `"C:\\apps\\catalog\\config\\application.yml"`. The `Path.of(...)` API helps handle OS-specific paths; when obtaining a path from environment variables or configuration, avoid manually concatenating `/` or `\` strings when `resolve(...)` can be used.

### 5.1. `file:` specifies a filesystem source for Spring Resource

In Spring:

~~~java
Resource external = resourceLoader.getResource(
        "file:./config/overrides.yml");

try (InputStream in = external.getInputStream()) {
    // Read from a file outside the JAR.
}
~~~

Here `file:./config/overrides.yml` describes a file on the filesystem, resolved from the working directory when the path is relative. It is not automatically packaged into the JAR.

If you already have a `Path`, you can read it directly with `Files` or use `FileSystemResource`:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Path path = Path.of("/opt/catalog/config/overrides.yml");
Resource resource = new FileSystemResource(path);
~~~

Choose the API based on your needs: `Resource` is convenient when working with multiple location types in Spring; `Path`/`Files` is suitable when the target is always a filesystem file and you need operations such as checking attributes, writing, or moving.

### 5.2. Files packaged in the JAR cannot be rewritten like regular data files

Resources in `src/main/resources` become data **inside the artifact** after building. They are suited for shipping default content, not for storing runtime writes. For user-uploaded files, exports, caches, or mutable configuration, use the filesystem outside the JAR, a volume/container mount, or an appropriate storage service.

This deployment pattern also lets you update data without rebuilding and redeploying the application.

## 6. Direct Connection to Spring Boot Externalized Configuration

Spring Boot has its own **config data discovery mechanism** (`application.properties`, `application.yml`, profile-specific variants, `spring.config.import`, etc.). This mechanism uses both the classpath and the filesystem; do not confuse it with reading an arbitrary resource via `ResourceLoader`.

### 6.1. Where does Spring Boot look for `application.*` by default?

With standard startup, Spring Boot searches for config data in default locations, including:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

The `./` in `file:` locations depends on the working directory. The `config/*/` pattern supports matching direct subdirectories inside the external `config` directory. Location order and configuration merge/override rules are handled by Spring Boot's config data mechanism, including profile-specific documents.

For example:

~~~text
catalog-service.jar
config/
  application.yml
~~~

If the JAR is run with the working directory at the same level as `config/`, Spring Boot can find `./config/application.yml` via the default mechanism. If run from another directory, the `./config` path changes as well.

Among the default config data sources, locations outside the JAR normally take precedence over the `application.yml` packaged inside the JAR. However, the **final configuration value** also depends on profiles, imports, environment variables, system properties, and command-line arguments; you cannot deduce the value merely by looking at the file location.

### 6.2. Using `spring.config.location` and `spring.config.additional-location`

If configuration must be placed at an explicit location, it can be passed at startup:

~~~bash
java -jar catalog-service.jar \
  --spring.config.additional-location=optional:file:/etc/catalog/
~~~

In this example:

- `spring.config.additional-location` **adds** the location to the default search set.
- `optional:` allows a non-existent location to be skipped.
- The directory path ends with `/` so Spring Boot appends names such as `application.yml`.
- An external location added later in the location-addition mechanism can override default configuration according to config data rules.

If you use:

~~~bash
java -jar catalog-service.jar \
  --spring.config.location=optional:file:/etc/catalog/
~~~

then `spring.config.location` **replaces** the default locations used to search for config data, rather than merely adding to them. When multiple locations are needed, declare them explicitly in the syntax supported by Spring Boot.

Properties that determine **where to search for configuration** such as `spring.config.location`, `spring.config.additional-location`, and `spring.config.name` must be present very early at startup (such as environment variables, system properties, or CLI arguments), because Boot uses them before loading the corresponding config data files. Do not expect declaring `spring.config.location` inside the very file that needs to be discovered to help Boot locate that file.

### 6.3. Using `spring.config.import` once a configuration file has been found

For example, inside an `application.yml` already loaded by Spring Boot:

~~~yaml
spring:
  config:
    import: "optional:file:./config/overrides.yml"

catalog:
  greeting: "Welcome"
~~~

`spring.config.import` declares an additional config data source. If the file exists in the appropriate working directory, the properties imported from it participate in Spring Boot's precedence mechanism. If it does not exist, `optional:` avoids a missing-file error. For critical configuration that must be present, consider omitting `optional:` so startup fails clearly when the file is missing.

Distinguish:

- `ResourceLoader.getResource("file:...")` only creates an object to **read a resource** on demand in code.
- `spring.config.import=...` instructs Spring Boot to **load the file as config data**, participating in configuration resolution through `Environment`.
- `@Value("${catalog.greeting}")` or `@ConfigurationProperties` reads the **resolved value** from `Environment`, rather than directly opening a filesystem path.

### 6.4. What if the file is not named `application.yml`?

The file `config/overrides.yml` is not automatically loaded by Boot just because it sits in `./config/`. Default discovery is primarily based on the name `application` and profile variants. To use a custom name such as `overrides.yml`, declare `spring.config.import` or specify an explicit file location. Likewise, `templates/welcome.txt` on the classpath does not automatically become a property source.

## 7. Example Comparing the Same Resource Name

Suppose there are two files both named `banner.txt`:

~~~text
src/main/resources/templates/banner.txt     (Content A: packaged)
./templates/banner.txt                      (Content B: external)
~~~

Snippet 1:

~~~java
Resource packaged = resourceLoader.getResource(
        "classpath:templates/banner.txt");
~~~

Snippet 2:

~~~java
Resource external = resourceLoader.getResource(
        "file:./templates/banner.txt");
~~~

If both are present, Snippet 1 reads **A** while Snippet 2 reads **B**. Having two files with the same name does not make Spring automatically prioritize one file for all APIs; the **location prefix/mechanism** determines which content is opened.

Snippet 3:

~~~java
Path path = Path.of("templates", "banner.txt");
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Snippet 3 also reads file **B** if the working directory contains the matching `templates` directory. If you change the working directory without changing the JAR file, Snippet 1 typically still reads A, while Snippets 2 and 3 may fail to find B.

Common scenario: a developer runs from the IDE with the working directory set to the project root, so `Path.of("src/main/resources/templates/banner.txt")` succeeds. After packaging and deploying only the JAR to a server, the `src/main/resources` directory is no longer there. The code fails even though the classpath resource was packaged properly. Use `classpath:templates/banner.txt` with `getInputStream()` to read such content.

## 8. Choosing How to Load Files by Use Case

| Need | Recommended Option | Notes |
| --- | --- | --- |
| Email templates, sample data, immutable resources packaged in the app | `classpath:...` and `Resource.getInputStream()` | Works even when the resource is inside a JAR |
| Reading a user data file placed on the machine/container | `Path`/`Files` or `file:...` | Put the base directory in deployment configuration |
| Reading a file relative to the current directory | `Path.of("relative/path")` or `file:./...` | The working directory must be declared/well understood |
| Reading a file at an absolute location | `Path.of("/path/...")` or `file:/path/...` | Depends on OS and access permissions |
| Loading additional configuration for Spring Boot `Environment` | `spring.config.import` or `spring.config.*` properties | Follows Boot's search, profile, and precedence rules |
| Writing files at runtime | Filesystem/volume/object storage outside the JAR | Do not write back into classpath resources inside a JAR |
| Looking up multiple classpath resources by pattern | `ResourcePatternResolver` and when appropriate `classpath*:` | Must handle multiple results and possible name collisions |

In production, an absolute path supplied by deployment via an environment variable or config is usually easier to control than assuming the working directory. Relative paths can be used, but the startup directory of the service/container must be explicitly defined.

## 9. Diagnosing File-Not-Found Errors

When encountering `FileNotFoundException`, `NoSuchFileException`, or similar resource errors, check in order:

1. **Which API is the code using?** `ResourceLoader("classpath:...")`, `ResourceLoader("file:...")`, `Path.of(...)`, or `ClassLoader.getResourceAsStream(...)`. Each API resolves paths differently.
2. **Is the resource name resolved properly from the classpath root?** For `src/main/resources/templates/welcome.txt`, typically use `classpath:templates/welcome.txt`.
3. **What is the process's working directory?** Check `user.dir` and `Path.of("").toAbsolutePath().normalize()` in the exact environment that is failing.
4. **Is the file packaged or mounted in the right place?** For classpath, inspect the artifact; for the filesystem, check the external file and deployment paths.
5. **Are you trying to obtain a `File` from a resource inside a JAR?** If you only need to read it, switch to `getInputStream()`.
6. **Are you confusing a resource with config data?** Having `custom.yml` does not mean Boot automatically loads its properties.
7. **Are permissions and letter casing different?** Linux is typically case-sensitive for file names; check permissions and container mounts.

Example checking the exact location of a file outside the JAR:

~~~java
Path relativePath = Path.of("data", "incoming.csv");
Path absolutePath = relativePath.toAbsolutePath().normalize();

System.out.println("Working directory: "
        + Path.of("").toAbsolutePath().normalize());
System.out.println("Expected data path: " + absolutePath);
System.out.println("Exists: " + Files.exists(absolutePath));
System.out.println("Readable: " + Files.isReadable(absolutePath));
~~~

Print only non-sensitive paths for diagnostics; avoid logging contents of secret files or tokens. `Files.exists` and `Files.isReadable` are useful for observation, but do not replace exception handling on the actual read operation, because the filesystem can change between check time and use time.

### Common Misconceptions

**"A file in `src/main/resources` can be opened with `new File("src/main/resources/...")` when deployed."** Unreliable. That is the project's source-code path, not the runtime location of packaged resources.

**"`classpath:config/app.yml` is the same as `./config/app.yml`."** Incorrect. The first searches the classpath; the second searches the filesystem relative to the working directory.

**"Running `java -jar /opt/app/app.jar` makes `/opt/app` the working directory."** Not true by default. The working directory belongs to the invoking process and may differ from the JAR's directory.

**"Having `custom.yml` in `./config/` makes Boot load it automatically."** Not by default. The `application.*` search mechanism and `spring.config.*` declarations decide which specific configuration files are loaded.

**"`Resource.getFile()` is the universal API for reading resources."** False. When a resource resides inside a JAR, the appropriate way to read it is typically `getInputStream()`.

## 10. Hands-On Exercises

### Exercise A: resource inside the JAR

Create `src/main/resources/templates/hello.txt` with content `Hello from classpath`. Write a service that reads it with `classpath:templates/hello.txt` and `getInputStream()`. Run from the IDE, then package as an executable JAR and run again. Observe that the content can still be read even without the project's `src` directory at the execution site.

### Exercise B: same JAR, two working directories

Place an external file at `/opt/catalog/data/demo.txt`. Run the application from `/opt/catalog` and then run again from `/tmp`, using `Path.of("data/demo.txt")` to read it. Compare `user.dir`, the resolved absolute path, and the read outcome. Finally, switch to an explicitly configured absolute path so it no longer depends on the current directory.

### Exercise C: Boot config data

Set `catalog.mode=internal` in `src/main/resources/application.properties` and `catalog.mode=external` in `./config/application.properties`. Run the JAR with the working directory containing that `config` directory. Read `catalog.mode` via `Environment` or `@Value`. Then change the working directory and observe the change. Try using `--spring.config.additional-location=optional:file:/external-path/` pointing to an appropriate external directory.

### Exercise D: distinguishing a regular file from a configuration source

Create `./config/extra.yml` containing a key not present in `application.yml`. Try reading the file via `ResourceLoader("file:./config/extra.yml")`, then reading the key with `Environment.getProperty(...)`. Next, declare `spring.config.import=optional:file:./config/extra.yml` in `application.yml` and compare the result. From this, distinguish **reading a file** from **bringing a file's data into Spring configuration**.

## 11. Takeaways

- **Classpath** locates resources via the ClassLoader; resources inside a JAR should be read via streams.
- **Working directory** is the process's context; relative filesystem paths depend on this context, not by default on the JAR's location.
- **File path** describes a location on the filesystem; `Path`/`Files` works with real files, while Spring `Resource` supports both `classpath:` and `file:`.
- **Spring Boot config data** has its own search and precedence rules: `classpath:/...` and `file:./...` are distinct locations, and `spring.config.location`/`spring.config.additional-location`/`spring.config.import` control configuration loading.
- Resilient design: default resources ship with the application; mutable data or configuration is stored externally with explicit deployment paths.

## References

- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `Resource`, `ResourceLoader`, classpath resources, and filesystem resources.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): config data, `application.*` search locations, and `spring.config.*`.
- [Java SE — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): classpath resource lookup.
- [Java SE — Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): relative/absolute paths and filesystem APIs.