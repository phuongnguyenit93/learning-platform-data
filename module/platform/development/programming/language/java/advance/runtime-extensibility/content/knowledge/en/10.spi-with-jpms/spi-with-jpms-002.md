# Separating Contract, Host Application, and Provider Modules in Java JPMS

## 1. Architectural Goal

With the Java Platform Module System (JPMS), a plugin system can clearly divide three responsibilities: the **contract module (service API)** defines a stable interface; the **host application module (consumer/host)** needs to use the service without depending on the implementation; and the **provider module** implements and registers the implementation. This architecture makes it possible to swap or add providers without modifying the host's source code, while letting JPMS validate module relationships at compile time and runtime.

Dependency model:

```text
                 requires
app.host ----------------------> app.contract
    |                                 ^
    | uses contract.Greeting          | requires
    |                                 |
    +-- ServiceLoader ---------- app.provider.en
                          provider registered via provides ... with ...
```

Key point: **the host does not write `requires app.provider.en`** just to use the service. The host only `requires app.contract` and `uses` the service; the provider `requires app.contract` and then `provides` the implementation. Having the provider module present in the runtime configuration is the responsibility of the launch setup/module resolution.

## 2. Role and Boundaries of Each Module

| Module | Owns | module-info.java | Should Not Do |
| --- | --- | --- | --- |
| `app.contract` | Service interfaces, DTOs, and shared API types | `exports contract;` | Know about concrete providers or call the host directly |
| `app.host` | Orchestrating, selecting, and using providers | `requires app.contract; uses contract.Greeting;` | Instantiate (`new`) implementations or hard-code provider names |
| `app.provider.en` | Implementation and internal plugin dependencies | `requires app.contract; provides contract.Greeting with en.EnglishGreeting;` | Force the host to import implementation packages |

The contract module should be kept lean with a clear versioning/compatibility policy: changing an interface signature can render previously compiled providers incompatible. `exports` only exposes the API package to modules that can read it; it does not require exporting the provider's implementation package.

A provider module can have multiple implementations for the same service, or multiple independent provider modules can register the same service. The host application must define how to select or use them; discovery order is not business priority order.

## 3. Complete Java 17+ Example: Three Named Modules

Directory structure:

```text
demo/
  src/
    app.contract/
      module-info.java
      contract/Greeting.java
    app.host/
      module-info.java
      host/Main.java
    app.provider.en/
      module-info.java
      en/EnglishGreeting.java
```

### Contract Module `app.contract`

`src/app.contract/module-info.java`:

```java
module app.contract {
    exports contract;
}
```

`src/app.contract/contract/Greeting.java`:

```java
package contract;

public interface Greeting {
    String name();
    String greet(String person);
}
```

The `contract` package is exported so both the host and provider can reference `Greeting`. Do not place concrete plugins in this module.

### Host Application Module `app.host`

`src/app.host/module-info.java`:

```java
module app.host {
    requires app.contract;
    uses contract.Greeting;
}
```

`src/app.host/host/Main.java`:

```java
package host;

import contract.Greeting;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        List<Greeting> providers = new ArrayList<>();
        for (Greeting provider : ServiceLoader.load(Greeting.class)) {
            providers.add(provider);
        }
        if (providers.isEmpty()) {
            throw new IllegalStateException("No Greeting provider resolved");
        }
        for (Greeting provider : providers) {
            System.out.println(provider.name() + ": "
                    + provider.greet("Java"));
        }
    }
}
```

`uses contract.Greeting;` declares that this module consumes the service. When calling `ServiceLoader.load(Greeting.class)` from code in a named module, omitting `uses` can cause a `ServiceConfigurationError`; therefore, it must be declared in the host module, not just imported as an interface in Java source.

### Provider Module `app.provider.en`

`src/app.provider.en/module-info.java`:

```java
module app.provider.en {
    requires app.contract;
    provides contract.Greeting with en.EnglishGreeting;
}
```

`src/app.provider.en/en/EnglishGreeting.java`:

```java
package en;

import contract.Greeting;

public final class EnglishGreeting implements Greeting {
    public EnglishGreeting() {}

    @Override
    public String name() {
        return "english";
    }

    @Override
    public String greet(String person) {
        return "Hello, " + person;
    }
}
```

