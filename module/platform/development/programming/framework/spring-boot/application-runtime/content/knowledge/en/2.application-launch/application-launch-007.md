# Impact of Classpath, Working Directory, and ResourceLoader When Launching Spring Boot

## 1. Why Does the Same Application Find a Resource on One Machine but Not Another?

A Spring Boot application may read a file successfully when run in an IDE, yet report `FileNotFoundException` when run with `java -jar` or inside a container. The cause usually lies not in the file's contents, but in **how the file's location is resolved**. Three concepts must be separated:

1. **Runtime classpath** is the set of directories containing compiled classes, resources, and libraries that the Java classloader can search. Resources packaged with the application are normally located via the classpath.
2. **Working directory** is the current directory of the **Java process** at launch time. Relative file paths like `config/message.txt` are normally resolved from here, not from the directory containing the JAR.
3. **Spring's `ResourceLoader`** is the mechanism that turns a location string into a `Resource` object. Prefixes such as `classpath:` or `file:` determine where to look; without a prefix, the result also depends on the `ResourceLoader` implementation and application context.

Remember: **paths in source code, resource paths on the classpath, OS filesystem paths, and the JAR's location are all different things**.

| Access Method | Where It Searches | Depends on Working Directory? |
| --- | --- | --- |
| `new ClassPathResource("demo/message.txt")` | Runtime classpath | Usually no, once classpath is properly set up |
| `resourceLoader.getResource("classpath:demo/message.txt")` | Runtime classpath | Usually no, with the same classpath |
| `Path.of("config/message.txt")` | Filesystem, relative to working directory | Yes |
| `resourceLoader.getResource("file:./config/message.txt")` | Filesystem, relative to working directory | Yes |
| `resourceLoader.getResource("file:/opt/demo/config/message.txt")` | Absolute path on Unix/Linux systems | No |
| `resourceLoader.getResource("demo/message.txt")` | Relative location per `ResourceLoader` type | Should not be assumed to be classpath or working directory |

The `./` prefix means the current directory in the path resolution context. It does not mean "next to the `.jar` file."

## 2. How Is the Classpath Formed During Build and Run?

Suppose the project has this structure:

```text
src/
  main/
    java/
      demo/runtime/RuntimePathsApplication.java
    resources/
      demo/message.txt
      application.properties
config/
  message.txt
```

Here:

- `src/main/java` is Java source code. During build, it is compiled into `.class` files.
- `src/main/resources/demo/message.txt` is an application resource. Gradle or Maven copies it to the resource output so it can be looked up by classpath name `demo/message.txt`.
- `config/message.txt` sits **outside** `src/main/resources`. It is a filesystem file; it is only found if the path and working directory match, or if packaging is separately configured.
- `src/test/resources` is normally added to the classpath only when running tests. Never rely on files present only in `src/test/resources` for the packaged application outside test runs.

For an executable Spring Boot JAR built by the `bootJar` task, the layout typically looks like:

```text
demo.jar
  BOOT-INF/
    classes/
      demo/runtime/RuntimePathsApplication.class
      demo/message.txt
      application.properties
    lib/
      ...dependency-libraries.jar
```

Spring Boot's classloader can read resources under `BOOT-INF/classes` and nested libraries inside the JAR. Thus `classpath:demo/message.txt` remains valid when running the JAR, even though there is no real `src/main/resources` folder on the deployment machine.

However, the classpath is **determined at launch time**. If you use `java -cp` with relative classpath entries, changing the working directory can cause Java to look in the wrong directory or libraries from the start. With an executable Boot JAR invoked via a valid path with `java -jar`, Spring Boot builds the classpath from the JAR structure itself. Distinguish **what affects how the classpath is constructed** from **how a resource is resolved once the classpath is ready**.

A common mistake is:

```java
// This only points to the source directory in some development environments:
Path sourcePath = Path.of("src/main/resources/demo/message.txt");
```

That path is not a classpath name. When running the packaged JAR in another directory, the `src/main/resources` tree usually does not exist. For internal resources, use `classpath:demo/message.txt` and read via an input stream.

## 3. Working Directory Differs from the Directory Containing the JAR

