# requires static in the Java Module System

The Java Platform Module System (JPMS) allows a module to declare another module as a dependency using the `requires` directive in `module-info.java`. Normally, a required dependency must be present both at compile time and at runtime. However, some libraries are only needed so the compiler can understand types, annotations, or extension APIs; the application still needs to run when that library is not installed.

The `requires static` directive solves this case: the dependent module is mandatory during compilation but can be absent from the module graph at runtime. This is JPMS's mechanism for declaring optional dependencies, not a mechanism that automatically downloads libraries or creates fallbacks for your code.

## 1. Syntax and Semantics

Declared in `module-info.java`:

~~~java
module com.example.app {
    requires static com.example.metrics;
}
~~~

The `com.example.app` module needs the `com.example.metrics` module to compile. At runtime, `com.example.metrics` might not be resolved into the runtime module graph.

This can be understood across two phases:

| Phase | Behavior of requires static |
|---|---|
| Compile time | The required module must be observable and readable; the compiler needs it to resolve types and type-check code |
| Runtime | The module is not required to be resolved; the application can still start if the dependency is absent |
| When the dependency is resolved by other means | The requiring module gets a readability edge to the dependency and can use its types |
| When code actually needs a type but the dependency is not resolved | Linkage errors such as `NoClassDefFoundError` may occur |

`static` here is a modifier on the `requires` directive. It is not the `static` keyword used to declare fields, methods, or nested classes.

## 2. Comparing requires, requires transitive, and requires static

The three common forms serve different purposes:

| Directive | Mandatory at compile time | Mandatory at runtime | Grants readability to dependent modules |
|---|---|---|---|
| `requires B;` | Yes | Yes | No |
| `requires transitive B;` | Yes | Yes | Yes |
| `requires static B;` | Yes | No | No |
| `requires static transitive B;` | Yes | No | Yes |

- `requires B` declares a standard dependency. If module B is not in the runtime module graph, module resolution may fail.
- `requires transitive B` additionally allows modules that read the current module to read B via implied readability.
- `requires static B` keeps the requirement at compile time and allows B to be absent at runtime.
- `requires static transitive B` combines both modifiers: B is mandatory at compile time, the dependency is propagated to downstream modules at compile time, yet it remains optional at runtime.

Do not add `transitive` just to make a dependency optional. Use it when types from module B appear in an API that other modules need to compile against when using the current module's API.

## 3. Two Phases of Module Resolution

JPMS builds the module graph from root modules and their `requires` directives. Each readability edge indicates whether one module can read the exported types of another module.

### 3.1. At Compile Time

With `requires static B`, module B must be observable in the compilation environment. The compiler needs to read B's descriptor, know which packages are exported, and resolve the types referenced in source code.

If B is not on the module path or does not export a package that the code needs to use, the compiler reports an error. `static` does not make the dependency optional at compile time.

### 3.2. At Runtime

When the runtime resolves the module graph, the `requires static` directive does not by itself ask the runtime to locate module B. Therefore:

- B can be absent from the module path and the application will still start.
- B can be present on the module path and still not be included in the module graph merely because `requires static` mentions it.
- B will be resolved if it is pulled into the graph by another mandatory dependency or explicitly added with `--add-modules`.
- Once B is resolved by one of those means, the module with `requires static B` can read B.

This is the easiest point to get confused about: **having a JAR file on the module path does not mean that module has been resolved**.

## 4. Complete Example with an Optional Dependency

Let us build two modules:

- `com.example.app`: the main application, which can run in core mode.
- `com.example.metrics`: an extension library providing metrics information.

When the metrics module is resolved, the application calls the integration. When it is not resolved, the application runs in core mode.

### 4.1. Directory Structure

~~~text
project/
└── src/
    ├── com.example.app/
    │   ├── module-info.java
    │   └── com/example/app/
    │       ├── Main.java
    │       └── MetricsBridge.java
    └── com.example.metrics/
        ├── module-info.java
        └── com/example/metrics/
            └── Metrics.java
~~~

### 4.2. Declaring the metrics Module

File `src/com.example.metrics/module-info.java`:

~~~java
module com.example.metrics {
    exports com.example.metrics;
}
~~~

File `src/com.example.metrics/com/example/metrics/Metrics.java`:

~~~java
package com.example.metrics;

public final class Metrics {
    private Metrics() {
    }

    public static String summary() {
        return "metrics enabled";
    }
}
~~~

The `com.example.metrics` package is exported so other modules can use the `Metrics` type.

### 4.3. Declaring the Application Module

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires static com.example.metrics;
}
~~~

The application module can compile against the metrics API, without requiring the runtime to resolve that module.

### 4.4. Isolating the Optional Integration

File `src/com.example.app/com/example/app/MetricsBridge.java`:

~~~java
package com.example.app;

import com.example.metrics.Metrics;

public final class MetricsBridge {
    private MetricsBridge() {
    }

    public static String summary() {
        return Metrics.summary();
    }
}
~~~

The `MetricsBridge` class directly references the optional module. Therefore, this class should only be loaded when the metrics module is actually present in the runtime graph.

