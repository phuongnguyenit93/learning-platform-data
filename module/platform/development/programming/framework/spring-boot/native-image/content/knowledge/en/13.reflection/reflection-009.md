# Verifying Actual Access Paths Instead of Registering an Entire Package

## 1. Why Must the Exact Reflection Path Be Identified?

On the JVM, an application can use reflection to look up classes by name, search for constructors or methods, read/write fields, and invoke methods at runtime. The JVM can usually access class metadata from the classpath, so a reflective code snippet can work even when the compiler sees no direct call to that class or member.

With **GraalVM Native Image**, reachability analysis happens at build time. Dynamically accessed classes/members that cannot be inferred from static analysis require reachability metadata. If registration is incomplete, the application may build successfully yet fail when that reflection branch executes. If registration is overly broad, the native image must keep extra unnecessary classes/members and metadata, reducing the effectiveness of closed-world analysis.

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring AOT and the `RuntimeHints` API help declare the dynamic accesses the application genuinely needs. This lesson focuses on an essential skill: **tracing reflection operations in code and verifying them with test/runtime evidence, then registering only the corresponding types/members**.

After this lesson, learners will be able to:

- Distinguish class lookup, constructor/method lookup, method invocation, and field access via reflection.
- Build a mapping table between runtime operations and required metadata.
- Write a registrar permitting only the exact classes, constructors, and methods actually used.
- Use the Spring RuntimeHints Agent or GraalVM tracing agent to discover executed access paths.
- Test key branches and explain the limitations of tracing data.

## 2. Understanding Exactly What the Code Is Doing

Not every API in `java.lang.reflect` has the same metadata requirements. Read the sequence of operations instead of seeing the word "reflection" and registering an entire package.

For example, an application selects an exporter from configuration:

```java
// The configuration value is only allowed to select a pre-packaged implementation.
String implementationName = environment.getRequiredProperty("export.plugin.class");

Class<?> pluginType = ClassUtils.forName(implementationName, classLoader);
Constructor<?> constructor = pluginType.getDeclaredConstructor();
Object plugin = constructor.newInstance();

Method exportMethod = pluginType.getMethod("export", ExportRequest.class);
exportMethod.invoke(plugin, request);
```

The snippet above is a condensed method body from a registry; imports, exception handling, and configuration validation are omitted to highlight the reflection sequence.

In the example, the `export.plugin.class` property may only be configured to the name of `CsvExportPlugin` or `PdfExportPlugin`; these classes are already on the classpath at build time. The property must not accept arbitrary class names from external requests. Because the class name is known only at runtime, Native Image needs metadata for each class in the allowed set.

The actual access path consists of:

1. **Selecting a class name:** the configuration property chooses `CsvExportPlugin` or `PdfExportPlugin`.
2. **Looking up the class:** `ClassUtils.forName(...)` looks up the type by name.
3. **Looking up the no-argument constructor:** `getDeclaredConstructor()` requires metadata to introspect the constructor.
4. **Instantiating the object via reflection:** `newInstance()` requires permission to invoke the constructor.
5. **Looking up a specific method:** `getMethod("export", ExportRequest.class)` looks up the public method with the exact name and signature.
6. **Invoking the method:** `Method.invoke(...)` executes the method via reflection.

If the application only calls `Class.forName()` and reads `getName()`, there is no reason to register every constructor and method of the class. If the application invokes a constructor and a single method, metadata should reflect exactly those two operations.

### Mapping Table: Operations and Metadata

| Operation in Code | What Native Image Must Support | Scope to Register |
|---|---|---|
| `Class.forName(name)` or `ClassLoader.loadClass(name)` | Look up type by name at runtime | Exact classes that may be selected |
| `getDeclaredConstructor(...)` | Introspect constructor with matching signature | Constructor with exact parameter types list |
| `Constructor.newInstance(...)` | Invoke constructor | The constructor being called |
| `getDeclaredMethod(name, types...)` | Introspect method with that name and signature | Specific method |
| `Method.invoke(...)` | Invoke method via reflection | Specific method and exact signature |
| `getDeclaredField(name)` | Introspect field | Specific field |
| `Field.get(...)` / `Field.set(...)` | Access field value via reflection | Field actually read/written |
| `getDeclaredMethods()` / `getDeclaredFields()` | List a set of members | Use introspection metadata only if code truly needs the list |
| `getAnnotations()` / `getAnnotation(...)` | Read annotation metadata | Check library/framework requirements and specific types/members |

