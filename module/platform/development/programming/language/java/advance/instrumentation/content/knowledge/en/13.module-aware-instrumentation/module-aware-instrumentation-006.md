# Adding `uses`, `provides`, and Verifying Service Conditions in Java Instrumentation

**Context:** When a Java agent instruments an application running on the **Java Platform Module System (JPMS)**, sometimes new code needs to call `ServiceLoader` from a **named module** that does not declare `uses`, or the tool wants to make a provider in **another named module** discoverable without editing the `module-info.java` file on disk. Java Instrumentation provides `Instrumentation.redefineModule(...)` with two special arguments: **`extraUses`** and **`extraProvides`**.

These two arguments address **two different sides of the service contract**:

- **`extraUses`** adds a *service dependence* for the **service-consuming module** (*consumer*): this module is permitted to use a service type when executing `ServiceLoader.load(...)` from code within that module itself.
- **`extraProvides`** adds a *service provider* for the **module containing the implementation** (*provider module*): declares one or more implementation classes **belonging to that module** for a service type.
- **The two conditions do not substitute for each other.** A consumer with `uses` but without a provider may receive an empty list; a provider with `provides` while the consumer still lacks `uses` can still result in `ServiceConfigurationError`.
- **Visibility of the service type and existence of the provider** also depend on module resolution, `requires`/`reads`, package exports, class loaders, and provider instantiation rules.

This lesson focuses on **`Instrumentation` and modules**, not on modifying method bytecode. It explains the exact conditions of JPMS services, the API contracts to preserve, and a **compilable/runnable Java 17+ example** with three named modules and one Java agent, demonstrating **all four cases: `none` / `uses` / `provides` / `both`**.

## 1. Services in JPMS: consumer and provider

In Java, a service is usually an interface or an abstract class. The consumer does not need to instantiate the implementation directly; instead, it uses **`ServiceLoader`** to locate suitable providers.

Example service:

~~~java
package svc.api;

public interface Greeting {
    String greet();
}
~~~

Provider:

~~~java
package svc.provider;

import svc.api.Greeting;

public final class FastGreeting implements Greeting {
    public FastGreeting() { }

    @Override
    public String greet() {
        return "hello";
    }
}
~~~

Consumer:

~~~java
ServiceLoader<Greeting> loader = ServiceLoader.load(Greeting.class);
String message = loader.findFirst()
        .map(Greeting::greet)
        .orElse("<none>");
~~~

The snippets above are not a complete project; the service and implementation are standalone `.java` files, while the consumer fragment resides inside a method that already imports `java.util.ServiceLoader` and `svc.api.Greeting`.

In **named modules**, there are at least two different kinds of module descriptor declarations:

~~~java
// consumer module, e.g., svc.consumer/module-info.java
module svc.consumer {
    requires svc.api;
    uses svc.api.Greeting;
}
~~~

~~~java
// provider module, e.g., svc.provider/module-info.java
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting with svc.provider.FastGreeting;
}
~~~

- `requires svc.api`: the module reads the module containing the service type. In the example, the API module **exports** package `svc.api`.
- `uses svc.api.Greeting`: the module has a **service dependence** when code in the module calls `ServiceLoader`.
- `provides svc.api.Greeting with ...`: the module advertises one or more provider implementations for the discovery mechanism.
- **`requires` is different from `uses`**: a module can read an interface without being permitted to call `ServiceLoader` for that interface.
- **`uses` is different from `provides`**: a module declaring usage does not necessarily contain an implementation; a providing module does not necessarily use the service.

Having a provider class inside a JAR on the module path **is not enough** if the module has not been resolved or lacks proper registration. Conversely, `uses` is a permission/commitment of the **caller module**, and does not create any provider on its own.

## 2. `redefineModule`: five runtime addition groups

Java 9+ API signature:

~~~java
void redefineModule(
        Module module,
        Set<Module> extraReads,
        Map<String, Set<Module>> extraExports,
        Map<String, Set<Module>> extraOpens,
        Set<Class<?>> extraUses,
        Map<Class<?>, List<Class<?>>> extraProvides);
~~~

This is the API signature. `Instrumentation inst` is passed by the JVM to the Java agent in `premain` or `agentmain`, rather than being instantiated with `new` by the application.

| Parameter | What is added | Example |
|---|---|---|
| `module` | The module **whose runtime graph is modified** | `svc.consumer` or `svc.provider` |
| `extraReads` | Modules that `module` is permitted to **read** | Add `svc.api` if the appropriate read edge does not exist yet |
| `extraExports` | Packages of **`module` itself** exported to specific modules | Open access to public types |
| `extraOpens` | Packages of **`module` itself** opened to specific modules | Allow controlled deep reflection |
| `extraUses` | Service types that **`module` uses** | `Set.of(Greeting.class)` on the consumer |
| `extraProvides` | Map of service type → list of provider classes **belonging to `module`** | `Map.of(Greeting.class, List.of(FastGreeting.class))` on the provider |

Unused collections can be passed as **`Set.of()` / `Map.of()`**, but **must not be `null`**. You must understand **which module is being modified**: `extraUses` is typically attached to the **consumer module**, while `extraProvides` is attached to the **provider module**, rather than automatically combining both onto the module containing the agent.

**Key facts about the nature of this operation:**

