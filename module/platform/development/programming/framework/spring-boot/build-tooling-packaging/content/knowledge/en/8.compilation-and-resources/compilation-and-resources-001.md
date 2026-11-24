# Configuring the Java Compiler, UTF-8 Encoding, and the -parameters Option in Spring Boot

## 1. Three Decisions When Compiling Java Source

In a Spring Boot project, Java files in `src/main/java` and `src/test/java` must be turned into `.class` bytecode by the **Java compiler (`javac`)** before the application runs. The build configuration determines which JDK compiles the code, how source characters are decoded, and which metadata is written into `.class` files. The three distinct concerns are:

1. **Java version/compile target:** which JDK is used and which Java language features/APIs are allowed (for example Java 17). Maven uses the Maven Compiler Plugin; Gradle uses the `JavaCompile` task and Java toolchains.
2. **UTF-8 source encoding:** which charset the compiler uses to decode the bytes of `.java` files into characters. This must match how the editor saves the files.
3. **The `-parameters` option:** instructs `javac` to write the **actual parameter names** of methods/constructors into the class file so libraries using Java reflection can read those names at runtime.

These three settings do not substitute for one another: enabling UTF-8 does not make parameter names appear in reflection; enabling `-parameters` does not determine the JDK or charset; and selecting Java 17 alone does not guarantee that all build tools or machines behave identically.

| Configuration | Core flag/property | Effect | If missing or incorrect |
|---|---|---|---|
| Java compiler / target | `--release 17`, JDK 17 toolchain, Maven `<release>` | Restricts syntax, bytecode, and APIs to the selected Java release | Code may compile against APIs missing on the target runtime, or an older compiler may fail |
| UTF-8 source | `javac -encoding UTF-8`; Maven `project.build.sourceEncoding` / `<encoding>`; Gradle `options.encoding` | Correctly reads Java files containing Vietnamese diacritics and Unicode characters | Unmappable character errors or corrupted text |
| Runtime parameter names | `javac -parameters`; Maven `<parameters>true</parameters>`; Gradle compiler arg `-parameters` | Records method/constructor parameter names for reflection and Spring to read | Reflection typically returns `arg0`, `arg1`; some name-based binding/injection fails |

**Choose the configuration approach based on the real project:** Spring Boot may already provide sensible defaults via the Maven parent or Gradle plugin. Inspect the **existing** setup before adding redundant compiler flags.

## 2. Flow from Source to Class File

```text
IDE/Git saves .java as a byte sequence (UTF-8 recommended)
                       |
                       v
                 Java compiler
   Selects compiler JDK + --release + -encoding
                       |
                       +-- -parameters ?
                       |      Yes -> MethodParameters attribute
                       |      No  -> parameter names may be absent
                       v
               .class (bytecode)
                       |
                       v
       Spring Boot startup / Java reflection
       Java 17+ runtime or matching runtime
                       |
        Reads methods, parameters, and annotations
```

For example, consider `UserController.java` with a method `hello(String username)`:

- `-encoding UTF-8` affects how the compiler reads Unicode characters in the file.
- `--release 17` (when using a `javac` that supports this release) restricts APIs and language features to Java 17, and generates class files for Java 17.
- `-parameters` makes the name `username` retrievable via `java.lang.reflect.Parameter.getName()` with `isNamePresent() == true`.

Note that `-parameters` applies to **method and constructor parameter names** in `.class` files; it is not an option for local variable names, Java packages, JSON fields, or Spring bean names.

## 3. Choosing the JDK, source/target, and --release for Java 17+

Two aspects are frequently confused:

- **The running compiler:** which JDK version's `javac` process runs, such as JDK 17 or JDK 21.
- **The target release:** the bytecode, syntax, and APIs that the artifact is permitted to use.

Since Java 9, `javac --release 17` is the standard way to constrain both the language and the Java platform APIs to Java 17. The compiler must be new enough to understand the requested release. `--release` differs from simply setting `-source 17 -target 17`: source/target set the language and bytecode level, but **do not guarantee blocking newer JDK APIs** when compiling with a newer JDK.

For example, using JDK 21 to produce an artifact compatible with Java 17 in language, bytecode, and standard APIs:

```bash
javac --release 17 -encoding UTF-8 -parameters Example.java
```