Consider the same `/opt/demo/app.jar` file invoked in two ways:

```bash
cd /opt/demo
java -jar /opt/demo/app.jar
```

In this run, `file:./config/message.txt` resolves to `/opt/demo/config/message.txt`.

```bash
cd /tmp
java -jar /opt/demo/app.jar
```

In this run, the exact same string `file:./config/message.txt` resolves to `/tmp/config/message.txt`. The JAR's location did not change at all.

In Java, you can observe the working directory with:

```java
System.out.println(Path.of("").toAbsolutePath().normalize());
System.out.println(System.getProperty("user.dir"));
```

The displayed value depends on how the process was launched: IDE run configuration, terminal, Gradle `bootRun`, OS service configuration, or `WORKDIR` in Docker. **Do not assume** every tool sets the working directory to the project directory. Check the actual output when diagnosing.

If you need to read a file sitting next to the JAR, **explicitly determine the directory containing the JAR**, such as via Spring Boot's `ApplicationHome` mechanism or a dedicated configuration path. Do not use `./` to implicitly assume the JAR's location. A more controllable operational solution is usually passing an absolute file path through deployment configuration.

## 4. How Does ResourceLoader Resolve Location Strings?

Spring provides the `Resource` interface as an abstraction over various data sources and the `ResourceLoader` interface to look up resources by location:

```java
Resource internal = resourceLoader.getResource("classpath:demo/message.txt");
Resource external = resourceLoader.getResource("file:./config/message.txt");
```

Important forms:

- **`classpath:`**: requests a resource from the classpath. This is suited for templates, static data, and read-only resources packaged inside the application.
- **`file:`**: requests a resource from the filesystem. The path can be relative to the working directory or absolute; suited for operations-supplied data, external configuration, and files with a lifecycle independent of the build.
- **`https:` / `http:`**: depending on the resource loading mechanism, may create a URL resource and initiate a network connection when read. Never take arbitrary URLs from untrusted input.
- **No prefix**: behavior depends on the specific `ResourceLoader`. For example, `DefaultResourceLoader` resolves relative locations differently from a `WebApplicationContext` rooted at a servlet context. Always include a prefix to make intent explicit.

Common implementation classes are `ClassPathResource`, `FileSystemResource`, `UrlResource`, and `ServletContextResource`. When code only needs to read, accept `Resource` instead of depending on a concrete implementation type.

`Resource` provides operations such as `exists()`, `isReadable()`, `getInputStream()`, `getURL()`, and `getDescription()`. **`getFile()` is not always usable**: a resource inside a JAR does not necessarily exist as an individual file on the filesystem, so `ClassPathResource#getFile()` may work when running from the build directory but fail once packaged into a JAR.

```java
// Prefer a reading approach that works even when the resource is inside a JAR:
try (InputStream input = resource.getInputStream()) {
    byte[] bytes = input.readAllBytes();
    // Process bytes according to the resource's format.
}
```

Do not use `resource.getFile().toPath()` just to read a classpath file. Open a fresh stream each time and close it with `try-with-resources`. Resources packaged inside a JAR are also not an appropriate place to write data that changes while the application runs.

If you need to find **multiple** resources matching a pattern across JARs, use `ResourcePatternResolver#getResources("classpath*:...")`; `ResourceLoader#getResource(...)` returns only a single `Resource` for one location. When files with the same name exist across multiple classpath entries, which "first match" is picked can depend on classpath order; avoid duplicate names if predictability matters.

## 5. Runnable Spring Boot 3.x Example

Create a Spring Boot 3.x project using Java 17 or higher with the `spring-boot-starter` dependency. Place `src/main/java/demo/runtime/RuntimePathsApplication.java`:

```java
package demo.runtime;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@SpringBootApplication
public class RuntimePathsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimePathsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectResources(ResourceLoader loader) {
        return args -> {
            System.out.println("cwd=" + Path.of("").toAbsolutePath().normalize());

            printResource("classpath",
                    loader.getResource("classpath:demo/message.txt"));
            printResource("file",
                    loader.getResource("file:./config/message.txt"));
        };
    }

    private static void printResource(String label, Resource resource)
            throws IOException {
        System.out.println(label + " exists=" + resource.exists());
        if (!resource.exists() || !resource.isReadable()) {
            return;
        }

        try (InputStream input = resource.getInputStream()) {
            String content = new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            System.out.println(label + " content=" + content);
        }
    }
}
```

