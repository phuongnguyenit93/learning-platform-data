# Readability Graph Instead of Classpath Visibility

## 1. Why Does JPMS Change How Dependencies Are Organized?

In traditional Java, applications typically bundle classes and JARs onto the **classpath**. The class loader locates bytecode along the path, while Java code imports public types that the compiler can find and that language access levels allow. This setup is convenient, but boundaries between libraries are not expressed as an explicit dependency structure.

Since Java 9, the **Java Platform Module System (JPMS)** adds **named modules** and **module descriptors**. Each named module explicitly declares which modules it depends on, which packages are exposed to the outside, and which services are used or provided.

The key shift is the **readability graph**. A named module does not automatically gain access to every type in every module just because the JARs are placed on the module path. It must **read** the module containing that type, and the package containing the type must also be appropriately **exported**.

High-level mental model:

~~~text
Traditional classpath
    classpath entries -> class loader searches for classes along the path
    No named module descriptor describing dependencies between JARs

JPMS named modules
    module path + root modules -> module resolution -> module graph
    A module only reads modules according to valid JPMS relationships
    Type access requires both readability and accessibility
~~~

As a result, JPMS makes dependencies more explicit, strengthens encapsulation, and helps catch certain structural errors as early as compile time or module resolution.

## 2. How Does Classpath Visibility Work?

Suppose the classpath contains these libraries:

~~~text
lib/
├── customer-api.jar
├── order-service.jar
└── analytics.jar
~~~

A traditional application is launched with:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

On Windows, the separator when specifying multiple individual paths is a semicolon; wildcard characters for a JAR directory are handled according to the launcher's rules.

When code uses a class, the class loader searches for the class across the configured locations. Within the same class loader/classpath space, a JAR does not need a descriptor declaring that it depends on another JAR. Therefore, a public class from any discoverable dependency can usually be referenced if access modifiers allow it.

Example:

~~~java
package com.acme.app;

import com.acme.customer.api.Customer;
import com.acme.analytics.Report;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("C-1");
        Report.print(customer);
    }
}
~~~

The code can compile as long as the compiler sees the needed classes on the classpath. There is no syntax equivalent to requires in a traditional JAR to express exact dependency relationships.

Common consequences:

- A class can accidentally use the API of a transitive dependency instead of only dependencies directly declared in the build file.
- The classpath can contain multiple versions of a class with the same fully qualified name; search order affects the outcome.
- Accidentally removing or changing a library can produce ClassNotFoundException or NoClassDefFoundError at runtime.
- Internal packages of a library are easily used directly by application code when their classes are public.

Maven or Gradle still manages dependencies at the build level, but the JVM's classpath itself does not represent a dependency graph with module names and requires as JPMS does.

## 3. What Is a Readability Graph?

A **readability graph** represents which module **reads** which module in a resolved JPMS configuration. In a module descriptor, the basic relationship is declared with the **requires** directive.

Example:

~~~java
module com.acme.app {
    requires com.acme.order;
}
~~~

~~~java
module com.acme.order {
    requires com.acme.customer;
}
~~~

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Direct dependency graph:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.order
    |
    | requires
    v
com.acme.customer
~~~

With ordinary requires, app reads order, and order reads customer. **You must not infer that app automatically reads customer just because order reads customer**. Readability does not propagate transitively across every requires edge.

This is a major difference from a shared classpath, where classes from customer-api.jar would already be available to both app and order if all were placed on the classpath together.

For app to use types from customer, there are two design options:

1. App directly declares requires com.acme.customer.
2. Module order uses requires transitive com.acme.customer when customer is part of the API contract that order provides.

## 4. Readability Differs from Package Accessibility

**Being able to read a module (readability)** and **being able to access a type (accessibility)** are two separate conditions.

Consider a library module:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Consumer module:

~~~java
module com.acme.app {
    requires com.acme.customer;
}
~~~

A public type in com.acme.customer.api can be used by app under Java rules:

~~~java
package com.acme.customer.api;

public record Customer(String id) {
}
~~~

