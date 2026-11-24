# Managing `src/main`, `src/test`, and Associated Resources in a Spring Boot Project

During **Spring Boot project initialization**, how you organize source code and resources determines what gets compiled, what is on the runtime **classpath**, what serves only for testing, and what goes into the deployment package. Maven and Gradle share nearly identical directory conventions; following these conventions keeps your IDE, build tool, tests, and JAR files working consistently.

After this lesson, you will be able to: place each file type in the right location; explain the difference between the main classpath and test classpath; read resources once the application is packaged; manage configuration, test data, and web resources; verify build outputs; and recognize common mistakes.

## 1. The Four Core Source Directories

A common directory structure for a Java Spring Boot application:

```text
demo/
├── build.gradle                 # Gradle (or pom.xml if using Maven)
├── settings.gradle
├── gradlew                      # Gradle Wrapper
├── gradlew.bat                  # Wrapper for Windows
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/demo/
    │   │       ├── DemoApplication.java
    │   │       └── GreetingService.java
    │   └── resources/
    │       ├── application.yml
    │       ├── greeting.txt
    │       ├── static/
    │       │   └── index.html
    │       └── templates/
    │           └── welcome.html
    └── test/
        ├── java/
        │   └── com/example/demo/
        │       └── GreetingServiceTest.java
        └── resources/
            ├── application-test.yml
            └── fixtures/
                └── sample-order.json
```

Each directory serves a distinct role:

| Path | What Belongs Here | Where Is It Used? | Included in a Typical Application JAR? |
| --- | --- | --- | --- |
| `src/main/java` | Production Java classes: `@SpringBootApplication` class, controllers, services, configuration, models | Compiled into `.class` files on the main classpath | **Yes**, as compiled classes |
| `src/main/resources` | `application.yml`, text files, templates, static assets, configuration metadata | Processed/copied onto the main classpath | **Yes**, unless explicitly excluded |
| `src/test/java` | Unit tests, integration tests, and test helper code | Compiled/run during the test phase | **No**, excluded from the executable JAR by convention |
| `src/test/resources` | JSON/CSV fixtures, configuration, and sample files strictly for tests | Available on the test classpath | **No**, excluded from the executable JAR by convention |

`src/main` and `src/test` are **two source sets** of the project, not Java package names. For example, a class in `src/main/java/com/example/demo/GreetingService.java` declares `package com.example.demo;`. Test classes can share the same package while residing under `src/test/java`.

When using Maven, the configuration file is `pom.xml`; with Gradle, it is typically `build.gradle` or `build.gradle.kts`. Build file names differ, but the four default source directories are the same.

## 2. How Does the Build Tool Turn Directories into the Classpath?

The **classpath** is the set of locations where Java/Spring looks up classes and resources at runtime.

- **Main classpath:** compiled classes from `src/main/java` together with resources from `src/main/resources` and required runtime libraries.
- **Test classpath:** test classes/resources from `src/test`, plus main classes/resources and test-only dependencies such as JUnit.
- **Executable JAR classpath:** main classes/resources and appropriately packaged dependencies; by default it does not contain code or fixtures from `src/test`.

Default flow:

```text
src/main/java       --compileJava (Gradle)----------> main classes
src/main/resources  --processResources--------------> main resources
                                                     \
                                                      +--> bootJar / package --> runnable JAR
src/test/java       --compileTestJava---------------> test classes
src/test/resources  --processTestResources----------> test resources
                                                     \
                                                      +--> test (also uses main classes/resources)
```

`compileJava`, `processResources`, `compileTestJava`, `processTestResources`, `test`, and `bootJar` are common Gradle task names. Maven performs the corresponding work through phases `process-resources`, `compile`, `process-test-resources`, `test-compile`, `test`, and `package`.

Typical output locations:

| Output Type | Gradle | Maven |
| --- | --- | --- |
| Main classes | `build/classes/java/main` | `target/classes` |
| Main resources | `build/resources/main` | `target/classes` |
| Test classes | `build/classes/java/test` | `target/test-classes` |
| Test resources | `build/resources/test` | `target/test-classes` |

**Do not edit `build/` or `target/` directly**: these are regenerated outputs during a build. Files that must persist belong in the source directories or managed configuration.

## 3. Reading Resources from the Classpath: A Working Example in a Spring Boot Project

Suppose you want to place a greeting message in a data file and read it from Java code without hardcoding a path to the project directory.

**Step 1 — Create `src/main/resources/greeting.txt`** with the content:

```text
Hello from the classpath!
```

