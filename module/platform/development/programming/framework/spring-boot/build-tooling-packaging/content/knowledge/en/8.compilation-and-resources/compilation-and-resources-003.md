# Configuring Annotation Processors and Generated Source Code

When compiling a Spring Boot application, in addition to the `.java` files written by developers, the compiler can invoke **annotation processors** to inspect Java annotations and declarations, validate rules, and **generate additional Java source files or metadata resources**. For example, MapStruct generates mapper interface implementation classes, while `spring-boot-configuration-processor` generates `spring-configuration-metadata.json` from `@ConfigurationProperties` classes.

A project may run in an IDE yet fail on `mvn clean verify` or `./gradlew clean build` if the processor is not declared properly. Conversely, a successful build may lack IDE-support metadata even though the application still runs at runtime. You need to understand **at which step a processor runs, which classpath it comes from, what kinds of files it creates, how those files are compiled/packaged, and how to verify them**.

This guide applies to Java 17+, using **Spring Boot 3.3.13**, **MapStruct 1.6.3**, and Maven/Gradle as consistent examples. These versions are fixed choices to illustrate the mechanism, not claims that they are the latest releases.

## 1. What Is an Annotation Processor?

An annotation processor is a program that runs **during compilation** via the Java Annotation Processing API (commonly known as JSR 269), using types such as `javax.annotation.processing.Processor`, `AbstractProcessor`, `RoundEnvironment`, and `javax.lang.model.element.Element`. From parsed source code, the processor accesses the syntax/declaration model and can create files through `Filer`.

General flow:

```text
src/main/java/*.java
       |
       v
javac / JavaCompile / maven-compiler-plugin
       |
       +--> Compile classpath: annotation APIs, application libraries
       |
       +--> Processor path: MapStruct processor,
       |                    Spring Boot configuration processor,...
       |
       v
Analyze annotations / types / elements
       |
       +--> Generate .java  ---> subsequent processing rounds ---> compile .class
       |
       +--> Generate metadata/resources (JSON, service files...)
       |
       v
classes + resources + dependencies
       |
       v
Executable JAR/WAR or other artifact
```

The compiler can run **multiple rounds**: when a processor generates new Java source files, those files are analyzed in the next round; finally, the compiler compiles both the original sources and generated sources as configured. A processor is not an HTTP request step, is not a Spring bean inside the application context, and certainly does not run each time the application handles a request.

From a build-control perspective, a processor is **third-party code executed during the build**. Use only trusted processors, pin versions, and do not let the compiler automatically discover and execute arbitrary processors that happen to appear on the dependency classpath.

### Three Output Types That Are Easily Confused

| Tool/mechanism | Input | Typical output | Generates `.java`? |
| --- | --- | --- | --- |
| **MapStruct** | `@Mapper`, `@Mapping` interfaces | `CustomerMapperImpl.java` then `CustomerMapperImpl.class` | **Yes** |
| **Spring Boot configuration processor** | `@ConfigurationProperties` on classes/records | `META-INF/spring-configuration-metadata.json` | **Not required; primary purpose is JSON metadata** |
| **Lombok** | `@Getter`, `@Builder`, `@Data`... | Augments compiler AST to emit bytecode | **Usually does not create separate `.java` files** |
| **Hibernate JPA metamodel processor** | JPA entities | Metamodel classes like `Customer_` | Yes |
| **Spring AOT** | Analyzes application and bean definitions via a dedicated AOT task | Sources/resources/hints used for AOT/native | **May generate files**, but **is not synonymous with** JSR 269 annotation processing |

**Distinguish annotations from processors:** `@Mapper` or `@ConfigurationProperties` are simply metadata/annotation APIs imported in Java code. A specific processor must be supplied on the **processor path** and executed by the compiler; otherwise, nothing produces the corresponding implementation or metadata.

## 2. Two Different Dependency Paths: Compile Classpath and Processor Path

In a Java build, distinguish:

1. **Compile classpath**: classes/annotation types that source code can import during compilation, such as `org.mapstruct.Mapper`.
2. **Annotation processor path**: JARs containing compiler plugins/processor implementations executed by `javac`, such as `org.mapstruct:mapstruct-processor`.

In Gradle, the two configurations are typically `implementation`/`compileOnly` and `annotationProcessor`. In Maven Compiler Plugin 3.x, use `<dependencies>` for APIs needed by sources and `<annotationProcessorPaths>` for processors when you want to control the execution path.

MapStruct example:

```text
Source: import org.mapstruct.Mapper
          |
          +-- requires org.mapstruct:mapstruct on the compile classpath

Compiler: looks up org.mapstruct.ap.MappingProcessor
          |
          +-- requires org.mapstruct:mapstruct-processor on the processor path
          |
          +-- generates CustomerMapperImpl.java
```

If you only add `mapstruct` without providing `mapstruct-processor`, the annotations may compile, but **no mapper implementation** is generated. If you only add `mapstruct-processor` to the processor path and forget the `mapstruct` API on the compile classpath, code importing `@Mapper` will fail to compile. Some library suites bundle API and processor together, so read each library's documentation instead of assuming they all share the same layout.

### How the Compiler Processes and Stores Outputs

- **Maven**: Java files generated by processors default to `target/generated-sources/annotations/`; compiled classes go to `target/classes/`. Spring Boot metadata is written under `target/classes/META-INF/` when generated successfully.
- **Gradle Java plugin**: Java sources generated by `compileJava` default to `build/generated/sources/annotationProcessor/java/main/`; classes and class-output resources go to `build/classes/java/main/` or the task's configured output directory.
- **JARs** generally contain **compiled `.class` files and resources**, not necessarily all generated `.java` source files. In an executable Spring Boot JAR, application outputs appear under `BOOT-INF/classes/`.

Do not copy generated sources into `src/main/java` to "fix missing class errors". Generated sources are build outputs; regenerated files must come from annotations + processors + build configuration. Manually editing generated files is usually lost on the next build and can cause duplicate declarations of the same class.

## 3. Complete Example: One Processor Generating Java, One Generating JSON

This example demonstrates **both output types in the same Spring Boot application**:

- MapStruct reads the `CustomerMapper` interface and generates the Java class `CustomerMapperImpl`, which can be registered as a Spring bean.
- The Spring Boot configuration processor reads the `CustomerSettings` record annotated with `@ConfigurationProperties(prefix = "demo")` and generates metadata for the `demo.message` property.
- A controller invokes the mapper bean; an HTTP test using `MockMvc` verifies that Spring actually instantiates the generated implementation.

### 3.1. Structure

```text
annotation-processor-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/aptdemo/
    │   │   ├── AptDemoApplication.java
    │   │   ├── Customer.java
    │   │   ├── CustomerView.java
    │   │   ├── CustomerMapper.java
    │   │   ├── CustomerSettings.java
    │   │   └── CustomerController.java
    │   └── resources/application.yml
    └── test/
        └── java/dev/example/aptdemo/
            └── CustomerControllerTest.java
```

This is a standalone Maven example for Java 17. In the Gradle section, you can reuse **the exact same Java/YAML files** while replacing `pom.xml` with the equivalent Gradle configuration.

