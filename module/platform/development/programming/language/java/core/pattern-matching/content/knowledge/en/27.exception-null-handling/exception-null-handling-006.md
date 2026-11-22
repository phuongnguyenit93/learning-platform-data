# Do Not Hide Errors with default

## 1. The problem: a valid fallback is different from swallowing errors

In Java, a `default` branch of a `switch` is often understood as "the remaining cases". That understanding is not enough when combining **pattern matching**, **exceptions**, and **domain modeling**: some remaining cases are normal data that the application needs to support; however, other remaining cases represent **a design flaw, invalid data, or a new unhandled subtype**.

For example, a service returns three result variants:

- `Ok`: completed successfully;
- `Rejected`: rejected with a specific reason;
- `Retry`: needs to be retried after an interval.

If a classification only recognizes `Ok` and `Rejected`, and puts `default -> "Không xác định"`, then every `Retry` can be turned into a generic label. The code still runs, and the system has no idea that it has **skipped a state that requires business handling**.

**Goal of this lesson:** identify when `default` is genuinely an intentional fallback and when it is hiding errors; know how to use `sealed interface`, pattern matching for `switch`, `case null`, and exceptions to clearly express the handling contract. You should not remove every `default`: the issue lies in the **meaning** of the remaining case.

## 2. Typical example: default silently ignores a subtype

Suppose the following are declared:

```java
sealed interface Result permits Ok, Rejected, Retry {}

record Ok(int receiptId) implements Result {}
record Rejected(String reason) implements Result {}
record Retry(int seconds) implements Result {}
```

These are illustrative Java 21 declarations; a later section has a complete runnable program.

An error-prone way to write it:

```java
static String describeUnsafe(Object value) {
    return switch (value) {
        case Ok ok -> "Thành công #" + ok.receiptId();
        case Rejected rejected -> "Từ chối: " + rejected.reason();
        default -> "Không xác định";
    };
}
```

If you call `describeUnsafe(new Retry(3))`, the result is `"Không xác định"`, even though `Retry` is a variant **explicitly defined in the domain**. The compiler does not force the author to add a `Retry` case because `default` already covers all remaining non-`null` values.

The danger does not necessarily lie in the string `"Không xác định"`, but in the consequences:

1. **Loss of information:** the retry delay (3 seconds) is ignored.
2. **Hidden model changes:** a new subtype can be added while the classification site still compiles and returns the old fallback.
3. **Hard to detect through monitoring:** an important business state is lumped together with genuinely unsupported types.
4. **Tests easily miss it:** testing only `Ok` and `Rejected` may fail to detect the missing `Retry`.

With a `switch` on `Object`, a `default` can make sense because data not belonging to the supported types may appear. However, this example uses `default` **instead of handling a valid subtype of `Result` itself**; that is a design mistake.

## 3. Use exhaustiveness so the compiler warns about missing branches

When the domain is a controlled set of variants, `sealed interface` allows Java 21 to check **`switch` expression exhaustiveness**.

A design that handles the variants explicitly:

```java
static String describe(Result result) {
    return switch (result) {
        case Ok(int receiptId) ->
                "Thành công #" + receiptId;
        case Rejected rejected ->
                "Từ chối: " + rejected.reason();
        case Retry(int seconds) ->
                "Thử lại sau " + seconds + " giây";
        case null ->
                throw new IllegalArgumentException("Kết quả không được null");
    };
}
```

Key points:

- `Result` is a `sealed interface` that directly permits only `Ok`, `Rejected`, and `Retry`. These are all records, and records are `final`.
- `Ok(int receiptId)` and `Retry(int seconds)` are **record patterns**: when matched, the `int` component is extracted into a variable.
- `case Rejected rejected` is a **type pattern**: it matches any non-`null` `Rejected` object, even when the `reason` component inside is `null`. To reject `reason == null`, a separate check is needed.
- With the cases above, the compiler knows that every non-`null` variant of `Result` already has a branch. No `default` is needed.
- `case null` handles a `null` selector explicitly with an exception matching the input policy.

**Benefit when adding a subtype:** If the domain owner adds a new direct subtype to `permits`, `switch` expressions without `default` that were previously exhaustive may be reported by the compiler as non-exhaustive when recompiled. This is a valuable signal: the programmer must decide how to handle the new subtype, rather than silently turning it into a generic value.

