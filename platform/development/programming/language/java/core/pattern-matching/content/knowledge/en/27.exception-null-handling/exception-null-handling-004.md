# NullPointerException When `case null` Is Missing in `switch` (Java 21+)

## 1. The Core Problem

With a `switch` accepting a reference type (**reference type**), if the selector expression evaluates to `null` and the switch **does not have a `case null` label**, Java throws a **`NullPointerException` (NPE)**. This holds true even when the switch has a `default` branch:

~~~java
Object value = null;

String result = switch (value) {
    case String s -> "String: " + s;
    default -> "Giá trị khác";
};
// Runtime: NullPointerException, does NOT return "Giá trị khác".
~~~

A common mistake is assuming that `default` is equivalent to `else` and will accept everything, including `null`. **Incorrect.** `default` handles values that do not match other labels according to switch rules, but `null` has its own rule: if `case null` is missing, handling a null selector throws an NPE.

The standard fix in Java 21:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String s -> "String: " + s;
        default -> "Giá trị khác";
    };
}

System.out.println(classify(null));  // Không có dữ liệu
System.out.println(classify(42));    // Giá trị khác
~~~

This article explains when NPEs occur, why `default`/record patterns/total patterns do not automatically handle null, how to use `case null` or proactively reject null, and how to test for errors with Java 21+.

**Version:** pattern matching syntax for `switch` and the `case null` label were standardized in **Java 21 (JEP 441)**. Earlier versions had preview stages; to compile the examples here without enabling preview features, use **JDK 21 or later**.

## 2. What Is a `selector`, and When Does NPE Occur?

In:

~~~java
String label = switch (value) {
    case String text -> "String: " + text;
    default -> "Other";
};
~~~

`value` is the **selector expression**: the expression evaluated to choose a `case` branch. If the selector's value is `null` and the switch has no `case null`, the result is an NPE by language rules—**not** because `text.toString()` ran or because `default` itself threw an error.

Distinguish between:

1. **NPE due to missing `case null`:** the selector is `null`; the switch does not handle null; the NPE occurs in the branch selection mechanism.
2. **NPE due to code inside a branch:** the selector may be non-null and the branch matched, but code inside the branch invokes a method on a null reference. Having `case null` for the selector **does not guarantee** that all other variables/fields/components are non-null.
3. **NPE caused by the selector expression itself before returning a value:** for example `switch (order.getStatus())` when `order == null`; at this point, calling `getStatus()` already throws an NPE, so `case null` cannot "rescue" that error.

Example of type (3):

~~~java
// When order is null, calling order.status() throws NPE before switch receives a selector.
String result = switch (order.status()) {
    case null -> "Không có trạng thái";
    default -> "Có trạng thái";
};
~~~

To handle this safely, check `order` **before accessing** it, or construct a selector that is itself allowed to be `null`:

~~~java
String status = order == null ? null : order.status();

String result = switch (status) {
    case null -> "Không có trạng thái";
    default -> "Có trạng thái";
};
~~~

These are illustrative snippets assuming an existing `order` variable and `status()` method; they are **not standalone programs**.

## 3. Why Doesn't `default` Catch `null`?

Consider:

~~~java
static String unsafe(Object value) {
    return switch (value) {
        case String s -> "Text: " + s;
        default -> "Khác";
    };
}
~~~

- `unsafe("Java")`: the selector is a non-null `String`, enters `case String s`.
- `unsafe(10)`: the selector is a non-null `Integer`, does not match `String`, enters `default`.
- `unsafe(null)`: null selector, **NPE**, does not enter `default`.

Fix by explicitly expressing the policy for null:

~~~java
static String safe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "Text: " + s;
        default -> "Khác";
    };
}
~~~

Key takeaway: having `default` covers the **remaining normal types/values** and satisfies the *exhaustiveness* requirement, but it does not implicitly turn a null selector into a default value.

This applies to **both switch expressions and switch statements**. The difference between the two forms is that a switch expression must produce a value, whereas a switch statement primarily controls execution flow; the rule for handling a null selector remains the same.

