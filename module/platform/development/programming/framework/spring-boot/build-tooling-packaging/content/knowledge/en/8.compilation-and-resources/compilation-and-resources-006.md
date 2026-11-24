# Property Interpolation in Resources and Avoiding Conflicts with Spring Placeholders

## 1. Objectives

When building a Spring Boot application, files in `src/main/resources` can contain both **values known at build time** (artifact version, product name, build ID) and **variables available only when the application runs** (HTTP port, service URLs, environment-specific settings). Maven, Gradle, and Spring all support placeholder substitution; if they all interpret `${...}` without separating stages, a Spring placeholder can be replaced too early, disappear, or break the build.

After this lesson, you will understand:

1. How **resource filtering/build-time interpolation** differs from **Spring property placeholders/runtime resolution**.
2. Which files are copied or interpolated, and where they end up after `process-resources`, `processResources`, `jar`, or `bootJar`.
3. Why Maven uses `@...@` for build variables and `${...}` for Spring runtime, plus the critical role of `<useDefaultDelimiters>false</useDefaultDelimiters>`.
4. How to configure filtering properly with or without `spring-boot-starter-parent`, while avoiding unintended processing of binaries and `src/test/resources`.
5. Equivalent approaches in Gradle: one using **exact token replacement** without touching Spring placeholders, and one using `expand()` with escaping.
6. How to write a runnable example with Spring Boot 4.1.2, Java 17, Maven, and Gradle, plus a test verifying filtered resources.
7. How to diagnose placeholder bugs along the chain **source → processed resource → packaged JAR → runtime Environment**.

**Practice scenario:** at build time, the project version is `1.0.0`; at runtime, the application keeps `${APP_MESSAGE:Hello runtime}` and `${SERVER_PORT:8080}` so they can be changed via environment variables **without rebuilding the JAR**.

## 2. Three Distinct Stages

~~~text
[1] Source in repository
src/main/resources/application.properties
  app.build-version=@project.version@       <- build-time token
  app.message=${APP_MESSAGE:Hello runtime}  <- runtime Spring placeholder
  server.port=${SERVER_PORT:8080}

                 |
                 | Maven resources:resources / Gradle processResources
                 v

[2] Post-build resource
Maven:  target/classes/application.properties
Gradle: build/resources/main/application.properties
  app.build-version=1.0.0
  app.message=${APP_MESSAGE:Hello runtime}
  server.port=${SERVER_PORT:8080}

                 |
                 | Boot Maven repackage / Gradle bootJar
                 v

[3] Spring Boot executable JAR
BOOT-INF/classes/application.properties
  app.build-version=1.0.0
  app.message=${APP_MESSAGE:Hello runtime}
  server.port=${SERVER_PORT:8080}

                 |
                 | JVM + Spring Environment reads configuration on startup
                 v

Runtime:
  APP_MESSAGE unset -> "Hello runtime"
  APP_MESSAGE=Hello production -> "Hello production"
  SERVER_PORT unset -> 8080
~~~

Comparison table:

| Mechanism | When? | Handled by? | Common syntax | Value source |
| --- | --- | --- | --- | --- |
| **Maven resource filtering** | `process-resources`, before compile/package | `maven-resources-plugin` | `@project.version@`; also supports `${...}` by default unless disabled | POM/project properties, filter files, Maven user/system properties |
| **Gradle CopySpec/filter** | `processResources` task, before packaging | Gradle CopySpec or filter reader | `@project.version@` when defining custom tokens | `project.version` or chosen token map |
| **Gradle `expand()`** | When `processResources` copies files | Groovy `SimpleTemplateEngine` | `${buildVersion}` and template expressions | Map passed to `expand` |
| **Spring property placeholder** | When Spring loads/resolves config at runtime | Spring `Environment`, property sources, binding | `${APP_MESSAGE:Hello runtime}`, `${server.port}` | Environment variables, system properties, command-line args, config files, etc. |
| **Spring Expression Language (SpEL)** | Where the framework evaluates expressions | Spring | `#{...}` | Spring context and permitted objects |

**Do not confuse:** `@Value("${app.build-version}")` in Java code is a Spring placeholder *inside Java source*, not a resource file. Maven Resources Plugin does not scan and replace Java source files under normal setup. `@Value` is resolved by Spring only when creating beans and resolving configuration values.

