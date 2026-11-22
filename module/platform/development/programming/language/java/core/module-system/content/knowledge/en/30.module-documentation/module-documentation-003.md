# Documenting requires, exports, uses, and provides

## 1. Why does module documentation need to spell out these four directives?

In the Java Platform Module System (JPMS), `module-info.java` is the technical contract between a named module and other modules. It states:

- `requires`: which modules this module needs to read.
- `exports`: which packages are exposed as APIs for other modules' code.
- `uses`: which service contracts this module consumes via service loading.
- `provides ... with ...`: which implementations this module registers for a service contract.

Merely seeing `public` classes in a JAR or a Maven/Gradle dependency list is not enough to understand the full JPMS contract. A module may sit on the module path without being resolved; a package containing public classes may remain unexported; a provider class may exist in the JAR without being registered via `provides`.

Therefore, a modular library's README should both present the **official descriptor** and explain **what it means for consumers and provider implementers**, while also providing ways to verify the built artifact.

Four questions documentation should answer clearly:

1. Which modules do library users need to declare in `requires`?
2. Which packages are actually public APIs and which are implementation details?
3. If the library uses services, which `uses` directive must consumer modules declare?
4. If the library provides a service, which provider class is registered and how is it loaded?

## 2. An example containing requires, exports, uses, and provides

Suppose a payment processing system consists of three parts:

~~~text
com.acme.payment.api       # Service contract and data exchange types
com.acme.payment.card      # Provider implementation module
com.acme.payment.checkout  # Application discovering and using providers
~~~

API module:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

Service interface:

~~~java
package com.acme.payment.api;

public interface PaymentProcessor {
    String providerId();
    boolean charge(long amountInCents);
}
~~~

Provider module:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.internal.CardPaymentProcessor;
}
~~~

Application module:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;

    uses com.acme.payment.api.PaymentProcessor;
}
~~~

At compile time, both the provider and consumer must read the API module. At runtime, the consumer uses `ServiceLoader` to locate providers participating in the module configuration. The consumer does not need `requires com.acme.payment.card;` just to use the provider through the service contract.

System documentation should explain each of these decisions, rather than pasting three descriptor files and leaving readers to deduce them.

## 3. Specifying module name and environment requirements

The top of a README should include a basic information block:

| Field | Example | Why document it |
|---|---|---|
| Module name | `com.acme.payment.api` | Consumers use the exact name in `requires` |
| Artifact | `com.acme:payment-api:1.2.0` | Build tools download the right dependency |
| Java baseline | JDK 21 | Avoids running with an incompatible runtime |
| Module type | Explicit named module | Distinguishes from automatic modules |
| Exports | `com.acme.payment.api` | Identifies public API |
| Services | `PaymentProcessor` | Clarifies service contract and provider discovery |
| Optional integrations | E.g., logging or SQL module | Identifies which dependencies are optional |

Maven/Gradle artifact names **do not necessarily match** the module name. For an explicit modular JAR, the module name is defined by the compiled descriptor. If users write the wrong `requires`, having a JAR with the right filename still will not let JPMS resolve the module.

In the README, prefer writing out the full module name instead of vague references like “the payment module”.

## 4. requires: clearly documenting modules to read and why

A descriptor snippet:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;
    requires java.logging;
}
~~~

should be explained:

- `requires com.acme.payment.api`: the application uses the payment API contract types.
- `requires java.logging`: the application uses the JDK logging API.
- `java.base` is read implicitly, so a `requires java.base;` line is usually unnecessary.

Example documentation table:

| Dependency module | Relationship type | Used for what? |
|---|---|---|
| `com.acme.payment.api` | `requires` | Accessing `PaymentProcessor` and public DTOs |
| `java.logging` | `requires` | Logging via `java.util.logging` |
| `java.base` | Mandated/implicit | Core Java types |

If a module is built with Maven or Gradle, include the corresponding artifact for third-party dependencies. A module name alone may not directly reveal the repository groupId, artifactId, and version.

**Do not merely list dependencies:** state which dependencies belong to the public contract, which only support implementation, and which must be supplied at runtime.