A type registered for lookup does not automatically mean all of its members can be invoked via reflection. Conversely, registering a method for invocation is not a reason to expose all fields or all remaining methods.

### Distinguishing INTROSPECT and INVOKE

Spring models executable reflection requirements using `ExecutableMode`:

- `INTROSPECT`: need to look up/inspect executable information such as a constructor or method.
- `INVOKE`: need to invoke that executable via reflection.

If code only retrieves a method to read its name or inspect its signature, evaluate introspection needs. If code proceeds to call `Method.invoke()` or `Constructor.newInstance()`, the path needs invocation capability. For a method invoked via reflection, registering only the method name while omitting parameter types may fail to match the actual overload.

## 3. Start from Evidence, Not from a Package Name

When encountering a native error caused by reflection, identify **the specific call site** using evidence sources:

1. **Read application code:** search for `Class.forName`, `loadClass`, `getDeclaredConstructor`, `getDeclaredMethod`, `Method.invoke`, `Field.get/set`, `MethodHandles.Lookup`, and framework helpers.
2. **Read stack traces:** identify which library calls reflection, which method creates the class/method handle, and where the class name value comes from.
3. **Inspect dependencies:** check whether the library already provides reachability metadata or a Spring `RuntimeHintsRegistrar`. Do not register duplicate hints if library metadata already satisfies the use case.
4. **Trace the configuration flow:** determine whether the set of classes selectable at runtime is fixed at build time, or loaded from external plugins.
5. **Reproduce with concrete inputs:** run the exact format, profile, request, or failing branch. One working endpoint does not prove all plugins/serializers have been tested.
6. **Record the access sequence:** which class is looked up, which member is queried, which member is invoked, and what data determines the selection.

A helpful investigation table:

| Question | Example Answer |
|---|---|
| Where does the class name come from? | Property `export.plugin.class` picks a class from an allow-list |
| How many valid implementations exist? | CSV and PDF, both present on the classpath at build time |
| Which constructor is called? | Public no-argument constructor |
| Which method is called? | `export(ExportRequest)` |
| Are fields read/written via reflection? | No |
| Are other overloaded methods called? | No |
| Does the framework already supply hints? | Check AOT output/dependency metadata |
| Which branches were tested? | CSV and PDF; error branches not yet tested |

From this table, you can identify a small, verifiable metadata set. Do not deduce "package `com.example.plugin` uses reflection" and enable every member of every class in the package.

## 4. Example Registrar Registering Only the Needed Constructor and Method

Suppose the application has two pre-packaged plugins: `CsvExportPlugin` and `PdfExportPlugin`. Both have a no-argument constructor and an `export(ExportRequest)` method.

Example registrar:

```java
package com.example.export;

import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.TypeReference;

public final class ExportPluginRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        registerExportPlugin(hints, CsvExportPlugin.class);
        registerExportPlugin(hints, PdfExportPlugin.class);
    }

    private void registerExportPlugin(RuntimeHints hints, Class<?> pluginType) {
        hints.reflection().registerType(pluginType, typeHint -> typeHint
            .withConstructor(List.of(), ExecutableMode.INVOKE)
            .withMethod(
                "export",
                List.of(TypeReference.of(ExportRequest.class)),
                ExecutableMode.INVOKE
            )
        );
    }
}
```

The code makes the scope clear:

- Only the two selectable implementations are registered.
- Only the no-argument constructor is invocable.
- Only the `export(ExportRequest)` method is invocable.
- It does not register all declared methods, public methods, fields, or constructors of the package.

`TypeHint.Builder.withConstructor` accepts a parameter types list; `withMethod` accepts the method name, parameter types list, and mode. If a method is overloaded, each signature is declared individually. This avoids letting a shared method name widen metadata beyond the use case.

Attach the registrar to the bean using the plugins:

```java
package com.example.export;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.stereotype.Component;

@Component
@ImportRuntimeHints(ExportPluginRuntimeHints.class)
public class ExportPluginRegistry {
    // Contains the export() method with the access sequence illustrated in Section 2.
}
```