## 3. Correct Input and Output Example

File **`src/main/resources/application.properties`**:

~~~properties
spring.application.name=filter-demo
app.build-version=@project.version@
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

**Build step input:** the file above + Maven project version `1.0.0` (or the equivalent Gradle project version).

**Desired output after resource filtering:**

~~~properties
spring.application.name=filter-demo
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Only **`@project.version@`** is substituted; both `${...}` expressions remain intact in the packaged file. At runtime, Spring reads property sources and resolves:

- `${APP_MESSAGE:Hello runtime}`: reads `APP_MESSAGE` from the environment if present; otherwise uses the default string.
- `${SERVER_PORT:8080}`: reads `SERVER_PORT` if supplied with a valid value; otherwise defaults to `8080`.
- `app.build-version=1.0.0`: version recorded by the build in the artifact. This acts as the default packaged value; Spring can still accept overrides from higher-priority property sources such as command-line arguments.

### Spring's Default Syntax Is Not a Maven Expression

In Spring, the colon in `${NAME:default}` separates the **property name** from its **fallback value**. Do not treat `${NAME:default}` as a Maven/Groovy token merely because it uses `$` and curly braces.

If a placeholder `${NAME}` has no default and `NAME` is absent from all property sources, its consumer may fail with an unresolved placeholder error depending on how the value is accessed. Supply defaults deliberately, or require mandatory variables and validate them at startup.

## 4. Maven: Why Change the Delimiter?

Apache Maven Resources Plugin supports both **`${name}`** and **`@name@`** token formats when filtering is enabled with default delimiters. Because Spring also uses **`${...}`**, their syntaxes overlap:

~~~properties
# Source intended for Spring to resolve at runtime
spring.datasource.url=${DB_URL:jdbc:postgresql://localhost:5432/demo}
server.port=${SERVER_PORT:8080}
~~~

If Maven is allowed to treat every `${...}` as a build token, variables whose names match Maven, project, or system properties can be replaced at build time. Unmatched expressions may pass through untouched; **do not rely on an expression currently happening not to resolve as proof of safety**. A new CI or corporate parent property could silently alter future builds.

**Common Maven solution:** switch build placeholders to **`@...@`** and disable default delimiters:

~~~xml
<configuration>
    <delimiters>
        <delimiter>@</delimiter>
    </delimiters>
    <useDefaultDelimiters>false</useDefaultDelimiters>
</configuration>
~~~

Meaning:

- `<delimiter>@</delimiter>`: build tokens use the form `@project.version@`, `@project.artifactId@`, `@my.build.property@`.
- `<useDefaultDelimiters>false</useDefaultDelimiters>`: **excludes** the default delimiters, notably `${...}`, from filtering.
- The filtered resource file can then safely hold both `@project.version@` tokens and `${APP_MESSAGE:...}` Spring placeholders without conflict.

The Spring Boot starter parent preconfigures suitable resource filtering for `application.properties`/`application.yml` and profile variants using `@...@` to prevent collisions. **When not using the starter parent**, importing the `spring-boot-dependencies` BOM **does not bring in Maven Resources Plugin settings**; you must declare `<resources>` and plugin/delimiter settings explicitly.

### Declaring Delimiters Alone Is Not Enough

Maven does not interpolate every file under `src/main/resources` unless the corresponding resource entry sets `<filtering>true</filtering>`. Without it, resources are still copied, preserving the source bytes unchanged. You need **both**: defining **which files are filtered** and **which token syntax is replaced**.

## 5. Maven: Selecting Only the Right Files for Filtering

Never turn on `<filtering>true</filtering>` across the entire resource tree hoping images, fonts, PDFs, certificates, compressed archives, templates, or JSON files with delimiter-like characters stay safe. Filtering should apply only to **known text files containing build tokens**. All other files should be copied verbatim.

A clear setup inside `<build>`:

~~~xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
        <includes>
            <include>application.properties</include>
        </includes>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <excludes>
            <exclude>application.properties</exclude>
        </excludes>
    </resource>
</resources>
~~~

The first `<resource>` entry processes **only** `application.properties`. The second copies everything else **without filtering**. The matching include/exclude pair ensures the unfiltered copy does not overwrite the filtered `application.properties`.

If your project uses multiple configuration files, expand the `includes`/`excludes` pair to match the exact set used, for example:

~~~xml
<include>application.properties</include>
<include>application-*.properties</include>
<include>application.yml</include>
<include>application-*.yml</include>
<include>application.yaml</include>
<include>application-*.yaml</include>
~~~

**Note:** the second snippet lists sample patterns for both sets, not a standalone `pom.xml`. You do not need to filter every profile config file; filter only files that actually contain build tokens. Never filter binary files. Maven has built-in skips for certain image extensions and the `nonFilteredFileExtensions` option, yet **separating filtered and unfiltered sets** avoids format mishaps.

### YAML and Special Characters

In YAML, wrap `@`-delimited tokens in quotes, because a leading unquoted `@...@` is not a valid YAML scalar:

~~~yaml
app:
  build-version: "@project.version@"
  message: "${APP_MESSAGE:Hello runtime}"
server:
  port: "${SERVER_PORT:8080}"
~~~

Post-filtering output becomes `build-version: "1.0.0"` while Spring placeholders remain strings. When Spring binds `server.port` to an integer, the runtime-resolved value must be a valid number. If build interpolation turns YAML into invalid syntax, the build tool may still copy it cleanly: parse or start the app to verify.

### Test Resources Are a Separate Branch

`src/main/resources` flows through `process-resources`. `src/test/resources` flows through `process-test-resources`, with its own `testResources` config and goal. When using the Spring Boot starter parent, default filtering covers **production configuration**, not necessarily every test resource in the same way.

If tests include a file with the same name at `src/test/resources/application.properties`, the test file can shadow the main file on the test classpath, misleading tests of main resource filtering. In the hands-on example below, **do not create a same-named test resource** so the test reads the output from `src/main/resources`.

## 6. Standalone Maven Example Without Starter Parent

Select Java 17, Spring Boot 4.1.2, Maven 3.6.3+, and a compatible JDK. This example intentionally **omits `<parent>`** to show the manual filtering configuration required when importing only the Spring Boot BOM.

Structure:

~~~text
filter-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/FilterDemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/dev/example/FilteredResourceTest.java
~~~

### 6.1. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>filter-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>4.1.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>application.properties</include>
                </includes>
            </resource>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
                <excludes>
                    <exclude>application.properties</exclude>
                </excludes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>4.1.2</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <phase>package</phase>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Mechanism:

- Imports the BOM to manage starter versions without using `spring-boot-starter-parent`.
- Maven Resources Plugin `3.5.0` filters only `application.properties` with delimiter `@`. `useDefaultDelimiters=false` preserves `${...}` expressions for Spring.
- `maven-compiler-plugin` compiles with syntax/API/bytecode matching `release=17`.
- Surefire `3.6.1` runs the example's JUnit Jupiter tests.
- `maven-jar-plugin` builds the regular JAR, and Boot Maven Plugin `repackage` builds the executable archive. Build plugin configuration is independent of resource filtering; the two cooperate through the lifecycle.
- Other files, such as `banner.txt` or static images under `src/main/resources/static`, are copied by the second resource entry without interpolation.

### 6.2. `src/main/resources/application.properties`

~~~properties
spring.application.name=filter-demo
app.build-version=@project.version@
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

This is the **input file**. Do not change `@project.version@` to `${project.version}` in the Maven example, as that mixes build and Spring namespaces.

### 6.3. `src/main/java/dev/example/FilterDemoApplication.java`

~~~java
package dev.example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FilterDemoApplication {
    @Value("${app.build-version}")
    private String buildVersion;

    @Value("${app.message}")
    private String message;

    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }

    @GetMapping("/info")
    public String info() {
        return "build=" + buildVersion + "; message=" + message;
    }
}
~~~

When Spring creates the controller bean, both fields are injected via `@Value` from the runtime `Environment`. `@Value` is used here for brevity; for multiple structured properties, `@ConfigurationProperties` with validation is preferable. Placeholders inside Java source files are not replaced by Maven Resources Plugin.

### 6.4. `src/test/java/dev/example/FilteredResourceTest.java`

~~~java
package dev.example;

