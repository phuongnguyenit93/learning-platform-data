# AOT, Runtime Hints, and Native Image at a Conceptual Level

Traditional Spring Boot applications typically run on the JVM. At startup, the JVM loads classes, instantiates objects, parses configuration, and uses mechanisms such as reflection or proxies to assemble the Spring ApplicationContext. The JVM can also optimize code at runtime using the Just-In-Time compiler (JIT).

For applications that need fast startup, low memory usage, or run in short-lived environments, the startup sequence and runtime overhead of the traditional model can become factors worth optimizing. Spring Framework 6 and Spring Boot 3 bring **Ahead-of-Time processing (AOT)** into the build pipeline to analyze the application earlier, generate initialization code, and supply metadata required by runtime environments with restricted dynamic discovery.

When combining AOT with **GraalVM Native Image**, a Java application can be compiled into a native executable targeting a specific operating system and CPU architecture. The result often starts faster and has a lower memory footprint across many workloads, though builds are more complex and certain dynamic Java features must be declared explicitly.

Three concepts need to be distinguished:

- **AOT processing**: analyzes the application at build time and generates sources, resources, and hints to reduce dynamic work at startup.
- **Runtime hints**: metadata describing runtime operations such as reflection, resource access, serialization, or proxy creation that the native compiler needs to know in advance.
- **Native image**: an executable produced from the application and its dependencies by the native-image compiler, capable of running directly on the target platform without requiring a separately installed JVM as in traditional JAR execution.

AOT and native image are related, but they are not the same concept. An AOT-generated application can still run on the JVM; a native image is a different packaging/runtime target that consumes the AOT output.

## 1. From Traditional JVM to AOT and Native Image

A typical Spring Boot application is packaged as an executable JAR:

~~~text
demo-app.jar
├── application classes
├── application resources
├── Spring libraries
├── third-party dependencies
└── Spring Boot loader
~~~

When running:

~~~bash
java -jar demo-app.jar
~~~

The JVM starts up, loads classes, builds the Spring context, and handles requests. During execution, the JIT compiler can optimize frequently executed code paths based on runtime profiling.

Native image follows a different flow. The native compiler analyzes reachable classes/methods, metadata, and runtime hints at build time to produce an executable:

~~~text
Source + dependencies
        |
        v
Spring AOT processing
        |
        +--> Generated Java sources
        +--> Generated resources
        +--> Runtime hints
        |
        v
Native Image compiler
        |
        v
Platform-specific executable
~~~

We can compare them:

| Criterion | Running JAR on JVM | Running Native Image |
| --- | --- | --- |
| Primary artifact | JAR containing bytecode and dependencies | Native executable per OS/CPU |
| Runtime | Requires a compatible JVM | Does not require a separate JVM as in JAR execution |
| Compilation | Java source to bytecode; JIT optimizes at runtime | Native compiler emits machine code at build time |
| Startup | Both JVM and application initialize | Typically significantly faster |
| Memory | Includes JVM runtime and an appropriate heap | Typically lower footprint in many workloads |
| Throughput optimization | JIT can optimize for real runtime behavior | No equivalent JIT profiling in traditional runtime |
| Reflection/dynamic loading | Many capabilities work flexibly | Needs metadata/hints for cases not statically analyzable |
| Build | Typically faster and simpler | Typically slower, needs native toolchain and more resources |
| Portability | One JAR can run on multiple OSes with a compatible JVM | Binary is tied to the build target platform |
| Debugging/diagnostics | Mature JVM ecosystem | Some tools and behaviors differ |

There is no single best choice for every application. Choose based on workload, startup time, memory, scaling behavior, dependency complexity, and build/release cost.

## 2. What Does AOT Processing Do?

Spring needs to know which beans will be created, which configurations apply, how dependencies are wired, and which proxies are required. In the traditional runtime model, part of this work happens dynamically when the application starts.

AOT processing shifts part of that work to build time. Spring analyzes application configuration in a defined build environment and generates artifacts that assist context initialization.

Conceptually, the pipeline includes:

1. The build tool prepares main classes, resources, and dependencies.
2. Spring AOT initializes/evaluates the application context during the build.
3. The framework analyzes bean definitions and related configurations.
4. The framework generates Java code and resources representing the analyzed initialization logic.
5. Runtime hints are collected to describe required dynamic capabilities.
6. The AOT outputs are used when running the application on the JVM or passed as input to native-image compilation.

~~~mermaid
flowchart TD
    A["Java source + application config"] --> B["Compile main classes"]
    B --> C["Spring AOT processing"]
    C --> D["Analyze bean/configuration graph"]
    C --> E["Collect RuntimeHints"]
    D --> F["Generated initialization code"]
    E --> G["Reflection/resource/proxy metadata"]
    F --> H["AOT-processed application"]
    G --> H
    H --> I["Run on JVM"]
    H --> J["Native Image compilation"]
    J --> K["Native executable"]
~~~

AOT is not simply running `javac` earlier. It understands part of the Spring application's structure in order to generate optimized initialization logic and runtime metadata.

### 2.1. Work That Can Be Performed Ahead of Time

Depending on the application and framework integrations, AOT can pre-process:

- Analyzing bean definitions and the dependency graph.
- Evaluating configuration classes and auto-configuration conditions.
- Generating bean registration/initialization code.
- Generating or describing required proxies.
- Preparing reflection access metadata.
- Recording resources that must be included in a native image.
- Preparing metadata for serialization and supported dynamic features.

Some operations still occur at runtime, such as instantiating bean instances, connecting to databases, binding server sockets, reading requests, or executing business logic. AOT reduces discoverable setup work that can be known ahead of time; it does not turn an application into a runtime-free program.

### 2.2. AOT Does Not Replace the Java Compiler