A limitation to understand: exhaustiveness checking reflects the **type information and patterns** that the compiler can determine. It does not replace business tests, data validation, or runtime error handling. In an environment with asynchronous module/binary upgrades, an old `switch` that was once compiled exhaustively can still encounter a new type at runtime and result in a `MatchException`. Therefore, when changing the hierarchy, dependent modules must be tested and released in sync.

## 4. Another mistake: default hides invalid data inside a valid subtype

Even when all three subtypes are handled, there can still be **invalid data in a component**.

For example, `Retry(int seconds)` allows creating `new Retry(0)` or `new Retry(-5)` if the record has no validation. Handling it with a generic branch like:

```java
// Easily loses the meaning of invalid seconds:
case Retry retry -> "Trạng thái khác";
```

will let bad data pass through as if it were a normal situation.

If the business rule requires `seconds > 0`, express that condition clearly:

```java
case Retry(int seconds) when seconds > 0 ->
        "Thử lại sau " + seconds + " giây";
case Retry retry ->
        throw new IllegalArgumentException(
                "Thời gian thử lại không hợp lệ: " + retry.seconds());
```

Here:

1. Java only evaluates `when seconds > 0` after the record pattern `Retry(int seconds)` has matched.
2. The unguarded `Retry retry` branch must come **after** the specific branch so it does not dominate the preceding branch.
3. `Retry(0)` still belongs to type `Retry` but is rejected with an exception that has a clear message.
4. Together, the two cases handle all non-`null` `Retry` values, so an ambiguous `default` is unnecessary.

**Do not confuse subtype checking with validation:** `sealed` controls which object types are permitted to participate in the type hierarchy; `record pattern` checks structure and extracts components; whereas `when` or a constructor checks value constraints such as `seconds > 0`. If every `Retry` must be valid across the entire system, it is better to enforce the invariant right at the constructor/boundary so invalid data cannot be created.

## 5. Null is not "another type"

In Java 21's pattern matching for `switch`, **a `null` selector is a separate case**. Do not expect `default` to always behave like `case null`.

For example:

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        default -> "Khác";
    };
}
```

With `label(null)`, the program can throw a `NullPointerException` because there is no `case null` branch, **not** return `"Khác"`. A `default` branch is not a null-handling policy.

If `null` is treated as an input error:

```java
case null -> throw new IllegalArgumentException("Thiếu dữ liệu");
```

If `null` is a valid business state, such as the UI not having selected a filter yet:

```java
case null -> "Chưa chọn";
```

Both approaches can be right in the appropriate context. The mistake is letting `null` be handled accidentally, and then using `default` or `catch (Exception ...)` to turn every error into the same string.

**For components inside a record**, you also need to be careful:

```java
record Rejected(String reason) implements Result {}
```

The type pattern `case Rejected rejected` accepts any non-null `Rejected`, but `rejected.reason()` can still be `null`. A message like `"Từ chối: " + rejected.reason()` could print `"Từ chối: null"`, misleading readers into thinking the rejection information is valid.

A stricter approach is to check the requirement explicitly:

```java
case Rejected rejected -> {
    String reason = rejected.reason();
    if (reason == null || reason.isBlank()) {
        throw new IllegalArgumentException(
                "Lý do từ chối không hợp lệ");
    }
    yield "Từ chối: " + reason;
}
```

In a `switch` expression, when a case uses a block and needs to produce a value, use `yield`. If the data is invalid, `throw` is an explicit option. Do not "sanitize" every error with a `default` and treat them as success.

## 6. When is default the right choice?

Not every `default` hides errors.

### 6.1. Input data belongs to an open set

If you receive `Object` from an integration point where many different types may appear, a fallback with a clear policy can be reasonable:

```java
static String friendlyLabel(Object value) {
    return switch (value) {
        case String text -> "Chuỗi: " + text;
        case Integer number -> "Số: " + number;
        case null -> "Không có giá trị";
        default -> "Định dạng chưa được hỗ trợ";
    };
}
```

Here, the author **intentionally** allows all remaining types to become a meaningful result: "Định dạng chưa được hỗ trợ" (unsupported format). If the feature only displays a label and no critical action is skipped, `default` may be appropriate.

However, at a boundary that requires the data to be one of a few supported types in order to continue business processing, it is better to reject explicitly:

```java
static String requireSupported(Object value) {
    return switch (value) {
        case String text -> text;
        case Integer number -> number.toString();
        case null -> throw new IllegalArgumentException("Thiếu đầu vào");
        default -> throw new IllegalArgumentException(
                "Kiểu không hỗ trợ: " + value.getClass().getName());
    };
}
```

The `default` branch is still present, but it **does not swallow errors**: it creates an exception with clear diagnostic data. Here `value.getClass()` is safe because `null` already has its own case; the type patterns handle the recognized cases.

### 6.2. The "unknown" case is genuinely a domain state

If the domain model defines an `Unknown` state as a valid variant, it should be represented by an explicit subtype or result, rather than silently pushing all errors into `default`. For example, `sealed interface Status permits Active, Inactive, Unknown` helps the caller distinguish **a state designed as Unknown** from **a data error or an unhandled subtype**.

### 6.3. Intentional compatibility or telemetry

When an application must accept formats from a legacy system, routing unfamiliar input into a fallback branch can be an intentional compatibility decision. However, you should:

- Log or measure unsupported events accurately if monitoring is needed.
- Avoid returning a false success for critical transactional operations.
- Document the policy clearly in the API, logs, and tests, especially where "unsupported" could easily be confused with "data error".

## 7. Complete runnable Java 21 program

Create the file **`DefaultMustNotHideErrorsDemo.java`**:

```java
public class DefaultMustNotHideErrorsDemo {
    sealed interface Result permits Ok, Rejected, Retry {}

