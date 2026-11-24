# Organizing Resources and Configuration to Run Consistently from IDE and JAR

In a first Spring Boot project, an application might successfully read a file when launched via the **Run** button in an IDE, yet report the file missing after being packaged as a JAR. Sometimes `application.yml` works in the IDE while configuration behaves differently when running `java -jar`; other times the application writes a file successfully yet cannot find the newly created file.

These situations usually relate to source code organization and three distinct concepts: **resources packaged on the classpath**, **configuration loaded by Spring Boot from multiple sources**, and **filesystem paths dependent on the runtime environment**. The goal of this lesson in **Source Organization** is to design a Spring Boot application so that whatever belongs to the artifact behaves identically in both IDE and JAR, while whatever belongs to the environment is configured explicitly.

## 1. Four Concepts to Distinguish

| Concept | Meaning | Example |
|---|---|---|
| Source resource | File placed in the project layout for the build tool to copy into runtime output | `src/main/resources/messages/welcome.txt` |
| Classpath resource | File looked up by name relative to the classpath root | `classpath:messages/welcome.txt` |
| External file | File existing on the filesystem, outside the application artifact | `/etc/demo/application.yml`, `C:/demo/data/report.txt` |
| Working directory | Current directory of the JVM process, used as the base for relative paths | `./config`, `./data` |

Compare these two paths:

```text
classpath:messages/welcome.txt
./messages/welcome.txt
```

The first line requests looking up a resource using the class loader; the physical backing can be an output directory in the IDE or an entry inside a JAR. The second line points to a **file on the filesystem**, relative to the working directory. It is not automatically converted into a path inside the JAR.

The question that decides how to organize a file is: **is this file shipped with the application release, or does it need to change independently of the application release?**

- Files shipped with the build and primarily read-only: place in `src/main/resources`.
- Generated data, user-uploaded files, or deployment environment configs: store or supply outside the JAR.
- Java code reading packaged resources: use classpath APIs.
- Java code writing files: use filesystem APIs with a configured storage directory.

## 2. A Maintainable Spring Boot Project Structure

Common layout with Maven or Gradle:

```text
demo/
├── build.gradle                  # Or pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/demo/
│   │   │       ├── DemoApplication.java
│   │   │       ├── config/AppProperties.java
│   │   │       ├── service/WelcomeTextService.java
│   │   │       └── web/WelcomeController.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-dev.yml
│   │       ├── application-prod.yml
│   │       ├── messages/
│   │       │   └── welcome.txt
│   │       ├── static/
│   │       │   └── css/site.css
│   │       └── templates/
│   │           └── home.html
│   └── test/
│       ├── java/
│       └── resources/
│           └── application-test.yml
└── README.md
```

**`src/main/java`** holds Java source code with appropriate packages. **`src/main/resources`** holds resources placed onto the runtime classpath. **`src/test/resources`** serves tests and is normally excluded from production artifacts.

### 2.1. Why Not Put Writable Data into `src/main/resources`?

A common mistake is using the source directory as an upload destination:

```java
Path uploadDir = Path.of("src/main/resources/static/uploads");
```

This path only makes sense when the application runs where the source tree still exists. Once the JAR is released, operators may not even have a `src` directory. Even if one exists, writing to the source tree does not update resources already packaged inside the running artifact.

Packaged resources fit templates, default configurations, sample texts, and static assets. Uploaded files, caches, generated reports, or user-mutable files must be stored externally.

### 2.2. Build Tool Output Can Differ from the Source Tree

With the Gradle Java plugin, a typical output layout is:

```text
build/
├── classes/java/main/
│   └── com/example/demo/...
└── resources/main/
    ├── application.yml
    └── messages/welcome.txt
```

With Maven, compiled classes and resources usually appear under `target/classes/`. IDEs may create their own output folders or delegate building to Maven/Gradle.

What they share is that resources are placed on the **runtime classpath**. Application code should not hardcode the name of a specific output directory.

## 3. Where Do Resources Live Inside a Spring Boot Executable JAR?

A typical Spring Boot executable JAR layout looks like:

```text
demo.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/demo/DemoApplication.class
    │   ├── application.yml
    │   ├── application-dev.yml
    │   ├── messages/welcome.txt
    │   ├── static/css/site.css
    │   └── templates/home.html
    └── lib/
        ├── spring-boot-....jar
        └── ...other libraries...
```

In this JAR layout, `BOOT-INF/classes/` holds application classes and resources, while `BOOT-INF/lib/` holds dependency JARs. The Spring Boot launcher initializes an appropriate class-loading mechanism so classes and resources can be resolved via the classpath.

Even though the resource sits at `BOOT-INF/classes/messages/welcome.txt`, Java code still accesses it by its logical name:

```text
messages/welcome.txt
```

Do **not** prepend `BOOT-INF/classes` to the name passed to `ClassPathResource`. That is an artifact packaging detail, not part of the resource key.

### 3.1. Reading Directly from the Source Directory Is Error-Prone

The following code may work when the IDE uses the project root as its working directory:

```java
Path path = Path.of("src/main/resources/messages/welcome.txt");
String message = Files.readString(path);
```

After deployment:

```bash
cd /opt/demo
java -jar demo.jar
```

the application will look for `/opt/demo/src/main/resources/messages/welcome.txt` on the filesystem. There is no reason for that file to exist there. It was packaged into the JAR, not placed under a source tree in the runtime environment.

Therefore, **never use the `src/main/resources` path to read resources at runtime**.

## 4. Reading Packaged Resources with Spring `Resource`

Spring provides `org.springframework.core.io.Resource` and `ClassPathResource`. Reading via `InputStream` works identically whether the resource sits in an output directory or inside a JAR.

`src/main/resources/messages/welcome.txt`:

```text
Welcome to Spring Boot!
```

`src/main/java/com/example/demo/service/WelcomeTextService.java`:

```java
package com.example.demo.service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

@Service
public class WelcomeTextService {

    public String readWelcomeText() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("messages/welcome.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
```

`ClassPathResource` represents a resource by its **name on the classpath**. `getInputStream()` reads the contents even when shipped inside a JAR. For large resources, stream in chunks rather than using `readAllBytes()`.

### 4.1. Injecting a Resource via Spring Configuration

A controller can receive a resource directly:

```java
package com.example.demo.web;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {

    private final Resource welcomeResource;

    public WelcomeController(
            @Value("classpath:messages/welcome.txt")
            Resource welcomeResource
    ) {
        this.welcomeResource = welcomeResource;
    }

    @GetMapping("/welcome")
    public String welcome() throws IOException {
        try (InputStream input = welcomeResource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

In an example with `spring-boot-starter-web` and the default port, `GET http://localhost:8080/welcome` returns the file contents.

If you want to make the resource location configurable:

```yaml
app:
  welcome-resource: classpath:messages/welcome.txt
```

Update the constructor to:

```java
public WelcomeController(
        @Value("${app.welcome-resource}") Resource welcomeResource
) {
    this.welcomeResource = welcomeResource;
}
```

This way, the resource location is expressed in configuration while the code continues using `Resource#getInputStream()` uniformly.

### 4.2. Do Not Force a Classpath Resource into a `File`

This approach is risky:

```java
Resource resource = new ClassPathResource("messages/welcome.txt");
File file = resource.getFile(); // May fail when the resource is inside a JAR
```

In an IDE, resources are usually real files in an output directory, so `getFile()` may succeed. Inside a JAR, a resource cannot necessarily be represented as a standalone `java.io.File`.

Use:

```java
try (InputStream input = resource.getInputStream()) {
    // Read contents here.
}
```

If an external library API requires a `File`, look for an API accepting `InputStream` first. If a physical file is truly required, extract the resource to a **temporary file outside the JAR**, use it, and clean it up according to an appropriate lifecycle.

### 4.3. Reading via Java `ClassLoader` When Spring APIs Are Not Needed

Example:

```java
try (InputStream input = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("messages/welcome.txt")) {

    if (input == null) {
        throw new IllegalStateException(
                "messages/welcome.txt not found"
        );
    }

    String text = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
    System.out.println(text);
}
```

Note the API differences:

- `ClassLoader#getResourceAsStream("messages/welcome.txt")` looks up from the classpath root, without a leading `/`.
- `SomeClass.class.getResourceAsStream("welcome.txt")` resolves relative to that class's package.
- `SomeClass.class.getResourceAsStream("/messages/welcome.txt")` resolves from the classpath root.

Using a consistent convention avoids bugs caused solely by a leading `/`.

## 5. Organizing Configuration with `application.yml` and Profiles

The default configuration file is typically placed at:

```text
src/main/resources/application.yml
```

Example:

```yaml
spring:
  application:
    name: resource-demo

server:
  port: ${APP_PORT:8080}

app:
  greeting: "Hello from common configuration"
  welcome-resource: classpath:messages/welcome.txt
  data-directory: ${APP_DATA_DIRECTORY:./var/data}
```

These represent different kinds of values:

- `spring.application.name` sets the application name.
- `server.port` can be read from the `APP_PORT` environment variable, falling back to `8080` if absent.
- `app.greeting` is an application-specific property.
- `app.welcome-resource` references a packaged resource.
- `app.data-directory` describes a writable directory on the filesystem.

Notice that `./var/data` remains relative to the **working directory**, even though that value is written inside `application.yml`. Using a configuration file does not automatically turn this path into an absolute one.

### 5.1. Profiles for Different Environments

`src/main/resources/application-dev.yml`:

```yaml
app:
  greeting: "Hello from development environment"
```

`src/main/resources/application-prod.yml`:

```yaml
app:
  greeting: "Hello from deployment environment"
  data-directory: ${APP_DATA_DIRECTORY}
```

When activating the `dev` profile, Spring Boot applies configuration for that profile according to config data rules; normally, `app.greeting` in `application-dev.yml` overrides the value from `application.yml`. Properties not redefined continue taking values from the corresponding active configuration source.

`${APP_DATA_DIRECTORY}` has no fallback. This makes sense when production requires configuring a storage directory explicitly; if the property is resolved while the variable is absent, the application can fail due to missing configuration.

One JAR can contain `application.yml`, `application-dev.yml`, and `application-prod.yml` simultaneously. Profiles are usually chosen **at runtime**, avoiding building a separate JAR just to change a greeting, port, or data directory.

### 5.2. Activating Profiles

From the command line:

```bash
java -jar demo.jar --spring.profiles.active=dev
```

Via environment variable on Linux/macOS:

```bash
export SPRING_PROFILES_ACTIVE=dev
java -jar demo.jar
```

On Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar demo.jar
```

In an IDE, set `SPRING_PROFILES_ACTIVE=dev` under **Environment variables**, or set `--spring.profiles.active=dev` in **Program arguments** of your Run Configuration.

Do not put `spring.profiles.active: dev` inside `application-dev.yml` itself: Spring Boot enforces rules restricting profile-activating properties in documents loaded only when that profile is already active. Select profiles via launch configuration or an appropriate configuration source.

## 6. Configuration Precedence: Why Does the JAR Receive Different Values?

Spring Boot supports *externalized configuration*: the same property can be declared in packaged files, external files outside the JAR, environment variables, Java system properties, or command-line arguments.

Example inside the JAR:

```yaml
server:
  port: 8080
```

Yet when running:

```bash
java -jar demo.jar --server.port=9090
```

the application normally uses port `9090` because command-line arguments have higher precedence than config data.

| Source | Example | Commonly Used For |
|---|---|---|
| Packaged config | `classpath:/application.yml` | Defaults and shared conventions |
| External config file | `./config/application.yml` | Deployment-location-specific values |
| Environment variable | `SERVER_PORT=9090` | Containers, OS, CI/CD |
| Java system property | `-Dserver.port=9090` | JVM parameters |
| Command-line argument | `--server.port=9090` | Direct overrides at launch |

In typical precedence order, command-line arguments outrank Java system properties, environment variables, and config data; Java system properties typically outrank environment variables. Spring Boot has many other PropertySources plus specific rules for profiles, tests, and config locations, so when conflicts arise, inspect the actual runtime configuration.

### 6.1. Naming Environment Variables for Custom Properties

Under standard relaxed binding rules from canonical property names to environment variable names, dots become underscores, hyphens are removed, and names become uppercase. Thus:

```text
app.data-directory  ->  APP_DATADIRECTORY
```

If you prefer a more readable name like `APP_DATA_DIRECTORY`, write an explicit placeholder:

```yaml
app:
  data-directory: ${APP_DATA_DIRECTORY:./var/data}