## 4. `case null`: Three Ways to Design Policy

### 4.1. Returning a Valid Value for Null

Use when null has business meaning, such as "no data yet":

~~~java
static String display(Object value) {
    return switch (value) {
        case null -> "Chưa có dữ liệu";
        case String s -> s;
        default -> "Không phải chuỗi";
    };
}
~~~

Advantage: clean code without needing an `if (value == null)` check outside the switch; null becomes a case declared right alongside the other cases.

### 4.2. Proactively Rejecting Null with a Meaningful Exception

Null is not always valid data. If the API contract forbids null, you can throw an explicit exception:

~~~java
static String displayStrict(Object value) {
    return switch (value) {
        case null -> throw new IllegalArgumentException("value không được null");
        case String s -> "String: " + s;
        default -> "Khác";
    };
}
~~~

This approach does **not** "fix" the null value; it converts an implicit, unclear NPE into an intentional rejection. Choose `IllegalArgumentException` or a domain exception that fits the API's contract. Another option is checking beforehand:

~~~java
Objects.requireNonNull(value, "value không được null");
return switch (value) {
    case String s -> s;
    default -> "Khác";
};
~~~

`Objects.requireNonNull` still throws an **NPE**, but the message clearly states the violated precondition. This can be a reasonable choice if the API specifies null as a programming error rather than a recoverable business state.

### 4.3. Combining `case null, default`

Java 21 allows combining the `null` label with `default` if you want them to have the **same behavior**:

~~~java
static String fallback(Object value) {
    return switch (value) {
        case String s -> "String: " + s;
        case null, default -> "Null hoặc kiểu khác";
    };
}
~~~

This works well when there is no need to distinguish null from unexpected values. However, if null and unsupported data carry different meanings, two separate branches make logs and metrics easier to track.

**Syntax restriction:** Java 21 does not allow mixing `null` with a regular **pattern label** in the same list, such as `case null, String s -> ...`. That snippet is a compile-time error: `invalid case label combination`. Only combine `null` with `default` in the allowed form above, or write separate branches.

## 5. The `case Object obj` Pattern Still Does Not Catch Null

An easy mistake to make when seeing a very broad pattern type is:

~~~java
static String catchEverything(Object value) {
    return switch (value) {
        case Object obj -> "Đã nhận object";
    };
}
~~~

The switch above is an **exhaustive switch** with an `Object` pattern for non-null instances: the compiler can consider all non-null values covered.

However:

~~~java
catchEverything(null); // Still throws NullPointerException.
~~~

Reason: `null` does not match the type pattern `Object obj`. For a null switch selector, language rules require a separate `case null`. There is no exception just because the pattern is `Object` or a general supertype.

To accept null as a normal result:

~~~java
static String catchEverythingIncludingNull(Object value) {
    return switch (value) {
        case null -> "Giá trị null";
        case Object obj -> "Object: " + obj.getClass().getSimpleName();
    };
}
~~~

In the `Object obj` branch, `obj` can be considered non-null, because null has already been handled separately and type patterns do not match null.

## 6. Exhaustiveness of a Sealed Hierarchy Is Not Null-Safety

A sealed interface allows describing a closed set of subtypes:

~~~java
sealed interface Message permits TextMessage, CountMessage {}

record TextMessage(String text) implements Message {}
record CountMessage(int count) implements Message {}
~~~

With a switch on `Message`:

~~~java
static String describe(Message message) {
    return switch (message) {
        case TextMessage(var text) -> "Tin: " + text;
        case CountMessage(var count) -> "Đếm: " + count;
    };
}
~~~

This is a switch expression that is **exhaustive at compile time** for the valid subtypes of `Message`: no `default` is needed. But:

~~~java
describe(new CountMessage(3)); // "Đếm: 3"
describe(null);                // NullPointerException.
~~~

The statement "the switch is exhaustive" only refers to coverage under type-checking rules; it does **not** mean the switch automatically accepts null. To handle null intentionally:

~~~java
static String describeSafe(Message message) {
    return switch (message) {
        case null -> "Thiếu thông điệp";
        case TextMessage(var text) -> "Tin: " + text;
        case CountMessage(var count) -> "Đếm: " + count;
    };
}
~~~

When encountering an NPE in a switch covering all subtypes, don't rush to add `default` thinking it's fixed. Investigate **where the selector can become null**, then decide whether to return a value, throw an explicit contract error, or prevent null at the data boundary.

## 7. Record Patterns: Null Selector vs. Null Component

In a pattern matching program, there are two null locations that are frequently confused.

**Case A — the switch selector is null.**

~~~java
Object input = null;

String label = switch (input) {
    case null -> "NULL";
    case Shipment(var id, var destination) -> id;
    default -> "Khác";
};
~~~

If **`case null` is omitted**, a null selector causes an NPE. The record pattern `Shipment(...)` will **not** be selected for null.

**Case B — the record selector is non-null, but a component is null.**

~~~java
record Address(String city) {}
record Shipment(String id, Address destination) {}

Object input = new Shipment("S-2", null);

String label = switch (input) {
    case Shipment(var id, Address(var city)) ->
        id + " đến " + city;
    case Shipment(var id, var destination) ->
        id + " thiếu địa chỉ";
    case null -> "NULL";
    default -> "Khác";
};
System.out.println(label); // S-2 thiếu địa chỉ
~~~

In Case B:

1. The selector is a `Shipment` instance, so it is **not null** itself.
2. The nested record pattern `Address(var city)` **does not match** the component `destination == null`.
3. The switch tries the next branch `Shipment(var id, var destination)`: `var destination` is an unconditional component pattern for the declared type `Address` and can bind a null value.
4. This branch returns the missing-address message. There is no NPE from a missing selector `case null`.

**Case C — the inner record exists, but a reference field inside it is null.**

~~~java
Object input = new Shipment("S-3", new Address(null));

String label = switch (input) {
    case Shipment(var id, Address(var city)) ->
        id + " đến " + (city == null ? "không rõ" : city);
    case Shipment(var id, var destination) ->
        id + " thiếu địa chỉ";
    case null -> "NULL";
    default -> "Khác";
};
System.out.println(label); // S-3 đến không rõ
~~~

The record pattern `Address(var city)` matches because the `Address` object exists. The variable `city` can receive null; the branch code itself must decide how to handle null before calling `city.length()` or `city.toUpperCase()`.

**In summary:** `case null` handles a null **selector**, not a "safety net" for **every component** of a record. Each place where data can be null must be evaluated separately.

## 8. `instanceof` and `switch` Differ on Null

Two seemingly similar expressions have different null rules:

~~~java
Object value = null;

boolean matched = value instanceof String text;
System.out.println(matched); // false
~~~

`instanceof String text` returns **false** when `value == null`; it does not throw an NPE just for checking the type. A record pattern in `instanceof` also does not match a null selector:

~~~java
boolean matchedRecord = value instanceof Shipment(var id, var destination);
// false, not NullPointerException due to null input value.
~~~

Conversely:

~~~java
String result = switch (value) {
    case String s -> s.toUpperCase();
    default -> "Khác";
};
// NPE due to null switch selector.
~~~

Therefore, you cannot infer from "`instanceof` is null-safe" that "a pattern switch doesn't need `case null`". Null-safety must be evaluated according to the **language construct being used**.

## 9. `when` Guards and Branch Ordering Do Not Solve a Missing Null Case

A guard only runs after the case pattern has matched:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "Chuỗi trắng";
        case String s -> "Text: " + s;
        default -> "Khác";
    };
}
~~~

- For null, enters `case null`; the guard `s.isBlank()` **does not run**.
- For `"   "`, the first `String` case matches and the guard is true, returning `"Chuỗi trắng"`.
- For `"Java"`, the guard is false, falling through to the second `String` case.
- For a non-`String` type, enters `default`.

