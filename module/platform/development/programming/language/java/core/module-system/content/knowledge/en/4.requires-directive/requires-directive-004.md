# requires static for Compile-Time-Only Dependencies

In the Java Platform Module System (JPMS), the **requires static** directive is used to declare a dependency that must be present at compile time but may be absent at runtime. This is the way to describe libraries supporting compile-time tasks, such as annotations, metadata, or optional integrations that the application does not need to load on every run.

The key point is that the static keyword only makes the dependency optional at runtime. It does not make the dependency optional at compile time, does not automatically download the library when needed, and does not protect code from linkage errors if the program actually uses classes from an absent dependency.

## 1. Syntax and Meaning

Syntax in module-info.java:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

The orders module needs to read the annotations module to compile. At launch, the module resolver is not required to find annotations solely because requires static is declared.

Comparison with regular requires:

| Declaration | At compile time | At runtime |
| --- | --- | --- |
| requires module.name | The dependency must be present and resolved | The dependency must be present for the module to be resolved. |
| requires static module.name | The dependency must be present and resolved | The dependency may be absent if not required by another relationship. |

Example:

~~~java
module com.example.orders {
    requires com.example.customer.api;
    requires static com.example.annotations;
}
~~~

Here:

- com.example.customer.api is a regular dependency. Without it, the orders module cannot be resolved properly.
- com.example.annotations is a compile-time dependency. It must be on the module path when compiling orders, but may not be needed in the runtime configuration.

requires static still establishes a module readability relationship during compilation. Therefore, source code can reference types belonging to that dependency and the compiler can still check them.

## 2. Why are compile-time-only dependencies needed?

Not every library appearing in source code needs to be packaged with the application at runtime. Some dependencies only provide information to the compiler or build tools.

Common cases:

- **Compile-time annotations:** mark code for processing by the compiler, annotation processors, or code generation tools.
- **Metadata:** provide types or descriptive information used only during compilation.
- **Optional integrations:** a module can compile against an extended API while a minimal runtime run does not activate that integration part.
- **Supporting APIs:** a library needs to know a type at compile time, while the runtime implementation is supplied by another environment or is not used in a minimal configuration.

Example of an annotation marking classes that need to be processed by a build tool:

~~~java
package com.example.annotations;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
public @interface GenerateMetadata {
}
~~~

Module using the annotation:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

Class inside the module:

~~~java
package com.example.orders.model;

import com.example.annotations.GenerateMetadata;

@GenerateMetadata
public class Order {
    private long id;
}
~~~

The compiler needs to see the GenerateMetadata type to verify the source code. If the annotation has CLASS retention, annotation metadata is stored in bytecode but does not require the application to read the annotation via reflection at runtime.

If a runtime tool needs to find and process that annotation, the dependency containing the annotation must be present at runtime and the package/type must be accessible according to the corresponding rules. requires static does not make a runtime annotation appear automatically once its JAR has been excluded from the run configuration.

## 3. The dependency is still mandatory at compile time

A common misconception is using requires static to skip a missing library during a build. That is incorrect.

At compile time, the module declared after requires static must still be observable on the module path. For example:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

If the compiler cannot find com.example.annotations, compilation will report a module not found error.

The compile command can specify the module path explicitly:

~~~bash
javac --module-path libs --module-source-path src -d out -m com.example.orders
~~~

In this command, the libs directory must contain the annotations module or a JAR that can be recognized as an appropriate module.

You can check the module name of a JAR:

~~~bash
jar --describe-module --file libs/example-annotations.jar
~~~

Do not guess the module name from the file name. For a modular JAR, the name is declared in module-info.class; for an automatic module, the name may come from Automatic-Module-Name or be derived from the JAR name.

## 4. In what cases can a dependency be absent at runtime?

Suppose an application only uses annotations to mark code and does not need to read annotations at runtime. In that case, the annotation dependency can be omitted from the runtime image.

Module configuration:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

At compile time, annotations must be present. At runtime, if annotations is not required by another module and is not added as a root module, the resolver can omit this static dependency.

That does not mean every reference to types in the dependency is safe when the library is excluded from runtime. If the program actually needs to load, link, initialize, or call a type belonging to the missing dependency, errors such as NoClassDefFoundError or ClassNotFoundException may occur.

For example, the following code snippet has a direct reference to a class from a dependency:

~~~java
package com.example.orders;

import com.example.optional.Client;

public class OptionalGateway {
    public void connect() {
        Client client = new Client();
        client.open();
    }
}
~~~

If the module containing Client is absent at runtime yet the connect branch is still executed, the application cannot execute that call. requires static does not automatically make calls optional.

To make an integration genuinely toggleable, you need to design a separate execution path: extract the implementation into an adapter module, check for the presence of the implementation, or use an SPI. You should not let core code always directly call classes that exist only in an optional dependency.

## 5. requires static and annotations

Annotations are the most common case because many annotations only serve the compiler or code analysis tools.

Example:

~~~java
module com.example.domain {
    requires static com.example.validation.annotations;
}
~~~

A class using the annotation:

~~~java
package com.example.domain.model;

import com.example.validation.NotBlank;

public class Customer {
    @NotBlank
    private String name;
}
~~~

If the annotation is only read at compile time or by post-compile bytecode processing tools, the application may not need the annotation library in the runtime image.

Retention policies must be distinguished:

| Retention | Where the annotation is stored | Usability |
| --- | --- | --- |
| SOURCE | Only in source code, discarded from bytecode | Processed by the compiler or annotation processors during compilation. |
| CLASS | Stored in the class file, does not require runtime reflection visibility | Tools reading bytecode can process it after compilation. |
| RUNTIME | Stored in the class file and readable via reflection | If the application/framework needs to read the annotation, the annotation type must be available and accessible at runtime. |

