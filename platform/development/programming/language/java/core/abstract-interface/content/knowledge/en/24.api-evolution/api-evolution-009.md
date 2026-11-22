# Java API Evolution: Subinterfaces, Adapters, and Deprecation

## 1. Why Is a Migration Path Needed?

Public APIs are often used by multiple applications, libraries, and development teams. After release, changing a method signature or adding a required method to an interface can prevent user source code from compiling, or cause already-compiled programs to fail at runtime. Therefore, API evolution requires clear transition steps and compatibility rules.

Three techniques are commonly combined:

- **Subinterface:** creates a new contract that extends the old contract, so that new capabilities have their own type without forcing every old implementation to change immediately.
- **Adapter:** wraps an old or new implementation and translates calls between the two contracts when the conversion can be clearly defined.
- **Deprecation:** marks the old API as no longer recommended, points to the replacement option, and gives users time to migrate before considering removal.

Each technique addresses a different part. A subinterface expresses type relationships; an adapter forwards or translates behavior; deprecation communicates the API lifecycle. They do not automatically guarantee that every change is compatible. Before releasing, you need to determine whether the goal is source compatibility, binary compatibility, behavioral compatibility, or all three.

## 2. Compatibility Goals During Migration

Before creating a bridge, determine whether old clients need to **be able to recompile** against the new API (source), **use old bytecode** with the new library (binary), or **preserve committed behavior** (behavioral). Subinterfaces help avoid modifying the old contract; adapters help translate calls between the two contracts; deprecation signals how and when to migrate. An adapter may resolve type errors yet still drop data or change exceptions, so test all three goals.

## 3. API Evolution Roadmap

1. **Survey the current contract.** List public types and methods, external implementations, clients currently using the API, and expected behavior.
2. **Design the new contract.** Identify added capabilities, parts whose semantics change, and parts that cannot be converted automatically. Preserve released signatures if possible.
3. **Add the new API.** Create a subinterface or new type for the new capabilities; keep the old API working during the transition period.
4. **Provide an adapter.** Forward equivalent operations and explicitly handle cases that cannot be mapped.
5. **Mark as deprecated.** State the reason, the replacement API, behavioral differences, and the expected removal timeline if planned.
6. **Test and monitor.** Verify old and new clients, old and new implementations, the adapter, and unsupported cases.
7. **Remove according to release policy.** Only remove the old API after a transition period appropriate to your compatibility commitments and user dependency levels.

For libraries with external users, the old and new APIs should generally coexist for at least one deprecation period. The exact timeline depends on the versioning policy and the impact of the change.

## 4. Using a Subinterface to Extend a Contract

Suppose the old API only accepts a name, whereas the new API also needs a locale to generate a language-specific greeting. You can create a new interface that extends the old interface, adds the new method, and provides a default method for the old signature:

~~~java
@Deprecated(since = "2.0", forRemoval = false)
interface LegacyGreeting {
    String greet(String name);
}

record GreetingRequest(String name, String locale) {
}

interface GreetingService extends LegacyGreeting {
    String greet(GreetingRequest request);

    @Override
    default String greet(String name) {
        return greet(new GreetingRequest(name, "en"));
    }
}
~~~

`GreetingService` is a subinterface of `LegacyGreeting`, so an object implementing GreetingService can also be used wherever LegacyGreeting is required. The default method forwards the legacy `greet(String)` call to the new method with a default locale of `en`.

However, an old implementation that only implements LegacyGreeting **does not automatically become** a GreetingService. Inheritance does not turn an existing object into an instance of the subinterface. An adapter can act as a bridge for this case.

The default method must have sensible semantics. In this example, the `en` locale is an intentional decision. If there is no suitable default value, require clients to call the new API or return a clear error rather than choosing an arbitrary value.

## 5. Using an Adapter to Wrap an Old Implementation

The adapter implements the new interface while accepting an instance of the old interface in its constructor. When a client calls the new method, the adapter translates the request to the old operation if possible:

~~~java
final class LegacyGreetingAdapter implements GreetingService {
    private final LegacyGreeting legacy;

    LegacyGreetingAdapter(LegacyGreeting legacy) {
        this.legacy = legacy;
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!"en".equals(request.locale())) {
            throw new IllegalArgumentException(
                    "Legacy API supports only en");
        }
        return legacy.greet(request.name());
    }
}
~~~

