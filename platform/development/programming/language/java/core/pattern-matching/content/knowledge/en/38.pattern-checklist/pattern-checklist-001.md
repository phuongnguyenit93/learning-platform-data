# Checklist for Choosing a Type Pattern

## 1. Choose the right tool before writing instanceof or switch

When handling a value with a supertype such as `Object` or an interface containing multiple subtypes, Java allows checking the type and handling cases using a **type pattern**. Typical syntax:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

`String text` here is a **type pattern**: the program checks whether the value matches the `String` type, then binds that reference to the name `text` with static type `String`. There is no need to write a manual cast `(String) value` after the check.

However, with type patterns, record patterns, sealed hierarchies, and pattern matching for `switch` in Java 21, the question is not just "which syntax compiles and runs?" but **"when is a type pattern the most readable and lowest-risk choice?"**.

A type pattern is usually worth choosing when:

- You need to distinguish **which subtype an object belongs to**.
- You need to use **the checked object as a whole** or pass it to another handler.
- The subtype **is not a record**, or deconstructing the entire record does not help.
- You only need a few accessors, without needing to read nested structures.
- A classification operation belongs to **an external context** outside the object, rather than being shared behavior that should be invoked via polymorphism.

Conversely, when you want to read multiple components of a record and that structure itself is what needs to be processed, a **record pattern** can express intent more clearly. When every subtype already provides the same behavior through an interface, **polymorphism** is usually better than checking each type and then calling the same method.

**Goal of this article:** provide a decision checklist that can be applied during code reviews, illustrated with Java 21 `instanceof` and `switch`, checking variable scoping errors, `null`, case ordering, generics, and extensibility.

## 2. Distinguishing four closely related options

| Tool | Example | When it makes sense |
| --- | --- | --- |
| Plain `instanceof` | `value instanceof String` | Only a true/false result is needed; the cast variable is not used. |
| **Type pattern** | `value instanceof String text` or `case String text -> ...` | Need to check the type **and** continue using the object with its specific type. |
| **Record pattern** | `value instanceof Point(int x, int y)` | Want to check a record and **deconstruct its components** into variables. |
| **Polymorphism** | `service.execute()` | Objects already share a behavioral contract and the caller does not need to know the subtype. |

Simplest example: if you are only asking "is this a string?", declaring a pattern variable is not required:

```java
static boolean isText(Object value) {
    return value instanceof String;
}
```

If you need the string's length after confirming the type:

```java
static int lengthOrZero(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

If you already have `record Point(int x, int y)` and actually need both coordinates:

```java
static int coordinateSum(Object value) {
    if (value instanceof Point(int x, int y)) {
        return x + y;
    }
    return 0;
}
```

The snippets above illustrate different choices. The last snippet requires the `Point` record in the same context and Java 21 for record patterns.

**Do not force every type test into a record pattern**, and do not keep manual casts after `instanceof` when a type pattern already clearly expresses what needs to be done.

## 3. Quick decision checklist in order

Read the questions from top to bottom; stop at the option that properly solves the task.

| Question | If the answer is "Yes" | Prefer |
| --- | --- | --- |
| 1. Do you only need a boolean to know whether an object belongs to a type? | No need to use the bound object. | Plain `instanceof T`, without creating an unnecessary pattern name. |
| 2. Does every subtype already have the meaningful method you need to call? | For example, every `PaymentMethod` has `pay()`. | Call via interface/polymorphism; do not split cases just to call the same method. |
| 3. Do you need the object **intact** to pass to a service or call multiple methods on it? | For example, passing `Submit submit` to a validator/handler. | **Type pattern**. |
| 4. Is the subtype a regular class, not a record? | There is no applicable record deconstruction. | **Type pattern** to check and obtain the object. |
| 5. Do you only need one component from a record with many components? | Deconstructing everything makes the code verbose/hard to follow. | Consider a type pattern and then call the needed accessor. |
| 6. Do you need multiple components and does the operation's meaning tie directly to the record's structure? | For example, `Point(int x, int y)` for computation. | **Record pattern**. |
| 7. Must you deconstruct nested records across multiple levels? | The structure to inspect is very clear. | Nested record pattern; if too deep, consider breaking it down. |
| 8. Are there multiple subtypes to branch on in a single transformation? | For example, log formatting or DTO mapping. | `switch` with type/record patterns. |
| 9. Is the hierarchy closed with `sealed`? | The set of subtypes is owned by the module. | `switch` without `default` when cases are exhaustive; leverage the compiler. |
| 10. Is the hierarchy open for plugins? | Future implementations may exist. | Prefer a polymorphic contract; if branching, define a meaningful fallback. |
| 11. Is there a condition to check after the type matches? | For example, quantity is at least 10. | Type pattern + `&&` in `if` or `case T t when ...` in `switch`. |
| 12. Could `null` be present? | The selector or a reference component may be null. | Explicit policy: `case null`, pre-check, or validation at the boundary. |

The checklist is not an algorithm that replaces domain design. There may be multiple valid approaches. What matters is choosing the one that expresses **the true responsibility of the logic**, avoids unnecessary deconstruction/casting, and preserves maintainability as the model evolves.

## 4. Prefer a type pattern when you need to keep the subtype object intact

Suppose an API receives an action with multiple subtypes:

```java
sealed interface Action permits Submit, Cancel, Heartbeat {}