```

Then Spring uses the environment variable referenced in the placeholder, rather than relying on assumptions that every underscore placement is interpreted identically by relaxed binding.

### 6.2. Choosing `@Value` or `@ConfigurationProperties`?

For a single simple value, you can use:

```java
@Value("${app.greeting}")
private String greeting;
```

When multiple related properties exist, `@ConfigurationProperties` creates a unified typed object:

```java
package com.example.demo.config;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String greeting,
        Path dataDirectory
) {
}
```

Enable scanning on the main class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Then inject the configuration into a bean:

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class StoragePathService {

    private final AppProperties properties;

    public StoragePathService(AppProperties properties) {
        this.properties = properties;
    }

    public Path directory() {
        return properties.dataDirectory();
    }
}
```

Spring Boot can bind strings into types such as `Path`. However, successful binding does not guarantee the directory already exists or is writable. Creating and checking the directory remains the responsibility of filesystem-handling code.

## 7. Reading Packaged Resources and Writing Data Are Two Separate Flows

Suppose the application needs to read a report template and write a new report:

```text
Report template:
  src/main/resources/templates/report-template.txt
  -> classpath resource, read-only

Generated report:
  /var/lib/resource-demo/reports/report.txt
  -> filesystem outside the JAR, requires write permission
```

Example service writing a report:

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final AppProperties properties;

    public ReportService(AppProperties properties) {
        this.properties = properties;
    }

    public Path writeReport(String content) throws IOException {
        Path directory = properties.dataDirectory();
        Files.createDirectories(directory);

        Path output = directory.resolve("report.txt");
        Files.writeString(output, content, StandardCharsets.UTF_8);
        return output;
    }
}
```

The example uses a fixed filename `report.txt` to stay focused on file organization. Real applications need rules for filenames, concurrent writes, overwriting, and permissions.

To ensure every execution mode writes to the same place, configure an absolute path for the environment.

Linux/macOS:

```bash
export APP_DATA_DIRECTORY=/var/lib/resource-demo
java -jar demo.jar --spring.profiles.active=prod
```

Windows PowerShell:

```powershell
$env:APP_DATA_DIRECTORY = 'C:\resource-demo\data'
java -jar demo.jar --spring.profiles.active=prod
```

The account running the application must have permission to create and write inside the chosen directory. In containers, the data directory should be mounted to a volume or a persistent storage service if data must survive redeployments.

## 8. Comparing Running from IDE, Gradle/Maven, and JAR

| Launch Method | How Classpath Is Set Up | What to Watch Out For |
|---|---|---|
| Run Main in IDE | IDE or build tool delegated by IDE | Working directory, profile, environment variables, and VM/program arguments |
| Gradle `bootRun` | Gradle with Spring Boot plugin | Dependencies/runtime classpath and args |
| Maven `spring-boot:run` | Maven with Spring Boot Maven Plugin | Profile, Maven plugin arguments, and environment |
| `java -jar demo.jar` | Spring Boot launcher inside executable JAR | Actual JAR, arguments, external config, and working directory |

The classpath can be built from output directories when running via IDE or build tool, and from nested entries inside the JAR when running the artifact. As long as code references `classpath:messages/welcome.txt`, that physical difference is handled by the class loader.

### 8.1. Running with a Profile via Gradle Wrapper

Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Build artifact:

```bash
./gradlew bootJar
```

Run the generated JAR:

```bash
java -jar build/libs/demo.jar --spring.profiles.active=dev
```

The name `demo.jar` is an example. `build/libs` is typically Gradle's default output directory, though exact artifact names and locations depend on project configuration.

### 8.2. Running with a Profile via Maven Wrapper

Linux/macOS:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=dev
./mvnw package
java -jar target/demo.jar --spring.profiles.active=dev
```