This is an illustrative command; `Example.java` must exist and contain valid code. Although `--release 17` helps preserve standard Java API compatibility, it does **not** automatically guarantee that every external dependency of the application supports Java 17; you must check dependency versions and the actual runtime.

**Gradle Java toolchains** let you select the exact compiler JDK:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

A toolchain can choose JDK 17 for compiling/testing even if the Gradle daemon runs on a different JDK, within the compatibility limits of the Gradle/plugin version. Do not equate `java.toolchain` with `options.release`: the toolchain selects the JDK tool, whereas `release` sets the API/language/bytecode target for the `JavaCompile` task.

**Maven:** `maven.compiler.release` or the `maven-compiler-plugin` configuration controls the target release. If you want Maven to actually select a specific **compiler JDK**, you must control `JAVA_HOME`/the Maven runtime or use the Maven Toolchains Plugin according to project requirements.

## 4. Why Is UTF-8 Encoding So Important?

UTF-8 is the portable convention for Java source code, configuration, documentation, and data containing Vietnamese text. For example:

```java
public class VietnameseText {
    public static void main(String[] args) {
        System.out.println("Xin chào, thế giới!");
    }
}
```

If `VietnameseText.java` is saved **as UTF-8**, compile explicitly with:

```bash
javac -encoding UTF-8 VietnameseText.java
java VietnameseText
```

Stdout from the program, when the terminal renders Unicode properly:

```text
Xin chào, thế giới!
```

**Two things must both be true:** the editor/Git saves valid UTF-8 bytes, and the compiler reads those bytes as UTF-8. Adding `-encoding UTF-8` **does not automatically convert** a source file originally saved in a legacy encoding. On JDK 17, do not rely on each machine's default charset; starting in JDK 18, UTF-8 became the default charset for standard Java APIs in many contexts, yet declaring the encoding explicitly in the build still helps multi-environment projects and prevents misunderstandings.

**Distinguish the types of encoding:**

| Concept | Example | Managed by javac `-encoding UTF-8`? |
|---|---|---|
| Encoding of `.java` file contents | `src/main/java/.../VietnameseText.java` | **Yes**, when `javac` reads the source |
| Encoding of filtered resources | `application.properties`, templates | **Not directly**; managed by Maven Resources Plugin/Gradle copy filtering |
| Charset of HTTP/JSON data | Application requests/responses | **No**; controlled by HTTP media types and library configuration |
| JDBC/database charset | Database connections and columns | **No**; depends on driver, DB, and schema |
| Stdout/terminal encoding | Windows/Linux console, log viewer | **No**; terminal and JVM output are also involved |
| Parameter names in `.class` | Reflection reading `username` | **No**; related to `-parameters` |

**Note on Spring Boot resources:** in Maven, `project.build.sourceEncoding` is commonly used as the default by the compiler/resources plugins; in Gradle, `options.encoding` applies only to `JavaCompile`. When **filtering resource contents** (for example using `expand` or `filter`), check the charset of the filtering task separately. When simply copying binary/resource bytes as-is, do not force unnecessary "decode and re-encode" steps. In particular, avoid mistakenly filtering binary files such as images or PDFs.

## 5. What Does -parameters Do in a Class File?

The Java compiler option `-parameters` requests that formal parameter name metadata for methods/constructors be written into the bytecode's **`MethodParameters` attribute**. The reflection API provides:

- `Executable.getParameters()`: the list of parameters on a method/constructor.
- `Parameter.getName()`: the parameter name known to reflection.
- `Parameter.isNamePresent()`: `true` when the class file contains the real name via `MethodParameters`.
- `Parameter.getType()` / `getParameterizedType()`: parameter type information, which is separate from the name.

If compiled **without** `-parameters`, parameter names are normally not stored; reflection synthesizes names like `arg0`, `arg1` and returns `isNamePresent() == false`. Parameter types, parameter counts, and annotations can still be present; do not assume that omitting `-parameters` removes the method signature.

**Do not confuse this with `-g` or debug symbols.** `javac -g` can emit `LocalVariableTable` along with information for debuggers. That is not the parameter name metadata that Java reflection uses for `Parameter.isNamePresent()`. Modern Spring Framework versions, especially Spring 6.1+, require `-parameters` in cases where names must be inferred via reflection; having debug local-variable metadata does not replace this flag.

