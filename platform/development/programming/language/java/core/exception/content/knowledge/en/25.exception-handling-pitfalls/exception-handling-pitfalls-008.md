# Returning null or a default value after an error without a clear contract

## 1. The problem: a "normal" value can mask a failure

In Java, when a piece of code catches an exception and returns `null`, `false`, `0`, an empty string, an empty list, `Optional.empty()`, or a default object, the caller only sees the **return value** and does not necessarily know that execution failed.

For example:

~~~java
String loadUserName(String id) {
    try {
        return repository.findName(id);
    } catch (RuntimeException ignored) {
        return null;
    }
}
~~~

This is a **non-standalone illustrative fragment**; `repository` is not defined. If `findName` already returns `null` when the user does not exist, then the following two situations become indistinguishable:

1. The query succeeded, and the user genuinely does not exist.
2. The query failed to execute because the database lost connection, was misconfigured, or the code threw an exception.

A caller might write `if (name == null) return 404;`, causing an infrastructure error to be presented as "user does not exist". Consequences can include returning the wrong message, triggering duplicate record creation, caching a false negative result, or skipping an error that should be retried.

**The core mistake is not merely returning `null`.** The problem is that **the API does not clearly define when that value is valid, what it means, and whether an exception occurred**. A default value is only safe when the contract states the conditions for its use and the caller can distinguish or accept the consequences of the fallback.

Lesson objectives:
- Distinguish **success with data**, **success with no data**, **failure**, **cancellation/timeout**, and **intentional fallback**.
- Understand why `null`, `Optional.empty()`, `0`, `false`, `""`, and empty collections are not general-purpose error signals.
- Choose when to **propagate exceptions**, when to return a **typed result**, and when fallback matches the contract.
- Preserve `cause`, error codes, and observability instead of turning a serious incident into "success".
- Test failure paths with fault injection, including side effects that already occurred before the exception.

## 2. Classify outcomes before designing the return type

Any operation can fall into the following categories:

| Outcome | Example | Meaning to convey |
| --- | --- | --- |
| Success with result | Customer `A` found | `Found(customer)` |
| Success with no result | Valid ID, query completed and no record exists | `NotFound(id)` or `Optional.empty()` per contract |
| Expected business rejection | Order violates limit | `Rejected(reason)` or a defined business exception |
| Execution failure | Database timeout, file read error, bug in callback | Exception or `Failed(code, cause)` |
| Timed out | Caller did not receive a result before deadline | `TimeoutException`/`PENDING`/`UNKNOWN` depending on scope |
| Cancelled | Task was cancelled on request | `Cancelled` or `CancellationException` per API |
| Controlled fallback | Use stale cache when primary source fails, allowed by policy | `Fallback(value, source, age)` or equivalent metadata |

An API does not necessarily need seven classes for seven states. However, **it must answer what each value means**, and which states are distinguished from which.

For example, `Optional<User> findById(String id) throws IOException` is a relatively clear contract: if the query succeeds, it returns `Optional.of(user)` or `Optional.empty()`; if the data source cannot be read, it throws `IOException`. Conversely, returning `Optional.empty()` for both "not found" and "cannot connect to DB" renders `Optional` meaningless.

### 2.1. Absence of a value is different from not knowing the value

There is a huge difference:

- **Absent:** the system checked successfully and confirmed there is no record.
- **Unknown:** the system could not check due to an error, timeout, or unsynchronized data.

`null`/`Optional.empty()` is usually only appropriate for the first case when the contract specifies it. The second case requires an error/unknown state or a retry/reconciliation mechanism. Without distinguishing them, the caller can make wrong decisions even though no exception appears in the logs.

## 3. Why catching and returning `null` is especially hard to diagnose

~~~java
User getUser(String id) {
    try {
        return database.load(id);
    } catch (Exception e) {
        return null;
    }
}
~~~

This is a fragment; `User`/`database` are undefined. Broadly catching and returning `null` carries at least four risks:

1. **Swallowing the root cause:** `IOException`, `SQLException`, `IllegalStateException`, and other programming errors are all collapsed into a single `null` state.
2. **Creating secondary exceptions:** upstream code accesses `user.getName()` and gets a `NullPointerException` far from the original error; the stack trace only points to the `null` dereference, with the original cause lost.
3. **Fake success:** the method completes normally and automatic metrics may record success even though a dependency failed.
4. **Corrupting business workflows:** the caller treats `null` as "no data yet" and proceeds to create a new record, write to cache, or make an incorrect decision.

Changing it to `catch (IOException e) { return null; }` narrows the catch scope, but **still loses the I/O error state** if the contract does not state that `null` also represents an error. A comment like `// ignore` is not a safety guarantee.

### 3.1. When can `null` be valid?

`null` can be a legally defined value in some legacy APIs, binding frameworks, or data protocols. In such cases, the documentation must state clearly:
- Which conditions cause the function to return `null`?
- Does `null` mean valid data, not found, not yet loaded, or an error?
- If the operation actually fails, which exception or state does the caller receive?
- Could statements with side effects before returning `null` have already executed?
- Are there nullability annotations/tooling and tests verifying the contract?

A public API `@Nullable User find(String id)` may specify `null` = does not exist; thus database errors must go through another channel and must not also return `null`. Nullability annotations help express **a nullable value**, but by themselves do not explain the full business meaning of `null`.

## 4. `false`, `0`, `""`, and empty collections can also mask errors

`null` is just one of several ways to turn an exception into normal-looking data.

| Default value | Valid scenario | Problem if also used on error |
| --- | --- | --- |
| `false` | Condition checked and not satisfied | Cannot distinguish "not permitted" from "permission check service failed" |
| `0` | Total record count is 0, valid price is 0 | Billing/data-reading failure is interpreted as an actual value of 0 |
| `""` | Empty but valid input string | Loses the ability to distinguish data-loading errors |
| `List.of()` | Query succeeded, list has no elements | API reports "no data" when the database could not be queried |
| `Map.of()` | Valid configuration with no overrides | Config-reading error causes the application to skip important policies |
| `Optional.empty()` | Valid search found no value | Execution failure is disguised as absence |
| Default object | User intentionally chose default parameters | Data corruption/deserialization error is hidden |