These commands apply only if the project has Maven Wrapper, the Spring Boot Maven Plugin, and an executable artifact produced through appropriate packaging configuration. Replace `demo.jar` with the actual artifact name.

### 8.3. How the Working Directory Affects Relative Paths

If the application calls:

```java
Path path = Path.of("./var/data/report.txt");
```

Running with current directory `/home/me/projects/demo` resolves to:

```text
/home/me/projects/demo/var/data/report.txt
```

Yet running the JAR from `/opt/demo` resolves to:

```text
/opt/demo/var/data/report.txt
```

These are two different storage locations even though bytecode and relative configuration are unchanged.

There are two suitable strategies:

1. Fix the working directory in the IDE, launch script, service manager, or container.
2. Supply an absolute data path via environment variables/config for each environment.

To observe the working directory:

```java
System.out.println(
        Path.of("").toAbsolutePath().normalize()
);
```

This helps during diagnostics, yet personal machine paths should never be hardcoded as fixed defaults in business code.

## 9. Configuration Outside the JAR and Config Lookup Rules

In addition to packaged configuration, Spring Boot can load config data from the filesystem. A clear deployment layout:

```text
/opt/resource-demo/
├── demo.jar
├── config/
│   └── application.yml
└── data/
```

When launched from `/opt/resource-demo`, Spring Boot with standard default config lookup locations can read `./config/application.yml`. This is a location **relative to the working directory**, distinct from `classpath:/application.yml`.

You can also specify locations:

```bash
java -jar demo.jar \
  --spring.config.additional-location=optional:file:./config/
```

On PowerShell, use one line:

```powershell
java -jar demo.jar --spring.config.additional-location=optional:file:./config/
```

Notes:

- `spring.config.additional-location` **adds** config search locations, suitable when keeping default locations.
- `spring.config.location` can **replace** default locations; use it when you intentionally want to control all config data sources.
- `optional:` merely skips missing locations; if the application lacks a required property, it may still fail to start.
- `file:./config/` uses the filesystem; `classpath:/config/` uses the classpath.
- For directory config locations, keep the trailing `/` per Spring Boot location syntax.

If the working directory can vary, use an absolute location:

```bash
java -jar /opt/resource-demo/demo.jar \
  --spring.config.additional-location=optional:file:/etc/resource-demo/
```

Spring Boot also offers `spring.config.import`:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
```

This mechanism is useful for importing extra configuration sources, with its own precedence rules. Relative paths in imports still need to be understood per Spring Boot semantics and the runtime environment; do not assume they are always relative to the source tree.

### 9.1. Do Not Embed Secrets in Packaged Resources

Do not commit passwords, API keys, or tokens into `application.yml`:

```yaml
# Example not recommended for real configuration
app:
  api-key: "real-secret-value"
```

Use a secret source suited to the deployment system, or reference values supplied by the environment:

```yaml
app:
  api-key: ${APP_API_KEY}
