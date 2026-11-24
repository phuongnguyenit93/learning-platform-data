# Processing Resources with Maven Resources Plugin and Gradle processResources

## Objectives and Big Picture

A Spring Boot project does not consist only of `.java` files. It also needs `application.properties`, `application.yml`, messages, templates, static files, library configs, and sometimes sample data. During the build, **resources** must be moved from source directories to outputs and, when genuinely needed, **filtered/substituted** with build information.

After this lesson, you will be able to:

1. Distinguish **copying resources**, **resource filtering**, and **Spring Boot runtime property resolution**.
2. Trace the `process-resources` step via **Maven Resources Plugin**; know where `resources:resources` and `resources:testResources` run.
3. Understand the **Gradle `processResources`** task, how `filesMatching`/`expand` process files, and their relationship with `classes`/`jar`/`bootJar`.
4. Build a reproducible example: a `build-info.properties` appears on the classpath with the project version, while `application.properties` preserves Spring placeholders.
5. Inspect real outputs in `target/classes` or `build/resources/main`, how resources are packaged into an executable JAR, and common issues around encoding, binary files, duplicates, faulty filtering, and caching.

**Scope:** resource processing in the Maven/Gradle compilation and packaging pipeline of a Spring Boot application. This lesson does not replace guides on environment configuration management, dependencies, or system deployment.

## 1. Where Do Resources Live and Where Do They Go?

In a convention-based Java Spring Boot project:

```text
project/
├── pom.xml                       (Maven)
│   or build.gradle[.kts]         (Gradle)
├── src/
│   ├── main/
│   │   ├── java/com/example/demo/...
│   │   └── resources/
│   │       ├── application.properties
│   │       ├── build-info.properties
│   │       ├── messages_vi.properties
│   │       ├── static/logo.png
│   │       └── templates/home.html
│   └── test/
│       ├── java/com/example/demo/...
│       └── resources/test-data.json
```

`src/main/java` holds Java source code to **compile**; `src/main/resources` holds non-Java files to **copy or transform**. `src/test/resources` holds resources for testing; test resources should not be treated as content shipped with the release artifact.

Typical paths:

| Source | Maven (default) | Gradle Java plugin (default) |
| --- | --- | --- |
| `src/main/resources/application.properties` | `target/classes/application.properties` | `build/resources/main/application.properties` |
| `src/main/resources/static/logo.png` | `target/classes/static/logo.png` | `build/resources/main/static/logo.png` |
| `src/test/resources/test-data.json` | `target/test-classes/test-data.json` | `build/resources/test/test-data.json` |
| `src/main/java` | `target/classes` (compiled classes) | `build/classes/java/main` |
| `src/test/java` | `target/test-classes` (test classes) | `build/classes/java/test` |

These paths are standard Java project conventions and can be changed in `pom.xml`/`sourceSets` or plugins; inspect your actual configuration. Resources **do not get compiled** into bytecode: files like `.png` or `.properties` are normally copied as files.

In an executable Spring Boot JAR, main resources are packaged under `BOOT-INF/classes/` alongside Java classes; for example `BOOT-INF/classes/application.properties` or `BOOT-INF/classes/static/logo.png`. In an executable WAR, the corresponding location is `WEB-INF/classes/`. **`processResources`/`resources:resources` prepares the resources**, while the packaging task places them into the archive.

## 2. Three Easily Confused Concepts: Copy, Filter, and Runtime Resolution

Consider a source file:

```properties
# src/main/resources/application.properties
spring.application.name=demo
server.port=${APP_PORT:8080}
```

- **Copy:** preserves the bytes/content of the file and copies it to the output directory.
- **Filter (build-time substitution):** replaces tokens such as `@project.version@` (Maven) or `${appVersion}` (Gradle expand) with concrete values **before creating the JAR**.
- **Resolve at runtime:** Spring Boot reads `${APP_PORT:8080}` when the app starts, checks for the `APP_PORT` property, and falls back to `8080` if absent. This is handled by the Spring `Environment`, **not required to be replaced by Maven/Gradle**.

In the example above, the expected result when **not intentionally filtering `application.properties`** is that the post-build file still reads `server.port=${APP_PORT:8080}`. If you accidentally run Gradle `expand` across all resources, `${APP_PORT:8080}` may be interpreted by `SimpleTemplateEngine` as a template expression and fail or be substituted prematurely.

**Design rule:** values **fixed per artifact** such as the project version may be filtered at build time; values **dependent on the launch environment** such as ports, service URLs, and credentials should come from runtime configuration, environment variables, or a secrets manager. Never filter passwords/tokens into packaged files.