However, a public class in a non-exported package is still not public API at the module level:

~~~java
package com.acme.customer.internal;

public final class CustomerCache {
    public static void clear() {
    }
}
~~~

If com.acme.customer.internal is not exported, app cannot access CustomerCache through normal Java calls merely because of requires com.acme.customer.

The conditions for accessing a type in named module B from named module A can be summarized as:

1. A has a read relationship to B.
2. B exports the package containing that type to A (unqualified or qualified exports).
3. The type and member satisfy Java's access modifier rules.
4. The type/class can be resolved by the relevant class-loading system.

Readability opens the path to the module; exports determines which packages cross that boundary. These two mechanisms should not be confused.

## 5. A Sample Project with Three Modules

To see the readability graph clearly, let us build an example with these modules:

- com.acme.model contains the Customer type.
- com.acme.service uses Customer and provides the service API.
- com.acme.app calls the service API and needs to reference the Customer type.

Source tree structure:

~~~text
project/
├── src/
│   ├── com.acme.model/
│   │   ├── module-info.java
│   │   └── com/acme/model/api/Customer.java
│   ├── com.acme.service/
│   │   ├── module-info.java
│   │   └── com/acme/service/api/CustomerService.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
~~~

In this layout, src is the shared source root, with one directory underneath for each named module. The module-info.java file sits at the source root of its corresponding module.

This structure is convenient for using javac --module-source-path and -m.

## 6. The Data Model Module

Descriptor of com.acme.model:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Exported type:

~~~java
package com.acme.model.api;

public record Customer(String id, String displayName) {
}
~~~

Because package com.acme.model.api is exported, modules that read com.acme.model can use Customer.

A module does not need to declare requires java.base because every named module has an implicit dependency on java.base according to JPMS rules.

However, the fact that the package is exported is not enough for app to import Customer. App must also read com.acme.model via a JPMS relationship.

## 7. The Service Module with Ordinary requires

Starting from the descriptor:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

CustomerService:

~~~java
package com.acme.service.api;

import com.acme.model.api.Customer;

public final class CustomerService {
    public Customer findById(String id) {
        return new Customer(id, "Demo Customer");
    }
}
~~~

Module com.acme.service has permission to read model because it declares requires. It exports the service API so app can use the public class CustomerService if app reads the service module.

However, the findById method returns the Customer type belonging to the model module. With a service descriptor containing only **requires com.acme.model**, an app that only requires service will not automatically have a read relationship to model.

This is why ordinary requires can be insufficient when a dependency's type appears in the public API of the providing module.

## 8. The Consumer and the Readability Error

Initial descriptor of app:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

App code:

~~~java
package com.acme.app;

import com.acme.model.api.Customer;
import com.acme.service.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.findById("C-42");
        System.out.println(customer.displayName());
    }
}
~~~

App declared requires service but does not yet have a read relationship to model. When compiling, javac may report that package com.acme.model.api is not visible because module com.acme.app **does not read** com.acme.model.

Module model may be present in the same compilation and still be resolved because service requires model. However, **a module existing in the configuration does not mean every other module can read it**.

This illustrates the core idea of the readability graph: visibility of a type must be determined per specific consumer module, not by the set of JARs present on a global classpath.

## 9. First Fix: Direct requires

If app genuinely depends directly on Customer, it can declare:

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.model;
}
~~~

Then the readability graph is:

~~~text
com.acme.app ------requires------> com.acme.service
      |
      +------------requires------> com.acme.model

com.acme.service --requires------> com.acme.model
~~~

App reads both modules; package com.acme.model.api is exported by model, so app can use Customer.

This approach makes the direct dependency explicit in app's descriptor. It fits when app actively uses model's API as a separate dependency, not solely because the service module exposes that type.

An application can have multiple direct requires. What matters is not minimizing the number of requires lines at all costs, but accurately describing actual dependencies.

## 10. Second Fix: requires transitive

If the service module treats Customer as part of its **public API contract**, the service descriptor can be updated:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

