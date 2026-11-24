# Packaging Resources Inside the Archive vs. Providing External Configuration in Spring Boot

## 1. Problem: one application, multiple deployment environments

When building an **executable JAR** for Spring Boot, two categories of data are easily mixed up:

- **Resources belonging to the application version:** text files, message templates, HTML templates, images/logos, static assets, SQL migrations, schemas, and **non-sensitive** default configuration. These files are usually packaged inside the archive so the artifact is self-contained and reproducible.
- **Configuration depending on the runtime environment:** database URLs, service hosts, ports, active profiles, operational feature flags, infrastructure timeouts, credentials, private keys, or tokens. These values should be supplied **outside the archive** by the deployment environment or a secret management system.

A sound practice is **building one tested artifact and deploying that exact same artifact** across dev, staging, and production—changing only external configuration and secrets per environment. Baking production passwords and hostnames into the executable JAR forces rebuilds or environment-specific JARs, complicating auditing and rollbacks.

```text
Source repository
├── src/main/java/...
├── src/main/resources/
│   ├── application.properties        # non-sensitive defaults
│   ├── assets/banner.txt             # classpath resource
│   ├── static/welcome.txt            # static HTTP resource
│   ├── templates/...                 # if using a template engine
│   └── db/migration/...              # migrations if using Flyway
└── pom.xml / build.gradle.kts
          |
          v build
Executable Boot JAR (immutable)
├── BOOT-INF/classes/...             # classes + resources
├── BOOT-INF/lib/...                 # runtime dependencies
└── Spring Boot loader
          |
          +----> runtime config outside JAR:
                  /opt/app/config/application.properties
                  environment variables / command-line args
                  ConfigMap / mounted Secret / configtree:
```

**Distinguish two questions:**

1. *Is this file part of the software version, or environment-specific data/secret?* → decides **package inside vs. provide externally**.
2. *By what mechanism will Java and Spring Boot read it?* → **classpath resources** differ from **filesystem files** and from **Spring Config Data**.

The hands-on example uses **Java 17 and Spring Boot 3.5.0** with Maven, followed by an equivalent Gradle Kotlin DSL setup. These versions are pinned for consistency, not as a claim of the latest Spring Boot release. For another version, consult that version's documentation.

## 2. Common resource types and where they belong

| Data type | Common source location | Package in JAR? | Rationale |
| --- | --- | --- | --- |
| Release-coupled HTML email templates | `src/main/resources/templates/mail/...` | Yes | Tied to app code and reviewed in Git |
| Notices, schemas, static mappings | `src/main/resources/assets/...` | Yes | Needed on classpath in all environments |
| Web static CSS/JS/favicon | `src/main/resources/static/...` | Yes | Frontend version ships with backend |
| Flyway SQL migrations | `src/main/resources/db/migration/...` | Usually yes | Keeps schema migrations aligned with app version |
| `application.properties` with harmless defaults | `src/main/resources/application.properties` | Yes | Supplies sensible startup defaults |
| `application-prod.yml` **with no secrets** | `src/main/resources/application-prod.yml` | Possibly | Profile defaults, still allowing external overrides |
| Per-environment DB URL/host | runtime file, env, secret config | Usually no | Changes per environment without rebuilding |
| API tokens, DB passwords, private keys | secret manager, mounted secrets | **No** | Prevents leaks via artifacts/Git/registries/logs |
| User-uploaded files | persistent volume/object storage | No | Mutable data created after build |
| Logs, caches, temp files | filesystem/runtime storage | No | Not part of immutable application build |
| Test fixtures | `src/test/resources` | Not in production JAR | Serves test classpath only |
| Trusted public CA certificates | classpath or managed trust store | Depends on policy | Public CAs can be packaged; private keys must be protected |
| Dev `.env` containing tokens | local secret setup outside project resources | **No** | Files under resource source sets risk accidental packaging |

**Do not assume every `.properties` file belongs outside the JAR.** For example, `assets/mapping.properties` may be stable reference data packaged inside the JAR. Conversely, `application.properties` is Spring configuration that can have both internal defaults and external overrides: same format, different **source and precedence**.

**Never place secrets under `src/main/resources/static` or `public`.** Spring MVC can serve those locations directly over HTTP, creating not only an artifact exposure risk but also a live web exposure risk.

## 3. Resource layouts in Maven, Gradle, and Spring Boot executable archives

### 3.1. Maven: `src/main/resources` → `target/classes`

In a standard Maven Java project, production resources are processed during `process-resources` by the Maven Resources Plugin, copied from:

```text
src/main/resources/application.properties
src/main/resources/assets/banner.txt
src/main/resources/static/welcome.txt
```

to:

```text
target/classes/application.properties
target/classes/assets/banner.txt
target/classes/static/welcome.txt
```

After `maven-jar-plugin:jar`, those files sit in the **source JAR** at the classpath root. With `spring-boot-maven-plugin:repackage`, the executable Spring Boot JAR uses:

```text
resource-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/resources/ResourceDemoApplication.class
│   │   ├── com/example/resources/InfoController.class
│   │   ├── application.properties
│   │   ├── assets/banner.txt
│   │   └── static/welcome.txt
│   └── lib/
│       ├── spring-boot-...jar
│       └── ...other-runtime-dependencies...
└── ...
```

Lines with `...` are illustrative diagrams, not literal JAR filenames. **`BOOT-INF/classes` is the application's classpath root when the Boot Loader runs**. Therefore, application code requests `assets/banner.txt`, **not** `BOOT-INF/classes/assets/banner.txt`. The `BOOT-INF/classes` prefix is a packaging detail handled by the loader.

`BOOT-INF/lib` holds nested runtime library JARs; it is not where the project's `src/main/resources` go by default. Resources inside dependency nested JARs can still be located on the classpath by the classloader.

### 3.2. Gradle: `processResources` and `bootJar`

