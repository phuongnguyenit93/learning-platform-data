# How Spring AOT, GraalVM Native Image, and Native Build Tools Relate

## 1. The Big Picture

When compiling a Spring Boot application into a **GraalVM Native Image**, three components work together while solving three distinct problems:

1. **Spring AOT (Ahead-of-Time)** pre-processes determinable parts of the Spring application at build time, generates initialization code, and supplies information needed for the native environment.
2. **GraalVM Native Image** analyzes the Java program and compiles the reachable code into an executable for the target operating system and CPU architecture.
3. **GraalVM Native Build Tools** consists of Maven/Gradle plugins that orchestrate the build steps, pass configuration to the Native Image compiler, and integrate with build/test workflows.

This is the foundation of the **SPRING_BOOT_NATIVE_IMAGE** topic: using Spring AOT and GraalVM to produce a native build, then evaluating startup time, memory, compatibility, container packaging, and operations. You need to clearly distinguish the three roles to know where to fix things when a build fails.

| Component | Primary Responsibility | Typical Inputs | Typical Outputs |
| --- | --- | --- | --- |
| Spring AOT | Prepares the Spring application for static processing | Bean definitions, Spring configuration, classpath, `RuntimeHints` | Generated Java code for bootstrap/bean registration, dynamic access info |
| GraalVM Native Image | Reachability analysis and compilation to an executable | Application bytecode, libraries, AOT code, reachability metadata | Native executable for target OS/CPU |
| Native Build Tools | Connects the build process to Native Image via Maven/Gradle | Plugin configuration, tasks/goals, toolchain, compiler arguments | Repeatable native build and test workflows |

**Core distinction:** Spring AOT understands Spring's initialization model; GraalVM Native Image compiles the program; Native Build Tools helps the build system invoke the appropriate steps. No single component completely replaces the others.

## 2. Why Does Spring Boot Need an AOT Step?

A Spring Boot application running on the JVM can typically do many things at startup: component scanning, evaluating configuration conditions, discovering beans, creating proxies, or using reflection. The JVM supports runtime class loading and type discovery, so these mechanisms usually work without listing every accessed type in advance.

Conversely, GraalVM Native Image operates under a **closed-world** assumption: at build time, the compiler needs sufficient information to determine which code and data may be used. A direct call like `new InvoiceService()` is relatively easy to analyze; assembling a class name from a configuration string and calling `Class.forName(...)` can prevent the analyzer from recognizing which class, constructor, or method must be retained.

Spring AOT bridges that gap by:

- Pre-processing the Spring context during the build phase and **generating Java code** for operations such as bean registration and instantiation.
- Providing or aggregating **runtime hints** for reflection, JDK dynamic proxies, resources, serialization, and certain other dynamic access patterns.
- Moving early-determinable configuration decisions to build time, reducing the work the application must perform at startup.