### 4.5. Checking Presence Before Loading the Integration

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        boolean metricsResolved = ModuleLayer.boot()
                .findModule("com.example.metrics")
                .isPresent();

        if (!metricsResolved) {
            System.out.println("Optional metrics not resolved; core mode");
            return;
        }

        Class<?> bridge = Class.forName("com.example.app.MetricsBridge");
        String summary = (String) bridge.getMethod("summary").invoke(null);
        System.out.println("Optional metrics: " + summary);
    }
}
~~~

`Main` inspects the module graph using `ModuleLayer.boot().findModule(...)`. It only loads `MetricsBridge` via reflection after confirming the metrics module has been resolved. Because `Main` has no direct type references to `Metrics` or `MetricsBridge`, the core startup path does not force the JVM to load the optional integration class.

### 4.6. Compiling Both Modules

Run from the `project` directory:

~~~bash
javac --module-source-path src -d mods -m com.example.metrics,com.example.app
~~~

The command compiles both modules in a single pass. The metrics module must be present on the source/module path at this stage because the application declares `requires static` and `MetricsBridge` uses the `Metrics` type.

After compilation, the output structure:

~~~text
mods/
├── com.example.app/
│   ├── module-info.class
│   └── com/example/app/
│       ├── Main.class
│       └── MetricsBridge.class
└── com.example.metrics/
    ├── module-info.class
    └── com/example/metrics/
        └── Metrics.class
~~~

### 4.7. Running Without Resolving the Optional Module

Run the application normally:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Even though the metrics module is on the module path, it is not resolved merely because the `requires static` directive mentions it.

Stdout:

~~~text
Optional metrics not resolved; core mode
~~~

### 4.8. Running With the Optional Module Resolved

Add the metrics module as a root module with `--add-modules`:

~~~bash
java --module-path mods --add-modules com.example.metrics -m com.example.app/com.example.app.Main
~~~

At that point, metrics is included in the runtime module graph. A readability edge from app to metrics is established, and `MetricsBridge` can be loaded and invoked.

Stdout:

~~~text
Optional metrics: metrics enabled
~~~

This example demonstrates both cases: an unresolved dependency and a dependency resolved by explicit request.

## 5. Why Isolate Code That Uses Optional Dependencies?

`requires static` only makes the module dependency optional during resolution. It does not automatically protect bytecode instructions that need classes from the dependency.

If code calls directly:

~~~java
Metrics.summary();
~~~

in a run where the metrics module is not resolved, the JVM may fail to find the class when linking or executing and throw `NoClassDefFoundError`.

Recommended practices:

1. Put code that directly depends on the optional module into a separate class.
2. Avoid placing optional types in method signatures, fields, or constructors of core startup classes if those classes must work when the dependency is absent.
3. Check whether the module is present in the appropriate layer before loading or invoking the integration.
4. Use reflection or dynamic loading only at the integration boundary, rather than scattering string class names throughout the application.
5. Handle the absent dependency case with clear core behavior.
6. Test both configurations: dependency resolved and dependency unresolved.

Reflection does not by itself make a dependency safe. If you load a class that references a missing type, loading or invocation can still fail. The key is checking the module graph before loading the integration class.

## 6. When to Use requires static?

Several suitable scenarios:

### 6.1. Compile-Time-Only Annotations

An annotation library may only serve the compiler, annotation processors, or build tools. If the application does not need to read those annotations via reflection at runtime, the annotation module can be declared with `requires static`.

Check the annotation's `@Retention` and how the application uses it. If runtime code or a framework needs to load the annotation type to read metadata, the module containing the annotation may still need to be resolved.

### 6.2. Integration with Optional Libraries

An application has core functionality but can be extended when additional libraries are installed:

- An adapter for a specific database vendor.
- Integration with a metrics or tracing library.
- A format converter available only in an extension package.
- Platform- or device-support APIs available only in certain environments.

In these cases, the optional integration needs to be isolated and loaded only when the module is available.

### 6.3. APIs Exposing Types from an Optional Dependency

A library may provide an extension API that uses types from an optional module. When other modules need to read those types during compilation, `requires static transitive` may be needed.

Use this form when the dependency is genuinely part of the API exposed to consumers. If the dependency types are only used internally, `requires static` is usually sufficient and keeps module relationships cleaner.

## 7. Combining static and transitive

Example:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
    exports com.example.api;
}
~~~

Meaning:

- The `com.example.annotations` module must be present when compiling the API module.
- Other modules that read `com.example.api` receive implied readability to `com.example.annotations` during compilation.
- At runtime, the annotations module is still not required to be resolved merely because of this directive.
- If the annotations module is resolved by another dependency or via `--add-modules`, it can participate in the runtime graph.

`transitive` does not make an optional dependency mandatory at runtime when combined with `static`. The two modifiers address separate aspects: propagating readability and when the dependency is required.

## 8. requires static and Maven/Gradle Dependencies

`requires static` lives in the module descriptor. It does not replace build tool dependency configuration.

