# Reflection Calls That GraalVM Can or Cannot Infer

Java Reflection allows a program to look up classes, constructors, methods, and fields and invoke them at runtime. This mechanism is useful for frameworks, dependency injection, serializers, plugins, and extension libraries. On a standard JVM, an application can load classes from string names and access members without knowing every specific target at compile time.

**GraalVM Native Image** operates on a static analysis model at build time. The compiler must determine ahead of time which classes and members may be used so that it can include the machine code and required metadata in the executable. Therefore, some reflection calls can be inferred when the access target is clear from the code; calls that depend on data known only at runtime generally require reachability metadata.

The key point is not that "Native Image does not support reflection." Native Image supports reflection, but **it cannot automatically guess every reflection target chosen from runtime data**. This lesson helps you distinguish between the two cases, recognize signs of code that can be statically analyzed, add metadata with the right scope, and test dynamic paths in Spring Boot applications.

## 1. Why Does Reflection Need to Be Described Ahead of Time?

A direct call such as:

~~~java
CsvExporter exporter = new CsvExporter();
exporter.export(report);
~~~

clearly shows the compiler which class and method are used. The call path can be traced from bytecode and added to the reachability graph.

Meanwhile:

~~~java
String className = configuration.getProperty("report.exporter");
Class<?> type = Class.forName(className);
Object exporter = type.getDeclaredConstructor().newInstance();
~~~

leaves the class name to be decided by configuration. The value might be `com.example.CsvExporter` in one environment and `com.example.XmlExporter` in another. From static code alone, the compiler cannot know the full set of names that might appear.

On the JVM, a class loader can load a class when its name is provided at runtime, provided the class is on the classpath and loading conditions are met. With Native Image, the necessary classes and metadata must be prepared in the executable beforehand. Without that information, a path that runs on the JVM may fail in the native executable.

~~~mermaid
flowchart TD
    A["Reflection call in bytecode"] --> B{"Are target and arguments determinable at build time?"}
    B -->|Yes, following a supported API pattern| C["Static analysis can infer target element"]
    B -->|No, depends on runtime data| D["Compiler does not know full target"]
    C --> E["Include required elements in image"]
    D --> F["Needs reachability metadata or redesign"]
    F --> G["RuntimeHints / JSON / metadata from agent"]
    G --> E
    E --> H["Native executable"]
~~~

**Reachability metadata** describes dynamically accessed components that static analysis cannot reliably determine. For reflection, metadata can declare classes, constructors, methods, or fields that need to be accessed; depending on the purpose, the declaration allows only introspection or also invocation/value access.

## 2. Which Calls Can Native Image Infer?

GraalVM has mechanisms to recognize certain standard reflection APIs, especially calls on `java.lang.Class`. When **arguments can be reduced to constants at build time** and the target element exists on the classpath, analysis can determine the accessed element.

Typical API forms described in GraalVM documentation include:

- `Class.forName(...)` with a determinable class name.
- `Class.getField(String)` and `Class.getDeclaredField(String)`.
- `Class.getMethod(String, Class[])` and `Class.getDeclaredMethod(String, Class[])`.
- `Class.getConstructor(Class[])` and `Class.getDeclaredConstructor(Class[])`.
- Certain forms of class access via class loaders or `MethodHandles.Lookup`, according to the metadata rules of the GraalVM version.

Example:

~~~java
Class<?> type = Class.forName("java.lang.Integer");

Method method = Integer.class.getDeclaredMethod(
    "bitCount",
    int.class
);

Constructor<String> constructor =
    String.class.getConstructor(String.class);
~~~

The class name, method name, and parameter types in the calls above are all determinable from code. GraalVM can precompute the access target for supported APIs and patterns.

However, **you should not generalize that every reflection call with string constants is automatically handled**. Processing capability still depends on the specific API, whether the class is on the classpath, whether parameter types are determinable, access permissions, the GraalVM version, and the metadata mode. Some class/member lookup operations still require metadata registration according to the rules of the version or strict checking mode enabled.