`@ImportRuntimeHints` ensures Spring AOT discovers the registrar during the build. Placing the annotation near the bean using reflection keeps metadata alongside the feature; if the bean is not contributed to the `BeanFactory` in the AOT configuration, hints attached to that bean are not contributed either.

## 5. Why Does Broad Registration Degrade Metadata Quality?

Some registration styles are convenient, yet cover a larger scope than the actual call path:

```java
// Register all declared methods of a type
hints.reflection().registerType(
    CsvExportPlugin.class,
    MemberCategory.INVOKE_DECLARED_METHODS
);
```

This permits invoking many methods declared in `CsvExportPlugin`, whereas the use case above only calls `export(ExportRequest)`. If applied across every class in the plugin package, metadata balloons and it becomes hard to tell which methods the application truly uses.

Comparison:

| Declaration | Scope | When to Consider |
|---|---|---|
| `withMethod("export", List.of(TypeReference.of(ExportRequest.class)), INVOKE)` | One method with a fixed signature | Default preference when code calls only this method |
| `withConstructor(List.of(), INVOKE)` | One no-argument constructor | When code instantiates using that constructor |
| `MemberCategory.INVOKE_DECLARED_METHODS` | All declared methods of a type | Only when the library genuinely invokes many methods that cannot be listed ahead of time |
| `MemberCategory.INVOKE_DECLARED_CONSTRUCTORS` | All declared constructors of a type | Only when multiple constructors are genuinely selected dynamically |
| `allDeclaredMethods` in reachability JSON | All declared methods of the declared type | Avoid if only a few specific methods exist |

Broad registration does not necessarily inflate the binary by a fixed ratio: the compiler still performs reachability analysis and optimizations. Nevertheless, excess metadata reduces precision, can keep extra code/members alive, and makes diagnosing missing hints harder. GraalVM recommends providing exact and sufficient metadata for dynamic accesses to ensure correctness and compatibility.

### What Does "Registering an Entire Package" Mean?

Native Image metadata describes specific types and members; do not treat a package name as proof that every class inside it needs reflection. Some frameworks have package-scanning mechanisms to find annotated elements. For instance, Spring's `@ReflectiveScan` scans packages during AOT to find elements carrying `@Reflective` (directly or via meta-annotations). That mechanism is **not synonymous** with enabling reflection for every member of every class in the package.

If a project uses `@RegisterReflection` or `MemberCategory`, read the scope of the annotation/category for your exact Spring Framework version. A category such as `INVOKE_PUBLIC_METHODS` still means allowing many methods on a type, not just the single method a test happened to invoke.

## 6. Testing Metadata with RuntimeHintsPredicates

For known access paths, you can verify a registrar using `RuntimeHintsPredicates` without building a native image. Example confirming a type has hints for the required constructor category:

```java
import org.junit.jupiter.api.Test;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class ExportPluginRuntimeHintsTests {

    @Test
    void shouldRegisterConstructorAccessForCsvPlugin() {
        RuntimeHints hints = new RuntimeHints();

        new ExportPluginRuntimeHints()
            .registerHints(hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
            .onType(CsvExportPlugin.class))
            .accepts(hints);
    }
}
```

The test above only confirms the type has a reflection hint; it does not yet prove the specific constructor or method is registered. To test individual executables, use member-level predicates. In Spring Framework 7, the APIs are `onConstructorInvocation(Constructor)` and `onMethodInvocation(Method)`. In Spring Framework 6, the corresponding APIs are `onConstructor(Constructor)` and `onMethod(Method)`; these are marked deprecated as of Framework 7. If you want to test the full sequence of executed calls, use the RuntimeHints Agent in the next section.


Example predicate verifying constructor and method on Spring Framework 7:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

Constructor<?> constructor = CsvExportPlugin.class.getDeclaredConstructor();
Method method = CsvExportPlugin.class.getMethod("export", ExportRequest.class);

assertThat(RuntimeHintsPredicates.reflection()
    .onConstructorInvocation(constructor))
    .accepts(hints);

assertThat(RuntimeHintsPredicates.reflection()
    .onMethodInvocation(method))
    .accepts(hints);