record Submit(String id, int units) implements Action {}

record Cancel(String id, String reason) implements Action {}

final class Heartbeat implements Action {
    private final String node;

    Heartbeat(String node) {
        this.node = node;
    }

    String node() {
        return node;
    }
}
```

These are illustrative declarations without validation; the complete runnable program is in section 10.

A service needs to process the entire `Submit` object:

```java
if (action instanceof Submit submit) {
    submitHandler.handle(submit);
}
```

`submitHandler` in this snippet is an illustrative dependency, not a built-in Java variable. A **type pattern** makes sense because the handler takes a **Submit object**. If you deconstructed `Submit(String id, int units)` and then had to reconstruct the object to pass it to the handler, the code would be doing unnecessary work.

A non-record subtype like `Heartbeat` **cannot use a record pattern `Heartbeat(...)`**. For this type, a type pattern is the natural choice:

```java
if (action instanceof Heartbeat heartbeat) {
    System.out.println(heartbeat.node());
}
```

You can also use a type pattern with a record:

```java
if (action instanceof Submit submit) {
    System.out.println(submit.id());
    System.out.println(submit.units());
}
```

A type pattern does not require the subtype to be a regular class. It works with classes, interfaces, and records in accordance with Java's type rules.

### Not every record needs deconstruction

Suppose there is a record with many components:

```java
record Shipment(
        String id,
        String destination,
        int units,
        long createdAt,
        String customerCode) {}
```

If a function only needs `id`:

```java
static String shipmentId(Object value) {
    if (value instanceof Shipment shipment) {
        return shipment.id();
    }
    return "UNKNOWN";
}
```

This approach expresses the exact intent: check for `Shipment`, then read only the needed component. Using `Shipment(var id, var destination, var units, var createdAt, var customerCode)` just to get `id` can mislead readers into thinking the other components also matter.

**Performance note:** record patterns access components through accessors. However, you cannot claim that a type pattern is always faster; the JIT can inline simple getters. Choose the clearer expression first, and measure with a profiler/JMH when there is an actual bottleneck.

## 5. Prefer a record pattern when the goal is structural deconstruction

If the requirement is to compute the sum of a `Point`'s coordinates, the two-component record is itself the data you need:

```java
record Point(int x, int y) {}

static int sum(Object value) {
    return switch (value) {
        case Point(int x, int y) -> x + y;
        case null -> 0;
        default -> 0;
    };
}
```

Here, a record pattern makes the formula read closer to the data structure compared to:

```java
static int sumByType(Object value) {
    if (value instanceof Point p) {
        return p.x() + p.y();
    }
    return 0;
}
```

Both approaches can be reasonable. If the operation mainly depends on **components**, a record pattern is often concise; if you need to call multiple methods on `Point` or pass the object to other code, a type pattern is more convenient.

### When a nested record pattern is needed

```java
record Address(String city) {}
record Customer(String id, Address address) {}

