# Choosing an Interface, Abstract Class, or Factory for an Extension Point

## 1. Understanding the Problem Correctly

An **extension point** is a location where an application or library allows external code to provide new behavior without modifying the core. In Java, typical examples include adding a data transformer, a rule validator, or an adapter for a third-party system.

Designing an extension point requires answering three **distinct** questions:

- **What must the extension code do?** This is the **behavioral contract**. An interface is usually the best fit.
- **Must implementations share a common workflow or base state?** An abstract class can provide an **implementation skeleton** and protect invariants.
- **Who selects, configures, and instantiates the implementation?** A factory is responsible for **instantiation and selection**.

Therefore, interfaces, abstract classes, and factories are not always three mutually exclusive options. A common design uses an **interface as the public contract**, an **abstract class as an optional base class**, and a **factory returning the interface**. The host depends only on the contract, not directly on individual plugins.

For example: a system receives text and applies multiple types of transformations. The host calls **Transformer.transform(input)**. Plugin developers provide Transformer implementations; a factory selects an implementation by name and configuration. Some plugins may extend a base class that handles input normalization, while others implement the interface directly.

## 2. Quick Comparison of the Three Tools

| Criterion | Interface | Abstract class | Factory |
|---|---|---|---|
| Primary purpose | Declare capabilities and invocation contract | Reuse code, preserve invariants, define workflows with hooks | Select and create objects, hide instantiation details |
| What the host sees | Abstract type and its methods | Often only needs to see the interface implemented by the base class | Creation method, configuration inputs, and result type |
| Multiple distinct implementation types | Very well suited, including classes that already have a superclass | Constrained by single class inheritance | Can create any implementation type matching the contract |
| Shared logic/state | Default methods support simple logic without instance state | Has fields, constructors, concrete methods, protected hooks | Manages configuration, dependencies, and creation/caching policies |
| Enforcing a sequence of steps | Only via specification and tests; default methods do not prevent overriding | Can use a public final template method | Not directly; can restrict creation to valid implementations |
| Adding providers at runtime | Combines with a registry, DI, or ServiceLoader | Does not solve provider discovery on its own | Can wrap a registry/ServiceLoader to select providers |
| Trade-offs | Contract must stay small, clear, and stable | Inheritance coupling and protected/constructor API surface | Adds a layer of indirection and lifecycle policy |

**Starting rule:** If an extension point only needs to describe "what to do", start with an **interface**. Only add an abstract class when there are shared invariants or workflows truly worth protecting. Add a factory when object selection or creation needs to be separated from the host.

## 3. When to Choose an Interface?

Choose an interface if:

1. The host only needs to invoke a capability; providers may use different algorithms, libraries, or superclasses.
2. Plugin authors should not be forced to extend a framework class hierarchy.
3. Providers need to be easily replaced with fakes/stubs in tests, or implemented as lambdas when the interface is a functional interface.
4. The contract needs to serve as a stable boundary between the core module and extension modules.

A minimal contract can look like this:

~~~java
/** Accepts a non-null string and returns a non-null string. */
public interface Transformer {
    String transform(String input);
}
~~~

This snippet describes **behavior**, without deciding who creates the object or which algorithm implements it. The comment needs to be turned into testable rules: how null is handled, whether input data may be mutated, which exceptions may be thrown, whether concurrent calls are safe, and whether resources need to be closed.

An interface can have default, static, and private methods (with an appropriate Java version), but **no per-instance state fields**. Default methods should provide independently meaningful default behavior; they should not be used to hide an overly large contract or force every plugin to follow unsuitable logic.

**Avoid a "god interface":** If each provider only supports a subset of dozens of methods, split the capabilities into small interfaces, or describe capabilities explicitly. Providing methods that throw UnsupportedOperationException everywhere is usually a sign of a flawed contract.

## 4. When to Choose an Abstract Class?

Choose an abstract class if implementations truly must share **a skeleton algorithm (Template Method)**, an invariant, or uniformly managed state. For example: every processor in a family must validate input, normalize it, measure execution time, and only then invoke the custom transformation step.

~~~java
import java.util.Objects;

// Illustrative snippet; Transformer is the interface defined above.
public abstract class NormalizingTransformer implements Transformer {
    @Override
    public final String transform(String input) {
        String normalized = Objects.requireNonNull(input, "input").strip();
        return transformNormalized(normalized);
    }