Counterexample:

~~~java
int loadAccountBalance(String accountId) {
    try {
        return backend.balance(accountId);
    } catch (RuntimeException ignored) {
        return 0;
    }
}
~~~

This is an illustrative fragment; `backend` is undefined. Returning `0` after an infrastructure error can lead to wrongly rejecting transactions, sending "out of funds" notifications, or producing inaccurate financial reports. If the domain allows an account to have an exact balance of 0, this value is no longer a unique sentinel.

For booleans, `false` is sometimes chosen under a "deny by default" policy when permissions cannot be verified. That can be the **right fail-closed security decision**, but the contract should state that `false` includes unverified cases, or return separate `DENIED` and `UNAVAILABLE` states for diagnosability. Never treat fail-closed as an excuse to drop logs/metrics for authorization service incidents.

## 5. Complete Java 17 example: same null for two situations and how to fix it

The following program has three representation layers:

- `legacy` simulates an old API: returns `null` for both "not found" and I/O errors.
- `findOptional` returns `Optional.empty()` only when the query **actually completed** without finding data, while `IOException` is propagated.
- `lookup` returns a **sealed result type** consisting of `Found`, `Missing`, and `Failed`, clearly distinguishing outcomes.
- `lookupWithCache` illustrates an intentional fallback labeled separately as `Fallback`; the cache value here is simulated to verify classification, not a production cache.

Save as **`ExplicitFailureResultDemo.java`**:

~~~java
import java.io.IOException;
import java.util.Optional;

public class ExplicitFailureResultDemo {
    sealed interface LookupResult permits Found, Missing, Failed, Fallback {}

    record Found(String key, String value) implements LookupResult {}
    record Missing(String key) implements LookupResult {}
    record Failed(String key, FailureCode code, Throwable cause)
            implements LookupResult {}
    record Fallback(String key, String value, String source)
            implements LookupResult {}

    enum FailureCode { STORAGE_UNAVAILABLE }

    static String fetch(String key) throws IOException {
        return switch (key) {
            case "A" -> "Alice";
            case "B" -> null;
            case "DB_DOWN" -> throw new IOException("database unavailable");
            default -> null;
        };
    }

    static String legacy(String key) {
        try {
            return fetch(key);
        } catch (IOException ignored) {
            return null;
        }
    }

    static Optional<String> findOptional(String key) throws IOException {
        return Optional.ofNullable(fetch(key));
    }

    static LookupResult lookup(String key) {
        try {
            String value = fetch(key);
            return value == null ? new Missing(key) : new Found(key, value);
        } catch (IOException e) {
            return new Failed(key, FailureCode.STORAGE_UNAVAILABLE, e);
        }
    }

    static LookupResult lookupWithCache(String key) {
        LookupResult result = lookup(key);
        if (result instanceof Failed && key.equals("DB_DOWN")) {
            return new Fallback(key, "stale Alice", "cache");
        }
        return result;
    }

    static String describe(LookupResult result) {
        if (result instanceof Found found) {
            return "FOUND " + found.key() + "=" + found.value();
        }
        if (result instanceof Missing missing) {
            return "MISSING " + missing.key();
        }
        if (result instanceof Failed failed) {
            return "FAILED " + failed.key() + "=" + failed.code()
                    + " (" + failed.cause().getMessage() + ")";
        }
        if (result instanceof Fallback fallback) {
            return "FALLBACK " + fallback.key() + "=" + fallback.value()
                    + " from " + fallback.source();
        }
        throw new IllegalStateException("Unknown result");
    }

    public static void main(String[] args) {
        System.out.println("legacy missing is null: " + (legacy("B") == null));
        System.out.println("legacy outage is null: " + (legacy("DB_DOWN") == null));
        System.out.println(describe(lookup("A")));
        System.out.println(describe(lookup("B")));
        System.out.println(describe(lookup("DB_DOWN")));
        System.out.println(describe(lookupWithCache("DB_DOWN")));
        try {
            System.out.println("Optional missing empty: " + findOptional("B").isEmpty());
            findOptional("DB_DOWN");
        } catch (IOException e) {
            System.out.println("Optional outage: " + e.getMessage());
        }
    }
}
~~~

Using JDK 17 or later, from the directory containing the file:

~~~bash
javac --release 17 ExplicitFailureResultDemo.java
java ExplicitFailureResultDemo
~~~

**Compiled/run-verified** stdout:

~~~text
legacy missing is null: true
legacy outage is null: true
FOUND A=Alice
MISSING B
FAILED DB_DOWN=STORAGE_UNAVAILABLE (database unavailable)
FALLBACK DB_DOWN=stale Alice from cache
Optional missing empty: true
Optional outage: database unavailable
~~~

### 5.1. Output explanation

- The first two lines are both `true`: the caller receives the same `null` in the legacy API and cannot distinguish absence from a lost database connection.
- `FOUND A=Alice`: data exists and the operation succeeded.
- `MISSING B`: the query was executed validly, and there is no record.
- `FAILED DB_DOWN=STORAGE_UNAVAILABLE (...)`: the I/O error is captured in a typed `Failed` result, with a stable code and `cause`.
- `FALLBACK ... from cache`: the fallback branch is a **labeled** result. The caller knows it is not fresh data from the primary source.
- `Optional missing empty: true`: `Optional.empty()` only describes the absence of a value, not an error code.
- `Optional outage: database unavailable`: the source error still travels through `IOException`; the caller can handle/record it properly.

The example simplifies this with the string `stale Alice` when key `DB_DOWN` fails. A real application must check the cache key, version, creation time, access permissions, and staleness limits before returning a fallback. **Do not serve an arbitrary cached entry to the wrong customer** just to provide a default value.