import java.io.InputStreamReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class FilteredResourceTest {
    @Test
    void interpolatesBuildVersionButPreservesSpringPlaceholders()
            throws IOException {
        try (var input = getClass().getResourceAsStream("/application.properties")) {
            assertNotNull(input, "Missing processed application.properties");
            var properties = new Properties();
            properties.load(new InputStreamReader(input, StandardCharsets.UTF_8));

            assertEquals("1.0.0", properties.getProperty("app.build-version"));
            assertEquals("${APP_MESSAGE:Hello runtime}",
                    properties.getProperty("app.message"));
            assertEquals("${SERVER_PORT:8080}",
                    properties.getProperty("server.port"));
        }
    }
}
~~~

The test reads **the file copied onto the test classpath**, rather than opening the source file directly. Because the project layout omits a conflicting `src/test/resources/application.properties`, this accurately verifies the resource filtering output. The two placeholder assertions are essential: the build must preserve those strings intact for Spring runtime.

### 6.5. Running Step by Step and Checking Outputs

In the directory containing `pom.xml`:

~~~bash
mvn -version
mvn clean process-resources
~~~

Open **`target/classes/application.properties`**. Exact expected contents:

~~~properties
spring.application.name=filter-demo
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Next step:

~~~bash
mvn clean verify
java -jar target/filter-demo-1.0.0.jar
~~~

In another terminal, once the server has started and neither `APP_MESSAGE` nor `SERVER_PORT` is set in the environment:

~~~bash
curl -fsS http://localhost:8080/info
~~~

**Exact HTTP response body:**

~~~text
build=1.0.0; message=Hello runtime
~~~

The response body is the string returned by the controller without a trailing newline from code. Spring Boot and Maven logs vary by system, so they are not shown as fixed stdout.

If the environment sets `APP_MESSAGE=Hello production`, restarting **the exact same JAR** returns:

~~~text
build=1.0.0; message=Hello production
~~~

This proves **version** was populated at build time while **message** is resolved at runtime. You can test overriding values without modifying machine environment variables via:

~~~bash
java -jar target/filter-demo-1.0.0.jar --app.message="Changed at runtime"
~~~

With that command, the HTTP response body becomes `build=1.0.0; message=Changed at runtime`. To change the port, pass `--server.port=8081` and call the URL on port 8081.

### 6.6. After Repackaging, Where Does the File Live?

In `target/filter-demo-1.0.0.jar`, with the default executable JAR layout, the resource sits at:

~~~text
BOOT-INF/classes/application.properties
~~~

You can list entries with:

~~~bash
jar tf target/filter-demo-1.0.0.jar
~~~

On a machine with `unzip`, you can print the packaged file directly:

~~~bash
unzip -p target/filter-demo-1.0.0.jar BOOT-INF/classes/application.properties
~~~

It should contain `app.build-version=1.0.0` and preserve both `${...}` expressions. If `target/classes` is right while the packaged JAR is wrong, verify which archive is being inspected, check `repackage`, and check for subsequent resource copy/overwrite steps.

## 7. Maven with Starter Parent: What Is Provided vs. What Must Still Be Checked

When the POM includes:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>
~~~

the starter parent supplies default **resource filtering** for application configuration files and configures `@...@` tokens to avoid `${...}` collisions. Therefore, in a project using the parent, e.g.:

~~~properties
app.build-version=@project.version@
app.port=${APP_PORT:8080}
~~~

you usually do not need to write out the full `resources` and `maven-resources-plugin` blocks shown in section 6's standalone POM. However, you **must inspect the effective POM** if a corporate parent, profile, or custom plugin config overrides defaults. Do not assume all files in `src/main/resources` are filtered identically.

Run:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean process-resources
~~~

Without the starter parent, the parent's default filter config is **not imported via the BOM**. If forgotten, `app.build-version=@project.version@` may remain literal in `target/classes/application.properties`, or Spring placeholders may be prematurely replaced because Maven still recognizes `${...}`.

**Another issue:** running `spring-boot:run` with `addResources=true` can place `src/main/resources` directly on the classpath for reload support, bypassing Maven-filtered resources. In that mode, values read from source files can differ from the packaged file. Verify the active run mode; inspecting `target/classes` and the JAR provides evidence of the real artifact.

## 8. Gradle: Understanding the Pitfalls of `expand()`

The Gradle Java plugin defines `processResources`, which normally copies `src/main/resources` to `build/resources/main`. By default, copying does not interpolate tokens in file contents. You can configure:

~~~groovy
tasks.named('processResources') {
    filesMatching('application.properties') {
        expand(buildVersion: project.version.toString())
    }
}
~~~