If `case null` is omitted, guards like `when s == null` or `when value == null` **do not** make null match a String pattern. The NPE from a null selector still occurs. Handle null at the `case null` label or in a check before the switch.

Regarding ordering: place `case String s when s.isBlank()` **before** the unguarded `case String s`; placing the general case first causes a dominance error on the guarded case after it—a compile-time error distinct from a runtime NPE.

## 10. Traditional Switch with `String`, Enum, and Boxed Numbers

Pattern switches are not the only ones with this risk.

### 10.1. `String` Selector

~~~java
String status = null;

switch (status) {
    case "OPEN" -> System.out.println("Đang mở");
    default -> System.out.println("Không xác định");
}
// Missing case null, runtime: NullPointerException.
~~~

Fix when Java 21+ is available:

~~~java
switch (status) {
    case null -> System.out.println("Thiếu trạng thái");
    case "OPEN" -> System.out.println("Đang mở");
    default -> System.out.println("Không xác định");
}
~~~

### 10.2. Enum Selector

~~~java
enum Mode { ON, OFF }

static String name(Mode mode) {
    return switch (mode) {
        case ON -> "BẬT";
        case OFF -> "TẮT";
    };
}
~~~

Even though all enum constants are covered, calling `name(null)` still throws an NPE if there is no `case null`.

### 10.3. Primitive or Boxed Reference Selector?

A selector of primitive type `int` cannot hold null; with a switch on a plain `int`, there is no null selector case. However, a selector of type **`Integer`** (wrapper/reference) **can** be null:

~~~java
Integer number = null;

String label = switch (number) {
    case null -> "Không có số";
    case 0 -> "Zero";
    default -> "Khác";
};
~~~

Here `case null` allows handling a null wrapper. If code performs **unboxing** on `number` before entering the switch (for instance, computing `number.intValue()`), an NPE can occur right at that unboxing operation, before any switch case can handle it.

## 11. Complete Java 21+ Example and Output

Save as **`NullSwitchDemo.java`**:

~~~java
public class NullSwitchDemo {
    record Address(String city) {}
    record Shipment(String id, Address destination) {}

    sealed interface Message permits TextMessage, CountMessage {}
    record TextMessage(String text) implements Message {}
    record CountMessage(int count) implements Message {}

    enum Mode { ON, OFF }

    static String withoutNullCase(Object value) {
        return switch (value) {
            case String s -> "Text: " + s;
            default -> "Khác";
        };
    }

