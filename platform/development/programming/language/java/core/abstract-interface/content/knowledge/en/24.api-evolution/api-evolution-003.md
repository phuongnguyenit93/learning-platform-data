# Java 17 Milestone for Sealed Classes and Sealed Interfaces

Java 17 marks the point when **sealed classes and sealed interfaces became an official feature of the Java language**. They allow API authors to control which types can directly extend or implement a supertype. This is useful when an API wants to publish an intentional set of variants while still needing to allow certain branches to be extended.

Sealed types are directly relevant to API evolution: they clarify which parts of the hierarchy are controlled by the library, which parts are allowed to be extended, and what changes need to be considered when releasing a new version.

## 1. Historical Milestone and Stable Syntax

Sealed classes were trialed as a preview in JDK 15, continued in JDK 16, and were finalized in JDK 17 under JEP 409. Starting in Java 17, `sealed`, `permits`, and `non-sealed` can be used as official syntax without enabling preview features.

Example of declaring an interface that permits only two direct types:

~~~java
sealed interface ApiResult permits ApiSuccess, ApiFailure {
}
~~~

`ApiSuccess` and `ApiFailure` must be direct subtypes of `ApiResult`. Each direct subtype must explicitly specify whether its branch will be closed, continue to be controlled, or be opened to other types.

~~~java
record ApiSuccess(String value) implements ApiResult {
}

record ApiFailure(int code, String message) implements ApiResult {
}
~~~

These two records are implicitly final according to Java's rules, so they satisfy the requirement of the sealed interface. They do not need to include the `final` keyword.

## 2. Three Options for Direct Subtypes

A class or interface listed in `permits` must declare how its branch continues:

| Declaration | Meaning in the Hierarchy |
|---|---|
| `final` | Closes the branch at this class; prevents other classes from extending it. |
| `sealed` | Continues to restrict direct subtypes with its own `permits` list. |
| `non-sealed` | Opens this branch so other types can extend or implement it without needing to be listed in the `permits` list of the root sealed type. |

Records are always implicitly `final`. An enum with no constants declaring their own class body is implicitly `final`; an enum with at least one constant having its own class body is implicitly `sealed`. An interface cannot be declared `final`; if an interface is a direct subtype of a sealed type, it must be `sealed` or `non-sealed`.

Example of a controlled level:

~~~java
sealed interface ApiResult permits ApiSuccess, ApiFailure, ApiDeferred {
}

sealed class ApiFailure implements ApiResult
        permits NotFoundFailure, ValidationFailure {
}

final class NotFoundFailure extends ApiFailure {
}

final class ValidationFailure extends ApiFailure {
}
~~~

This snippet illustrates type relationships, not a complete program. `ApiFailure` has its own `permits` list because it is a sealed class. Its two subtypes close their branches with `final`.

An open branch can be declared as follows:

~~~java
non-sealed interface ApiDeferred extends ApiResult {
    String retryAfter();
}

final class RetryLater implements ApiDeferred {
    @Override
    public String retryAfter() {
        return "30 seconds";
    }
}
~~~

`ApiDeferred` must still appear in the `permits` list of `ApiResult`, because it is a direct subtype. However, `RetryLater` only implements `ApiDeferred`; it does not need to appear in `ApiResult`'s list, because that relationship is indirect.

## 3. Rules for Packages, Modules, and the permits List

Java applies several constraints to keep a sealed hierarchy controlled:

- The types named in `permits` must actually be direct subtypes of that sealed class or sealed interface.
- In a named module, the sealed type and its permitted direct subtypes must belong to the same module.
- In an unnamed module, the sealed type and its permitted direct subtypes must belong to the same package.
- Each direct subtype must be `final`, `sealed`, or `non-sealed`, except for types such as records that are implicitly final.
- If the `permits` clause is omitted, Java infers the permitted subtypes from matching declarations in the same compilation unit.

These restrictions are significant for public APIs. A sealed interface in a library cannot be arbitrarily implemented by a class in an external module. If third-party extensions need to be supported, the API can provide a `non-sealed` branch as an extension point, or choose an unsealed interface from the start.

## 4. Complete Example Running on Java 17

Save the following program as the file `SealedApiDemo.java`. The example demonstrates a result API with two closed variants and an extensible deferred branch. The program uses pattern matching with `instanceof`, which was already an official feature before Java 17; it does not use preview switch patterns.

~~~java
public class SealedApiDemo {
    public static void main(String[] args) {
        ApiResult[] results = {
            new ApiSuccess("created"),
            new ApiFailure(404, "Not found"),
            new RetryLater("30 seconds")
        };

        for (ApiResult result : results) {
            if (result instanceof ApiSuccess success) {
                System.out.println("SUCCESS: " + success.value());
            } else if (result instanceof ApiFailure failure) {
                System.out.println(
                        "ERROR " + failure.code() + ": " + failure.message());
            } else if (result instanceof ApiDeferred deferred) {
                System.out.println("DEFERRED: retry after " + deferred.retryAfter());
            }
        }
    }
}

sealed interface ApiResult
        permits ApiSuccess, ApiFailure, ApiDeferred {
}

record ApiSuccess(String value) implements ApiResult {
}

record ApiFailure(int code, String message) implements ApiResult {
}

non-sealed interface ApiDeferred extends ApiResult {
    String retryAfter();
}

final class RetryLater implements ApiDeferred {
    private final String delay;

    RetryLater(String delay) {
        this.delay = delay;
    }