Java source still must be compiled. AOT processing uses prepared application classes and dependencies to analyze Spring configuration and generate additional sources/resources. If the source fails to compile, AOT cannot turn it into a valid application.

The stages remain related:

~~~text
Java compile
    |
    v
Spring AOT processing
    |
    v
Compile generated AOT sources
    |
    v
JVM execution or native-image compilation
~~~

The build tool integrates these tasks into a task graph; exact ordering depends on plugins and project configuration.

## 3. AOT Can Be Used Without Native Image

This is a common point of confusion: **AOT processing does not require the application to become a native executable**.

An application can produce generated AOT code and continue running on the JVM. In that setup:

- The artifact still runs inside the JVM.
- Pre-generated initialization code can reduce some startup setup work.
- Libraries and runtime features still need to be compatible with how the application was AOT-processed.
- You do not need the native-image compiler just to understand or experiment with AOT processing on the JVM.

Native image uses AOT outputs along with hints to build a native executable. Thus, the pipeline generally has two output paths:

~~~text
                     +--> AOT application running on the JVM
Spring AOT output ---|
                     +--> Native Image compiler --> Native executable
~~~

### 3.1. When Is AOT on the JVM Useful?

Consider it when you want to:

- Measure AOT's impact without changing the runtime deployment model yet.
- Discover dynamic features that are not yet native-image compatible.
- Inspect generated initialization code.
- Incrementally prepare an application for native compilation.
- Keep JAR/JVM operations while evaluating benefits.

AOT on the JVM does not automatically guarantee startup improvements comparable to a native image. Benchmark with the same application, same data, and same environment.

### 3.2. Native Image Is a Subsequent Step, Not Another Name for AOT

AOT processing produces build-time information. The Native Image compiler uses that information to produce an executable. If a build only runs the AOT task and packages a JAR, you may still be shipping a JVM application.

When reading CI logs, identify which task actually builds the native executable instead of assuming from the word “AOT” appearing in the output.

## 4. Native Image and the Closed-World Assumption

GraalVM Native Image uses reachability analysis to determine which code can be invoked from the application entry points. Reachable classes, methods, and resources are included in the image according to compiler rules and metadata.

This approach is commonly called the **closed-world assumption**: the compiler needs to be able to determine in advance what components may be used. It differs from the traditional JVM, where an application can load classes or discover methods dynamically at runtime.

Example:

~~~java
Class<?> type = Class.forName(className);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

On a traditional JVM, the class name can come from runtime configuration and the class loader can find the class if it is on the classpath. With native image, the compiler cannot always know every possible value of `className`. If the class or constructor is not identified as reachable, the code can fail when running the native executable.

### 4.1. Reachability Analysis

Native Image analyzes call relationships and metadata to find components reachable from application entry points. It can exclude unreachable code from the executable, reducing footprint.

However, indirect access paths such as reflection, dynamic proxies, resource lookups, or serialization may not be visible in a standard call graph.

### 4.2. Why Missing Metadata Causes Failures

Suppose a library reads a class name from YAML and then uses reflection to instantiate the object. The native compiler does not necessarily see that class being used directly.

Without appropriate hints/metadata, the following can happen:

- Class not found inside the native image.
- Constructor or method inaccessible.
- Proxy creation fails.
- Resource not found.
- Serialization/deserialization fails.
- A feature works on the JVM but fails inside the native executable.

Key point: these failures may surface **only after the native image builds successfully**, at runtime when execution reaches a code path lacking complete metadata declarations.

## 5. What Are Runtime Hints?

Runtime hints are declarations telling Spring AOT which runtime capabilities must be preserved or permitted when building a native image.

Spring Framework provides APIs to describe the main categories:

| Hint Category | Purpose | Example |
| --- | --- | --- |
| Reflection | Access classes/members via reflection | Constructors, fields, methods |
| Resources | Include files/resources in the image | Templates, schemas, JSON, public certificates |
| Proxies | Create proxies by interface | JDK dynamic proxy |
| Serialization | Support Java serialization for specified types | Objects needing serialize/deserialize |
| Additional native metadata | Runtime/library-specific requirements | JNI or class initialization per native toolchain config |

Runtime hints are not an encryption mechanism for secrets or a replacement for dependency management. They are technical metadata informing the compiler/runtime that certain dynamic operations must be supported.

### 5.1. Hints Do Not Create Missing Dependencies

If an application uses `com.vendor.sdk.Client` but that dependency is absent from the build, registering a reflection hint for the class cannot make the class appear.

Before adding hints, confirm:

- Is the dependency on the runtime classpath?
- Is the class/resource actually packaged?
- Which dynamic operation prevents the compiler from seeing the usage?
- Does the library already provide reachability metadata?
- Is there a Spring Framework API that declares it instead of a custom hint?

### 5.2. Register Only the Access Actually Needed

Do not open reflection for an entire package or every member just to silence a build error. Overly broad hints can increase image size and retain more code than necessary.

Register the exact classes, members, and resources the application genuinely uses.

## 6. Reflection Hints

Reflection lets code look up classes, constructors, methods, or fields at runtime. Frameworks such as JSON binding, ORM, dependency injection, validation, and mapping libraries may use reflection.

Example:

~~~java
Class<?> type = Class.forName("com.example.shop.PaymentRequest");
Constructor<?> constructor = type.getDeclaredConstructor();
Object request = constructor.newInstance();
~~~

With native image, classes and constructors accessed this way may require reflection metadata.

The Spring RuntimeHints API lets you declare:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.TypeReference;

public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                TypeReference.of(PaymentRequest.class),
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

This example only illustrates the idea of registering public constructors and public methods for a specific type. Choose member categories based on how the library actually accesses the object.

### 6.1. Attaching RuntimeHintsRegistrar to Configuration

You can import the registrar:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
public class PaymentConfiguration {
}
~~~