### 5.2. Why use `sealed interface` and `record`?

Java 17 supports `sealed interface` and `record` as stable features, allowing you to model the allowed result cases:
- `Found` holds the returned data.
- `Missing` holds the absent key.
- `Failed` holds the error code and internal cause.
- `Fallback` holds the value along with the backup source.

Using `instanceof` pattern matching in `describe` clearly separates branches without needing a `null` sentinel. If another result type is added, the handling logic must be updated accordingly. In production, you can choose a sealed hierarchy with richer records, or exceptions + `Optional` if the requirements are genuinely simple.

**Security note:** `Throwable cause` in a record is only suitable for internal storage/logging. Do not serialize stack traces, connection details, or sensitive data directly into an HTTP response or public message. Only expose error codes and safe information per the API contract.

## 6. `Optional` is not a general-purpose error container

`Optional<T>` in Java is designed to represent **the presence or absence of a value**. It does not carry a reason or cause.

Correct pattern if `Optional.empty()` = "not found":

~~~java
Optional<String> readName(String id) throws IOException {
    String name = readFromStorage(id);
    return Optional.ofNullable(name);
}
~~~

This is a fragment; `readFromStorage` is undeclared. If storage throws `IOException`, the exception propagates out instead of being silently converted into `Optional.empty()`. For the caller, this enables:
- `Optional.of(value)`: data is present.
- `Optional.empty()`: query completed, no data.
- `IOException`: query could not be completed.

Incorrect pattern:

~~~java
Optional<String> readName(String id) {
    try {
        return Optional.ofNullable(readFromStorage(id));
    } catch (IOException ignored) {
        return Optional.empty();
    }
}
~~~

Here `Optional.empty()` both indicates absence and hides I/O errors. If the original API contract did not state this, it is a dangerous **semantic change**.

### 6.1. `orElse` and `orElseGet` do not recover from lower-layer errors

For example:

~~~java
String label = optionalName.orElse("Anonymous");
~~~

This is a fragment with an existing `optionalName`. `"Anonymous"` is used when the `Optional` is empty, not to "catch all exceptions" from producing `optionalName`. If the author converted an `IOException` into an empty `Optional` at a lower layer, `orElse` will silently fabricate a fake "valid name".

In addition, `orElse(expression)` evaluates its argument according to Java method invocation rules, whereas `orElseGet(supplier)` only invokes the supplier when the value is missing. This difference matters if the fallback is expensive or has side effects; however, **using a lazy supplier does not fix an ambiguous error contract**.

### 6.2. `Optional.ofNullable` only inspects null, not the source of null

`Optional.ofNullable(value)` creates an empty `Optional` when `value == null`. It receives no metadata stating whether `null` came from "does not exist", "deserialization error", "dependency unavailable", or "a developer caught an exception". If the system needs to distinguish causes, that information must be designed **before the conversion to `Optional`**.

## 7. `Map.get` and APIs with their own default values

`Map.get(key)` can return `null` in two cases:
- There is no mapping for the key.
- There is a mapping, and the stored value is `null` (for `Map` implementations that allow `null`).

With a `Map` that allows `null`, to distinguish whether a key exists, use `containsKey(key)`:

~~~java
Map<String, String> settings = new HashMap<>();
settings.put("theme", null);
System.out.println(settings.containsKey("theme")); // true
System.out.println(settings.get("theme") == null); // true
~~~

This is a fragment; `java.util.Map` and `java.util.HashMap` must be imported. This is an **ambiguity inherent to Map's data contract**, not an exception. When a cache or repository adapter returns `null` after an exception, the ambiguity grows: not only "is the key missing or is the value null", but also "did the query succeed at all".

`Map.getOrDefault(key, defaultValue)` returns the fallback when there is no mapping; if the key exists and is mapped to `null`, the behavior can preserve `null`. Do not use `getOrDefault` as a "recover if the query fails" mechanism; it only handles absence per `Map` semantics.

**Rule:** understand the existing default sentinel of a collection/API before repurposing it as a new error channel.

## 8. When is an exception the right contract?

Not every error needs to be turned into a `Failed` record. For many Java APIs, a method can:
- return a valid value or domain-level absence;
- **throw an exception** if it cannot complete the operation.

For example:

~~~java
Optional<Invoice> findInvoice(String id) throws IOException {
    return invoiceStore.find(id);
}
~~~

This is a fragment with assumed `Invoice` and `invoiceStore`. If the read operation fails, propagating `IOException` keeps the error channel separate. If an upper layer wants to translate it into HTTP 503 or a `StorageUnavailable` result, do that at the boundary capable of making policy decisions.

If an exception is an expected business outcome (e.g., an invalid ID), you can use a checked exception, an unchecked domain exception, or a result type depending on system conventions. What matters is that **callers can recognize and test those outcomes**.

### 8.1. Rethrow and wrap while preserving `cause`

When unable to handle it:

~~~java
try {
    return remoteRead();
} catch (IOException e) {
    throw e;
}
~~~

This fragment assumes the method declares `throws IOException`. If you add no handling or context, you can omit the try-catch and let the exception propagate naturally.

If you want to wrap at the service layer:

~~~java
try {
    return remoteRead();
} catch (IOException e) {
    throw new IllegalStateException("Unable to read report", e);
}
~~~

This fragment leaves `remoteRead` undefined. Using a constructor that takes `cause` helps callers/logging see the root cause. Avoid:

~~~java
catch (IOException e) {
    return null;
}
~~~

when `null` is not a defined error branch. Also avoid `throw new IllegalStateException("failed")` without a `cause`, as it loses the trace back to the original I/O error.

### 8.2. Do not catch broadly to turn every error into a default

~~~java
try {
    return execute();
} catch (Exception e) {
    return defaultResult();
}
~~~

This is a fragment. `Exception` can include both expected `IOException`s and `NullPointerException`/`IllegalStateException` caused by bugs. When a dependency introduces a new error, a broad catch also turns it into a fallback, hiding programming mistakes.