static String customerCity(Object value) {
    return switch (value) {
        case Customer(var id, Address(var city)) ->
                id + " ở " + city;
        case Customer customer ->
                "Khách thiếu địa chỉ: " + customer.id();
        case null -> "Không có khách";
        default -> "Loại khác";
    };
}
```

This is a Java 21 illustrative snippet assuming the records are declared in the same context. The nested record pattern clearly expresses that the city is needed from the `Address` inside `Customer`.

The trailing `case Customer customer` branch covers a `Customer` object whose component does not match the nested pattern, such as `address == null`. That is **different** from binding `var address`: a `var` for a reference component can receive a null value, whereas the nested record pattern `Address(...)` does not match when the address itself is null.

**Rule of thumb:** If you do not genuinely need to read nested structures, a type pattern can help reduce nesting depth and avoid creating a long pattern that is hard to modify.

## 6. Type pattern vs. manual cast

Previously, code was often written as:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Java 16+ allows replacing this with:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Benefits of a type pattern:

- Reduces repetition of the type name and the cast operation.
- The compiler knows the variable `text` has type `String` where the pattern has matched.
- Reduces the risk of accidentally changing the type in the cast or reading the wrong variable.
- Pattern variables are governed by **flow scoping**: they cannot be used on paths where the pattern is not guaranteed to have matched.

However, a type pattern **does not replace every cast**. For example, when generic type arguments are erased at runtime, you cannot use `instanceof List<String>` as a complete check for a list of `String`s. If you need to verify each element, you must check the elements or use controlled validation.

You should also avoid creating a variable only to discard it:

```java
// Only true/false needed:
boolean isText = value instanceof String;

// Not needed:
// boolean isText = value instanceof String unused;
```

When a boolean is enough for the task, plain `instanceof T` is usually less noisy.

## 7. Using type patterns in if: flow scope and short-circuiting

The most important characteristic of a type pattern is that the variable is in scope **only where the compiler proves the pattern has matched**.

### Valid: right-hand side of &&

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.toUpperCase());
}
```

`&&` only evaluates its right-hand side when the `instanceof` test is true, so `text` is already bound.

Conditions can also be written with subtypes:

```java
if (action instanceof Submit submit
        && submit.units() >= 10) {
    System.out.println("BULK " + submit.id());
}
```

Read from left to right: check type → check data → perform processing.

### Invalid: using the variable on the right-hand side of ||

```java
// DOES NOT COMPILE if uncommented:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

`||` only evaluates its right-hand side when the left-hand side is **false**; in that case `text` is not guaranteed to exist. Furthermore, an `if` using OR can enter its body simply because another condition is true, even if the pattern did not match. If you need two independent cases, split the branches.

### Invalid: using in else or after an unguarded if

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    // No valid text here.
}

// DOES NOT COMPILE:
// System.out.println(text);
```

The fact that test data is "always a String" creates no flow-scope guarantee when the static type allows other values.

### Valid: early-exit guard clause

```java
static String requireText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.strip();
}
```

The non-matching branch ends with `throw`, so every path reaching `return text.strip()` has matched the pattern. If it only logged a warning and continued after the `if`, there would be no such guarantee.

**Checklist when using `if`:** Check `&&`/`||` operators, negation `!`, `return`/`throw` branches, and where the variable is used. Do not fix scope errors with an unsafe cast.

## 8. Type patterns in switch: ordering, when, null, and exhaustiveness

Starting in **Java 21**, type patterns in `switch` are a standard feature, no `--enable-preview` required.

```java
static String classify(Object value) {
    return switch (value) {
        case String text when !text.isBlank() ->
                "Có chữ: " + text.strip();
        case String ignored ->
                "Chuỗi trống";
        case Integer number ->
                "Số: " + number;
        case null ->
                "Không có dữ liệu";
        default ->
                "Kiểu khác";
    };
}
```

**Each case has a clear role:**

- `case String text when ...`: matches `String` then evaluates the guard.
- `case String ignored`: matches all remaining `String`s, including empty or whitespace-only strings.
- `case Integer number`: handles integers, without using the `text` variable from another case.
- `case null`: policy for a null selector.
- `default`: handles the remaining types in the open `Object` domain.

### Place specific cases before general cases

```java
// Correct:
case Submit submit when submit.units() >= 10 -> "BULK";
case Submit submit -> "STANDARD";
```

The lines above are illustrative branches belonging to a `switch`. If the unguarded `case Submit submit` is placed first, it covers every non-null `Submit`; the guarded case after it can be reported by the compiler as *dominated*.

A general type pattern can also cover subtypes:

```java
// DOES NOT COMPILE if ordered as follows in a switch on Object:
// case Object anything -> "OBJECT";
// case String text -> "TEXT";
```

`case Object anything` matches every non-null object, so the `String` case after it has no chance to run. Place specific branches before broad ones.

### Sealed and open interfaces

If the selector is `sealed interface Action` with subtypes `Submit`, `Cancel`, `Heartbeat`, a `switch expression` listing all those **type patterns** can be exhaustive **without `default`**. When a new subtype is added to `permits`, the compiler can require updating the classification sites upon recompilation.

With an **open** interface for plugins, you cannot reliably list all future subtypes with a few concrete cases; when classifying, you need a policy for the remainder or to invoke behavior through the interface. A `default` on an open domain can be reasonable, as long as it does not turn unsupported situations into false successes.

### Null is not default

With Java 21 pattern-matching `switch`, a `null` selector requires an explicit policy. Do not assume `default` replaces `case null`. If null is an error, you can use `case null -> throw new IllegalArgumentException(...)` instead of returning a message.

## 9. Type pattern or polymorphism?

Consider a service interface:

```java
interface ReportExporter {
    byte[] export();
}
```

If the code only needs to export data, the appropriate usage is:

```java
static byte[] runExport(ReportExporter exporter) {
    return exporter.export();
}
```

Do not write a series of `if (exporter instanceof CsvExporter csv) ...` just to call `export()` on each implementation. Polymorphism already solves behavior dispatch, and the caller only needs the shared contract.

Conversely, operations like **displaying a subtype-specific label**, **DTO conversion**, **log classification**, or **validating input types at a boundary** may need to know which case an object belongs to. A type pattern is appropriate if the logic belongs to the consumer layer and should not be pushed into the domain interface.

Example:

```java
static String auditLabel(Action action) {
    return switch (action) {
        case Submit submit -> "Submitted " + submit.id();
        case Cancel cancel -> "Cancelled " + cancel.id();
        case Heartbeat heartbeat -> "Heartbeat " + heartbeat.node();
        case null -> "No action";
    };
}
```

This illustration makes sense when the subtypes are defined like `Action` in section 4 and the author only needs a label for auditing. On the other hand, if "executing the action" is already a contract of every object, consider a handler/service or polymorphism instead of defaulting to a switch over all subtypes.

**Review rule:** A type pattern should clarify **a decision that genuinely depends on the type**; it should not be used to manually simulate behavior dispatch that an interface already defines.

## 10. Standalone runnable Java 21 example: type pattern as the primary choice

The program below intentionally combines:

1. `route`: uses **type patterns** in `switch`, because the handler wants to keep the whole object and call a few subtype accessors.
2. `routeByRecord`: uses **record patterns** on records to illustrate the difference when you actually want to extract components; `Heartbeat` is not a record so it still uses a type pattern.
3. `probe`: uses an `instanceof` type pattern with `&&`, showing flow scoping and a guard.
4. `describeInput`: uses type patterns to classify `Object`, with `when`, `case null`, and `default` for an open domain.

Create the file **`ChooseTypePatternChecklistDemo.java`**:

```java
public class ChooseTypePatternChecklistDemo {
    static void requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
    }

    sealed interface Action permits Submit, Cancel, Heartbeat {}

    record Submit(String id, int units) implements Action {
        Submit {
            requireNonBlank(id, "id");
            if (units <= 0) {
                throw new IllegalArgumentException(
                        "units must be positive");
            }
        }
    }

    record Cancel(String id, String reason) implements Action {
        Cancel {
            requireNonBlank(id, "id");
            requireNonBlank(reason, "reason");
        }
    }

    static final class Heartbeat implements Action {
        private final String node;

        Heartbeat(String node) {
            requireNonBlank(node, "node");
            this.node = node;
        }

        String node() {
            return node;
        }
    }

    static String route(Action action) {
        return switch (action) {
            case Submit submit when submit.units() >= 10 ->
                    "BULK:" + submit.id();

            case Submit submit ->
                    "SUBMIT:" + submit.id();

            case Cancel cancel ->
                    "CANCEL:" + cancel.id();

            case Heartbeat heartbeat ->
                    "HEARTBEAT:" + heartbeat.node();

            case null ->
                    "NULL_ACTION";
        };
    }

    static String routeByRecord(Action action) {
        return switch (action) {
            case Submit(var id, var units) when units >= 10 ->
                    "BULK:" + id;

            case Submit(var id, var units) ->
                    "SUBMIT:" + id;

            case Cancel(var id, var reason) ->
                    "CANCEL:" + id;

            case Heartbeat heartbeat ->
                    "HEARTBEAT:" + heartbeat.node();

            case null ->
                    "NULL_ACTION";
        };
    }

    static String probe(Object input) {
        if (input instanceof Submit submit
                && submit.units() >= 10) {
            return "FLAG:BULK";
        }
        if (input instanceof Submit submit) {
            return "FLAG:SUBMIT";
        }
        if (input instanceof Heartbeat heartbeat) {
            return "FLAG:NODE:" + heartbeat.node();
        }
        return "FLAG:OTHER";
    }

    static String describeInput(Object input) {
        return switch (input) {
            case String text when !text.isBlank() ->
                    "STRING:" + text.strip();

            case String ignored ->
                    "STRING_BLANK";

            case Action action ->
                    "ACTION:" + route(action);

            case null ->
                    "NULL_INPUT";

            default ->
                    "UNSUPPORTED:" + input.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        Action bulk = new Submit("O-10", 10);
        Action standard = new Submit("O-4", 4);
        Action cancelled = new Cancel("O-10", "duplicate");
        Action heartbeat = new Heartbeat("node-a");

        System.out.println(route(bulk));
        System.out.println(route(standard));
        System.out.println(route(cancelled));
        System.out.println(route(heartbeat));
        System.out.println(route(null));

        System.out.println(routeByRecord(bulk));
        System.out.println(routeByRecord(standard));
        System.out.println(routeByRecord(cancelled));
        System.out.println(routeByRecord(heartbeat));
        System.out.println(routeByRecord(null));

        System.out.println(probe(bulk));
        System.out.println(probe(standard));
        System.out.println(probe(heartbeat));
        System.out.println(probe("x"));

        System.out.println(describeInput("  abc  "));
        System.out.println(describeInput("   "));
        System.out.println(describeInput(bulk));
        System.out.println(describeInput(null));
        System.out.println(describeInput(42));

        try {
            new Submit(" ", 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("BAD_ID:" + ex.getMessage());
        }
    }
}
```

**Requirement:** JDK 21 or later. Compile and run without `--enable-preview`:

```bash
javac --release 21 -encoding UTF-8 ChooseTypePatternChecklistDemo.java
java ChooseTypePatternChecklistDemo
```

**Exact standard output:**

```text
BULK:O-10
SUBMIT:O-4
CANCEL:O-10
HEARTBEAT:node-a
NULL_ACTION
BULK:O-10
SUBMIT:O-4
CANCEL:O-10
HEARTBEAT:node-a
NULL_ACTION
FLAG:BULK
FLAG:SUBMIT
FLAG:NODE:node-a
FLAG:OTHER
STRING:abc
STRING_BLANK
ACTION:BULK:O-10
NULL_INPUT
UNSUPPORTED:Integer
BAD_ID:id must not be blank
```

### Output analysis

**First five lines:** `route` classifies using type patterns. `Submit("O-10",10)` satisfies the `units >= 10` guard so it returns `BULK`; `Submit("O-4",4)` misses the first guard, falls through to the unguarded `Submit` case, and returns `SUBMIT`. `Cancel` and `Heartbeat` are recognized by type. `null` has its own case.

**Next five lines:** `routeByRecord` produces the corresponding results but uses `Submit(var id, var units)` and `Cancel(var id, var reason)` to extract components. For `Heartbeat`, which is not a record, a type pattern must be used. This article does not treat `routeByRecord` as an always-better option: it merely illustrates the choice when deconstruction is genuinely desired.

**Four `FLAG` lines:** `probe` demonstrates type patterns in `if` with `&&`; `Submit` with sufficient units is matched first, and the remaining `Submit` is matched afterward. `Heartbeat` has its own branch; a string not belonging to any checked type returns `FLAG:OTHER`.

**Five `describeInput` lines:** a non-blank `String` is `strip()`ped to produce `STRING:abc`; a whitespace-only string goes to `STRING_BLANK`; an `Action` is passed to `route`; `null` enters `NULL_INPUT`; `Integer(42)` is not among the listed types so `default` returns `UNSUPPORTED:Integer`.