When Spring AOT processes the configuration, the registrar is invoked to contribute the corresponding hints.

### 6.2. @RegisterReflectionForBinding

For DTOs used in data binding/serialization scenarios supported by Spring, you can use the annotation:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;

@RegisterReflectionForBinding({
        PaymentRequest.class,
        PaymentResponse.class
})
@Configuration(proxyBeanMethods = false)
public class PaymentBindingConfiguration {
}
~~~

This annotation helps register the reflection hints required for binding the specified types. It is cleaner than manually writing numerous member hints when the goal is supporting binding through corresponding Spring integrations.

Do not assume this annotation solves every reflection library's needs. If a third-party library performs reflection in its own way, check reachability metadata or add appropriate hints.

### 6.3. Registering Specific Classes vs. Registering Every Class in a Package

If only two DTOs need binding, register those two DTOs. Do not open an entire package with a blanket reflection rule without good reason.

Precise metadata ensures the image retains only what is necessary and reduces the risk of implicit dependencies on undeclared code.

## 7. Resource Hints

Java applications can read files from the classpath:

~~~java
try (InputStream input =
        getClass().getResourceAsStream("/templates/invoice.html")) {
    // Read template.
}
~~~

On the JVM, resources can be found from the classes directory or dependency JARs. Native image needs to know which resources must be embedded in the executable.

Example of pattern registration:

~~~java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("templates/payment/*.html");
        hints.resources().registerPattern("schemas/payment/*.json");
    }
}
~~~

Patterns are evaluated against classpath resource paths. Keep the scope tight; overly broad patterns can bundle unnecessary assets into the executable.

### 7.1. A Resource Is Not a Filesystem File

A resource packaged inside a JAR/native image does not necessarily have a physical filesystem path. Code should prefer streams:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Parse resource.
}
~~~

Instead of assuming:

~~~java
File file = resource.getFile();
~~~

Reading via streams generally fits resources packaged inside archives or native images much better.

### 7.2. Resources Created at Runtime

If the application creates temporary files, downloads data from a remote endpoint, or writes files to a writable directory, that is filesystem/runtime behavior, not a static resource to bundle into the image.

Do not register a resource pattern as a substitute for configuring a runtime data storage directory.

## 8. Proxy Hints

Spring and many libraries use proxies to implement features such as:

- AOP and method interception.
- Transaction management.
- Security method interception.
- Lazy loading.
- Interface-based clients or adapters.

JDK dynamic proxies typically generate a proxy for a set of interfaces. Native image needs to know which interface proxies may be created.

Registration example:

~~~java
hints.proxies().registerJdkProxy(
        PaymentGateway.class,
        Auditable.class
);
~~~

This sits inside a `RuntimeHintsRegistrar`. The hint declares that the runtime needs the ability to create a JDK proxy implementing the specified interfaces.

### 8.1. JDK Proxies vs. Class-Based Proxies

JDK proxies implement interfaces. Class-based proxies may rely on subclass generation or another proxying mechanism. Spring AOT and native support can handle many common cases via generated code/hints, but do not assume every bytecode generation library is automatically compatible.

If a library generates classes/proxies via bytecode at runtime, check that library's native support documentation. You may need a different integration or a design change.

### 8.2. Hints Do Not Fix Proxy Design Limitations

If a method cannot be overridden under Java rules or a proxy cannot intercept self-invocation calls, adding a proxy hint does not change method call semantics. Distinguish native metadata errors from AOP/proxy limitations in the application's own design.

## 9. Serialization Hints

Some applications use Java object serialization or libraries that require type metadata when converting objects into serialized form.

Spring RuntimeHints can register types for serialization:

~~~java
hints.serialization().registerType(PaymentSnapshot.class);
~~~

This is an example of a type whose serialization metadata must be preserved in a native image.

### 9.1. JSON Binding Is Not Java Serialization

Jackson JSON binding, Spring HTTP message conversion, and Java native serialization are distinct mechanisms. Do not add a Java serialization hint merely because a DTO is returned from a REST controller.

For JSON binding, use reflection/binding hint mechanisms appropriate for Jackson and Spring integrations. Identify the actual serializer/deserializer in use.

### 9.2. Check Serialization Libraries

If an application uses an external serialization library, verify whether that library provides native support or built-in reachability metadata. Adding a hint for one class may not suffice if the library also needs constructors, fields, annotations, or other resources.

## 10. Third-Party Libraries and Reachability Metadata

Spring Boot applications rarely use only team-written code. Dependencies may internally rely on reflection, proxies, resources, JNI, or dynamic class loading.

A native-ready library may provide reachability metadata so the compiler knows what components are needed. The GraalVM ecosystem includes the Reachability Metadata Repository as well as mechanisms for shipping metadata alongside dependencies.

When adopting a new dependency, verify:

- Do the maintainers declare GraalVM Native Image support?
- Does the current dependency version have matching metadata?
- Is that metadata automatically picked up by the build tool/native toolchain?
- Is extra configuration needed for the specific feature you use?
- Does the test suite pass on a native executable?

Do not conclude a library is native-compatible simply because a JVM application uses it without issues.

### 10.1. Native Compatibility Depends on Usage

A library may work natively in case A while requiring extra hints in case B. For example, standard APIs may be statically visible to the compiler, whereas an extension system loading classes by runtime-configured names still needs additional metadata.

Verify your specific use cases rather than relying solely on a “GraalVM supported” badge.

### 10.2. Avoid Duplicating Metadata Manually

If a dependency already ships accurate reachability metadata, maintaining a second manual configuration layer can create maintenance burden. Prefer metadata owned by the library; supplement only the gaps specific to your application or custom integration.

## 11. Spring AOT and Configuration Conditions

Spring Boot can evaluate certain configuration conditions during AOT processing, for example:

- `@ConditionalOnClass`.
- `@ConditionalOnProperty`.
- `@Profile`.
- Auto-configuration conditions.
- Bean definitions and the configuration import graph.

Because part of the decision-making happens at build time, **the environment running AOT processing must align with the expected application configuration at runtime**.

For example, suppose a module is only created when:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
public class PaymentConfiguration {
}
~~~

If AOT processing runs with property values that disable the configuration, the generated application may omit that module at runtime even if you expect it later.

### 11.1. Runtime Properties vs. Build-Time Decisions

Not every property is frozen during AOT. Configuration values read normally at runtime can still vary when running. What needs attention is that values used to decide bean/configuration structure during AOT can shape the generated output.

Distinguish between:

- **Application structural configuration**: profiles/conditions deciding which beans are registered.
- **Runtime operational configuration**: URLs, timeouts, credentials, or business values read at runtime when supported by the design.
- **Native build configuration**: target platform, build options, and compiler metadata.

### 11.2. Do Not Put Production Secrets into the AOT Build

An AOT build is not the place to supply production credentials. Never bake passwords, tokens, or private keys into the image or generated artifacts.

Inject secrets from a secret manager or environment at runtime. If a property condition governs application structure at build time, use only non-sensitive configuration values under a clear build/release policy.

### 11.3. Multiple Profiles with Different Bean Graphs

If `dev` and `prod` register different implementations via `@Profile`, an AOT application generated with a single build-time profile cannot be assumed to dynamically restructure its entire bean graph for any runtime profile.

You may need separate AOT/native artifacts per structural configuration, or design variations using runtime properties/strategies supported by AOT. Verify the behavior for your exact Boot version and build setup.

## 12. Java Features Requiring Attention When Moving to Native

Native Image does not always support every dynamic operation identically to the JVM. Areas to review:

| Feature | Risk | Approach |
| --- | --- | --- |
| Reflection | Classes/members lack metadata declarations | Spring RuntimeHints or dependency metadata |
| Dynamic class loading | Class names known only at runtime | Reduce dynamic loading or supply metadata/build-time registration |
| Resource lookup | Files omitted from the image | Register resource patterns |
| JDK dynamic proxy | Interface proxy unrecognized | Register proxy hints |
| Runtime bytecode generation | New classes generated while running | Use AOT-supported integrations or redesign |
| Java serialization | Type/member metadata missing | Serialization hints and native testing |
| JNI | Native library or symbol unconfigured | Check GraalVM/native metadata and platform libraries |
| Class initialization | Static state initialized at the wrong time | Review build-time vs. runtime initialization |
| ServiceLoader | Providers not discovered | Verify service metadata and resource inclusion |
| Scripting/plug-in systems | Dynamic external code loading | Identify limits; may not fit native image |

### 12.1. Dynamic Class Loading

If an application lets an administrator enter an arbitrary class name to load a plugin, native image's closed-world model struggles. A native executable cannot inherently include every class unknown at build time.

An alternative is selecting from a known set of implementations and registering them explicitly:

~~~java
Map<String, PaymentProvider> providers = Map.of(
        "card", new CardPaymentProvider(),
        "bank", new BankPaymentProvider()
);
~~~

This makes usage explicit and statically analyzable. If loading arbitrary code after deployment is truly required, the JVM may be the better fit.

### 12.2. Runtime Bytecode Generation

Some libraries generate new subclasses or bytecode at runtime. Native Image generally requires that code to be generated ahead of time or handled via a supported mechanism.

Spring AOT can pre-generate certain proxies/initialization artifacts that the framework knows how to handle. However, it cannot automatically make every runtime bytecode-generation library native-compatible.

### 12.3. ServiceLoader

A library may locate providers via `ServiceLoader`. Verify that provider metadata and resources are properly packaged in the native image. If providers are discovered dynamically from the classpath without static compiler visibility, hints/metadata supported by the library may be needed.

## 13. Static Initialization and Build-Time Initialization

Java classes can execute work inside static initializers:

~~~java
public class RuntimeSettings {

    static final String REGION =
            System.getenv("APP_REGION");

    static final Instant STARTED_AT = Instant.now();
}
~~~

In a native image environment, certain classes may be initialized at build time according to compiler rules or configuration. If a static initializer reads an environment variable, current time, file, or network resource, those values risk capturing the build environment instead of the runtime environment.

### 13.1. Avoid Side Effects in Static Initializers

Do not use static initialization to:

- Connect to a database or network.
- Read runtime credentials.
- Write files.
- Capture timestamps meant to reflect application startup.
- Read environment variables that differ between build and deployment.
- Create environment-dependent global mutable state.

Move such work into bean initialization or an appropriate runtime lifecycle hook.

### 13.2. Build-Time Init vs. Runtime Init

GraalVM provides options to control when class initialization occurs. This is a native compiler configuration and should be used intentionally, because shifting initialization to build time can freeze state or trigger side effects prematurely.

Do not arbitrarily mark an entire third-party package as build-time initialized just to get native compilation to succeed. Consult library documentation and inspect compiler diagnostic output.

## 14. From Which Version Does Spring Boot Support AOT?

Spring Boot 3 is built on Spring Framework 6 and integrates AOT/native-image support as part of the core platform. With Spring Boot 3, you no longer rely on the older experimental Spring Native project as a separate standalone plugin for the current model.

Conceptually:

- Spring Framework provides the AOT infrastructure and RuntimeHints API.
- Spring Boot integrates AOT processing into build plugins and application bootstrap.
- The GraalVM Native Image compiler builds the native executable.
- GraalVM Native Build Tools or buildpacks can orchestrate native compilation.
- Dependencies/libraries can ship their own reachability metadata.

Always consult documentation matching the exact Spring Boot and GraalVM versions you run. Native build toolchains, plugin compatibility, and metadata formats can change across versions.