`catch (Throwable)` even catches JVM `Error`s, which are rarely appropriate to turn into a success value. At a very specific boundary you may catch broadly for monitoring and controlled shutdown, but you must still **preserve the failure signal** rather than returning success by default.

## 9. Designing fallbacks properly: value, source, and reliability

A fallback is a **business decision**, not a catch-block habit. For instance, a dashboard reading statistics might allow a 5-minute-old cache when the upstream source is temporarily unavailable. However, the API must specify:
- Which error types permit a fallback?
- Is there a valid cached value for the **exact key/tenant**?
- How old can the cache be at most? Are there cases where stale data must never be used (prices, inventory, permissions, transactions)?
- Does the client need to know the data is **degraded/stale**?
- Are there metrics/logs so operations knows the primary source failed?
- When the fallback also fails, what outcome does the caller see?
- Were any side effects performed before falling back?

Therefore, a type like:

~~~java
record CachedValue<T>(
        T value,
        String source,
        java.time.Instant fetchedAt,
        boolean stale) {}
~~~

is a **Java 17 fragment** that can carry metadata. With an API returning `CachedValue<T>`, the caller does not have to guess at a fallback from an empty string or `null`.

### 9.1. Configuration example: "missing" vs. "invalid"

A configuration setting like `APP_PORT` can be defined as:
- Environment variable **absent** → use default value `8080`.
- Present with `"abc"` → invalid configuration; fail startup.
- Present with `"-1"` → out-of-range value; report an error.
- Present with `"0"` → may carry special meaning (e.g., asking the server to pick an ephemeral port) if the contract allows; do not silently replace it with `8080`.

Anti-pattern:

~~~java
try {
    return Integer.parseInt(rawPort);
} catch (NumberFormatException e) {
    return 8080;
}
~~~

This is a fragment with an assumed `rawPort`. It treats an **invalid configuration value** as "unconfigured", causing the deployment to silently run on the wrong port. You can choose a default when *the variable genuinely does not exist*, then validate the present value per the contract.

### 9.2. Fail-open and fail-closed must be explicit

For security decisions, an API returning `false` after an error sometimes implements a **fail-closed** policy (denying when unable to verify). That may be the right decision. However, if the caller treats `false` as "the user definitely lacks permission" instead of "unable to verify permission", reporting and operations will be wrong.

You can separate:
- `ALLOWED`;
- `DENIED`;
- `UNAVAILABLE`/`INDETERMINATE`.

Then the API layer applies the fail-closed policy to `UNAVAILABLE` while still recording the dependency failure. Never turn a permission-check error into `true` just so "the service stays uninterrupted".

## 10. `CompletableFuture.exceptionally` can turn errors into "fake success"

A common async snippet:

~~~java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> loadRemote())
                .exceptionally(error -> "");
~~~

This is a **fragment**; `loadRemote()` is undeclared. If the supplier throws an exception, the new stage completes **normally with an empty string**. A downstream `whenComplete((value, error) -> ...)` will see `error == null`; success metrics there may increment even though the source failed.

When read data can legitimately be empty, `""` hides the entire cause. A clearer design is:
- Let exceptional completion propagate to the caller and handle the cause at the appropriate boundary; or
- Use `handle` to map both success and failure into a typed `Outcome`; or
- Use `exceptionally` with a **contract-allowed** fallback, returning metadata via the stage's data type.

### 10.1. Differences among `handle`, `exceptionally`, and `whenComplete`

| API | Primary effect | Pitfall to avoid |
| --- | --- | --- |
| `exceptionally(fn)` | Produces a new value when the stage fails | Unlabeled fallback turns an error into fake success |
| `handle((value,error) -> ...)` | Maps success/failure into a new result | Returning a default object on the error branch without a status code remains ambiguous |
| `whenComplete((value,error) -> ...)` | Observes completion, usually without changing the result | It does not "handle away" the exception; an observer throwing can fail the new stage |
| `thenApply(fn)` | Transforms the value when upstream succeeds | Not invoked on the upstream failure branch |
| `get()` / `join()` | Observes the result and exceptional completion | If the task swallowed the error earlier, the cause cannot be recovered from the Future alone |

Typed outcome example (fragment, assuming `Outcome`/`Success`/`Failure` are defined):

~~~java
CompletableFuture<Outcome> observed = source.handle((value, error) ->
        error == null
                ? new Success(value)
                : new Failure("REMOTE_ERROR", error));
~~~

If a stage succeeds with `null`, `error == null` still indicates normal completion. Do not use `value != null` to infer success. For errors wrapped in `CompletionException`, preserve the cause chain or unwrap carefully; do not assume `error.getCause()` is always non-null.

### 10.2. `Future` and executors suffer from the same issue

~~~java
Future<String> task = executor.submit(() -> {
    try {
        return loadRemote();
    } catch (IOException e) {
        return null;
    }
});
~~~

This is a fragment with assumed `executor` and `loadRemote`. Because the `Callable` caught the exception and returned `null` normally, `task.get()` can also return `null`, **without throwing `ExecutionException`**. The executor cannot reconstruct an error that the task already swallowed.

Do not equate "Future completed normally" with business success; if type `T` allows `Failure`, the caller must inspect the business status inside `T`.

## 11. Timeout and cancellation: not a normal empty value

If `future.get(timeout, unit)` throws `TimeoutException`, it only tells the caller that **no result was received within the wait window**; the task may still be running and producing side effects. Returning `null`/`false`/`List.of()` for a timeout without stating its meaning easily misleads the caller into thinking "no data".

Incorrect example:

~~~java
try {
    return future.get(1, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    return null;
}
~~~

This is a fragment needing imports/other checked exceptions and a method with an appropriate return type. Merely "not getting a timely result" does not prove the request failed, was cancelled, or never happened.

Depending on the system:
- You can return `PENDING(jobId)` and allow polling/lookup for the result.
- You can return `UNKNOWN(operationId)` if a remote side effect cannot yet be confirmed.
- You can throw/propagate the timeout via the exception contract.
- You can cancel a caller-owned task if the task supports cancellation and business rules allow it.

Also, do not swallow `InterruptedException` on a waiting thread and return a "success" default value; typically you must propagate it or restore the interrupt status and stop processing. `CancellationException` must be classified per contract rather than turning all cancellations into valid empty data.

## 12. HTTP and JSON: null/empty can break protocol semantics

When an API server catches a storage error and returns a response body with `"user": null` and HTTP 200, clients struggle to distinguish:
- The user genuinely does not exist.
- The user exists, but the data is intentionally empty.
- The backend failed to read the data.
- The request timed out or the token lacked permissions.

A clearer API contract might choose:
- HTTP **200** for data found / operation succeeded.
- HTTP **404** for a resource that does not exist **after a valid check**.
- HTTP **503** when the backend is temporarily unavailable.
- HTTP **500** for unexpected internal errors.
- HTTP **202** and a job ID for accepted work that is not yet complete.

These status codes are typical choices that should match the API's semantics, not rigid rules for every case. For a list-search endpoint, an empty list can be a **valid 200**; a database error must not be disguised as an empty list just to always return HTTP 200.

### 12.1. JSON `null` can carry multiple meanings

In JSON, you must distinguish:
- Field **absent**.
- Field present with value `null`.
- Field with empty string `""`.
- Field with array `[]` or object `{}`.
- Field with a valid but default value.

Do not assume the serializer maps all of these under the same rule; that depends on the DTO, serialization library, and configuration. In patch/update APIs, `null` may mean **delete the value**, whereas an absent field means **no change**. If an adapter swallows an error and builds a DTO with `null`, you can accidentally perform an unrequested deletion.

An error response can include a stable code, correlation ID, and safe message; do not expose stack traces, JDBC URLs, tokens, or user data on the public side.

## 13. Database: "no record" is different from a query execution error

With JDBC:
- `ResultSet.next() == false` after a validly executed statement can indicate **no more result rows**.
- `SQLException` during prepare/query/result reading signals incomplete execution per contract.
- Connection timeouts, transaction timeouts, and commit errors can have distinct semantics, sometimes leaving execution state **uncertain**.

Anti-pattern:

~~~java
try {
    return queryCustomer(id);
} catch (SQLException ignored) {
    return null;
}
~~~

This is a fragment; `queryCustomer` is assumed. If `null` means "customer does not exist", the caller might insert a new row thinking the ID does not exist yet, even though the DB is temporarily failing.

For transactions with side effects, receiving an error after commit does not necessarily prove the transaction rolled back. Do not arbitrarily return an empty list, `false`, or `UNKNOWN`; choose the right state and reconciliation mechanism when needed.

### 13.1. Negative caching prolongs errors

A cache may store **"not found"** results to reduce repeated queries. But if a storage error is converted into `Optional.empty()`, the cache may store a false absence with a TTL of several minutes; even after the DB recovers, the application keeps returning "does not exist".

Therefore, define:
- **Positive cache** for `Found`.
- **Negative cache** only for confirmed `NotFound`, with an appropriate TTL.
- **Never cache as `NotFound`** any `Failed` or `Unknown` results.
- If caching fallback after an error, attach source/degraded status and a separate TTL.

This pattern shows that the harm of an ambiguous default does not stop at a single response; it can leak into cache state and affect subsequent requests.

## 14. Parse/validate: missing input vs. invalid data

Suppose we read a worker-count configuration:

~~~java
int parseWorkers(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException e) {
        return 1;
    }
}
~~~

This is a syntactically complete fragment without an enclosing class. If the contract is "default to 1 when unconfigured", turning `"xyz"` into `1` hides a configuration error. A better approach:
1. Check if the config variable **does not exist** → use `1`.
2. Value is present → parse; if not a number, throw a contextual configuration exception.
3. Check bounds (e.g., 1 to 64).
4. Fail startup or return a clear validation result.

For user forms, an empty string may be valid input in some fields, but it cannot be used for an unreadable JSON body or an encoding error if the contract distinguishes them.

`Integer.parseInt` throws `NumberFormatException`; it does not return `0` when parsing fails. Do not add a catch block to turn it into `0` unless the spec explicitly defines "parse fail = 0" and callers understand that policy.

## 15. Structured error codes: designing a sufficient contract

A hierarchy like:

~~~java
sealed interface SaveOutcome
        permits Saved, Rejected, SaveFailed {}

record Saved(String id) implements SaveOutcome {}
record Rejected(String businessCode) implements SaveOutcome {}
record SaveFailed(String technicalCode, Throwable cause)
        implements SaveOutcome {}
~~~

This is a **Java 17 fragment**, not a standalone runnable file. It clarifies that saving successfully differs from a business rejection and from a save operation failure.

In a public API, callers handle the result:
- `Saved` → confirm success.
- `Rejected` → display business reason.
- `SaveFailed` → error code, retry policy, incident recording.

If typed results are the module's standard, do not mix returning `null` in one API and `SaveFailed` in a comparable API without documenting it. An error code enum should be **stable**, not just `Throwable.getMessage()` strings that can change across drivers, locales, and code versions.

### 15.1. Propagate exception or return Result?

| Which approach? | When is it appropriate? | Responsibility |
| --- | --- | --- |
| `T` + `throws IOException` | Exceptional execution failure the caller needs to know | Preserve cause/stack; do not swallow |
| `Optional<T>` + exception | Only presence/missing are normal data branches | Only empty when absence is confirmed |
| `Result<T, E>` | Multiple expected states and caller needs to classify them | Return all states faithfully, do not swap codes |
| `Fallback<T>` | Policy allows using a substitute value | Expose source, freshness, limits |
| `null` with explicit contract | Legacy/framework API requires `null` with a single meaning | Document and test clearly; other errors use a separate channel |
| `boolean`/primitive default | Result is truly binary / default value is meaningful | Do not use it to hide other errors in the same domain |