## 6. Self-Contained Java 17 Example: Comparing With and Without -parameters

Create **a single file** `ParameterProbe.java` (saved as UTF-8):

```java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public final class ParameterProbe {
    public static String greet(String guest, int repeat) {
        return "Xin chào, " + guest + " (" + repeat + ")";
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = ParameterProbe.class.getDeclaredMethod(
                "greet", String.class, int.class);

        for (Parameter parameter : method.getParameters()) {
            System.out.println(parameter.getName()
                    + ": " + parameter.isNamePresent());
        }

        System.out.println(greet("Hà", 2));
    }
}
```

The code is self-contained and uses only the Java Standard Library. Run it with JDK 17+ and a terminal that supports Unicode. The clearest approach is to compile into **two different output directories** so you do not accidentally run stale class files.

### 6.1. Compiling with -parameters

On Linux/macOS or a POSIX-compatible shell:

```bash
mkdir -p out-with out-without
javac --release 17 -encoding UTF-8 -parameters -d out-with ParameterProbe.java
java -cp out-with ParameterProbe
```

Stdout **from `java`** is:

```text
guest: true
repeat: true
Xin chào, Hà (2)
```

`javac` usually prints nothing when compilation succeeds. `--release 17` is an example of setting the Java target; `-encoding UTF-8` ensures Vietnamese strings are read accurately; `-parameters` supplies the names `guest` and `repeat` to reflection.

### 6.2. Compiling without -parameters

```bash
javac --release 17 -encoding UTF-8 -d out-without ParameterProbe.java
java -cp out-without ParameterProbe
```

Stdout **from `java`** is:

```text
arg0: false
arg1: false
Xin chào, Hà (2)
```

The Vietnamese string part **still prints correctly** because UTF-8 was used; only the parameter name metadata differs. Because both directories hold separate class versions, you can compare them without overwriting `.class` files.

On Windows PowerShell, create the directories with:

```powershell
New-Item -ItemType Directory -Force out-with, out-without | Out-Null
```

Then run the `javac` and `java -cp` commands above (without `./`). If the Windows console displays Vietnamese text incorrectly, check the terminal/output encoding settings before blaming `-parameters`.

### 6.3. Inspecting MethodParameters with javap

`javap`, bundled with the JDK, lets you inspect bytecode metadata:

```bash
javap -v -p -classpath out-with ParameterProbe
javap -v -p -classpath out-without ParameterProbe
```

Find the `MethodParameters` section of the `greet` method in the `out-with` build: it records the two names `guest` and `repeat`. The `out-without` build lacks the corresponding parameter metadata for `greet`. `javap -v` output also includes many other constant-pool entries and attributes, so you do not need to memorize all of it.

This is a **practical** way to verify the mechanism: inspect the class file itself rather than just seeing variable names in your editor.

## 7. Where Does Spring Framework Use Parameter Names?

Spring Boot runs on Spring Framework. Many annotation-driven tasks only need to know types, but **some mechanisms need parameter names** when you do not specify the name explicitly in the annotation.

### 7.1. Spring MVC: @PathVariable and @RequestParam

Consider the following controller snippet, placed in a project that has `spring-boot-starter-web`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/users/{username}")
    public String byPath(@PathVariable String username) {
        return "Hello, " + username;
    }

    @GetMapping("/greeting")
    public String byQuery(@RequestParam String name) {
        return "Hello, " + name;
    }
}
```

When compiled with `-parameters`, the framework can identify the names `username` and `name` even when the annotations do not declare a name. Example HTTP requests: `GET /users/ha` or `GET /greeting?name=Ha`.

When parameter names are **absent from the class file** and the annotation **does not specify a name**, Spring may be unable to determine the argument name to bind and raise an error, depending on the framework version/code path. This commonly happens when a build is switched from the Maven parent or the Gradle Spring Boot plugin to a hand-written `javac` configuration.

Explicit declarations avoid depending on parameter name metadata in this case:

```java
@GetMapping("/users/{username}")
public String byPath(@PathVariable("username") String username) {
    return "Hello, " + username;
}