## 15. Building AOT/Native with Gradle

In a Spring Boot Gradle project, the Spring Boot plugin integrates with AOT processing. When adding a compatible GraalVM Native Build Tools plugin, the build gains native compilation tasks.

Conceptual build structure example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.x'
    id 'io.spring.dependency-management' version '1.1.x'
    id 'org.graalvm.buildtools.native' version '0.10.x'
}
~~~

Versions shown here only illustrate plugin lines; use versions verified compatible with your project's JDK, Spring Boot, and GraalVM versions.

### 15.1. Running AOT Processing

~~~bash
./gradlew processAot
~~~

This task runs Spring AOT processing and generates sources/resources for the application. Exact output directories depend on the Gradle plugin/version, typically located under the project's `build/generated` or build output folder.

Successful AOT processing does not mean a native executable has been built.

### 15.2. Native Compile

~~~bash
./gradlew nativeCompile
~~~

This task requires a compatible native toolchain, usually GraalVM Native Image or an appropriately configured build environment. The Spring Boot Gradle plugin can wire AOT processing into the task graph when the Native Build Tools plugin is applied.

The result is a native executable built for the build environment's OS/architecture.

### 15.3. Building an Image with Buildpacks

The Spring Boot Gradle plugin provides the `bootBuildImage` task to create an OCI image through Cloud Native Buildpacks when the project is configured accordingly.

A buildpack can produce either a JVM image or a native image depending on the builder, environment, and configuration. Do not assume every `bootBuildImage` run creates a native image; check buildpack configuration and build logs.

### 15.4. Inspecting the Task Graph

You can list related tasks:

~~~bash
./gradlew tasks --all
~~~

Or:

~~~bash
./gradlew nativeCompile --dry-run
~~~

`--dry-run` lets you inspect the task graph without executing the actual build. This helps clarify task dependencies before running a time-consuming native compilation.

## 16. Building AOT/Native with Maven

The Spring Boot Maven Plugin provides AOT goals. For projects using the Spring Boot parent and a conventionally configured native profile, a common command is:

~~~bash
mvn -Pnative native:compile
~~~

The flow typically involves:

1. Maven prepares project classes and dependencies.
2. Spring Boot Maven Plugin runs AOT processing.
3. Generated sources are compiled.
4. Native Build Tools invokes the GraalVM Native Image compiler.
5. The native executable is produced in the plugin-configured output directory.

You can run the AOT goal directly in a configured project:

~~~bash
mvn spring-boot:process-aot
~~~

Goal names and execution wiring depend on the Spring Boot Maven Plugin version. Inspect the POM/effective POM if a task is unrecognized or does not run in the expected phase.

### 16.1. The Native Profile Does Not Auto-Install All Tools

The Maven profile normally configures plugins and dependencies needed for a native build. The machine or CI runner still needs a compatible native toolchain or a supported build environment.

If the `native-image` executable is missing, the build can fail even though Java compilation and AOT processing succeeded.

### 16.2. Building Images via Buildpacks

The Spring Boot Maven Plugin can build OCI images via buildpacks. A native image requires a supporting builder/configuration and may require specific environment variables or buildpack options.

Read the output to verify whether the buildpack created a JVM image or a native executable image. Do not judge solely by the Docker image name.

## 17. Native Compilation Is Typically Heavier Than JVM Builds

The Native Image compiler must perform reachability analysis and emit machine code across a large codebase. Compared to standard Java compilation, the process can:

- Take several minutes or longer depending on project size.
- Consume significant CPU and RAM.
- Be sensitive to GraalVM/Native Build Tools versions.
- Take longer as the dependency graph grows.
- Be harder to cache than routine Java compilation tasks.

This affects CI/CD: native builds may need runners with higher RAM/CPU and appropriate timeouts.

### 17.1. Separating Native Build Jobs in CI

A pipeline can separate:

- JVM compile/unit test job.
- AOT/native compile job.
- Native smoke/integration test job.
- Artifact/container image publish job.

If native builds only run on release branches, ensure dependency or runtime hint changes are still verified early enough so native issues are not discovered at the last minute.

### 17.2. Caching and Reproducibility

Native builds depend on toolchain, OS, architecture, and metadata. When caching, ensure cache keys reflect critical inputs such as JDK/GraalVM version, plugins, dependencies, build configuration, and target platform.

Never reuse a native executable built for one OS/architecture on a different target just because the source revision matches.

## 18. Running the Native Executable

Once native compilation succeeds, the build output contains the executable. Its name and path depend on your Gradle/Maven configuration.

Illustrative example:

~~~bash
./build/native/nativeCompile/demo-app
~~~

On Windows, the executable file may carry an appropriate extension such as `.exe` depending on toolchain/platform.

Run the executable:

~~~bash
./demo-app
~~~

It starts the application without invoking `java -jar`. However, the application still needs external dependencies such as databases, message brokers, secret sources, networking, and runtime configuration.

### 18.1. Binaries Are Platform-Specific

A native executable is built for a specific operating system and architecture. A Linux x86_64 binary will not run natively on Windows or ARM64.

Build artifacts for the exact target environment or use a buildpack/container builder supporting that target.

### 18.2. System Libraries and libc

The executable may depend on native libraries or the ABI of the target system. Container base images and runtime OSes must be compatible. Building on one distribution and running inside an ultra-minimal image can fail with missing shared libraries.

Buildpacks standardize part of the image environment, yet you still must test the actual runtime image.

## 19. Testing AOT and Native Image Applications

An application that works on the JVM is not guaranteed to work in a native image. Tests must cover both normal behavior and code paths using reflection, resources, or proxies.

### 19.1. JVM Unit Tests Remain Necessary

Isolated logic unit tests usually continue running quickly and conveniently on the JVM. There is no need to turn every unit test into a native test.