The app descriptor can keep:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Effective read relationship:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.service
    |
    | requires transitive
    v
com.acme.model

=> com.acme.app reads com.acme.model
~~~

In JPMS, requires transitive causes any module that reads com.acme.service to also read the dependency com.acme.model. As a result, app uses the Customer type in CustomerService's public signature without needing to add requires model itself.

When a module re-exports part of a dependency's API through public signatures, requires transitive usually expresses the contract better than ordinary requires.

Do not use requires transitive for every dependency just for convenience. It expands the readability graph of consumer modules and increases coupling between the public API and external dependencies.

## 11. Compiling and Running the requires transitive Example

Once the service descriptor uses requires transitive and the app descriptor only requires service, compile:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.model,com.acme.service,com.acme.app
~~~

Javac reads each module's module-info.java, resolves the graph, and checks type access according to effective requires edges.

Typical output:

~~~text
mods/
├── com.acme.model/
│   ├── module-info.class
│   └── com/acme/model/api/Customer.class
├── com.acme.service/
│   ├── module-info.class
│   └── com/acme/service/api/CustomerService.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Run:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Demo Customer
~~~

Note: javac -m selects modules **to compile**, whereas java -m selects the module **to run**. The source module path belongs to --module-source-path; compiled modules belong to --module-path.

On Windows, this example uses only a single mods path, so no separator for multiple path entries is needed.

## 12. Readability Is a Directed Relationship

In a readability graph, if module A reads module B, it does not mean B also reads A.

Example:

~~~text
com.acme.app ----reads----> com.acme.service
~~~

Module app can use the exported API of service. The service module does not thereby gain permission to import classes from app.

This is very important in dependency design:

- Higher-layer modules depend on lower-layer APIs.
- Lower-layer modules should not depend back on higher-layer implementations.
- If extensibility from another module is needed, SPI and ServiceLoader can be used instead of creating cyclic dependencies.
- If two modules need to share a type, put the type in a separate API module rather than making them depend on each other.

The readability graph helps identify coupling along dependency directions, making it convenient to build a layered module structure.

## 13. requires static: Optional Dependency at Runtime

JPMS also has the **requires static** syntax:

~~~java
module com.acme.feature {
    requires static com.acme.annotations;
}
~~~

requires static expresses a dependency required at compile time that may be absent at runtime. A common example is compile-only annotations.

By contrast:

~~~java
module com.acme.feature {
    requires com.acme.annotations;
}
~~~

is a mandatory dependency during module resolution at runtime.

static and transitive can be combined when a compile-time dependency is reflected in the API, but you must consider the possibility that a consumer encounters the missing type at runtime.

Key point: **requires static does not make every class of the dependency safely optional at runtime**. If runtime code actually uses a type that is not present, linking/class-loading errors can still occur. Readability and optionality must match actual code behavior.

## 14. A Module on the Module Path Does Not Mean It Is Resolved

There are two independent concepts:

- **Observable modules**: modules that the finder/module path can observe.
- **Resolved modules**: modules selected into the Configuration, based on root modules, requires dependencies, and potentially service binding.

Example:

~~~text
mods/
├── com.acme.app/
├── com.acme.service/
├── com.acme.model/
└── com.acme.experiments/
~~~

Run:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

This does not mean every module in mods becomes a root or is resolved. Module com.acme.experiments may not participate in the graph if it is not required or added through another resolution mechanism.

A root module can be added explicitly:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiments \
     -m com.acme.app/com.acme.app.Main
~~~

However, **--add-modules does not automatically create a reads edge from app to experiments**. It adds the module to the root set, while read relationships still follow module descriptors and module system rules.

The distinction between a module being **present**, **resolved**, and **read** is central to JPMS.

## 15. Qualified Exports Further Restrict Visibility

Even when app reads the service module, service may export a package only to specific target modules.

Example:

~~~java
module com.acme.service {
    exports com.acme.service.api;

    exports com.acme.service.integration
        to com.acme.erp.adapter;
}
~~~

