# Optional.empty(), Optional.of(), and Optional.ofNullable() in Java

`java.util.Optional<T>` is a **container object that may or may not contain a non-`null` value**. Optional helps an API clearly express that a result may be absent, instead of forcing the caller to infer it from a `null` return value. The three most important static factory methods for creating an Optional are **`empty()`**, **`of(value)`**, and **`ofNullable(value)`**.

Choosing the right factory is especially important when data comes from a database, configuration, map, API response, or legacy method that may return `null`. All three methods can produce an `Optional<T>`, but their **`null`-handling policies are completely different**.

After this lesson, you will be able to:
- Create an empty Optional, a present Optional, and a potentially empty Optional from nullable input.
- Know the exact moment when `Optional.of(null)` throws `NullPointerException`.
- Distinguish an Optional that **contains no value** from an Optional containing `""`, `0`, `false`, or an empty collection.
- Use generics and target typing to create `Optional<T>` clearly.
- Choose the appropriate factory when designing APIs, avoiding null Optionals, nested Optionals, and unsafe access operations.

## 1. What does Optional represent?

Consider two cases:

```java
Optional<String> found = Optional.of("Java");
Optional<String> missing = Optional.empty();
```

This is an **illustrative code snippet** that requires `import java.util.Optional;` and belongs inside a suitable method or initializer.

- `found` **is present** with a `String` whose content is `"Java"`.
- `missing` **has no value**.
- `Optional<String>` does not allow the state "an Optional is present, but the element inside is `null`". For `null`, use `ofNullable` to create an **empty** Optional.
- `Optional` is a reference type. A **variable** of type `Optional<T>` itself can still be assigned `null` if you intentionally do so; that is a state to avoid.

Think of Optional as a two-branch result: **present** or **absent**. It does not state the reason for absence on its own, does not replace every error model, and does not guarantee that the inner value is valid according to custom business rules.

## 2. Quick comparison of the three factory methods

| Factory | Input | If value is non-null | If value is null | Use when |
| --- | --- | --- | --- | --- |
| `Optional.empty()` | No arguments | Not applicable | Not applicable | You know for sure the result is absent. |
| `Optional.of(value)` | A required non-null value | **Present** Optional | **Throws `NullPointerException` immediately** | The value must always exist by contract. |
| `Optional.ofNullable(value)` | A nullable value | **Present** Optional | **Empty** Optional | Data comes from a nullable source or may be absent. |

All three are **static methods** on the `Optional` class, typically called as `Optional.empty()`, `Optional.of(...)`, and `Optional.ofNullable(...)`. Do not use `new Optional<>()`: Optional does not provide a public constructor for direct instantiation that way.

### Rule of thumb

- **Know there is no data** → `empty()`.
- **Have data and do not allow null** → `of(value)`.
- **Not sure whether data is null or not** → `ofNullable(value)`.

Do not use `ofNullable` to hide a contract-violating null error if the API must reject null. When null is a programming bug that needs to be caught early, `of` is more appropriate.

## 3. Optional.empty(): creating an absent result

`Optional.empty()` creates an Optional **containing no value**. For example:

```java
Optional<String> noName = Optional.empty();
Optional<Integer> noAge = Optional.empty();

boolean missingName = noName.isEmpty();  // true
boolean hasAge = noAge.isPresent();       // false
```

This is an illustrative code snippet and requires importing `java.util.Optional`. `isEmpty()` has been available since Java 11; JDK 17 fully supports it. `isPresent()` returns true only when a value is present; `isEmpty()` returns true only when absent.

### Generic type of empty()

`empty()` is a static generic method with the conceptual signature:

```java
public static <T> Optional<T> empty()
```

When you write `Optional<String> noName = Optional.empty();`, Java uses the target type on the left-hand side to infer `T` as `String`. If you need to make it explicit in another context, you can write:

```java
Optional<String> none = Optional.<String>empty();
```

The `<String>` after the class name is a **type witness**, specifying the type parameter `T` for the generic method call. Both ways create an Optional with no value, not a `null` value of `String`.

**Identity note:** Optional is a **value-based class**. Do not use `==`, `System.identityHashCode`, synchronization locks on Optional, or assume that every call to `empty()` must return the exact same instance. Check state using `isEmpty()` or compare semantics using `equals` when appropriate.

## 4. Optional.of(value): rejecting null at creation time