Here Gradle `expand()` invokes **Groovy `SimpleTemplateEngine`**. The source file for this approach would look like:

~~~properties
app.build-version=${buildVersion}
app.message=\${APP_MESSAGE:Hello runtime}
server.port=\${SERVER_PORT:8080}
~~~

Expected output after copying:

~~~properties
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

In **an input file using `expand()`**, the `\` immediately before `${...}` is a **Groovy template escape** so Gradle does not treat the Spring expression as a template variable. After processing, the backslash disappears from the output file. This syntax is specific to **Gradle `expand()`**, not general advice to insert backslashes into Spring config files.

**Key takeaway:** applying `expand(project.properties)` to all files instead of scoping to one file and specific keys risks letting Groovy evaluate Spring `${...}` expressions, substituting unintended values or failing on undefined variables/invalid syntax. This is a **mechanism conflict** and cannot be solved by switching Java runtimes.

Because escaping is easy to forget in projects with many Spring properties, this lesson prefers a Gradle variant that **replaces the exact literal `@project.version@` token**.

## 9. Gradle: Conflict-Free Example Using Exact Token Replacement

Keep `application.properties` and the Java code from section 6 unchanged:

~~~properties
spring.application.name=filter-demo
app.build-version=@project.version@
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Below is a **Gradle Groovy DSL** configuration sharing the same `@project.version@` convention as Maven and replacing only that exact token. It avoids Groovy `expand()`, so Spring `${...}` placeholders stay intact without escaping.

**`settings.gradle`**

~~~groovy
rootProject.name = 'filter-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

def buildVersionForResources = project.version.toString()

tasks.named('processResources') {
    filteringCharset = 'UTF-8'
    inputs.property('resourceBuildVersion', buildVersionForResources)

    filesMatching('application.properties') {
        filter { String line ->
            line.replace('@project.version@', buildVersionForResources)
        }
    }
}
~~~

**What each block does:**

- `id 'java'` creates `processResources`, `compileJava`, `test`, and core Java tasks.
- `id 'org.springframework.boot' version '4.1.2'` provides `bootJar` to package the executable Spring Boot JAR.
- `platform(SpringBootPlugin.BOM_COORDINATES)` imports the BOM aligned with the plugin version so starters need no explicit versions.
- `filteringCharset = 'UTF-8'` avoids platform-default charset assumptions when reading/writing text.
- `filesMatching('application.properties')` limits filtering to **a single text file**; images, binaries, and other files are untouched.
- `filter { String line -> line.replace(...) }` replaces only the literal `@project.version@`, never interpreting `${...}` as a template or evaluating Spring expressions.
- `inputs.property('resourceBuildVersion', ...)` declares the version as a task input so Gradle knows when to reprocess resources on version changes. For more complex custom filters, declare all inputs that affect output.
- `tasks.named('test') { useJUnitPlatform() }` enables JUnit Platform for tests.

**Run when the project has a Gradle Wrapper** compatible with Spring Boot 4.1.2 (Gradle 8.14+ or 9.x supported) and JDK 17 installed:

~~~bash
./gradlew clean processResources
./gradlew test
./gradlew bootJar
java -jar build/libs/filter-demo-1.0.0.jar
~~~

On Windows: use `gradlew.bat`. If no Wrapper exists, use a compatible installed Gradle version. Do not assume every project already includes `gradlew`.

The output file after `processResources` is:

~~~text
build/resources/main/application.properties
~~~

with contents:

~~~properties
spring.application.name=filter-demo
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

In `bootJar`, this file is packaged at `BOOT-INF/classes/application.properties`, while bytecode/controllers and runtime dependencies follow the Boot archive layout. The `FilteredResourceTest` unit test from section 6 also works in the Gradle project because it reads the resource via the classpath rather than hardcoding Maven's `target/classes` path.

**HTTP verification** matches the Maven example: start the JAR and run `curl -fsS http://localhost:8080/info`, receiving `build=1.0.0; message=Hello runtime` when no environment override is set.

### Why Use `filter { String line -> ... }` Instead of Ant `ReplaceTokens`?

Gradle also supports Ant's `org.apache.tools.ant.filters.ReplaceTokens` filter for `@name@` tokens, which works across many Gradle 8/9 projects. However, Gradle documentation notes that default availability of Ant classes in build scripts changes starting in Gradle 10. The example's string-replacement filter closure **requires no Ant dependency** and substitutes only the targeted token, making it a clear baseline.