Module app reads service, but is not named in the qualified export, so it cannot import public types in com.acme.service.integration in the normal way.

Module com.acme.erp.adapter can use the integration package when it reads service and its module name matches the list after to.

We can distinguish:

| Mechanism | Question |
|---|---|
| requires | Does module A declare a dependency on B? |
| requires transitive | Do modules reading A also read B through the transitive edge? |
| exports | Which packages of B are accessible to modules that read B? |
| exports ... to | To which target modules only is a package of B exported? |
| opens / opens ... to | Which packages allow deep reflection, and to which modules? |

Therefore, the readability graph should not be described simply as a way to "see every class" in another module. It is one component of the encapsulation mechanism, not a replacement for accessibility rules.

## 16. Readability with the Unnamed Module on the Classpath

The classpath is still supported by Java. Classes loaded from the ordinary classpath belong to the **unnamed module** of the corresponding class loader.

The unnamed module has broader readability rules than named modules to preserve compatibility. However, this should not be interpreted as meaning every module on the module path automatically appears and every internal package is opened.

Example of running a legacy app on the classpath while the new library is a named module:

~~~bash
java --module-path mods \
     --add-modules com.acme.service \
     --class-path legacy-app \
     com.acme.legacy.Main
~~~

--add-modules puts the service module into the root set when needed. Public packages exported without qualification by service can be accessed by unnamed-module code under compatibility rules, while non-exported packages remain encapsulated.

If a named module wants to read the unnamed module, that is a different situation: a named module cannot declare requires on an unnamed module in module-info.java. Mixing classpath and module path requires careful thought about dependency structure, and may need --add-reads in special compatibility cases.

Long-term design should avoid having named-module code depend arbitrarily on the legacy classpath without a clear architecture.

## 17. Automatic Modules on the Migration Path

When a JAR without module-info.class is placed on the module path, it can be treated as an **automatic module**.

Automatic modules provide a bridge for legacy libraries:

- Has an automatic module name or a name specified by Automatic-Module-Name.
- Exports its packages according to automatic module rules.
- Has broader readability rules than explicit named modules to support compatibility.

However, automatic modules **do not eliminate** all JPMS rules. For example, multiple automatic modules containing overlapping packages can cause a split-package conflict when resolved in the same graph.

During migration, legacy libraries can be moved onto the module path as automatic modules and module descriptors can be added step by step. Still, official dependencies in module-info.java should be organized around stable module names.

Do not rely long-term on module names arbitrarily derived from JAR file names, because renaming an artifact can change the module name referenced by requires.

## 18. Distinguishing Readability Errors from Class-Loading Errors

In a JPMS project, not every class-related error is of the same kind.

**Compile-time readability error**

Example:

~~~text
package com.acme.model.api is not visible
(module com.acme.app does not read com.acme.model)
~~~

Approach: check requires in the app module, requires transitive in the module providing the public API, or the module graph structure. Do not just add the JAR to the module path if the read relationship is missing.

**Non-exported package error**

Example:

~~~text
package com.acme.model.internal is not visible
(package is declared in module com.acme.model,
 which does not export it)
~~~

Approach: use an exported API package, or design appropriate exports. An existing requires does not solve a non-exported package.

**Module not found error**

Example:

~~~text
Module com.acme.service not found, required by com.acme.app
~~~

Approach: check the module path, module name, output/JAR, and mandatory dependencies.

**Class not found error**

ClassNotFoundException or NoClassDefFoundError can appear when the actual class cannot be loaded or linked at runtime. Check where the class resides, the loader, the module layer, and the corresponding runtime dependencies.

**Reflection access error**

InaccessibleObjectException can appear when a framework attempts deep reflection into a package of a named module that has not been opened. This issue is not the same as an ordinary missing requires.

## 19. --add-reads Is a Compatibility Workaround, Not a Descriptor Replacement

Java supports the option:

~~~text
--add-reads source.module=target.module
~~~

Example:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiments \
     --add-reads com.acme.app=com.acme.experiments \
     -m com.acme.app/com.acme.app.Main
~~~