This adapter only supports the `en` locale because the old API does not accept locale information. For other locales, it throws a clear error instead of pretending to support localization. If the old API can represent sufficient data, the adapter can convert automatically; otherwise, the documentation must clearly state the limitation.

There are two common forwarding directions:

- **Old to new:** wraps an old implementation so that clients expecting the new interface can use it.
- **New to old:** provides a compatible view for old clients when the internal implementation has already moved to the new API. A default method on the subinterface may suffice for this direction; if the two models differ significantly, a dedicated adapter may be needed.

Two adapters are not always required. Create only the necessary bridges and avoid duplicating logic if a default method or a facade already satisfies the contract.

## 6. Complete Java 17 Example

The following program demonstrates both directions. ModernGreetingService implements the new contract while still being usable by old clients through LegacyGreeting. Conversely, LegacyGreetingAdapter wraps an old implementation so that new clients can call it via GreetingService.

~~~java
@Deprecated(since = "2.0", forRemoval = false)
interface LegacyGreeting {
    String greet(String name);
}

record GreetingRequest(String name, String locale) {
}

interface GreetingService extends LegacyGreeting {
    String greet(GreetingRequest request);

    @Override
    default String greet(String name) {
        return greet(new GreetingRequest(name, "en"));
    }
}

final class SimpleLegacyGreeting implements LegacyGreeting {
    @Override
    public String greet(String name) {
        return "Legacy hello, " + name;
    }
}

final class LegacyGreetingAdapter implements GreetingService {
    private final LegacyGreeting legacy;

    LegacyGreetingAdapter(LegacyGreeting legacy) {
        this.legacy = legacy;
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!"en".equals(request.locale())) {
            throw new IllegalArgumentException(
                    "Legacy API supports only en");
        }
        return legacy.greet(request.name());
    }
}

final class ModernGreetingService implements GreetingService {
    @Override
    public String greet(GreetingRequest request) {
        return switch (request.locale()) {
            case "en" -> "Hello, " + request.name();
            case "vi" -> "Xin chào, " + request.name();
            default -> throw new IllegalArgumentException(
                    "Unsupported locale: " + request.locale());
        };
    }
}