You do not need to build an oversized Result framework for a simple method. The principle to preserve is that **an important outcome must be recognizable at the decision-making layer**.

## 16. Backward compatibility: fixing a legacy API without breaking callers

If a public API `User getUser(id)` has historically returned `null`, changing it immediately to `Result<User>` can break existing callers. A safer migration path:
1. Verify the current meaning of `null` via tests/official contracts, not by guessing from a few callers.
2. Create a clearly named new API, e.g., `findUser(id)` returning `Optional<User>` and propagating exceptions, or `lookupUser(id)` returning a typed result.
3. Write an adapter between new and old when needed, without losing critical error information in an API advertised as safe.
4. Mark/document deprecation if there is a migration timeline.
5. Update callers at HTTP, batch, async, and UI boundaries to handle all branches.
6. Add metrics to track remaining calls to the old API before removing it.

Caution: an old adapter forced to return `null` may not be able to express the new branches. If the signature cannot change, you may need to propagate an appropriately typed exception instead of silently returning `null`. The practical choice depends on compatibility and existing error-handling rules.

### 16.1. Nullability annotations are not enough

Annotations like `@Nullable`, `@NonNull`, or JSpecify/IDE metadata help static analysis detect possible `null`s, but:
- They do not explain **why** `null` appears.
- They do not guarantee the caller can distinguish valid `null` from a swallowed error.
- Not all annotations are automatically checked at runtime.
- They do not replace exception/result documentation.

If the contract is "`null` = not found" and "backend unavailable = exception", document both in Javadoc and tests. Do not just add an annotation to an already ambiguous API and declare the issue solved.

## 17. Capture full exceptions and preserve causes when reporting errors

Suppose the code is:

~~~java
try {
    return repository.load(id);
} catch (IOException e) {
    return fallback;
}
~~~

This is a fragment. If `fallback` is stale data that is permitted, you still need to:
- record a primary-source failure metric;
- distinguish degraded results from primary results;
- keep the exception/cause in internal logs for investigation;
- mark fallback usage on traces when possible;
- define which errors are allowed to recover via fallback.

Do not log the full stack trace at **every layer** and then rethrow, causing duplicates. Choose a boundary that owns reporting, and pass `cause` through wrappers/results so no information is lost; on external channels, emit only safe messages.

Proper wrapping pattern:

~~~java
try {
    return repository.load(id);
} catch (IOException e) {
    throw new ServiceUnavailableException("User store unavailable", e);
}
~~~

This is a fragment; `ServiceUnavailableException` can be a custom `RuntimeException` or checked exception and must be defined in a real project. The constructor taking `cause` lets the API layer map to an appropriate error code while logs retain the original stack trace and correlation ID.

### 17.1. Do not create secondary errors instead of the root cause

If you catch an error and return `null`, the caller may throw `NullPointerException` at a distant location. The final log only shows the NPE without `IOException`. This is why you should preserve the cause as soon as the error occurs, rather than waiting for another operation to fail.

If converting the error into `Result.Failed`, you can keep the `Throwable` **internally** or an error object with appropriate tracing details. Do not turn message text into a parsing contract for callers.

## 18. Default results and retry correctness

An I/O error converted into a default result prevents the caller from triggering policy-based retries. For example:
- Search API returns `List.of()` → caller thinks there really are no orders to process.
- Job scheduler receives `true` → marks the job DONE and does not retry.
- ETL receives `0` → logs "0 records", skipping an entire batch.
- Permission service returns `false` → everyone is denied, with no infrastructure incident reported.
- Inventory service returns `0` → system closes sales even though stock may still exist.

Conversely, if a callback retries **after a timeout with unknown state**, re-running can duplicate side effects. Thus you should not automatically turn every error into `Retryable` either.

A complete policy typically needs categories like:
- `RETRYABLE_TRANSIENT` when there is evidence the operation is safe to retry.
- `PERMANENT_VALIDATION` when input needs correction.
- `UNKNOWN_OUTCOME` when the request may have completed remotely.
- `CANCELLED` when there was a valid cancellation request.
- `SUCCESS`/`NOT_FOUND` per contract.

For operations with side effects, you need an **operation ID/idempotency key enforced properly by the server** and a status lookup/reconciliation process. An HTTP timeout does not prove the server did not commit; returning `null` or `false` can hide that uncertainty.

## 19. Transactions and partial state

Example workflow:
1. Write order to database.
2. Send payment command to remote service.
3. Write audit event.

If an error occurs in step 2 or 3, catching and returning `Order.default()` can falsely claim the order was not created even though the DB already committed. Even when throwing the right exception, existing side effects **do not roll back automatically**.

Design the boundaries properly:
- Inside an uncommitted JDBC transaction, roll back on appropriate errors and know the connection state.
- For file publishing, use staging/temp + atomic move when supported, and clean up owned temp files.
- For HTTP/payment/email, use idempotency, outbox/saga/compensation, or reconciliation depending on system characteristics.
- If the outcome is undetermined, return `UNKNOWN`/`PENDING` instead of a default value implying certainty.

Do not hide exceptions out of fear that callers will see "failed" and retry incorrectly. The right approach is to **convey a state that accurately describes the uncertainty** and design safe retries.

## 20. Batch and aggregate: empty does not mean every task succeeded

An empty `List<Result>` can mean:
- The input list was empty.
- Every task completed with no data.
- The aggregator failed and discarded results.
- An exception stopped the loop before adding elements.

If the code is:

~~~java
List<Item> items = new ArrayList<>();
for (String id : ids) {
    try {
        items.add(loadItem(id));
    } catch (IOException ignored) {
    }
}
return items;
~~~

This is a fragment assuming `Item`, `ids`, and `loadItem` are declared/imported. The caller receives a list that may be missing elements without knowing which IDs failed. In reporting/reconciliation workflows, this is incomplete data presented as a final result.