## 5. requires transitive: documentation must state impact on consumers

`requires transitive` is an important part of the public module contract.

Suppose a report module's public API returns a type from `java.sql`:

~~~java
module com.acme.report.api {
    requires transitive java.sql;
    exports com.acme.report.api;
}
~~~

Interface:

~~~java
package com.acme.report.api;

import java.sql.Connection;

public interface ReportService {
    void generate(Connection connection);
}
~~~

The `requires transitive java.sql` line grants modules that read `com.acme.report.api` readability to `java.sql` under JPMS rules. It is appropriate when a dependency's types appear in the API's public contract.

The README needs to state clearly:

- Which consumers can use the API without declaring `requires java.sql` separately?
- Why is the dependency transitive?
- Which types in the public API make that dependency part of the contract?
- If changed to a regular `requires`, how might consumers have to update `module-info.java`?

Do not use `requires transitive` for every module dependency just to “save compile errors”. Extending readability is an API design decision and should be recorded as part of the library's compatibility guarantee.

## 6. requires static: clearly documenting runtime conditions

Example of an optional integration:

~~~java
module com.acme.payment.integration {
    requires static com.acme.annotations;
}
~~~

`requires static` describes a dependency that must be resolved at compile time, but is not required to be present in the runtime configuration in the way a regular `requires` is.

Documentation should explain:

- What is the dependency used for at compile time?
- Are there any runtime code paths that actually need it?
- When enabling which features must consumers add the artifact/module?
- What is the fallback behavior if the dependency is absent?

Example description:

> The `com.acme.annotations` module is required when compiling sources that use supporting annotations. At runtime, the application does not need this module for basic payment flows; if enabling specific integration features, check their separate runtime requirements.

`requires static` is not directly equivalent to a Maven scope or Gradle configuration. Both the build-tool dependency and JPMS runtime rules must be documented clearly, especially when the library offers optional features.

## 7. exports: exposing API packages, not individual classes

Descriptor:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

This means eligible public types in the `com.acme.payment.api` package can be accessed by other modules when the consumer has readability. Other packages are not automatically exported.

Example:

~~~text
com.acme.payment.api
com.acme.payment.api.internal
com.acme.payment.internal
~~~

Exporting only `com.acme.payment.api` **does not recursively export** `com.acme.payment.api.internal` or `com.acme.payment.internal`.

In the README, include a clear list:

| Package | Status | Commitment |
|---|---|---|
| `com.acme.payment.api` | Exported | Public API for consumers |
| `com.acme.payment.card.internal` | Not exported | Provider detail, do not import directly |
| `com.acme.payment.api.internal` (if present) | Not exported | Internal helper, not a contract |

If source code contains a `public` class in an internal package, that does not make the class a usable API from another named module. Package boundaries are established by `exports`.

## 8. Qualified exports: granting API access only to specific modules

JPMS supports targeted exports:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;

    exports com.acme.payment.spi
        to com.acme.payment.card, com.acme.payment.wallet;
}
~~~

The corresponding README section should state:

- `com.acme.payment.api` is exported unconditionally.
- `com.acme.payment.spi` is exported only to `com.acme.payment.card` and `com.acme.payment.wallet`.
- Other modules cannot treat `spi` as a general public API without additional permission.
- Target modules still need an appropriate readability relationship to import types in the package.

Do not describe qualified exports with a generic sentence like “this package is public”. Specify **public to whom**, because any module outside the list can fail to compile even though the package exists in the JAR.

Qualified exports create coupling to target module names, so documentation must also be updated when collaborating modules are renamed.

## 9. Distinguishing exports from opens in documentation

Although the topic focuses on the four directives `requires`, `exports`, `uses`, and `provides`, a README also needs to explain `opens` when reflection frameworks are involved to avoid confusion.

Example:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
    opens com.acme.payment.model
        to com.fasterxml.jackson.databind;
}
~~~

Explanation:

- `exports` is for normal Java access to public APIs.
- `opens` grants deep reflection access into a package for the specified framework.
- A package that is `opens` does not thereby become a public API package for importing like an exported package.
- Nor does `exports` automatically allow frameworks to read/write arbitrary private fields.