Create `src/main/resources/demo/message.txt` with content:

```text
Hello from classpath
```

Also create `config/message.txt` at the **project root** with content:

```text
Hello from working directory
```

When running from the project root, if the working directory is indeed the project root and the external file exists, the relevant output will look like:

```text
cwd=<project-root-path>
classpath exists=true
classpath content=Hello from classpath
file exists=true
file content=Hello from working directory
```

The `cwd=...` line is illustrative; the actual path is printed by the program. Besides these lines, Spring Boot also outputs startup logs.

Package with `./gradlew bootJar` in a Gradle project with the Spring Boot plugin, then run the generated JAR from `build/libs/`. If you run from a directory that does not contain `config/message.txt` while supplying the right path to the JAR, the main output will be:

```text
classpath exists=true
classpath content=Hello from classpath
file exists=false
```

This example proves that **the same application can find a resource inside the JAR while failing to find the external file when the working directory changes**. `file exists=false` only holds when the corresponding file genuinely does not exist in the new working directory.

To see which resource is being resolved, you can add `resource.getDescription()` to diagnostic logs. Never print raw contents of sensitive files, passwords, or tokens in real applications.

## 6. Choosing the Right Access Method by Purpose

**Internal resources tied to the release:** templates, sample images, non-secret default configs, and source-coupled assets belong in `src/main/resources` and should be read via `classpath:`. When a new version is released, their content updates with the artifact.

**Operations-supplied files or files that can change after deployment:** certificate files, volume-mounted data, report output directories, and downloaded assets belong outside the JAR. Declare their locations via environment variables, launch arguments, or application configuration; clarify whether paths are absolute or relative. Control process permissions accordingly.

**Paths in Java code:** for OS file operations use `Path` / `Files`, for example:

```java
Path configDir = Path.of("/opt/demo/config");
Path settingsFile = configDir.resolve("settings.json");
String settings = Files.readString(settingsFile, StandardCharsets.UTF_8);
```

This snippet illustrates filesystem operations assuming the file exists; it is not a classpath reading example. If configuration passed from outside uses prefixed strings like `classpath:`, `file:`, or a URL, `ResourceLoader` unifies reading. If the application needs to **write** data, use filesystem APIs and a writable path; never write into classpath resources.

**Relative files without a prefix:** avoid writing `loader.getResource("config/message.txt")` and assuming it equals `file:./config/message.txt`. Explicitly write `file:` when you need the filesystem, or `classpath:` when you need a packaged resource.

## 7. Relation to application.properties and Startup Configuration

Spring Boot has its own **Config Data mechanism** to load `application.properties` / `application.yml`. This mechanism searches multiple default locations, including classpath locations and external locations relative to the working directory, such as `./` and `./config/`. Eligible external config sources can override keys of the same name inside the JAR according to Spring Boot's precedence order.

Consequently, when moving from an IDE to a JAR or container, an application can **change configuration values** even though the packaged `application.properties` stays identical: a new working directory may cause Spring Boot to find or miss an external config file. This is Spring Boot's configuration loading rule; it **does not mean** every `ResourceLoader#getResource(...)` call applies the Config Data precedence chain.