~~~java
@Test
void calculatesDiscount() {
    assertThat(calculator.discount(1_000, 10))
            .isEqualTo(900);
}
~~~

These tests verify business logic, though they do not catch all native metadata issues.

### 19.2. Testing Spring AOT Processing

AOT processing can surface issues while analyzing configuration or generating code. Include AOT tasks in CI at an appropriate stage, especially when the application uses many conditional configurations and custom runtime hints.

### 19.3. Testing the Native Executable

Scenarios that should run natively:

- Jackson DTO deserialization.
- Reflection-based mappers.
- Validation annotations.
- JDK proxies/AOP.
- Resource loading.
- Serialization.
- ServiceLoader or plugin registration.
- Database drivers and messaging clients.
- Startup/shutdown lifecycle.
- Security configuration and filter chains.

If you only run JVM unit tests, you have not verified differences caused by closed-world analysis.

### 19.4. Native Tests

GraalVM Native Build Tools supports native build/test flows depending on plugin and version. In Gradle, a project can expose native test tasks when the plugin and test configuration are set up. In Maven, matching native test goals can be configured.

Task/goal names and support conditions vary across plugin versions. Check the task list and documentation rather than assuming every project shares identical task names.

## 20. Testing RuntimeHints Programmatically

Spring Framework provides test utilities to verify runtime hints. A test can instantiate a registry, invoke a registrar, and assert that required hints were registered.

Conceptual example:

~~~java
class PaymentRuntimeHintsTests {

    @Test
    void registersPaymentRequestReflection() {
        RuntimeHints hints = new RuntimeHints();

        new PaymentRuntimeHints().registerHints(
                hints,
                getClass().getClassLoader()
        );

        RuntimeHintsPredicates.reflection()
                .onType(PaymentRequest.class)
                .test(hints);
    }
}
~~~

Exact utility and predicate names must match the project's Spring Framework version. The example shows the test's goal: confirming a hint is registered, not proving by itself that the native executable works.

### 20.1. Hint Registration Tests Are Not Enough

A test verifying that the registry contains a hint does not prove:

- That the native compiler picked up the metadata.
- That resources actually reside in the image.
- That third-party libraries need no additional hints.
- That production code paths executed properly.
- That the binary runs on the target OS.

You still need native builds and runtime tests on risky paths.

## 21. AOT/Native and Spring Testing

A Spring test context may use different configuration and bean graphs than the production application. Some test framework integrations require dedicated AOT processing to generate matching context initializers.

Gradle/Maven can provide tasks/goals for AOT testing, but never assume running regular `test` executes native tests.

Determine:

- Which unit tests only need the JVM.
- Which integration tests need Spring AOT test processing.
- Which tests must run on the native executable.
- Which tests require real databases/containers.
- Which tests require a specific target OS/architecture.

A well-structured test suite combines fast JVM tests with a focused set of native tests targeting critical dynamic features.

## 22. Native Image Limitations in Application Design

Native image fits best when the application graph and runtime capabilities can be clearly described at build time. Some highly dynamic designs may need adjustment.

### 22.1. Post-Deployment Plugin Loading Systems

If an application lets users drop a new plugin JAR into a directory and dynamically load classes without rebuilding, the closed-world model causes friction. A native executable cannot arbitrarily load new bytecode like a traditional JVM process with a dynamic classpath/plugin loader.

Options include:

- Making plugins known modules compiled into the image.
- Calling an external service to provide the functionality.
- Using a JVM runtime for components requiring dynamic loading.
- Isolating the plugin host into a separate process.

### 22.2. Unbounded Configuration-Driven Reflection

If configuration can specify arbitrary class names and the application uses reflection to instantiate them, registering every possible class may be impractical. Consider a registry/allowlist of known implementations.

### 22.3. Runtime-Generated Bytecode

Libraries generating classes with ASM, Byte Buddy, or similar tools need appropriate AOT/native support. Some Spring use cases are handled through generated code, but not every runtime generator is transformed by the framework.

### 22.4. Scripting Engines and Dynamic Languages

Systems running arbitrary scripts or loading interpreters/runtimes dynamically may be a poor fit for native image or require complex configuration. Evaluate the workload before committing.

### 22.5. Native Libraries and JNI

If a dependency invokes native code, confirm the shared library is present on the target, architecture matches, and JNI/native metadata is configured. A passing JVM build does not guarantee native linking succeeds.

## 23. Performance Trade-Offs: Startup, Memory, and Throughput

Native image is often attractive for fast startup and low memory footprint, yet startup time should not be the only metric measured.

| Metric | Where Native Image Often Shines | Considerations |
| --- | --- | --- |
| Cold startup | Very fast startup in many apps | Still depends on external connections and initialization |
| Memory footprint | Often lower in many workloads | Heap/GC and allocation patterns still matter |
| Long-term throughput | Can be solid for steady workloads | JVM JIT can achieve higher peak throughput after warm-up |
| Build duration | — | Native compilation is usually slower and resource-heavy |
| Artifact size | Can trim runtime dependencies distributed | Binary can still be sizable due to retained code/resources |
| Horizontal scaling | Helpful for scale-to-zero/rapid scale-out | Must weigh build matrix and image distribution |

### 23.1. Cold Start Is Not All of Performance

A short-lived serverless function may benefit greatly from fast startup. A long-running service staying up for days may prioritize peak throughput, profiling, and JIT optimizations.

### 23.2. Measure with Realistic Workloads

Compare JVM and native image under identical conditions:

- Same code version and dependencies.
- Same dataset and request mix.
- Same CPU/memory limits.
- Same connection pool configuration.
- Measure both cold startup and warm steady state.
- Measure p50/p95/p99 latency, throughput, and memory.
- Repeat runs to reduce noise.

Do not draw production conclusions from a single local run.

## 24. When to Choose JVM, AOT, or Native Image?