`Optional.of(value)` is used when the value **must be non-null**:

```java
Optional<String> language = Optional.of("Java");
Optional<Integer> quantity = Optional.of(0);
Optional<Boolean> enabled = Optional.of(false);
```

Both `0` and `false` are autoboxed into `Integer` and `Boolean` respectively and are **present values**. Similarly, `Optional.of("")` contains an empty string, so the Optional is still **present**.

An explicitly marked invalid example:

```java
// INTENTIONALLY CAUSES A RUNTIME EXCEPTION:
Optional<String> invalid = Optional.of(null);
// Throws NullPointerException immediately at the of(null) call.
```

The call `of(null)` can still **compile** in a validly typed context, but it does not create an empty Optional: it throws `NullPointerException`. No Optional object is returned from that failed call.

This can be the **intended behavior by design** if the data is required to exist: the error is detected right where the contract is violated instead of silently turning into "not found".

## 5. Optional.ofNullable(value): converting null to empty

When a data source may return `null`, `Optional.ofNullable(value)` helps represent both cases:

```java
String found = "Kotlin";
String absent = null;

Optional<String> a = Optional.ofNullable(found);  // contains "Kotlin"
Optional<String> b = Optional.ofNullable(absent); // empty
```

`ofNullable` is functionally equivalent in result to the following logic, but clearer and more concise:

```java
static <T> Optional<T> fromNullable(T value) {
    return value == null ? Optional.empty() : Optional.of(value);
}
```

The second snippet is a standalone demo method; in normal application code, you should call the standard API `Optional.ofNullable(value)` instead of redefining it.

Data sources that commonly have the potential to be null:
- `Map.get(key)` if the key is not in the map, or has a null value mapping in implementations that allow it.
- Legacy methods declared to return `String`, `User`, etc. that may return null.
- Optional parameters from a layer interacting with an old library.
- Results from an external API with a convention that "null means no data".

**Important:** an `Optional.empty()` created from `Map.get(key)` cannot distinguish between "key does not exist" and "key exists but its value is null". If business logic needs to distinguish them, check `containsKey` or use a more detailed result type.

## 6. Java 17 program: directly comparing the three factories

Create the file **`OptionalFactoriesDemo.java`**:

```java
import java.util.Optional;

public class OptionalFactoriesDemo {
    public static void main(String[] args) {
        Optional<String> empty = Optional.empty();
        Optional<String> strict = Optional.of("Java");
        Optional<String> nullableMissing = Optional.ofNullable(null);
        Optional<String> nullableValue = Optional.ofNullable("Kotlin");

        Optional<String> blankString = Optional.of("");
        Optional<Integer> zero = Optional.of(0);
        Optional<Boolean> disabled = Optional.of(false);

        System.out.println("empty present=" + empty.isPresent());
        System.out.println("of value=" + strict.orElse("fallback"));
        System.out.println("nullable(null) empty=" + nullableMissing.isEmpty());
        System.out.println("nullable(value)=" + nullableValue.orElse("fallback"));
        System.out.println("empty string present=" + blankString.isPresent());
        System.out.println("zero present=" + zero.isPresent());
        System.out.println("false present=" + disabled.isPresent());
        System.out.println("same empty meaning=" + empty.equals(nullableMissing));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 OptionalFactoriesDemo.java
java OptionalFactoriesDemo
```

**Exact stdout:**

```text
empty present=false
of value=Java
nullable(null) empty=true
nullable(value)=Kotlin
empty string present=true
zero present=true
false present=true
same empty meaning=true
```

Explanation:
1. `empty` and `nullableMissing` both have no value despite being created differently.
2. `strict` and `nullableValue` contain a non-null `String`.
3. The string `""`, the number `0`, and the boolean `false` **are not synonymous with absence**.
4. `equals` compares the semantics of Optional; do not use `==` to compare two empty Optionals.

The `orElse("fallback")` method in the example only provides a default value if the Optional is empty; it does not mutate the original Optional.

## 7. Java 17 program: how do of(null) and ofNullable(null) differ?

Save as **`OptionalNullDemo.java`**:

```java
import java.util.Optional;

public class OptionalNullDemo {
    static Optional<String> strict(String input) {
        return Optional.of(input);
    }

    static Optional<String> tolerant(String input) {
        return Optional.ofNullable(input);
    }

    public static void main(String[] args) {
        System.out.println("of(Java) present=" + strict("Java").isPresent());
        System.out.println("ofNullable(null) empty=" + tolerant(null).isEmpty());

        try {
            strict(null);
            System.out.println("Không chạy tới đây");
        } catch (NullPointerException ex) {
            System.out.println("of(null): NullPointerException");
        }

        Optional<String> noValue = Optional.empty();
        System.out.println("empty fallback=" + noValue.orElse("anonymous"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 OptionalNullDemo.java
java OptionalNullDemo
```

**Exact stdout:**

```text
of(Java) present=true
ofNullable(null) empty=true
of(null): NullPointerException
empty fallback=anonymous
```

In `strict(null)`, `Optional.of(input)` throws an error before the method returns an Optional. The program catches `NullPointerException` for illustration, so the next line in the `try` block is not printed. `tolerant(null)`, on the other hand, returns `Optional.empty()` without throwing an error.

**Do not catch `NullPointerException` to turn every error into an empty Optional.** The example only illustrates the difference between the two factories. In real applications, choose `ofNullable` when null is a valid possibility, and `of` when null violates the contract.

## 8. API design: returning Optional instead of returning null

Suppose a small repository returns `null` if a name is not found:

```java
static String legacyFindName(java.util.Map<String, String> names, String id) {
    return names.get(id); // may be null
}
```

To make the new API explicitly express the possibility of absence:

```java
static Optional<String> findName(java.util.Map<String, String> names,
                                 String id) {
    return Optional.ofNullable(names.get(id));
}
```

These two snippets are method declaration fragments; they require importing `java.util.Optional` or using the fully qualified name. The caller does not need to manually check for null before using the container:

```java
String display = findName(names, "unknown").orElse("Ẩn danh");
```

In this example, `names` is an existing `Map<String,String>`. `ofNullable` is an appropriate choice at the boundary with an API that may return null; conversely, you should not unconditionally use `ofNullable` for a method where `null` is a serious error that needs to be detected.

### When the API itself knows for sure there is no data

```java
static Optional<String> lookup(boolean available) {
    if (!available) {
        return Optional.empty();
    }
    return Optional.of("Java");
}
```

Use `empty()` as soon as a conditional branch determines that the value is absent. Use `of("Java")` in the branch where you know for sure the value must exist. There is no need to create an intermediate null variable just to call `ofNullable`.

## 9. Java 17 example: using Optional with Map and further operations

Create the file **`OptionalLookupDemo.java`**:

```java
import java.util.Map;
import java.util.Optional;

public class OptionalLookupDemo {
    static Optional<String> findName(Map<String, String> names, String id) {
        return Optional.ofNullable(names.get(id));
    }

    public static void main(String[] args) {
        Map<String, String> names = Map.of(
                "u1", "Lan",
                "u2", "Mai"
        );

        Optional<String> found = findName(names, "u1");
        Optional<String> missing = findName(names, "u9");

        System.out.println("found=" + found.orElse("Ẩn danh"));
        System.out.println("missing=" + missing.orElse("Ẩn danh"));
        System.out.println("found present=" + found.isPresent());
        System.out.println("missing empty=" + missing.isEmpty());

        String upper = found.map(String::toUpperCase)
                .orElse("UNKNOWN");
        System.out.println("upper=" + upper);
    }
}
```

Compile/run with JDK 17:

```bash
javac -encoding UTF-8 OptionalLookupDemo.java
java OptionalLookupDemo
```

**Exact stdout:**

```text
found=Lan
missing=Ẩn danh
found present=true
missing empty=true
upper=LAN
```

`findName` wraps the result of `Map.get` with `ofNullable`. When the key has a value, the Optional is present; when the key is missing, the Optional is empty. `map(String::toUpperCase)` only performs the transformation when there is a value inside; if empty, the result remains empty. `orElse` at the end receives the default value.

`Map.of` creates a map that does not allow null keys or values. This example uses valid input and a missing key for illustration; with other Map implementations that can store null values, `findName` will collapse both "key not present" and "null value" into an empty Optional.

## 10. Reading Optional results safely

After creating an Optional, callers often want to continue processing the value or use a default. Some important APIs:

| API | When present | When empty |
| --- | --- | --- |
| `isPresent()` | `true` | `false` |
| `isEmpty()` | `false` | `true` |
| `ifPresent(consumer)` | Executes the action | Does nothing |
| `map(function)` | Transforms the value, wraps nullable result into Optional | Remains empty |
| `filter(predicate)` | Keeps the value if the condition is true | Remains empty |
| `orElse(value)` | Returns the present value | Returns the fallback |
| `orElseGet(supplier)` | Returns the present value | Calls the supplier to create the fallback |
| `orElseThrow()` | Returns the present value | Throws `NoSuchElementException` |

You can call `get()` on a present Optional, but calling `get()` when empty throws `NoSuchElementException`. In most application logic, consider `orElse`, `orElseGet`, `ifPresent`, `map`, `flatMap`, or `orElseThrow` with appropriate conditions and messages, instead of unnecessarily repeating the `isPresent()` followed by `get()` pattern.

Do not treat an empty Optional as an exception. **`empty()` and `ofNullable(null)` do not throw exceptions**; exceptions only occur if you perform a disallowed operation such as `get()` on an empty Optional or use `of(null)`.

### Difference between orElse and orElseGet

If the fallback is expensive or has side effects, `orElseGet` is useful because it only calls the supplier when the Optional is empty. Conversely, **the argument expression of `orElse` is evaluated eagerly according to Java rules**, even when the Optional is present.

Example:

```java
static String createFallback() {
    System.out.println("Tạo fallback");
    return "ẩn danh";
}

// Inside a method:
Optional<String> present = Optional.of("Lan");
String a = present.orElse(createFallback()); // still prints "Tạo fallback"
String b = present.orElseGet(() -> createFallback()); // does not print
```

These are illustrative code snippets, not a complete Java file. While the choice of Optional factory determines the present/empty state, choosing `orElse` or `orElseGet` determines **how the fallback is evaluated**.

## 11. Common points of confusion regarding generics, null, and empty

### 11.1. Optional.empty() is not null

```java
Optional<String> empty = Optional.empty();
Optional<String> invalid = null; // not recommended
```

The second line is valid in terms of Java typing, but it defeats the purpose of an Optional-returning API: the caller can hit a `NullPointerException` immediately when calling `invalid.isEmpty()`. A method declared to return `Optional<T>` should return a **non-null** Optional object, using `Optional.empty()` if there is no data.

### 11.2. Optional.of("") differs from Optional.empty()

```java
Optional<String> blank = Optional.of("");
Optional<String> missing = Optional.empty();

boolean a = blank.isPresent();  // true
boolean b = missing.isPresent(); // false
```

An empty string `""` is still a non-null `String`. Similarly, `Optional.ofNullable("")` is still **present**. If business rules treat an empty string or a whitespace-only string as "no data", you need to **normalize or filter explicitly**, for example:

```java
Optional<String> normalized = Optional.ofNullable(input)
        .map(String::strip)
        .filter(value -> !value.isEmpty());
```

This is an illustrative snippet with a `String` variable `input` from context. With null, the result is empty; with `"   "`, after `strip()` and `filter`, it is also empty; with `" Java "`, the result contains `"Java"`.

### 11.3. Optional.ofNullable(Optional<T>) creates a nested Optional

Example:

```java
Optional<String> inner = Optional.of("Java");
Optional<Optional<String>> nested = Optional.ofNullable(inner);
```

`nested` is `Optional<Optional<String>>`, not `Optional<String>`. `ofNullable` wraps **the exact object passed in** when that object is non-null; it does not automatically "flatten" an Optional. If a transformation already returns an Optional, consider `flatMap` instead of `map` in an appropriate pipeline.

### 11.4. Optional<Integer> and OptionalInt

`Optional<T>` uses a generic reference type, so `Optional<Integer>` wraps `Integer`:

```java
Optional<Integer> number = Optional.of(7);
java.util.OptionalInt primitive = java.util.OptionalInt.of(7);
java.util.OptionalInt noPrimitive = java.util.OptionalInt.empty();
```

`OptionalInt`, `OptionalLong`, and `OptionalDouble` are specialized forms for primitives. They have `of` and `empty`, but **do not have a corresponding static `ofNullable`**. If the original source is a nullable `Integer` and you want an `OptionalInt`, you must convert it conditionally.

## 12. Choosing a factory by API contract, not just syntax