With the Gradle Java plugin, `src/main/resources` is the resource directory of the `main` source set. `processResources` copies resources into `build/resources/main`; `classes` aggregates compiled bytecode and resources. The Spring Boot Gradle `bootJar` task packages production outputs and runtime dependencies into the executable archive, placing resources under `BOOT-INF/classes` just like Maven.

```text
Gradle project
  src/main/java          --> compileJava ------+
  src/main/resources     --> processResources -+--> classes --> bootJar
                                                           |
                                                           v
                                                   build/libs/app.jar
                                                   BOOT-INF/classes/*
                                                   BOOT-INF/lib/*
```

**`jar` and `bootJar` are distinct tasks:** the Java plugin's `jar` creates a plain JAR if run; `bootJar` creates the executable Boot archive. Inspect the right file in `build/libs`. The mere presence of `src/main/resources` in the repository **does not prove a file landed in the final artifact**: custom source sets, excludes, filtering, and plugin settings can change what gets packaged.

### 3.3. How does a WAR differ from a JAR?

When packaging an executable WAR, classes and resources normally live under `WEB-INF/classes`, and dependencies under `WEB-INF/lib` or `WEB-INF/lib-provided`, rather than `BOOT-INF/classes`. This lesson's hands-on example uses `<packaging>jar</packaging>`; when switching to WAR, update your archive checks accordingly instead of just changing the extension.

## 4. Maven + Java 17 example: bundled resources and external config

We will build an API with three independent behaviors:

1. `GET /banner` reads **`assets/banner.txt` packaged inside the JAR**.
2. `GET /values` reads two Spring configuration keys that can be **overridden externally**.
3. `GET /welcome.txt` is served by Spring MVC from `static/welcome.txt` inside the archive.

We then keep the exact same JAR and run it under two different environment configs to prove **build once, configure many times**.

### 4.1. File layout

```text
resource-demo/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/resources/
│       │   └── ResourceDemoApplication.java
│       └── resources/
│           ├── application.properties
│           ├── assets/banner.txt
│           └── static/welcome.txt
├── runtime-config/
│   └── application.properties          # created for runtime, NOT inside resources
└── target/                              # generated by Maven
```

`runtime-config` is an external test directory outside the main source set, so Maven does not package it under standard layout rules. In real deployments, staging/production runtime config files live in `/etc/myapp` or are mounted by CI/orchestrators rather than stored in the Git repository.

### 4.2. Complete `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>resource-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>resource-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
</project>
```

`spring-boot-starter-parent` manages starter versions, configures Java 17 compiler targets, and wires `spring-boot:repackage`. Thus `mvn clean package` builds an executable JAR without extra execution blocks or per-resource plugins.

### 4.3. Complete Java source

**`src/main/java/com/example/resources/ResourceDemoApplication.java`:**

```java
package com.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ResourceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDemoApplication.class, args);
    }
}

@RestController
class InfoController {

    private final Environment environment;

    InfoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/values")
    public String values() {
        String message = environment.getProperty("demo.message", "missing");
        String region = environment.getProperty("demo.region", "missing");
        return "message=" + message + ";region=" + region;
    }