| Scenario | Direction to Consider |
| --- | --- |
| Traditional long-running CRUD app with no startup constraint | JVM is the simplest and most mature option |
| Want to try generated initialization while keeping current deployment | AOT on the JVM |
| Serverless, scale-to-zero, CLI, or cold-start-sensitive workloads | Native image warrants benchmarking |
| Heavy post-deployment dynamic plugin loading | JVM is usually more flexible |
| Key dependencies lack native support | JVM or AOT on JVM; evaluate replacing dependencies first |
| CI has tight CPU/RAM/time limits | Weigh native build cost and release cadence |
| Multiple OS/architecture targets | Account for per-target build cost |
| Long-term throughput is the primary KPI | Benchmark native vs. JVM JIT realistically |

A practical strategy can be building native images only for specific cold-start-sensitive services while keeping the rest on the JVM.

## 25. Docker and Native Image

JVM applications are typically packaged in images containing a JRE/JDK or using layered JARs with an appropriate runtime image.

Native images can be packaged into smaller container images because a full JVM runtime is not needed. Still, they may require libc, CA certificates, timezone data, DNS support, and other system libraries.

### 25.1. Buildpacks

Spring Boot plugins integrate Cloud Native Buildpacks to create OCI images. Buildpacks can choose JVM or native builds depending on builder and environment settings.

Benefits:

- Standardizes container builds.
- Builds images on compatible stacks/base images.
- Manages layers and runtime dependencies.
- Supports native build workflows when a capable builder is configured.

Do not assume every buildpack builder includes a native compiler. Check builder capabilities and logs.

### 25.2. Building for the Target Platform

If production runs on Linux ARM64, the native binary must be built for that target. Building on Linux x86_64 and copying the binary to ARM64 will not work simply because both run Linux.

Use native build runners or a supported cross-compilation workflow, and test the artifact on the target architecture.

### 25.3. Runtime Configuration Must Still Be Provided

A native executable still reads environment variables, external configuration, and secrets as designed. Never embed production credentials inside the binary or build layers.

## 26. Troubleshooting Common AOT/Native Issues

| Symptom | Possible Cause | Approach |
| --- | --- | --- |
| Runs on JVM, but native build warns/errors on reflection | Missing metadata for dynamically accessed class/member | Trace the call path and add targeted runtime hints |
| Native build succeeds, but runtime reports missing class | Class unreachable/omitted from image | Inspect dynamic loading and reflection hints |
| Template/JSON/schema not found | Resource not included | Register resource pattern and test resource access |
| Proxy creation fails | Missing proxy metadata or unsupported runtime generator | Register JDK proxy hints or change integration |
| JSON binding fails | Insufficient DTO/member metadata | Use binding hints and test serialization/deserialization |
| Beans differ between JVM AOT and native | AOT build-time conditions/profiles differ from runtime | Verify active profiles and build-time properties |
| Native compile runs out of RAM | Large project or under-provisioned runner | Increase resources, tune build job, narrow metadata scope |
| Native build is very slow | Large reachability graph/dependencies | Cache effectively, trim dependencies, split pipeline |
| Native executable won't run on another host | OS/CPU/ABI mismatch | Build for exact target and inspect shared libraries |
| Wrong static value in production | Class initialized at build time | Avoid static side effects; adjust init policy |
| Third-party library incompatible | Missing reachability metadata or dynamic behavior | Check support/version or swap library |
| AOT task not found | Plugin/version/build config mismatch | Check Spring Boot plugin and Native Build Tools |
| JVM tests pass, native tests fail | Reflection/resource/proxy/runtime differences | Add native-focused tests and precise hints |

### 26.1. Investigation Workflow

1. Identify whether the failure happens during AOT processing, native compilation, or native runtime.
2. Read the first meaningful warning rather than only the final build-failure line.
3. Determine which class, resource, or proxy is accessed dynamically.
4. Check whether the dependency already supplies reachability metadata.
5. Add the smallest hint necessary.
6. Rebuild the native executable.
7. Run tests covering the exact failing code path.
8. Verify the artifact on the target OS/architecture.

Do not add broad package-level metadata just to silence warnings; doing so can mask an unsuitable dynamic design.

## 27. A Conceptual End-to-End Example

Suppose a payment service reads a DTO from JSON and loads an email template from the classpath.

DTO:

~~~java
public record PaymentRequest(
        String orderId,
        BigDecimal amount
) {
}
~~~

Template:

~~~text
src/main/resources/templates/payment/receipt.html
~~~

Configuration registering hints:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
public class PaymentConfiguration {
}
~~~

Registrar:

~~~java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
                "templates/payment/*.html"
        );
    }
}
~~~

DTO binding can be declared with `@RegisterReflectionForBinding` when the integration requires reflection metadata for the type.

Workflow:

1. Compile application Java sources.
2. Spring AOT analyzes configuration and collects hints.
3. Generated code/resources are produced.
4. The Native Image compiler analyzes reachable code and metadata.
5. A native executable is generated for the target platform.
6. Run the executable and send a request containing a JSON body.
7. Confirm the DTO binds and the template is read.
8. Run regression tests against the native artifact.

This example illustrates that **AOT hints are part of the build/runtime contract**. Omitting a resource hint or binding hint where needed can let the app pass on the JVM while failing natively.

## 28. Practices for Building AOT-Ready Applications

Even before deciding on native image, certain design habits make an application easier to migrate:

- Favor explicit dependency injection and configuration.
- Avoid reflection based on arbitrary class names when unnecessary.
- Limit runtime bytecode generation that lacks native support.
- Use classpath resource APIs rather than assuming resources are physical files.
- Keep static initializers free of environment-dependent side effects.
- Choose libraries with native support/reachability metadata when targeting native image.
- Register hints in the module that owns the types, resources, or proxies.
- Write integration tests for binding, serialization, and resource loading paths.
- Never bake secrets or runtime environment assumptions into AOT/native builds.
- Verify active profiles and condition values during AOT processing.
- Separate native build jobs from JVM builds if resource and duration profiles differ.
- Build for the exact OS/architecture of the deployment target.