@GetMapping("/greeting")
public String byQuery(@RequestParam("name") String name) {
    return "Hello, " + name;
}
```

The two methods in the second snippet are **replacements** for the corresponding methods in the controller; do not paste them verbatim into the same class with the same paths. They require importing `GetMapping`, `PathVariable`, and `RequestParam` as in the previous example.

### 7.2. Constructor Injection and Bean Selection by Name

Spring resolves dependencies primarily by **type**; parameter names act as an additional signal when multiple beans share the same type, rather than a mandatory requirement for every constructor injection. For example, if two `Formatter` beans exist and a constructor accepts `Formatter orderFormatter`, Spring can use the name `orderFormatter` to disambiguate when no qualifier or primary bean applies.

According to the Spring Framework documentation, since **Spring Framework 6.1**, fallback matching by parameter name during autowiring requires the `-parameters` flag. Therefore, in modern Spring Boot projects, omitting the flag can cause an injection case that previously worked to fail bean resolution.

When bean intent truly needs to be explicit, use `@Qualifier("orderFormatter")` or an appropriate bean selection mechanism; do not rely unintentionally on source variable naming. `-parameters` is still recommended so reflection works reliably.

### 7.3. Other Situations

Some mapping, binding, or serialization libraries use constructor/method parameter names; the degree of impact depends on the library, annotations, and configuration. Do not claim that all Spring/Jackson APIs require `-parameters`: annotations with explicit names, record metadata, and other inference paths may suffice in individual cases.

**Kotlin note:** Kotlin code has its own metadata mechanism. When the Spring Boot Gradle plugin works alongside the Kotlin plugin, it can configure `-java-parameters` for `KotlinCompile`; do not mechanically apply Java's `JavaCompile` options to a pure Kotlin project.

## 8. Maven with spring-boot-starter-parent: Defaults Already Provided

For a Maven project inheriting from **`org.springframework.boot:spring-boot-starter-parent`**, the Spring Boot 3.5 documentation preconfigures:

- Java 17 as the default level unless `java.version` is overridden.
- UTF-8 source encoding.
- Compilation with `-parameters`.
- Purposeful configuration of the Maven Compiler Plugin and other plugins.

An illustrative `pom.xml` for a **standalone Spring Boot project**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>compiler-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

With valid `@SpringBootApplication` application source and a Java controller, this is a working POM for Spring Boot 3.5.x. To package it as an executable JAR, the project must have an actual `main` entry point. This example **does not need to declare `<parameters>true</parameters>`** because the starter parent already sets it.

`<java.version>17</java.version>` selects the Java target per the parent model; `project.build.sourceEncoding` makes the encoding explicit, even though the parent already provides the corresponding default. **Do not repeat the `-parameters` flag across multiple configurations unnecessarily.**

Once you have the Maven Wrapper generated by Spring Initializr, run:

```bash
./mvnw clean compile
./mvnw test
```

On Windows: `mvnw.cmd clean compile` and `mvnw.cmd test`. Maven compiles sources and runs tests by lifecycle phase, without a single fixed stdout across all projects. `compile` outputs classes to `target/classes`; `test` executes tests according to the plugins and tests in the project.

## 9. Maven with a Corporate Parent or BOM Import Only: Manual Configuration Needed

If a project **does not inherit from `spring-boot-starter-parent`**, such as using a custom corporate parent and importing the `spring-boot-dependencies` BOM, you **do not automatically inherit** the compiler plugin configuration and defaults from the starter parent.

**A BOM only manages dependency versions**; it does not guarantee the same Java compiler, `-parameters`, or resource filtering configuration as the parent. In that case, configure the Maven Compiler Plugin explicitly in `pom.xml`:

```xml
<!-- Add to <build><plugins> in a POM that does not use the Boot parent. -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Alternatively, you can set properties at the POM level:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
```

**Choose one primary source of configuration:** use either the plugin's `<configuration>` or the corresponding properties (supported by the plugin), and avoid scattering conflicting values. `<parameters>true</parameters>` tells the compiler to emit `MethodParameters`; it is not a runtime option for `java -jar`. `<encoding>UTF-8</encoding>` specifies the Java source charset.

Do not copy **both snippets** with conflicting values into the same POM; they simply illustrate two ways to express the same configuration. The Maven Compiler Plugin version should be pinned by your organization's parent/plugin management or declared explicitly, and must be compatible with your Maven/JDK versions.

Some compiler plugin versions may change default `source`/`target` values or minimum Maven/JDK versions over time; keep `release` explicit to avoid relying on defaults.

## 10. Gradle + Spring Boot Plugin: Configuring JavaCompile

With the Spring Boot Gradle Plugin **and** the Java plugin applied, the Spring Boot 3.5 documentation states that it:

- Automatically sets `options.encoding = 'UTF-8'` on `JavaCompile` tasks that **do not yet have an encoding** configured.
- Automatically adds the `-parameters` compiler argument to `JavaCompile` tasks.
- Provides tasks such as `bootJar`, `bootRun`, and Java support configurations.

Therefore, a project **that already applies the Spring Boot Gradle plugin** does not need to add `-parameters` manually to retain parameter names, unless custom build logic has altered compiler args or the build has plain Java modules that do not apply the Boot plugin.

Example Groovy DSL `build.gradle` for a Java 17 Spring Boot project:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

// Explicitly configure encoding and Java target for all JavaCompile tasks.
// The Spring Boot plugin already supplies -parameters; no need to add it again.
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this example build, both `compileJava` and `compileTestJava` are covered by the `tasks.withType(JavaCompile)` rule. Generated Java sources wired properly into a `JavaCompile` task also receive these options. `options.release = 17` selects the API/language target; the toolchain requests JDK 17. There is no need to set `sourceCompatibility`/`targetCompatibility` redundantly when using this explicit model.

Verification commands (with a Gradle Wrapper and valid project code):

```bash
./gradlew --version
./gradlew clean compileJava --info
./gradlew test
```

On Windows, use `gradlew.bat`. Simply checking flags in `--info` logs is not necessarily enough to verify the actual bytecode; inspect the class file with `javap` as shown in section 6.

### 10.1. Equivalent Gradle Kotlin DSL

`build.gradle.kts` in a project with the same plugins:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

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
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.test {
    useJUnitPlatform()
}
```