**Step 2 — Create `src/main/java/com/example/demo/GreetingService.java`:**

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class GreetingService {

    public String loadGreeting() throws IOException {
        try (InputStream input = GreetingService.class
                .getClassLoader()
                .getResourceAsStream("greeting.txt")) {

            if (input == null) {
                throw new IOException("greeting.txt not found on classpath");
            }

            return new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }
}
```

`getResourceAsStream("greeting.txt")` looks up the file from the **classpath root**. Because the file sits directly in `src/main/resources`, the lookup path is `greeting.txt`, not `src/main/resources/greeting.txt`. `try-with-resources` closes the stream automatically; `StandardCharsets.UTF_8` avoids relying on the default charset; `strip()` removes trailing newlines.

**Step 3 — Create `src/test/java/com/example/demo/GreetingServiceTest.java`:**

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {

    @Test
    void readsMainResourceFromTestClasspath() throws IOException {
        GreetingService service = new GreetingService();

        assertEquals(
                "Hello from the classpath!",
                service.loadGreeting()
        );
    }
}
```

The test can access `GreetingService` and `greeting.txt` because **the test classpath includes main outputs**. This is a class executed by JUnit, not a standalone Java program with a `main` method. The example uses syntax compatible with Java 17+ and requires JUnit Jupiter on the test classpath. In a Spring Boot project generated from Initializr, the `spring-boot-starter-test` dependency typically covers this; with Gradle, ensure the `test` task is configured to use JUnit Platform.

**Step 4 — Run tests from the project root directory:**

```bash
# macOS / Linux, Gradle project
./gradlew test

# macOS / Linux, Maven project
./mvnw test
```

On Windows PowerShell, use `.\gradlew.bat test` or `.\mvnw.cmd test`. If the project does not yet have a wrapper, run `gradle test` or `mvn test` when the tool is installed. For Gradle using JUnit Jupiter, a common configuration in `build.gradle` (Groovy DSL) is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Only add any missing lines; do not declare duplicate dependencies that already exist. If the test passes, JUnit confirms the string actually read from the resource is `Hello from the classpath!`; there is no need to guess a fixed stdout line from Gradle/Maven since logs vary by version and configuration.

**Why not use `new File("src/main/resources/greeting.txt")`?** That path depends on the working directory and on the source file existing on disk. When running `java -jar` on another machine, the resource typically lives **inside the JAR**, no longer as a standalone file at the source path. Classpath APIs like `ClassLoader.getResourceAsStream` or Spring's `ClassPathResource` can read packaged contents. If you need to write data that changes at runtime, use a directory outside the JAR rather than writing back into packaged resources.

## 4. Distinguishing Application Resources, Configuration, and Test Data

### 4.1. Spring Boot Configuration

`src/main/resources/application.yml` contains default configuration packaged with the application:

```yaml
app:
  display-name: "Demo"
logging:
  level:
    root: INFO
```

`src/test/resources/application-test.yml` can provide values for the test profile:

```yaml
app:
  display-name: "Demo Test"
```

In a Spring test that boots the application context, use `@ActiveProfiles("test")` to activate the `test` profile; Spring Boot can then load `application-test.yml` and apply configuration precedence rules. Merely placing `application-test.yml` in `src/test/resources` **does not automatically activate** the `test` profile. For the plain Java/JUnit test in section 3, neither a Spring context nor profiles are initialized automatically.

Distinction:
- `application.yml` in main can go into the deployment package.
- `application-test.yml` in test only serves tests for the current build and does not go into the executable JAR by default.
- `application-dev.yml` or `application-prod.yml` in main are profile configurations that **can be packaged**; the profile name does not keep the file's contents secret.

Do not store real passwords, access tokens, or private keys in committed/packaged resources. Use environment variables, a secret manager, or external configuration per deployment environment. External configuration can override packaged values depending on Spring Boot's property precedence order.

### 4.2. Web Resources and Templates

Common paths under `src/main/resources`:

| Directory | Role | Things to Note |
| --- | --- | --- |
| `static/` | Static HTML, CSS, JavaScript, images | With appropriately configured Spring MVC/WebFlux, can be served directly over HTTP; do not put sensitive data here |
| `public/` | Another default location for static assets | Avoid creating duplicate-URL resources that are hard to manage |
| `templates/` | HTML templates for template engines, e.g., Thymeleaf | Requires a template engine dependency and configuration to render; placing a file here alone does not create an endpoint |
| `META-INF/` | Metadata per Java/library conventions | Path and filenames must match the conventions of the feature using them |

For example, `src/main/resources/static/index.html` can serve as the welcome page of a Spring Boot web application when static/welcome page handling conditions are met. Meanwhile, `templates/welcome.html` does not automatically become a URL; you usually need a controller returning the view name and a corresponding template engine.

### 4.3. Test-Specific Fixtures

Place JSON, CSV, sample data scripts, or mock responses in `src/test/resources`:

```text
src/test/resources/
└── fixtures/
    └── sample-order.json
```

In tests, look it up via the classpath path `fixtures/sample-order.json`. This keeps sample data separate from the deployment artifact and ensures tests run consistently on developer machines and CI.

If `src/main/resources` and `src/test/resources` have files at the same relative path, the test resource may shadow the main resource depending on classpath order. Only use this override intentionally with verifying tests; prefer distinct names/paths to avoid tests behaving differently across environments.

## 5. Changing Resource Paths When Truly Necessary

**Prefer default conventions.** Only configure additional directories outside `src/main/resources` for a concrete reason, such as a module having a shared resource folder managed by the build.

Example **Gradle Groovy DSL** adding `shared/config` to main resources while keeping the default path:

```groovy
sourceSets {
    main {
        resources {
            srcDir 'shared/config'
        }
    }
}
```

Gradle processes files in main resource directories to place them on the classpath; `srcDir` adds an extra source directory. If two directories contain the same target path, resolve duplicates intentionally according to the project's resource-handling configuration.

Example **Maven** declaring an extra resource directory in `pom.xml`, listing the default directory as well because an explicit `<resources>` block can replace the default resource configuration:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
        </resource>
        <resource>
            <directory>shared/config</directory>
        </resource>
    </resources>
</build>
```

These examples only modify main resource paths; they do **not** put `src/test/resources` into the production package. Nor should you move Java files into the resources folder or manually copy files from `src/main/resources` to `build/` or `target/`.

When you need to transform resource contents at build time, you can use Gradle's `processResources` or Maven's resource filtering. Enable it only for necessary files: accidentally filtering `application.yml` containing Spring placeholders, unintended substitutions, or injecting secrets into packaged files can cause operational/security issues. Inspect the **processed file content**, not just the source file.

## 6. Inspecting Outputs and JAR Contents

For an application with the Spring Boot Gradle plugin and Java plugin configured to build an executable JAR:

```bash
./gradlew clean test bootJar
```

With Maven Wrapper and the Spring Boot Maven plugin configured for repackage:

```bash
./mvnw clean verify
```

On Windows, use `.\gradlew.bat clean test bootJar` or `.\mvnw.cmd clean verify`. Specific commands and JAR files depend on project name, version, plugins, and packaging mode; do not assume every project produces an executable JAR.

After building, inspect:

1. **Main output:** `build/classes/java/main` and `build/resources/main` (Gradle), or `target/classes` (Maven) contain the expected classes/resources.
2. **Test output:** test directories contain classes and fixtures for `test`, not used as runtime application data.
3. **JAR file:** run `jar tf <path-to-jar-file>` with the exact path of the generated artifact. For a common Spring Boot executable JAR layout, look for `BOOT-INF/classes/com/example/demo/GreetingService.class` and `BOOT-INF/classes/greeting.txt`; dependencies typically reside under `BOOT-INF/lib/`.
4. **No leaked tests:** `GreetingServiceTest.class` and `fixtures/sample-order.json` should not appear in the default executable JAR.

`jar tf` is a JDK command to **list** archive contents; it does not run the application. If using a plain JAR, WAR, or another packaging layout, internal paths may differ from `BOOT-INF/classes`. Inspect the actual artifact rather than relying solely on source filenames.

## 7. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Works in IDE but `java -jar` reports file not found | Using relative path `src/main/resources/...` as a filesystem path | Read via classpath stream/`ClassPathResource`; verify file inside JAR |
| `getResourceAsStream` returns `null` | Wrong path or file not copied to resource output | Confirm the file is in `src/main/resources`/`src/test/resources` as intended; look up using path from classpath root |
| Test compile error `package org.junit.jupiter.api does not exist` | Missing test dependency or JUnit configuration | Add `spring-boot-starter-test` with proper scope/configuration and configure the matching test engine |
| Tests see different data than runtime | Same-named file in main/test or active test profile | Check paths, classpath order, profiles, and configuration sources |
| Fixture file appears in deployed application | Fixture placed in main by mistake or copied from test to main | Move to `src/test/resources` and remove the erroneous copy rule |
| Edits in `build/` or `target/` disappear on next run | Editing outputs instead of sources | Edit under `src/...`, rebuild, and verify the artifact |
| Web resource is unreachable | Placed under `templates`, missing web stack, or static configuration | Put static assets under `static`/`public`; verify web dependency and routing |
| Profile-specific config values are not applied | Profile not activated or overridden by external config | Check active profiles and property source precedence |

## 8. Checklist When Initializing or Expanding a Project

- [ ] Application code is in `src/main/java` with packages matching directory paths; tests are in `src/test/java`.
- [ ] Runtime configuration/resources are in `src/main/resources`; test-only fixtures and configuration are in `src/test/resources`.
- [ ] Code loads resources via the **classpath**, independent of working directory or source directories existing after packaging.
- [ ] Tests have appropriate dependencies and test engine; test profiles are activated intentionally.
- [ ] Static assets and templates are placed properly with matching dependencies/runtime.
- [ ] No secrets or test data are packaged accidentally; build outputs are never edited manually.
- [ ] Tests are run and the JAR is inspected to confirm required classes/resources are packaged and test resources are excluded.

**Decision rule:** files serving the deployed application belong in `main`; files solely for verifying behavior belong in `test`. Java sources are **compiled**; resources are **placed on the classpath**; the build tool decides what appears in the final artifact.