public class Main {
    @SuppressWarnings("deprecation")
    public static void main(String[] args) {
        GreetingService modern = new ModernGreetingService();

        // Old clients still use the new implementation through the old type.
        LegacyGreeting oldView = modern;
        System.out.println("Old client -> " + oldView.greet("Linh"));

        // New clients use the old implementation through the adapter.
        GreetingService adapted =
                new LegacyGreetingAdapter(new SimpleLegacyGreeting());
        System.out.println("New client -> "
                + adapted.greet(new GreetingRequest("An", "en")));

        // Default method forwards the old call to the new API.
        System.out.println("Default bridge -> " + adapted.greet("Mai"));

        try {
            adapted.greet(new GreetingRequest("An", "vi"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Unsupported feature -> " + ex.getMessage());
        }
    }
}
~~~

Save the entire program to `Main.java`, then compile and run it using JDK 17 or later:

~~~text
javac Main.java
java Main
~~~

Exact stdout output:

~~~text
Old client -> Hello, Linh
New client -> Legacy hello, An
Default bridge -> Legacy hello, Mai
Unsupported feature -> Legacy API supports only en
~~~

The first line shows that the new implementation can still be used through the old type thanks to the default method. The second line shows the adapter wrapping the old implementation to satisfy the new API. The third line demonstrates the default bridge; the last line illustrates the adapter rejecting a request that the old API cannot represent.

The switch expression in this example is standard syntax since Java 14, so no preview features need to be enabled on Java 17. Non-public types can reside in the same file as public class Main.

## 7. Intentional Deprecation

Use `@Deprecated` to signal that an API is no longer recommended. Since Java 9, the annotation supports two important attributes:

- `since`: the version in which the API was deprecated, for example `since = "2.0"`.
- `forRemoval`: indicates whether the API is scheduled for removal. `false` is appropriate when initially advising migration; `true` expresses a stronger intent to remove.

The annotation does not migrate users automatically, does not create adapters, and does not delete methods. Supplement it with a `@deprecated` Javadoc tag stating the reason and the replacement API. The standalone illustrative example below reuses the type name from the main program, so you do not need to paste this snippet into the same `Main.java` file:

~~~java
/**
 * @deprecated Use {@link GreetingService} instead.
 *     This legacy API does not support locale selection.
 */
@Deprecated(since = "2.0", forRemoval = false)
interface LegacyGreeting {
    String greet(String name);
}
~~~

Keep guidance consistent across the annotation, Javadoc, release documentation, and examples. Only set `forRemoval = true` when there is an actual intent to remove and a timeline that aligns with the library's compatibility policy.

## 8. Publishing and Maintaining the Transition Period

When introducing a new API, continue shipping the old signatures for the committed compatibility window; publish the adapter, deprecation Javadoc, and migration instructions in the same release. Monitor where the old API is still used, test running client bytecode from previous versions, and measure the cases the adapter cannot represent. Only switch `forRemoval` to `true` once the removal plan is clear, and avoid deleting the old API immediately after releasing the new type.

## 9. Limitations to Handle in Adapters

A good adapter performs an explainable mapping and discloses incompatibilities. Pay attention to:

- **Information loss:** The old API lacks new data fields. Specify default values, reject the request, or require an explicit conversion policy.
- **Error differences:** The new API may use different result types or exceptions. The adapter must translate intentionally and preserve necessary causes.
- **Lifecycle differences:** The new API may require resource closing, task cancellation, or state management that the old API does not support.
- **Recursive call loops:** If a default method calls the new API while an adapter calls back into the old method, ensure there is a concrete implementation point that terminates the call. Two bridges calling each other can cause infinite recursion.
- **State and threading:** If the new API adds thread safety, immutability, or synchronization, the adapter should only promise what it actually guarantees.

Document limitations in Javadoc and test unmappable cases. A transparent adapter may reject unsupported operations; silently returning dummy values often causes harder-to-detect bugs.

## 10. Testing the Migration Path

1. **Old implementations:** Verify that classes implementing only the old interface still work with the supported library version.
2. **New implementations:** Verify that new classes implement the subinterface and work through both the new and old types.
3. **Adapter:** Test data, results, exceptions, and unsupported cases.
4. **Old and new clients:** Compile old clients against the old API and test them in the supported upgraded environment; compile new clients against the new API.
5. **Compatibility testing:** If binary compatibility is committed, use an API/binary compatibility checker or a compatibility test suite.
6. **Documentation:** Verify migration guides, examples, deprecation Javadoc, and release notes.

Running tests only after recompiling all source code is not enough to prove binary compatibility. When a library makes this commitment, keep compiled artifacts from previous versions in the test suite.

## 11. Choosing a Technique by Scenario

| Scenario | Approach |
|---|---|
| Want to add capabilities while keeping the old type as the base contract | Create a subinterface and place the new methods there. |
| Old clients need to use a new implementation | Make the new type compatible with the old type via a subinterface and a default method with valid semantics. |
| New clients need to use an implementation that only implements the old API | Write an adapter from the old interface to the new interface. |
| There is a valid default behavior for all old implementations | Consider a default method after checking for conflicts and semantics. |
| The two APIs differ significantly in data or behavior | Design an explicit conversion; an independent new API may be needed. |
| The old API already has a stable replacement | Mark it deprecated, provide migration guidance, and plan removal according to the versioning policy. |

There is no single pattern for every change. Base your decision on the number of external implementations, the committed compatibility level, semantic differences, and the cost of supporting two contracts during the transition period.

## 12. Common Mistakes

- **Adding abstract methods directly to a public interface without assessing impact.** External implementations may fail to compile or fail to satisfy the new calls.
- **Assuming a subinterface automatically turns an old implementation into a new one.** An adapter or an explicit change in the implementing class is required.
- **Using a default method with arbitrary values.** Only use one when the default is valid and documented.
- **Marking something deprecated without stating a replacement.** Users need to know which type or method to use instead and what the differences are.
- **Setting `forRemoval = true` before a roadmap exists.** The annotation should reflect actual release intent.
- **Ignoring lost data in an adapter.** Do not silently drop locale, state, errors, or data required by the new API.
- **Testing only after recompiling the entire project.** That does not prove old binaries remain compatible.
- **Deleting the old API immediately upon creating the new API.** Maintain a transition period matching the library's commitments.

## 13. Key Takeaways

Safe API evolution requires a clear new contract, bridges with well-defined behavior, and early deprecation notices. A subinterface extends capabilities while preserving the old type as the base contract; an adapter enables using an old implementation with the new API or vice versa; `@Deprecated` informs users of the migration path. Distinguish between source, binary, and behavioral compatibility, verify mapping limitations, test with old implementations and clients, and only remove APIs after a transition period aligned with your versioning policy.