This uses Kotlin DSL syntax, differing from Groovy DSL in `id("...")`, `implementation("...")`, `tasks.withType<JavaCompile>()`, and `options.release.set(17)`. For Java sources with the Boot plugin, `-parameters` is still configured by the Boot plugin.

### 10.2. Java Modules Without the Spring Boot Plugin

In a multi-module build, a library module may apply only `java-library` without applying `org.springframework.boot`. In that case, **do not assume** the compiler flags from the Boot application module automatically propagate to the library module's `JavaCompile` task.

Configure that module explicitly:

```groovy
// build.gradle of a module using only the 'java-library' plugin
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs.add('-parameters')
}
```

Kotlin DSL in `build.gradle.kts` for a plain Java module:

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.add("-parameters")
}
```

**Key takeaway:** adding `options.compilerArgs.add("-parameters")` in a module that only uses the Java plugin is explicit. In a Boot module where the plugin already adds the flag, do not repeat it, especially if custom tasks or plugins inspect flags in specific ways.

In multi-module builds, to avoid forgetting configuration on a module, consider a **convention plugin** or centrally managed shared build logic. Do not assume every module targets the exact same Java release; the choice depends on which APIs the library intends to support.

## 11. When Do You Need Separate Resource Encoding Configuration?

Java compilation and resource processing are **two separate steps**:

```text
src/main/java/*.java  --javac encoding UTF-8--> target/classes or build/classes
src/main/resources/** --copy/filter-----------> target/classes or build/resources
```

- **Maven:** `maven-resources-plugin` handles files from `src/main/resources`. The `project.build.sourceEncoding` property is commonly the plugin's default when filtering text, though it also has its own `encoding` option and per-file filtering rules. With the Spring Boot Maven parent, `application.properties`/`application.yml` also use a separate placeholder delimiter convention to avoid colliding with Spring placeholders.
- **Gradle:** the `processResources` task typically copies resources; if you configure `expand` or `filter` for text variable substitution, set `filteringCharset`, such as `'UTF-8'`, so the text transformation step reads the data properly. `JavaCompile`'s `options.encoding` does not automatically set `filteringCharset` on `processResources`.
- **Binary resources** (images, fonts, compressed archives, etc.) must be copied as raw bytes; avoid indiscriminately applying text filters to them.

Gradle Groovy DSL example when **resource filtering is actually used**:

```groovy
tasks.named('processResources', ProcessResources) {
    filteringCharset = 'UTF-8'
    filesMatching('build-info.txt') {
        expand(projectVersion: project.version)
    }
}
```

This is an **advanced snippet**: it assumes a text file `src/main/resources/build-info.txt` containing the corresponding Groovy template placeholder and a project with the Java plugin applied. If you do not use resource filtering, do not add this configuration. When using Spring's `application.properties`, be careful with placeholders in config so the build tool does not alter them unintentionally.

Similarly, `application.properties` can contain Unicode characters; at runtime, Spring reads resources using its own mechanisms. That concern lies outside `javac -encoding`, so do not try to fix resource issues merely by changing compiler flags.

## 12. Verifying That the Compiler Actually Used the Right Options

### 12.1. Maven Diagnostics

In a Maven project with the wrapper:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw clean compile
```

`help:effective-pom` shows the effective configuration after merging parents, profiles, and plugin management, which is useful when inspecting `maven-compiler-plugin`. The output can be very long; search for `maven-compiler-plugin`, `release`, `encoding`, and `parameters`. Compiler configuration coming from properties or parents may not appear where you expect in a short excerpt, so inspect the plugin actually used in the build.

If you need detailed compiler diagnostics, you can run `./mvnw -X compile`; debug logs may contain environment details, so do not post raw logs publicly without redacting sensitive information.

Compiled Java files go to `target/classes` and test classes to `target/test-classes`, unless the build changes the output paths.

### 12.2. Gradle Diagnostics

```bash
./gradlew --version
./gradlew clean compileJava --info
./gradlew compileTestJava --info
```

If a task reports `UP-TO-DATE`, Gradle may have reused valid outputs from a previous run. When compiler args or encoding change, task inputs usually change and trigger recompilation; however, to confirm metadata with high confidence, run an intentional clean compile and inspect `.class` files.

Default Gradle Java plugin outputs are usually under `build/classes/java/main` and `build/classes/java/test`, with separate resource outputs. Custom builds may use different paths.

### 12.3. Using javap to Inspect Class Metadata

For a class you created in package `com.example.demo`:

```bash
# Maven (at module root)
javap -v -p -classpath target/classes com.example.demo.GreetingController

# Gradle (at module root)
javap -v -p -classpath build/classes/java/main com.example.demo.GreetingController
```

In the section for a method with parameters, look for `MethodParameters`. If real parameter names exist and `javap` shows them, the compiler emitted the metadata. Otherwise, check that you are inspecting the right module/build output, plugin config, compiler args, toolchain, and whether the class came from another dependency JAR.

If the build runs with a different JDK than the target JDK, the `javap`/`java` runtime used for inspection must still be compatible with the generated class-file version. Check `./gradlew --version`, `./mvnw -version`, and `java -version` to avoid version mismatches.

### 12.4. Verifying Behavior in the Application

With the `@GetMapping("/users/{username}")` controller wired into a Spring Boot application, call the actual endpoint via an integration test or HTTP request. If an error occurs due to missing parameter names, inspect the stacktrace and class metadata, then compare against the case where the annotation explicitly specifies `@PathVariable("username")`.

**Observed evidence matters more than assumptions from source signatures.** Seeing `String username` in a source method does not mean the running `.class` file actually stored `username`. Many bugs come from stale builds, old JARs, different modules, or classes compiled by another pipeline.

## 13. Common Errors and How to Fix Them

| Symptom | Common cause | Resolution |
|---|---|---|
| `unmappable character for encoding...` during `javac` compile | Source file saved in a different charset than the compiler uses | Check file bytes/editor encoding, convert file to UTF-8, and set `-encoding UTF-8` |
| Logs or responses garble Vietnamese diacritics while compilation succeeds | Console, resource, HTTP, or database charset differs | Identify which layer causes the issue; `options.encoding` does not fix runtime/terminal output |
| Reflection returns `arg0`, `arg1` | Class lacks `MethodParameters` from `-parameters` | Enable the flag in the right module's compile task/plugin, clean compile, and check with `javap` |
| Spring MVC cannot infer argument names for `@PathVariable` / `@RequestParam` | Missing explicit annotation name and class lacks parameter names | Enable `-parameters` or specify the annotation value explicitly; verify the running class |
| Constructor injection fails to pick the right bean by name | Multiple beans of the same type, missing qualifier/primary, or missing name metadata | Use `@Qualifier` or `@Primary` when appropriate; ensure `-parameters` if relying on parameter names |
| Maven build imports a BOM but lacks `-parameters` | A BOM only manages dependencies and does not bring in parent compiler plugin defaults | Configure `maven-compiler-plugin` or project properties explicitly |
| Gradle Boot module works, but a library module lacks metadata | The Boot Gradle plugin only applies to modules where it is configured | Configure `JavaCompile` in the library or convention plugin |
| JDK 17 toolchain not found | Gradle/Maven Toolchain has not detected the JDK or auto-provisioning is not configured | Verify JDK installation, toolchain resolver, and wrapper version |
| `invalid source release: 17` | The active compiler JDK is older than Java 17 | Use an appropriate JDK 17+; verify the actual compiler/toolchain |
| Setting `-Dfile.encoding=UTF-8` still loses parameter metadata | JVM runtime encoding is not `javac -parameters` | Configure the compiler flag in the right place |
| Compilation succeeds, but runtime throws `UnsupportedClassVersionError` | Bytecode targets a newer Java version than the runtime supports | Check the runtime JDK and release target; align environments |
| Compilation still allows newer JDK APIs despite an older target | Only source/target were set without controlling release APIs | Use `--release` or an equivalent tool when a strict target is required |
| `javap` does not show names even though POM/`build.gradle` was updated | The inspected class came from an old build or a different module | Delete the relevant output and recompile; verify the exact class inside the artifact |

**Do not try to fix an encoding issue by adding every compiler option you can find.** Determine first whether the fault lies in source decoding, resource filtering, text output, or runtime behavior. Likewise, enabling `-parameters` only in the app module will not fix classes inside an independently compiled library JAR.

## 14. Standard Configuration Workflow for a Development Team

1. **Standardize the JDK and Java target.** For example, Java 17 for Spring Boot 3.x projects; verify the actual Spring Boot version, Gradle Wrapper/Maven Plugin, and deployment environment before locking it down.
2. **Standardize UTF-8 across editors, Git, and the compiler.** Establish code style/IDE policies and explicit build configuration. Avoid relying on OS-specific defaults.
3. **Choose the build model.** With Maven starter parent, leverage the built-in `java.version`, UTF-8, and `-parameters`; with a Maven corporate parent, explicitly define compiler plugin options. With Gradle Boot modules, the Boot plugin automatically adds UTF-8 if unconfigured and `-parameters`; for plain Java library modules, add the flags explicitly.
4. **Apply consistently to both main and test sources when needed.** `compileJava`, `compileTestJava`, and custom `JavaCompile` tasks must share consistent config if frameworks/reflection read them.
5. **Verify with a small reflection probe.** Compare `Parameter.isNamePresent()` with and without the flag; inspect `MethodParameters` via `javap` when in doubt.
6. **Test real binding behavior.** When annotations rely on parameter names, include integration tests to catch missing compiler metadata immediately.
7. **Fix only the configuration layer at fault.** Maven parents, Gradle modules, toolchains, resources, and consoles are distinct; do not use a runtime JVM property to compensate for a compiler setting.
8. **Keep CI reproducible.** Commit build scripts and wrappers, select a standard JDK, run clean builds per pipeline requirements, and verify the actual artifact.

### Official Documentation for Reference

- [Java javac command — `-encoding`, `--release`, `-parameters`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Java Reflection Parameter API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Spring Boot 3.5 Gradle Plugin — Reacting to Other Plugins](https://docs.spring.io/spring-boot/3.5/gradle-plugin/reacting.html)
- [Spring Boot 3.5 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Maven Compiler Plugin — compile goal parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Gradle CompileOptions API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/compile/CompileOptions.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Spring Framework — Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)

**Takeaway:** The Java compiler needs the **right JDK/release**, the **right encoding** to read sources, and **`-parameters`** if the application needs parameter names at runtime. The compiler produces the bytecode; Spring can only read metadata present in the bytecode that the build process actually generated.