    static String withNullCase(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "Chuỗi trắng";
            case String s -> "Text: " + s;
            case Integer n -> "Số: " + n;
            case Shipment(var id, Address(var city)) ->
                    id + " đến " + (city == null ? "không rõ" : city);
            case Shipment(var id, var destination) ->
                    id + " thiếu địa chỉ";
            default -> "Kiểu khác";
        };
    }

    static String nullAndDefault(Object value) {
        return switch (value) {
            case String s -> "String: " + s;
            case null, default -> "Null hoặc kiểu khác";
        };
    }

    static String catchAllObject(Object value) {
        return switch (value) {
            case Object obj -> "Object: " + obj.getClass().getSimpleName();
        };
    }

    static String fromSealed(Message value) {
        return switch (value) {
            case TextMessage(var text) -> "Tin: " + text;
            case CountMessage(var count) -> "Đếm: " + count;
        };
    }

    static String modeNoNull(Mode value) {
        return switch (value) {
            case ON -> "BẬT";
            case OFF -> "TẮT";
        };
    }

    static String rejectNull(Object value) {
        return switch (value) {
            case null -> throw new IllegalArgumentException(
                    "value không được null");
            case String s -> "String: " + s;
            default -> "Khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(withNullCase(null));
        System.out.println(withNullCase("   "));
        System.out.println(withNullCase("Java"));
        System.out.println(withNullCase(42));
        System.out.println(withNullCase(
                new Shipment("S-1", new Address("Hà Nội"))));
        System.out.println(withNullCase(new Shipment("S-2", null)));
        System.out.println(withNullCase(
                new Shipment("S-3", new Address(null))));
        System.out.println(withNullCase(2.5));
        System.out.println(nullAndDefault(null));
        System.out.println(nullAndDefault(7));
        System.out.println(fromSealed(new CountMessage(3)));

        try {
            withoutNullCase(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: thiếu case null");
        }

        try {
            catchAllObject(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: Object pattern");
        }

        try {
            fromSealed(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: sealed exhaustive");
        }

        try {
            modeNoNull(null);
        } catch (NullPointerException e) {
            System.out.println("NPE: enum");
        }

        try {
            rejectNull(null);
        } catch (IllegalArgumentException e) {
            System.out.println("Đã từ chối: " + e.getMessage());
        }
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac --release 21 NullSwitchDemo.java
java NullSwitchDemo
~~~

Exact output:

~~~text
NULL
Chuỗi trắng
Text: Java
Số: 42
S-1 đến Hà Nội
S-2 thiếu địa chỉ
S-3 đến không rõ
Kiểu khác
Null hoặc kiểu khác
Null hoặc kiểu khác
Đếm: 3
NPE: thiếu case null
NPE: Object pattern
NPE: sealed exhaustive
NPE: enum
Đã từ chối: value không được null
~~~

Key cases:

1. `withNullCase(null)` returns `"NULL"` because it has a null label.
2. The guard `when s.isBlank()` applies when the object is actually a String; null is not passed into the guard.
3. The nested record `Address(var city)` does not match if the **`Address` component** is null; the `Shipment(..., var destination)` branch handles that case.
4. An existing `Address` with `city == null` can still match the nested record pattern and be handled directly in the branch.
5. `case null, default` groups null and non-String values into a single response.
6. `catchAllObject(null)` still throws NPE even though `Object` is a very broad type.
7. `fromSealed(null)` still throws NPE even though the switch is exhaustive over all subtypes of the sealed interface.
8. `modeNoNull(null)` still throws NPE even though both enum constants are handled.
9. `rejectNull(null)` intentionally throws `IllegalArgumentException` with a contract message, instead of an implicit NPE.

The `catch` blocks in `main` are only to let the demo program continue and observe each error scenario; in real applications, do not catch every NPE and silently ignore it.

## 12. Debugging Checklist: Where Did the NPE Actually Come From?

When a `NullPointerException` appears in the logs near a `switch`, check in order:

1. **Is the selector value null?** Find the source: method return, map lookup, nullable JSON/DB field, wrapper, or external input.
2. **Is `case null` present?** Do not confuse `default`, `case Object obj`, or exhaustiveness with null handling.
3. **Did the NPE occur before the switch received the selector?** For example, calling `dto.status()` when `dto == null`, or unboxing a null `Integer`.
4. **Did the NPE actually come from code inside a branch?** When the selector is non-null, a field or component used in the case can still be null; check accesses like `city.toUpperCase()`, `address.city()`, and similar.
5. **Did a nested record pattern fail to match because of null?** Nested record patterns do not match null; consider a general record branch and handle null components explicitly.
6. **Does null have domain meaning?** If yes, write `case null` returning a valid value; if not, reject null at the API boundary with a clear message.
7. **Is the policy tested?** Write tests for null selectors, other types, records with null components, null enums/wrappers, and guards.

Example of a function receiving data from the persistence layer:

~~~java
static String statusLabel(String status) {
    return switch (status) {
        case null -> "Chưa thiết lập";
        case "NEW" -> "Mới";
        case "DONE" -> "Hoàn thành";
        default -> "Trạng thái không hỗ trợ";
    };
}
~~~

If null means "invalid data that must not be stored", replace `case null -> "Chưa thiết lập"` with `case null -> throw new IllegalArgumentException(...)`. Do not automatically assign "not set" if the domain requires this field to be mandatory.

## 13. Common Mistakes and Fixes

| Misconception | Consequence | Solution |
| --- | --- | --- |
| `default` catches everything, including null | Null selector throws NPE | Add `case null` or check before the switch |
| `case Object o` matches null | NPE even though the pattern covers all non-nulls | Handle `case null` separately |
| Exhaustive switch on a sealed interface cannot cause NPE | Null selector still causes NPE | Distinguish exhaustiveness from null-safety |
| Enum switch covering all constants also accepts null | Null enum reference still throws NPE | Have an explicit null policy |
| `case null, String s` is how to combine null with String | Compile error `invalid case label combination` | Write separate cases or `case null, default` |
| Guard `when s == null` will catch a null selector | No String pattern match occurs, switch still throws NPE | `case null` |
| `case null` automatically protects all record fields | Can still throw NPE when operating on a null component | Check null on each component |
| `instanceof` null returns false, so pattern switch does too | The two constructs have different rules | Treat a null switch selector as a separate case |
| Just use `try/catch (NullPointerException)` to handle it | May hide bugs inside a branch or before the switch | Validate input, `case null`, and root cause |
| Add `default` to every switch to avoid exceptions | Does not handle null and may hide missing new subtypes | Leverage exhaustiveness, handle null in the right place |

## 14. Exercises and Guided Answers

**Exercise 1.** Why does the following snippet throw an NPE? Fix it in two different ways: (a) null returns `"empty"`, (b) null is rejected with `IllegalArgumentException`.

~~~java
static String test(Object value) {
    return switch (value) {
        case String s -> s.toUpperCase();
        default -> "unknown";
    };
}
~~~

**Exercise 2.** Given `sealed interface Command permits Create, Delete {}`, the compiler accepts a switch covering both subtypes with no `default`. If the selector is null, what happens? Why does that not contradict exhaustiveness?

**Exercise 3.** Given `record Address(String city) {}` and `record Shipment(String id, Address destination) {}`. Write a switch expression that separately handles a null selector, a shipment with `destination == null`, and a shipment with `destination.city() == null` without throwing an NPE.

**Exercise 4.** Does `case null, String s -> ...` compile in Java 21? Write a valid alternative branch so that null and non-String types produce the same result.

**Exercise 5.** Compare these two expressions:

~~~java
Object value = null;
boolean first = value instanceof String s;

String second = switch (value) {
    case String s -> s;
    default -> "other";
};
~~~

What is the value of `first`? Does `second` receive `"other"`?

**Suggested Answers:**

~~~java
// Exercise 1(a):
static String safe(Object value) {
    return switch (value) {
        case null -> "empty";
        case String s -> s.toUpperCase();
        default -> "unknown";
    };
}

// Exercise 1(b):
static String strict(Object value) {
    return switch (value) {
        case null -> throw new IllegalArgumentException("value null");
        case String s -> s.toUpperCase();
        default -> "unknown";
    };
}

// Exercise 4: null and non-String cases share the same branch.
static String grouped(Object value) {
    return switch (value) {
        case String s -> s;
        case null, default -> "fallback";
    };
}
~~~

Exercise 2: still throws NPE because a null selector requires an explicit policy. Exercise 3: use `case null`, nested `Shipment(var id, Address(var city))` with handling for `city == null`, and `Shipment(var id, var destination)` as the fallback branch. Exercise 5: `first == false`, whereas the switch throws an NPE when evaluating `second` before any value can be assigned.

## Summary

For a **`switch` on a reference selector**, treat `null` as a data contract decision:

- **Null is valid:** use `case null -> ...` (or `case null, default -> ...` if the two cases are genuinely equivalent).
- **Null is invalid:** reject explicitly with `case null -> throw ...` or validate right at the boundary.
- **Missing `case null`:** a null selector makes the switch throw NPE, regardless of `default`, `case Object`, or having covered all subtypes of a sealed hierarchy.
- **Null in components/fields:** must be checked along each access path; `case null` only handles the **selector**.

## References

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): sections on **Null case Labels**, dominance, exhaustive pattern switches, and record patterns.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch rules and stabilized null handling in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns and nested component matching.
- [JLS 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11) and [§15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