### Two Questions When Inspecting a File in a JAR

1. Where was this file **copied** from, and by which task?
2. If its contents differ from the source file, **what filtered/transformed it**, using which property and delimiter syntax?

Do not assume Spring Boot modified the file on disk just because a different value is returned at runtime: Spring can resolve placeholders dynamically while the file inside the JAR remains unchanged.

## 3. Maven Resources Plugin: Goals and Lifecycle

In Maven, `maven-resources-plugin` processes resources declared under `<build><resources>` or `<build><testResources>` and binds to lifecycle phases.

| Goal | Typical phase | Default source | Default output |
| --- | --- | --- | --- |
| `resources:resources` | `process-resources` | `src/main/resources` | `target/classes` |
| `resources:testResources` | `process-test-resources` | `src/test/resources` | `target/test-classes` |
| `resources:copy-resources` | Not bound by default; requires explicit configuration | Configured source | Configured destination directory |

The `resources:resources` and `resources:testResources` goals can be invoked standalone or run automatically when Maven passes through the corresponding phases of a Java-packaged project.

```bash
# Run the lifecycle up to copying main resources
./mvnw process-resources

# Invoke the plugin goal directly for main resources
./mvnw resources:resources

# Process test resources
./mvnw process-test-resources

# After copying: compile and package per lifecycle
./mvnw package
```

On Windows PowerShell:

```powershell
.\mvnw.cmd process-resources
.\mvnw.cmd resources:resources
.\mvnw.cmd process-test-resources
```

`process-resources` is a **lifecycle phase name**; `resources:resources` is a **plugin goal**. Both commands often achieve the same outcome in a standard Java POM, yet they **do not necessarily run the exact same set of actions**: a phase may run additional executions bound to it, whereas invoking a goal directly runs only that specific goal. When suspecting a plugin runs extra times, inspect `effective-pom` and lifecycle logs.

### Are Tokens Replaced by Default?

In Maven Resources Plugin generally, if `filtering` is not enabled for a resource, it is copied **without altering its contents**. For example, `hello.txt` containing `Hello ${name}` keeps its literal token if filtering is off.

However, a Spring Boot project **inheriting from `spring-boot-starter-parent`** includes sensible defaults for `application.properties`/`application.yml` and profile variants. That parent uses `@...@` delimiters to avoid conflicting with Spring's `${...}` syntax. **This configuration comes from the parent**, not from every Maven POM by default. A project that only imports the `spring-boot-dependencies` BOM without inheriting from the parent must not assume that filtering is enabled.

To check **what rules your current POM has**, run:

```bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

Search for `<resources>`, `<testResources>`, `<filtering>`, and `maven-resources-plugin` in the effective POM. A line with `@project.version@` in a source resource **will not be substituted automatically** if the file is not covered by a filtered resource entry or if the delimiter does not match.

## 4. Maven: Controlled Copying and Filtering Configuration

### 4.1 A Standalone Example Filtering Exactly One File

Suppose the project POM declares:

```xml
<groupId>com.example</groupId>
<artifactId>demo</artifactId>
<version>1.2.3</version>
```

This is only a **POM identity snippet**, not a complete POM. Create:

```properties
# src/main/resources/build-info.properties
app.version=@project.version@
```

A `pom.xml` **already inheriting the Spring Boot parent's `@...@` delimiter** can use the following snippet under `<build>` to filter **only that file**:

```xml
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
```

**How to read this configuration:**

1. The first `<resource>` entry processes only `build-info.properties` with `filtering=true`.
2. The second entry copies all **remaining** resources without filtering.
3. Splitting into two groups prevents `png`, `jpg`, font, or binary files from passing through text decoding and re-encoding.
4. `<includes>` and `<excludes>` use path patterns relative to the declared directory. `<filtering>false</filtering>` means copy only, without token substitution.
5. **Redefining the entire `<resources>` block** as shown can **override resource rules inherited from the Spring Boot parent**, including filtering for `application*.properties`/`application*.yml`. If an existing project relies on the parent's built-in filtering, preserve or adapt those rules when adding resources instead of copying the snippet blindly.

If you do not inherit from the parent and want to **use only `@...@` delimiters** rather than `${...}`, configure the plugin under `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <configuration>
        <delimiters>
            <delimiter>@</delimiter>
        </delimiters>
        <useDefaultDelimiters>false</useDefaultDelimiters>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