If an annotation has RetentionPolicy.RUNTIME and a framework uses reflection to find annotations, do not exclude the annotation library from runtime without checking the framework's behavior. A compile-time-only dependency is only appropriate when the runtime execution does not need to load that annotation type.

An annotation processor is also a tool running inside the compiler process. Processor dependencies and production code dependencies may be two different groups; do not confuse requires static in the application's module descriptor with the build tool's processor path configuration.

## 6. requires static combined with transitive

The two modifiers can be combined:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
}
~~~

The two modifiers have distinct meanings:

- **static:** the dependency is mandatory at compile time but optional at runtime.
- **transitive:** propagates the readability relationship to modules reading the current module in the corresponding resolution context.

This declaration is appropriate when types from the dependency appear in the public API and the dependency is only needed at compile time.

Example of an API library using annotations to mark return types or parameters:

~~~java
module com.example.customer.api {
    requires static transitive com.example.contract.annotations;
    exports com.example.customer.api;
}
~~~

Modules compiling against customer.api can read contract.annotations through the transitive relationship. However, if the annotation is not needed at runtime, the runtime configuration can still omit that module.

Use this combined form only when both intents are true. If the dependency is only used internally and is not part of the public API, regular requires static is sufficient.

## 7. Differences from other ways of marking optional dependencies

requires static is a JPMS directive in the module descriptor. It describes relationships between modules at the Java platform level.

Build tools have their own dependency configurations. For example, Gradle has the compileOnly configuration to provide a dependency during compilation without placing it on the default runtime classpath. When using modular JARs, the build configuration and the module descriptor must be consistent: the compiler needs to see the module on the module path to satisfy requires static.

In Maven, an optional dependency controls whether a dependency is transitively propagated to consumers of the artifact; it is not directly synonymous with requires static. The provided scope also has its own distribution and runtime rules. Inspect the actual dependency graph and classpath/module path rather than inferring solely from configuration names.

A short checklist:

- The module descriptor has requires static for compile-time-only dependencies.
- The build tool provides that dependency on the compile module path.
- The runtime configuration excludes the dependency when it is genuinely unnecessary.
- Executed code does not directly call classes belonging to the excluded dependency.
- Annotations/frameworks do not need to read annotation types at runtime when the dependency is absent.

## 8. When an optional dependency needs to be used at runtime

If an optional feature needs to call a library at runtime, there are several design approaches.

### Approach A: Extract the adapter into a separate module

Keep the core module independent of the optional library:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Create an adapter:

~~~java
module com.example.orders.audit {
    requires com.example.orders;
    requires com.example.audit.client;
}
~~~

Only applications needing auditing add the adapter module to runtime. This approach keeps dependencies clear and avoids having core classes directly reference optional APIs.

### Approach B: Use SPI

The core module declares an interface it owns itself, and consumers/providers are connected via uses and provides. The adapter module depends on the external library and provides an implementation of that interface.

As a result, the core module only knows the service contract. When no provider is installed, the application can disable the optional feature without needing to load classes of the external library.

### Approach C: Load classes on demand

Some integrations may check for class presence using reflection or a class loader. This approach suits very small adapters, but requires handling class names, class loaders, module readability, and initialization errors. Class.forName should not be treated as a general solution for all optional dependencies.

In a modular system, extracting an adapter or using an SPI usually describes dependencies more clearly than scattering reflection checks throughout business code.

## 9. Common Errors with requires static

| Symptom | Cause | Resolution |
| --- | --- | --- |
| module not found during compile | The static dependency is not on the module path at compile time | Add the dependency to the compile module path. |
| NoClassDefFoundError at runtime | An executed code branch used a class belonging to an excluded dependency | Include the dependency at runtime or separate the optional execution path. |
| Annotation not recognized by framework | The annotation dependency is absent at runtime or retention is inappropriate | Check retention and the framework's runtime configuration. |
| Consumer cannot see types in API | Missing exports or readability | Check requires and exports in both modules. |
| Dependency still appears at runtime | It is required by another module or added as a root module | Check module resolution and the runtime dependency graph. |

A dependency declared static can still appear at runtime if it is required via another path or explicitly included in the launch configuration. The static keyword is not a command to strip a JAR from every runtime image.

## 10. Verifying Compile-Time and Runtime Behavior

Use the describe JAR command to confirm the module name:

~~~bash
jar --describe-module --file libs/example-annotations.jar
~~~

Compile the module with the dependency present on the module path:

~~~bash
javac --module-path libs --module-source-path src -d out -m com.example.orders
~~~

List modules in the runtime:

~~~bash
java --list-modules
~~~

Observe module resolution when running the application:

~~~bash
java --show-module-resolution --module-path out -m com.example.orders/com.example.orders.Main
~~~

If the static dependency is absent, verify that the application still runs on the intended launch command and that optional code paths are not invoked. If the dependency appears because another module requires it, re-check the module graph to see the actual dependency path.

## 11. Usage Principles

- Use requires static when a dependency is needed at compile time but not mandatory for the application configuration's runtime.
- Ensure the dependency is still present on the module path during compilation.
- Do not use static to hide a missing dependency in the build.
- Do not directly call optional classes on an execution path that can be triggered when the dependency is absent.
- For annotations, check retention and whether a framework reads the annotation via reflection at runtime.
- Use requires static transitive when a dependency is both optional at runtime and part of the API contract requiring readability propagation.
- For toggleable runtime integrations, prefer extracting adapters or using SPI so dependencies do not leak into the core module.

The value of requires static lies in accurately describing when a dependency is mandatory. When compile time and runtime are clearly designed, a project can retain supporting tools and optional integrations without forcing every runtime configuration to carry them.