```

Avoid printing secrets to logs when inspecting configuration. External files and environment variables also must be protected with appropriate access permissions.

## 10. `static` and `templates` in Web Applications

In addition to resources read explicitly by code, Spring Boot web has conventions for HTTP-served resources.

### 10.1. Static Assets

Example:

```text
src/main/resources/static/
├── css/site.css
├── js/app.js
└── images/logo.svg
```

In a typical Spring MVC application, these files are served at URLs:

```text
GET /css/site.css
GET /js/app.js
GET /images/logo.svg
```

The `static` directory name does not normally appear in public URLs. Spring Boot has default static locations on the classpath, including `/static`, `/public`, `/resources`, and `/META-INF/resources`; these rules can be changed via project configuration.

If assets work in the IDE yet return 404 from the JAR, check whether the artifact contains them, whether URLs are correct, and whether static resource handling configuration was altered.

### 10.2. Templates for Template Engines

Example placement:

```text
src/main/resources/templates/home.html
```

With an appropriately configured template engine, such as Thymeleaf, an MVC controller can return a view name:

```java
package com.example.demo.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class HomeController {

    @GetMapping("/")
    public String home() {
        return "home";
    }
}
```

The template engine typically looks up `classpath:/templates/home.html` per configured conventions. Unlike `@RestController`, `@Controller` in this example returns a view name rather than writing the literal string `home` directly to the HTTP response.

If the template engine starter or template file is missing, the application may still start yet fail when rendering the request. Distinguish this error from missing resources at startup.

### 10.3. Static Assets Differ from User-Uploaded Content

`src/main/resources/static` is suited for CSS, JavaScript, and images shipped with the release. Newly uploaded images should be stored outside the JAR or in an appropriate storage service. If uploaded images must be served over HTTP, implement a mechanism that streams files from storage with appropriate access-control policies.

## 11. End-to-End Example: One Application, Two Ways to Run

Let's combine these pieces into a small Spring Boot example. Assume the project is configured with the Spring Boot plugin, an appropriate Java version, and the `spring-boot-starter-web` dependency.

### 11.1. Resources and Configuration

`src/main/resources/messages/welcome.txt`:

```text
This is a resource packaged with the application.
```

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: resource-demo

app:
  greeting: "Hello"
  data-directory: ${APP_DATA_DIRECTORY:./var/data}
```

`src/main/resources/application-dev.yml`:

```yaml
app:
  greeting: "Hello from the dev profile"
```

### 11.2. Binding Configuration

`src/main/java/com/example/demo/config/AppProperties.java`:

```java
package com.example.demo.config;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(String greeting, Path dataDirectory) {
}
```

`src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 11.3. Endpoint Returning Both Configuration and Resource

`src/main/java/com/example/demo/web/WelcomeController.java`:

```java
package com.example.demo.web;

import com.example.demo.config.AppProperties;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {

    private final AppProperties properties;
    private final Resource welcomeText;

    public WelcomeController(
            AppProperties properties,
            @Value("classpath:messages/welcome.txt") Resource welcomeText
    ) {
        this.properties = properties;
        this.welcomeText = welcomeText;
    }

    @GetMapping("/welcome")
    public String welcome() throws IOException {
        try (InputStream input = welcomeText.getInputStream()) {
            String text = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            return properties.greeting() + "\n" + text;
        }
    }
}
```

In the IDE, select main class `com.example.demo.DemoApplication` and Program argument `--spring.profiles.active=dev`. When running successfully, `GET /welcome` returns content containing the greeting from the dev profile and the resource text.

With Gradle:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
./gradlew bootJar
java -jar build/libs/demo.jar --spring.profiles.active=dev
```

In Windows PowerShell, replace the wrapper command with `.\gradlew.bat` and use the corresponding argument syntax. Replace `demo.jar` with the actual artifact name.

Resource reading and profile configuration selection follow the exact same rules in both execution modes. If you run the JAR from a different directory, packaged resources remain readable; only relative filesystem paths, such as `./var/data`, change where they resolve.

## 12. Diagnosing When the IDE Works Yet the JAR Fails

| Symptom | Common Cause | How to Handle |
|---|---|---|
| `NoSuchFileException: src/main/resources/...` | Code uses source path at runtime | Use classpath resource if data is packaged |
| `FileNotFoundException` when calling `Resource#getFile()` | Resource is not a real file inside JAR | Use `getInputStream()` or extract to temp file if needed |
| `ClassPathResource ... does not exist` | Wrong name or resource not packaged | Check source location and artifact contents |
| `application-dev.yml` has no effect | Profile not active or property overridden | Check program args, env, and external config |
| JAR uses wrong port | Another config source overrides `server.port` | Check command-line, system properties, env, config |
| File written successfully yet in a different place | Different working directory | Print resolved absolute path; configure absolute path |
| `Permission denied` when saving report | Data directory is not writable | Check permissions and volumes |
| CSS/JS returns 404 | Wrong location under `static`, wrong URL, or missing from JAR | Check JAR contents and static path config |
| Template does not render | Missing template engine or template not found | Check dependencies, controller, and `templates` |
| Works on Windows yet fails on Linux | Case-sensitivity or path separator differences | Use exact resource casing; use `/` in classpath names |