If the framework runs in an unnamed module or another runtime configuration, the module name performing reflection may differ; deployment documentation must use the actual module identity.

Avoid putting `--add-opens` or `--add-exports` into default instructions if the descriptor can express the proper relationship. If launcher flags must be used during migration, clearly document the reason, target module, scope, and removal plan.

## 10. uses: clearly stating which module consumes a service

`uses` is a declaration on the module that **consumes** a service. Example:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;

    uses com.acme.payment.api.PaymentProcessor;
}
~~~

It does not select a specific provider. It indicates that the checkout module intends to look up implementations of `PaymentProcessor`.

Code example:

~~~java
package com.acme.payment.checkout;

import com.acme.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        PaymentProcessor processor =
                ServiceLoader.load(PaymentProcessor.class)
                        .findFirst()
                        .orElseThrow(() ->
                                new IllegalStateException(
                                        "No PaymentProcessor provider"));

        System.out.println(processor.providerId());
    }
}
~~~

The consumer's README should answer:

1. What is the exact service type?
2. Which module declares `uses`?
3. Is at least one provider required to start up?
4. If no provider is present, how does the consumer handle an empty result?
5. If multiple providers exist, what criteria does the selection logic use?

If code running from a named module calls `ServiceLoader` directly, the caller module's descriptor needs the corresponding `uses`. Declaring only `requires` on the API module does not replace `uses`.

## 11. provides ... with ...: clearly documenting registered implementations

Provider module:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.internal.CardPaymentProcessor;
}
~~~

Implementation:

~~~java
package com.acme.payment.card.internal;

import com.acme.payment.api.PaymentProcessor;

public final class CardPaymentProcessor
        implements PaymentProcessor {

    public CardPaymentProcessor() {
    }

    @Override
    public String providerId() {
        return "card";
    }

    @Override
    public boolean charge(long amountInCents) {
        return amountInCents > 0;
    }
}
~~~

The provider's README should state:

| Item | Value |
|---|---|
| Provider module | `com.acme.payment.card` |
| Service type | `com.acme.payment.api.PaymentProcessor` |
| Implementation | `com.acme.payment.card.internal.CardPaymentProcessor` |
| Provider identifier | `card` |
| Dependency | `requires com.acme.payment.api` |
| Activation | Include the provider module in the runtime configuration |
| Provider's public packages | No need to export the implementation package just for ServiceLoader to find the provider |

The provider class can be declared in an unexported package. JPMS service binding uses `provides` metadata, so consumers do not need to import the implementation class.

`ServiceLoader` supports a valid provider constructor or provider method according to JPMS rules. If the library uses a special approach, describe the instantiation mechanism and constructor/`provider()` requirements in the guide for provider maintainers.

## 12. Service API and provider should not be forced into reverse dependencies

A common architecture:

~~~text
checkout module ------requires------> payment API module
                                        ^
                                        |
                                     requires
                                        |
                                    card provider module
~~~

The contract lives in the API module. The provider implements the contract and the consumer uses the contract.

Do not write:

~~~java
// Coupling-prone design, not the default choice
module com.acme.payment.api {
    requires com.acme.payment.card;
}
~~~

just to bring the provider into runtime. Doing so couples the API to a specific implementation, reducing provider substitutability.

Instead, deployment documentation can show how to add the provider as a root module when needed:

~~~bash
java --module-path mods \
  --add-modules com.acme.payment.card \
  -m com.acme.payment.checkout/com.acme.payment.checkout.Main
~~~

Or use service binding in the appropriate configuration/module layer. Finding providers depends on the actual module configuration, not merely on the presence of JARs in a directory.

## 13. Documenting ServiceLoader with module layers

In a plugin architecture, providers may reside in a custom `ModuleLayer` rather than the boot layer.

In that case, usage instructions should distinguish:

~~~java
ServiceLoader.load(PaymentProcessor.class)
~~~

and:

~~~java
ServiceLoader.load(pluginLayer, PaymentProcessor.class)
~~~