**Last line:** The `Submit` constructor rejects a blank `id` before a valid object can be created. Pattern matching recognizes subtypes; it does not replace data validation on its own.

Note: the program uses a **closed** sealed hierarchy for `Action` and an **open** `Object` domain for `describeInput`. This very contrast explains why `route` does not need `default` while `describeInput` has an intentional fallback.

## 11. When to choose a type pattern in switch?

A `switch` with type patterns is a good choice when there are **multiple branches handling subtypes** and you want to see the entire policy in one place. For example, mapping an API result:

```java
sealed interface Result permits Success, Failure {}

record Success(String message) implements Result {}

record Failure(int code, String reason) implements Result {}

static String toHttpSummary(Result result) {
    return switch (result) {
        case Success success ->
                "success: " + success.message();
        case Failure failure ->
                "error " + failure.code()
                        + ": " + failure.reason();
        case null ->
                "missing result";
    };
}
```

The declarations above are a separate example, not part of the program class in section 10. A type pattern can be suitable because the presentation logic uses **a few accessors** without needing to deconstruct the entire record.

When the record has the exact components needed, you can write:

```java
static String toHttpSummaryByRecord(Result result) {
    return switch (result) {
        case Success(var message) ->
                "success: " + message;
        case Failure(var code, var reason) ->
                "error " + code + ": " + reason;
        case null ->
                "missing result";
    };
}
```

Both express the same goal. Do not turn a guideline into a rigid mandate to use one syntax across the entire codebase; prioritize consistency within the module, readability, and how closely the logic ties to the record's structure.

### When should you not use switch?

For a single simple branch, `if (value instanceof T t)` can be more readable than a multi-line `switch`. If the logic is only meant to call a method already defined on the interface, polymorphism is clearer. If subtype-specific handling spans hundreds of lines, extract handlers, helpers/services, or redesign responsibilities instead of cramming all business logic into one `switch` expression.

## 12. Notes on generics and runtime-checkable types

Type patterns still obey the limits of **type erasure**:

```java
static int listSize(Object value) {
    if (value instanceof java.util.List<?> list) {
        return list.size();
    }
    return 0;
}
```

`List<?>` is a valid type for runtime checking with `instanceof`. However, from `List<?> list` you cannot infer that every element is a `String`. For example, a `List<Integer>` still matches the `List<?>` pattern.

Do not write:

```java
// Invalid for this kind of runtime check:
// if (value instanceof java.util.List<String> list) {
//     ...
// }
```

Because Java does not retain the full `String` type argument of `List<String>` at runtime to check with `instanceof` in that manner.

If you need to validate element structure, check each element:

```java
static boolean allStrings(Object value) {
    if (!(value instanceof java.util.List<?> list)) {
        return false;
    }
    for (Object element : list) {
        if (!(element instanceof String)) {
            return false;
        }
    }
    return true;
}
```

This function treats an empty list as valid under the rule "every element is a String". If the domain requires a non-empty list, add a separate condition. A type pattern helps us bind `List<?>` safely, **not automatically verify the collection's content contract**.

## 13. Common mistakes when choosing a type pattern

| Mistake | Why it matters | How to fix |
| --- | --- | --- |
| Writing `instanceof` then manually casting in the true branch | Repeats the type check, more code than necessary. | `value instanceof T t`. |
| Creating a pattern name when only a boolean is needed | Adds an unused variable, cluttering the code. | `value instanceof T`. |
| Using a type pattern just to call the same interface method | Caller becomes unnecessarily coupled to subtypes. | Call polymorphic behavior. |
| Using a record pattern when the whole object is needed | Deconstruction serves no purpose. | Use a type pattern and pass the object to the handler. |
| Using a type pattern in a case and trying to use the variable in another case | Invalid flow scope. | Keep the variable within its own case or pass data intentionally. |
| Placing a general type pattern before a specific pattern | The specific case is *dominated*. | Place specific/guarded branches first. |
| Using a type pattern variable on the right-hand side of `||` | The right-hand side is evaluated when the left-hand pattern may be false. | Split branches or use `&&` when dependent. |
| Assuming `default` always handles null | A null selector has special rules in pattern switch. | `case null` or validate before the switch. |
| Adding `default -> "OK"` to a sealed hierarchy | Hides missing subtypes that need handling. | List all cases exhaustively and leverage exhaustiveness. |
| Using `case Record(...)` for a regular class | Record patterns only work on records with valid structure. | Use a type pattern for regular classes. |
| Assuming a type pattern proves fields are non-null | It only proves the object matches the type. | Constructor/boundary validation and component checks. |
| Thinking `List<?>` is `List<String>` | Generic arguments can be erased at runtime. | Validate elements and separate domain rules. |
| Assuming a type pattern is always faster than a record pattern | Compiler/JIT behavior and actual work vary. | Measure when needed, do not guess from syntax. |
| Adding plugin subtypes while only classifying a few fixed types | Code does not handle new implementations. | Use an open contract or a meaningful fallback. |