In this example, --add-reads adds a read relationship from app to experiments in the runtime environment.

Keep in mind:

- The target module must be resolved or available through an appropriate mechanism.
- --add-reads does not automatically export packages of the target module.
- --add-reads does not create or replace the module-info.java file.
- If source code needs read access at compile time, the appropriate option may also need to be supplied to javac at compile time.
- Compatibility flags should be managed consistently across build/test/runtime.

For stable application dependencies, declaring requires in module-info.java is usually clearer and easier to maintain than putting --add-reads in multiple startup scripts.

## 20. Dynamic Module Layers and Readability

A plugin application can create additional ModuleLayers at runtime. Each layer is tied to a Configuration consisting of resolved modules and reads relationships.

API example:

~~~java
ModuleFinder finder =
        ModuleFinder.of(Path.of("plugin-mods"));

Configuration parent =
        ModuleLayer.boot().configuration();

Configuration config = parent.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
);
~~~

The code above requires the corresponding imports:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
~~~

Modules resolved in the new layer are based on root modules and requires. A plugin module does not get access to an arbitrary named module just because it is present in plugin-mods.

A layer can be created from the configuration:

~~~java
ModuleLayer pluginLayer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                config,
                ClassLoader.getSystemClassLoader()
        );
~~~

When using multiple layers, you also need to check the parent layer, the class loader containing the service API, and which modules are actually resolved. Readability continues to apply to every named module in the graph.

Do not treat ModuleLayer as a free-form classpath recreated under different names; it still enforces JPMS boundaries.

## 21. Readability with ServiceLoader

ServiceLoader adds a dynamic kind of relationship: the consumer needs the service contract, while providers can be discovered through service metadata.

Consumer example:

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

Provider:

~~~java
module com.acme.payment.provider {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.provider.CardGateway;
}
~~~

The consumer does not necessarily have to requires the provider module. It can simply requires the service API and declare uses. The provider module needs to be resolved into the layer and register a valid provides so ServiceLoader can find it.

This is not "every module sees every class" behavior. The consumer still operates through the PaymentGateway type of the API module, without needing to import the CardGateway class located in the provider package.

For custom ModuleLayers, Configuration.resolveAndBind can bring provider modules into the graph according to uses/provides metadata. This differs from adding direct requires to each implementation and preserves dependency inversion at the module level.

## 22. Observing the Graph with JDK Tools

When running a modular application, use:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

The command helps observe root modules, dependency resolution, and resolved modules. If a module does not appear in the configuration, check the module path and roots before inferring accessibility issues.

To view the descriptor of a modular JAR:

~~~bash
jar --describe-module --file dist/com.acme.service.jar
~~~

To inspect module-info.class of an exploded module:

~~~bash
javap -p -v mods/com.acme.service/module-info.class
~~~

Information to check:

- requires or requires transitive?
- Is the package exported with exports or only exports ... to a specific module?
- Is the module name in requires exact?
- Is the dependent module actually on the module path and resolved?
- Is there a missing dependent module or a split-package conflict?

jdeps can be used to analyze dependencies at the bytecode level:

~~~bash
jdeps --list-deps --module-path mods \
      --module com.acme.app
~~~

jdeps helps identify dependencies; its output does not replace reading module descriptors and understanding API contracts. Classes loaded dynamically via reflection/services may not be fully represented in static analysis.

## 23. Direct Comparison Between Classpath Visibility and the Readability Graph

| Aspect | Traditional classpath | Named modules / JPMS |
|---|---|---|
| Input | List of directories/JARs | Module path and set of root modules |
| Unit of dependency | Mostly classes/JARs arranged by build tools | Named module in the module graph |
| Language-level dependency declaration | No requires | module-info.java with requires |
| Public types of a library | Usually available when found by class loader and access allows | Requires readability + exports + Java access |
| Transitive dependencies | Classes can appear together on the classpath | Readability propagates only according to appropriate rules, such as requires transitive |
| Internal public packages | Can be used directly by consumers | Can be kept hidden if not exported |
| Dependency identity | JAR/path and class name | Module name, descriptor, and module graph |
| Class lookup | Class loader and search order | Module resolution combined with class loading |
| Service discovery | Usually META-INF/services | uses/provides and ServiceLoader, plus compatibility mechanisms |