1. `redefineModule` **only expands** reads/exports/opens/uses/provides; it **never removes** existing relationships.
2. Calling it with empty collections for all additions produces no meaningful change.
3. Calling it on an **unnamed module** is a **no-op**. `isModifiableModule(unnamed)` always returns `true`, but that **does not mean** you can add a provider via `redefineModule` on an unnamed module and expect it to work.
4. The API can be called concurrently by multiple agents; design without assuming all agents modify modules in your preferred order.
5. This is a **dynamic change to the Module runtime**, not recompiling or editing `module-info.class` on disk. Do not rely on `Module.getDescriptor()` as the sole source for querying dynamically added `uses`.
6. You do not need to declare `Can-Retransform-Classes` or `Can-Redefine-Classes` just to call `redefineModule`; those manifest capabilities are for class operations. However, the target module must be **modifiable**.

## 3. `extraUses`: giving a consumer a service dependence

Suppose the consumer module `svc.consumer` has:

~~~java
module svc.consumer {
    requires svc.api;
    // Does not yet have uses svc.api.Greeting;
}
~~~

From code inside `svc.consumer`, calling:

~~~java
ServiceLoader.load(Greeting.class);
~~~

may throw **`ServiceConfigurationError`** because the caller module **does not declare that it uses the service**. The issue is not solved merely by `requires svc.api`; `requires` allows the module to read the API, whereas `uses` expresses the service dependence.

An agent can add `uses` for the consumer:

~~~java
inst.redefineModule(
        consumerModule,
        Set.of(),
        Map.of(),
        Map.of(),
        Set.of(serviceClass),
        Map.of());
~~~

The snippet above is a fragment inside an agent callback, with `Instrumentation inst`, `Module consumerModule`, and `Class<?> serviceClass` already determined. This is **not a standalone runnable snippet**.

After a valid call, verify with:

~~~java
boolean allowed = consumerModule.canUse(serviceClass);
System.out.println(allowed);
~~~

`Module.canUse(Class<?>)` reflects the **runtime service dependence**; this is the right check to confirm whether the module is permitted to use the service. It is more useful than only inspecting `module-info.java` on disk, because the runtime graph has been augmented.

**Watch out for the caller module:** `ServiceLoader.load(Greeting.class)` must be called **from code in the consuming named module** so that the `uses` check reflects that module. If you put the same statement in a Java agent running in an **unnamed module**, `ServiceLoader` checks **the caller module, which is the agent**, not the consumer being instrumented. Unnamed modules are allowed to use services under different rules, so the test may report success and mask the consumer's missing `uses`.

### `extraUses` does not automatically make the service type accessible

The `Instrumentation.redefineModule` specification explicitly states that **the agent must ensure the service type is validly accessible at every instrumentation site**. The API **does not automatically verify** that the service type resides in the modified module or in a package exported by a module that the consumer can read.

For example, a consumer might have `extraUses = Set.of(Greeting.class)` without reading the module defining `Greeting`, or package `svc.api` might not be properly exported. When instrumentation inserts a call to `Greeting` into the consumer's bytecode, the JVM can still encounter **readability, class resolution, or accessibility** errors.

**Valid conditions for the end-of-lesson example:**

- `svc.api` is resolved and defines `svc.api.Greeting`.
- `svc.api/module-info.java` has `exports svc.api;`.
- `svc.consumer/module-info.java` has `requires svc.api;`.
- The agent calls `extraUses` with the **exact `Class<?>` object of `svc.api.Greeting`**.
- The consumer calls `ServiceLoader` inside module `svc.consumer` itself.

`extraUses` does not automatically add `requires`, does not add `extraReads`, and does not export packages. When reads/exports need to be added, do so on the **right module/right side** after analyzing dependencies.

## 4. `extraProvides`: declaring a provider belonging to the provider module

For `svc.provider`, the agent adds:

~~~java
inst.redefineModule(
        providerModule,
        Set.of(),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of(serviceClass, List.of(implementationClass)));
~~~

Where:

- `providerModule` is **the module to which `implementationClass` actually belongs**.
- Key `serviceClass` is the `Class<?>` of the service type (`Greeting`).
- Value is a **non-empty list** of implementation classes, such as `FastGreeting`.
- Each implementation must **belong to the module being redefined** and **be an implementation of the service type**.
- The `extraProvides` parameter allows **adding provider registrations** to an already resolved module; it does not create new classes from source, nor does it bring an unresolved JAR into the module graph.

**Checking membership and type before calling** is good practice:

~~~java
if (implementationClass.getModule() != providerModule) {
    throw new IllegalArgumentException(
            "implementation is not in provider module");
}
if (!serviceClass.isAssignableFrom(implementationClass)) {
    throw new IllegalArgumentException(
            "implementation does not implement service");
}
~~~

This is a fragment; the variables are determined by the agent from actual module/class objects.

According to the `redefineModule` contract, `IllegalArgumentException` can occur if:

- The provider list for a key is **empty**.
- A class passed in `extraProvides` **does not belong to the module being modified**.
- That class **is not an implementation** of the service type.

Do not interpret `Map.of(Greeting.class, List.of(FastGreeting.class))` as "bringing `FastGreeting` from another module into the consumer." It must be called on **module `svc.provider`**.

### A provider must be instantiable by ServiceLoader

Even when `redefineModule` accepts the registration, `ServiceLoader` also has rules for **loading and instantiating providers**. For an ordinary provider class like `FastGreeting`:

- It implements the `Greeting` service.
- It has a **public no-argument constructor**.
- The implementation module has been **resolved in the target module layer**.
- The class has a valid class file version and can be initialized without errors.

Some providers in named modules can use a valid **public static provider method** instead of a public no-arg constructor, per the `ServiceLoader` contract; the hands-on section chooses a public constructor for easy verification.

**There is no need to export the implementation package publicly just for ServiceLoader to find a provider in a named module**. ServiceLoader has a mechanism to access providers under the module service contract. Exporting packages is about allowing other code to reference the type directly, not a prerequisite for a provider to be discovered via ServiceLoader.

## 5. Condition matrix: none, `uses` only, `provides` only, both

Suppose there is **one service `Greeting`**, one consumer module `svc.consumer`, and one provider module `svc.provider` already resolved by the JVM. Both read the API module `svc.api`, and the API package is exported.

| Agent addition | `consumer.canUse(Greeting.class)` | `ServiceLoader` from consumer | Result |
|---|---|---|---|
| Nothing added | `false` | Not permitted to use service | `ServiceConfigurationError` |
| **`extraUses` only** | `true` | Permitted to call, but no provider registered | Empty provider list |
| **`extraProvides` only** | `false` | Consumer still lacks service dependence | `ServiceConfigurationError` |
| **Both `extraUses` and `extraProvides`** | `true` | Consumer has permission to use; provider is declared and found | Finds `FastGreeting` |

This is why the lesson is titled **“Adding `uses`, `provides`, and Verifying Service Conditions”**: a boolean check `canUse == true` is a **condition for the consumer**, but **does not prove** there is a provider to execute. Conversely, a valid provider does not guarantee every named consumer has permission to request the service.

Condition model:

~~~text
Consumer code calls ServiceLoader.load(Greeting.class)
                        │
                        ▼
 Does caller module have service dependence? ── No ─► ServiceConfigurationError
             │ Yes
             ▼
 Is service type accessible at call site? ── No ─► access/service error
             │ Yes
             ▼
 Is provider module resolved in matching layer?
             │ No ─► cannot find provider in that layer
             ▼
 Is provider declared in descriptor or extraProvides?
             │ No ─► provider list may be empty
             ▼
 Correct module, service, and valid instantiation?
             │ No ─► ServiceConfigurationError
             ▼
        Can obtain instance from ServiceLoader
~~~

This is a **logical condition diagram**, not a claim that the JVM always checks these conditions in the exact order shown for every `ServiceLoader.load` overload.

## 6. Java 17+ hands-on: three named modules and one agent

The example creates **three named modules**:

- `svc.api`: declares the `Greeting` service.
- `svc.consumer`: reads the API but **has no `uses` line**.
- `svc.provider`: reads the API, contains provider `FastGreeting`, but **has no `provides` line**.

A **separate Java agent** adds `extraUses`/`extraProvides` in `premain`, depending on the option `none`, `uses`, `provides`, or `both`. Because this is a runtime experiment, **do not edit `module-info.java` after each run**, and run each case in a fresh JVM so the results are independent.

Directory tree:

~~~text
module-service-lab/
├── src/
│   ├── svc.api/
│   │   ├── module-info.java
│   │   └── svc/api/Greeting.java
│   ├── svc.consumer/
│   │   ├── module-info.java
│   │   └── svc/consumer/Client.java
│   └── svc.provider/
│       ├── module-info.java
│       └── svc/provider/FastGreeting.java
├── src-agent/
│   └── Agent.java
├── AGENT.MF
└── out/
    ├── mods/                  compiled modules
    ├── agent-classes/         agent class
    └── agent.jar
~~~

### 6.1. `src/svc.api/module-info.java`

~~~java
module svc.api {
    exports svc.api;
}
~~~

**`exports svc.api` is essential** because both the consumer and the provider must access the public `Greeting` interface from another module.

### 6.2. `src/svc.api/svc/api/Greeting.java`

~~~java
package svc.api;

public interface Greeting {
    String greet();
}
~~~

A service type is identified by its **`Class<?>` object**, not just the text name `"svc.api.Greeting"`; at runtime with class loaders, the same name with different defining loaders is not necessarily the same service type.

### 6.3. `src/svc.consumer/module-info.java`

~~~java
module svc.consumer {
    requires svc.api;
}
~~~

Intentionally **omits** `uses svc.api.Greeting;`. This still allows compiling a class in the consumer module that imports `Greeting`, but calling `ServiceLoader` from this module will be **invalid** if the agent has not added the service dependence at runtime.

### 6.4. `src/svc.consumer/svc/consumer/Client.java`

~~~java
package svc.consumer;

import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;
import svc.api.Greeting;

