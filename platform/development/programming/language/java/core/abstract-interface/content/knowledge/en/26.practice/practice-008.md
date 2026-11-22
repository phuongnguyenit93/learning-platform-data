# Modeling Results with Sealed Interfaces and Records

## Objective

When an operation can end in multiple ways, such as success, failure, or pending processing, we often need to represent each case explicitly in the data type. Combining `sealed interface` with `record` allows us to define a bounded set of variants and describe the data of each variant with concise syntax.

A `sealed interface` specifies which types are permitted to implement it directly. Each `record` represents a specific kind of result, holds data components, and provides a built-in constructor, accessors, `equals()`, `hashCode()`, and `toString()`. This combination is useful when you want readers and the compiler to understand the kinds of results an API can return.

## 1. Why Model Results as Variants?

Suppose an API searches for a resource. The result can be:

- Success: has data and a status code.
- Failure: has an error code and an explanatory message.
- Pending: has information about the operation currently in progress.

A common design is to return `Object`, use `null` for certain cases, or return a class containing multiple nullable fields. Those approaches easily create invalid states: a result that has both success data and error information, or no information at all to explain the result.

A closed type model represents each case as a separate type. In that case, the data needed for success lives in the success record, error data lives in the failure record, and a pending result has its own structure. Callers can handle each case by checking the concrete type instead of inferring from combinations of multiple nullable fields.

## 2. The Role of Sealed Interfaces and Records

A sealed interface declares the list of direct subtypes using `permits`:

```java
sealed interface ApiResult permits Success, Failure, Pending {
}
```

This list contains only direct subtypes. Each listed type must actually `implements ApiResult`. In a sealed hierarchy, direct subtypes must close or extend the hierarchy according to Java's rules: a subclass must be `final`, `sealed`, or `non-sealed`; a record is already implicitly `final`.

Records can implement a sealed interface:

```java
record Success(String value, int status) implements ApiResult {
}

record Failure(String code, String message) implements ApiResult {
}

record Pending(String operation) implements ApiResult {
}
```

Each record defines the data for one case. Java automatically generates accessors named after the components, for example `value()`, `status()`, or `message()`. A record also has value comparison and string representation methods based on its components.

A record cannot extend a custom application class because it already directly extends `java.lang.Record`; record declaration syntax has no `extends` clause for a custom superclass. However, a record can implement one or more interfaces, including a sealed interface. This is why the `sealed interface + record` model is suitable for data variants.

## 3. Complete Runnable Example on Java 17+

The following example models three results of an operation: success, failure, and pending. The constructors validate input data to prevent creating invalid results. The `describe` method handles each variant using pattern matching for `instanceof`, a feature officially supported since Java 16.

Save the contents to the file `ResultModelDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class ResultModelDemo {
    public static void main(String[] args) {
        List<ApiResult> results = List.of(
            new Success("OK", 200),
            new Failure("NOT_FOUND", "resource not found"),
            new Pending("import-catalog")
        );

        for (ApiResult result : results) {
            System.out.println(describe(result));
        }
    }

    private static String describe(ApiResult result) {
        if (result instanceof Success success) {
            return "Success: " + success.value()
                    + " (" + success.status() + ")";
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.code()
                    + " - " + failure.message();
        }
        if (result instanceof Pending pending) {
            return "Pending: " + pending.operation();
        }

        throw new IllegalStateException(
            "Unsupported result type: " + result.getClass().getName()
        );
    }
}

sealed interface ApiResult permits Success, Failure, Pending {
}

record Success(String value, int status) implements ApiResult {
    Success {
        Objects.requireNonNull(value, "value must not be null");
        if (value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }
        if (status < 200 || status > 299) {
            throw new IllegalArgumentException("success status must be 2xx");
        }
    }
}

record Failure(String code, String message) implements ApiResult {
    Failure {
        Objects.requireNonNull(code, "code must not be null");
        Objects.requireNonNull(message, "message must not be null");
        if (code.isBlank()) {
            throw new IllegalArgumentException("code must not be blank");
        }
        if (message.isBlank()) {
            throw new IllegalArgumentException("message must not be blank");
        }
    }
}

record Pending(String operation) implements ApiResult {
    Pending {
        Objects.requireNonNull(operation, "operation must not be null");
        if (operation.isBlank()) {
            throw new IllegalArgumentException("operation must not be blank");
        }
    }
}
```