### Unfeasible type check errors

The compiler also checks static type compatibility: not every `instanceof` between two unrelated types is valid. Do not try to work around this error by forcing every value to `Object` without a domain reason. Design meaningful API supertypes/interfaces and use type patterns at boundaries where data can genuinely have multiple types.

### Null object vs. null component

`value instanceof Submit submit` does not match when **value is null**. If `submit` is bound, the `Submit` object itself is non-null. However, `submit.id()` could in general be null if the constructor/API allowed it; in the demo, the constructor forbids null/blank. **A type pattern does not automatically verify every component of an object**.

## 14. Testing when refactoring to a type pattern

A refactor should not be judged solely by "it compiles". You should test:

1. **Correct subtype:** each subtype is classified into the expected branch.
2. **Non-matching types:** `instanceof` returns false or `switch` reaches a meaningful fallback.
3. **Null:** test a null selector separately; do not assume `default` is the null case.
4. **Guard true/false:** e.g., `Submit(10)` vs. `Submit(9)`, while also testing the fallback `Submit` case.
5. **Case dominance:** the compiler rejects or tests ensure broad branches do not shadow narrow ones.
6. **Null/blank components:** the constructor or boundary throws/returns errors per contract.
7. **Errors/exceptions:** if removing a cast or replacing a record pattern, confirm exception types and error paths remain appropriate.
8. **Compatibility:** adding a sealed subtype requires updating cases; an open interface needs a policy for unknown types.
9. **Generics:** check element data if business logic requires it, not just the collection type.
10. **Performance:** benchmark if this is a hot path; do not change code structure merely out of a hunch that a pattern has fewer opcodes.

### JUnit Jupiter test example