    protected abstract String transformNormalized(String normalized);
}
~~~

The **transform** method is marked **final**, so subclasses only customize the **transformNormalized** step and cannot bypass the null check and strip step managed by the base class. The base class can use a constructor to validate shared dependencies or state if genuinely needed.

In return, Java only allows **extending one class**. A provider that already extends another class cannot extend this base class. The protected API and constructors of the abstract class also become part of the compatibility surface that the library author must maintain.

Therefore, if you use a base class, prefer having it **implement the public interface**, while the host accepts the **interface**. Allow plugins to implement the interface directly without extending the base class; only put rules into the base class when they belong to the *family of implementations using that base class*. If a rule is mandatory for **all** providers, express it in the contract and enforce it at the host boundary instead of assuming every provider inherits from a single class.

**No abstract class is needed** if you only want to share a few stateless utilities: a helper/service passed via composition is usually less restrictive than inheritance.

## 5. When to Choose a Factory?

A factory answers the question: "Given a provider name, configuration, and available dependencies, how do we obtain an implementation instance?". It is useful when:

- An implementation must be chosen based on configuration, environment, feature flags, or system capabilities.
- Provider constructors differ, involving validation steps, dependency initialization, or resource management.
- The host should not know concrete class names or plugin construction details.
- You need to specify clearly whether to create a new object per request, one object per session, or cache a shared object.

A factory typically returns an **interface**, for example:

~~~java
import java.util.Map;

// Illustrative snippet; Transformer is defined above.
public interface TransformerFactory {
    Transformer create(String id, Map<String, String> options);
}
~~~

The interface is the **contract type of the product**; the factory is **how to obtain the product**. The two concepts complement each other. A factory itself can also be described by an interface to abstract over provider registration/discovery.

A factory is **not needed by default**: if there is only a simple class with a straightforward constructor and no selection or lifecycle policy, calling the constructor or letting a dependency-injection container create the object may suffice. Nor should you create a factory merely to rename the `new` operation without establishing a useful abstraction boundary.

In real systems, consider strongly typed configuration instead of a string Map; Map only keeps the example below concise and self-contained.

## 6. Complete Example: Combining All Three