If a system has **many tokens**, manage a clean token map or move resource filtering into a tested mechanism rather than scattering ad-hoc `replace` calls and forgetting corresponding task inputs.

## 10. How Do Maven, Gradle, and Spring Differ?

| Question | Maven | Gradle | Spring Boot runtime |
| --- | --- | --- | --- |
| Input files | `src/main/resources` | `src/main/resources` | Classpath and external config sources |
| Processing step | `resources:resources` in `process-resources` | `processResources` | Spring `Environment` / config binding |
| Lesson token | `@project.version@` | `@project.version@` with literal filter; `${buildVersion}` with `expand` | `${APP_MESSAGE:default}` |
| Value source | POM, filter files, Maven properties | `project.version`, explicit map | Env vars, system props, args, YAML/properties, etc. |
| Observed output | `target/classes/application.properties` | `build/resources/main/application.properties` | Resolved value while app runs |
| Modifies source file? | No: copies to `target` | No: copies to `build` | No: resolves in memory |
| Keeps Spring placeholders in resource? | Intact when default delimiters are off | Intact with literal filter; requires escaping with `expand` | Must resolve or use an intentional default |

**Practical rule:** **the build fills in artifact-bound values** such as version and build ID; **runtime fills in environment-bound values** such as hosts, ports, secrets, and service URLs. This allows the same immutable artifact to move across dev/test/staging/prod without rebuilding per environment.

## 11. Profiles and Multiple Application Configuration Files

Real projects often contain:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
├── application-prod.yml
├── static/logo.png
└── certificates/public.crt
~~~

Do not enable filtering globally just because one file contains `@project.version@`. List only the files that **contain build tokens** and restrict filtering to them; copy everything else verbatim.

In Maven, `includes` and `excludes` patterns must mirror each other. If `application-prod.yml` needs interpolation, add its pattern to the filtered resource entry and exclude it from the unfiltered copy entry. In Gradle, `filesMatching` accepts multiple Ant-style patterns to apply the same filter selectively to chosen config files.

**Do not mix the two mechanisms:** `application-prod.yml` is a profile config file **selected by Spring at runtime**, whereas Maven/Gradle filtering happens **before runtime**. All profile files included in the build's filter set get filtered during the build, **not just the profile active at runtime**, unless you deliberately structure your build differently.

When placing `@project.version@` in YAML, quote it:

~~~yaml
app:
  build-version: "@project.version@"
  endpoint: "${API_ENDPOINT:https://example.org}"
~~~

This avoids unsafe unquoted `@...@` YAML scalar syntax while preserving the Spring placeholder for runtime environment resolution. Only the actual post-copy output and running application prove both steps succeeded.

## 12. Common Errors, Causes, and Fixes

| Symptom | Possible cause | Verification and fix |
| --- | --- | --- |
| `@project.version@` stays literal in `target/classes` | `<filtering>true</filtering>` not enabled, file not included, or plugin misconfigured | Check effective POM, `<resources>`, and `process-resources` logs |
| `${APP_MESSAGE:...}` replaced at build time | Maven still has default `${...}` delimiter enabled, or Gradle runs `expand` on the file | Maven: `useDefaultDelimiters=false`; Gradle: use literal token replacement or escape `\${...}` for `expand` |
| Gradle `expand` fails with missing variable error | Groovy treated a Spring placeholder as a template expression | Escape `\${...}` before `expand` or switch to literal filter as shown |
| Maven project has starter parent, yet filtering does not happen | Parent overridden/replaced, different resource pattern, or plugin config overridden | Check effective POM and `target/classes` outputs |
| Spring runtime throws `Could not resolve placeholder` | Runtime variable missing, typoed name, no default, or loaded config file lacks the property | Check env vars, CLI args, property names, and loaded config files |
| Running JAR prints old value despite source changes | Running stale JAR, cache, wrong artifact, or external override file | Run an intentional `clean` build, inspect the file inside the JAR, and verify runtime config |
| `src/main/resources` looks right, `target/classes` differs | Either expected build interpolation or accidental token substitution | Diff source vs. output line by line; distinguish build vs. runtime tokens |
| Tests read a different application file | `src/test/resources/application.properties` shadows main resource | Inspect test classpath, rename test config, or verify which source is loaded |
| YAML parse fails on `@project.version@` | Value starting with `@` is unquoted | Quote as `"@project.version@"` and validate post-filtering YAML |
| Image/font/JAR corrupted after build | Text filter applied to binary resources | Separate filtered and unfiltered resources; filter text only |
| App runs, but version returns empty or wrong value | Token was never resolved or runtime config overrides it | Inspect processed file, packaged file, then runtime config precedence |
| `spring-boot:run` behaves differently from `java -jar` | `addResources` or run mode reads raw source resources instead of processed copy | Check runtime classpath of the run mode and compare with the packaged artifact |
| Build passes, but production uses wrong environment settings | Build baked environment-specific values instead of deferring to runtime | Bake only immutable metadata; inject URLs, secrets, and ports at runtime |
| Filtering corrupts Vietnamese characters | Source charset differs from resource filtering charset | Use UTF-8 consistently; Maven `encoding`, Gradle `filteringCharset` |
| Version changed, yet Gradle reuses cached output | Custom filter forgot to declare version as a task input | Add `inputs.property` as shown; check `processResources` task outcome |
| Build uses another profile, yet tokens look stale | Maven profile, filter file, or properties differ from expectation | Check `mvn help:effective-pom`, active profiles, and build properties |