`provides ... with ...` registers the implementation for `ServiceLoader` to discover in the module configuration. Because this is a public provider class with a public no-arg constructor, it satisfies the provider class mechanism of a named module. JPMS also supports a static provider method mechanism in certain cases, though it is not needed for this example. The `en` package **does not need `exports`** merely to be instantiated by `ServiceLoader` via service binding.

## 4. Compiling and Running on the Module Path

From the `demo` directory, using JDK 17+ with a multi-module source layout:

```bash
javac --module-source-path src -d mods --module app.contract,app.host,app.provider.en
java --module-path mods --add-modules app.provider.en --module app.host/host.Main
```

Expected output:

```text
english: Hello, Java
```

In the run command, `--module-path mods` makes the modules observable; `--add-modules app.provider.en` requests that the provider module be included in the module graph to ensure the behavior is demonstrated without relying on the launcher's resolution inference. With JPMS service binding, a provider can also be resolved through the service binding mechanism when applicable; however, the illustrative command intentionally names the provider module explicitly for easy verification.

Do not arbitrarily mix `-cp` with `--module-path`. Classes on the classpath belong to the unnamed module and are governed by different readability rules than named modules. In this example, all three are named modules.

### Packaging Each Module into a Modular JAR

After compiling:

```bash
mkdir -p dist
jar --create --file dist/app.contract.jar -C mods/app.contract .
jar --create --file dist/app.host.jar -C mods/app.host .
jar --create --file dist/app.provider.en.jar -C mods/app.provider.en .
java --module-path dist --add-modules app.provider.en --module app.host/host.Main
```

The final command still prints `english: Hello, Java`. Now the runtime uses the actual distribution JARs instead of the `mods` directory. If no provider module is on the module path or resolved into the appropriate layer, the host will not find this implementation. If another provider has been resolved, the count/output may differ; tests should assert the expected set of providers for the distribution.

Inspect the module descriptors:

```bash
jar --describe-module --file dist/app.contract.jar
jar --describe-module --file dist/app.host.jar
jar --describe-module --file dist/app.provider.en.jar
```

The output should show the corresponding `exports contract`, `requires app.contract`, `uses contract.Greeting`, and `provides contract.Greeting with en.EnglishGreeting` relationships. Inspect the final artifacts to detect if `module-info.class` was lost during shading/packaging.

## 5. Why Doesn't the Host Directly Depend on the Provider?

Suppose the host writes:

```java
import en.EnglishGreeting;
Greeting greeting = new EnglishGreeting();
```

This is only an illustrative snippet (not a standalone class). For this code to compile inside a named module, the host must read the provider module and the `en` package must be exported. This couples the host to the implementation and typically defeats the goal of swapping plugins independently.

With SPI, the host only knows `Greeting` and uses `ServiceLoader`; the provider module can be replaced with `app.provider.vi` without modifying `app.host`, as long as the provider satisfies the same API contract and is resolved at runtime.

The desired dependency direction is one-way:

```text
host ----requires----> contract <----requires---- provider
host ----uses-------> contract.Greeting
provider --provides--> contract.Greeting
```

Do not let the contract module `requires app.host` or `requires app.provider.en`; doing so destroys independence and can create module dependency cycles.

## 6. Scaling to Multiple Providers

To add a Vietnamese provider, create a new module:

```java
module app.provider.vi {
    requires app.contract;
    provides contract.Greeting with vi.VietnameseGreeting;
}
```

This is an illustrative descriptor; you need to add the `vi.VietnameseGreeting` class implementing `contract.Greeting`, then compile and place the JAR on the module path. The host does not need to change its `module-info.java` if it continues using `Greeting`.

With multiple providers, `ServiceLoader` lets you iterate over them but does not guarantee a desired business order. If you need to select providers by `name()`, region, capacity, or priority, build an independent selection policy (filtering, ranking, tie-breaking, and handling missing providers). Avoid implicitly using the first element of the iterator as the default choice.

In a modular architecture, a provider can be registered without publicly exporting its implementation package. Consumers should not use reflection to bypass encapsulation; `provides ... with ...` is the service contract.

## 7. Module Resolution, Module Layers, and Runtime Discovery

**Being present on the module path** does not mean a provider module is always resolved into the layer that the loader is searching. JPMS resolves the module graph based on root modules, requirements, and service binding according to the launch/layer mode; when creating dynamic layers, the application must include the module in the appropriate configuration.

