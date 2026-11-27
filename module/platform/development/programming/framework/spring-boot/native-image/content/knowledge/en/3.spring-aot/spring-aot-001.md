# Why Does Spring Need Ahead-of-Time Processing Before Compiling to a Native Image?

## 1. The Core Problem: Spring Is Flexible at Runtime, Native Image Needs Many Things Known Upfront

The goal of **SPRING_BOOT_NATIVE_IMAGE** is to compile a Spring Boot application into a GraalVM Native Image using **Spring AOT (Ahead-of-Time)**, and then evaluate startup speed, memory consumption, compatibility, Maven/Gradle build workflows, and packaging and operations. To achieve this, we first need to answer a fundamental question: **Why not pass a Spring Boot JAR directly into GraalVM Native Image for compilation?**

On the JVM, Spring can discover and assemble an application very flexibly at startup. For example, Spring Boot commonly relies on:

- **Classpath scanning** to find classes annotated with `@Component`, `@Service`, `@Repository`, `@Controller`.
- **Bean definition and dependency injection** to determine which beans need to be created, choose constructors, and wire dependencies.
- **Configuration conditions** such as `@ConditionalOnClass`, `@ConditionalOnProperty`, profiles, and auto-configuration to decide the application structure.
- **Reflection** to look up constructors, fields, methods, bind properties, or interact with the framework.
- **Proxies** (JDK dynamic proxies or subclass-based proxies) to implement mechanisms such as transactions, AOP, and infrastructure capabilities.
- **Resource discovery** to read configurations, templates, schemas, or packaged data from the classpath.

For an application running on the JVM, many decisions are made when the program starts running. The JVM can load classes, read metadata, and invoke methods via reflection when needed.

**GraalVM Native Image** takes a different approach: the compiler analyzes the application under a **closed-world** model. At build time, the tool needs to identify sufficient classes, call paths, and dynamic access behaviors that will occur at runtime. It then produces a machine-code executable for a specific operating system and architecture. It cannot assume there is a full JVM classloader available to discover arbitrary new classes in the future.

Therefore, a Spring Boot application may run normally on the JVM yet fail when building or running natively: **operations that the JVM can discover at runtime might not be recognized by the static analyzer and included in the executable**.

### Small Example: Access Patterns Not Obvious from Source Code

~~~java
String className = environment.getProperty("app.report.formatter");
Class<?> formatterClass = Class.forName(className);
Object formatter = formatterClass.getDeclaredConstructor().newInstance();
~~~

The class name is retrieved from configuration. Looking solely at bytecode, Native Image cannot necessarily deduce the class, constructor, or elements that must be retained. On the JVM, this can succeed as long as the class is on the classpath; with a native executable, reflective access may require **reachability metadata** to be registered in advance.

And it is not just reflection: if the program selects a template by a name in configuration, or creates a proxy for a dynamically inferred set of interfaces, the compiler may also need additional information.

## 2. Which Part of the Problem Does Spring AOT Solve?

**Spring AOT is the process by which Spring analyzes and prepares the application at build time**, shifting work that would otherwise happen at startup into pre-generated code, while also declaring the dynamic access patterns required for native compilation.

It is neither a machine-code compiler nor a container packaging tool. Spring AOT understands *Spring semantics*; GraalVM Native Image understands bytecode and reachability; Native Build Tools integrates the native build process into Maven/Gradle.

| Question | What does Spring AOT contribute? | What does GraalVM Native Image do next? |
| --- | --- | --- |
| Which beans exist in the application? | Processes configuration/bean definitions and generates corresponding bootstrap code | Analyzes the bootstrap code and reachable branches that can be invoked |
| Need to invoke constructors/methods via reflection? | Spring and libraries provide runtime hints; the application can supply additional hints | Retains the declared accessibility inside the image |
| Need JDK dynamic proxies/resources/serialization? | Provides metadata for known cases | Uses the metadata during compilation and packaging |
| How is a native executable created? | Prepares code and metadata | Compiles machine code for the target environment |
| What brings these steps into Maven/Gradle? | The Spring Boot build plugin integrates the AOT steps | Native Build Tools invokes and configures the compiler |

Technically, ahead-of-time processing can leverage extension points such as `BeanFactoryInitializationAotProcessor` and `BeanRegistrationAotProcessor` to contribute initialization code for the corresponding infrastructure/beans. From an application developer's perspective, you do not necessarily have to use these APIs directly: Spring Framework, Spring Boot, and many integrated libraries already provide handling for common cases.