**Diagnostic principle:** inspect in order: **source file → resource task output → resource inside JAR → Spring Environment value**. Finding the first stage that diverges from expectations pinpoints the bug far better than reading only the final log.

## 13. Automatable QA Checklist

### Post-Build Resource-Level Checks

1. After `mvn clean process-resources` or `./gradlew clean processResources`, `application.properties` exists in the expected output folder.
2. Required build tokens have been interpolated, e.g., `app.build-version=1.0.0`.
3. No literal `@project.version@` remains where substitution was required in that file.
4. Spring placeholders in the output file remain intact: `${APP_MESSAGE:Hello runtime}`, `${SERVER_PORT:8080}`.
5. All resources not needing filtering are copied byte-for-byte, especially binaries.
6. Source files tracked in Git were not modified by the build process.

### Executable JAR-Level Checks

1. `mvn clean verify` or `./gradlew clean build` executes required tasks and tests.
2. The expected executable Spring Boot JAR is created; `jar tf` shows `BOOT-INF/classes/application.properties`.
3. The file contents inside the JAR match the `processResources` output.
4. `java -jar` starts cleanly on the target JDK, and `/info` returns the build version and environment message.
5. Testing with a different `APP_MESSAGE` environment value changes the message **without rebuilding the artifact**.
6. Verify production configs are supplied at runtime and no secrets leak into JARs or logs.

Consider adding an automated test that reads `application.properties` from the classpath, like `FilteredResourceTest`. It catches regressions in delimiters or file includes whenever the POM or build script changes. In multi-environment CI, avoid hardcoding a single version in long-lived assertions; pass the expected build version or generate dedicated test metadata. The example test hardcodes `1.0.0` for straightforward verification of the lesson.

### Distinguishing Technical Build Success from Runtime Behavior

`mvn process-resources` succeeding only proves the resource processing goal finished; if a misspelled token remained literal, Maven may not fail the build. Therefore assert on **output contents**, not just exit codes. Likewise, Spring starting up does not prove a value came from build-time filtering: external property sources can override it; verify each layer.

## 14. Exercises and Answers

**Exercise 1.** A file contains `app.version=@project.version@` and `server.port=${PORT:8080}`. Maven enabled filtering with delimiter `@` without disabling default delimiters. What is the risk?

**Answer:** Maven can still interpret `${...}` as a build token, causing premature replacement when a matching property exists or differing across build environments. Add `<useDefaultDelimiters>false</useDefaultDelimiters>`.

**Exercise 2.** A POM imports `spring-boot-dependencies` without inheriting from the starter parent. Does it automatically inherit the parent's resource filtering?

**Answer:** No. Importing a BOM manages dependency versions, not plugin configurations; you must configure `<resources>` and Maven Resources Plugin for filtering.

**Exercise 3.** `mvn clean process-resources` produces `target/classes/application.properties` with `app.build-version=1.0.0` and `app.message=${APP_MESSAGE:Hello runtime}`. Did the build fail to finish interpolation?

**Answer:** That is the exact desired output. The build-time token was replaced; the Spring placeholder is preserved for runtime.