## 3. What Is a Constant Argument?

An argument is considered determinable at build time when the compiler can prove its value. Common cases:

- String literals, numeric literals, or class literals.
- Access to a static field initialized at build time.
- An effectively final variable whose value can be proven.
- Fixed-length arrays where every element is determinable.
- Simple computations from constant values, such as concatenating two constant strings.

Example of a class name constructed from constant strings:

~~~java
String packageName = "com.example.export.";
String simpleName = "CsvExporter";
String className = packageName + simpleName;

Class<?> type = Class.forName(className);
~~~

The compiler can fold the concatenation above into a known name if all input values are proven to be constants.

Parameter type arrays can also be analyzed when both length and elements are determinable:

~~~java
Class<?>[] parameterTypes = {
    String.class,
    int.class
};

Method method = ReportFormatter.class.getDeclaredMethod(
    "format",
    parameterTypes
);
~~~

Certain ways of creating and assigning array elements in sequential steps can also be analyzed if the compiler reliably tracks every write before the array is passed to the reflection call. Arrays obtained from static fields or mutated across complex control branches are harder to prove constant. In particular, a `static final` array does not mean immutable contents: the field cannot point to another array, but its elements can still be overwritten.

There is no Java syntax that guarantees a value becomes a constant across every GraalVM version. Treat constant folding as an analysis aid, not a language contract to rely on in every case.

## 4. Inferable Case: Class and Member Explicitly Specified

Consider an application with a report formatting interface:

~~~java
public interface ReportExporter {
    byte[] export(String reportId);
}

public final class CsvExporter implements ReportExporter {

    @Override
    public byte[] export(String reportId) {
        return ("report_id," + reportId).getBytes(StandardCharsets.UTF_8);
    }
}
~~~

A reflection snippet with a fixed target:

~~~java
Class<?> type = Class.forName("com.example.CsvExporter");
Constructor<?> constructor = type.getDeclaredConstructor();
Object instance = constructor.newInstance();

Method method = type.getMethod("export", String.class);
byte[] result = (byte[]) method.invoke(instance, "R-100");
~~~

Analysis can infer the class name, no-argument constructor, method `export(String)`, and parameter types if the arguments are genuinely proven constant. Being able to infer the lookup does not mean every metadata mode in every version permits invocation without declaration; check the logs and run native tests.

When the class, constructor, and method are already clearly known, a direct invocation design is often even simpler:

~~~java
ReportExporter exporter = new CsvExporter();
byte[] result = exporter.export("R-100");
~~~

If there is no plugin requirement or framework forcing reflection, direct invocation reduces metadata maintenance and helps the compiler trace the call path clearly.

## 5. Hard-to-Infer Case: Class Name Obtained at Runtime

The following example depends on configuration:

~~~java
public ReportExporter createExporter(Environment environment)
        throws ReflectiveOperationException {

    String className = environment.getProperty("report.exporter");
    Class<?> type = Class.forName(className);

    return (ReportExporter) type.getDeclaredConstructor()
        .newInstance();
}
~~~

The value of `report.exporter` may come from:

- An environment variable.
- `application.yml` or `application.properties` mounted at runtime.
- Config Server or a secret/configuration service.
- A database record.
- An HTTP request.
- Tenant metadata or a plugin registry.
- A file modified by operators after the executable has been built.

The compiler cannot know all of these values solely from the call `Class.forName(className)`. To keep the reflection architecture, you must declare every class and member the application may use in the image.

For example, if only two exporters are allowed:

~~~text
com.example.CsvExporter
com.example.XmlExporter
~~~

then metadata needs to cover both classes, their constructors, and dynamically invoked methods. If a class is only added to a plugin folder after the image is built, metadata cannot make new bytecode magically appear in the executable. Native Image requires the classes to be present in the build input and prepared accordingly.

## 6. Reflection Lookup and Reflection Invocation Are Two Different Needs