```

These two predicates verify the exact required executables. When using Spring Framework 6, replace them with `onConstructor(constructor)` and `onMethod(method)` per that version's API. Spring Framework 7 replaced the older predicates with clearer names to distinguish invocation.

## 7. Recording Executed Reflection Paths with Spring RuntimeHints Agent

Unit tests verifying declared hints are helpful, yet sometimes a team is unsure which reflection operations a library actually performs. Spring Framework provides the RuntimeHints Agent in the `org.springframework:spring-core-test` module. The agent records runtime-hint-related calls inside executed code, then lets you compare those calls against `RuntimeHints`.

This is **execution-behavior** testing:

1. Run the exact business logic inside a lambda tracked by the recorder.
2. The agent records the metadata-requiring operations that occurred.
3. Populate `RuntimeHints` using the application's real registrar.
4. Compare the recorded invocations against the registered hints.
5. If any operation is uncovered, the test reports the missing invocation details.

Example:

```java
import org.junit.jupiter.api.Test;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.test.agent.EnabledIfRuntimeHintsAgent;
import org.springframework.aot.test.agent.RuntimeHintsInvocations;
import org.springframework.aot.test.agent.RuntimeHintsRecorder;

import static org.assertj.core.api.Assertions.assertThat;

@EnabledIfRuntimeHintsAgent
class ExportPluginRuntimeHintsAgentTests {

    @Test
    void shouldCoverReflectiveCallsUsedByCsvExport() {
        RuntimeHints hints = new RuntimeHints();
        new ExportPluginRuntimeHints()
            .registerHints(hints, getClass().getClassLoader());

        RuntimeHintsInvocations invocations = RuntimeHintsRecorder.record(() -> {
            ExportPluginRegistry registry = testExportPluginRegistry();
            registry.export("csv", sampleExportRequest());
        });

        assertThat(invocations).match(hints);
    }
}
```

`testExportPluginRegistry()` and `sampleExportRequest()` are test helpers to implement in your project. The example illustrates test structure; it is not a complete standalone class you can copy and run directly.

### Agent Setup and Limitations

- Add `org.springframework:spring-core-test` to test dependencies with the version managed by Spring Boot/Spring Framework dependency management.
- Configure the Java agent for your test task according to the instructions for Spring Framework and your build tool.
- `@EnabledIfRuntimeHintsAgent` ensures the test runs only when the agent is loaded.
- Per Spring Framework documentation, the agent instruments the `org.springframework` package by default. To record reflection calls in an application package such as `com.example.export`, configure instrumentation scope for that package.
- Run tests across all branches needing verification. Running only CSV cannot prove the PDF path is covered.

**Important limitation:** the agent only records operations that **actually executed**. An untested branch will not appear in the recording. Therefore, combine the agent with feature checklists, test cases, and testing across all valid configurations/implementations.

## 8. Using the GraalVM Tracing Agent to Generate Metadata from a JVM App

The GraalVM Native Image tracing agent can run alongside a JVM application or test suite to collect dynamic accesses and generate JSON metadata configuration. This is a useful source of evidence when third-party libraries use reflection not called directly by application code.

General workflow:

1. Launch the application/tests on the JVM with the tracing agent according to your exact GraalVM version's guide.
2. Exercise the requests, plugins, serializers, profiles, and business branches to support.
3. Collect the metadata generated by the agent.
4. Review every entry: which type is looked up, which constructor/method/field is accessed, and whether that call path is still needed.
5. Remove entries outside release scope or already supplied by Spring/libraries; retain required dynamic accesses.
6. Build the Native Image and re-test those access paths on the binary.

The tracing agent is not an analyzer of every possible execution path. It only observes what executed during the instrumented run. A test suite missing the PDF plugin branch, for example, may emit metadata for CSV without capturing PDF.

Do not copy the entire agent-generated JSON file into production without review. The agent can observe operations from test frameworks, auxiliary libraries, or test-only code paths. Output metadata and file placement vary by GraalVM version; use the format/schema of your project's toolchain. Newer versions support `reachability-metadata.json` under `META-INF/native-image/<groupId>/<artifactId>/`.

## 9. Checking for Missing Metadata on Native Image

Even after registrar unit tests and agent tests pass, you must still build and run the native executable. JVM tests cannot substitute for this step because the native environment enforces different metadata and reachability rules.

With GraalVM versions supporting the corresponding options, you can enable exact reachability metadata checking at build time:

```text
--exact-reachability-metadata
```

When running the application or native tests, depending on the GraalVM version you can use:

```text
-XX:MissingRegistrationReportingMode=Warn
```

`Warn` mode logs missing registration errors rather than letting failures surface only when users trigger that branch. When strict CI checking is needed, GraalVM can provide `Exit` mode to report an error and terminate the process immediately upon detecting a missing registration. Verify exact options and behavior with the Native Image version in use; do not copy flags from another release without checking.

Verification workflow:

1. Build native with exact metadata configuration matching your GraalVM version.
2. Run smoke tests and the full business test suite on the native executable.
3. Enable the appropriate reporting mode to detect dynamic accesses missing registrations.
4. Exercise both CSV, PDF, and error/edge cases.
5. Fix the registrar at source, rebuild, and repeat tests.

Do not handle `MissingReflectionRegistrationError` by catching and ignoring `Error` or adding `catch (Throwable)` to continue business logic. This error signals that the program is performing a reflection access not properly declared for the native image. Fix the metadata or redesign the access path.

## 10. When Should You Drop Reflection Instead of Adding More Registrations?

If the set of implementations is known and Spring can manage them as beans, consider removing class-loading by name. For example, inject plugins into a registry:

```java
@Component
public class ExportPluginRegistry {

