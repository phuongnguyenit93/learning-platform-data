# Reachability and Eliminating Unnecessary Code

In a Spring Boot application running on the JVM, a dependency can contain hundreds of classes even though the application uses only a few of its APIs. The JVM loads classes and executes code on demand, while also being able to optimize code at runtime. When compiling into a **GraalVM Native Image**, the tool must determine ahead of time which parts of the program *can potentially be executed* to build the native executable. That step is called **reachability analysis**.

Reachability is the foundation of dead code elimination and Native Image's **closed-world assumption** model. Understanding this mechanism clearly helps explain why a native build can start up quickly, why a class present in a dependency can still “disappear” at runtime, and why certain features using reflection or dynamic class names require additional declarations.

## 1. What Is Reachability?

A component is considered **reachable** when the analysis determines that at least one valid execution path leads to it, starting from entry points known at build time. The component can be a method, constructor, field, object type, or related code segment.

Typical starting points and information sources include:

- The `main` method along with application startup and entry points established by the Native Image system.
- Direct calls discovered from bytecode, along with *potential* call targets of interfaces, virtual methods, lambdas, and callbacks.
- Components that frameworks or libraries register via metadata, such as constructors invoked via reflection, dynamic proxies, or JNI.
- Decisions the analyzer can infer at build time, such as branches with statically determined values.

Picture the program as a graph: each node represents a piece of code, and edges represent the possibility that one piece of code leads to another. The analyzer starts from the root set, continuously expands reachable edges, and forms the reachable set. Code outside this set can be omitted from the native executable.

~~~mermaid
flowchart TD
    A["Entry points: main, application startup"] --> B["Analyze calls and type flow"]
    B --> C["Expand set of potentially executable code"]
    M["Metadata for reflection, proxies, JNI…"] --> C
    C --> D{"All possible paths examined?"}
    D -->|No| B
    D -->|Yes| E["Generate machine code for reachable parts"]
    B -. "No path found" .-> F["Code is omitted from image"]
    R["Resource configuration"] --> G["Package required resources"]
~~~

**Reachable does not mean guaranteed to execute.** For instance, both branches of an `if` statement that depends on runtime configuration may be retained. Native Image must preserve behaviors that could occur, so you cannot conclude that every snippet “never executed in a test” will be deleted.

Conversely, **unreachable does not mean the source code or JAR file was deleted**. The analysis result decides what is included in the generated executable; the source code and input dependencies still remain in the project.

## 2. From Static Calls to the Retained Code Set

Consider an application that returns receipts as CSV:

~~~java
interface ReceiptFormatter {
    String format(String receiptId);
}

final class CsvFormatter implements ReceiptFormatter {
    @Override
    public String format(String receiptId) {
        return "receipt_id," + receiptId;
    }
}

final class XmlFormatter implements ReceiptFormatter {
    @Override
    public String format(String receiptId) {
        return "<receipt id=\"" + receiptId + "\"/>";
    }
}

@RestController
class ReceiptController {
    private final ReceiptFormatter formatter = new CsvFormatter();

    @GetMapping("/receipts/{id}")
    String getReceipt(@PathVariable String id) {
        return formatter.format(id);
    }
}
~~~

In this snippet, the path starting from HTTP handling can lead to `ReceiptController.getReceipt`, `CsvFormatter.format`, and their supporting code. If the application has no call, configuration, or other mechanism leading to `XmlFormatter`, the XML implementation may be omitted from the image.

A few distinctions to make:

| Situation | Impact on Reachability |
|---|---|
| Direct call to `new CsvFormatter()` | The constructor and code called from it have a clear static path. |
| Call via `ReceiptFormatter` | Analysis must consider implementation types that may appear at the call site, not just the interface name. |
| Branch depending on request, environment, or runtime data | Feasible branches usually must be retained. |
| Branch or value proven invariant at build time | The optimizer may simplify the branch and related code. |
| Class present only in a JAR with no usage path | Not necessarily included in the executable. |
| Class referenced only by string name from dynamic config | Static analysis may fail to infer the target class; appropriate dynamic support is needed. |

Reachability analysis is **conservative**: when the tool cannot prove a path is impossible, it may have to retain more code to preserve correctness. Executable size therefore does not scale linearly with the number of source classes or dependencies.

## 3. The Closed-World Assumption and Limits of Static Analysis

The **closed-world assumption** means Native Image builds a “program universe” that is sufficiently described at build time: required object types, call paths, and dynamic access capabilities must be recognizable to the analyzer. A native application does not have the same model of loading and compiling arbitrary Java bytecode at runtime as a regular JVM.

Problems arise when behavior depends on information only known after the executable is created. For example:

~~~java
@Service
class FormatterFactory {
    ReceiptFormatter create(String configuredClassName)
            throws ReflectiveOperationException {
        Class<?> type = Class.forName(configuredClassName);
        return (ReceiptFormatter) type.getDeclaredConstructor().newInstance();
    }
}
~~~