### 3.2. Complete Maven `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>annotation-processor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <mapstruct.version>1.6.3</mapstruct.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.mapstruct</groupId>
            <artifactId>mapstruct</artifactId>
            <version>${mapstruct.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.mapstruct</groupId>
                            <artifactId>mapstruct-processor</artifactId>
                            <version>${mapstruct.version}</version>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why configure it this way?**

- `spring-boot-starter-parent` manages starter versions and default Spring Boot Java/Maven plugin settings. The `maven-compiler-plugin` version is stated explicitly here to make the processor configuration easy to compare.
- `org.mapstruct:mapstruct` holds the annotations/APIs that Java sources import; therefore it belongs in `<dependencies>`.
- `mapstruct-processor` and `spring-boot-configuration-processor` are passed to the compiler via `<annotationProcessorPaths>` and **do not need** to be added to the application's runtime dependencies.
- The Spring Boot Maven Plugin produces an executable JAR via the `repackage` execution managed by the starter parent when the plugin is declared; it is a **packaging plugin**, independent of the two annotation processors.
- Processor paths are listed explicitly, avoiding accidental execution of processors present on the regular dependency graph. When adding a new processor, append it to this list.

Running the example requires a compatible JDK 17 and Maven 3.9.x (or a matching Maven Wrapper). The example pins Maven Compiler Plugin 3.13.0; for another project, check JDK/plugin compatibility against your project's build baseline.

### 3.3. Application Java Code

File `src/main/java/dev/example/aptdemo/AptDemoApplication.java`:

```java
package dev.example.aptdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class AptDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AptDemoApplication.class, args);
    }
}
```

File `src/main/java/dev/example/aptdemo/Customer.java`:

```java
package dev.example.aptdemo;

public record Customer(long id, String name) {
}
```

File `src/main/java/dev/example/aptdemo/CustomerView.java`:

```java
package dev.example.aptdemo;

public record CustomerView(long id, String displayName) {
}
```

File `src/main/java/dev/example/aptdemo/CustomerMapper.java`:

```java
package dev.example.aptdemo;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface CustomerMapper {
    @Mapping(source = "name", target = "displayName")
    CustomerView toView(Customer customer);
}
```

This is an interface with no hand-written `toView` implementation. When `javac` processes `@Mapper` and `@Mapping`, MapStruct generates `CustomerMapperImpl.java` containing the logic to copy `id` and map `name → displayName`. `componentModel = "spring"` adds the appropriate annotations so Spring manages the generated implementation as a bean.

File `src/main/java/dev/example/aptdemo/CustomerSettings.java`:

```java
package dev.example.aptdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record CustomerSettings(String message) {
}
```

This record provides runtime configuration binding. `@ConfigurationPropertiesScan` on the application class lets Spring register the `CustomerSettings` bean. **The annotation processor does not perform property binding at runtime**; its role is to generate metadata for IDEs and configuration tools. Spring Boot runtime can still bind `demo.message` even if JSON metadata is not generated, provided classes and configuration are set up properly.

File `src/main/java/dev/example/aptdemo/CustomerController.java`:

```java
package dev.example.aptdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {
    private final CustomerMapper mapper;
    private final CustomerSettings settings;

    public CustomerController(CustomerMapper mapper, CustomerSettings settings) {
        this.mapper = mapper;
        this.settings = settings;
    }

    @GetMapping("/customer")
    public CustomerView customer() {
        return mapper.toView(new Customer(7L, settings.message()));
    }
}
```

With MapStruct's Spring component model, constructor injection on `CustomerController` receives a bean implementing `CustomerMapper` once the generated source is compiled. You do not manually call `new CustomerMapperImpl()` or declare a `@Bean` method.

File `src/main/resources/application.yml`:

```yaml
demo:
  message: Lan
```

### 3.4. End-to-End Verification Test

File `src/test/java/dev/example/aptdemo/CustomerControllerTest.java`:

```java
package dev.example.aptdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void mappingIsGeneratedAndRegisteredAsSpringBean() throws Exception {
        mvc.perform(get("/customer"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.displayName").value("Lan"));
    }
}
```

This test proves that `CustomerMapperImpl` was generated, compiled, and registered by Spring as a bean: if the implementation is missing, the application context typically fails to construct `CustomerController`. `jsonPath` assertions do not depend on JSON field order.

### 3.5. Compiling, Testing, and Running

In the directory containing `pom.xml`:

```bash
mvn -version
mvn clean verify
java -jar target/annotation-processor-demo-1.0.0.jar
```

If the project includes a Maven Wrapper, replace `mvn` with `./mvnw` (on Windows, use `mvnw.cmd`). `clean verify` removes old outputs and runs the compiler/annotation processors, unit tests, and goals bound up to `verify`.

Open a second terminal after the application starts:

```bash
curl -s http://localhost:8080/customer
```

Response content by fields:

```json
{"id":7,"displayName":"Lan"}
```

JSON property ordering can vary by serializer/configuration; the values `id = 7` and `displayName = "Lan"` are what the test verifies.

## 4. Inspecting Real Outputs After Compilation

Do not look only at `BUILD SUCCESS` logs. Inspect **generated files, compiled classes, and metadata** to distinguish the two processors:

| Maven path | Created by | Meaning |
| --- | --- | --- |
| `target/generated-sources/annotations/dev/example/aptdemo/CustomerMapperImpl.java` | MapStruct | Java source generated from the `CustomerMapper` interface |
| `target/classes/dev/example/aptdemo/CustomerMapperImpl.class` | Java compiler | Bytecode compiled from the generated source |
| `target/classes/META-INF/spring-configuration-metadata.json` | Spring Boot configuration processor | Metadata describing properties such as `demo.message` |
| `target/annotation-processor-demo-1.0.0.jar` | Maven JAR + Spring Boot Maven Plugin | Executable JAR containing application classes/resources |

On Linux/macOS, inside the project directory:

```bash
ls target/generated-sources/annotations/dev/example/aptdemo/
ls target/classes/dev/example/aptdemo/CustomerMapperImpl.class
grep -n 'demo.message' target/classes/META-INF/spring-configuration-metadata.json
jar tf target/annotation-processor-demo-1.0.0.jar
```

In the `jar tf` output, check for:

```text
BOOT-INF/classes/dev/example/aptdemo/CustomerMapperImpl.class
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

These are the two key entries; `jar tf` will output many other entries as well. Inside the metadata output, look for a property entry for `demo.message`. If the file is missing, inspect the processor configuration and `@ConfigurationProperties` structure. Do not expect the metadata processor to generate a Java class simply because MapStruct creates `.java` files.

On Windows PowerShell, you can use:

```powershell
Test-Path target/generated-sources/annotations/dev/example/aptdemo/CustomerMapperImpl.java
Test-Path target/classes/META-INF/spring-configuration-metadata.json
Select-String -Path target/classes/META-INF/spring-configuration-metadata.json -Pattern 'demo.message'
```

Both `Test-Path` commands should return `True` if the build succeeded properly. `Select-String` searches for `demo.message`; JSON formatting and field ordering may vary by processor version.

**Core verification takeaway:** generated sources are then compiled by the compiler; the JAR typically carries **compiled classes**. JSON metadata is a build-time resource for tooling, not what decides which profile is active or the runtime value of `demo.message`.

## 5. Equivalent Gradle Configuration

If the project uses Gradle, create `settings.gradle` and `build.gradle` in the root directory **instead of `pom.xml`**. Keep the Java sources, YAML, and tests from section 3 unchanged.

`settings.gradle`:

```groovy
rootProject.name = 'annotation-processor-demo'
```

`build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '1.0.0'

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
    implementation 'org.mapstruct:mapstruct:1.6.3'

    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

When both `org.springframework.boot` and `io.spring.dependency-management` are applied, the Spring Boot Gradle Plugin coordinates importing the Boot release's BOM, allowing `spring-boot-configuration-processor` in the example to omit a version. If using Gradle's native `platform(...)` instead of the dependency management plugin, ensure the processor configuration also receives the needed constraints/versions; do not assume a BOM automatically applies to every configuration.

Dependency paths:

- `implementation 'org.mapstruct:mapstruct:1.6.3'`: makes the annotation API visible during source compilation.
- `annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'`: runs the processor that generates `CustomerMapperImpl.java`.
- `annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'`: runs the processor that generates configuration metadata JSON.
- `testImplementation ...starter-test`: compiles/runs tests; if **test sources themselves declare mappers that need processing**, configure `testAnnotationProcessor` separately rather than assuming main processors apply identically to test compilation.

In a project with a compatible Gradle Wrapper, run (use `gradlew.bat` on Windows):

```bash
./gradlew clean build
java -jar build/libs/annotation-processor-demo-1.0.0.jar
```

Check typical Java plugin outputs:

```text
build/generated/sources/annotationProcessor/java/main/dev/example/aptdemo/CustomerMapperImpl.java
build/classes/java/main/dev/example/aptdemo/CustomerMapperImpl.class
build/classes/java/main/META-INF/spring-configuration-metadata.json
build/libs/annotation-processor-demo-1.0.0.jar
```

Metadata class-output paths can vary by task, toolchain, or specialized plugin; confirm against the actual `JavaCompile` configuration. With `bootJar`, `.class` files and required metadata go into `BOOT-INF/classes/`. Plain JARs and executable JARs have different packaging layouts.

With Gradle's default `annotationProcessor`, the compiler receives processors on a **dedicated processor path**. Do not move processors into `implementation` just so an IDE "sees" them, as this pollutes the classpath and may fail to trigger processing as expected, especially on newer JDKs.

## 6. The Specific Role of spring-boot-configuration-processor

Spring Boot uses `@ConfigurationProperties` to describe and bind a group of configuration properties to a Java bean/record. `spring-boot-configuration-processor` analyzes these declarations and generates metadata so IDEs can suggest property keys, types, and descriptions. **Runtime property binding is a separate mechanism** and does not depend on whether JSON metadata exists.

Example:

```java
package dev.example.aptdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record CustomerSettings(String message) {
}
```

The processor can generate metadata for `demo.message` based on the prefix and the record's `message` component. IDEs with Spring Boot support can use this metadata to autocomplete keys in `application.yml`.

Important limitations:

- The processor does not emit the value `Lan` into metadata merely because it appears in `application.yml`; it analyzes Java declarations and additional metadata, and is not used as a runtime configuration system.
- Metadata generally does not store secrets. If supplying descriptions and value hints via additional metadata, never include real credentials in metadata.
- If a property is defined in a way the processor cannot recognize, the JSON may omit an entry even though the application still binds it at runtime. Verify the output file rather than guessing from startup logs.
- When using Lombok alongside the configuration processor, processor ordering and compatibility can matter because the metadata processor must see the final property model.
- When `src/main/resources/META-INF/additional-spring-configuration-metadata.json` is present, resource processing order matters. In Gradle, the Spring Boot documentation recommends making `compileJava` see `processResources` outputs (for example `tasks.named('compileJava') { inputs.files(tasks.named('processResources')) }`), though only configure this when actually using additional metadata.

## 7. Annotation Processing in `javac`: Discovery, Rounds, and Options

When enabled, the Java compiler can discover processors via the service provider file `META-INF/services/javax.annotation.processing.Processor` in JARs on the processor path. Alternatively, processor class names can be specified explicitly. Processors use `RoundEnvironment` to inspect annotated elements and `Filer#createSourceFile` or `createResource` to emit outputs.

A simple processor workflow (illustrative, not a standalone build command):

```text
Round 1: sees @Mapper on CustomerMapper
  -> MapStruct generates CustomerMapperImpl.java
Round 2: compiler receives CustomerMapperImpl.java
  -> processes annotations that may exist on newly generated sources
Final round
  -> processor finishes, compiler compiles sources
```

Relevant `javac` options:

| Option | Meaning |
| --- | --- |
| `-processorpath` or `--processor-path` | Where the compiler looks for processors |
| `-processor class.name.Processor` | Specifies explicit processor(s) |
| `-proc:none` | Compiles **without** running annotation processing |
| `-proc:only` | Runs annotation processing without compiling Java classes |
| `-proc:full` | Runs annotation processing **and** compiles |
| `-s directory` | Directory where generated Java sources are saved |

Maven and Gradle translate their configurations into appropriate compiler options. **You do not need to invoke `javac` manually with a long list of JARs** in Spring Boot projects using properly configured build plugins.

### Note on JDK 23 and Later

Starting with **JDK 23**, `javac` no longer scans the classpath and runs annotation processors by default simply because they happen to be present, unless processing is explicitly requested or configured. Consequently, a project relying on implicit discovery can suddenly start missing generated sources after a JDK upgrade.

The fix is to **declare the processor path or specific processors via the build tool**, such as `<annotationProcessorPaths>` or Gradle `annotationProcessor`. If you must configure `-proc:full`, verify that the running JDK supports it; `-proc:full` was backported to recent JDK 17 updates, so **do not assume every older JDK 17 build accepts this flag**.

In the Maven configuration in section 3, the processor path list is already explicitly declared; there is no need to add `<proc>full</proc>` just to run the Java 17 example. Review your project's security goals when deciding between discovery and explicitly listing processor classes.

## 8. Other Code-Generation Technologies to Distinguish

### 8.1. Lombok

Many projects use Lombok with `@Getter`, `@Builder`, and `@RequiredArgsConstructor` to reduce boilerplate. Because it hooks into compilation directly, after a build you normally **will not see an independently generated `SomeClassWithGetters.java` source file**. Interoperating with MapStruct may require the `lombok-mapstruct-binding` adapter so MapStruct sees getters/setters generated by Lombok.

Typical Gradle configuration for Lombok alone (snippet added to `dependencies`):

```groovy
compileOnly 'org.projectlombok:lombok:<version-compatible>'
annotationProcessor 'org.projectlombok:lombok:<version-compatible>'
```

`<version-compatible>` in this fragment is a placeholder requiring a specific Lombok version compatible with your JDK/project; this snippet **does not run standalone**. When combining Lombok and MapStruct, add the binding dependency recommended by both projects, verify processor handling, and run a clean build. Lombok is not used in the MapStruct example in section 3, so that POM **does not** need the binding.

### 8.2. JPA Metamodel and QueryDSL

Tools generating `*_` metamodel classes or Q-types can use annotation processing to generate Java types for type-safe queries. Output folder layout and processor setup resemble MapStruct, but artifact/processor names and `javax`/`jakarta` compatibility differ across generations. For Spring Boot 3.x/Jakarta Persistence, verify the Jakarta-compatible processor branch before following older guides.

### 8.3. Spring AOT and OpenAPI Code Generation

Spring AOT can generate sources/resources based on application context analysis in the `processAot` task or corresponding goal; OpenAPI Generator can generate clients/servers from schemas in a separate plugin step. Both produce **generated source**, yet neither should be called a Java annotation processor if it does not use the compiler's JSR 269 mechanism.

**Distinguishing question:** Is the file generated during a compiler annotation-processing round, or in a separate code-generation task/goal before or after compilation? The answer determines task dependencies, source directories, caching, and debugging.

## 9. Generated Sources in IDEs, CI, and Source Control

**IDEs:** IntelliJ IDEA, Eclipse, or VS Code may use an internal build mode or Java language server different from Maven/Gradle CLI. When an IDE reports `Cannot resolve CustomerMapperImpl` while `mvn clean verify` passes, check IDE annotation processing settings, reimport the Maven/Gradle project, and inspect `generated-sources` source roots. Never copy generated files into `src/main/java` to silence editor errors.

**CI:** use the Wrapper if provided, pin the JDK/toolchain, and run a **clean build** to eliminate reliance on stale outputs from developer machines:

```bash
# Maven
mvn clean verify

# Or Gradle
./gradlew clean build
```

Do not run both build tools with two different build models for the same release unless your project actively maintains both. The commands above are **alternatives**, not two sequential mandatory steps.

**Source control:** commit interfaces, annotations/configuration, and POM/Gradle build scripts to Git. Normally exclude `target/`, `build/`, and generated files from Git when they are reproducible. If a special requirement demands committing generated sources (such as external contracts), clearly define **who owns them**, how they are regenerated, and drift checks; avoid files that are both generated and hand-edited.

**Build reproducibility:** pin processor and build plugin versions. Some generators embed timestamps or build environment info into generated sources, causing artifacts to differ. Configure timestamp suppression if the processor supports it, check MapStruct-specific options, and keep the JDK/toolchain consistent. Do not claim reproducibility solely because `clean` was run.

**Compile lifecycle:** avoid wiring tasks such that `compileJava` runs before a required source-generating task without an explicit dependency. For properly declared JSR 269 processors, generated Java sources are handled by the compiler as part of compilation; no fake custom copy task is needed.

**Module separation:** if developing an internal processor, build the processor as a separate artifact (or an upstream module compiled first) so consumer projects can place the built artifact on their annotation processor path. A processor normally cannot both live as uncompiled source inside the consumer module and be used by the compiler during that same compilation.

## 10. Troubleshooting by Signals Instead of Guessing

| Symptom | Typical cause | How to inspect/fix |
| --- | --- | --- |
| `Cannot find symbol CustomerMapperImpl` or Spring missing mapper bean | MapStruct processor did not run, wrong processor path, or generated output not compiled | Inspect `target/generated-sources/annotations`/`build/generated/sources`, processor list, and compiler logs; run a clean build |
| `No qualifying bean of type CustomerMapper` | Implementation not generated or generated mapper lacks Spring component model | Verify `@Mapper(componentModel = "spring")`, `CustomerMapperImpl.class`, and component scanning |
| Interface has `@Mapper` but no `.java` is generated | Only MapStruct annotation API present; processor implementation missing | Add `mapstruct-processor` to the proper processor path |
| Compiler reports `org.mapstruct.Mapper` not found | MapStruct API missing from compile classpath | Declare `mapstruct` in `<dependencies>` or Gradle `implementation` |
| App runs, but IDE does not autocomplete `demo.message` | Missing `spring-configuration-metadata.json` or IDE has not indexed metadata | Add `spring-boot-configuration-processor`, recompile, check JSON and IDE sync |
| `@ConfigurationProperties` does not bind at runtime | Configuration properties bean not registered, wrong prefix/key, or config source issue | Use `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` and inspect Spring `Environment`; the metadata processor does not handle runtime binding |
| Maven builds on machine A, missing generated code on machine B | Different JDK/plugin, annotation processing disabled, or relying on implicit discovery | Check `mvn -version`, effective POM, processor paths; watch out for JDK 23+ |
| Gradle IDE results differ from CLI | IDE uses its own compiler and misses processor path or generated source roots | Reimport Gradle project, enable annotation processing, compare with `./gradlew clean build` |
| MapStruct + Lombok cannot see getters | Processor ordering/binding or incompatible versions | Check `lombok-mapstruct-binding` and official version compatibility; use explicit processor paths |
| Generated Java exists, but not found inside Boot JAR | JAR holds compiled `.class` files, not generated `.java` by default | Check `BOOT-INF/classes/...Impl.class` with `jar tf` |
| `-proc:none` enabled and mapper disappears | Compiler instructed to skip annotation processing | Remove/isolate diagnostic flags from release builds |
| Generated metadata stale after source changes | Incremental compilation/cache/IDE did not rebuild completely | Run `clean compile` to confirm, then fix task inputs/outputs if recurring |

### Ordered Diagnostic Workflow

1. **Confirm the active compiler:** check `mvn -version` or Gradle toolchain; verify Java version, plugin versions, and the module being built.
2. **Verify inputs:** check annotations, package placement, and imports for MapStruct API or `@ConfigurationProperties`.
3. **Verify the processor path:** Maven `annotationProcessorPaths`; Gradle `annotationProcessor`. Do not look only at `implementation`/runtime dependencies.
4. **Run a clean build:** `mvn clean verify` or `./gradlew clean build` and read the earliest error in compiler logs.
5. **Inspect both distinct outputs:** MapStruct `.java` and `spring-configuration-metadata.json`; do not conclude a processor is broken just because it did not create a file it is not responsible for.
6. **Inspect compiled classes and JAR:** look for `...CustomerMapperImpl.class` in classes/Boot JAR; if source exists without a `.class`, check compile steps and source roots.
7. **Run integration or smoke tests:** does Spring inject the mapper? Is the HTTP response right? Does property binding work?
8. **Compare CI and IDE:** when CLI passes and IDE fails, fix IDE integration/source paths; when CLI fails, fix the build model/processors.

## 11. Self-Check Exercises

**Scenario A.** A Maven project uses `@Mapper` but only declares `org.mapstruct:mapstruct` in `<dependencies>`. Is `CustomerMapperImpl.java` guaranteed to be generated?

*Answer:* No. `@Mapper` is only the annotation API; you must supply the MapStruct processor on the annotation processor path, ensure processing is enabled, and verify the compiler runs cleanly.

**Scenario B.** `spring-boot-configuration-processor` is present, yet there is no `CustomerSettingsImpl.java`. Is the processor broken?

*Answer:* No. The configuration processor is not responsible for generating a Java implementation for the record; it generates JSON metadata such as `META-INF/spring-configuration-metadata.json`. `CustomerSettings` remains the developer-declared record.

**Scenario C.** A Java 17 build previously auto-discovered processors from the classpath; after upgrading to JDK 23, generated files vanish. What must be fixed?

*Answer:* Declare the processor path explicitly in Maven Compiler Plugin or Gradle `annotationProcessor`. JDK 23 changed implicit annotation processing defaults; check compiler options before editing source code.

**Scenario D.** `target/generated-sources/annotations/CustomerMapperImpl.java` exists, so should we commit it to Git so production does not have to regenerate it?

*Answer:* Not as the default practice. Commit the original source and processor/build configuration so CI regenerates and compiles sources under version and test control. Commit generated artifacts only if an explicit policy requires it.

**Scenario E.** Why can `spring-configuration-metadata.json` be inside a JAR even without a corresponding generated `.java` file?

*Answer:* Annotation processors can emit **resources** through the compiler without having to generate Java sources. The Spring Boot configuration processor uses JSON metadata to support tools and IDEs.

**Scenario F.** `@ConfigurationProperties` binding works fine, yet the IDE does not suggest `demo.message`. Where should you look?

*Answer:* Check the metadata processor, the compiled JSON file, and IDE indexing. Do not change runtime binding logic if runtime already works.

**Scenario G.** A project uses both Lombok and MapStruct. Missing-getter errors break the mapper. Will simply upgrading the Spring Boot version definitely fix it?

*Answer:* No. Check MapStruct + Lombok support, processor paths, and the corresponding binding integration; upgrading Boot does not automatically resolve every interaction between annotation processors.

## 12. Checklist Before Accepting an Artifact

- Sources and build model are versioned; processor APIs and processor implementations are declared on the **correct classpaths**.
- Processor versions, JDK/toolchain, and Maven/Gradle plugin versions are explicitly defined.
- A clean build succeeds; generated Java appears in the right output directory; JSON metadata appears if the module runs a metadata-generating processor.
- Generated Java is compiled into `.class` files, and required classes/resources appear in the artifact.
- Spring Boot tests exercising the mapper bean and property binding pass; do not check file existence alone.
- Generated files have clear ownership (normally build-owned) and are not hand-edited; CI can reproduce outputs from sources and dependencies.
- The compiler is not allowed to run unapproved processors implicitly from the dependency graph; treat processor artifacts with the same supply-chain control as build plugins.

**Key takeaway:** An annotation processor is a **build-time** tool running alongside the compiler that can generate **Java sources** or **metadata resources**. Place APIs on the compile classpath, place processors on the processor path, inspect outputs in generated-sources/classes, and verify behavior in the packaged artifact. For Spring Boot, MapStruct generates the mapper implementation; `spring-boot-configuration-processor` generates metadata for IDE support and does not replace runtime property binding.

### References

- Java `javac`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Apache Maven Compiler Plugin 3.13.0 — `compiler:compile` and `annotationProcessorPaths`: https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html
- MapStruct 1.6 — Reference Guide: https://mapstruct.org/documentation/1.6/reference/html/
- Spring Boot — Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html
- Gradle — Java Library Plugin/Declaring an Annotation Processor: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Oracle JDK 23 release notes — Annotation processing default: https://www.oracle.com/java/technologies/javase/23-relnote-issues.html