For a module layer created by the host, you can use `ServiceLoader.load(layer, Greeting.class)` to discover providers in the appropriate layer. Short example (illustrated inside a method that already has `ModuleLayer layer`):

```java
ServiceLoader<Greeting> loader = ServiceLoader.load(layer, Greeting.class);
for (Greeting provider : loader) {
    System.out.println(provider.name());
}
```

Do not infer that `ServiceLoader.load(Greeting.class)` on the thread context classloader will automatically find providers in every layer created by the application. You must choose the right overload for the loader/layer architecture and test with the final artifacts.

**Readability and accessibility:** `requires app.contract` allows the dependent module to read the API module; `exports contract` allows other modules to access public types in the `contract` package. `opens en` is not needed for a normal service provider to be loaded via the JPMS `provides` mechanism, and you should not broaden `opens` just to "fix" service lookup without identifying the root cause.

## 8. API Compatibility and Version Management

The contract boundary is where changes must be managed carefully:

- Adding an abstract method to an interface can break binary/source compatibility of older providers; consider a default method when appropriate, or version the contract in a controlled manner.
- Changing the package/name of a service interface changes the service identity; both `uses`, `provides`, and implementations must be updated.
- Ensure the host and provider use the same runtime `contract.Greeting` class. If multiple copies of the API are loaded by different loaders/layers, type mismatches can occur even when the class names are identical.
- Do not let provider JARs bundle arbitrary duplicate copies of the contract API in a shared-interface architecture.
- Use compatibility tests against supported plugin versions; compilation succeeding is only one step—actual runtime behavior must be invoked.

With JPMS, module versions do not automatically create a semantic versioning compatibility upgrade resolver. Developers must still manage dependency versions and release contracts.

## 9. Common Errors

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `ServiceLoader` returns 0 providers | Provider module is not in the resolved layer/module graph | Check `--module-path`, roots, service binding, or `--add-modules` |
| `ServiceConfigurationError` when loading service | Host is missing `uses`, provider violates contract, or instantiation fails | Check `module-info.java`, stacktrace, and provider |
| Compile reports package is not visible | API package is not `exports`ed or `requires` is missing | Adjust descriptors to match proper boundaries |
| Host has to import implementation | Design still depends directly on the provider | Switch to SPI and `uses`/`provides` |
| `ClassCastException`/`not a subtype` | Service API was loaded with different runtime identities | Use only one API identity across the graph/loader boundary |
| Works on classpath, fails on module path | Resource/descriptor mechanisms and module resolution differ | Test as proper named modules; check `module-info.class` |
| Adding `opens` to every package | Misunderstanding service lookup or trying to bypass encapsulation | Keep `exports`/`opens` minimal and use `provides` |

## 10. Three-Module Testing Strategy

1. **Contract unit tests:** verify API semantics and input/output formats.
2. **Host–provider integration tests:** run the host with a resolved provider, asserting counts/names and outputs.
3. **Negative tests:** run the host when no provider is present, verifying a clear error instead of silently continuing.
4. **Multi-provider tests:** add a second provider and verify both are found; test order-independent selection policies.
5. **Artifact tests:** use `dist/*.jar` on the module path, read `jar --describe-module`, and execute the exact launch command used in production.
6. **Compatibility tests:** verify older providers still work with newer contract versions when backward compatibility is claimed.

In CI, build and test the actual final modular JARs. Testing on an IDE classpath may fail to catch missing `module-info.class` files or unresolved providers.

## 11. Design Checklist

- [ ] The contract module contains only shared APIs and `exports` the appropriate packages.
- [ ] The host `requires` the contract, declares `uses`, and does not import concrete providers.
- [ ] The provider `requires` the contract, declares `provides ... with ...`, and has a valid implementation.
- [ ] Place provider modules in the runtime module graph/module layer.
- [ ] Verify `ServiceLoader` with the correct overload and classloader/layer.
- [ ] Manage API compatibility and avoid duplicating the service interface at runtime.
- [ ] Select providers based on application policy rather than discovery order.
- [ ] Test with released modular JARs, not just classes in the IDE.

**Key takeaway:** the contract module owns *what the service is*, the host owns *when and why the service is used*, and the provider owns *how the service is implemented*. JPMS expresses these boundaries via `requires`, `exports`, `uses`, and `provides`; `ServiceLoader` connects the components at runtime.