```

This is also a **plugin snippet**; a project without the parent should specify an appropriate plugin `<version>` or `<pluginManagement>` entry and place the block in the right section of the POM. `<useDefaultDelimiters>false</useDefaultDelimiters>` is critical: without it, Maven Resources Plugin's default delimiters can also process Spring's `${...}` expressions. There is no need to add this plugin block redundantly if the effective POM already configures it properly.

### 4.2 Predictable Output

With `project.version=1.2.3` and filtering restricted to `build-info.properties` as above:

```bash
./mvnw process-resources
```

Then `target/classes/build-info.properties` contains exactly:

```properties
app.version=1.2.3
```

In the same example, `src/main/resources/application.properties` contains:

```properties
spring.application.name=demo
server.port=${APP_PORT:8080}
```

After copying **without filtering `application.properties`** via the second resource group, `target/classes/application.properties` remains:

```properties
spring.application.name=demo
server.port=${APP_PORT:8080}
```

Thus the build records `1.2.3`, while Spring still determines the port at runtime. This demonstrates an intentional **build-time / runtime boundary**.

### 4.3 If You Want to Filter Spring Boot Parent Application Files

In a project inheriting from `spring-boot-starter-parent` with unmodified parent filtering defaults, you can write:

```properties
spring.application.name=demo
app.version=@project.version@
server.port=${APP_PORT:8080}
```

After `process-resources`, `app.version` is substituted from the Maven POM while `server.port=${APP_PORT:8080}` is preserved for Spring runtime. **Do not assume this behavior applies if the project overrides `<resources>`, delimiters, or omits the Boot parent.**

### 4.4 Property Sources and Filter Files

Maven filtering can draw from project properties, system properties, filter files, and command-line/user properties supported by Maven. For example, if the project declares:

```xml
<properties>
    <app.buildLabel>release</app.buildLabel>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

A resource with `app.label=@app.buildLabel@` becomes `app.label=release` when filtering runs. If using `<build><filters>` to load a `.properties` file of build values, carefully control that filter file; such files can hold sensitive values, and secrets must never be packaged into artifacts.

An often-overlooked detail: `filtering=true` does not mean **every arbitrary placeholder** gets replaced properly. The property name must exist in the sources read by the plugin, delimiters must match, and escaping/encoding must be valid. If a token remains literal, check **value sources, delimiters, `<resources>`, and the effective POM** first.

## 5. Gradle `processResources`: The Java Plugin's Copy Task

When applying Gradle's `java` or `java-library` plugin, the `main` source set gets `processResources` and the `test` source set gets `processTestResources`. These are file-copy/transform tasks provided by the Gradle Java plugin.

```text
src/main/java                --> compileJava ------> build/classes/java/main
src/main/resources           --> processResources -> build/resources/main
                                        \                 /
                                         +-- classes ---+
                                               |
                                        jar / bootJar / runtime classpath

src/test/resources           --> processTestResources -> build/resources/test
```

The diagram shows the conceptual relationship. The exact task graph may contain additional tasks added by plugins, source sets, and project configuration.

Commands in a Gradle project with the Java plugin:

```bash
# Process main resources only
./gradlew processResources

# Process test resources
./gradlew processTestResources

# Preview the task plan without executing
./gradlew classes --dry-run

# Run compilation + main resource copying
./gradlew classes
```

Windows PowerShell:

```powershell
.\gradlew.bat processResources
.\gradlew.bat processTestResources
.\gradlew.bat classes --dry-run
```

**By default, `processResources` only copies** and does not replace all `${...}` variables. Do not equate the presence of the Spring Boot Gradle plugin `org.springframework.boot` with automatic Gradle resource filtering. The `processResources` task comes from the **Gradle Java plugin**, whereas the Spring Boot plugin uses the source set outputs to run and package the app when applied alongside the Java plugin.

### 5.1 Groovy DSL Configuration: Expanding Only One File

Example in `build.gradle`, assuming a project with the Java plugin (adding the Spring Boot plugin does not alter this principle):

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

def resourceVersion = project.version.toString()

tasks.named('processResources') {
    inputs.property('appVersion', resourceVersion)

    filesMatching('build-info.properties') {
        expand(appVersion: resourceVersion)
    }
}
```

This is a **complete Gradle Groovy DSL configuration sufficient to run `processResources`** in a Gradle project with a Wrapper; if you need a Spring Boot executable JAR, apply the Spring Boot plugin and application dependencies in the rest of the build.

The source file uses **Gradle SimpleTemplateEngine syntax**:

```properties
# src/main/resources/build-info.properties
app.version=${appVersion}
```

Run:

```bash
./gradlew processResources
```

`build/resources/main/build-info.properties` should contain:

```properties
app.version=1.2.3
```

Explanation:

- `filesMatching('build-info.properties')` selects only matching files for transformation. All other files are copied verbatim by the task.
- `expand(appVersion: resourceVersion)` passes a map `appVersion` → `1.2.3` to the template. During copying, `${appVersion}` is replaced.
- `inputs.property('appVersion', resourceVersion)` registers the value used by the transformation as a task input so Gradle detects changes for up-to-date checks and caching. In real builds, other task inputs are tracked by Gradle's standard mechanisms.
- Gradle's `version` must be defined, otherwise it may default to `unspecified`.
- This pattern avoids calling `expand(project.properties)` on **all resources**, which risks interpreting Spring placeholders and other template content.

### 5.2 Equivalent Kotlin DSL

If the build file is `build.gradle.kts`, use Kotlin syntax:

```kotlin
plugins {
    java
}