Clearer alternatives:
- Fail fast and propagate the exception if the entire batch must succeed.
- Return `BatchResult(successes, failures)` containing the list of failed IDs and their causes/error codes.
- Return per-item results `Found/Missing/Failed` in input order.
- If ignoring partial errors is intentional, explicitly record `partial=true` and count the failed tasks.

When handling multiple `Future`s or `CompletableFuture.allOf`, do not just wait for completion and return `List.of()` when one future fails. Task failures must be observed/aggregated per contract. `isDone()` includes failed or cancelled completions; it is not a business success flag.

## 21. Designing monitoring metrics for failures and fallbacks

If all exceptions are converted into "normal" results, monitoring based on HTTP 5xx counts, exception counters, or `Future` exceptional completions will miss many incidents.

Metrics should distinguish:

| Metric/state | Meaning |
| --- | --- |
| `primary_success` | Primary source returned a valid result |
| `not_found` | Query completed, no data |
| `technical_failure` | Failure at primary source, unrecovered |
| `fallback_used` | Primary source failed, policy used fallback |
| `fallback_failed` | Fallback also failed to produce a result |
| `unknown_outcome` | Final outcome cannot be confirmed (timeout after side effect) |
| `cancelled` | Work was cancelled per contract |
| `partial_result` | Batch only has partial results, with unhandled/reported errors remaining |

Do not use unique request IDs as high-cardinality metric labels; store them in logs/traces instead. Do not log personal data, tokens, or stack traces into public responses. With fallbacks, both final success metrics and primary failure metrics **may increment** depending on purpose: one measures primary source quality, the other measures user-experience resilience.

### 21.1. Logging and catching do not have to be at the same layer

Not every `catch` needs to log at ERROR level. If a lower layer catches to wrap and rethrow an exception, you can let the boundary layer log once. If a fallback branch recovers, you can record a degraded metric/trace instead of printing the same stack trace in multiple places.

What is mandatory is that **the failure signal or recovery status does not vanish**, not the number of log lines.

## 22. Testing: fault injection and proving states are not conflated

Testing only the happy path is insufficient. A test matrix should include:

| Data/fault injection point | Expected correct outcome |
| --- | --- |
| Record exists | `Found(value)` |
| Query succeeds, not found | `Missing`/`Optional.empty()` |
| Database throws `IOException` | `Failed(STORAGE_UNAVAILABLE)` or exception |
| Configuration/parsing error | Report invalid config; do not default if a value was provided |
| Primary fails, valid cache exists | `Fallback(value, provenance)` if policy permits |
| Primary fails, no cache | `Failed`, never `Found("")` |
| Stale cache / wrong tenant | Do not return fallback as valid data |
| Async task throws exception | Future/stage preserves failure or explicit typed result |
| Task catches error and returns `null` | Test detects contract violation |
| Caller times out before worker finishes | `UNKNOWN`/timeout per policy, never silent `NotFound` |
| Batch has partial failure | Failures are preserved in report, no lost IDs |
| API has side effect then fails | Never definitively report "nothing happened" if committed |

### 22.1. JUnit 5 example for typed results

The following is a **fragment** for a project that already has JUnit Jupiter and the `ExplicitFailureResultDemo` class from the runnable example. Static imports from `org.junit.jupiter.api.Assertions` are required:

~~~java
var found = ExplicitFailureResultDemo.lookup("A");
assertInstanceOf(ExplicitFailureResultDemo.Found.class, found);

var missing = ExplicitFailureResultDemo.lookup("B");
assertInstanceOf(ExplicitFailureResultDemo.Missing.class, missing);

var failed = ExplicitFailureResultDemo.lookup("DB_DOWN");
var error = assertInstanceOf(ExplicitFailureResultDemo.Failed.class, failed);
assertEquals(ExplicitFailureResultDemo.FailureCode.STORAGE_UNAVAILABLE,
        error.code());
assertInstanceOf(IOException.class, error.cause());
~~~

This test proves the three branches are not conflated. For an API using `Optional` plus `throws IOException`, tests must verify empty only when the query completes normally and that storage errors propagate the exception.

### 22.2. Testing contracts with mocks/fakes

If a real repository is hard to inject faults into, use a fake dependency that can:
- Return a record.
- Return no record.
- Throw the exact infrastructure exception.
- Throw an unexpected programming exception.
- Wait past the deadline.
- Perform a side effect and then throw.

Verify **output + cause + post-error state + metric/job state**, not just "the method did not crash". For concurrent code, use latches/future timeouts for coordinated tests; do not rely on `Thread.sleep` to guess scheduling.

### 22.3. Useful property/invariant tests

Some invariants you can check:
- If the repository throws an exception and no fallback is allowed, the API **never** returns `Found`/`NotFound`.
- If `Fallback` is returned, metadata must state the source and satisfy data-age limits.
- If `Missing` is returned, no source read error occurred during that operation.
- If the caller receives `SUCCESS`, every required step of the contract completed or has a durable commitment mechanism.
- If the result is `UNKNOWN`, the code does not automatically retry a non-idempotent command with a new operation ID.
- Never use the same sentinel for two outcomes that require different handling.

These properties can be applied to contract tests in CI; do not hardcode stack traces or source line numbers into functional unit tests.

## 23. Anti-patterns to spot in code reviews

### 23.1. `catch (Exception e) { return null; }`

Problem: loses error type and cause, mixes multiple outcomes. Fix: catch only the exact type you can handle; if unrecoverable, propagate the exception or a typed result.

### 23.2. `catch (RuntimeException e) { return 0; }`

Problem: programming bugs are also turned into `0`. For critical numeric data, inaccuracies can leak into billing/reporting. Fix: validate inputs and handle errors at the right boundary; do not use `0` as "error" if `0` is valid.

### 23.3. `exceptionally(error -> List.of())`

Problem: `CompletableFuture` completes normally with an empty list when the source fails. Downstream observers may record success. Fix: preserve exceptional completion or map to a coded `Failure`.

### 23.4. `Optional.empty()` from every I/O error