    record Ok(int receiptId) implements Result {}
    record Rejected(String reason) implements Result {}
    record Retry(int seconds) implements Result {}

    // Illustrative anti-pattern: missing Retry is swallowed by default.
    static String describeUnsafe(Object value) {
        return switch (value) {
            case Ok ok -> "Thành công #" + ok.receiptId();
            case Rejected rejected ->
                    "Từ chối: " + rejected.reason();
            default -> "Không xác định";
        };
    }

    // Handles all domain types and validates internal data.
    static String describeStrict(Result result) {
        return switch (result) {
            case Ok(int id) -> "Thành công #" + id;

            case Rejected rejected -> {
                String reason = rejected.reason();
                if (reason == null || reason.isBlank()) {
                    throw new IllegalArgumentException(
                            "Lý do từ chối không hợp lệ");
                }
                yield "Từ chối: " + reason;
            }

            case Retry(int seconds) when seconds > 0 ->
                    "Thử lại sau " + seconds + " giây";

            case Retry retry ->
                    throw new IllegalArgumentException(
                            "Thời gian thử lại không hợp lệ: "
                                    + retry.seconds());

            case null ->
                    throw new IllegalArgumentException(
                            "Kết quả không được null");
        };
    }

    // Open boundary: explicitly rejects values outside Result.
    static String describeExternal(Object input) {
        if (input == null) {
            throw new IllegalArgumentException(
                    "Kết quả không được null");
        }
        if (!(input instanceof Result result)) {
            throw new IllegalArgumentException(
                    "Không phải Result: " + input.getClass().getName());
        }
        return describeStrict(result);
    }