group = "com.example"
version = "1.2.3"

val resourceVersion = project.version.toString()

tasks.processResources {
    inputs.property("appVersion", resourceVersion)

    filesMatching("build-info.properties") {
        expand(mapOf("appVersion" to resourceVersion))
    }
}
```

This is a complete Kotlin DSL configuration for resource processing in a Java Gradle project. Do not copy Groovy's `expand(appVersion: resourceVersion)` into Kotlin DSL because map argument syntax differs. When applying the `war` plugin, the Java plugin is also applied and `processResources` still exists.

### 5.3 What Happens to Other Files?

Suppose resources contain:

```text
src/main/resources/
├── build-info.properties
├── application.properties
├── static/logo.png
└── templates/home.html
```

With `filesMatching('build-info.properties')`, only that file is filtered. `application.properties`, `static/logo.png`, and `templates/home.html` are copied **unchanged** by the task. Thus `server.port=${APP_PORT:8080}` remains intact for Spring to read later and the PNG image does not pass through a template engine.

If you want to **omit** a file from the output entirely, `processResources` supports `exclude('path/relative/to/resources')`; Maven has `<excludes>` for the same intent. Excluding removes a file **from the output completely**, which is very different from simply not filtering it.

## 6. Special Note: Spring Boot Placeholders vs. Gradle

### Same Syntax, Different Processing Time

Spring runtime:

```properties
server.port=${APP_PORT:8080}
```

Gradle `expand` also uses `${...}` syntax and evaluates template expressions via Groovy's `SimpleTemplateEngine`. If you write:

```groovy
tasks.named('processResources') {
    expand(project.properties)
}
```

then **every resource file goes through transformation**, including `application.properties` if present. In it, `${APP_PORT:8080}` may be parsed as invalid template syntax; if a variable name matches a property, it may be substituted **at build time** instead of being resolved by Spring at runtime.

**Preferred approach for build versions:** filter only `build-info.properties` as shown in section 5. When metadata does not have to live inside `application.properties`, isolating a dedicated resource is easy to verify.

If you intentionally **filter `application.properties` itself** with Gradle, Spring Boot documentation explains that Spring placeholders must be escaped. Example source file:

```properties
app.version=${appVersion}
server.port=\${APP_PORT:8080}
```

When `processResources` applies `expand` **only to that file**, `app.version` is replaced with the build version while the backslash escape in the source leaves the Spring token intact. Escaping and backslashes in YAML/Properties/Groovy should always be verified directly on the **processed output file**, because template engines and Java properties/YAML have different escaping rules.

A less error-prone design is to keep environment config untouched, place build metadata in a separate resource, and filter only that file. **Do not remove escape characters by guessing** without inspecting the actual output file.

### With Maven Spring Boot Parent, Use `@...@`

The Spring Boot Maven parent switches the resource filtering delimiter for application files to `@...@` so you can write both:

```properties
app.version=@project.version@
server.port=${APP_PORT:8080}
```

With the right parent configuration, Maven values are substituted while Spring placeholders are not consumed by Maven. If you **do not inherit from the parent** or enabled Maven filtering manually with `${...}`, reconfigure the delimiters—for example `<useDefaultDelimiters>false</useDefaultDelimiters>` and `<delimiter>@</delimiter>`—or isolate filtered values into a separate resource file.

### Do Not Confuse Build Expansion with Spring PropertyPlaceholder

Similar syntax can appear at three stages:

| Stage | Expression | Handled by |
| --- | --- | --- |
| Inside POM/build script | `project.version`/`version` | Maven or Gradle during build configuration |
| Resource file at build time | `@project.version@` or `${appVersion}` | Maven Resources Plugin or Gradle `expand` **if enabled** |
| Running application | `${APP_PORT:8080}` | Spring `Environment` when reading runtime config |

If you run `java -jar` twice with two different environment variables, a runtime placeholder can produce two different values **without rebuilding**. By contrast, a version filtered into a file is baked into the artifact and does not change just because runtime environment variables change.

## 7. Resource Filtering in Spring Boot Packaging

### 7.1 Maven Pipeline

For a Spring Boot POM using `jar` packaging:

```text
src/main/resources/
       |
       v