**Exercise 4.** Why should you avoid Gradle `expand(project.properties)` across all resources containing `${...}`?

**Answer:** Because `expand` uses Groovy templates with the same `${...}` syntax and may misinterpret Spring placeholders. Scope `expand` to specific files and keys, escape Spring placeholders, or use literal `@...@` filtering.

**Exercise 5.** When a YAML source contains unquoted `build-version: @project.version@` before processing, what problem occurs?

**Answer:** A token starting with `@` is invalid as an unquoted YAML scalar. Write `build-version: "@project.version@"`.

**Exercise 6.** Why inspect `target/classes` or `build/resources/main` instead of looking only at source files?

**Answer:** Builds do not modify source files; interpolation occurs during copying, so only the output reveals which tokens were substituted, preserved, or mangled.

**Exercise 7.** A unit test reading `/application.properties` sees the right version, yet an integration test sees a different runtime message. Is resource filtering broken?

**Answer:** Not necessarily. Spring runtime resolves values across property source precedence, environment variables, system properties, and command-line args; inspect values at each layer.

**Exercise 8.** Why keep JDBC URLs, secret tokens, service endpoints, and ports in runtime config instead of baking them from CI into the JAR?

**Answer:** To avoid embedding secrets and tying the artifact to one environment, allowing the same artifact to deploy across environments while reducing leak risk.

**Exercise 9.** Gradle changes `version='1.0.0'` to `1.0.1`; why did the example declare `inputs.property('resourceBuildVersion', ...)`?

**Answer:** So `processResources` recognizes that `version` affects output during incremental/cache checks and does not reuse stale outputs.

**Exercise 10.** In a Spring Boot app, does Maven replace `@Value("${app.build-version}")` inside `.java` files during `process-resources`?

**Answer:** No. Maven Resources Plugin processes declared resource files; `@Value` is resolved by Spring when instantiating beans at runtime.

## 15. Checklist for Real Projects

- [ ] Clearly list **build-bound values** to bake into the artifact (version, non-secret commit ID).
- [ ] Clearly list **runtime values** preserved for Spring `Environment` resolution.
- [ ] Use build delimiters distinct from Spring's `${...}`, preferring `@...@` in Maven.
- [ ] In Maven, set `<filtering>true</filtering>` on exact resources and `<useDefaultDelimiters>false</useDefaultDelimiters>` when using `@`.
- [ ] Never run text filtering over images, fonts, PDFs, archives, or binaries.
- [ ] In YAML, quote unprocessed `@...@` tokens.
- [ ] Without the starter parent, configure resources/plugins explicitly; importing the BOM is not enough.
- [ ] In Gradle, use exact token filtering or escape Spring placeholders when using `expand()`.
- [ ] Set `filteringCharset=UTF-8` or Maven `encoding=UTF-8` for text files.
- [ ] Verify which profile files are filtered or left unfiltered as intended.
- [ ] Check `src/test/resources` separately and avoid same-named test resources shadowing main results.
- [ ] Test post-processing resource outputs and file contents inside the executable JAR.
- [ ] Run a runtime smoke test confirming environment variables change behavior without rebuilding.
- [ ] Never bake secrets or environment-exclusive production settings into the artifact.
- [ ] Cross-check source, processed resources, JAR, and Spring `Environment` when debugging.

**Takeaway:** **Build-time tokens → replaced by Maven/Gradle when copying resources; Spring placeholders → kept intact for Spring to resolve at runtime.** Separating delimiters, scoping which files are interpolated, and verifying actual outputs are the three most important practices to avoid conflicts.

## 16. Official References

1. [Spring Boot — Automatically Expand Properties at Build Time (Maven and Gradle)](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html#howto.properties-and-configuration.expand-properties)
2. [Spring Boot Maven Plugin — Using the Plugin; without the Parent POM](https://docs.spring.io/spring-boot/maven-plugin/using.html)
3. [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
4. [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
5. [Maven Resources Plugin — Filtering Binary Files](https://maven.apache.org/plugins/maven-resources-plugin/examples/binaries-filtering.html)
6. [Gradle — Working With Files: Filtering File Content](https://docs.gradle.org/current/userguide/working_with_files.html)
7. [Gradle — CopySpec API: expand, filesMatching, filter](https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html)
8. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
9. [Spring Boot 4.1.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