    @GetMapping("/banner")
    public String banner() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("assets/banner.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }
}
```

Both classes sit in one Java file: only `ResourceDemoApplication` is `public`, while `InfoController` is package-private, which is valid Java 17. Spring Boot component scanning starts at `com.example.resources` and discovers `InfoController`. `Environment` resolves Spring properties by precedence; `ClassPathResource` opens the *archive-packaged* file as a stream, working both in IDEs and in executable JARs.

If `assets/banner.txt` is missing, `getInputStream()` throws an exception and `/banner` fails—signaling the **resource was not packaged properly**, rather than Spring silently creating a fallback.

### 4.4. Three production resource files

**`src/main/resources/application.properties`:**

```properties
spring.application.name=resource-demo
server.port=8080
demo.message=packaged
demo.region=local
```

**`src/main/resources/assets/banner.txt`:**

```text
BANNER_FROM_ARCHIVE
```

**`src/main/resources/static/welcome.txt`:**

```text
STATIC_OK
```

Values in `application.properties` are non-sensitive defaults. `assets/banner.txt` is an internal resource read by Java code; `static/welcome.txt` is automatically served by Spring MVC at `/welcome.txt`. If an app sets a custom servlet context path or Spring MVC `static-path-pattern`, that URL changes accordingly.

### 4.5. Build and run the executable archive

From the root directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn -B -ntp clean package
java -jar target/resource-demo-0.0.1-SNAPSHOT.jar
```

- Java 17 or newer is supported by Spring Boot 3.5.0.
- `-B` runs Maven in batch mode; `-ntp` suppresses download progress logs.
- `clean` clears stale outputs; `package` compiles, runs tests if present, and repackages via the Boot Maven Plugin.
- If the repository provides a Maven Wrapper, use `./mvnw -B -ntp clean package` or `mvnw.cmd` on Windows.

Once running on port 8080, open another terminal:

```bash
curl -fsS http://localhost:8080/values
curl -fsS http://localhost:8080/banner
curl -fsS http://localhost:8080/welcome.txt
```

**Exact response bodies for each request:**

| Request | Body |
| --- | --- |
| `GET /values` | `message=packaged;region=local` |
| `GET /banner` | `BANNER_FROM_ARCHIVE` |
| `GET /welcome.txt` | `STATIC_OK` |

The sample text files may have a trailing newline; `/banner` calls `strip()` so its body omits trailing newlines, whereas static resource `/welcome.txt` serves the raw file bytes. `curl` does not append a newline itself. Stop the server with `Ctrl+C` before running the next configuration.

## 5. Inspect the archive: prove which files were actually packaged

After building, inspect:

```bash
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar
```

Key expected entries:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/application.properties
BOOT-INF/classes/assets/banner.txt
BOOT-INF/classes/static/welcome.txt
BOOT-INF/classes/com/example/resources/ResourceDemoApplication.class
BOOT-INF/classes/com/example/resources/InfoController.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
```

`...` stands for multiple runtime files, not a literal entry. A handy Bash filter:

```bash
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar |
  grep -E '^BOOT-INF/classes/(application.properties|assets/banner.txt|static/welcome.txt)$'
```

Expect exactly these three paths:

```text
BOOT-INF/classes/application.properties
BOOT-INF/classes/assets/banner.txt
BOOT-INF/classes/static/welcome.txt
```

On Windows PowerShell use:

```powershell
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar |
  Select-String '^BOOT-INF/classes/(application.properties|assets/banner.txt|static/welcome.txt)$'
```

**Difference between archive inspection and classpath lookup:** the ZIP path `BOOT-INF/classes/assets/banner.txt` is not what you pass to `new ClassPathResource(...)`. In Java code, pass `assets/banner.txt`. The Spring Boot loader maps `BOOT-INF/classes` as the classpath root when running the executable JAR.

If entries are missing:
- Check the folder name is `src/main/resources`, not `src/resources` or `src/main/java/resources`.
- Check `pom.xml` for custom source sets or resource exclusions.
- Confirm you built the **right Maven/Gradle module** and are not inspecting a plain JAR.
- Run a clean build to clear stale outputs, without wiping global dependency caches if the issue is just a resource path configuration.

## 6. Supplying an external `application.properties` without modifying the JAR

Keep the already-built `target/resource-demo-0.0.1-SNAPSHOT.jar` untouched. Create **`runtime-config/application.properties`** at project root:

```properties
server.port=9090
demo.message=external
demo.region=staging
```

Run from project root:

```bash
java -jar target/resource-demo-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./runtime-config/
```

**Important conditions:**
- Relative path `./runtime-config/` resolves against the **Java process's current working directory**, not the JAR file's directory.
- The trailing `/` is critical because this is a **directory location**. Spring Boot searches that folder for `application.properties`/`application.yml` and profile variants.
- `optional:` prevents a missing directory/file from failing startup. For mandatory production configs or secrets, consider omitting `optional:` to fail fast.
- `spring.config.additional-location` adds new search locations alongside default locations, allowing external values to override packaged defaults.

With the server listening on port 9090:

```bash
curl -fsS http://localhost:9090/values
curl -fsS http://localhost:9090/banner
curl -fsS http://localhost:9090/welcome.txt
```

Corresponding responses:

| Endpoint | Body |
| --- | --- |
| `/values` | `message=external;region=staging` |
| `/banner` | `BANNER_FROM_ARCHIVE` |
| `/welcome.txt` | `STATIC_OK` |

**Takeaway from the example:** changing `demo.message`, `demo.region`, and `server.port` **never modified the JAR**. `banner.txt` and static assets stay identical because they belong to the application version. The same binary adapts to another environment through runtime configuration.

### 6.1. Default external config locations Spring Boot checks automatically

Spring Boot also checks default Config Data locations, roughly in order:

- Classpath root: `classpath:/application.properties` or equivalent YAML.
- Classpath `/config` package.
- JVM working directory: `file:./application.properties`.
- `file:./config/application.properties` and direct subdirectories matching default patterns.

`./runtime-config/application.properties` in our example is **not** a default location, which is why we pass `spring.config.additional-location` explicitly. Conversely, if you place `application.properties` next to a JAR yet launch the JVM from a different working directory, it may **not** be discovered; verify `user.dir`, systemd `WorkingDirectory`, or container working directories.

**External `application.properties` files normally outrank defaults inside the JAR** under Config Data precedence. Still, Java system properties, OS environment variables, and command-line arguments have higher precedence; do not assume an external file always beats every other source.

## 7. `spring.config.location`, `spring.config.additional-location`, and `spring.config.import`

These three properties look related yet behave very differently:

| Key | Function | Risk if misused |
| --- | --- | --- |
| `spring.config.location` | **Replaces default search locations** with the specified list | Drops packaged `application.properties` defaults from Config Data lookup |
| `spring.config.additional-location` | **Adds** locations to default search locations so external keys can override | Wrong working directory, missing file, precedence surprises |
| `spring.config.import` | Imports additional config files from loaded configs, supporting `file:`, `classpath:`, `configtree:` | Missing non-optional import fails startup; wrong path |

**Example adding external config only:**

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/resource-demo/
```

**Example replacing all default locations:**

```bash
java -jar app.jar \
  --spring.config.location=file:/etc/resource-demo/application.properties
```

With `spring.config.location`, you can no longer assume defaults packaged inside the JAR will be read. If the external file specifies only a subset of keys, omitted defaults may become `missing` or fall back to library defaults. When your intent is "supply external overrides while preserving packaged defaults," **prefer `spring.config.additional-location`**.

**Example importing an extra config file from an existing config:**

```properties
# Can be placed inside an application.properties read by Spring Boot
spring.config.import=optional:file:./runtime-config/feature-flags.properties
```

`optional:` ignores missing locations; avoid it for mandatory config. `spring.config.location` and `spring.config.additional-location` are read **very early** to discover configs, so pass them via environment variables, JVM system properties **before `-jar`**, or application CLI arguments **after `-jar`**—not inside a file Spring does not yet know where to find.

### 7.1. Configuration precedence order

In a typical Spring Boot runtime setup for the same key `demo.message`:

```text
--demo.message=cli              (application command-line argument)
          >
-Ddemo.message=jvm              (Java system property on app JVM)
          >
DEMO_MESSAGE=env                (OS environment variable)
          >
runtime-config/application.properties
          >
classpath:/application.properties
```

This diagram **omits other `PropertySources`**: `SPRING_APPLICATION_JSON`, test properties, JNDI, DevTools settings, programmatic defaults, and `@PropertySource`. When debugging precedence issues, consult the official precedence table for your Boot version rather than treating this simplified chain as exhaustive.

Example on Linux/macOS with the external file from section 6:

```bash
DEMO_MESSAGE=from-env java \
  -jar target/resource-demo-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./runtime-config/
```

`/values` on port 9090 returns:

```text
message=from-env;region=staging
```

Appending `--demo.message=from-cli` at the end changes `message` to `from-cli`. Passing JVM property `-Ddemo.message=from-jvm` must go **before `-jar`**. Run **one JVM at a time** across all tests, stopping previous instances to avoid port conflicts.

### 7.2. Profile-specific files

Each environment can select a profile:

```bash
java -jar target/resource-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=staging \
  --spring.config.additional-location=optional:file:./runtime-config/
```

When `staging` is active, Spring Boot also considers `application-staging.properties` / `application-staging.yml` in matching locations. Profile-specific files generally override non-profile files per Config Data rules. **Never hardcode `spring.profiles.active=prod` inside a profile-specific file**; activation belongs to runtime/CLI/environment. Avoid complex untested profile combinations because location-group ordering and profiles interact.

### 7.3. Explicit config file naming

If an organization uses a custom filename instead of `application.properties`, e.g., `company.properties`, you can pass `--spring.config.name=company` or point a location to the **exact file**. Note that changing config names alters default file lookup; test thoroughly. For a single service separating dev/prod configs, `application-{profile}.properties` or `spring.config.import` is usually clearer to trace than renaming `spring.config.name`.

## 8. Secrets: why must they stay outside the archive?

A JAR archive is a ZIP file that is trivial to inspect and unpack. If `src/main/resources/application.properties` contains:

```properties
# Example TO AVOID: never store real passwords in resources
spring.datasource.password=hardcoded-password
```

then the password ships inside `BOOT-INF/classes/application.properties` in the artifact, propagating through Git history, CI artifact stores, registries, backups, and every host receiving the JAR. Even a private source repository is no substitute for secret management.

**Recommended practices:**

- In packaged `application.properties`, keep only non-sensitive defaults and required key names.
- For mandatory secrets, use Spring placeholders without harmless fallbacks that mask missing secrets, e.g., `spring.datasource.password=${DB_PASSWORD}` when actually using a datasource.
- When a secret manager injects environment variables, ensure they reach only the **application process** and are never echoed to logs.
- In Kubernetes/Docker, prefer **volume-mounted secrets** and `configtree:` so secrets do not appear in CLI arguments visible via process listings.
- Enforce least-privilege read permissions, rotation, and avoid logging secrets at startup, in exceptions, or via Actuator `/env` and `/configprops` endpoints.
- If a secret ever entered Git or an artifact store, assess exposure and **rotate** it; deleting the file in a later commit does not erase Git history.
- Encryption-at-rest and secret stores are important controls, yet encryption alone does not prevent leaks if the app logs or exposes secrets post-decryption.

### 8.1. Configuration tree: one file per property

Spring Boot Config Data supports `configtree:`. Suppose the platform mounts:

```text
/run/secrets/
├── demo.api-key            # content: real secret, never committed to docs/repo
└── demo.partner-token      # content: real secret, never committed to docs/repo
```

Inside the environment's **external `application.properties`**:

```properties
spring.config.import=configtree:/run/secrets/
```

Spring Boot maps filenames to property keys such as `demo.api-key` and `demo.partner-token`. File contents become property values injected via `Environment` or `@ConfigurationProperties`. If the mount path is missing without `optional:`, startup fails—usually desirable for mandatory secrets. For local dev where secrets are optional, `optional:configtree:/run/secrets/` can be used.

**Note:** Kubernetes ConfigMaps and Secrets can be mounted as files or injected as environment variables. `configtree:` is a **file-reading** mechanism, not an encryption mechanism. Kubernetes RBAC, volume permissions, and secret lifecycles must still be governed properly.

### 8.2. Do not use `src/main/resources` for post-deployment writable data

User uploads, receipts, logs, reports, and images belong in durable storage (object storage, databases, persistent volumes). An application JAR is **not a writable folder**. Under `java -jar`, classpath resources live inside a ZIP archive; attempting `FileOutputStream` against `BOOT-INF/classes/...` is invalid and fails.

If you need to ship a default template and later edit a user-customized copy:

1. Open the **classpath resource** via `getInputStream()`.
2. Copy bytes to a configured writable external data directory.
3. Read and write the **external file** as runtime data without touching the JAR.
4. Define migration, backup, and file-permission policies for that storage.

## 9. Reading classpath resources properly in Java 17+

### 9.1. Use `InputStream` instead of `File`

Section 4's example uses:

```java
new ClassPathResource("assets/banner.txt").getInputStream()
```

This works whether the resource sits inside an executable JAR or on an IDE classpath.

**Avoid doing this by default:**

```java
File file = new ClassPathResource("assets/banner.txt").getFile();
```

`getFile()` works only when the resource resolves to a real filesystem file. Inside an executable JAR, the resource lives **inside an archive**, not as an individual file on disk, so `getFile()` throws an exception. Likewise:

```java
Path path = Paths.get(
    getClass().getResource("/assets/banner.txt").toURI()
);
```

is not portable with nested Boot JARs; the URI uses a `jar:` or loader-specific scheme that cannot convert to a default filesystem `Path` the way it works in an IDE.

**Plain Java approach without Spring's `Resource` abstraction:**

```java
try (InputStream stream =
        ResourceDemoApplication.class.getResourceAsStream(
                "/assets/banner.txt")) {
    if (stream == null) {
        throw new IllegalStateException("Missing assets/banner.txt");
    }
    String data = new String(stream.readAllBytes(),
            StandardCharsets.UTF_8);
    System.out.println(data.strip());
}
```

This is a **Java snippet inside a class/method that already imports** `InputStream` and `StandardCharsets` as in section 4, not a standalone `.java` file. It illustrates classpath lookup; either `getResourceAsStream` or Spring `Resource` works cleanly.

### 9.2. When the resource must be an external file

Read external filesystem files with `FileSystemResource` or Java NIO:

```java
Path external = Path.of("/etc/resource-demo/policy.json");
String policy = Files.readString(external, StandardCharsets.UTF_8);
```

This snippet requires importing `java.nio.file.Path`, `Files`, and `StandardCharsets`, plus an existing readable file. Never assume a hardcoded absolute path is portable across Windows, containers, and VMs. For properties/YAML configs, **let Spring Config Data load them** instead of writing custom Java parsers; for other data documents, use appropriate filesystem APIs.

### 9.3. Templates and static content

- `src/main/resources/templates` holds templates processed by configured engines (Thymeleaf, FreeMarker...); files are **not served verbatim** without an engine/controller.
- `src/main/resources/static`, `public`, `resources`, and `META-INF/resources` are locations Spring Boot serves as **static HTTP content**. `static/welcome.txt` in the demo is served at `/welcome.txt`.
- `src/main/resources/assets` is just an ordinary classpath folder. It does **not automatically map to URL `/assets/...`** unless you configure resource handlers or a controller.
- `src/test/resources` serves unit/integration tests on the **test classpath**, not the production executable JAR in standard builds.

Never place secrets, protected internal files, or user backups inside static resource directories. Static files may be publicly reachable without passing through controller endpoints depending on security config.

## 10. Maven resource filtering: transform only intended files

**Resource filtering** substitutes placeholders with build metadata during `process-resources`. This is distinct from **runtime Spring `Environment` resolution**.

With `spring-boot-starter-parent`, Spring Boot configures filtering for `application.properties`/`application.yml` using `@...@` delimiters to avoid colliding with Spring's runtime `${...}` placeholders.

Example addition to **`src/main/resources/application.properties`**:

```properties
app.build-version=@project.version@
app.runtime-host=${SERVICE_HOST:localhost}
```

After `mvn clean package` with the sample POM:

- `@project.version@` is filtered by Maven Resources Plugin into `0.0.1-SNAPSHOT` in the processed resource.
- `${SERVICE_HOST:localhost}` is a **Spring property placeholder** resolved from the environment at runtime; the starter parent's `@...@` convention leaves it untouched at build time.

Build version is **non-sensitive** build-time metadata safe to embed in the JAR; `SERVICE_HOST` is runtime configuration. If CI injects build numbers, Git revisions, or timestamps, ensure verification and reproducible-build rules are clear; avoid injecting secrets or uncontrolled timestamps across all resources.

### 10.1. When not using the Spring Boot starter parent

If you only import the Spring Boot BOM without inheriting the starter parent, filtering config, plugin goals, and resource rules are not automatically inherited. You must configure Maven Resources Plugin and `<resources>` with delimiters and versions matching your corporate parent and build rules. **POM fragment** (not a complete POM):

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <version>3.3.1</version>
            <configuration>
                <delimiters>
                    <delimiter>@</delimiter>
                </delimiters>
                <useDefaultDelimiters>false</useDefaultDelimiters>
            </configuration>
        </plugin>
    </plugins>
</build>
```

**Important:** enabling `<filtering>true</filtering>` across **all** of `src/main/resources` can corrupt images, fonts, certificates, PDFs, or other binary files. Although Maven Resources Plugin maintains default and custom non-filtered binary extensions, the safest design is **separating filtered text resources from non-filtered binary resources with explicit `<resource>`/`<includes>` blocks**. Do not use this snippet as-is if your resource folder contains binary assets needing byte-exact preservation.

When using starter parent's built-in filtering convention, **do not re-declare a generic `<resources>` block** unnecessarily. Overriding it can accidentally drop parent filtering defaults. Check `mvn help:effective-pom` and actual `target/classes` outputs whenever customizing.

### 10.2. Do not confuse Maven filtering with Spring placeholders

| Syntax | When resolved | Example |
| --- | --- | --- |
| `@project.version@` | Maven `process-resources` if filtering is enabled | Artifact version, build metadata |
| `${SERVICE_HOST:localhost}` | Spring Boot runtime property resolution | Per-environment host |
| `--server.port=9090` | Spring Boot runtime CLI property | Per-environment port |
| `SPRING_PROFILES_ACTIVE=prod` | Application process environment | Profile selection |
| `-Ddemo.region=prod` before `-jar` | App JVM Java system property | Runtime override |

When Maven build logs show a placeholder stayed unreplaced, check which resource filter set owns the file, whether starter parent is used, delimiter config, and `mvn process-resources`. When Spring Boot fails resolving a placeholder due to a missing env var, that is **runtime configuration**—do not "fix" it by filtering secrets into the JAR at build time.

## 11. Gradle Kotlin DSL: building the same resource layout

If using Gradle instead of Maven, keep the exact Java source and `src/main/resources` from section 4, replacing `pom.xml` with two files:

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "resource-demo"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Using a Gradle Wrapper compatible with the Spring Boot plugin, from project root:

```bash
./gradlew clean bootJar
java -jar build/libs/resource-demo-0.0.1-SNAPSHOT.jar
```

On Windows use `gradlew.bat`. If the repo lacks a wrapper, create one with a matching, project-controlled Gradle version. `bootJar` produces the executable JAR; `build/libs` paths reflect project name, version, and archive customizations. `processResources` copies `src/main/resources` into `build/resources/main`, which then enters `BOOT-INF/classes` inside the archive.

### 11.1. Filter only dedicated text files rather than all resources

Suppose you want isolated build metadata in:

**`src/main/resources/build-info.properties`:**

```properties
app.build.version=${buildVersion}
```

This is a **Gradle template expansion placeholder**, not a Spring runtime property. In `build.gradle.kts`, add:

```kotlin
import org.gradle.language.jvm.tasks.ProcessResources

val buildVersionForResources = version.toString()

tasks.named<ProcessResources>("processResources") {
    filesMatching("build-info.properties") {
        expand(mapOf("buildVersion" to buildVersionForResources))
    }
}
```

After `./gradlew processResources`, `build/resources/main/build-info.properties` contains:

```properties
app.build.version=0.0.1-SNAPSHOT
```

Using `filesMatching("build-info.properties")` avoids running template expansion on binary files or on `application.properties` containing Spring `${...}` placeholders. Gradle's `expand` relies on template expansion that processes `${name}`, which **easily collides with Spring property placeholders** if applied broadly. Never run `expand(project.properties)` across all resources when runtime placeholders must stay intact.

If a project has custom resource directories, configure `sourceSets.main.resources` per the Gradle Java plugin and verify the output. Do not add `from("src/main/resources")` again directly into `bootJar` when `processResources` already includes it, or you risk duplicate paths or bypassing packaging rules.

## 12. Docker: same image, different mounted config

A strong container pattern is: build tested JAR → copy JAR into image → inject environment settings via env/volumes/secrets at deployment.

**Dockerfile** for the Maven sample artifact:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/resource-demo-0.0.1-SNAPSHOT.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Build:

```bash
mvn -B -ntp clean package
docker build -t resource-demo:dev .
```

Run the image with the **exact `runtime-config/application.properties`** from section 6 mounted read-only:

```bash
docker run --rm \
  -p 127.0.0.1:9090:9090 \
  -v "$PWD/runtime-config:/config:ro" \
  resource-demo:dev \
  --spring.config.additional-location=optional:file:/config/
```

This command applies to Bash/Linux/macOS with Docker authorized to bind-mount the project folder. On Windows PowerShell, adjust the host path and line continuations. Inside the container, the **working directory is `/app`**, while the external file is mounted at **`/config/application.properties`**. `--spring.config.additional-location=...` is passed to the Spring application **after** the image entrypoint without modifying the JAR.

Once running, `curl -fsS http://localhost:9090/values` returns:

```text
message=external;region=staging
```

Because `-p 127.0.0.1:9090:9090` binds only to host loopback for local practice, external hosts cannot reach this port automatically. Production deployments need proper network/routing policies instead of copying this dev binding verbatim.

**Note:** `EXPOSE 8080` in a Dockerfile is metadata only; it does not force Spring Boot to listen on 8080. Because the external file sets `server.port=9090`, Docker `-p` must map to **container port 9090**. Changing ports never requires rebuilding the image as long as container routing is updated.

When no mounted file is needed, run the exact same image with runtime env vars:

```bash
docker run --rm \
  -p 127.0.0.1:8080:8080 \
  -e DEMO_MESSAGE=container \
  resource-demo:dev
```

With `demo.region` still `local` in packaged config, `/values` returns `message=container;region=local`. In production, tokens and DB passwords must come from proper secret mechanisms—never baked into image layers via `docker build --build-arg`.

## 13. Kubernetes: ConfigMap, Secret, and Config Data

Kubernetes provides two primitives matching this lesson's separation:

- **ConfigMap:** non-sensitive configuration; mountable as `application.properties` files or injected as environment variables.
- **Secret:** sensitive values (never treat a Kubernetes Secret object alone as complete security); typically mounted as read-restricted files or injected via env per policy.

**Snippet inside a Kubernetes Deployment** (not a standalone Deployment YAML):

```yaml
containers:
  - name: app
    image: registry.example.org/resource-demo:release-1
    args:
      - "--spring.config.additional-location=file:/config/"
    volumeMounts:
      - name: app-config
        mountPath: /config
        readOnly: true
      - name: app-secret
        mountPath: /run/secrets
        readOnly: true
volumes:
  - name: app-config
    configMap:
      name: resource-demo-config
  - name: app-secret
    secret:
      secretName: resource-demo-secret
```

This snippet assumes the image defines `ENTRYPOINT ["java","-jar","/app/app.jar"]` as in the Dockerfile, the ConfigMap holds an **`application.properties`** key, and the Kubernetes Secret exists in the right namespace with proper RBAC. `registry.example.org` and resource names are placeholders to be replaced with real infrastructure. For mandatory config, omitting `optional:` in `spring.config.additional-location=file:/config/` makes the app fail fast if the volume is unmounted.

To import secrets stored one file per key, put in **external `/config/application.properties`**:

```properties
spring.config.import=configtree:/run/secrets/
```

For example, a file mounted at `/run/secrets/demo.api-key` becomes property `demo.api-key`. Never expose real keys in docs, logs, or error pages. Note that when a Secret updates, Kubernetes may update the mounted volume, yet **the application does not automatically reload Spring `Environment` by default**, because standard Config Data loads at startup; plan rollouts/restarts or an explicitly designed and tested refresh mechanism.

**One image across namespaces:** swap ConfigMaps, Secrets, runtime envs, and deployment settings without rebuilding per-namespace JARs. Still ensure **matching configuration versions** accompany the image; an incompatible config can still crash an unchanged binary.

## 14. Customizing which resources enter the archive

Sometimes a repo contains source files that must not ship: large test fixtures, dev-local files, sample credentials, sample datasets, or doc-only images. **Moving them outside `src/main/resources`** is the first-line solution. Where custom packaging is still needed, use explicit includes/excludes.

### 14.1. Maven: `<resources>` blocks and exclusions

In Maven POMs, `<build><resources>` configures resource folders, filtering, and include/exclude patterns. Example:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>dev-only/**</exclude>
                <exclude>private/**</exclude>
            </excludes>
        </resource>
    </resources>
</build>
```

**This is an illustrative snippet; never paste it verbatim into a starter-parent POM without checking side effects.** It alters resource processing and can drop `application.properties` filtering conventions inherited from the parent. In real projects, prefer moving files out of the resource source set; if exclusions are required, align carefully with the effective POM and verify the artifact. Keeping secrets out of Git/CI inputs from the outset remains far more important than relying on a late exclude rule.

### 14.2. Gradle: `processResources` excludes

In `build.gradle.kts`:

```kotlin
import org.gradle.language.jvm.tasks.ProcessResources

tasks.named<ProcessResources>("processResources") {
    exclude("dev-only/**", "private/**")
}
```

This is a **supplemental snippet** assuming the Java plugin is applied. Excluded files are omitted from main resource outputs. If also applying the `processResources` filtering snippet from section 11.1, combine them cleanly in the same task without conflicting rules.

**Limitations:** exclusions only filter paths matched by that task. Sensitive files can enter the artifact from other paths (custom `from(...)` tasks, dependency JARs, Docker build contexts, generated resources). Always inspect the **final artifact**, rather than trusting `build.gradle.kts` or `pom.xml` alone.

### 14.3. Generated resources

If the build generates version metadata or schemas, keep generators and outputs under the build directory (`target/generated-resources` or `build/generated/resources`), register them with Maven/Gradle resource phases, and declare task inputs/outputs properly. Avoid writing generated files back into `src/main/resources` unless you intentionally commit them. In Gradle, wire generator outputs via tasks/providers so the build cache and task graph track dependencies cleanly rather than writing files manually without hooking into `processResources`.

## 15. Verifying packaging and external config in CI/CD

A pipeline checking only `mvn package` success can still emit a JAR missing templates, leaking secrets, or failing under runtime config. Add at least these QA layers:

### 15.1. Verify archive contents

Bash:

```bash
set -e
mvn -B -ntp clean verify

JAR=target/resource-demo-0.0.1-SNAPSHOT.jar
test -f "$JAR"

jar tf "$JAR" |
  grep -q '^BOOT-INF/classes/assets/banner.txt$'

jar tf "$JAR" |
  grep -q '^BOOT-INF/classes/application.properties$'

jar tf "$JAR" |
  grep -q '^BOOT-INF/classes/static/welcome.txt$'
```

This is a Bash script requiring `grep`/`test` and Maven, not a full YAML pipeline. For Gradle, swap the build command to `./gradlew clean build bootJar` and update the JAR path. These checks verify **presence**, not sensitive-content scanning.

### 15.2. Check for unwanted resources/secrets

Example filename scan across archive entries:

```bash
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar |
  grep -Ei '(^|/)(\.env|id_rsa|secret|private-key|.*\.pem|.*\.p12)(/|$)' || true
```

Results can have **false positives** (e.g., a legitimate library containing "secret" in a filename) or **false negatives** (a secret stored in `config.json`). Never treat an empty `grep` as proof no secrets exist. Run proper secret scanners/SBOM/CI policies, and inspect Docker build contexts, generated files, and nested dependency JARs as needed. Never print secret values in CI logs just to confirm presence or absence.

### 15.3. Run smoke tests with both default and external config

- Launch the artifact without external files; verify `/values` returns `message=packaged;region=local` and `/banner` returns `BANNER_FROM_ARCHIVE`.
- Stop the JVM and run the **exact same artifact** with `--spring.config.additional-location=optional:file:./runtime-config/`; verify `/values` returns `message=external;region=staging` on port 9090.
- Run a session with `DEMO_MESSAGE=from-env` to verify precedence.
- Verify HTTP status codes, startup logs, and fail-fast behavior when mandatory external config is missing.
- Hash the artifact before and after runs (`sha256sum` on Linux, `Get-FileHash` on PowerShell) if proving binary immutability.

Smoke tests can be automated with a script launching the background process, polling readiness/HTTP responses, asserting bodies, and cleaning up inside `finally`/`trap`. Avoid `sleep 5` as a readiness guarantee; startup times vary across CI runners.

### 15.4. Separating build-time from run-time in the release pipeline

```text
Build (CI):
  checkout source + dependencies
  -> test
  -> processResources
  -> executable JAR
  -> inspect / scan / checksum
  -> publish immutable artifact

Deploy (CD):
  select exact artifact digest
  -> supply ConfigMap / config file / env / secret
  -> start JVM with runtime args
  -> verify readiness / smoke test
  -> rollout / rollback per release
```

**Build-time** values like `project.version` belong in filtered resource files because they bind to the artifact version. **Runtime** values like `spring.datasource.url` or secrets must never pass through Maven/Gradle filtering at image build time. Keeping both stages separate eliminates unnecessary "one JAR per environment" builds.

## 16. Common failures and diagnostics

| Symptom | Possible cause | How to inspect |
| --- | --- | --- |
| `ClassPathResource("assets/banner.txt")` not found | File missing from `src/main/resources/assets`, excluded, or wrong module built | Run `jar tf` looking for `BOOT-INF/classes/assets/banner.txt` |
| Works in IDE yet fails under `java -jar` | Called `getFile()`/`Path` on an archive-nested resource | Switch to `getInputStream()` / Spring `Resource` |
| `java -jar` uses defaults instead of external values | External file not found, wrong working directory, or missing `additional-location` | Verify location/path/filename and startup config logs |
| `spring.config.location` erased JAR defaults | Property replaces default search locations | Use `spring.config.additional-location` to append |
| `application.properties` overridden unexpectedly | Env var or CLI arg has higher precedence | Check `DEMO_MESSAGE`, `-Ddemo.message`, `--demo.message` |
| `application-prod.yml` ignored | `prod` profile not active, or wrong profile/location | Check `spring.profiles.active` and filename |
| `ConfigDataLocationNotFoundException` | Mandatory external location does not exist | Supply real file/volume or add `optional:` if missing is allowed |
| Docker listens on 9090 while host maps 8080 | External `server.port` changed inside container | Map host port to the actual container app port |
| Maven placeholder `@project.version@` unreplaced | Filtering disabled/overridden or not using starter parent | Check `target/classes` and effective POM |
| Spring placeholder `${SERVICE_HOST}` mangled by Maven | Filtering used default `${...}` delimiter colliding with Spring | Use `@...@` convention or explicit filtering delimiters |
| Gradle `expand` fails on `application.properties` | Template expansion tried parsing Spring `${...}` | Restrict filtering to dedicated build-metadata files |
| Binary files/resources corrupted post-build | Filtering rewrote bytes in images/certs/fonts/JARs | Disable filtering on binaries; compare checksums |
| `/welcome.txt` returns 404 despite file in JAR | Wrong static folder, custom MVC mapping/security/context path | Check `static/` and Spring MVC resource handler config |
| App runs yet uploaded files vanish after restart | Wrote to ephemeral container layer or confused classpath archive | Use persistent volumes/object storage for runtime data |
| Updated ConfigMap/Secret yet app still uses old values | Spring Config Data loaded once at startup | Trigger rollout/restart or implement a tested refresh mechanism |
| Secret found inside JAR | Placed in `src/main/resources`, filtered, or generated | Move secret to runtime, rotate secret, tighten CI scanning |
| Spring Boot JAR lacks `BOOT-INF/classes` | Inspecting plain JAR, wrong plugin, or missed `repackage`/`bootJar` | Check Boot plugin, artifact path, and manifest |
| Absolute file path works locally, fails in CI | Different OS/container/machine filesystem | Supply external path at deploy and check mounts/permissions |

### Step-by-step troubleshooting order

1. Decide **whether this is a versioned resource or runtime configuration**. For stable resources check the artifact; for environment-specific values check external config sources.
2. Verify exact artifact path, Maven/Gradle module, Java version, and source path.
3. For resources inside the JAR: confirm entry via `jar tf` and read via classpath `InputStream`, never IDE filesystem paths.
4. For external `application.properties`: verify working directory, `file:` URI, trailing `/` on directories, `optional:`, and read permissions.
5. Check active profiles, default/extra/import locations, and higher-precedence property sources.
6. For containers: check mount paths **inside the container**, actual app port, UID/permissions, and rollout state.
7. For sensitive values: never print values for debugging; log only key names/presence status if permitted, and verify secret injection outside logs.
8. Rebuild or restart matching the change type: updating external runtime files usually requires a **restart/config reload**, not a new JAR build.
9. Run smoke tests verifying both config values and packaged resources behave as expected.

## 17. Misconceptions to avoid

1. **"Putting a file in `src/main/resources` means it can be edited post-deploy."** False: inside an executable JAR, it is immutable archive content.
2. **"`BOOT-INF/classes` must be passed to `ClassPathResource`."** False: `BOOT-INF/classes` is already the classpath root.
3. **"Every `application.properties` must stay outside the JAR."** No: non-sensitive defaults can live inside the JAR while external config overrides per environment.
4. **"Changing the database password requires editing the JAR."** No: inject via secret manager/env/file mount and rotate per deployment.
5. **"`spring.config.location` and `spring.config.additional-location` are the same."** No: one replaces default locations while the other appends to them.
6. **"An external file next to the JAR is always picked up by Spring Boot."** Not guaranteed: Spring checks working directory and configured locations, not necessarily the JAR's own directory.
7. **"`getFile()` always reads classpath resources."** False when resources reside inside an archive or nested JAR.
8. **"Putting secrets in `static` is safe because it's inside the JAR."** Quite the opposite: static contents can be served over HTTP.
9. **"Maven/Gradle filtering only substitutes versions."** False: misconfiguration can mangle placeholders or corrupt binary files.
10. **"Resource filtering and Spring property placeholders both run at startup."** False: Maven/Gradle filtering runs at build time; Spring placeholders run at runtime.
11. **"Grepping filenames guarantees no secrets exist."** False: filenames can look harmless or secrets can sit inside ordinary-looking files.
12. **"Mounting a new ConfigMap/Secret makes Spring auto-reload immediately."** Not guaranteed; Config Data loads at startup by default.
13. **"Profile-specific files should contain credentials."** False: packaged profile files ship everywhere with the JAR.
14. **"Changing external config changes the artifact's checksum."** False: editing only external files leaves the JAR's checksum unchanged.
15. **"An executable JAR bundles the Java runtime."** False: a regular Spring Boot JAR still needs a compatible JVM; native images and OCI images are different packaging formats.

## 18. Pre-release checklist

- **Resource classification:** identified which files belong with code vs. runtime config/secrets/data.
- **Production resources:** placed only non-sensitive defaults, assets, templates, and required schemas/migrations in `src/main/resources`.
- **Archive verification:** checked `BOOT-INF/classes`, `BOOT-INF/lib`, exact filenames, filtered outputs, and `InputStream` classpath lookups.
- **Runtime config:** verified file locations, working directories, active profiles, precedence, and fail-fast behavior for mandatory configs/secrets.
- **Build tooling:** Maven `process-resources` + `repackage` or Gradle `processResources` + `bootJar` using compatible plugin/JDK versions.
- **Filtering:** filtered only selected text files, avoiding Spring placeholder collisions and binary corruption.
- **Secret hygiene:** zero passwords, tokens, or private keys in Git/JARs/image layers/logs; enforced secret manager, RBAC, file permissions, and rotation.
- **Deployment layout:** mounted external volumes/configs read-only where appropriate; never wrote runtime data into the archive.
- **Testing:** smoke tested both default and overridden configs/profiles/ports, plus tested missing mandatory config failure behavior.
- **Reproducibility:** recorded JAR checksum/digest, external config versions, release metadata, and rollback plans.

## 19. Official documentation

- Spring Boot – [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): PropertySources, Config Data, default locations, `spring.config.location`, `spring.config.additional-location`, `spring.config.import`, and `configtree:`.
- Spring Boot – [Properties and Configuration](https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html): Maven `@...@` filtering, Gradle `expand`, and placeholder conflicts.
- Spring Boot – [Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): static resources in `/static`, `/public`, `/resources`, and `/META-INF/resources`.
- Spring Boot – [Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `BOOT-INF/lib`, and Boot Loader.
- Spring Boot Maven Plugin – [Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html): starter parent and `repackage`.
- Gradle – [The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): source sets, `processResources`, and resource outputs.
- Gradle – [Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): filtering/processing resources and packaging.
- Spring Framework – [Resource Interface](https://docs.spring.io/spring-framework/reference/core/resources.html): `Resource`, `ClassPathResource`, and `getInputStream()`.

**Conclusion:** resources **belonging to the application version** are packaged inside the executable JAR and accessed via classpath; **environment-specific** configuration must be provided outside the JAR via Spring Config Data, environment variables, CLI flags, or secret volumes. Maven/Gradle process `src/main/resources` at build time, while Spring Boot resolves runtime values at startup. Separating the two gives you **one immutable artifact** that is easy to audit, secure, and deploy consistently across dev, staging, and production.