resources:resources          (process-resources)
       |
       v
target/classes/              (+ classes from compiler:compile)
       |
       v
jar:jar / spring-boot:repackage per configured lifecycle
       |
       v
target/<artifact>-<version>.jar
       |
       v
BOOT-INF/classes/...          (executable Spring Boot JAR)
```

`spring-boot-maven-plugin` is not `maven-resources-plugin`. The Resources plugin copies and filters resources; the Boot plugin builds/repackages the executable archive per your configuration. Custom POMs can alter plugin execution order, so check logs and the effective POM when customized.

### 7.2 Gradle Pipeline

```text
src/main/resources/ --> processResources --> build/resources/main/
src/main/java/      --> compileJava     --> build/classes/java/main/
                                 \          /
                                    classes
                                      |
                                      v
                            jar / bootJar / bootWar
                                      |
                                      v
                              build/libs/...
```

`bootJar` and `bootWar` come from the Spring Boot Gradle plugin when applied alongside the Java/War plugin, whereas `processResources` comes from the Java plugin. Processed files must exist in the source set output before packaging. The `jar` task generally places resources at the archive root; `bootJar` places main classes and resources under `BOOT-INF/classes`. Make sure you inspect the right archive.

### 7.3 Verifying Inside the Archive

After building, list entries with `jar tf` (a JDK tool requiring no Java code):

```bash
# Maven, when pom.xml configures a Spring Boot executable JAR
./mvnw package
jar tf target/demo-1.2.3.jar

# Gradle, when Spring Boot + java plugins are applied
./gradlew bootJar
jar tf build/libs/demo-1.2.3.jar
```

The archive name `demo-1.2.3.jar` is just an **example**; it depends on `artifactId`, `rootProject.name`, `version`, and `archiveBaseName`. In `jar tf` output, look for `BOOT-INF/classes/build-info.properties` and `BOOT-INF/classes/application.properties`. `jar tf` lists **entry names**, not filtered content; to read file contents, inspect `target/classes`/`build/resources/main` or extract/inspect the exact archive.

Do not conclude a resource is missing just because you looked in `build/classes/java/main`: in Gradle, resources default to `build/resources/main`, and both directories are combined in the classpath/source set output.

## 8. Verifying with Java 17+: Resource Is Actually on the Classpath

A standalone example showing how Java reads a resource after Maven/Gradle processing. Create `src/main/java/com/example/demo/ResourceProbe.java`:

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ResourceProbe {

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input = ResourceProbe.class.getClassLoader()
                .getResourceAsStream("build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing build-info.properties on classpath");
            }
            properties.load(input);
        }

        System.out.println("app.version=" + properties.getProperty("app.version"));
    }
}
```

This is a **complete Java class runnable on JDK 17+** inside a Java project. Spring Boot is not needed to read a file using `ClassLoader` and `java.util.Properties`. It resolves `build-info.properties` **on the classpath**, independent of the process working directory.

If `build-info.properties` was processed into `app.version=1.2.3` as in the two examples above, stdout from **`ResourceProbe` itself** is:

```text
app.version=1.2.3
```

Maven (project with a valid Java POM and Wrapper):

```bash
./mvnw compile
java -cp target/classes com.example.demo.ResourceProbe
```

Gradle (project with the Java plugin and Wrapper; macOS/Linux uses `:` as classpath separator):

```bash
./gradlew classes
java -cp build/classes/java/main:build/resources/main com.example.demo.ResourceProbe
```

Windows PowerShell:

```powershell
.\mvnw.cmd compile
java -cp target\classes com.example.demo.ResourceProbe

.\gradlew.bat classes
java -cp "build\classes\java\main;build\resources\main" com.example.demo.ResourceProbe
```

Run **only the command set matching your project's build tool**. If the resource was dropped by include/exclude rules or a wrong path, Java throws `IllegalStateException` with `Missing build-info.properties on classpath`. If the resource was not filtered, stdout prints the literal token such as `@project.version@` or `${appVersion}` — proving a **build-processing** issue, not a `ClassLoader` issue.

**Distinction:** the example output applies strictly to `version=1.2.3`, the described source file, filter rules, and classpath. Do not assume full Maven/Gradle/Spring Boot stdout logs are fixed across plugin versions and environments.

## 9. Include/Exclude, Encoding, Binary Files, and Duplicate Paths

### 9.1 Copy Only What Is Needed