### Conceptual Processing Pipeline

~~~mermaid
flowchart TB
    S["Application code + dependencies + build configuration"] --> A["Spring AOT analyzes bean definitions and Spring configuration"]
    A --> G["Generated Java code for bean initialization / registration"]
    A --> H["Required runtime hints and metadata"]
    G --> C["Compile application bytecode and AOT code"]
    H --> N["GraalVM Native Image"]
    C --> N
    N --> E["Native executable for target OS / architecture"]
    B["Maven / Gradle + Spring Boot plugin + Native Build Tools"] -. "orchestrates" .-> A
    B -. "orchestrates" .-> N
~~~

The diagram illustrates the logical relationships; task order and generated code directories may vary across build systems and plugin versions. The AOT output consists of **source/compiled code and metadata to be used in the next step**, not the native executable itself.

## 3. What Spring AOT Can Know Ahead of Time

### 3.1. Generating Code for Bean Registration and ApplicationContext Initialization

A simple application:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {
    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}
~~~

In traditional JVM execution, Spring needs to process the configuration, construct bean definitions, resolve dependencies, and prepare bean creation logic. During the AOT phase, Spring can analyze this information and **generate Java code that performs the pre-determined bootstrap/bean registration work**.

The generated code can contain logic equivalent to registering beans and invoking factory methods. Avoid assuming that **Spring AOT pre-instantiates all bean instances at build time**. Beans are still created when the application starts according to the appropriate lifecycle; the difference is that part of the discovery and setup work has been prepared early.

Consequence: when the native executable starts running, Spring typically has less configuration analysis work to perform, helping improve startup time.

### 3.2. Determining Which Configurations Form the Bean Graph

In Spring Boot, auto-configuration and conditional annotations determine whether a bean is present. For example:

~~~java
@Configuration(proxyBeanMethods = false)
class AuditConfiguration {
    @Bean
    @ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

When the AOT process evaluates conditions affecting the bean graph, the decision can be **fixed according to the environment/configuration at build time**. If you build the native image with `app.audit.enabled=false`, you should not assume that simply changing it to `true` when running the executable will make Spring re-detect the configuration, create the new bean, and rebuild the entire bean graph.

This must be distinguished from **ordinary property values read at runtime**, such as service URLs, timeouts, or credentials. Not every application property is frozen; the notable risk lies in **values that decide which beans are registered or how the application structure is generated**.

Therefore, when an application has multiple profiles or feature flags that alter the bean graph, you must check whether they are evaluated during AOT processing. If you need to distribute a single binary across multiple environments, design it so that runtime variations reside in configuration values and appropriate runtime logic, rather than relying on re-scanning and redefining beans after build.

### 3.3. Generating and Aggregating Information for Dynamic Access

GraalVM can analyze explicit static calls very well:

~~~java
ReportService service = new ReportService();
service.generate();
~~~

However, for reflection, proxies, and resources looked up by dynamic names, metadata is required. Spring AOT and related integrations can contribute information about:

| Access Type | Common Example | Information to Prepare |
| --- | --- | --- |
| Reflection | Instantiating objects via `Class.forName`, invoking constructors/methods dynamically | Classes and members permitted for reflective access |
| JDK proxy | Proxy for a specific set of interfaces | List of interfaces for the proxy |
| Resource | Reading templates, schemas, or files on the classpath | Resources or patterns to include in the image |
| Serialization | Framework accessing types used in serialization/deserialization | Metadata suitable for the serialization mechanism |
| Proxy/subclass used by Spring | AOP, certain infrastructure bean types | Pre-generated code/metadata or required configuration for the specific proxy mechanism |

Not every dynamic access case requires manually writing hints. Many Spring components already have built-in support. The application's responsibility is to **precisely supplement cases not yet described by the framework or dependencies**.

## 4. How Failures Manifest When Ahead-of-Time Processing Is Missing

An application can build natively with success, open an HTTP port, and serve a simple endpoint, yet still fail when a user executes a less frequently exercised flow. For example, a report export feature:

1. The user sends a request to export data in a selected format.
2. The program reads the implementation class name from configuration and instantiates the object via reflection.
3. The native executable lacks sufficient metadata for the constructor that needs to be invoked.
4. The report export flow fails even though the build succeeded and the health endpoint remains green.

That is why **a successful build does not prove the application is native-compatible**. Tests must exercise critical dynamic behaviors: binding/serialization, database connections, transaction proxies, resource access, configuration conditions, and integrated libraries.

If an application genuinely uses a class by dynamic name, you can register runtime hints in Spring:

~~~java
package com.example.report;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ReportRuntimeHints.class)
class ReportConfiguration {
}

class ReportRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CsvReportFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("report-templates/*.txt");
    }
}

class CsvReportFormatter {
    public CsvReportFormatter() {}
}
~~~

This example assumes `CsvReportFormatter` is an actual implementation included in the build, instantiated via reflection from a name retrieved from configuration, and a file such as `src/main/resources/report-templates/default.txt` is read at runtime. `@ImportRuntimeHints` instructs Spring to include information from the registrar in the AOT process. When invoking a constructor via reflection, Native Image needs to know it must preserve the ability to call that constructor; for resources, it needs to know which files/patterns should be packaged.

**Do not treat hints as an automatic fix for every error.** They do not enable loading an arbitrary JAR newly copied into a directory after compilation, nor do they automatically declare every method/field of a class. `MemberCategory.INVOKE_DECLARED_CONSTRUCTORS` describes the constructor requirement; if methods are invoked via reflection, metadata for the corresponding methods must be considered. Adding excessive hints can bloat image size and mask unnecessary dynamic dependencies.

## 5. AOT Limitations That Require Intentional Application Design

Spring AOT works best when the application structure can be determined at build time. Pay special attention to approaches that alter Spring's structure after the ahead-of-time processing phase:

- **Registering beans via unpredictable runtime logic**: if beans are added based on inputs only available at runtime, AOT code may not be able to prepare all corresponding bean creation paths.
- **Custom classpath scanning or loading plugin JARs added after build**: a native image lacks the capability to arbitrarily discover and load new classes like a full JVM environment.
- **Custom reflection/proxy/resource usage**: if Spring or a library does not provide metadata, the application must declare it.
- **Changing profiles/conditions between build and runtime**: this can cause the configuration fixed in AOT code to differ from runtime expectations.
- **Libraries using code generation or runtime bytecode manipulation**: verify whether the mechanism is native-compatible or requires a build-time alternative.

Not every `BeanFactoryPostProcessor`, `BeanPostProcessor`, or proxy is forbidden. The issue is **when they execute, what they produce, and whether Spring AOT can predict that outcome**. Even within Spring applications, a framework mechanism with built-in AOT support carries vastly different risk compared to a custom mechanism manipulating the classpath at runtime.

Illustrative distinctions:

| Case | Usually AOT-friendly | Needs further review |
| --- | --- | --- |
| Beans declared with `@Bean` and fixed dependencies | Yes | If conditions depend on runtime state that AOT decides at build time |
| `@ConfigurationProperties` for host, port, timeout | Usually yes | If values are used to register different beans at build time |
| Reflection on a predefined set of classes | Usually yes | Ensure runtime hints are complete |
| Loading arbitrary class names from a new plugin directory at runtime | Difficult to fit closed-world model | Needs extensibility redesign |
| Templates in `src/main/resources` | Usually yes | Verify whether resources are packaged into the native image |

## 6. Benefits and Costs: "Do Work Early" to "Start Fast"

When part of Spring's processing is moved from runtime to build time, the application can reduce configuration analysis, scanning, and metadata preparation steps at startup. Combined with a native executable, the commonly sought benefits are:

- **Startup time**: useful for short-lived tasks, deployments requiring rapid scaling, serverless workloads, or environments with frequent instance initialization.
- **Memory usage**: some workloads may show lower RSS compared to running the equivalent application on the JVM, though the reduction depends on GC, dependencies, environment, and load.
- **Deployment**: an executable can be distributed for the target platform without installing a JVM at the runtime destination, provided required native/OS dependencies are met.

In return, **native builds** typically take significantly more time, CPU, and RAM than building a JVM JAR; debugging and build-toolchain setups are more complex; and libraries relying on dynamic behavior may need adjustments or additional metadata. Long-running application performance, latency, and throughput can also differ from a JVM with JIT. There is no guarantee that a native build will always be faster or more memory-efficient in every scenario.

Reliable measurement requires:

1. Using the same application, data, and enabled features.
2. Comparing on equivalent CPU/RAM/container environments.
3. Distinguishing **startup time**, **time to readiness**, **RSS**, **latency**, **throughput**, **build time**, and **artifact size**.
4. Running repeated iterations, filtering out system noise, and recording exact JDK/GraalVM/Spring Boot/plugin versions and configurations.

