# Separating Lightweight Metadata Inspection from Expensive Provider Initialization

## 1. The Problem When Selecting Providers

In a plugin architecture, a host often discovers many **providers** (classes implementing an extension contract), yet only needs to use one or a few. If the host instantiates every object just to ask whether it fits, discovery can inadvertently:

- Open network or database connections inside constructors.
- Initialize native libraries, thread pools, caches, or read large configurations.
- Trigger side effects before the user selects a feature.
- Slow down startup or fail because of an unselected plugin.
- Make it hard to reclaim resources allocated for skipped providers.

Wrong instantiation-timing example:

\`\`\`java
for (MessageProvider provider : ServiceLoader.load(MessageProvider.class)) {
    if (provider.id().equals(requestedId)) {
        return provider;
    }
}
\`\`\`

This loop calls \`ServiceLoader\`'s \`iterator()\` and requests **instances**. To reach the matching provider, it may instantiate every provider preceding it in iteration order. If constructors are costly, checking \`id()\` alone creates unnecessary work.

Goal: separate **discovery and lightweight metadata inspection** from **activation and resource allocation**. The host should select based on information that does not require a full object, and instantiate only the winning provider when truly needed.

## 2. Three Layers of Activity to Distinguish

| Phase | Work to perform | Should real providers be instantiated? |
|---|---|---|
| **Discovery** | Find providers registered in JARs/modules, obtain class names or supplier info | Not yet |
| **Selection** | Inspect metadata: ID, feature type, version, capability, priority, policy | Usually not |
| **Activation** | Create instance, load config, open connections, execute work, release resources per lifecycle | Yes, for the selected provider |

Not all metadata is built into Java SPI. Classpath \`META-INF/services\` only lists provider class names; it does **not** inherently provide fields like \`id\`, \`priority\`, or \`capabilities\`. To select on those criteria before instantiation, the host and plugin authors must agree on a description mechanism: runtime-retained annotations, dedicated manifests/descriptors, registries, or module descriptors and type-identification rules.

One further distinction: **not instantiating** does not mean **not loading or verifying classes**. Discovery and metadata access can still trigger class loading/linkage, module configuration processing, or provider errors; therefore, error handling is still required during discovery.

## 3. Java 9+ Mechanism: ServiceLoader.Provider

Since Java 9, \`ServiceLoader.stream()\` returns \`ServiceLoader.Provider<S>\` elements, enabling:

- \`Provider.type()\`: inspect the provider type (\`Class\` object) to check annotations or class name.
- \`Provider.get()\`: request a provider instance once selected.

Example:

\`\`\`java
ServiceLoader<MyService> loader = ServiceLoader.load(MyService.class);

MyService selected = loader.stream()
    .filter(p -> p.type().isAnnotationPresent(MyPlugin.class))
    .findFirst()
    .orElseThrow()
    .get();
\`\`\`

The difference from \`for (MyService instance : loader)\` is that filtering via \`type()\` does not call \`get()\` for skipped providers. **Note:** \`get()\` is the point where an instance is requested; \`ServiceLoader\` may cache instances it has created across traversals depending on usage, so do not assume every \`get()\` always creates a new object. When working with module provider factories, \`type()\` may describe the factory's return type; annotations and metadata rules must match the provider style the application supports.

### Metadata via Annotations

Define the annotation:

\`\`\`java
package example.api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface PluginInfo {
    String id();
    String category();
    int priority() default 0;
}
\`\`\`

Place the annotation on the implementation class:

\`\`\`java
@PluginInfo(id = "uppercase", category = "text", priority = 10)
public final class UppercaseProvider implements TextProvider {
    // Only initialize required resources when the provider is used.
}
\`\`\`

The host can read \`p.type().getAnnotation(PluginInfo.class)\` during selection. The annotation must have \`RUNTIME\` retention; if \`SOURCE\` or \`CLASS\` is used, runtime reflection cannot find it. Annotation metadata comes from plugin code and must not be trusted blindly: the host must validate values and enforce the selection policy.

## 4. Complete Example, Runnable on Java 17+

The following example places all classes in **a single file** \`Demo.java\` for easy compilation, while using a separate SPI file. In a real application, the contract lives in an API JAR, and the host and implementations live in separate JARs; the selection principle stays the same.

Structure:

\`\`\`text
demo/
├── Demo.java
└── META-INF/
    └── services/
        └── Demo$TextProvider
\`\`\`

### Source Code Demo.java

\`\`\`java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;

public class Demo {
    @Retention(RetentionPolicy.RUNTIME)
    public @interface PluginInfo {
        String id();
        String category();
        int priority() default 0;
    }

    public interface TextProvider {
        String transform(String text);
    }

    @PluginInfo(id = "lowercase", category = "text", priority = 1)
    public static final class LowercaseProvider implements TextProvider {
        public LowercaseProvider() {
            System.out.println("init lowercase");
        }

        @Override
        public String transform(String text) {
            return text.toLowerCase(java.util.Locale.ROOT);
        }
    }

    @PluginInfo(id = "uppercase", category = "text", priority = 10)
    public static final class UppercaseProvider implements TextProvider {
        public UppercaseProvider() {
            System.out.println("init uppercase");
        }

        @Override
        public String transform(String text) {
            return text.toUpperCase(java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        ServiceLoader<TextProvider> loader = ServiceLoader.load(TextProvider.class);

        List<ServiceLoader.Provider<TextProvider>> candidates = loader.stream()
                .filter(p -> {
                    PluginInfo info = p.type().getAnnotation(PluginInfo.class);
                    return info != null && info.category().equals("text");
                })
                .toList();

        System.out.println("discovered: " + candidates.size());

        ServiceLoader.Provider<TextProvider> chosen = candidates.stream()
                .max(Comparator.comparingInt(
                        p -> p.type().getAnnotation(PluginInfo.class).priority()))
                .orElseThrow(() -> new IllegalStateException("No provider"));

        System.out.println("selected: "
                + chosen.type().getAnnotation(PluginInfo.class).id());

        TextProvider provider = chosen.get();
        System.out.println("result: " + provider.transform("HeLLo"));
    }
}
\`\`\`

The \`META-INF/services/Demo$TextProvider\` file contains two lines:

\`\`\`text
Demo$LowercaseProvider
Demo$UppercaseProvider
\`\`\`

Because the nested classes are \`public static\`, their binary names contain the \`$\` symbol. The service descriptor filename must also be the **binary name** of the service interface, namely \`Demo$TextProvider\`; do not use the source-style name \`Demo.TextProvider\`.

Compile and run from the \`demo/\` directory:

\`\`\`bash
javac -encoding UTF-8 Demo.java
java -cp . Demo
\`\`\`

Exact output:

\`\`\`text
discovered: 2
selected: uppercase
init uppercase
result: HELLO
\`\`\`

What to observe: there is no \`init lowercase\` line. Both providers were discovered and had their annotations read, but only the provider with the highest \`priority\` was instantiated.

In this example, \`Demo.java\` compiles into multiple \`.class\` files (including nested classes). The \`META-INF/services\` directory is a **runtime resource**, not an output of \`javac\`; when packaging into a JAR, you must place the descriptor in the right location. To inspect the full JAR after packaging:

\`\`\`bash
jar --create --file demo.jar \
  -C . 'Demo.class' \
  -C . 'Demo$PluginInfo.class' \
  -C . 'Demo$TextProvider.class' \
  -C . 'Demo$LowercaseProvider.class' \
  -C . 'Demo$UppercaseProvider.class' \
  -C . META-INF/services
jar --list --file demo.jar
java -cp demo.jar Demo
\`\`\`

The \`jar\` commands above use POSIX shell quoting for filenames containing \`$\`. On Windows, you can replace packaging by putting the class files and descriptor into a staging directory and running \`jar --create --file demo.jar -C staging .\`, ensuring staging contains the exact listed files.

## 5. When Is Metadata Truly “Lightweight”?

Reading annotations via reflection is usually cheaper than instantiating a provider with external connections, yet it still incurs class loading, annotation lookup, and class type-dependency costs. To optimize, choose the right level:

| Description approach | Advantages | Limitations |
|---|---|---|
| \`Provider.type()\` + annotation | Avoids instantiation, keeps metadata close to implementation | Involves class loading/reflection; compatibility must be controlled |
| Standalone descriptor (JSON/YAML/properties) | Can read descriptions before loading plugin classes | Needs schema, versioning, validation, and avoiding stale metadata |
| Build-generated registry | Fast ID/capability lookup, convenient pre-validation | Needs a pipeline ensuring metadata and classes stay in sync |
| Lightweight provider factory | Allows choosing a factory before creating heavy products | The SPI factory/provider itself may still be instantiated |
| Instantiate every provider then ask \`id()\` | Simple API | Wastes resources, causes side effects, and risks unnecessary failures |

If an application has hundreds of plugins, standalone metadata can allow displaying a list without triggering plugin class loaders. An illustrative file:

\`\`\`properties
plugin.id=uppercase
plugin.category=text
plugin.priority=10
plugin.implementation=example.plugin.UppercaseProvider
plugin.apiVersion=1
\`\`\`

This is an **application-defined convention**, not a Java SPI standard. The host must validate ID uniqueness, \`priority\` values, API version, implementation name, consistency between descriptor and reality, and plugin provenance before deciding to activate.

## 6. Do Not Confuse Provider Selection with Resource Initialization

Even when \`Provider.get()\` creates an instance, the constructor does not have to open all resources. A maintainable design lets the constructor accept only configuration and dependencies; actual activation uses explicit lifecycle methods:

\`\`\`java
public interface ManagedPlugin extends AutoCloseable {
    void start();
    void execute();
    @Override void close();
}
\`\`\`

The snippet above is **an illustrative contract**, not a standalone runnable program. The host selects an implementation via metadata, calls \`get()\`, and then calls \`start()\` at the right time. Upon completion, the host calls \`close()\` in \`finally\` or uses \`try-with-resources\` if the lifecycle fits. Constructors should avoid opening database connections or starting threads prematurely; \`start()\` should fail clearly, and \`close()\` must release allocated resources even on partial activation failure.

When providers manage expensive connections or non-thread-safe state, define who owns the object, whether it is reused, whether concurrent access is valid, and when it stops. \`ServiceLoader\` does not replace lifecycle management.

## 7. Selection Rules for Deterministic Outcomes

Using \`max(priority)\` above suffices when priorities differ, but real systems need rules for equal priorities:

1. **Filter capabilities and compatibility**: exclude providers of the wrong category, missing features, or incompatible API/runtime versions.
2. **Apply policy**: allow/deny lists, permissions, or host configuration.
3. **Rank explicitly**: compare priority, then use unique ID as a tie-breaker. Do not treat \`ServiceLoader\` discovery order as business semantics.
4. **Activate only the selected provider**: call \`get()\` after selection; on error, log the cause and apply an explicit fallback policy.
5. **Observability**: log ID, version, selection/rejection reason, and activation duration, avoiding logging secrets.

For example, the host can sort by descending priority and then ascending ID as a tie-breaker:

\`\`\`java
Comparator<ServiceLoader.Provider<TextProvider>> ranking =
    Comparator.<ServiceLoader.Provider<TextProvider>>comparingInt(
        p -> p.type().getAnnotation(PluginInfo.class).priority())
        .reversed()
        .thenComparing(
            p -> p.type().getAnnotation(PluginInfo.class).id());
\`\`\`

This is an **illustrative snippet in the context of Demo.java**, not standalone source. After sorting \`candidates.stream().sorted(ranking).findFirst()\`, the host gets the highest-priority provider; on a tie, it picks the lexicographically first ID. When metadata comes from untrusted plugins, check that the annotation exists and is valid before running the comparator to avoid unexpected errors.

## 8. Common Errors and How to Handle Them

| Error | Cause | Fix |
|---|---|---|
| Provider not found | Missing \`META-INF/services\` file, wrong binary name, plugin JAR not on classpath/module layer | Check descriptor, JAR, and class loader |
| Provider instantiated during filtering | Iterating \`ServiceLoader<T>\` directly to get instances and calling \`id()\` | Iterate \`loader.stream()\`, read metadata via \`Provider.type()\` |
| \`getAnnotation(...)\` returns \`null\` | Annotation lacks \`RUNTIME\` retention or provider class lacks annotation | Declare proper retention and check for \`null\` |
| Provider fails even before calling \`get()\` | Class loading, linkage, SPI config, or metadata error | Catch and handle discovery/validation errors; do not assume discovery is free |
| Wrong provider chosen on equal priority | Relying on iteration order without a business contract | Sort with a stable tie-breaker |
| Descriptor says one thing, class does another | Metadata written manually without synchronization | Validate at build time and load time, use explicit schema/version |
| Initialization cost remains high | Constructor does heavy work immediately when \`get()\` is called | Separate constructor from \`start()\`; manage lifecycle separately |
| Duplicated/broken plugin API | Host and plugin see different versions of the contract | Share the API JAR properly, control class loaders and compatibility |

## 9. Properly Testing Both Phases

A minimal test suite should verify:

- **Discovery without activation**: when calling only \`stream()\`, \`type()\`, reading annotations, and selecting, constructors of unselected providers have not run.
- **Exact activation**: only \`get()\` of the selected provider is called; execution produces the right result and resource lifecycle is verified.
- **No matching provider**: the host returns a semantic error or defined fallback without instantiating all providers.
- **Invalid metadata**: missing annotations, duplicate IDs, invalid priority, incompatible version.
- **Failing providers**: SPI errors (\`ServiceConfigurationError\`) and initialization/activation errors do not blind the host's diagnostics.
- **Multiple providers**: repeated selection yields deterministic results per the published rules, independent of JAR order.

You can time discovery and activation separately (for example via \`System.nanoTime()\`) to catch slow constructors. When benchmarking, warm up the JVM and distinguish first-time class loading cost from steady-state cost; a single measurement is insufficient to draw performance conclusions.

## 10. Design Summary

In a runtime extensibility system, **metadata serves decision-making**, while **instances serve execution**. The decision step should have as few side effects as possible; the execution step should have explicit lifecycle, error, and resource management. On Java 17+, \`ServiceLoader.Provider.type()\` helps filter by type/annotation before calling \`get()\`, provided the metadata fits and the host handles discovery limitations. If you must browse a very large plugin catalog without loading classes, extract metadata into external descriptors and load providers only after selection.