For example, with a bean declared via `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
class BillingConfiguration {
    @Bean
    BillingService billingService(PaymentGateway gateway) {
        return new BillingService(gateway);
    }
}
~~~

When building in AOT mode, Spring can generate code for registering and instantiating the bean based on the definition above. The generated code is **Java source used in the subsequent build steps**; it is not a native executable and does not replace the GraalVM compiler.

An important consequence: choices that alter the bean structure, such as certain `@Conditional` annotations, profiles, or configurations evaluated when AOT processes the application, may become fixed in the build output. You should not assume that changing an environment variable at runtime will rebuild the entire `ApplicationContext` under a new configuration the way running a JAR on the JVM does.

## 3. What Does GraalVM Native Image Do After Spring AOT?

Native Image takes the compiled bytecode, related libraries, AOT-generated code, and dynamic accessibility metadata. The compiler performs **reachability** analysis from the program's entry points, determines which classes, methods, and data must be kept, and generates machine code for the target platform.

At build time, Native Image needs to know about operations that cannot easily be inferred via static analysis, such as:

- Instantiating a class via reflection when the class name comes from a string.
- Invoking a constructor or method via reflection.
- Reading classpath resources via dynamically constructed names or patterns.
- Creating a JDK dynamic proxy for a specific list of interfaces.
- Serialization/deserialization requiring access to members not directly visible to the analyzer.

This information is supplied via **reachability metadata**, including runtime hints contributed by Spring and libraries. Native Image uses metadata to decide which dynamic access capabilities to preserve in the executable. Metadata helps the compiler recognize dynamic access needs, but **it does not turn a native image into an environment capable of arbitrarily loading classes absent at build time**.

The resulting binary can run **without installing a JVM on the host machine**, yet may still depend on operating system libraries or platform linking mechanisms. An executable built for Linux/x86-64 cannot natively run on Windows/ARM64; you must build for the right target or use a compatible build environment.

Native Image also carries trade-offs: builds generally take more time and resources, some dynamic libraries require extra configuration, and long-running throughput/latency can differ from a JIT-enabled JVM. Faster startup or lower RSS must be **measured on the same application and the same scenario**, not treated as a guarantee for every workload.

## 4. Where Does Native Build Tools Fit in the Build Chain?

Native Build Tools provides the primary plugins:

- Maven: `org.graalvm.buildtools:native-maven-plugin`.
- Gradle: `org.graalvm.buildtools.native`.

The plugin manages how `native-image` is invoked, accepts build argument configurations, locates the executable, and integrates native build/test tasks. When combined with the **Spring Boot Maven/Gradle plugin**, the pipeline invokes the Spring AOT step at the right moment and feeds its outputs into Native Image. In other words, Native Build Tools **does not analyze beans with Spring semantics itself** and **does not replace the GraalVM compiler**.

~~~mermaid
flowchart TD
    A["Spring Boot source code and dependencies"] --> B["Spring AOT: process ApplicationContext"]
    B --> C["Generated initialization code and runtime hints"]
    C --> D["Compile Java to bytecode"]
    D --> E["GraalVM Native Image: reachability and native compilation"]
    E --> F["Native executable for target OS/CPU"]
    G["Maven / Gradle + Native Build Tools"] -. "orchestrate build" .-> B
    G -. "invoke native-image" .-> E
~~~

The diagram illustrates logical responsibilities; specific steps, temporary directory locations, and exact task ordering can vary across Maven, Gradle, and plugin versions. Whichever tool you use, the essential invariant is that **AOT code and metadata must be fed into native compilation**.

### Maven: Workflow Example

In a Spring Boot project using `spring-boot-starter-parent`, you can declare the Native Build Tools plugin alongside the Spring Boot Maven plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

With a compatible set of Spring Boot and plugin versions, the parent already prepares the `native` profile:

~~~bash
./mvnw test
./mvnw -Pnative native:compile
~~~

The first command runs the standard JVM test suite. The second triggers the native executable build process with the required AOT steps. The Maven executable typically resides in `target/`, though the filename depends on project configuration. On Windows, you can use `mvnw.cmd` instead of `./mvnw`.

If the project **does not use** `spring-boot-starter-parent`, you must set up the equivalent AOT, compiler, and lifecycle/plugin executions; do not assume the `native` profile exists automatically. Also ensure the build machine has the JDK/GraalVM, the `native-image` tool, a native compiler, and the system libraries required by the toolchain.

### Gradle: Workflow Example

With Gradle Groovy DSL, in addition to your project's Spring Boot and Java plugins, add Native Build Tools:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'org.graalvm.buildtools.native' version '<native-build-tools-version>'
}
~~~

The two values inside `<...>` are placeholders for actual versions **compatible with your project**; leaving the placeholders unmodified will fail to build. After configuring dependencies and the toolchain:

~~~bash
./gradlew test
./gradlew nativeCompile
~~~

When the Spring Boot and Native Build Tools plugins are integrated, the `nativeCompile` task consumes the AOT outputs. You can inspect tasks such as `processAot`, `nativeCompile`, and `nativeTest` in your plugin version. The Gradle executable is typically placed under `build/native/nativeCompile/`. On Windows, you can use `gradlew.bat`.

**There is no single Native Build Tools command that applies to every project**: how versions, profiles, tasks, and native tests are declared depends on the build system. The invariant is that the build task must connect AOT code to `native-image`.

## 5. Example: When Do You Need to Add RuntimeHints?

Suppose an application reads an exporter name from configuration and instantiates the object via reflection:

~~~java
String className = "com.example.demo.CsvExporter";
Class<?> type = Class.forName(className);
Object exporter = type.getDeclaredConstructor().newInstance();
~~~

On the JVM, this snippet can work if the class is on the classpath and accessible. In a native build, the static analyzer **cannot necessarily determine** which class will be instantiated from the string. Without appropriate metadata, accessing the constructor may fail at native runtime.

A clear way to declare intent is using Spring's `RuntimeHintsRegistrar`:

~~~java
package com.example.demo;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ImportRuntimeHints;

@SpringBootApplication
@ImportRuntimeHints(DemoHints.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

class DemoHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CsvExporter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("reports/*.txt");
    }
}

class CsvExporter {
    public CsvExporter() {}
}
~~~

In this example:

- `@ImportRuntimeHints` instructs Spring to load the registrar; `CsvExporter` is registered for invoking its constructor via reflection.
- The `reports/*.txt` pattern illustrates a classpath resource, such as `src/main/resources/reports/sample.txt`, that must be packaged to be read at runtime.
- If Spring or a framework library already generates sufficient hints for a given access type, **there is no need to register duplicates**. Extra hints are meant for dynamic behaviors the system does not yet know about.

You must register the **exact access type**: retaining a constructor does not mean allowing invocation of every private method or all forms of serialization. For dynamic proxies, resources, or serialization, use the corresponding section of `RuntimeHints` or library-provided metadata. Avoid registering the entire classpath wholesale just to "fix" errors; that inflates binary size and sacrifices control.

## 6. Distinguishing Stages and Responsibilities

| Situation | Which Component to Check First? | Why |
| --- | --- | --- |
| A conditional bean behaves differently in the native build | Spring AOT and build-time configuration | Conditions affecting the bean graph may have been locked during AOT processing |
| Native runs but fails to instantiate a class via reflection | Runtime hints/reachability metadata, then Native Image | The dynamically used type or member may not have been declared |
| Template/resource not found in the binary | Resource hints and how resources are included in the artifact | The resource may not have been packaged into the image |
| Build reports `native-image` or native compiler not found | Toolchain, Maven/Gradle Native Build Tools | System compiler/tooling is missing or misconfigured |
| Native image build runs out of memory or is too slow | Native Image and build environment configuration | Native compilation has its own CPU/RAM costs |
| Native app runs on wrong architecture or lacks OS libraries | Build platform, linker, and container runtime | Executable depends on OS/CPU and library linking strategy |
| JAR works but native functional tests fail | Dynamic feature usage and native test suite | JVM-supported behavior may require additional metadata or implementation changes |

Three easily confused notions:

1. **Spring AOT is not synonymous with GraalVM Native Image.** AOT generates code to prepare the application; Native Image compiles it into machine code.
2. **Native Build Tools is not synonymous with `spring-boot-maven-plugin` or `org.springframework.boot` in Gradle.** The Spring Boot plugin provides application/AOT tasks; Native Build Tools integrates the native compiler. They collaborate.
3. **AOT does not eliminate all need for reflection.** Parts using reflection can still work, provided the compiler has sufficient metadata and the API is supported.

## 7. Hands-On Sequence to Verify All Three Work Together

Suppose an application has an HTTP endpoint and a report-export flow using resources or reflection:

1. **Verify the JVM build:** run unit/integration tests, package the JAR, and test the endpoint. This establishes baseline behavior for comparison.
2. **Prepare the native toolchain:** use compatible versions of Java, Spring Boot, GraalVM, and Native Build Tools; check `native-image --version` along with the required compiler/linker.
3. **Build native with Maven or Gradle:** run `native:compile` in the appropriate profile or `nativeCompile`. Inspect logs to verify both the AOT and Native Image steps executed.
4. **Run the native executable and test dynamic branches:** call the HTTP endpoint, instantiate the exporter, load resources, test serialization, connect to the database, and exercise critical integrations. An app that merely starts successfully does not prove every branch is compatible.
5. **Fix by symptom:** adjust beans/configs if AOT fixed a condition unintentionally; add hints for genuinely needed dynamic access; fix the toolchain when the native compiler fails. Rebuild and rerun native after every relevant change.
6. **Compare performance fairly:** measure the same endpoint, data, CPU/RAM resources, configuration, and container limits. Separate startup time, RSS/actual memory, throughput, and warmed-up latency; also record build time and artifact size.

You can package the native executable directly into a compatible runtime container or use Cloud Native Buildpacks. For example, with proper Maven/Spring Boot configuration and Docker/Buildpacks ready:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Buildpacks is a **container-based packaging and build path**; it does not alter the essence of Spring AOT or Native Image. In this build approach, the native toolchain can be provided inside the builder image rather than needing a full local installation. Verify the architecture of both the builder and runtime images when deploying.

## 8. Self-Check

Use these three questions to pinpoint where responsibility lies:

- **Who understands `@Bean`, `@Conditional`, and can generate bean registration code?** Spring AOT.
- **Who analyzes reachable code and produces an executable requiring no JVM at runtime?** GraalVM Native Image.
- **Who provides goals/tasks like `native:compile` or `nativeCompile` in the Maven/Gradle workflow?** Native Build Tools, working with the Spring Boot plugin.

When troubleshooting, trace in order: **build-time Spring configuration → AOT code/hints → Native Image analysis and compilation → actual executable behavior**. Dividing responsibilities this way helps isolate the root cause, avoiding random tweaks to Spring config, native arguments, and containers all at once.