    private final Map<String, ExportPlugin> plugins;

    public ExportPluginRegistry(List<ExportPlugin> availablePlugins) {
        this.plugins = availablePlugins.stream()
            .collect(Collectors.toUnmodifiableMap(
                ExportPlugin::format,
                Function.identity()
            ));
    }

    public void export(String format, ExportRequest request) {
        ExportPlugin plugin = this.plugins.get(format);
        if (plugin == null) {
            throw new IllegalArgumentException("Unsupported format: " + format);
        }
        plugin.export(request);
    }
}
```

In this example, Spring creates beans for the plugins and the registry invokes them through the interface via standard Java calls. If no other code uses reflection, there is no need to register plugin constructors/methods for this use case. Spring AOT can analyze the bean relationships and generate the corresponding initialization code.

This approach fits when:

- The plugin list is fixed at build time.
- Each plugin can be a Spring bean.
- Selection only needs a key such as `csv` or `pdf`.
- Loading new classes/JARs after the native executable is released is not required.

If the product genuinely requires loading new plugins from JAR files or an extended classpath after build time, that is a different model from closed-world Native Image. Simply adding reflection hints cannot bring arbitrary bytecode absent at build time into a native executable. Design an appropriate extension boundary, such as a separate plugin process or a different deployment mechanism.

## 11. Common Mistakes When Scoping Reflection

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Class registered, yet `newInstance()` still fails | Missing hint for the specific constructor | Check parameter types and `ExecutableMode.INVOKE` |
| Method registered, yet overload still fails | Hint does not match actual parameter signature | Verify method name and all parameter types |
| One method works, another fails | Only the registered method has metadata | Add the exact method called; do not enable the entire type |
| Field readable on JVM, fails on native | Missing field reflection hint or framework binding metadata | Identify code using `Field.get/set`, then register the specific field |
| Hint added, yet native behaves unchanged | Registrar not discovered by AOT or build used stale output | Check bean/`@ImportRuntimeHints`, AOT profile, and clean build |
| Agent test does not record application code | Agent only instruments default packages | Configure package instrumentation for application packages |
| Agent test passes, yet production still fails | Tests did not exercise production branch or different inputs | Add tests for real formats/profiles/features |
| GraalVM tracing agent generates huge JSON | Agent observed test frameworks, libraries, and non-production branches | Review, remove test-only metadata, and narrow per type/member |
| Metadata duplicates dependency | Library already supplies reachability metadata/hints | Check dependency metadata before registering manually again |
| Package scan misleads learners into thinking all classes have reflection enabled | Confusing `@ReflectiveScan` with registering all members | Remember scanning only finds elements marked with `@Reflective` |
| Native executable still does not load new plugin | Plugin JAR was not on the classpath at build time | Keep plugin set fixed or design extensions via another process |

## 12. Practical Workflow from Error to Minimal Metadata

When a reflection branch fails, proceed in order:

1. **Reproduce the error:** record the exact request, property, profile, and stack trace.
2. **Trace the caller:** identify which reflection API was called and which class/member is the target.
3. **Check existing metadata:** see if Spring AOT, Spring/third-party hints, and classpath metadata already cover it.
4. **Document the access table:** class lookup, constructor lookup/invoke, method lookup/invoke, field read/write.
5. **Register minimally:** add only the exact class/member with required signature and mode.
6. **Unit test the registrar:** check hints via `RuntimeHintsPredicates`.
7. **Behavior-based testing:** use the Spring RuntimeHints Agent to compare real invocations against hints.
8. **Build and run native:** test the failing branch itself, plus all remaining branches in the feature list.
9. **Review size/scope:** remove redundant registrations once confirmed unnecessary.

A good metadata change should explain: **which call caused the error, which member lacked a hint, and why the added entry is the smallest scope satisfying that call**.

## 13. Practice Exercises

### Exercise A — Inventory Plugin Call Paths

Given an application with two CSV/PDF plugins, read the registry code and list every reflection call in order. For each call, record the class, constructor/method/field, parameter types, and required mode.

**Completion criteria:** produce a call-path table showing which classes can be selected and why those classes must be on the classpath at build time.

### Exercise B — Compare Narrow Hints and Broad Hints

Write two registrars: one using `withConstructor` and `withMethod` for exact signatures; another using `INVOKE_DECLARED_METHODS`. Inspect both hint sets and explain which one reflects the use case more accurately and which one could permit unnecessary access.

### Exercise C — Use the RuntimeHints Agent

Configure `spring-core-test` and the RuntimeHints Agent for your application package. Run the CSV test, then add the PDF test. Observe the difference in invocation records and verify both sets are covered by hints.

**Question:** why can a test running only CSV never prove that PDF already has sufficient reflection metadata?

### Exercise D — Try the Tracing Agent and Native Image

Run the test suite with the GraalVM tracing agent, review the JSON metadata, and compare it with your existing registrar. Build native with the exact reachability metadata mode appropriate for your version, run critical tests, and record any missing-registration reports.

**Completion criteria:** have test logs, a list of retained metadata, and proof that the native executable runs both plugins.

## 14. Pre-Handoff Checklist

- [ ] Located the reflection APIs actually invoked in code/dependencies.
- [ ] Identified where class names come from and the selectable set of classes.
- [ ] Listed constructors/methods/fields with signatures and required operations.
- [ ] Checked hints already provided by Spring and libraries.
- [ ] Registrar registers only needed types/members.
- [ ] Did not use package-wide scanning as a substitute for identifying access paths.
- [ ] Unit tests confirm the registrar produces expected hints.
- [ ] RuntimeHints Agent or tracing agent ran on all supported branches.
- [ ] Remembered that agents only observe executed code paths.
- [ ] Native executable built and tested directly against the reflection branches.

## References

- [Spring Framework Reference — Ahead of Time Optimizations, Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): `RuntimeHints` API, `@Reflective`, `@ReflectiveScan`, `@RegisterReflection`, RuntimeHints Agent, and invocation testing.
- [Spring Boot Reference — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): registering custom reflection hints with `RuntimeHintsRegistrar`.
- [Spring Framework Javadoc — TypeHint.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/TypeHint.Builder.html): `withConstructor`, `withMethod`, `withField`, and `withMembers`.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): reflection metadata, dynamically accessed members, tracing agent, and exact reachability metadata.

## Conclusion

For Native Image to support reflection reliably, start from **actual access paths**: which class is looked up, which constructor is instantiated, which method is invoked, and which field is read/written. Spring `RuntimeHints` lets you declare exact types/members and signatures; `RuntimeHintsPredicates`, the Spring RuntimeHints Agent, and the GraalVM tracing agent help verify metadata based on executed operations. Tracing tools do not prove unexecuted branches, so combine them with tests covering business scenarios. When the plugin set is fixed, consider replacing reflection with a Spring bean registry so Spring AOT can process direct relationships and reduce manual metadata needs.