Problem: loses the distinction between absence and unavailability, risking wrong negative caching. Fix: return empty only when absence is confirmed.

### 23.5. `return false` from a save operation on remote timeout

Problem: `false` can imply definite failure when the server actually committed. Fix: model `UNKNOWN`/operation ID and reconciliation.

### 23.6. `return defaultConfig` after a parse error

Problem: invalid configuration is silently accepted. Fix: use defaults only for absence if defined by the contract; invalid configuration data must be reported clearly.

### 23.7. Log `e.getMessage()` then return `null`

Problem: logs may lack stack/cause; the caller still sees a fake result. Fix: convey an explicit error state and log the throwable at the appropriate point when needed.

### 23.8. `return null` inside `finally`

Incorrect fragment:

~~~java
String compute() {
    try {
        throw new IllegalStateException("calculation failed");
    } finally {
        return null;
    }
}
~~~

This is **method-level complete Java code**, needing a class wrapper to compile. A `return` in `finally` can **mask exceptions or results** from the `try` block. Avoid placing `return` in `finally` just to provide a default; use `finally` for safe cleanup, not for unexpectedly altering the primary result control flow.

### 23.9. Using a default result without disclosing degraded mode

Problem: the caller does not know whether the value came from cache or the primary source. Fix: return provenance/freshness or an explicit status fitting the API.

### 23.10. Swallowing `InterruptedException` and returning success/default

Problem: loses shutdown/cancellation signals, allowing tasks to continue in an invalid state. Fix: propagate or restore the interrupt flag and terminate per contract; do not treat this as a negligible business error.

## 24. Quick decision guide

~~~text
Thinking of catching an exception and returning a default value?
|
+-- Is that value a valid result of the operation?
|      +-- Yes -> risk of mixing success/absence/failure
|      +-- No -> contract must specify the sentinel and ensure callers check it
|
+-- Can the exception genuinely be recovered from?
|      +-- No -> preserve exception/cause or return an explicit Failure
|      +-- Yes -> perform bounded recovery and verify postconditions
|
+-- Is fallback permitted by business rules?
|      +-- Yes -> return value + appropriate provenance/status
|      +-- No -> do not fabricate fake success
|
+-- Is there a side effect or remote timeout?
|      +-- Yes -> may need Partial/Pending/Unknown + operation ID
|      +-- No -> failure result per API
|
+-- Who needs to know the final outcome?
       +-- Caller / coordinator / metrics / job store
       +-- ensure failure information is not truncated at catch
~~~

This is a guiding decision tree. If a situation genuinely has only two states and the default is fully defined by the contract, there is no need to force a complex hierarchy. Once the caller needs to distinguish **no data** from **unable to read data**, a single sentinel is no longer enough.

## 25. Pre-production API checklist

- [ ] `null`, empty values, `0`, `false`, and default objects have **explicitly documented meanings**.
- [ ] Absence is distinguished from infrastructure errors/timeouts/cancellations.
- [ ] `Optional.empty()` is not used to hide `IOException`/`SQLException` when empty means `NotFound`.
- [ ] `catch` only catches exceptions allowed by policy; bugs are not swallowed by overly broad catches.
- [ ] If unrecoverable, exceptions are propagated or converted into `Failure` with a code and cause.
- [ ] Fallbacks are business-approved, with clear source, freshness, and limits.
- [ ] When caching `NotFound`, only confirmed absences are cached.
- [ ] `CompletableFuture.exceptionally`/`handle` do not fabricate "fake success" with unlabeled defaults.
- [ ] Futures are fully observed; exceptions are not ignored just because a task completed.
- [ ] Timeouts/interrupts/cancellations are not turned into success results without sufficient evidence.
- [ ] HTTP APIs distinguish true 404 from 503/500 and Pending when appropriate.
- [ ] Operation ID/idempotency is in place when remote side effects may complete despite caller timeout.
- [ ] Stack traces, secrets, or raw causes are not exposed in public responses.
- [ ] Monitoring tracks primary failures, fallback usage, technical failures, and unknown outcomes.
- [ ] Dependency fault-injection tests prove the code does not conflate states that must remain distinct.
- [ ] Backward compatibility and documentation are considered when changing legacy API return types.

## 26. Practice exercises

A service receives a request to fetch a product price and returns `BigDecimal`. Current implementation:

~~~java
BigDecimal getPrice(String sku) {
    try {
        return priceRepository.get(sku);
    } catch (Exception ignored) {
        return BigDecimal.ZERO;
    }
}
~~~

This is a **fragment** with assumed `BigDecimal` and `priceRepository`.

Answer and implement:
1. If a product has a valid price of **0 VND**, how does the caller distinguish it from a database error?
2. If `sku` does not exist, should you return `Optional<BigDecimal>`, throw a `NotFoundException`, or return a `Missing` result? Choose one contract and explain.
3. If the price is used for checkout/payment, is it acceptable to use a stale cached price when the primary source fails? Which invariants must be checked?
4. If the HTTP API returns 200 with price 0 after a `SQLException`, what mistakes could downstream systems make?
5. Write a sealed result type `PriceFound`, `PriceMissing`, `PriceUnavailable`; keep error codes stable and the cause internal.
6. Create a fake repository for the three scenarios found/missing/exception. Add a test verifying that an exception **is not turned into a valid 0 price**.
7. Suppose the price lookup runs in a `CompletableFuture`: replace `exceptionally(e -> BigDecimal.ZERO)` with a stage returning a typed result or preserving exceptional completion. Verify that metrics do not count errors as successes.
8. If the price was already used to create an order and then sending a notification failed, explain why you must not return price 0 / imply no order was created, and which state is needed for the side effect that already occurred.

**Conclusion:** A default value does not inherently mean "failure". When the contract is silent, catching an exception and returning `null`, `false`, `0`, `Optional.empty()`, or an empty collection can turn real errors into seemingly valid data. Always **separate absence, failure, fallback, and unknown**, preserve error causes, and test failure paths so callers receive the truth about the operation's outcome.