The overload taking `ModuleLayer` searches for providers in the given layer and its related ancestor layers. Therefore, if you need to find only providers from the custom layer, you can check the module/layer of the provider class:

~~~java
var providers =
        ServiceLoader.load(pluginLayer, PaymentProcessor.class)
                .stream()
                .filter(p ->
                        p.type().getModule().getLayer() == pluginLayer)
                .toList();
~~~

The README should state how the application creates or obtains `pluginLayer`, which modules are placed into the configuration, and how consumers identify expected providers.

If there are multiple layers or multiple providers, do not make blanket claims like “putting the JAR on the module path automatically uses it”. Clearly specify the resolution/service-binding mechanism and instantiation approach.

## 14. Contract table: requires, exports, uses, provides

In a modular library's README, a summary table often helps readers orient quickly:

| Directive | Located in module | Meaning | What consumer/provider must do |
|---|---|---|---|
| `requires com.acme.payment.api` | Checkout | Consumer reads API module | Ensure API module is on the module path |
| `requires com.acme.payment.api` | Card provider | Provider implements API contract | Use the exact same service class identity |
| `exports com.acme.payment.api` | Payment API | Public API usable by other modules | Import only public types from exported packages |
| `uses PaymentProcessor` | Checkout | Consumer requests service | Call ServiceLoader and handle missing providers |
| `provides PaymentProcessor with CardPaymentProcessor` | Card provider | Registers implementation | Include provider module in runtime configuration |

You can add version/artifact columns if the system has many third-party dependencies.

This table should be derived from the descriptor of the **released artifact**, not solely from source intent. If the build pipeline creates a multi-release JAR or alters descriptors by profile, record the exact configuration users actually download.

## 15. A usable README should give consumers concrete instructions

Short guide snippet example:

### Adding the module to a project

For consumers on the module path, add the `payment-api` artifact and required dependencies to your build tool, then declare:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

### Adding a provider

Add the `payment-card` artifact to the runtime module path. Ensure the `com.acme.payment.card` module is resolved, for instance with `--add-modules` if the launch configuration does not automatically include providers.

### Discovering a provider

~~~java
PaymentProcessor processor =
        ServiceLoader.load(PaymentProcessor.class)
                .findFirst()
                .orElseThrow();
~~~

### Handling failures

If no provider is found:

- Verify the caller module declared `uses`.
- Verify the provider module has `provides`.
- Verify the provider module was resolved.
- Verify consumer/provider service types share the same class identity.
- Check provider instantiation errors from the actual exception.

Concrete steps like these are far more valuable than a README line simply saying “supports ServiceLoader”.

## 16. Distinguishing required, optional, and build/test-only dependencies

A modular README should avoid mixing dependency categories.

Example:

| Component | At compile time | At runtime | Notes |
|---|---|---|---|
| `com.acme.payment.api` | Required for consumer/provider | Required when consumer/provider uses contract | Named API module |
| `com.acme.payment.card` | Consumer does not need to compile against provider class | Needed when selecting card provider | Service implementation |
| `java.logging` | Needed if module imports logging API | Usually needed per module graph | JDK module |
| Annotation helper `com.acme.annotations` | May only be needed at compile time | Depends on design | Consider `requires static` |
| JUnit or test fixtures | For tests | Not a production dependency | Keep out of normal runtime guides |

This information needs to align with Maven/Gradle dependency scopes/configurations. For instance, in Gradle `api` and `implementation` govern how dependencies appear on a consumer's compile classpath; whereas `requires` and `requires transitive` are JPMS readability relationships. The two systems are related but not identical.

## 17. Inspecting the descriptor after building

The `module-info.java` file in source may differ from the published artifact due to build steps, packaging, or profiles. Therefore, release documentation should include a command to inspect the modular JAR directly:

~~~bash
jar --describe-module --file dist/com.acme.payment.api.jar
~~~

For the provider:

~~~bash
jar --describe-module --file dist/com.acme.payment.card.jar
~~~

The `provides` line must show the corresponding service type and implementation. Check `exports`, `requires`, and any qualified exports/opens.