This is a **standalone test snippet**, requiring JUnit Jupiter and `ChooseTypePatternChecklistDemo.java` in the same package; it is **not** part of the standalone program in section 10:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ChooseTypePatternChecklistDemoTest {
    @Test
    void bulkSubmitUsesGuard() {
        var action = new ChooseTypePatternChecklistDemo.Submit("O-1", 10);
        assertEquals("BULK:O-1",
                ChooseTypePatternChecklistDemo.route(action));
    }

    @Test
    void standardSubmitFallsThroughToSecondCase() {
        var action = new ChooseTypePatternChecklistDemo.Submit("O-2", 9);
        assertEquals("SUBMIT:O-2",
                ChooseTypePatternChecklistDemo.route(action));
    }

    @Test
    void invalidIdRejectedByConstructor() {
        assertThrows(IllegalArgumentException.class,
                () -> new ChooseTypePatternChecklistDemo.Submit(" ", 1));
    }

    @Test
    void nullActionHasExplicitPolicy() {
        assertEquals("NULL_ACTION",
                ChooseTypePatternChecklistDemo.route(null));
    }
}
```

Testing with `units=10` and `9` helps catch accidental changes from `>=` to `>`. Checking other branches and null helps detect an inappropriate `default`. If the system has real domain behavior in the handler, tests should also verify **side effects or state**, not just the returned string.

## 15. Exercises applying the checklist

**Exercise 1 — Type check only**

Requirement: The method only returns true if `value` is a `Number`, without needing to use that value. What do you choose?

**Answer:**

```java
static boolean isNumber(Object value) {
    return value instanceof Number;
}
```

`instanceof Number number` is not wrong, but creates an unnecessary variable if it is never used.

**Exercise 2 — Passing the whole object to a handler**

Requirement: If the value is `Cancel`, pass the entire command to the handler. What do you choose?

**Answer:** Use `if (value instanceof Cancel cancel)` or `case Cancel cancel`, because the handler needs the **intact Cancel object**. Deconstructing `Cancel(var id,var reason)` and reconstructing the object has no benefit.

**Exercise 3 — Reading two components of a record**

Requirement: From `Point(x,y)`, compute `x*x + y*y`. What do you choose?

**Answer:** Record pattern `Point(int x,int y)` makes the deconstruction clear; type pattern `Point point` followed by calling `x()`/`y()` is also valid. Choose whichever is more readable in context.

**Exercise 4 — Non-record class**

Requirement: `Heartbeat` is a regular class with accessor `node()`. Can you use `Heartbeat(var node)`?

**Answer:** No, because it is not a record. Use `Heartbeat heartbeat` and call `heartbeat.node()`.

**Exercise 5 — Threshold check**

Requirement: Classify `Submit` with `units >= 10` as BULK; the rest as STANDARD. How do you write the `switch`?

**Answer:**

```java
return switch (action) {
    case Submit submit when submit.units() >= 10 -> "BULK";
    case Submit submit -> "STANDARD";
    case Cancel cancel -> "CANCEL";
    case Heartbeat heartbeat -> "HEARTBEAT";
    case null -> "NONE";
};
```

This is an illustrative snippet inside a method returning `String` on the sealed `Action`. The guarded case must precede the general `Submit` case. Do not add `default` just to ignore new subtypes.

**Exercise 6 — Classifying Object and unknown subtypes**

Requirement: The input may be a new plugin implementation. Should you list a few current classes and then `default -> "SUCCESS"`?

**Answer:** You should not report success for an unsupported case. Consider calling a polymorphic contract on the open interface or returning a meaningful `UNSUPPORTED` result/exception at the boundary.

## 16. Final checklist for pull request review

Before choosing a **type pattern**, answer:

- **Purpose:** Do you need to know the subtype and use the object, or just a boolean?
- **Contract:** Is there a meaningful polymorphic method that the caller should invoke directly?
- **Data:** Do you really need to deconstruct a record or nested record, or only use one accessor?
- **Shape:** Is the subtype a record, regular class, sealed, or open interface?
- **Placement:** Does a type pattern in `if` or `switch` reduce casts and clarify case selection?
- **Flow scope:** Is every use of the pattern variable on a path guaranteed to have matched?
- **Guard:** Do `&&`/`when` check the right condition; does a false guard have a subsequent case?
- **Ordering:** Is a broad case causing a specific branch to be dominated?
- **Null:** Are null selectors and nullable components separated according to contract?
- **Exhaustiveness:** For a sealed domain, are you leveraging exhaustive subtype checking instead of adding a default that hides errors?
- **Generics:** Are you confusing raw/runtime type checks with type argument validation?
- **Maintainability:** If a new subtype or operation is added, how many places will need to change?
- **Validation:** Matching a type structure does not guarantee valid business data.
- **Testing:** Have you tested matching/non-matching subtypes, guard true/false, null, unknown inputs, and errors?
- **Performance:** Do you have profiler/benchmark evidence before optimizing syntax?

## 17. Background references

- **JEP 394 — Pattern Matching for instanceof (Java 16):** https://openjdk.org/jeps/394
- **JEP 409 — Sealed Classes (Java 17):** https://openjdk.org/jeps/409
- **JEP 440 — Record Patterns (Java 21):** https://openjdk.org/jeps/440
- **JEP 441 — Pattern Matching for switch (Java 21):** https://openjdk.org/jeps/441
- **Java Language Specification 21 — Patterns (`14.30):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **Java 21 Language Guide — Pattern Matching for switch:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html

**Conclusion:** Choose a **type pattern** when you need to **confirm a subtype and use the bound object**, especially when the subtype is a regular class, the whole object must be passed to a handler, or data deconstruction is unnecessary. Choose a **record pattern** when the component structure itself is what needs to be read. Choose **plain `instanceof`** when only a boolean is needed. Choose **polymorphism** when shared behavior is already defined. In all cases, verify **flow scope, `when`/`&&`, case ordering, `null`, exhaustiveness, and data contracts** before finalizing the refactor.