Maven: each `<resource>` supports `<directory>`, `<includes>`, `<excludes>`, and `<filtering>`; `<targetPath>` can remap the relative destination path in the output.

Gradle: `processResources` is a `Copy`-style task supporting `include`/`exclude` and `filesMatching`. Groovy DSL example:

```groovy
tasks.named('processResources') {
    exclude('private-notes/**')

    filesMatching('build-info.properties') {
        expand(appVersion: project.version.toString())
    }
}
```

Here `private-notes/**` is **excluded from the output**, while `build-info.properties` is transformed. If a file contains sensitive runtime values, the proper approach is **not to store secrets in the repo/artifact at all**; use environment variables or a secret store. `exclude` only controls build outputs and does not scrub Git history.

### 9.2 Why Never Filter Images or Binaries?

Maven Resources Plugin filtering and Gradle `expand` operate as text processors. Trying to read a PNG image, PDF, font, or JAR as text can corrupt bytes. Maven Resources Plugin skips some default binary extensions and supports `nonFilteredFileExtensions`; exact defaults depend on plugin version. Rather than relying solely on extension lists, **enable filtering only on text files that actually need variable substitution**.

When filtering specific text files inside a directory holding mixed file types, use **two Maven resource groups** as in section 4 or **Gradle `filesMatching`** as in section 5 so all other files are copied untouched.

### 9.3 Encoding of Filtered Files

If a template contains Vietnamese text, a mismatched encoding can corrupt accented characters during the build. Maven Resources Plugin defaults `encoding` from `project.build.sourceEncoding` and supports `propertiesEncoding` for `.properties` files in supported versions. Example:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Match the encoding to both the file's real bytes and the runtime parser. Traditional Java `Properties.load(InputStream)` decodes per ISO-8859-1/escape rules; if you need UTF-8 for Vietnamese text, use `Properties.load(Reader)` with `InputStreamReader(StandardCharsets.UTF_8)` or Spring Boot's supported property loading. `ResourceProbe` reads only the ASCII value `1.2.3`, so it encounters no diacritic encoding issues.

Gradle `expand` is also a text operation; encoding, backslash escaping, and template engine semantics can alter contents. In supported Gradle versions, `expand(map) { escapeBackslash = true }` can prevent unwanted escape interpretation; only use it after checking your Gradle API/version and inspecting the output file.

### 9.4 Duplicate Destination Paths

Suppose you add both `src/main/resources` and another resource directory containing `application.properties` to the same output. Two files target the same destination. Maven is affected by resource entry order and overwrite/change-detection rules; Gradle uses `duplicatesStrategy` and may fail or overwrite depending on configuration and version.

When a file inside a JAR has **unexpected contents**, inspect every declared resource root, relative target path, tasks/executions touching it, and execution order before blaming a plugin for randomly modifying files.

Never put a duplicate copy of a resource inside `src/main/java` just to "make sure it gets packaged": that puts non-Java sources in the wrong place and risks classpath collisions.

## 10. How Do Test Resources Differ from Main Resources?

Maven:

- `src/main/resources` → `resources:resources` → `target/classes`.
- `src/test/resources` → `resources:testResources` → `target/test-classes`.
- With Spring Boot Maven parent, application resource filtering rules target **production resources**, not necessarily filtering test resources identically. If tests need filtering, configure `<testResources>` intentionally.

Gradle:

- `src/main/resources` → `processResources` → `build/resources/main`.
- `src/test/resources` → `processTestResources` → `build/resources/test`.
- `tasks.named('processResources')` customizes **main resources only**. To substitute tokens in test resources, configure `processTestResources` explicitly; do not assume both tasks share rules.
- The test classpath typically includes both test and main resources; if names collide, classpath ordering can affect which file is loaded depending on the runner/test task. Do not rely on vague guesses; inspect `ClassLoader.getResource(...)` to check the actual URL when needed.

For instance, `src/test/resources/application-test.properties` holds test configuration and should not be packaged into the executable JAR. Seeing a file in `target/test-classes` or `build/resources/test` while it is absent from the release JAR represents **intentional separation**, not a bug by default.

## 11. Incremental Builds, UP-TO-DATE, and Stale Resources

When source files and transformation settings have not changed, Gradle may report `processResources UP-TO-DATE` or `FROM-CACHE`. This is normal: the build system tracks the task's declared inputs and outputs. If a value outside source files affects expansion, register it with `inputs.property(...)` (like `appVersion` in our example) so Gradle knows when to rerun.

Maven Resources Plugin likewise tracks when to copy or overwrite resources. Exact behavior depends on plugin version and configuration; do not assume "running Maven rewrites every file unconditionally".