For example, to supply an additional fixed external config directory at startup:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/demo/
```

The directory is a Unix/Linux example. `additional-location` adds search locations; `spring.config.location` can replace the default set of locations, so do not treat these two properties as interchangeable. The `optional:` prefix allows a missing location without failing configuration loading solely because that location does not exist. Some location configuration properties must be available early in startup (such as command-line arguments or environment variables).

Key differences to remember:

- `classpath:application.properties`: describes a resource on the classpath.
- `file:./config/application.properties`: describes a file relative to the working directory.
- **Selecting and merging configuration sources** is the responsibility of Spring Boot's Config Data, with its own precedence order.
- **Explicitly reading a resource in application code** is the responsibility of code using `Resource` / `ResourceLoader`.

## 8. Common Errors and Root-Cause Diagnosis

| Symptom | Likely Cause to Check | Resolution |
| --- | --- | --- |
| Works in IDE, JAR reports `src/main/resources/...` not found | Used a source-tree path as a runtime filesystem path | Place resource in `src/main/resources` and access via `classpath:...` |
| `ClassPathResource#getFile()` fails in JAR | Resource is a JAR entry, not a standalone file | Read via `getInputStream()` instead of forcing conversion to `File` |
| Running the same JAR from different directories gives different results | `file:./...`, `Path.of("...")`, or external config depends on working directory | Check `Path.of("").toAbsolutePath()`, pass absolute paths, or configure working directory explicitly |
| Docker run misses files present on dev machine | External file not copied/mounted; `WORKDIR` differs | Check `WORKDIR`, volume mounts, file location, and read permissions in container |
| Resource name works on Windows but fails on Linux | Case sensitivity differences in filename or path | Verify exact filename and casing inside the artifact |
| Tests have the resource but release build lacks it | Resource only exists in `src/test/resources` | Move release resources into `src/main/resources` |
| Configuration appears changed after deployment | External `application.properties` has higher precedence or lookup locations shifted with cwd | Check active property sources, startup arguments, and Config Data locations |
| Unprefixed string yields unexpected result | `ResourceLoader` implementation determines meaning of relative path | Specify `classpath:` or `file:` explicitly |

Ordered diagnostic checklist:

1. Determine whether the expected resource is **classpath** or **filesystem**. Record the full location string including prefix.
2. Print the process's actual working directory and `resource.getDescription()`; check `exists()` / `isReadable()`. If reading fails, log the exact exception from `getInputStream()`.
3. If it is a classpath resource, inspect the artifact: you can run `jar tf build/libs/your-app.jar` to check whether the resource lies under `BOOT-INF/classes/`; check how the runtime classpath is built if launching with `-cp`.
4. If it is an external file, check the absolute path, read permissions, volume mounts, working directory, and launch configuration. Never infer the working directory from the JAR's location.
5. If the issue involves `application.properties`, check Config Data source ordering and properties like `spring.config.location` / `spring.config.additional-location` before altering resource-reading code.

Avoid fixing path issues by mutating `System.setProperty("user.dir", ...)` while the application is running. Many APIs and components already resolve paths based on prior context; configuring the process working directory or using explicit absolute paths gives far more consistent behavior.

## 9. Pre-Deployment Verification Practice

Perform three small experiments yourself on the example from section 5:

1. **Keep the artifact fixed, change working directory:** run the JAR from two different directories. Compare `cwd` and the results of both resources. Explain why `classpath` still reads cleanly while `file:./...` changes.
2. **Keep working directory fixed, remove external file:** rename `config/message.txt` and run again. `classpath` should still succeed; the `file` resource must report nonexistent. Restore the file after testing.
3. **Inspect JAR structure:** check whether `demo/message.txt` is packaged under `BOOT-INF/classes/demo/message.txt`. If missing, fix the build configuration or resource source location—do not replace the resource name with a `src/main/resources` path in deployment.

When writing tests, create external files in an isolated temporary directory (such as JUnit `@TempDir`) and pass the known path to the code under test. This prevents tests from passing accidentally only because the IDE and Gradle share the same working directory.

## 10. Principles to Maintain in the Codebase

- Choose where to store resources by lifecycle: **packaged and fixed** belongs on the classpath; **environment-varying** belongs on the filesystem or external storage.
- With Spring `ResourceLoader`, **write explicit prefixes** so lookup locations are clear and do not implicitly depend on context.
- For resources in a JAR, **read via InputStream**; use `File`/`Path` only when an actual filesystem file exists.
- When using relative paths, identify and test the **working directory** of each launch method (IDE, Gradle, JAR, container, service).
- For Spring Boot configuration, distinguish **Config Data loading** from **manual Resource reading**, and control external config sources that could override configuration inside the JAR.

Understanding these three concepts makes Spring Boot launches reproducible between development and deployment, and lets you quickly pinpoint whether an issue stems from packaging, classpath, working directory, or resource resolution.