    @Override
    public String retryAfter() {
        return delay;
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 SealedApiDemo.java
java SealedApiDemo
~~~

Exact stdout:

~~~text
SUCCESS: created
ERROR 404: Not found
DEFERRED: retry after 30 seconds
~~~

The helper types are not declared `public`, so they can reside in the same file as the `public` class `SealedApiDemo`. When adapting the example into a real library, the package/module and access levels need to be designed to fit the API contract.

## 5. How Do Sealed Types Shape API Evolution?

Suppose the first version of a library publishes:

~~~java
public sealed interface ApiResult
        permits ApiSuccess, ApiFailure {
}
~~~

The contract states that every direct implementation belongs to the controlled list. API consumers can rely on the published set of variants when writing business logic and tests.

If a later version needs to add a deferred result, the library can expand the list explicitly:

~~~java
public sealed interface ApiResult
        permits ApiSuccess, ApiFailure, ApiDeferred {
}
~~~

The library then declares `ApiDeferred` as `non-sealed` if it wants to allow other types to continue implementing this branch. If the new branch also needs to be tightly controlled, a `sealed` interface or class with its own `permits` list can be used.

Changing the permitted list is an API contract change that needs to be reviewed upon release. Before publishing a new version, recompile dependent modules and verify the handling of all variants. The degree of impact depends on how clients use the API, the Java version, and how client code is compiled.

Sealed types strike a balance between stability and extensibility:

- **Closed set of variants:** suited for results, states, or data types that the library wants to control.
- **Intentionally open branch:** suited when an extension point is needed for other implementations.
- **Open interface:** suited when the primary goal is to allow external clients to implement many types on their own that the library cannot enumerate in advance.

Do not seal a public interface merely to use new syntax. Choose it when restricting direct subtypes is an intentional part of the API design.

## 6. Impact on switch and Exhaustive Branch Handling

A sealed hierarchy provides information about direct subtypes that the compiler can use to check exhaustiveness in language constructs that support it. This is especially useful with pattern matching for `switch` in modern Java.

It is important to distinguish the language milestones: pattern matching for `switch` was still a preview feature in Java 17 and only became an official feature in Java 21. Therefore, the example above running with `--release 17` uses `instanceof` instead of a pattern switch.

When a library adds a new variant, clients using an exhaustive switch expression may need to update their branches upon recompilation. Even if a client currently uses `if/else`, the logic may also need to be reviewed so that a new variant is not overlooked. Sealed types help the compiler detect certain missing-branch cases, but do not by themselves guarantee that all business logic handles them correctly.

With a `non-sealed` branch, special care is needed: more indirect subtypes may exist than are listed in the root sealed type. Handling code should treat that open abstraction as a group, rather than assuming there is only a single concrete implementation.

## 7. Choosing Between sealed, non-sealed, or an Open Interface

Use `sealed` when the set of direct variants is part of the domain model and the library needs to control which types are allowed to appear. Examples include parsing results, transaction states, or internal event types.

Use `non-sealed` for a branch when the library wants to control the conceptual category at the upper level, while still allowing applications to extend below it. For example, `ApiResult` can restrict the result categories, while `ApiDeferred` lets each application create its own deferred result types.

Use an open interface when clients need the ability to implement it directly without prior permission from the library. This is typically the right choice for an SPI or plugin API designed to be extended through independent modules.

Evaluate module boundaries, access levels, API lifecycle, and the ability to handle new variants. Those decisions matter more than simply adding the `sealed` keyword.

## 8. Common Mistakes When Applying to APIs

**Forgetting the modifier on a direct subtype.** A regular class extending a sealed class without declaring `final`, `sealed`, or `non-sealed` will not compile. Explicitly decide whether the branch should be closed or open.

**Including an indirect subtype in `permits`.** The clause only lists direct subtypes. A type deeper in the hierarchy must be connected through an intermediate branch.

**Using `sealed` for a plugin API that needs free extensibility.** Clients outside the module/package cannot arbitrarily implement a sealed interface directly. Consider an open interface or a public `non-sealed` branch.

**Assuming Java 17 already has official pattern switch.** Java 17 has official sealed types, but pattern matching for `switch` in this version is still a preview feature. Do not enable preview features when targeting standard Java 17 source code.

**Adding variants without checking clients.** When the `permits` list changes, review result-handling code, integration tests, and the compilation process of dependent modules.

**Using `non-sealed` while assuming the type tree is closed.** `non-sealed` intentionally opens that branch. Any logic relying on a fixed list of implementations must account for subtypes that may be added later.

**Confusing type restrictions with data validation.** Sealed types control inheritance/implementation relationships in the hierarchy. They do not replace input checks, authorization, validation, or business rules.

## 9. Checklist Before Publishing an API

- Determine whether the set of direct subtypes truly needs to be controlled.
- Explicitly declare the `permits` list, or let Java infer it when the permitted types reside in the same compilation unit.
- Choose `final`, `sealed`, or `non-sealed` for each direct subtype according to the extension policy.
- Verify the same-module/same-package rules.
- If you want to allow client extensions, provide an appropriate `non-sealed` branch or keep the interface open.
- When changing the `permits` list, check client code, handling branches, and compatibility tests before releasing.
- Compile examples and the library with the target Java version. For Java 17, use `javac --release 17` to verify stable syntax.
- Clearly document in the API documentation whether the set of variants is closed or has supported extension points.

Sealed classes and sealed interfaces in Java 17 provide a tool for publishing clear extension boundaries. They fit best when the policy on direct subtypes is an important part of the API contract and is intentionally maintained across library versions.