**How to investigate when stale contents persist:**

1. Verify the exact source file, resource directory, and output path.
2. Print/check the input version value at build time.
3. Verify the build runs on the intended module and Wrapper.
4. Check whether Gradle skipped the task via `UP-TO-DATE`/`FROM-CACHE` or Maven skipped copying.
5. When verification is needed, run a clean build in a **safe environment or practice branch**, then compare outputs; avoid deleting shared workspace files indiscriminately.

`./mvnw clean process-resources` or `./gradlew clean processResources` are handy in test projects, though `clean` deletes build output directories; only use it where wiping outputs is safe. If `clean` fixes a bad output, investigate the root cause in inputs, tasks, caching, or paths rather than treating `clean` as a permanent "solution".

## 12. Quick Comparison: Maven vs. Gradle

| Criterion | Maven Resources Plugin | Gradle processResources |
| --- | --- | --- |
| Task/goal name | Goal `resources:resources` | Task `processResources` |
| Pipeline position | `process-resources` phase | Task on the Java `main` source set |
| Default main source | `src/main/resources` | `src/main/resources` |
| Default main output | `target/classes` | `build/resources/main` |
| Default test output | `target/test-classes` | `build/resources/test` |
| Source configuration | POM `<resources>`/`<resource>` | `sourceSets` and Copy task |
| Enabling filtering | `<filtering>true</filtering>` on a resource group | `expand` or another filter in the task |
| Selecting files to filter | `includes/excludes` and resource groups | `filesMatching(...)` |
| Token syntax | Typically `${name}` or `@name@` per delimiters | `${name}`/`$name` per `SimpleTemplateEngine` |
| Avoiding Spring `${...}` clash | Spring Boot parent uses `@...@` and delimiters are configurable | Filter only needed files or escape Spring placeholders |
| Test resources | `resources:testResources` | `processTestResources` |
| Spring Boot packaging | Boot plugin repackages after resources are processed | Boot task consumes processed source set outputs |
| Verification | Inspect `target/classes` and JAR contents | Inspect `build/resources/main` and JAR contents |

This table reflects standard Java project behavior and **does not replace reading your actual build config**. In particular, the Spring Boot plugin and other plugins can customize resource sets, task graphs, delimiters, and archive names.

## 13. Common Error Diagnostics

| Symptom | Possible cause | Check / fix |
| --- | --- | --- |
| File in `src/main/resources` is missing from output | Wrong exclude/include, altered `sourceSets`, task didn't run, or built another module | Inspect POM effective resources or Gradle `sourceSets`; run the resource task and check the right folder |
| `@project.version@` remains literal in Maven output | Filtering not enabled on file, missing `@` delimiter, or POM lacks property/parent | Check `<filtering>`, `<delimiters>`, `<useDefaultDelimiters>`, and effective POM |
| `${appVersion}` remains literal in Gradle output | `expand` not applied to file, wrong `filesMatching`, or map missing key | Inspect `processResources` task and `build/resources/main` file |
| Maven overwrites `${APP_PORT:8080}` | Filtering uses `${...}` delimiter on Spring config | Switch to `@...@` with `useDefaultDelimiters=false` or exclude file from filtering |
| Gradle `expand` fails on Spring placeholders | `SimpleTemplateEngine` tries to evaluate Spring's `${...}` | Filter only `build-info`; if filtering application config, escape Spring tokens and verify output |
| Images/binaries corrupted after build | Text filter applied to whole directory | Isolate filtered files or use `filesMatching`; never transform binaries |
| Vietnamese characters garbled | Inconsistent charset across source, filter, and runtime parser | Standardize on UTF-8; check `propertiesEncoding` and Java property loading API |
| `processResources` UP-TO-DATE even after expected version change | External expansion input not declared or checking wrong module/output | Add `inputs.property`, inspect Gradle logs and source files |
| Resource appears in `build/resources/main` but not `build/classes/java/main` | Those are two separate Gradle output directories | Check `build/resources/main` or the JAR instead of looking in the wrong folder |
| File exists in test, missing from release JAR | Test resources do not belong in main artifact | Move runtime files to `src/main/resources` if needed; don't copy test data carelessly |
| Multiple `application.properties` with odd contents | Multiple resource roots/duplicate paths or overlapping filters | Check includes/excludes, final outputs, task graph, and `duplicatesStrategy` |
| Running from IDE sees different config than JAR | IDE reads resources directly/copies separately, stale build output, or different profile | Run via Wrapper, compare source vs. artifact files, check IDE classpath |
| Secrets end up in the JAR | Build-time filtering injected sensitive data into resources | Remove secrets from artifact/source and use runtime config/secret management |