### 12.1. Inspecting JAR Contents

After building:

```bash
jar --list --file build/libs/demo.jar
```

Look for entries:

```text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-dev.yml
BOOT-INF/classes/messages/welcome.txt
```

On Windows PowerShell:

```powershell
jar --list --file build/libs/demo.jar | Select-String 'BOOT-INF/classes'
```

If a resource is missing from the JAR, check the file's location in `src/main/resources` and the build tool's resource-copying configuration. If the resource is inside the JAR, check the name passed to `ClassPathResource`, how the resource is opened, and which class loader is used.

### 12.2. Observing Runtime Paths

When investigating, you can print non-sensitive details:

```java
System.out.println("Working dir: " +
        Path.of("").toAbsolutePath().normalize());

System.out.println("Data dir: " +
        properties.dataDirectory().toAbsolutePath().normalize());

Resource resource = new ClassPathResource("messages/welcome.txt");
System.out.println("Welcome resource exists: " + resource.exists());
```

If `properties.dataDirectory()` is a relative path, this printout reveals which absolute path it resolves to. Never print entire property sources or environment variables when they might contain secrets.

### 12.3. A Concise Investigation Workflow

```text
Does the source file sit properly in src/main/resources?
                    │
                    ▼
Does the build output / JAR contain the resource?
                    │
                    ▼
Is the code reading from classpath or from filesystem?
                    │
                    ▼
Are the profile and property sources as expected?
                    │
                    ▼
If writing data: are the storage location and filesystem permissions right?
```

Pick the check that matches the error. If `ClassPathResource` reports missing, changing the HTTP port will not fix it. If an uploaded file cannot be written due to permissions, copying resources into the JAR will not give the external storage directory write permissions either.

## 13. Organizational Rules and Practice Exercises

Useful conventions when starting a project:

1. Place read-only resources shipped with the build in `src/main/resources` and access them via the **classpath**.
2. Place program-generated or user-supplied files outside the JAR; use `Path` and a property to specify the storage directory.
3. Keep `application.yml` as non-sensitive defaults; use profiles, external configs, or environment variables for environment differences.
4. Set the working directory explicitly in Run Configurations or launch scripts if relative paths are used.
5. Use exact casing in resource names, `/` for classpath paths, and explicit encoding such as UTF-8 when reading text.
6. Never hardcode personal machine paths like `C:\Users\someone\Desktop\...` or `/home/someone/projects/...` into application logic.
7. Use `jar --list --file` to verify what was actually packaged when suspecting resource packaging bugs.

### Practice Exercise A: Resources Independent of the Source Tree

Create `src/main/resources/messages/welcome.txt`, add an endpoint reading via `Resource#getInputStream()`, and run it from the IDE. Build the JAR and run `java -jar` from a directory outside the source tree. Compare the endpoint output. Temporarily switch to `Path.of("src/main/resources/messages/welcome.txt")` to observe why filesystem reading is unstable, then restore classpath reading.

### Practice Exercise B: One JAR, Multiple Profiles

Create `application.yml` and `application-dev.yml` with two `app.greeting` values. Run the exact same artifact with and without `--spring.profiles.active=dev`. Explain which configuration source determines the endpoint's response.

### Practice Exercise C: Environment-Specific File Write Paths

Configure `app.data-directory=./var/data` and observe the output directory when running from two different working directories. Then supply `APP_DATA_DIRECTORY` with an absolute path and verify the file is written to the specified location. This demonstrates that packaged resources and runtime data have separate lifecycles.

### Practice Exercise D: Inspect the Artifact

Use `jar --list --file <jar-name>` to find `BOOT-INF/classes/messages/welcome.txt` and `BOOT-INF/classes/application.yml`. If missing, check the source file and packaging mechanism before changing Java code.

After these exercises, you should be able to tell whether a path uses the classpath or the filesystem, understand why the same `application.yml` file can be overridden by runtime configuration, and organize source code so that **resources ship with the build** while **configuration, data, and filesystem permissions** are clearly defined at deployment time. This is the foundation for running Spring Boot applications consistently from IDE to executable JAR.