    static void showFailure(
            String label,
            java.util.function.Supplier<String> action) {
        try {
            System.out.println(label + " -> " + action.get());
        } catch (IllegalArgumentException ex) {
            System.out.println(label
                    + " -> IllegalArgumentException: "
                    + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println(describeStrict(new Ok(12)));
        System.out.println(describeStrict(
                new Rejected("Thiếu chữ ký")));
        System.out.println(describeStrict(new Retry(3)));

        System.out.println("default âm thầm: "
                + describeUnsafe(new Retry(3)));

        showFailure("retry 0",
                () -> describeStrict(new Retry(0)));

        showFailure("lý do null",
                () -> describeStrict(new Rejected(null)));

        showFailure("selector null",
                () -> describeStrict(null));

        showFailure("kiểu không hỗ trợ",
                () -> describeExternal("lạ"));
    }
}
```

Compile and run with **JDK 21 or later**, without enabling preview features:

```bash
javac -encoding UTF-8 DefaultMustNotHideErrorsDemo.java
java DefaultMustNotHideErrorsDemo
```

Output:

```text
Thành công #12
Từ chối: Thiếu chữ ký
Thử lại sau 3 giây
default âm thầm: Không xác định
retry 0 -> IllegalArgumentException: Thời gian thử lại không hợp lệ: 0
lý do null -> IllegalArgumentException: Lý do từ chối không hợp lệ
selector null -> IllegalArgumentException: Kết quả không được null
kiểu không hỗ trợ -> IllegalArgumentException: Không phải Result: java.lang.String
```

Line-by-line explanation:

1. `Ok(12)` matches `Ok(int id)` and returns a success receipt.
2. `Rejected("Thiếu chữ ký")` matches `Rejected`, passes validation, and produces a specific message.
3. `Retry(3)` matches the record pattern with the guard `seconds > 0`.
4. The same `Retry(3)`, when passed through `describeUnsafe`, falls into `default` and is turned into `Không xác định`. This directly illustrates hiding a domain state.
5. `Retry(0)` has a valid subtype, but its value fails the rule; the unguarded `Retry retry` branch throws `IllegalArgumentException`.
6. `Rejected(null)` still matches the type pattern `Rejected rejected`; validation detects the null reason and throws an exception.
7. `describeStrict(null)` selects `case null` and throws an exception with a dedicated message.
8. The string `"lạ"` does not belong to `Result`. `describeExternal` rejects it with `IllegalArgumentException` including the runtime class name `java.lang.String`.

`showFailure` is only used to demonstrate **expected errors** and print deterministic output. In production code, you should not catch `IllegalArgumentException` on every path just to turn it into a string and treat the transaction as successful. The UI or boundary layer can catch errors to return an appropriate message, but the business layer still needs to preserve an explicit error state.

## 8. Do not hide exceptions with catch and an empty fallback

A related anti-pattern:

```java
// DO NOT: swallow every RuntimeException and continue as if successful.
static String unsafeOperation() {
    try {
        return performImportantOperation();
    } catch (RuntimeException ex) {
        return "OK";
    }
}
```

This example is illustrative only, assuming the method `performImportantOperation()` is defined elsewhere. It can hide programming logic bugs, data-persistence failures, or environment-related exceptions.

A version with a clearer policy distinguishes recoverable errors from errors that must be reported:

```java
// Illustrative; assumes recoverableAction() and notifyFailure(...) exist.
static String performWithPolicy() {
    try {
        return recoverableAction();
    } catch (TransientServiceException ex) {
        notifyFailure(ex);
        throw ex;
    }
}
```

This is **illustrative pseudocode**: `TransientServiceException`, `recoverableAction()`, and `notifyFailure()` are not built-in Java APIs. The point is to show that catching an expected error type must have an explicit policy — controlled recovery, returning a typed error result, or rethrowing — rather than `return "OK"` regardless of cause.

In practice, not every application has to throw an exception for every unfamiliar input. It can return a dedicated typed `Result` such as `UnsupportedInput`. What matters is that **the error is represented, not disguised as success**.

## 9. Rules for writing switches that surface errors easily

### 9.1. Separate business branches from technical fallbacks

A `switch` should make the valid business variants clear first. If the type domain is closed, let the compiler warn about missing branches. Only if the type domain is open should you decide on an explicit fallback policy.

Do not write `default -> null`, `default -> false`, or `default -> "OK"` just to silence the error "switch expression does not cover all possible input values", unless those results **truly** are the contract for all remaining cases.

### 9.2. Specific first, general last

Place detailed or guarded patterns before broader patterns:

```java
case Retry(int seconds) when seconds > 0 -> "Đang chờ";
case Retry retry -> throw new IllegalArgumentException("Sai seconds");
```

If the order is reversed, `case Retry retry` can cover all of `Retry`, causing the specific branch after it to be *dominated* and fail to compile. The compiler helps detect such dominance cases according to Java's rules.

### 9.3. Do not let a generic default hide changes to a sealed hierarchy

A pattern to avoid in a closed domain:

```java
// Drawback: when adding a new subtype, you may not get a warning
// about a missing case in this expression because default is present.
return switch (result) {
    case Ok ok -> "OK";
    case Rejected rejected -> "NO";
    default -> "OTHER";
};
```

This snippet is illustrative inside a method returning `String`, where variable `result` already exists. If `Retry` needs an explicit outcome, replace `default` with a `Retry` case and only use a catch-all branch when the contract genuinely requires it.

### 9.4. Choose the right error type

- **`IllegalArgumentException`** is appropriate when an input violates the method's contract, such as negative seconds or an unsupported subtype.
- **`IllegalStateException`** is appropriate when the internal state is incompatible with the requested operation.
- **A named domain exception or result type** is appropriate when a business error needs to be handled across other layers, such as `PaymentDeclined` or `ValidationError`.
- **`NullPointerException`** can be the consequence of using a null selector without a case, but if null is an input error that should be reported intentionally, using an explicit check/`case null` is clearer.

No single exception fits every situation. What matters is **defining who detects the error, who handles it, and what behavior counts as success**.

## 10. Decision table: use default, case null, or throw?

| Situation | Handling to consider | Reason |
| --- | --- | --- |
| `switch expression` on a sealed domain with all subtypes known | List specific cases, usually without adding `default` | The compiler checks exhaustiveness and warns when subtypes are extended. |
| A valid subtype whose component violates an invariant | Case with the subtype + validation, `throw`, or a typed error result | Avoids turning invalid data into a generic success state. |
| Selector can be `null` | `case null` or check before `switch` | Separates the null policy from fallbacks for other types. |
| API accepts `Object`/open interface and tolerates unknown types | `default` with a documented fallback label | This may be normal behavior, not an error. |
| API receives an unknown type and business logic cannot continue | `default -> throw ...` or validation at the boundary | The error is expressed clearly and is observable. |
| Extending `sealed permits` in a new release | Recompile `switch`es, add cases, and add tests | Prevents missing handling for a new valid state. |
| System intentionally has `Unknown` as a valid state | Create a dedicated subtype/result when appropriate | Avoids equating intentional unknown with a program bug. |

## 11. Test error branches, not just success branches

A test suite should also verify the cases that `default` can easily hide:

1. **Every permitted subtype:** for `Ok`, `Rejected`, `Retry`, verify the specific result; do not only check that the method does not throw an exception.
2. **Guard boundary values:** `Retry(1)`, `Retry(0)`, `Retry(-1)`; verify the exact `seconds > 0` condition.
3. **Nullable components:** `Rejected(null)` or `Rejected("")` if the model can construct them; verify the exception or error result.
4. **Null selector:** test separately; do not assume `default` handles it.
5. **Out-of-domain types:** for APIs accepting `Object`, pass a `String` or another type to verify the fallback or exception matches the contract.
6. **Sealed hierarchy changes:** whenever a subtype is added, recompile, resolve warnings/errors, and add tests for the new variant.
7. **Error observability:** when an error must be recorded, ensure the program does not turn it into `"OK"` or `false` that the caller interprets as success.

You can use JUnit to write unit tests like `assertThrows(IllegalArgumentException.class, ...)`, but no external library is required to grasp the core idea: every failure branch must have a **clear expected outcome**.

## 12. Self-check

Suppose:

```java
sealed interface JobState permits Done, Failed, Waiting {}
record Done(int id) implements JobState {}
record Failed(String reason) implements JobState {}
record Waiting(int seconds) implements JobState {}
```

**Question 1.** Why should the following snippet not be used when `Waiting` is an important business state?

```java
// Illustrative inside a method receiving JobState state.
return switch (state) {
    case Done done -> "Xong";
    case Failed failed -> "Lỗi";
    default -> "Khác";
};
```

**Answer:** `Waiting` is pushed into `default` and loses the information that the job is waiting. With a sealed hierarchy, you should add an explicit `Waiting` case and let the compiler check `switch` exhaustiveness.

**Question 2.** If `Waiting(0)` is invalid, is merely adding `case Waiting waiting -> "Chờ"` enough?

**Answer:** No. Matching the subtype does not check the `seconds > 0` rule. You need validation in the constructor or a guarded branch that reports an error when the value does not meet the rule.

**Question 3.** If `state == null` and the `switch` only has `default`, can you be sure you will get `"Khác"`?

**Answer:** No. In Java 21's pattern matching for `switch`, `null` has its own handling rules. You may get a `NullPointerException` if there is no null policy; use `case null` or check before `switch` when needed.

**Remember:** `default` **is not wrong in itself**. It becomes dangerous when it turns a case **that ought to be handled or reported as an error explicitly** into a generic result, making callers believe the program succeeded. For closed domains, prefer specific `case`s so the compiler checks exhaustiveness; for open inputs, define a fallback or exception matching the contract; for `null` and data violating invariants, check explicitly. Doing so makes errors surface in the right place instead of being hidden in a seemingly convenient `default` branch.