Reflection metadata does not just answer "can this method be found?". It also distinguishes **listing/lookup** from **invoking a method or constructor**, as well as reading/writing field values.

| Operation | Example | Metadata Requirement |
|---|---|---|
| Get class by name | `Class.forName(name)` | Class must be recognized/registered if name cannot be inferred |
| Look up method | `type.getDeclaredMethod(name, params)` | Member must be allowed for introspection per metadata rules |
| Invoke method | `method.invoke(target, args)` | Invocation metadata required for the corresponding method |
| Look up constructor | `type.getDeclaredConstructor(params)` | Constructor must be recognized/registered |
| Create instance | `constructor.newInstance(args)` | Metadata allowing constructor invocation required |
| Look up field | `type.getDeclaredField(name)` | Field must be recognized/registered |
| Read/write field | `field.get(obj)`, `field.set(obj, value)` | Metadata allowing field value access required |

Some metadata formats distinguish `queriedMethods`/`queryAllDeclaredMethods` from `methods`/`allDeclaredMethods`, or equivalent modes in newer schemas. The query part only provides information for introspection; it does not automatically grant permission to invoke the method via reflection.

Therefore, when encountering an error in `Method.invoke` or `Constructor.newInstance`, merely registering the ability to look up the method may not be enough. You must determine whether the application needs lookup, method invocation, object instantiation, or field value access.

## 7. Example Reachability Metadata for Dynamic Reflection

With current GraalVM versions, the new reachability metadata format can be placed in `META-INF/native-image/{groupId}/{artifactId}/reachability-metadata.json`. Illustrative example:

~~~json
{
  "reflection": [
    {
      "type": "com.example.CsvExporter",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "export",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    },
    {
      "type": "com.example.XmlExporter",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "export",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

The metadata above lets Native Image prepare the listed constructors and methods for those classes. In a real application, narrow the scope to the exact constructors/methods needed. Do not enable `allDeclaredMethods` or `allDeclaredFields` for a large library just to try making errors disappear.

In older GraalVM versions, reflection configuration typically used `reflect-config.json` with a schema featuring `name`, `methods`, `fields`, and `allDeclared...` flags. Spring Boot/Spring AOT can also generate corresponding configuration files in the build output. **Do not mix the new `reachability-metadata.json` schema with the old `reflect-config.json` schema**; use the exact format supported by the project's native-image toolchain.

A metadata entry can be conditioned on a reachable type to avoid including metadata in the image when the related code is unused. With the new schema, the `condition` field can use `typeReached` as defined by the version. Conditions help reduce excess metadata and keep the image leaner.

## 8. Registering with Spring RuntimeHintsRegistrar

In a Spring Boot application, the integration closest to source code is typically `RuntimeHintsRegistrar`. Spring AOT collects these hints and translates them into the configuration GraalVM needs.

Example:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

public class ExporterRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            CsvExporter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.reflection().registerType(
            XmlExporter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ExporterRuntimeHints.class)
class ExporterNativeConfiguration {
}
~~~

In the example, the two exporter classes are known at build time, and their constructors and public methods require invocation. If only introspection or only constructors are needed, choose a narrower member category. Category APIs may vary across Spring Framework versions; this example uses categories common in Spring Framework 6.x.

If an exporter requires non-public methods, explicitly identify the method and actual access permission. Do not automatically expose all private members just because a library uses reflection.

## 9. Using Annotations for Common Cases

Spring provides annotations to express reflection needs right where they apply.

**`@RegisterReflection`** lets you declare required classes and member categories:

The `@RegisterReflection` annotation has been available since Spring Framework 6.2. If the project uses an older Spring Framework version, use `RuntimeHintsRegistrar` or the hint API appropriate for that version.

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflection(
    classes = CsvExporter.class,
    memberCategories = {
        MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
        MemberCategory.INVOKE_PUBLIC_METHODS
    }
)
class ExporterConfiguration {
}
~~~

**`@RegisterReflectionForBinding`** is suitable for data types requiring binding/serialization, commonly encountered when Jackson processes DTOs in programmatic APIs such as `WebClient` or `RestClient` that Spring cannot infer from controller signatures.

`@RegisterReflectionForBinding` has been available since Spring Framework 6.0 and registers constructors, fields, properties, record components, and referenced types needed for data binding. It is not a general-purpose way to expose arbitrary plugin methods.

~~~java
@Component
class ReportClient {

    @RegisterReflectionForBinding(ReportPayload.class)
    ReportPayload decode(String json) {
        // Call ObjectMapper or client according to application configuration.
        return objectMapper.readValue(json, ReportPayload.class);
    }
}
~~~

The example assumes `objectMapper` is injected and exceptions are handled appropriately. The binding annotation does not replace metadata for arbitrary plugin methods; it targets data-type introspection/binding needs.

For controllers accepting/returning DTOs via Spring MVC, Spring AOT can often infer some hints from data types and signatures. However, when a type appears only inside a programmatic client call or is selected dynamically, check and add hints when needed.

## 10. When Should Reflection Be Replaced with a Static Registry?

If the set of plugins is finite and known upfront, you can avoid using user-supplied class names. Example:

~~~java
public enum ExportFormat {
    CSV,
    XML
}

@Component
class ExporterRegistry {

    private final Map<ExportFormat, Supplier<ReportExporter>> exporters =
        Map.of(
            ExportFormat.CSV, CsvExporter::new,
            ExportFormat.XML, XmlExporter::new
        );

    ReportExporter get(ExportFormat format) {
        Supplier<ReportExporter> supplier = exporters.get(format);
        if (supplier == null) {
            throw new IllegalArgumentException(
                "Unsupported export format: " + format
            );
        }
        return supplier.get();
    }
}
~~~

The method references `CsvExporter::new` and `XmlExporter::new` create clear static call paths. The compiler sees the referenced implementations and constructors. The application still chooses the format from the request/runtime, but selection happens over a known registry rather than loading arbitrary classes from strings.

Advantages:

- No need to maintain class names in configuration.
- Reduces reflection metadata and risk of missing registrations.
- Clearly bounds the set of supported plugins.
- Easier to test, authorize, and validate input.
- Easier to analyze reachability and eliminate unused implementations if there is no call path.

If the architecture requires third-party plugins supplied after the build, Native Image cannot simply load an arbitrary JAR like the JVM. An architectural change is needed, such as isolating plugins into a separate process/service or determining the plugin set at build time and creating the corresponding image.

## 11. Reflection in Common Libraries and Frameworks

Not all reflection is invoked directly by application code. Frameworks may use reflection internally:

- Jackson looks up constructors, record components, getters/setters, or fields to serialize/deserialize.
- ORMs look up entity metadata, constructors, and accessors.
- Dependency injection frameworks look up annotations and injection points.
- Validation frameworks look up constraint annotations and methods.
- Logging, scripting, or plugin frameworks may look up classes, methods, and resources by name.
- Mapping libraries may create proxies or dynamic adapter classes.

Spring AOT and libraries shipping reachability metadata can automatically provide most of the necessary hints. However, non-standard paths, programmatic APIs, DTOs appearing only inside method bodies, or types selected from runtime data may require additions.

When a library already provides metadata in its artifact, do not duplicate that configuration into your application without a reason. First check the library version and its bundled reachability metadata.

## 12. Tracing Agent: Collecting Metadata from Real Execution Flows

GraalVM provides the Native Image Tracing Agent to observe dynamic features when running the application on the JVM. The agent can record reflection, proxy, JNI, serialization, and resource operations that were executed.

Example of running the JVM application with the agent:

~~~bash
java -agentlib:native-image-agent=config-output-dir=target/native-agent-config -jar target/application.jar
~~~

After the application exits, the output directory may contain metadata configuration files. You can review and place the required entries onto the native build classpath following the structure supported by the toolchain.

The agent only records paths that actually ran during the observation session. If tests did not exercise the XML format, did not process a special DTO, or did not enable the production profile, metadata for those paths may be missing. Therefore:

1. Run tests with diverse inputs and configurations.
2. Cover all supported plugins, profiles, and business branches.
3. Inspect the generated agent metadata; remove unnecessary entries.
4. Build the native image with the reviewed metadata.
5. Re-run native tests to uncover any remaining gaps.

**Agent-generated metadata is observed data, not proof of full coverage.** Do not ship a massive raw metadata dump into production without inspecting its origin and scope.

## 13. Diagnosing Reflection Errors When Running Native

Common symptoms:

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `ClassNotFoundException` with class name from config | Class is not in the image or runtime name is not in the registered set | Check classpath, class name, and reflection metadata |
| `NoSuchMethodException` only on native | Method/constructor was not included in metadata or signature is wrong | Confirm name, parameter types, and member category |
| `IllegalAccessException` | Java visibility or module access is insufficient | Check visibility, package/module, and access design |
| `InvocationTargetException` | Target method threw an exception | Inspect the cause of the exception |
| `MissingReflectionRegistrationError` | Dynamic access lacks reachability metadata | Read stack trace and register exact class/member |
| Jackson deserialization fails on native | DTO or constructor/property needs binding hint | Use `RegisterReflectionForBinding` or `RuntimeHints` |
| Plugin works on JVM but fails on native | Class name is chosen dynamically or plugin is not in the image | Register plugin set at build time or switch to static registry |
| `Method.invoke()` fails even though `getMethod()` succeeds | Query metadata exists but invocation metadata is missing | Register invocation for the exact method signature |
| `MethodHandles` lookup fails | Missing metadata for type/member accessed via lookup | Check metadata and the specific `MethodHandles` API |

Do not catch `Throwable` and silently ignore missing registration errors. Some registration errors are `Error` instances signaling that the image lacks required information. Swallowing them can leave the application running in a broken state and hide missing metadata from tests.

## 14. Strict Metadata Checking in GraalVM

Recent GraalVM versions offer stricter reachability metadata checking modes. You can enable `--exact-reachability-metadata` during build to detect missing registrations earlier. Some versions allow scoping this by package.

When running the application, missing registration reporting modes can help observe errors:

~~~bash
# Report locations with missing registrations while running native tests
./application -XX:MissingRegistrationReportingMode=Warn
~~~

~~~bash
# Exit immediately on encountering a missing registration in tests
./application -XX:MissingRegistrationReportingMode=Exit
~~~

These flags depend on the GraalVM Native Image version. Verify against your toolchain/documentation before adding them to pipelines. `Warn` mode is useful during exploration; `Exit` mode causes tests to fail immediately even if code accidentally catches `Throwable` and masks the error.

During development, you can enable exact metadata mode for application packages first, then expand coverage. You do not necessarily have to turn it on for all dependencies at once if migration produces too many hard-to-triage warnings.

## 15. Hands-On Practice: Comparing Constant Reflection and Dynamic Reflection

Objective: observe two ways of selecting an exporter and determine which case requires metadata.

### Step 1 — Create Two Exporters

~~~java
public interface ReportExporter {
    byte[] export(String id);
}

public final class CsvExporter implements ReportExporter {
    public CsvExporter() {
    }

    @Override
    public byte[] export(String id) {
        return ("csv:" + id).getBytes(StandardCharsets.UTF_8);
    }
}

public final class XmlExporter implements ReportExporter {
    public XmlExporter() {
    }

    @Override
    public byte[] export(String id) {
        return ("<report>" + id + "</report>")
            .getBytes(StandardCharsets.UTF_8);
    }
}
~~~

### Step 2 — Try a Constant Class Name

~~~java
Class<?> type = Class.forName("com.example.CsvExporter");
Constructor<?> constructor = type.getDeclaredConstructor();
ReportExporter exporter =
    (ReportExporter) constructor.newInstance();
~~~

Build native and run tests. Observe GraalVM logs and verify behavior according to the metadata version in use. If the compiler can process the constant arguments per supported APIs, the target class/constructor will be determined at build time.

### Step 3 — Try a Class Name from a Property

~~~java
String className = environment.getProperty("report.exporter");
Class<?> type = Class.forName(className);
Constructor<?> constructor = type.getDeclaredConstructor();
ReportExporter exporter =
    (ReportExporter) constructor.newInstance();
~~~

Run on the JVM with both CSV and XML values. Then build native and run again. If metadata is missing, one or both paths may fail.

### Step 4 — Add Metadata

Register both classes and constructors using Spring `RuntimeHints` or reachability metadata. If a method is invoked via `Method.invoke`, register the method signature with invocation permission as well.

### Step 5 — Try a Static Registry

Replace the class name with an `ExportFormat` enum and a `Supplier` registry. Rebuild native and compare the amount of metadata to maintain, configuration clarity, and testability.

### Observation Table

| Test Case | Class Selection Method | When Is Target Known? | What to Check |
|---|---|---|---|
| A | `CsvExporter.class` | Build time | Direct call path |
| B | `Class.forName("com.example.CsvExporter")` | Constant in source | Whether API is analyzed and invocation metadata |
| C | `Class.forName(className)` from property | Runtime | Metadata for all allowed classes/members |
| D | `Supplier` registry | Fixed set of implementations in source | Reachability from method reference |
| E | Plugin JAR added after build | After image is created | Cannot simply add reflection metadata to load new bytecode |

## 16. Workflow for Handling a Reflection Call in a Project

When you find reflection, follow this sequence:

1. **Identify the API:** `Class.forName`, `getDeclaredMethod`, `Constructor.newInstance`, `Field.get/set`, `MethodHandles`, or proxy.
2. **Identify the input data:** literal, class literal, static field, property, environment, request, or database.
3. **Check constancy:** can the class name, member name, and parameter types array be determined at build time?
4. **Determine the purpose:** only lookup/introspection or actual constructor/method invocation, field read/write?
5. **Check the classpath:** are the class and all parameter types present in the build input?
6. **Look for existing metadata:** have Spring AOT, the library, or the reachability metadata repository already provided hints?
7. **Choose how to add metadata:** `RuntimeHints`, annotations, JSON metadata, or tracing agent.
8. **Narrow the scope:** register only required classes/members, and use conditional metadata where appropriate.
9. **Test native:** run across all class names, profiles, data types, and runtime branches.
10. **Consider redesigning:** if the target set is finite, a static registry is usually simpler and safer than arbitrary reflection.

## 17. Takeaways

GraalVM Native Image can infer some reflection calls when the API is supported and arguments can be reliably determined at build time. Constant class names, member names, and parameter types are good signals; data coming from the environment, requests, databases, or plugin registries usually means the access target is known only at runtime.

Even when a lookup is inferred, distinguish metadata for introspection from metadata for invocation. `getDeclaredMethod` finding a method does not automatically prove `Method.invoke` has sufficient access permissions in the image. Likewise, registering a class does not mean all of its constructors, methods, and fields are opened.

With Spring Boot, prefer hints provided by Spring AOT and libraries; supplement with `RuntimeHintsRegistrar`, annotations, or reachability metadata for application-specific paths. The Tracing Agent helps discover executed paths, but broad test coverage is still required. When the plugin set is finite, a static registry reduces reflection and makes reachability clearer.

### References

- GraalVM — Reachability Metadata: https://www.graalvm.org/reference-manual/native-image/metadata/
- GraalVM — Reflection in Native Image: https://www.graalvm.org/reference-manual/native-image/dynamic-features/Reflection/
- GraalVM — Collect Metadata with the Tracing Agent: https://www.graalvm.org/reference-manual/native-image/Agent/
- Spring Boot — Advanced Native Image Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html

Metadata syntax and checking options may change across GraalVM versions. When implementing, verify the schema and flags against the toolchain pinned in your project.