You can list JAR contents:

~~~bash
jar --list --file dist/com.acme.payment.api.jar
~~~

For a typical explicit modular JAR, `module-info.class` must exist at the root:

~~~text
module-info.class
com/acme/payment/api/PaymentProcessor.class
~~~

If a JAR lacks an explicit descriptor, placing it on the module path may turn it into an automatic module. Its readability/export contract then differs from an explicit module; the README must accurately describe the module type being released.

## 18. Viewing modules from the Java launcher's perspective

For built modules under a `mods` directory, you can run:

~~~bash
java --module-path mods \
  --describe-module com.acme.payment.api
~~~

Or:

~~~bash
java --module-path mods \
  --describe-module com.acme.payment.card
~~~

To see which modules are observable to the launcher:

~~~bash
java --module-path mods --list-modules
~~~

And to observe module resolution when running the application:

~~~bash
java --show-module-resolution \
  --module-path mods \
  --add-modules com.acme.payment.card \
  -m com.acme.payment.checkout/com.acme.payment.checkout.Main
~~~

Distinguish:

- `jar --describe-module`: describes a specific JAR artifact.
- `java --describe-module`: describes an observable module given the current module path/runtime.
- `--show-module-resolution`: observes the module graph resolved when launching the application.

The README should clarify which command serves which purpose. Successfully describing a module does not by itself prove a provider was selected or the program ran properly.

## 19. Avoiding misleading statements about encapsulation

Some statements to avoid:

| Misleading statement | Appropriate phrasing |
|---|---|
| “Having `requires` lets you use every class in the dependency” | `requires` creates readability; the package must still be appropriately exported |
| “`exports` makes the whole module public” | `exports` exposes a specific package, non-recursively |
| “A `public` class in an internal package is always usable” | Other named modules remain bound by `exports` |
| “`uses` guarantees a provider exists” | `uses` only declares the need to consume a service |
| “`provides` always causes the provider to run” | The provider must be in the configuration/layer and instantiated by ServiceLoader when needed |
| “The provider package must be `exports`ed to consumers” | With a valid `provides`, there is no need to export the implementation package just for service loading |
| “`opens` is like `exports`” | `opens` is for deep reflection, whereas `exports` is for normal Java access |
| “The JAR name is the module name” | Explicit module names come from the descriptor; automatic modules have their own naming rules |

Documentation language should distinguish compiler behavior, module resolver behavior, and ServiceLoader behavior. These are distinct phases.

## 20. Documenting breaking changes to the module contract

Not every change to `module-info.java` is harmless.

Examples of changes that can affect consumers:

- Renaming a module used in `requires`.
- Removing an `exports` or switching an unconditional export to a qualified export.
- Renaming an exported API package.
- Changing `requires transitive` to `requires` when consumers rely on transitive readability.
- Removing or changing an exposed service contract.
- Removing a provider that consumers expect at runtime.
- Changing a constructor/provider method such that service instantiation is no longer compatible.

The README and release notes should document:

1. Old and new module names, if any.
2. Packages whose exports were added or removed.
3. Dependencies added, removed, or whose modifiers changed.
4. Services in `uses`/`provides` added or removed.
5. Migration actions that consumers or provider authors need to take.

A release keeping the same artifact name while renaming the module can force every named-module consumer to edit its descriptor; do not summarize it merely as “internal refactor”.

## 21. Organizing documentation for a multi-module repository

If a repository has multiple modules:

~~~text
payment/
├── payment-api/
├── payment-card/
├── payment-wallet/
└── checkout-example/
~~~

Split documentation into two levels:

**Repository-level README:** presents the overall module graph, Java version, shared dependency management, build instructions, and how to run examples.

**Module-level README:** describes the specific `module-info.java`, exported packages, service contracts, implementations, module dependencies, and guides for consumers/providers.

Overview table example:

| Module | Role | Requires | Exports | Uses | Provides |
|---|---|---|---|---|---|
| `com.acme.payment.api` | Contract | `java.base` implicit | `com.acme.payment.api` | None | None |
| `com.acme.payment.card` | Provider | `com.acme.payment.api` | No need to export implementation | None | `PaymentProcessor` |
| `com.acme.payment.checkout` | Consumer | `com.acme.payment.api` | Not required | `PaymentProcessor` | None |

You can create a dependency diagram, but the diagram must match the built descriptors. If custom `ModuleLayer`s are used, add a diagram showing parent/child layers and where providers are loaded.

## 22. README section template for a named module

Below is a reusable structure:

~~~markdown
# com.acme.payment.card

## Module info
- Module name: com.acme.payment.card
- Artifact: com.acme:payment-card:1.2.0
- Java baseline: 21
- Type: explicit named module

## Module descriptor
~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.internal.CardPaymentProcessor;
}
~~~

## Requires
- com.acme.payment.api: required service contract.

## Exports
- Does not export the implementation package.

## Uses
- This module does not call ServiceLoader for other contracts.

## Provides
- Service: com.acme.payment.api.PaymentProcessor
- Implementation: com.acme.payment.card.internal.CardPaymentProcessor

## Integration
- Consumers need requires com.acme.payment.api and uses PaymentProcessor.
- The provider module must be included in the runtime configuration.

## Verification
- jar --describe-module --file payment-card.jar
- java --module-path mods --describe-module com.acme.payment.card
~~~

In real Markdown, if nesting code fences, use a longer outer fence than inner fences or separate code blocks so content renders properly.

This template saves readers from hunting down service contracts in source code, while reducing the risk of documentation describing only classes and omitting module boundaries.

## 23. Verification steps before publishing documentation

A workflow to keep documentation aligned with artifacts:

1. Clean-build all modules with the target JDK.
2. Confirm module names and descriptors of each final JAR.
3. List all `requires`, including `transitive` and `static` if present.
4. Cross-check the `exports` list against the promised public APIs.
5. Verify qualified exports/opens and target modules.
6. List `uses` services of consumers.
7. List `provides` services and provider implementations.
8. Run the consumer example on the module path instead of only the classpath.
9. If providers exist, run the ServiceLoader example with the provider module resolved.
10. Cross-check Maven/Gradle metadata against actual module names and dependencies.
11. Update the README and migration notes when descriptors change.
12. Publish artifacts and documentation under the same version.

When supporting multiple JDK versions, document differences if the module graph or JDK dependencies change. Do not hard-copy results from one JDK and claim they hold for every runtime.

## 24. Short checklist for README authors

- [ ] State the exact **module name**, not just the artifact/JAR name.
- [ ] Provide a working `module-info.java` example.
- [ ] Explain each `requires` and distinguish `transitive`/`static` when used.
- [ ] Clearly list which packages are `exports`ed and which are internal.
- [ ] If qualified exports exist, specify the target modules.
- [ ] If `opens` exists, state the reflection purpose and authorized modules.
- [ ] If `uses` exists, state the service type and how consumers handle missing providers.
- [ ] If `provides` exists, state the service interface and implementation type.
- [ ] Instruct how to include the provider module in the module configuration.
- [ ] Do not require consumers to import the provider implementation package when the design relies on ServiceLoader.
- [ ] State the Java baseline, dependency artifacts, and sample run commands.
- [ ] Include `jar --describe-module` commands to inspect the final artifact.
- [ ] Include a standalone consumer example to verify the contract.
- [ ] Document module contract changes in release notes.

## 25. Key takeaways

For a modular library, good documentation must reflect the **module contract**, not merely list classes in a JAR.

- **`requires`:** which modules the module reads, which dependencies propagate transitively to consumers, and which dependencies are compile-only.
- **`exports`:** which packages are supported as public API and which packages are kept internal.
- **`uses`:** which service contracts the module needs to discover and how provider discovery is handled.
- **`provides`:** which implementations the module registers and how providers are brought into runtime.

Write the README from the user's perspective: **which artifacts to add, how to declare module-info.java, which packages to import, how to discover providers, and where to check for errors**. When this information matches the published `module-info.class`, users can integrate the module more reliably while keeping API/implementation boundaries clear.