The table above describes common differences when moving from the classpath to named modules. The JVM still uses class loaders to load bytecode in JPMS; the readability graph **adds module-level access rules**, rather than completely replacing class loading.

## 24. Dependency Graph Design Principles

A maintainable module graph typically has these characteristics:

1. **Declare actual dependencies explicitly** using requires.
2. **Use requires transitive deliberately** when a module's exported API contains types from a dependency.
3. **Export only packages needed externally**, keeping implementation packages internal.
4. **Use qualified exports** for controlled integration rather than widening the public API.
5. **Separate service APIs from provider implementations**, using uses/provides when provider substitutability is needed.
6. **Do not rely on a JAR's presence on the module path** to infer which modules are resolved or readable.
7. **Minimize cyclic dependencies**; move shared contracts into an API module if needed.
8. **Do not use --add-reads as a long-term primary configuration** if the descriptor can be edited.
9. **Verify both compile-time and runtime module paths** have the appropriate dependencies.
10. **Use tools to observe module resolution** before fixing visibility errors.

When migrating from the classpath, proceed step by step: list required JARs, determine module names, write descriptors, resolve split packages, restrict exports, and then address missing requires or transitive dependencies genuinely needed for public APIs.

## 25. Practice Exercises

**Exercise 1 – Direct requires**

With the three modules app, service, and model, keep ordinary requires in service. Add requires model to app so that code importing Customer compiles. Record app's direct readability edges.

**Exercise 2 – requires transitive**

Remove requires model from app, and change the service module to requires transitive model. Recompile and explain why app can still access Customer.

**Exercise 3 – Encapsulating an internal package**

Add a public class to com.acme.model.internal without exporting this package. Try importing it from app. Observe the difference between a non-exported package error and a missing read-relationship error.

**Exercise 4 – Present but unresolved module**

Place an additional named module that is not required into mods. Run app and inspect --show-module-resolution. Then use --add-modules to observe the difference between observable and resolved.

**Exercise 5 – Error analysis**

If javac reports module app does not read model, yet a developer says "model.jar is already on the module path", explain why that answer does not resolve the error and state the appropriate descriptor fix.

These exercises aim to distinguish precisely among three concepts: **an observable module**, **a resolved module**, and **a module that the consumer has permission to read**.

## 26. Key Takeaways

- Traditional classpath prioritizes class lookup via class loaders; JARs on the same classpath have no JPMS-level dependency descriptors.
- The readability graph in JPMS describes which named module reads which named module.
- requires creates a read relationship; ordinary requires does not automatically make readability transitive to every consumer.
- requires transitive propagates readability to modules that read the declaring module when the dependency is part of its API.
- requires static describes a dependency needed at compile time that may be absent at runtime, without guaranteeing all runtime calls are safe.
- **Readability and exports are two distinct conditions**: being able to read a module does not mean being able to access every package of that module.
- A module appearing on the module path is not necessarily a resolved root or readable from a consumer module.
- Unexported internal packages allow a named module to preserve encapsulation boundaries even when its classes are public.
- The unnamed module and automatic modules have their own compatibility rules; do not equate them with explicit named modules.
- --add-reads is a compatibility tool that adds a temporary read edge; it does not edit the descriptor and does not automatically export packages.
- ServiceLoader lets consumers rely on a service contract instead of directly depending on provider modules.
- --show-module-resolution, jar --describe-module, and javap help diagnose dependency graphs.

**Conclusion:** JPMS shifts the mindset from "is the class located somewhere on the classpath?" to "does the consumer module have a valid read relationship to the module providing the type, and is the package exported?". The readability graph makes dependencies more explicit, while exports and access modifiers define API boundaries. Mastering that separation is the foundation for designing, compiling, and operating modular Java applications.