public final class Client {
    public static void main(String[] args) {
        System.out.println("clientCanUse="
                + Client.class.getModule().canUse(Greeting.class));

        try {
            ServiceLoader<Greeting> loader =
                    ServiceLoader.load(Greeting.class);

            System.out.println("providers=" + loader.stream()
                    .map(p -> p.type().getName())
                    .sorted()
                    .toList());

            System.out.println("first=" + loader.findFirst()
                    .map(Greeting::greet)
                    .orElse("<none>"));
        } catch (ServiceConfigurationError error) {
            System.out.println("lookupError="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

`Client` runs **inside the named module `svc.consumer`**, so `ServiceLoader` checks the consumer's service dependence accurately. We use:

- `Module.canUse(Greeting.class)` to display the **`uses`** condition at runtime.
- `ServiceLoader.load(Greeting.class)` to check the service contract directly in the caller module.
- `loader.stream().map(p -> p.type().getName())` to observe **provider type names** via the `ServiceLoader.Provider` API, without necessarily instantiating them during listing.
- `findFirst().map(Greeting::greet)` to actually **instantiate and use** the provider; if no provider is available, print `<none>`.
- `.sorted()` for deterministic display order if the demo is extended with multiple providers. **Do not infer that provider ordering across modules is guaranteed by the JVM**.

**`ServiceConfigurationError` is an `Error`, not an `Exception`**. The `catch` here is strictly intentional for this lab so that all four cases print easily comparable output. In production, service configuration errors must be treated as issues to diagnose, not swallowed to silently continue.

### 6.5. `src/svc.provider/module-info.java`

~~~java
module svc.provider {
    requires svc.api;
}
~~~

Intentionally **omits** `provides svc.api.Greeting with svc.provider.FastGreeting;`. Nor is there any need to export package `svc.provider` for ServiceLoader to find a provider **in a named module**.

### 6.6. `src/svc.provider/svc/provider/FastGreeting.java`

~~~java
package svc.provider;

import svc.api.Greeting;

public final class FastGreeting implements Greeting {
    public FastGreeting() { }

    @Override
    public String greet() {
        return "hello";
    }
}
~~~

The provider **implements the service**, resides in `svc.provider`, and has a public no-argument constructor.

### 6.7. `src-agent/Agent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class Agent {
    public static void premain(String mode, Instrumentation inst)
            throws Exception {
        Module consumer = ModuleLayer.boot()
                .findModule("svc.consumer").orElseThrow();
        Module provider = ModuleLayer.boot()
                .findModule("svc.provider").orElseThrow();

        Class<?> service =
                Class.forName("svc.api.Greeting");
        Class<?> implementation =
                Class.forName("svc.provider.FastGreeting");

        if (!inst.isModifiableModule(consumer)
                || !inst.isModifiableModule(provider)) {
            throw new IllegalStateException("module not modifiable");
        }

        if (mode.equals("uses") || mode.equals("both")) {
            inst.redefineModule(
                    consumer,
                    Set.of(),
                    Map.of(),
                    Map.of(),
                    Set.of(service),
                    Map.of());
        }

        if (mode.equals("provides") || mode.equals("both")) {
            inst.redefineModule(
                    provider,
                    Set.of(),
                    Map.of(),
                    Map.of(),
                    Set.of(),
                    Map.of(service, List.of(implementation)));
        }

        System.out.println("agentMode=" + mode);
        System.out.println("agentConsumerCanUse="
                + consumer.canUse(service));
    }
}
~~~

**Reading each decision in the agent:**

1. `ModuleLayer.boot().findModule(...)` retrieves the **Module objects** corresponding to the named modules resolved in the boot layer. If a module has not been resolved, `orElseThrow()` fails fast instead of assuming every module is available.
2. `Class.forName(...)` retrieves the two **Class objects** defined at runtime. In this example, the classes have public APIs and the modules are in the boot layer, so lookup succeeds. In a real agent, consider `Class.forName(name, false, loader)` to avoid unintended eager class initialization and to select the right loader.
3. `isModifiableModule` checks both consumer and provider before modifying the graph. This method **does not check** whether a class can be retransformed.
4. `uses` mode: calls `redefineModule` on **consumer**, passing only `extraUses = Set.of(service)`.
5. `provides` mode: calls `redefineModule` on **provider**, passing only `extraProvides = Map.of(service, List.of(implementation))`.
6. `both` mode: performs **both modifications** in the same `premain` before the consumer calls `ServiceLoader`.
7. `none` mode: does not call `redefineModule` (used as a control).

The agent intentionally **does not modify `extraReads`, `extraExports`, or `extraOpens`**, because the module descriptors already contain `requires svc.api` and `exports svc.api`. If you remove those declarations, the test must be re-evaluated; `extraUses`/`extraProvides` do not automatically fix every module access error.

In this experiment, `mode` is always passed via `-javaagent:...=none|uses|provides|both`. This is a simple demo protocol; production code needs to validate agent arguments before using them.

### 6.8. `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: Agent

~~~

Ensure there is a trailing blank line. There is no `Can-Redefine-Classes` or `Can-Retransform-Classes` because the demo **does not redefine/retransform classes**, and only uses `redefineModule`.

## 7. Compiling and running the four cases

Open a terminal in `module-service-lab`. Create the output directories.

Bash/Git Bash:

~~~bash
mkdir -p out/mods out/agent-classes
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/mods, out/agent-classes | Out-Null
~~~

**Compile the three named modules** with JDK 17+:

~~~bash
javac --release 17 -d out/mods --module-source-path src -m svc.api,svc.consumer,svc.provider
~~~

The `src/<module-name>/module-info.java` structure must match the instructions, because `--module-source-path src` requires each module's source root to be inside `src`.

**Compile the agent outside any named module** and package the JAR:

~~~bash
javac --release 17 -d out/agent-classes src-agent/Agent.java
jar --create --file out/agent.jar --manifest AGENT.MF -C out/agent-classes .
~~~

**Four commands run on four separate JVMs:**

~~~bash
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=none -m svc.consumer/svc.consumer.Client
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=uses -m svc.consumer/svc.consumer.Client
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=provides -m svc.consumer/svc.consumer.Client
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=both -m svc.consumer/svc.consumer.Client
~~~

These commands have been verified with **JDK 24**, compiled with `--release 17`; the source uses no APIs newer than Java 17.

### Why is `--add-modules svc.provider` required?

Merely placing `svc.provider` on `--module-path` **does not guarantee** that module will be **resolved in the boot layer** when the main module is `svc.consumer`. In the demo, `svc.consumer` only `requires svc.api`, not `requires svc.provider`; therefore `--add-modules svc.provider` adds the provider module to the set of root modules to resolve.

Without it, `ModuleLayer.boot().findModule("svc.provider")` may be empty, and the agent will have no target **Module object** on which to declare the provider. `redefineModule` **is not an API for resolving/inserting a new module into a layer**.

This is one of the key conditions of the lesson: **declaring a provider in an already resolved module** and **making a module resolved** are two distinct operations.

### Case 1 — `none`: missing `uses`, missing `provides`

**Verified stdout:**

~~~text
agentMode=none
agentConsumerCanUse=false
clientCanUse=false
lookupError=ServiceConfigurationError
~~~

`ServiceLoader` is not permitted to use a service from a named module that lacks a service dependence. This is **not** a missing `Greeting` class error: the consumer still compiles successfully and already `requires svc.api`.

### Case 2 — `uses`: permitted to use service, but no provider

~~~text
agentMode=uses
agentConsumerCanUse=true
clientCanUse=true
providers=[]
first=<none>
~~~

This is proof that **`extraUses` does not create a provider**. The consumer passes the `ServiceLoader` check, but the provider module has not declared `FastGreeting` via `module-info` or `extraProvides`.

### Case 3 — `provides`: has provider, but consumer lacks `uses`

~~~text
agentMode=provides
agentConsumerCanUse=false
clientCanUse=false
lookupError=ServiceConfigurationError
~~~

Declaring a provider does not automatically fix the service dependence for every named consumer. The consumer still lacks `uses`, so `ServiceLoader.load` from this caller fails.

### Case 4 — `both`: both `uses` and `provides` present

~~~text
agentMode=both
agentConsumerCanUse=true
clientCanUse=true
providers=[svc.provider.FastGreeting]
first=hello
~~~

This is the success path:

- `extraUses` adds the service dependence to `svc.consumer`.
- `extraProvides` declares `FastGreeting` belonging to `svc.provider`.
- Both modules read `svc.api`, and the service type is exported.
- `svc.provider` has been resolved in the boot layer thanks to `--add-modules`.
- `ServiceLoader` finds the provider type, creates an instance, and calls `greet()` returning `"hello"`.

**Note:** In a system with multiple providers, discovery order has its own rules; you should not rely on the "first provider" as a business guarantee if multiple implementations may participate. The demo has exactly one provider, so `findFirst()` produces a deterministic result.

## 8. When should you use module descriptors instead of `redefineModule`?

If you **own the source of the modules** and the service relationship is part of the normal design, declare it in `module-info.java`:

~~~java
// Consumer
module svc.consumer {
    requires svc.api;
    uses svc.api.Greeting;
}
~~~

~~~java
// Provider
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting with svc.provider.FastGreeting;
}
~~~

This allows the build, module tools, and source readers to understand the relationship upfront. There is no need for an agent to modify the runtime graph for a feature already known at compile time.

`Instrumentation.redefineModule` is useful when:

- A **Java agent** injects code calling `ServiceLoader` into a named module that originally lacked `uses`.
- A framework/agent needs to register a provider **already residing in a valid module** that the static module descriptor did not declare.
- You need to adjust runtime relationships of a module managed by an application or framework without modifying classes/module descriptors on disk.
- You can prove appropriate service access boundaries and the target module is modifiable.

Do not use `redefineModule` as a tool to "patch all broken classpath/module-path setups"; its purpose is to **extend relationships already permitted by the API** on existing modules.

## 9. Checking the right conditions before adding `uses` and `provides`

A safe verification workflow:

1. **Identify the actual caller.** Which code will call `ServiceLoader` after instrumentation? `callerClass.getModule()` is the consumer module; do not infer it from the agent's module.
2. **Identify the exact service type** by `Class<?>`, along with the appropriate runtime/class loader. Verify that it has suitable public/accessibility at the call site.
3. **Check module resolution and layer.** `ModuleLayer.boot().findModule(...)` applies to the boot layer example; for custom layers, use the exact layer where the consumer/provider resides.
4. **Check reads/exports.** If the service is in `svc.api`, the consumer needs to read the API module and the API package must be appropriately exported. `Module.canRead` and `Module.isExported` help inspect the runtime graph.
5. **Check `consumer.canUse(service)`** before/after adding `extraUses`. This is the query for service dependence.
6. **Check implementation and membership.** `implementation.getModule() == providerModule`, `service.isAssignableFrom(implementation)`, plus checking construction/provider method per `ServiceLoader`.
7. **Check `inst.isModifiableModule(target)`** before each `redefineModule`. Note that unnamed modules always return `true`, yet redefining them is a no-op.
8. **Add only the necessary relationships.** Use immutable `Set.of`, `Map.of`, `List.of` and avoid adding overly broad exports/opens beyond the target.
9. **Verify the result via `ServiceLoader` at the exact caller.** `canUse=true` does not prove a provider exists. Use a new loader or `reload()` after changing registrations.
10. **Observe errors.** If `ServiceLoader` does not find a provider, distinguish between "no provider", "unresolved module", "provider failed to instantiate", "inaccessible service type", and "caller lacks `uses`".

### Compact preflight pattern in an agent

~~~java
static void checkProvider(
        Module targetProviderModule,
        Class<?> service,
        Class<?> implementation) {
    if (implementation.getModule() != targetProviderModule) {
        throw new IllegalArgumentException(
                "provider belongs to another module");
    }
    if (!service.isAssignableFrom(implementation)) {
        throw new IllegalArgumentException(
                "provider does not implement service");
    }
}
~~~

This is a complete method to place in a utility class; it does not run standalone. It is **not sufficient** to confirm that the provider has a public no-arg constructor, a valid provider factory, that the service type's module has proper readability/accessibility, or that `ServiceLoader` will be called in the right layer.

You can additionally check:

~~~java
Module apiModule = service.getModule();
boolean readable = consumerModule.canRead(apiModule);
boolean exported = apiModule.isExported(
        service.getPackageName(), consumerModule);
boolean canUse = consumerModule.canUse(service);

System.out.println(readable);
System.out.println(exported);
System.out.println(canUse);
~~~

This is a fragment assuming `service` and `consumerModule` already exist. For an API module with an unqualified export, `isExported(..., consumerModule)` returns `true` when the relationship is valid. If the service resides in the same module as the caller, the access analysis may differ; the goal here is to confirm the **specific case where the service interface belongs to a separate API module**.

## 10. Easy-to-miss constraints of `extraProvides`

**You cannot attach an implementation belonging to another module to a provider module** merely through the `Map<Class<?>, List<Class<?>>>` value. The API checks membership and the relationship type.

**Invalid** examples:

~~~java
// Wrong: empty providerList.
Map<Class<?>, List<Class<?>>> invalid1 =
        Map.of(serviceClass, List.of());

// Wrong: implementation is in another module
// but passed to providerModule's extraProvides.
Map<Class<?>, List<Class<?>>> invalid2 =
        Map.of(serviceClass, List.of(classFromAnotherModule));
~~~

The fragments above assume the variables are already provided; **do not actually call** `redefineModule` with these maps in a production application.

The typical consequence is `IllegalArgumentException`, per the Instrumentation specification:

- The `extraProvides` map contains an **empty** value list.
- A provider class **is not a member of the module being redefined**.
- A provider class **does not implement the service type**.

In the demo, these conditions are guaranteed by `FastGreeting implements Greeting` and `FastGreeting.class.getModule()` being `svc.provider`.

Beyond the three conditions directly checked by the API, `ServiceLoader` can also fail when **the provider class cannot be loaded/instantiated**: missing or invalid constructor, invalid static provider method contract, broken provider dependency, or a provider method throwing an exception or returning `null`.

**A provider implementation does not need to export its package for consumers to instantiate it via ServiceLoader**, but if a consumer wants to directly reference a concrete class such as `new FastGreeting()`, that is a different access relationship and requires corresponding exports/reads.

## 11. `ServiceLoader`: discovery, instantiation, caching, and errors

`ServiceLoader` has two distinct phases:

- **Discovery:** locating providers declared/advertised in modules/layers and other appropriate sources.
- **Instantiation:** creating a provider instance when the user retrieves an element, calls `findFirst()`, iterates, etc.

Example:

~~~java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(Greeting.class);

loader.stream()
        .map(ServiceLoader.Provider::type)
        .forEach(System.out::println);

loader.forEach(greeting ->
        System.out.println(greeting.greet()));
~~~

This is a fragment inside a class belonging to a named consumer with the corresponding `uses`. `stream().map(Provider::type)` accesses provider types; `forEach` on `loader` actually obtains instances.

`ServiceLoader` **caches providers** already loaded on a loader instance. If an agent adds `extraProvides` after application code has already iterated an older `ServiceLoader`, do not assume that cache will automatically refresh the way you need. You can create a **new `ServiceLoader`** at the proper caller/layer or call **`loader.reload()`** to clear the cache before searching again.

`reload()` **does not automatically resolve new modules**, nor does it turn a module without `uses` into a valid consumer. It only manages the cache/discovery of the loader instance.

The specification also states that providers added by instrumentation agents **are discovered after providers already declared in the module descriptor** (when considering that module's providers). Ordering **across modules in the same layer** is not a stable contract for choosing the "highest-priority provider." Use explicit priority/configuration when ordering affects business logic.

### `ServiceLoader.load(...)` and `load(ModuleLayer, ...)`

- `ServiceLoader.load(Greeting.class)` uses the **thread context class loader** per the convenience API, and checks the service dependence of the **caller module**.
- `ServiceLoader.load(layer, Greeting.class)` searches for providers in the **specified module layer and its parent layers**, without searching for providers in unnamed modules the way the other overload does. A caller in a named module must still have permission to use the service.
- `ServiceLoader.loadInstalled(Greeting.class)` uses the platform class loader and has a **different discovery scope**; it is not a default replacement for named providers on the application module path.

The demo chooses the single-argument overload and `ModuleLayer.boot()` because all three named modules are in the boot layer and the default thread context loader is suitable. In applications with custom layers, choose the right overload/layer rather than defaulting to `ModuleLayer.boot()` out of habit.

## 12. Three different errors often lumped together as “ServiceLoader is broken”

| Symptom | What is actually missing |
|---|---|
| `ServiceConfigurationError` stating the module does not declare `uses` | **Consumer lacks service dependence** |
| `ServiceLoader` returns an empty list | Caller is valid, but **no provider was discovered in the search scope** |
| Provider is listed, but `findFirst`/iterator throws `ServiceConfigurationError` | **Provider failed during loading/validation/instantiation** |

This explains why **looking only at `Module.canUse()` is not enough**. It confirms the module's ability to *use a service*, not provider availability or constructors.

Other errors to distinguish:

| Error/symptom | Cause and check |
|---|---|
| `UnmodifiableModuleException` | Module cannot be modified via `redefineModule`; check `isModifiableModule` |
| `IllegalArgumentException` during `redefineModule` | `extraProvides` contains a provider from the wrong module / not implementing the service / empty list, or `extraExports`/`extraOpens` is invalid |
| `NullPointerException` during `redefineModule` | One of the arguments or a key/value collection is `null` |
| `NoSuchElementException` at `findModule(...).orElseThrow()` | Module is not resolved in the searched layer; check `--add-modules`, graph, and layer |
| `NoClassDefFoundError` / `ClassNotFoundException` | Type not found by the appropriate loader; check module resolution and defining loader |
| `IllegalAccessError` / module access error | Named module cannot read required module or package is not properly exported |
| `InaccessibleObjectException` on deep reflection | Package is not **open** to caller; distinct from `uses`/`provides` |
| `ServiceConfigurationError` during instantiation | Provider constructor/factory or dependency failed; inspect cause and module/class identity |
| `ClassCastException` | Same-named type from different class loaders; provider does not share the same service class identity |
| Unable to find provider after adding it | Module is unresolved, ServiceLoader uses a different layer/loader, or cache was not reloaded |

Do not use `--add-opens` to fix a missing `uses` error: opening a package for reflection **does not** add a service dependence. Conversely, `extraUses` does not fix reflective access errors.

## 13. `Module.addUses` vs. `Instrumentation.redefineModule`

Java's `Module` has the method:

~~~java
Module addUses(Class<?> service);
~~~

However, `Module.addUses` has a **caller module** restriction: for a named module, the caller must reside in the very module whose service dependence is being added; otherwise, it can throw **`IllegalCallerException`**. It is designed for frameworks or appropriate code operating from inside the module.

A Java agent in another module should not simply call:

~~~java
consumerModule.addUses(serviceClass);
~~~

and assume it has permission to modify any named module. For an agent to modify a consumer module **from the outside**, `Instrumentation.redefineModule(consumerModule, ..., extraUses, ...)` is the appropriate API.

Another point: `Module.addUses` **does not re-trigger `resolveAndBind`**, and by itself does not pull a new unresolved provider module into the layer. `Instrumentation.redefineModule` is also not a tool for rebuilding layers and resolving all modules on the module path.

## 14. Modules, class loaders, and service availability conditions

Service conditions are not just two flags, `uses` and `provides`. When integrating into a real system, consider the **module graph and class loader identity**:

~~~text
                  svc.api (export svc.api)
                  /                     \
           requires                     requires
             /                             \
        svc.consumer                    svc.provider
        extraUses(Greeting)             extraProvides(Greeting → FastGreeting)
             |                             |
             | ServiceLoader call          | registration
             └───────── discover ──────────┘
                       (when provider module
                        is resolved and lookup
                        uses the right layer)
~~~

For named consumer/provider modules on the **boot layer** as in the exercise:

- Both consumer and provider have **`requires svc.api`**, sufficient to reference the service interface.
- `svc.api` has **`exports svc.api`**, ensuring the public interface can be used from other modules.
- `svc.provider` is present in the **resolved boot layer**, thanks to `--add-modules svc.provider` at startup.
- `extraUses` adds the consumer → service type relationship, but **does not** replace `requires`.
- `extraProvides` registers an implementation class that actually resides in `svc.provider`, but **does not** move a class from another loader into the provider module.
- `ServiceLoader.load` runs in the consuming caller module, using the right loader/layer to locate the provider.

In an application with containers or plugin loaders, comparing only **binary class names** can be misleading. Log `service.getModule()`, `service.getClassLoader()`, `implementation.getModule()`, and their module layers. A `Class<?>` defined by loader A is not automatically equal to a class with the same name defined by loader B.

## 15. Why shouldn't `extraUses` / `extraProvides` be used indiscriminately?

`redefineModule` can **expand interoperability between modules**. This is an action with security/encapsulation implications for the application, even without modifying class files.

Guidelines:

1. **Modify only the modules that actually need instrumentation.** Do not add `uses` to a slew of modules just because ServiceLoader failed to find a provider.
2. **Choose the exact service type** and verify that the consumer is permitted to read/access that type; the API does not automatically validate accessibility at every site.
3. **Register a provider only on the module containing the implementation**, never assigning a class coming from an arbitrary module.
4. **Do not open packages more broadly than needed** to fix service discovery errors; `extraExports`/`extraOpens` are separate access permissions that require separate evaluation.
5. **Understand additivity:** `redefineModule` has no operation to retract added `uses`/`provides` in the current JVM via this API. Avoid treating it as a configuration that can be easily toggled on and off.
6. **Do not assume everything on the module-path is loaded.** Only modules resolved in the proper layer have a `Module` object for runtime registration.
7. **Track the `ServiceLoader` lifecycle.** It has caching and lazy loading, so re-test with a new loader or `reload`.
8. **Protect provider constructors/factories.** Instances may be created at unexpected times, requested by another module.
9. **Test on the same JDK and module topology** that will be used in production. Loading modules with custom loaders, automatic/unnamed modules, or another agent modifying the graph concurrently can lead to behavior different from a minimal example.
10. **Do not swallow service configuration errors.** Log the service name, caller module, provider module, and cause for diagnostics.

With an architecture whose source you own, the most stable approach is usually still declaring `uses` and `provides` in `module-info.java`, and using instrumentation only when runtime relationship additions are genuinely required.

## 16. A post-instrumentation service QA checklist

Below is a checklist to apply after an agent adds `extraUses` or `extraProvides`:

| Check | Query / tool |
|---|---|
| Right consumer module? | `callerClass.getModule()` |
| Module already resolved? | Corresponding `ModuleLayer`, `findModule` |
| Service type has right class identity? | `service.getName()`, `service.getModule()`, `service.getClassLoader()` |
| Consumer reads service module? | `consumer.canRead(service.getModule())` |
| Service package properly exported? | `service.getModule().isExported(service.getPackageName(), consumer)` |
| Consumer permitted to use service? | `consumer.canUse(service)` |
| Provider belongs to provider module? | `implementation.getModule() == provider` |
| Provider implements service? | `service.isAssignableFrom(implementation)` |
| Provider can be instantiated? | `ServiceLoader` instantiates successfully; valid constructor/factory |
| Provider within discovery scope? | `ServiceLoader.load(...)` / `load(layer, ...)`, `stream()` |
| Stale cache? | Create a new loader or `reload()` |
| Module allows agent updates? | `inst.isModifiableModule(module)` |
| Did API throw during registration? | Catch/log `IllegalArgumentException`, `UnmodifiableModuleException` appropriately |

At an instrumentation site with a service type from another module, check **both `canUse` and `canRead` and package export**. A single `true` field does not prove all conditions succeed.

Do not test `ServiceLoader` from the agent's unnamed module and treat that result as proof that a named consumer has permission; **the actual caller module** is the deciding factor.

## 17. Self-check questions

1. **Can `requires svc.api` replace `uses svc.api.Greeting`?** No. `requires` is a module reading relationship; `uses` is a service dependence.
2. **Which module should `extraUses` be added to?** The module **making the call to use the service** (consumer).
3. **Which module should `extraProvides` be added to?** The module **containing the implementation class** (provider).
4. **`extraUses` succeeded, `consumer.canUse(service)==true`. Will `ServiceLoader` necessarily find a provider?** No. The provider may not be declared/resolved yet or may be outside the discovery scope.
5. **`extraProvides` declared `FastGreeting`, consumer lacks `uses`. What happens when `ServiceLoader.load` is called from the consumer?** It can throw `ServiceConfigurationError` due to the missing service dependence.
6. **Can `extraProvides` contain an implementation from a different module than the one being redefined?** No. The API checks membership and service implementation.
7. **Is an empty `List.of()` value in the `extraProvides` map valid?** No; `IllegalArgumentException`.
8. **Is it necessary to export the implementation package to every consumer just to use `ServiceLoader`?** No, for a provider belonging to a named module and properly registered.
9. **Why does the demo use `--add-modules svc.provider`?** So that the provider module is **resolved**, not merely present on the module path.
10. **Can `redefineModule` remove existing `uses`/`provides`?** No; the API is additive-only.
11. **`isModifiableModule(unnamedModule)` is always true. Can `redefineModule` be used to modify an unnamed module?** The call is a **no-op** for unnamed modules.
12. **How do you confirm a runtime service dependence was added?** `Module.canUse(serviceClass)`.
13. **How do you confirm a provider is actually used?** Run `ServiceLoader` from the right consumer, find the provider, and instantiate it successfully.
14. **Does `ServiceLoader.load` succeeding from an agent's unnamed module prove the named consumer is valid?** No; the caller modules are different.
15. **When the service type is not accessible at the instrumentation site, does `extraUses` fix it automatically?** No; the agent must ensure module readability and type accessibility.
16. **When the provider module is unresolved, does `redefineModule` automatically add it to the boot layer?** No.
17. **Can a provider be discovered yet fail during instantiation?** Yes; `ServiceConfigurationError` can still occur.
18. **Should `Module.getDescriptor().uses()` be used instead of `Module.canUse` after runtime modification?** Not if you need runtime state; `Module.canUse` is the query for the service dependence contract.

### Official documentation

- [Java SE 21 — `Instrumentation.redefineModule` and `isModifiableModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `extraUses`, `extraProvides` contract, membership conditions, non-empty lists, additive-only limitation.
- [Java SE 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canUse`, `canRead`, `isExported`, `addUses`, module layer, and caller restriction.
- [Java SE 21 — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): named-module caller `uses`, provider discovery, `Provider`, cache/reload, and errors.
- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): resolved modules and layers.
- [Java SE 21 — `ModuleDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html): `requires`, `uses`, and `provides` declarations in descriptors.
- [JLS Java SE 21 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): syntax and semantics of `module-info.java`.

**Takeaway:** **`extraUses` grants a service dependence to the consumer**, while **`extraProvides` declares an implementation belonging to the provider module**. The two steps are independent. For a service call to succeed, you also need an **accessible service type, a resolved provider module, a valid provider, `ServiceLoader` running in the right caller/layer, and verification of the result at actual runtime**.