Compile and run:

```text
javac --release 17 -encoding UTF-8 ResultModelDemo.java
java ResultModelDemo
```

Expected output:

```text
Success: OK (200)
Failure: NOT_FOUND - resource not found
Pending: import-catalog
```

The example shows that each variant carries exactly the data that belongs to it. `Success` validates the success data and status code; `Failure` requires an error code and a message; `Pending` requires an operation name. These checks preserve basic invariants as soon as the object is created. Because this is a `Success` variant for HTTP-based results, the status code is restricted to the `2xx` range; a `4xx` or `5xx` response should be represented by an error variant instead of creating a `Success` with a contradictory meaning.

## 4. How Callers Handle Variants

When receiving an `ApiResult`, a caller should identify the kind of result and then handle it according to that kind's data. In the example, `instanceof Success success` both checks the type and creates a reference variable with the concrete type to access the accessors. The following branches handle `Failure` and `Pending`.

Because `ApiResult` is sealed and its subtypes are known in advance, the list of variants is finite within the scope of that hierarchy. This makes reviewing logic easier: if a new result type is added, developers can locate existing handling points and decide how to add the corresponding branch.

However, the `if/instanceof` block does not automatically guarantee that every branch has been handled. The final branch throws `IllegalStateException` to indicate an unexpected case. When adding a new variant, you need to update the handling functions and related tests.

Java 21 and later support pattern matching for `switch` as a standard feature, which can be combined with a sealed hierarchy to write clearer branching logic. On Java 17, pattern matching for `switch` is still a preview feature, so this example uses `instanceof` to compile without enabling preview features.

## 5. Keeping the Model Valid and Extensible

### Avoiding Contradictory States

You should not combine all fields into a single record such as `Result(String value, String errorCode, String message, boolean pending)` if many field combinations can occur without making sense. A success record that also has error data, or a failure result without an error code, increases the number of states every caller must check.

Separate variants help constrain the data structures that can be created. A record's compact constructor allows validating input without rewriting component assignments. If input data violates invariants, you can consistently throw `IllegalArgumentException` or `NullPointerException`.

### Adding New Variants Deliberately

If the API needs to add a state such as `Cancelled`, add that type to `permits` and have it implement the sealed interface. Then, update the handling functions, documentation, and tests. Changing the set of variants can affect client code that assumes only the old cases exist, so compatibility must be considered when publishing a public library.

Types permitted to extend or implement must obey location constraints: in a named module, they must belong to the same module; in an unnamed module, they must be in the same package. Placing a subtype in the wrong module or package makes the hierarchy invalid.

### Understanding the Limitations of Records

Records are suitable for data with clearly defined components that do not need to inherit state from an application superclass. Record components are final, but immutability is shallow: if a component references a mutable object, that object can still be modified. In the example, the components are all `String`, which is immutable, so this issue does not arise.

There is no need to create JavaBean-style getters such as `getValue()`; a record's accessor uses the component name directly, such as `value()`. If the API requires different conventions or behavior, additional methods can be declared, but keep their meaning clear and avoid unnecessary duplication.

## 6. When Should You Use This Model?

| Scenario | Suitable Design |
|---|---|
| An operation has a few well-defined results | A sealed interface with records representing each result |
| Each result carries a different set of data | A separate record for each variant |
| Need to restrict the result types that application code is allowed to create | A sealed interface with an explicit `permits` list |
| Types need to share state from a custom superclass | Consider a sealed class with regular subclasses |
| Results need to be extended by external libraries | Consider an unsealed interface or a `non-sealed` branch, with a clear understanding that the scope of variants will expand |

Do not choose sealed solely because of newer syntax. Sealed is useful when restricting variants is part of the design. If third parties need to define new implementation types themselves, an open interface may be more suitable.

## Key Takeaways

- `sealed interface` restricts which types are permitted to implement it directly; `permits` lists the direct subtypes.
- `record` describes the data of a variant and provides accessors and value-based methods; a record is implicitly `final`.
- A record cannot extend a custom application class, but it can implement a sealed interface.
- Separating into distinct records helps avoid nullable field combinations and contradictory states.
- After adding a variant, update handling points and tests; sealed helps define the type scope but does not automatically guarantee that business logic is complete.
- The example uses Java 17 and `instanceof` pattern matching, without needing to enable preview features.