The class name here comes from runtime configuration, such as `com.example.receipt.XmlFormatter`. The compiler cannot look only at `Class.forName(configuredClassName)` and know for certain every class name that might be passed in. If the target class or constructor has not been made reachable and properly configured, the native build may fail even though the exact same path works on the JVM.

This **does not mean every `Class.forName` call fails**. GraalVM can deduce some reflection patterns with constant or sufficiently clear arguments. Metadata needs to be added when actual dynamic behavior is not automatically analyzed, and must be verified with native tests.

## 4. The Role of Spring AOT in Spring Boot

Spring Boot uses **Spring AOT (Ahead-of-Time processing)** to turn many startup operations that are inherently dynamic into information and code generated at build time. This process helps GraalVM clearly see the Spring application structure before running reachability analysis.

For example, Spring AOT can:

1. Analyze application configuration and beans identifiable during the AOT phase.
2. Generate bean initialization or bean registration code in place of part of the runtime scanning and configuration inference.
3. Contribute required runtime hints for reflection, resources, proxies, or other dynamic mechanisms managed by Spring.
4. Feed the AOT output into Native Image inputs so the analyzer can continue determining which code to keep.

High-level flow:

~~~text
Spring Boot source + dependencies
           |
           v
   Spring AOT processing
   - Analyze beans/configuration
   - Generate startup helper code
   - Collect runtime hints
           |
           v
    GraalVM Native Image
   - Perform reachability analysis
   - Generate machine code and image data
           |
           v
      Native executable
~~~

Spring AOT reduces the need for runtime application discovery, yet **does not automatically understand every custom mechanism**. Libraries that load class names from a database, plugins from an external directory, or custom string-based reflection may still need developer-supplied metadata.

Keep in mind that configuration choices are only resolved at build time when the tool has enough data to decide. Do not assume every `@Conditional...`, profile, or config property is fixed at build time; verify the behavior for each specific case.

## 5. Reflection, Proxies, and Resources: What Is Easily Missed

**Reflection.** Accessing constructors, methods, or fields via `Class`, `Method`, or `Field` may require reflection metadata so Native Image prepares the corresponding member. Overly broad declarations can also retain unnecessary metadata and code.

**Dynamic proxies.** Libraries may create proxies for a set of interfaces at runtime. Required interface sets must be discoverable or registered so the corresponding proxy exists in the image.

**Resources.** JSON files, templates, certificates, schemas, images, or config files in `src/main/resources` are not method nodes in the Java call graph. Their packaging is governed by separate resource inclusion/configuration mechanisms. Having a file in an input JAR does not guarantee it is available to read from the image's classpath.

**Serialization and data binding.** Jackson or mapping libraries may locate constructors, getters/setters, record components, or fields via reflection. Spring AOT and native-ready libraries often contribute many hints automatically, though dynamically discovered types may require additional declarations.

**JNI and native libraries.** JNI interactions require proper configuration for Java elements accessed from native code; platform-dependent native binaries must also be checked for the target deployment environment.

The common thread is: **metadata expands what the analysis needs to know about**. Declaring a hint does not mean “keep the entire dependency,” and one kind of hint does not replace another. For instance, a reflection hint for a class will not make an arbitrary template appear on the classpath.

## 6. Adding Runtime Hints in a Controlled Way

Suppose the application lets runtime configuration choose between `CsvFormatter` or `XmlFormatter` and also uses a template `templates/receipts/summary.txt`. When Spring AOT and libraries do not supply this information automatically, it can be registered via Spring's `RuntimeHints` API:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

final class ReceiptHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CsvFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.reflection().registerType(
            XmlFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("templates/receipts/*.txt");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ReceiptHints.class)
class ReceiptNativeConfiguration {
}
~~~

This example assumes the classes are in the same package as the configuration. Both formatters must have constructors matching the reflective instantiation. The resource pattern only applies to files that actually exist in the build's resource sources, such as `src/main/resources/templates/receipts/summary.txt`.

Code reading the resource might look like this:

~~~java
Resource template =
    new ClassPathResource("templates/receipts/summary.txt");

try (InputStream input = template.getInputStream()) {
    // Read the template and process its contents.
}
~~~

Spring supports other registration options depending on the case, such as `@RegisterReflectionForBinding` for data-binding types. Additionally, GraalVM has reachability metadata mechanisms for libraries and dedicated native configurations. **Choose the narrowest registration level that covers the actually used path**, because registering reflection for all members or every class in a package easily bloats the image and hides design issues.

Whenever possible, replace arbitrary class-name lookups with an explicit set of strategies declared as Spring beans or a configuration enum. This keeps the logic easier to control and test, and lets Spring AOT see the implementation types.

## 7. What Actually Gets Eliminated

Once analysis finishes, Native Image can omit unreachable code from the final machine code, subject to several important boundaries:

- **Executable code and metadata are two different concepts.** A type can be retained to serve a specific reflective operation; the scope of declared metadata affects what runtime code can access.
- **Resources follow separate packaging rules.** Eliminating a method does not by itself prove a resource file can be dropped, and retaining a class does not automatically keep every accompanying file.
- **Build-time initialization differs from reachability.** A class can be initialized during the build and certain objects stored in the image heap. Deciding when to initialize a class and deciding whether code is reachable are related yet distinct questions.
- **Indirect calls expand the reachable set.** Interface calls, virtual dispatch, callbacks, and broad metadata force the analyzer to consider many potential targets.
- **The runtime requires foundational code.** The image still includes parts of the native runtime system and required libraries. Do not estimate file size purely from the number of application classes.

A dependency with a large JAR size may not increase the image size proportionally if most of its code is unreachable. Conversely, a mechanism that bulk-registers classes for reflection can cause the image to include more components than expected.

## 8. How to Verify on a Spring Boot Project

The steps below apply when the project already has Spring Boot AOT, GraalVM, and the corresponding native build plugin configured. Exact commands may vary depending on the project's build setup.

**Step 1 — Identify dynamic paths.** Look for uses of `Class.forName`, `getDeclaredConstructor`, `getMethod`, `ServiceLoader`, dynamic proxies, non-fixed-type deserialization, or reading resources by configuration-supplied names. Pay special attention to branches that only appear under production profiles or data.

**Step 2 — Build the native binary.** Using common build configurations:

~~~bash
# Maven (when the native profile and plugin are configured)
./mvnw -Pnative native:compile

# Gradle (when the GraalVM Native Build Tools plugin is configured)
./gradlew nativeCompile
~~~

On Windows, use the corresponding wrapper scripts such as `mvnw.cmd` or `gradlew.bat`. A successful build only proves that analysis and executable generation finished; **it does not prove that all runtime features are compatible**.

**Step 3 — Run the exact generated executable.** Call endpoints and business flows involving reflection, serialization, proxies, or resources. For example, test both CSV/XML selection config values and template-reading branches. Run the same scenario suite on both JVM and native to surface discrepancies.

**Step 4 — Isolate the error from specific symptoms.**

| Symptom When Running Native | Hypothesis to Check |
|---|---|
| Class not found when config selects a dynamic implementation | Target class not recognized/registered; inspect the call path and reflection metadata. |
| Object instantiation fails, missing constructor, or member access error | Hint is not accurate enough for the constructor/method/field accessed via reflection. |
| Jackson deserializes incorrectly or fails for only one DTO | Accessibility of constructors, properties, or runtime hints for data binding. |
| `getResourceAsStream` returns `null` | Resource or inclusion pattern is incorrect. |
| Error creating a proxy for a specific interface set | Corresponding proxy information was not included in the native image. |

These symptoms suggest investigation directions, not the sole conclusion. Read the exception and build log before adding metadata. If needed, use GraalVM's diagnostic mode or a tool to trace library dynamic behavior to pinpoint exactly what is missing; avoid copying all collected metadata without reviewing its scope.

**Step 5 — Measure benefits under the same workload.** Evaluate cold startup time, time to first response, process RSS or working set, throughput, and latency under load. Compare identical functionality, environment configuration, and measurement methodology. A smaller code set generally helps footprint, though it does not automatically guarantee every native app uses less memory or achieves higher throughput than the JVM build under all conditions.

## 9. Practical Scenario: Extensible Configuration Breaking Closure

A report-processing service exposes `/reports/export`. Initially it only supports CSV and calls `CsvExporter` directly. Later, the team adds an `export.class` option holding a Java class name to support per-customer plugins. In a JVM environment, a plugin present on the classpath can be loaded dynamically when a request arrives. With a pre-built Native Image, adding a JAR file or configuring a new implementation name at runtime does not automatically make the new class appear in the executable.

There are three common ways to handle this:

1. **Build-time fixed implementation list:** package the supported exporters, declare beans or an explicit registry, and select by configuration key; usually the easiest to keep native-compatible.
2. **Finite dynamic target set:** keep the reflection mechanism but supply metadata for the exact types that can appear and test every supported configuration.
3. **Plugins unknown at build time:** revisit the architecture, such as extracting plugins into external processes/services; do not rely on the JVM's arbitrary bytecode loading inside a Native Image executable.

The lesson here is not “forbid reflection” but **make runtime behavior describable at build time**. Spring AOT handles the Spring structures it can recognize well; custom application code still needs corresponding design and verification.

## 10. Summary of Principles

You can use four questions to analyze a feature before migrating a Spring Boot application to native:

1. **Which path causes the code to be called?** If the path is clear through bytecode or AOT code, GraalVM has a basis to analyze it.
2. **Are any target types only known at runtime?** If so, identify whether they involve reflection, proxies, JNI, serialization, or another mechanism.
3. **Do metadata and resources cover that exact behavior?** Check what Spring AOT or libraries already provide before adding manual hints.
4. **Has that path been executed on the native executable?** JVM tests and a successful build cannot replace native runtime testing.

Reachability determines which parts of the program are potentially needed; dead code elimination leverages that result to reduce the code packaged into the executable. **Spring AOT is the bridge** that makes inherently dynamic Spring Boot structures visible to GraalVM, while runtime hints complete the information for cases that cannot be safely inferred via static analysis.