The following Java 17 example is contained in **a single file ExtensionChoiceDemo.java**. The Transformer interface is the host contract; NormalizingTransformer is an **optional** base class; UppercaseTransformer extends the base class; PrefixTransformer implements the interface directly; the factory creates both and returns the same Transformer type.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class ExtensionChoiceDemo {
    @FunctionalInterface
    public interface Transformer {
        String transform(String input);
    }

    public static abstract class NormalizingTransformer implements Transformer {
        @Override
        public final String transform(String input) {
            String normalized = Objects.requireNonNull(input, "input").strip();
            return transformNormalized(normalized);
        }

        protected abstract String transformNormalized(String normalized);
    }

    public static final class UppercaseTransformer extends NormalizingTransformer {
        @Override
        protected String transformNormalized(String normalized) {
            return normalized.toUpperCase(Locale.ROOT);
        }
    }

    public static final class PrefixTransformer implements Transformer {
        private final String prefix;

        public PrefixTransformer(String prefix) {
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public String transform(String input) {
            return prefix + Objects.requireNonNull(input, "input");
        }
    }

    public interface TransformerFactory {
        Transformer create(String id, Map<String, String> options);
    }

    public static final class BuiltinTransformerFactory implements TransformerFactory {
        @Override
        public Transformer create(String id, Map<String, String> options) {
            Objects.requireNonNull(options, "options");
            return switch (Objects.requireNonNull(id, "id")) {
                case "upper" -> new UppercaseTransformer();
                case "prefix" -> new PrefixTransformer(
                        Objects.requireNonNull(options.get("prefix"), "missing prefix option"));
                default -> throw new IllegalArgumentException("Unknown transformer: " + id);
            };
        }
    }

    public static void main(String[] args) {
        TransformerFactory factory = new BuiltinTransformerFactory();

        Transformer first = factory.create("upper", Map.of());
        Transformer second = factory.create("prefix", Map.of("prefix", ">> "));

        System.out.println(first.transform("  java  "));
        System.out.println(second.transform("plugin"));
    }
}
~~~

Compile and run (requires JDK 17 or later):

~~~bash
javac -encoding UTF-8 ExtensionChoiceDemo.java
java ExtensionChoiceDemo
~~~

Expected output:

~~~text
JAVA
>> plugin
~~~

Explanation:

1. **first** receives an UppercaseTransformer implementation. The base class checks for null, trims leading/trailing whitespace using String.strip, and converts to uppercase with Locale.ROOT, so the output is "JAVA".
2. **second** receives a PrefixTransformer, which does not extend NormalizingTransformer. It prepends the prefix to the unmodified input, so the output is ">> plugin".
3. The host interacts only with **TransformerFactory** and **Transformer**. The host does not need to downcast or call either provider's constructor.
4. The factory here uses a **fixed switch** to keep the example self-contained and runnable. This works when the provider list is controlled by the application; if external JARs must register providers without editing the switch, replace the provider lookup with a registry, DI, or ServiceLoader.
5. The base class is optional: **strip is not a universal guarantee** of every Transformer. The shared contract only guarantees non-null input/output and per-implementation transform behavior. If the host should always receive normalized input, normalize at the host or explicitly specify and test that obligation for every plugin.

In a real project, separate the public interfaces into an API package, place providers in implementation modules, and place the factory/registry in the integration layer. Nested types in the example are only for running cleanly in a single file.

## 7. When Providers Come from External JARs/Modules

When "extensibility" means **adding new providers after the host has been compiled**, a **discovery mechanism** is needed alongside the interface/abstract class. Java provides **ServiceLoader**, or an application can use a DI container or its own registry.

A common design uses a **provider factory** instead of directly registering a Transformer instance that requires configuration:

~~~java
import java.util.Map;

// Illustrative API snippet in the SPI module; Transformer is the contract type.
public interface TransformerProvider {
    String id();
    Transformer create(Map<String, String> options);
}
~~~

The host can use ServiceLoader to find registered TransformerProvider instances, choose a provider by id, and call create. For providers on the classpath, the service file mechanism uses the path **META-INF/services/fully.qualified.name.of.TransformerProvider**, listing the fully qualified implementation class names; providers must satisfy ServiceLoader instantiation requirements, typically being a public class with a no-arg constructor. With the Java Platform Module System, the consuming module declares **uses**, and the provider module declares **provides ... with ...** and follows JPMS provider rules.

When switching from a switch statement to a registry, you also need to handle **duplicate ids**, missing providers, missing configuration, initialization failures, and lifecycle policies. You can instantiate a provider once while still creating a **new Transformer** per session if the implementation holds mutable state. Instantiate a single shared instance only when the contract confirms it is safe for concurrent access and compatible with the lifecycle.

**ServiceLoader is only a provider discovery/instantiation mechanism**, not a sandbox, hot-swap system, or automatic plugin unloader. If you need JAR loading/unloading, classloader/module-layer isolation, library version management, and resource cleanup, those responsibilities must be designed separately.

## 8. Checking the Robustness of an Extension Contract

A good extension point needs to specify more than method signatures:

| Contract aspect | Questions to answer |
|---|---|
| Input/output | Are null, empty data, null results, or mutating the input allowed? |
| Errors | Which exceptions may the plugin throw, and how does the host handle or wrap them? |
| Thread safety | Can one instance be called concurrently? May a provider store per-session state? |
| Lifecycle | Who creates, who closes, and when? Is AutoCloseable or a shutdown hook needed? |
| Resources | Who owns streams, executors, and connections, and who is responsible for cleanup? |
| Runtime behavior | Can a plugin run slowly, block, or call back into the host? What timeouts/limits are needed? |
| Compatibility | What is the minimum API, which versions are supported, and are there compatibility tests? |
| Independence | Does the contract expose concrete implementation/framework classes that make providers hard to replace? |

**Evolve the API carefully:**

- **Adding an abstract method to an interface** makes old implementations fail the new contract: old source code must be updated; if old binaries are still loaded, calling the missing method can lead to AbstractMethodError.
- **Adding a default method** often reduces the need to update implementations, but can still cause method conflicts or carry wrong semantics. Do not treat default methods as a compatibility guarantee in all cases.
- **Changing constructors, protected hooks, or adding abstract methods to an abstract class** can break external subclasses. Therefore, a base class should stay small, stable, and hold only genuine responsibilities.
- **Renaming provider ids, configuration keys, or factory error behavior** is also a contract change, even if Java signatures do not change.
- Split new capabilities into supplementary interfaces when doing so is cleaner than forcing all old providers to implement new methods.

To verify compatibility, build a **contract test suite** that runs against every implementation: checking null handling, outputs, errors, repeated calls, concurrent calls (if promised), lifecycle, and edge-case behavior. Test the factory separately for valid ids, unknown ids, invalid configuration, and object scope. In host tests, you can replace Transformer with a lambda returning fixed results to prove that the host genuinely depends only on the interface.

## 9. Common Wrong Choices and How to Fix Them

**Forcing every plugin to extend a large BasePlugin.** This locks in the inheritance path, forces providers to depend on unneeded hooks, and makes API evolution difficult. Extract a **small public interface**, keeping only an optional abstract base for implementation families with a shared workflow.

**Using an abstract class just to reuse a few lines.** If the logic does not need to enforce an algorithm, move it to a helper/service and use composition. Inheritance should only be used when an "is-a" relationship genuinely makes sense and hooks have clear boundaries.

**Host switching on concrete types, downcasting providers, and calling custom methods.** This means the Transformer contract is insufficient for the host's needs. Add an appropriate capability interface or redesign the SPI; keep the factory/registry at the object-creation boundary.

**Letting the factory also contain all processing algorithms.** The factory should focus on selection, configuration validation, and object construction. Business behavior belongs in the corresponding implementations; avoid a giant factory containing code for every plugin.

**Sharing a stateful singleton without defining thread safety.** If a Transformer keeps counters, buffers, or per-request context, sharing it can cause race conditions and cross-request data leaks. The factory must specify a clear scope; the provider must have a matching concurrency contract.

**Assuming ServiceLoader automatically guarantees safety and compatibility.** Discovery does not verify third-party code, restrict access permissions, or guarantee binary compatibility. You need to control which providers are allowed to load, API versions, dependencies, and isolation mechanisms if the environment requires them.

**Creating too many factory/abstract class layers before they are needed.** For two simple strategies, an interface with constructors/DI may be enough. Add a factory when a concrete selection/instantiation policy arises for a specific reason, and add an abstract class when a stable shared workflow emerges.

## 10. How to Decide for a New Extension Point

Follow this order:

1. **Write down the observable contract:** which methods does the host call, and what are the inputs/outputs, errors, concurrency, resources, and lifecycle? If multiple implementations do not share an inheritance relationship, describe it with an **interface**.
2. **Identify truly shared invariants:** is there a sequence of steps where subclasses may only override specific hooks? If so, build an **abstract class implementing the interface**, using final for template methods that must be protected. If only sharing utilities, prefer composition.
3. **Decide who creates the object:** does the host know the concrete type and is `new` always trivial, or do you need dynamic selection, dependency injection, configuration, or scope management? In the latter case, use a **factory returning the interface**.
4. **Determine how to locate providers:** if the provider set is closed, a switch/DI may suffice; if new JARs must self-register, design a provider registry or ServiceLoader behind the factory.
5. **Test a provider that does not use the base class and a fake for the host:** if the host still works through the interface without downcasting or knowing implementations, the extension boundary is being preserved properly.
6. **Test API version changes:** can a provider written against an older version still compile/run, and where are incompatibility errors detected?

### Three Typical Scenarios

| Scenario | Recommended choice | Reason |
|---|---|---|
| Allow third parties to add independent text-processing algorithms | **Interface** as SPI | Does not force providers into a superclass; host only calls the contract |
| Multiple parsers must all follow validate → read → parse → cleanup | **Interface + optional or family-required abstract class** | Template method controls the shared sequence and opens only needed hooks |
| Users pick providers by name; each provider needs its own token, config, connection, or scope | **Interface + factory**, optionally backed by registry/ServiceLoader | Separates algorithm from creation, selection, configuration, and lifecycle management |

**Criterion of a good design:** the host knows **the contract and how to request a provider**, each provider only needs to know **its own obligations**, and instantiation and implementation details stay behind the abstraction boundary.