| Situation | Choice | Explanation |
| --- | --- | --- |
| No result found | `Optional.empty()` | The absent state is already determined. |
| Hard-coded value guaranteed non-null | `Optional.of("Java")` | If the value were null, it would be a contract error. |
| `Map.get(key)` may be null | `Optional.ofNullable(map.get(key))` | Converts null into absence. |
| Nullable legacy method | `Optional.ofNullable(legacy())` | Expresses a contract that returns a potentially missing result. |
| Required value, null is an error | `Optional.of(required)` | Fail-fast at the point of Optional creation. |
| String `""` is a valid value | `Optional.of("")` or `ofNullable("")` | The Optional is still present. |
| Whitespace string is treated as no data | `ofNullable(...).map(...).filter(...)` | Requires business rules beyond a null check. |

Some design principles:
- In Java APIs, Optional is usually suitable as a **return type** when a method may not find a result. It is not necessary to replace every parameter or field with Optional.
- Optional is not a storage, synchronization, or caching mechanism. It is a way to express the possibility of absence at the API level.
- If you need to distinguish multiple failure reasons, use an enum/record result or a more detailed result type; an empty Optional does not contain cause information.
- There is no need to call `Optional.ofNullable` in every situation just "to be safe": a contract-violating null should be detected clearly rather than hidden.

## 13. Common mistakes

1. **Using `Optional.of(null)` to create an empty Optional:** wrong, the method throws `NullPointerException`.
2. **Returning `null` from a method with return type `Optional<T>`:** deprives the caller of a consistent handling mechanism.
3. **Confusing `Optional.empty()` with `Optional.of("")`:** having an empty string value does not mean having no value.
4. **Using `==` to compare two Optionals:** Optional is a value-based class; use `equals` or check state.
5. **Calling `get()` when not sure a value is present:** an empty Optional causes `NoSuchElementException`.
6. **Using `ofNullable` to hide contract-violating null errors:** can turn a serious bug into "not found".
7. **Assuming `ofNullable(value)` checks for empty strings:** it only checks for **null**, not `""` or whitespace.
8. **Putting an Optional inside an Optional:** `Optional.of(innerOptional)` creates `Optional<Optional<T>>`.
9. **Using `Optional<Integer>` as a primitive:** it still uses the `Integer` wrapper; consider `OptionalInt` when appropriate.
10. **Confusing `orElse` with `orElseGet`:** the `orElse` argument is evaluated before the call, whereas the `orElseGet` supplier only runs when empty.
11. **Assuming Optional holds null inside:** standard factories only create an Optional with a **non-null value** or an empty Optional.
12. **Wrapping nullable data without describing its semantics:** API users need to know whether null means "not found", "not loaded yet", or an error to handle.

## 14. Self-check

**Question 1.** Choose the factory to create an Optional guaranteed to contain no value.

**Answer:** `Optional.empty()`.

**Question 2.** What does `Optional.of(null)` result in?

**Answer:** Throws `NullPointerException` immediately upon executing the call; does not return `Optional.empty()`.

**Question 3.** What does `Optional.ofNullable(null).isEmpty()` return?

**Answer:** `true`, because null is converted into an empty Optional.

**Question 4.** What do `Optional.of("").isPresent()` and `Optional.of(0).isPresent()` return?

**Answer:** Both return `true`. An empty string and the number 0 are not null.

**Question 5.** The method `String find(String key)` may return null. If you want the caller to see the possibility of absence through the return type, how should you write it?

```java
static Optional<String> findOptional(String key) {
    return Optional.ofNullable(find(key));
}
```

This is a snippet inside a class that already has the `find(String)` method. Choose `ofNullable` because null is a possible outcome.

**Question 6.** When should you use `of` instead of `ofNullable`?

**Answer:** When `null` must be treated as a data contract violation and needs to **fail-fast** with `NullPointerException`.

**Question 7.** Should you write `optional == Optional.empty()` to check for absence?

**No.** Use `optional.isEmpty()` (Java 11+) or `!optional.isPresent()`.

**Question 8.** What does `Optional.ofNullable("  ").isEmpty()` return?

**Answer:** `false`, because `"  "` is a non-null string. If you want to treat whitespace as no data, you need separate `strip`/`filter` rules.

**Remember:** **`empty()` = intentionally no value; `of(x)` = value required, null causes an error; `ofNullable(x)` = present if x is non-null, empty if x is null.** Choose the factory according to the data contract rather than by habit.