### Example of Evidence-Based Troubleshooting Instead of Guessing

If the application prints `app.version=@project.version@` instead of `1.2.3`, a logical investigation order is:

1. Open `src/main/resources/build-info.properties` to verify the source token.
2. Check the effective POM or Gradle task to verify the file is actually filtered.
3. Inspect `target/classes/build-info.properties` / `build/resources/main/build-info.properties`. **If the output still contains the literal token, the fault is in build-time filtering.**
4. If the output is right but the app prints the wrong value, inspect the classpath or running JAR; it may be running a stale artifact, a different profile, or a same-named resource elsewhere.
5. Verify using `ResourceProbe` from section 8 and the actual release artifact. Change one variable at a time to isolate the cause cleanly.

The same approach applies to YAML, templates, and message bundles: always treat "source", "post-process output", and "runtime-loaded resource" as three separate pieces of evidence.

## 14. Self-Verifiable Practice Exercises

### Part A – Maven

Use a Spring Boot Maven (or Java Maven) project, set version `1.2.3` in the POM, and create `src/main/resources/build-info.properties` containing `app.version=@project.version@`. If using the Boot parent, inspect its existing resource filtering rules before adding the two-group `<resources>` config from section 4.

1. Run `./mvnw process-resources` and open `target/classes/build-info.properties`.
2. Explain why the file contains `app.version=1.2.3`; identify the source property and delimiter.
3. Add `application.properties` with `server.port=${APP_PORT:8080}` and verify the Spring token stays intact **under the example's non-filtered application config setup**.
4. Create `src/test/resources/test-data.json`, run `./mvnw process-test-resources`, and explain why the file goes to `target/test-classes`.
5. Use `ResourceProbe` to read the value from the classpath and verify exact stdout.
6. Answer: what is the difference between `process-resources` (phase) and `resources:resources` (goal)? What changes when inheriting the Boot parent?

### Part B – Gradle

Use a Gradle project with the Java plugin, set `version = '1.2.3'`, and configure `processResources` with `filesMatching` + `expand` as in section 5.

1. Create `build-info.properties` containing `app.version=${appVersion}`.
2. Run `./gradlew processResources` and inspect `build/resources/main/build-info.properties`.
3. Keep `application.properties` with `server.port=${APP_PORT:8080}` and verify it is not filtered.
4. Add a small image under `src/main/resources/static` and verify it is copied byte-for-byte without going through the template engine.
5. Run `./gradlew classes` and invoke `ResourceProbe` with **both** `build/classes/java/main` and `build/resources/main` on the classpath.
6. Change the version to `1.2.4` on a test branch and rerun `processResources`, verifying the output updates to `1.2.4` thanks to the declared input property.
7. If using the Spring Boot Gradle plugin, run `bootJar` and locate `BOOT-INF/classes/build-info.properties` inside the executable archive.

### Part C – Comparison and Explanation

Answer using this structure:

- "**Source:** this file lives at ..., containing ...".
- "**Processor:** Maven goal ... / Gradle task ...".
- "**Rule:** filters file ... using delimiter ... with value ...".
- "**Build output:** I read the file directly at ... and observed ...".
- "**Runtime:** Java/Spring loads the resource from the classpath or Spring Environment resolves remaining placeholders ...".
- "**Packaging:** the file sits at ... inside the executable JAR/WAR".

**Completion criteria:** demonstrate at least one filtered file and one unfiltered file in **each** tool; identify exact output paths; prove `ResourceProbe` reads from the classpath; explain the difference between build-time tokens and runtime placeholders; and leave binary files uncorrupted.

## Official Documentation for Reference

- Apache Maven Resources Plugin – Introduction/Goals: https://maven.apache.org/plugins/maven-resources-plugin/
- Maven Resources Plugin – Usage (`resources`, `testResources`): https://maven.apache.org/plugins/maven-resources-plugin/usage.html
- Apache Maven – Guide to Filtering Resources: https://maven.apache.org/guides/mini/guide-filtering-resources.html
- Maven Resources Plugin – Include/Exclude: https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html
- Spring Boot – Maven Plugin, using the Spring Boot parent and `@..@` filtering: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot – Properties and Configuration, automatically expanding properties at build time: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Gradle – Building Java/JVM Projects, managing resources: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle – ProcessResources DSL: https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html

**Takeaway:** the resource pipeline has three layers to verify separately: **source file → processed file in build output → file/value actually used by the application**. Maven Resources Plugin and Gradle `processResources` handle the second layer; Spring Boot handles runtime configuration and packaging based on those outputs.