Evaluating AOT effectiveness cannot stop at seeing the `native-image` command succeed; you must observe the application running real business workflows.

## 7. Observing Spring AOT in Maven/Gradle

To see what Spring does before Native Image runs, you can explicitly execute the AOT step separately and inspect the generated code. For example, in a Spring Boot project with the plugin properly configured:

**Maven:**

~~~bash
./mvnw spring-boot:process-aot
~~~

**Gradle:**

~~~bash
./gradlew processAot
~~~

Depending on the build system and version, generated AOT source files and metadata typically appear under generated directories in `target/` (Maven) or `build/` (Gradle). These are **build-generated artifacts**, not source files to edit by hand. Re-running the build may overwrite them.

Once you have ensured the JDK/GraalVM includes the `native-image` tool, native compiler, and compatible plugins, you can run the full compilation:

~~~bash
# Maven: applies when the project has an appropriate native profile/configuration
./mvnw -Pnative native:compile

# Gradle: applies when Spring Boot and Native Build Tools are integrated
./gradlew nativeCompile
~~~

In projects using the Spring Boot Maven parent, the `native` profile is typically preconfigured by convention; projects managing their own Maven lifecycle require equivalent configuration. Gradle requires compatible Spring Boot and `org.graalvm.buildtools.native` plugins. Native Build Tools is responsible for integrating the native compiler, while the `process-aot`/`processAot` step comes from Spring Boot's build mechanism.

The purpose of running the AOT step separately is to see **how the application structure has been decided and described upfront**, allowing you to check discrepancies between build configuration and runtime expectations. After modifying code or config, rebuild to update the AOT code; do not manually edit code inside generated directories.

## 8. Diagnosing When JVM Works but Native Fails

| Symptom | Where to check first | Appropriate remediation |
| --- | --- | --- |
| Bean missing, `NoSuchBeanDefinitionException` | Profiles, conditions, or configurations affecting the bean graph during AOT | Verify the build environment; redesign runtime variations if needed |
| Error accessing constructor/method via reflection | Runtime hints and dynamic invocation mechanisms | Register the right class/members; check whether the library already provides hints |
| Error finding template/schema files | Resource hints and packaged resources | Register the proper resource/pattern, verify the file exists on the build classpath |
| Proxy/AOP or serialization library fails in a branch | AOT integration and library metadata | Check native support, configure proxy/serialization appropriately |
| Native compilation cannot find `native-image` executable | Native Build Tools and toolchain | Install/configure GraalVM and the corresponding system tools |
| Native build runs out of RAM | Resources allocated to the Native Image phase | Adjust build machine resources, flags, and dependency scope; do not confuse with runtime RAM |
| Binary fails to run on target server/container | OS/CPU architecture, linker, runtime libraries | Build for the right platform or use a compatible builder/runtime image |

A short diagnostic workflow:

1. Run JVM tests to confirm baseline functionality.
2. Run the AOT step, inspect logs and generated code; verify expected profiles, conditions, and beans.
3. Run the native build, classifying any failure under AOT, compiler, or linker.
4. Run the native executable and test flows involving reflection/resources/proxies/serialization.
5. Fix the root cause at the right layer: Spring config, runtime hints, dependencies, or toolchain. Rebuild and verify with corresponding tests.

**Avoid concluding "AOT has handled everything" just because the native image starts up.** AOT helps Spring prepare what can be known in advance, but it cannot automatically know every dynamic behavior produced later by application code or libraries.

## 9. Remembering the Core Nature of Spring AOT

Three takeaways explain *why* Spring needs ahead-of-time processing:

1. **Spring on the JVM relies heavily on runtime discovery and configuration**, whereas GraalVM Native Image requires a sufficiently clear picture of executable code and dynamic access metadata at build time.
2. **Spring AOT shifts the predictable portion of Spring bootstrap to build time**, generating bean registration/initialization code and supplying the metadata Native Image needs; it is not merely flipping an optimization flag for the JVM.
3. **Moving work to build time introduces new boundaries for configuration and extensibility.** Understanding these boundaries helps you know where to add hints, write compatibility tests, design configuration, and realistically evaluate startup time and memory benefits.

When reading build logs and observing application behavior, you can trace the chain: **Spring configuration/bean graph → Spring AOT generated code + hints → GraalVM reachability analysis → native executable → runtime testing**. This causal chain explains both the benefits and the constraints of Spring Boot Native Image.