Do not sacrifice application architecture merely to force native execution at all costs. If a core feature depends on dynamic loading incompatible with the closed-world model, the JVM may be the right technical choice.

## 29. Common Misconceptions

### 29.1. “AOT and Native Image Are the Same Thing”

Incorrect. AOT processes the application ahead of runtime and produces code/hints. The Native Image compiler uses that output to build a native executable. An AOT-generated application can still run on the JVM.

### 29.2. “Native Images No Longer Need Runtime Configuration”

Incorrect. Applications still need database URLs, credentials, external services, ports, and operational settings. Only the JVM runtime is no longer the primary launcher.

### 29.3. “Adding One Reflection Hint Makes Every Native Error Disappear”

Incorrect. Missing resources, proxies, serialization metadata, or incompatible dependencies could be the cause. Identify the exact failing dynamic operation.

### 29.4. “If Native Build Succeeds, the Application Definitely Works”

Incorrect. A runtime branch might never have executed during build or tests. Native executables still require integration and smoke tests.

### 29.5. “Native Image Is Always Faster Than the JVM”

Incorrect across all metrics. Native image often wins on startup and memory in many scenarios; JVM JIT can achieve higher peak throughput on long-running workloads after warm-up. Always benchmark.

### 29.6. “A Native Binary Runs on Every Machine”

Incorrect. Binaries depend on OS, CPU architecture, and required native libraries/ABI.

### 29.7. “Every Java Library Is Native-Compatible”

Incorrect. Libraries using reflection, runtime code generation, dynamic loading, or JNI may require extra metadata or integration work.

### 29.8. “AOT Eliminates All Reflection”

Incorrect. AOT reduces some dynamic operations and declares metadata for those still needed. Reflection can still exist when properly supported and declared.

## 30. Hands-On Exercises

### Exercise 1 — Distinguish the Three Concepts

Diagram a Spring Boot app running as a JAR on the JVM, running as an AOT-generated application on the JVM, and running as a native executable. Label which compilers and runtimes participate in each flow.

### Exercise 2 — Locate the AOT Task

In a Gradle Spring Boot project, inspect the task list and run `processAot`. Inspect the generated sources/resources and explain why this task alone does not mean a native binary was produced.

### Exercise 3 — Build a Native Executable

Configure a GraalVM Native Build Tools plugin compatible with the project, run `nativeCompile`, and locate the generated executable. Note the OS/architecture and toolchain version.

### Exercise 4 — Reflection Hint

Create a DTO instantiated via reflection from a class name. Run on both JVM and native. If native requires metadata, register only the needed constructor/members and retest.

### Exercise 5 — Binding Hint

Create a DTO bound from JSON by Jackson. Use `@RegisterReflectionForBinding` or the appropriate mechanism, then test serialization/deserialization on the native executable.

### Exercise 6 — Resource Hint

Read a template from `src/main/resources`. Build a native image and confirm the resource is present. Remove the hint to observe the error if the case requires one, then register a tight matching pattern.

### Exercise 7 — Proxy Hint

Create an interface used as a JDK dynamic proxy. Register a proxy hint in `RuntimeHintsRegistrar` and run native tests. Compare with a class-based proxy use case.

### Exercise 8 — Build-Time Conditions

Create configuration using `@ConditionalOnProperty`. Run AOT processing with the property set to true and false, then inspect the generated application. Explain why conditions governing the bean graph must match the build/deploy setup.

### Exercise 9 — Static Initializer

Create a class reading an environment variable in a static initializer. Compare outcomes when initialized at build time versus runtime. Refactor to read values inside a runtime bean/lifecycle.

### Exercise 10 — Third-Party Metadata

Pick a dependency using reflection/resources. Check native support and reachability metadata. Identify what the library provides versus what the application must declare.

### Exercise 11 — Benchmark JVM vs. Native

Run the same workload on JVM and native image. Measure cold startup, memory, throughput, and p95 latency. Use identical resource limits and datasets, then choose based on KPIs.

### Exercise 12 — Native Smoke Test

Build a native executable, run it on the exact target OS/architecture, connect test dependencies, and call an API. Verify serialization, resource loading, logging, and graceful shutdown.

## 31. References

- [Spring Boot 3.3 — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/reference/packaging/aot.html)
- [Spring Framework — AOT Processing and Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [GraalVM Native Image — Overview](https://www.graalvm.org/latest/reference-manual/native-image/)
- [GraalVM Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

## 32. Key Takeaways

**AOT processing, runtime hints, and native image are three related parts of one pipeline, each with a distinct role.** Spring AOT analyzes application configuration at build time and generates code/resources. Runtime hints declare dynamic capabilities that must be retained, such as reflection, resource access, proxies, and serialization. The GraalVM Native Image compiler uses the application along with metadata to build a target-platform native executable.

AOT can be used even when the application continues running on the JVM. Native image often improves cold startup and memory footprint across many workloads, in exchange for longer builds, specific toolchain/platform requirements, and restrictions on certain forms of dynamic loading, reflection, or runtime bytecode generation.

When preparing for native image, prefer native-ready dependencies, register minimal hints for truly required dynamic operations, verify configuration conditions evaluated at build time, and avoid environment-dependent static initialization. JVM unit tests remain useful, but should be complemented by native builds, native-focused integration tests, and smoke tests on the exact target OS/architecture.

Do not choose native simply because the binary looks compact or starts fast in a single test run. Measure cold start, memory, throughput, latency, CI cost, and operational complexity on realistic workloads.