For example, Maven or Gradle must still provide the required artifact on the module path during compilation. Whether the artifact is packaged into the runtime distribution depends on dependency configuration, packaging, and how the application is deployed.

Keep the responsibilities distinct:

| Component | Responsibility |
|---|---|
| `requires static` in `module-info.java` | Declares the module relationship: required at compile time, optional at runtime |
| Maven/Gradle dependency configuration | Downloads artifacts, selects versions, and places dependencies on the compile/runtime classpath or module path |
| `--module-path` | Tells the compiler/launcher where to find modules |
| `--add-modules` | Instructs the launcher to include specified modules in the runtime graph |

Do not edit only `module-info.java` and forget the build configuration. If the dependency is not on the compile module path, the compiler cannot resolve the types being used.

## 9. Inspecting requires static in the Module Descriptor

You can view the descriptor of a compiled module with:

~~~bash
javap -v mods/com.example.app/module-info.class
~~~

In the `Module` attribute section, look for the `requires` entry corresponding to `com.example.metrics`. The `ACC_STATIC_PHASE` flag indicates a dependency that is mandatory at compile time and optional at runtime. If `transitive` is also present, the descriptor also has the `ACC_TRANSITIVE` flag.

You can observe the module graph at runtime with:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Then add the module explicitly:

~~~bash
java --show-module-resolution --module-path mods --add-modules com.example.metrics -m com.example.app/com.example.app.Main
~~~

Compare the two runs to see that the metrics module only joins the graph when pulled in by another mechanism.

## 10. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `module not found` at compile time | Dependency is not on the compile module path or is not observable | Add the appropriate module/JAR to the compiler's module path |
| Application still reports missing module at runtime | Standard `requires` was used instead of `requires static` | Check the directive in `module-info.java` |
| Module is on the module path but `findModule` returns empty | `requires static` does not automatically resolve the module at runtime | Use `--add-modules` or a mandatory runtime dependency if the design requires it |
| `NoClassDefFoundError` when calling optional functionality | Code loaded or executed a class referencing an unresolved dependency | Check the module graph before loading integration classes; isolate dependent code |
| `IllegalAccessError` or package access error | Module is present, but the needed package is not exported or not read | Check `exports`, readability, and the module descriptor |
| Consumer fails to compile against library API | Types in the API come from a dependency without propagated readability | Consider `requires static transitive` if those types are genuinely part of the API |
| Local build runs, but runtime distribution fails | Dependency is only on the compile path, or packaging differs from expectations | Check Maven/Gradle configuration and the deployment module path |
| Assuming `requires static` provides a built-in fallback | Confusing optional resolution with error handling in code | Write a core code path and check for module presence |

## 11. Limitations to Remember

- `requires static` does not make a dependency optional at compile time.
- A module being on the module path does not mean the runtime has resolved it.
- When a module is resolved by other means, the requiring module can read it via a readability edge.
- Code can still fail if it actually references classes from an absent module.
- The directive does not download libraries, manage versions, or configure Maven/Gradle.
- `requires static` is not synonymous with `requires transitive`; to propagate readability, you must also declare `transitive`.
- `java.base` is the foundational module implicitly required; do not declare `requires static java.base`.
- Only use optional dependencies when the application has clear behavior for when the dependency is unresolved.

## 12. Adoption Workflow

When you want to make a dependency optional at runtime:

1. **Identify the need:** Is the dependency truly needed only at compile time or for an extension feature?
2. **Audit the API:** Which code directly references types from the dependency? Can those classes be loaded independently of startup?
3. **Declare the module:** Use `requires static module.name;`; add `transitive` only when consumers need readability to the dependency.
4. **Configure the build:** Ensure the dependency is present on the module path during compilation.
5. **Isolate the integration:** Separate classes that use the optional dependency.
6. **Check the module graph:** Use `ModuleLayer.findModule` or `--show-module-resolution`.
7. **Run both configurations:** Test when the dependency is absent/unresolved and when it is added with `--add-modules`.
8. **Test for linkage errors:** Verify that the core path does not load optional classes when the module is absent.
9. **Verify packaging:** Confirm that the runtime image or distribution includes the dependency only according to your release policy.

## 13. Key Takeaways

`requires static` declares a module dependency that is mandatory at compile time but optional in the runtime module graph. It is useful for annotations, supporting APIs, and optional integrations. An optional module may sit on the module path and still remain unresolved unless another runtime dependency pulls it in or it is added via `--add-modules`.

To use it safely, isolate code that depends on the optional module, inspect the module graph before loading the integration, and always test both configurations with and without the dependency. When types from the dependency are part of an API that must be passed through to consumers, consider `requires static transitive`; otherwise, use the simpler directive.

References:

- [Java Language Specification, Java SE 21 — 7.7.1 Dependences](https://docs.oracle.com/javase/specs/jls/se21/jls21.pdf)
- [Java SE 21 API — ModuleDescriptor.Requires.Modifier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.Requires.Modifier.html)
- [Dev.java — Optional Dependencies with requires static](https://dev.java/learn/organizing/modules/optional-dependencies/)