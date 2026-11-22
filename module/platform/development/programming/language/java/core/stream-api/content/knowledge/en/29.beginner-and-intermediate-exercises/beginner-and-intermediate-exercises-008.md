# Handling Empty Sources, `null`, and Absent Search Results

## 1. Series Objectives

In the **Beginner and Intermediate Exercises** chapter of **JAVA_STREAM_API**, you have learned to build declarative pipelines using `filter`, `map`, `reduce`, `collect`, and search terminal operations. Real-world data, however, is rarely complete: sources may be empty, list references may be `null`, elements inside a list may be `null`, object fields may be missing, or no element may satisfy a search predicate.

This lesson builds the skill of **writing pipelines that handle missing data with clear semantics**, rather than merely keeping code from throwing exceptions. After practicing, you will be able to:

- Distinguish an **empty Stream**, a **`null` source reference**, a **`null` element**, and **`Optional.empty()`**.
- Choose the right policy: skip missing data, return a default, preserve absence, or fail fast.
- Use `Objects::nonNull`, `Stream.ofNullable`, `Optional.ofNullable`, and `Optional.stream` appropriately.
- Handle `findFirst`, `findAny`, `min`, `max`, `average`, and `reduce` on empty sources.
- Avoid `null`-related errors with `Collectors.toUnmodifiableList`, `toMap`, and `groupingBy`.
- Design small, testable programs that behave predictably on incomplete inputs.

Solutions target **Java 17+**. `Stream.ofNullable` and `Optional.stream` arrived in Java 9; `Stream.toList()` arrived in Java 16. Most examples use sequential streams for clarity, followed by parallel considerations.

### Four Situations That Must Not Be Conflated

| Situation | Example | Meaning | Typical Risk |
| --- | --- | --- | --- |
| **Empty source** | `List.<String>of().stream()` | Valid source containing zero elements | `findFirst()` returns `Optional.empty()` |
| **`null` source reference** | `List<String> names = null` | No source object exists | `names.stream()` throws `NullPointerException` |
| **`null` element** | `Arrays.asList("A", null)` | Source exists; one element has no value | `map(String::trim)` can throw NPE |
| **Absent search result** | `stream.filter(...).findFirst()` | No matching element found | `Optional.get()` throws `NoSuchElementException` if empty |

Diagram:

~~~text
Input
  ├─ source == null ──────────► fail fast OR treat as empty source
  └─ source != null
       │
       ▼
     stream()
       │
       ├─ null element? ──────► filter / ofNullable / fail fast
       └─ valid elements
             │
             ▼
        filter / map / ...
             │
             ├─ no elements left ──────► Empty Stream
             │                              │
             │                              ▼
             │                        Optional.empty()
             │
             └─ element found ─────────► Optional holding value
                                            │
                                orElse / orElseGet / orElseThrow
~~~

**Presentation convention:** Each exercise includes **Requirement**, **Solution**, and **Explanation and Edge Cases**. Short snippets reuse variables defined just above them; programs with a `public class` are standalone and can be saved in a matching file to compile with `javac`.

## 2. Background: Terminal Operations on an Empty Stream

Before tackling the exercises, predict these outputs:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class EmptyStreamBasics {
    public static void main(String[] args) {
        Stream<String> empty = Stream.empty();
        System.out.println(empty.count()); // 0

        System.out.println(List.<String>of().stream().toList()); // []
        System.out.println(List.<String>of().stream().findFirst()); // Optional.empty
        System.out.println(List.<String>of().stream().reduce(String::concat));
        // Optional.empty

        System.out.println(IntStream.empty().sum()); // 0
        System.out.println(IntStream.empty().average()); // OptionalDouble.empty
    }
}
~~~

Never reuse a Stream after invoking a terminal operation. Each call above opens a new Stream for its expression.

| Terminal Operation | Empty Source Return | Notes |
| --- | --- | --- |
| `count()` | `0L` | No Optional needed |
| `toList()` | Empty List | List from `Stream.toList()` is unmodifiable |
| `collect(Collectors.toList())` | Empty List | Does not guarantee exact List class/mutability |
| `findFirst()` or `findAny()` | `Optional.empty()` | Do not call `get()` directly |
| `min(comparator)` / `max(comparator)` | `Optional.empty()` | No elements to compare |
| `reduce(operator)` | `Optional.empty()` | Overload without identity |
| `reduce(identity, op)` | `identity` | Must supply a valid identity |
| `IntStream.sum()` | `0` | Can still overflow on large inputs |
| `IntStream.average()` | `OptionalDouble.empty()` | Do not confuse with a 0 average |
| `anyMatch(predicate)` | `false` | No matching element exists |
| `allMatch(predicate)` | `true` | Holds by propositional logic on empty sets |
| `noneMatch(predicate)` | `true` | No element violates the predicate |

`allMatch` and `noneMatch` returning `true` on an empty source is not a bug; it is *vacuous truth*. If business rules require **at least one element** to be present, check non-emptiness explicitly.

## 3. Exercise 1 — `null` List Reference vs. Empty List

**Level:** Beginner.

**Requirement:** Write `normalize(List<String> source)` returning a list of names with leading and trailing whitespace stripped. Exercise rule: if the source reference is `null`, treat it as **no data** and return an empty list. If the List is non-null but empty, also return an empty list. This exercise assumes **elements themselves are non-null**; Exercise 2 handles null elements.

**Solution:**

~~~java
import java.util.List;
import java.util.Optional;

public class NullListExercise {
    static List<String> normalize(List<String> source) {
        return Optional.ofNullable(source)
            .orElseGet(List::of)
            .stream()
            .map(String::strip)
            .toList();
    }

    public static void main(String[] args) {
        System.out.println(normalize(null)); // []
        System.out.println(normalize(List.of())); // []
        System.out.println(normalize(List.of(" An ", " Bình ")));
        // [An, Bình]
    }
}
~~~

**Explanation:**

- `Optional.ofNullable(source)` returns `Optional.empty()` when `source` is `null`.
- `orElseGet(List::of)` supplies an empty List when the source is absent.
- `stream()` traverses the valid list.
- `map(String::strip)` cleans each name.
- `toList()` returns an unmodifiable List preserving the input List's encounter order.

**Edge case:** if an element inside the list is `null`, `String::strip` still throws `NullPointerException`. Do not assume checking `source != null` guards against null elements.

### When Should a `null` Source Not Be Treated as Empty?

In production systems, `null` may signify **an integration failure, missing required input, or unloaded data**. If that is the contract, fail explicitly instead of silently returning an empty list:

~~~java
import java.util.List;
import java.util.Objects;

static List<String> normalizeStrict(List<String> source) {
    Objects.requireNonNull(source, "source must not be null");
    return source.stream().map(String::strip).toList();
}
~~~

This is an **alternative policy**, not the single answer for every problem. Decide based on the input contract.

## 4. Exercise 2 — Filtering `null` Elements Before Calling Methods

**Level:** Beginner.

**Requirement:** A list from a legacy system may contain `null` elements. Clean the names, drop null and blank/empty names, and convert to uppercase for display. Preserve original order.

**Solution:**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class NullableElementsExercise {
    public static void main(String[] args) {
        List<String> raw = Arrays.asList(
            " an ", null, "", "   ", " Bình ", "chi"
        );

        List<String> cleaned = raw.stream()
            .filter(Objects::nonNull)
            .map(String::strip)
            .filter(name -> !name.isEmpty())
            .map(name -> name.toUpperCase(Locale.ROOT))
            .toList();

        System.out.println(cleaned); // [AN, BÌNH, CHI]
    }
}
~~~

**Explanation and edge cases:**

- `Arrays.asList(...)` allows `null`; `List.of(...)` **forbids** null elements.
- `filter(Objects::nonNull)` must come **before** `String::strip`.
- `String::strip` removes leading/trailing whitespace using Java's Unicode whitespace definition.
- `filter(name -> !name.isEmpty())` removes strings that became empty after stripping.
- `Locale.ROOT` avoids machine-locale-dependent uppercasing.
- `toList()` preserves the order of remaining elements when the source has encounter order.

**Common mistake:**

~~~java
// Wrong order: String::strip receives null and throws NPE.
// raw.stream().map(String::strip).filter(Objects::nonNull).toList();
~~~

Putting `filter` after `map` is **too late** if the method inside `map` has already been invoked on `null`.

## 5. Exercise 3 — Distinguishing `Stream.ofNullable` and `Stream.of`

**Level:** Beginner.

**Requirement:** Given a `String` that may be `null`, create a Stream containing **0 or 1 non-null elements** for further processing. Compare with `Stream.of(...)`.

**Solution:**

~~~java
import java.util.List;
import java.util.stream.Stream;

public class OfNullableExercise {
    public static void main(String[] args) {
        String missing = null;
        String present = "Java";

        List<String> a = Stream.ofNullable(missing).toList();
        List<String> b = Stream.ofNullable(present).toList();

        System.out.println(a); // []
        System.out.println(b); // [Java]

        // Contains one null element (not an empty Stream):
        List<String> c = Stream.of((String) null).toList();
        System.out.println(c); // [null]

        System.out.println(Stream.ofNullable(null).count()); // 0
        System.out.println(Stream.of((String) null).count()); // 1
    }
}
~~~

`Stream.ofNullable(x)` (Java 9+) returns an empty Stream when `x == null`; otherwise it returns a single-element Stream. `Stream.of((String) null)`, by contrast, produces a Stream with **one null element**. Casting `(String) null` makes the single-argument overload explicit and avoids varargs ambiguity.

### When an Object Field May Be `null`

~~~java
import java.util.List;
import java.util.stream.Stream;

record Customer(String id, String email) {}

List<Customer> customers = List.of(
    new Customer("C1", "a@example.com"),
    new Customer("C2", null),
    new Customer("C3", "b@example.com")
);

List<String> emails = customers.stream()
    .flatMap(c -> Stream.ofNullable(c.email()))
    .toList();

System.out.println(emails); // [a@example.com, b@example.com]
~~~

`flatMap` flattens the 0/1-element Streams into a single email Stream. An equivalent alternative, often shorter when the field is already mapped to `String`:

~~~java
List<String> emails = customers.stream()
    .map(Customer::email)
    .filter(java.util.Objects::nonNull)
    .toList();
~~~

**Distinction:** `Stream.ofNullable` handles **one nullable value**; it does not protect against a `null` source list or a `null` `Customer` element. If both can happen, combine this with Exercises 1 and 2.

## 6. Exercise 4 — Finding the First Element and Handling `Optional.empty`

**Level:** Beginner.

**Requirement:** Write a method returning the first name of length at least 4. If none is found, return `"NOT_FOUND"`; if the list contains `null` elements, skip them.

**Solution:**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class FindFirstExercise {
    static String firstLongName(List<String> names) {
        Objects.requireNonNull(names, "names");

        return names.stream()
            .filter(Objects::nonNull)
            .filter(name -> name.length() >= 4)
            .findFirst()
            .orElse("NOT_FOUND");
    }

    public static void main(String[] args) {
        System.out.println(firstLongName(
            Arrays.asList(null, "An", "Bình", "Châu")
        )); // Bình

        System.out.println(firstLongName(
            Arrays.asList(null, "An", "Vy")
        )); // NOT_FOUND

        System.out.println(firstLongName(List.of())); // NOT_FOUND
    }
}
~~~

Here `findFirst()` returns `Optional<String>`, because no elements may remain after filtering. `orElse(...)` converts the Optional to `String` per the problem policy.

### Important Trap: Does `findFirst` Automatically Skip `null`?

**No.** `findFirst()` and `findAny()` can throw `NullPointerException` if the selected element is null. Never expect `Optional.empty()` to silently wrap a `null` stream element.

~~~java
import java.util.Arrays;

// May throw NPE: the first element of the Stream is null.
// Arrays.<String>asList(null, "A").stream().findFirst();

// Guard against this when business policy is to skip nulls:
var first = Arrays.<String>asList(null, "A")
    .stream()
    .filter(java.util.Objects::nonNull)
    .findFirst();

System.out.println(first); // Optional[A]
~~~

This exercise selects the **skip-null** policy before searching. In pipelines that must flag dirty data, replace filtering with explicit validation/error reporting rather than ignoring nulls silently.

## 7. Exercise 5 — `orElse` vs. `orElseGet` When the Fallback Is Expensive

**Level:** Beginner → Intermediate.

**Requirement:** After `findFirst`, the program may need to load a default value from another source. Ensure the fallback is **loaded only when nothing is found**.

**Solution:**

~~~java
import java.util.List;
import java.util.Optional;

public class LazyFallbackExercise {
    static String loadFallback() {
        System.out.println("Loading fallback value");
        return "DEFAULT_GUEST";
    }

    public static void main(String[] args) {
        Optional<String> found = List.of("An", "Bình")
            .stream()
            .filter(name -> name.startsWith("B"))
            .findFirst();

        String eager = found.orElse(loadFallback());
        System.out.println("orElse: " + eager);

        String lazy = found.orElseGet(
            LazyFallbackExercise::loadFallback
        );
        System.out.println("orElseGet: " + lazy);
    }
}
~~~

Output:

~~~text
Loading fallback value
orElse: Bình
orElseGet: Bình
~~~

**Explanation:** `orElse(loadFallback())` evaluates its argument before the call, so `loadFallback()` runs even when the Optional already holds a value. `orElseGet(supplier)` invokes the Supplier body only if the Optional is empty.

When no match is found:

~~~java
String value = List.of("An", "Vy")
    .stream()
    .filter(name -> name.startsWith("B"))
    .findFirst()
    .orElseGet(LazyFallbackExercise::loadFallback);

// Prints the fallback log; value == "DEFAULT_GUEST".
~~~

**Policy:** When the fallback is a simple constant such as `"NOT_FOUND"`, `orElse` is simpler. When the fallback performs computation, allocates large objects, or runs I/O, `orElseGet` is usually appropriate. Note that `orElseGet` does not handle network errors, transactions, or retries inside the fallback on its own.

## 8. Exercise 6 — Missing Result as a Business Error: `orElseThrow`

**Level:** Intermediate.

**Requirement:** A transaction list holds valid entries. A specific transaction must be found by required ID; if missing, throw an error instead of fabricating a dummy value.

**Solution:**

~~~java
import java.util.List;
import java.util.Objects;

public class RequiredTransactionExercise {
    record Transaction(String id, long amount) {}

    static Transaction requireById(
        List<Transaction> transactions,
        String id
    ) {
        Objects.requireNonNull(transactions, "transactions");
        Objects.requireNonNull(id, "id");

        return transactions.stream()
            .filter(Objects::nonNull)
            .filter(t -> id.equals(t.id()))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Transaction not found: " + id
            ));
    }

    public static void main(String[] args) {
        List<Transaction> transactions = List.of(
            new Transaction("T01", 100L),
            new Transaction("T02", 200L)
        );

        System.out.println(
            requireById(transactions, "T02").amount()
        ); // 200

        // requireById(transactions, "T99");
        // Throws IllegalArgumentException with a clear message.
    }
}
~~~

Calling `id.equals(t.id())` avoids invoking a method on `t.id()` if that field is null. A transaction with `id == null` will simply not match the non-null requested ID.

### How Do `orElseThrow` and `get` Differ?

`Optional.get()` on an empty Optional throws `NoSuchElementException`, which makes it hard to explain **why it is a business error**. `orElseThrow(() -> new ...)` lets you throw a domain-specific exception with context. If the default exception suffices, no-arg `orElseThrow()` can also be used.

**Key decision:** Failing to find a user on a search screen may be a normal empty state; failing to find a mandatory transaction during posting is an error. The same `Optional.empty()` demands different handling policies.

## 9. Exercise 7 — Computing Average, `min`, and `max` on Empty Primitive Streams

**Level:** Beginner → Intermediate.

**Requirement:** Given a list of scores where only values from 0 to 100 are valid, compute the average score; if no valid scores exist, preserve **absence of result** instead of substituting 0. Also print min/max when data exists.

**Solution:**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class PrimitiveOptionalExercise {
    static int[] validScores(List<Integer> source) {
        return source.stream()
            .filter(java.util.Objects::nonNull)
            .mapToInt(Integer::intValue)
            .filter(score -> score >= 0 && score <= 100)
            .toArray();
    }

    public static void main(String[] args) {
        List<Integer> raw = Arrays.asList(
            null, -5, 80, 100, 120
        );

        int[] scores = validScores(raw);

        OptionalDouble average =
            Arrays.stream(scores).average();
        OptionalInt minimum =
            Arrays.stream(scores).min();
        OptionalInt maximum =
            Arrays.stream(scores).max();

        System.out.println(average.orElseThrow()); // 90.0
        System.out.println(minimum.orElseThrow()); // 80
        System.out.println(maximum.orElseThrow()); // 100

        int[] emptyScores = validScores(
            Arrays.asList(null, -1, 200)
        );

        OptionalDouble noAverage =
            Arrays.stream(emptyScores).average();

        System.out.println(noAverage); // OptionalDouble.empty
    }
}
~~~

`IntStream.min()` and `max()` return `OptionalInt`; `average()` returns `OptionalDouble`. These accurately represent the absence of measurements.

### Why Should You Not Always Write `average().orElse(0.0)`?

**No data** and **an actual average of 0.0** carry very different business meanings. If the UI should display `"No scores"`, keep the Optional until the presentation layer:

~~~java
OptionalDouble avg = Arrays.stream(emptyScores).average();

String label = avg.isPresent()
    ? String.format(java.util.Locale.ROOT, "%.1f", avg.getAsDouble())
    : "No scores";

System.out.println(label); // No scores
~~~

Call `getAsDouble()` only after confirming `isPresent()`. If missing scores are disallowed altogether, fail fast instead of forcing `0.0`.

**Note:** `Arrays.stream(scores)` creates a fresh `IntStream` for each metric because a consumed Stream cannot be reused. If you just need standard summary stats in a single pass, `summaryStatistics()` is available.

## 10. Exercise 8 — `reduce` on Empty Sources and Identity

**Level:** Intermediate.

**Requirement:** Given a list of integers, compute the sum in two ways: (1) `reduce(Integer::sum)`, and (2) `reduce(0, Integer::sum)`. Explain the behavior on an empty list.

**Solution:**

~~~java
import java.util.List;
import java.util.Optional;

public class ReduceEmptyExercise {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 5);

        Optional<Integer> optionalSum =
            numbers.stream().reduce(Integer::sum);

        int sumWithIdentity =
            numbers.stream().reduce(0, Integer::sum);

        System.out.println(optionalSum); // Optional[10]
        System.out.println(sumWithIdentity); // 10

        List<Integer> empty = List.of();

        System.out.println(
            empty.stream().reduce(Integer::sum)
        ); // Optional.empty

        System.out.println(
            empty.stream().reduce(0, Integer::sum)
        ); // 0
    }
}
~~~

**Explanation:**

- `reduce(BinaryOperator)` has no identity, so it returns an Optional, empty when there are no elements.
- `reduce(identity, BinaryOperator)` starts from an identity value. On an empty source, it returns that identity.
- `0` is a valid additive identity because `0 + x = x + 0 = x`.
- `10` is not an additive identity. `reduce(10, Integer::sum)` on `[2,3,5]` yields `20` sequentially; that is not a pure sum.

### Handling `null` in `reduce`

~~~java
import java.util.Arrays;
import java.util.Objects;

List<Integer> values = Arrays.asList(2, null, 3);

int sum = values.stream()
    .filter(Objects::nonNull)
    .reduce(0, Integer::sum);

System.out.println(sum); // 5
~~~

Never pass `null` to `Integer::sum`. Also, `reduce(BinaryOperator)` cannot return `null` to represent an empty Optional; reduction may throw `NullPointerException` if a combiner/accumulator yields `null`.

For large counts, prefer `mapToLong(...).sum()` if sums may exceed `int`; `long` still has bounds that must be checked against real scale.

## 11. Exercise 9 — Flattening Multiple Optionals into a Valid Stream

**Level:** Intermediate.

**Requirement:** Given a list of lookup results `List<Optional<String>>`, extract only present values, preserve order, and never call `get()` on an empty Optional.

**Solution:**

~~~java
import java.util.List;
import java.util.Optional;

public class FlattenOptionalExercise {
    public static void main(String[] args) {
        List<Optional<String>> lookups = List.of(
            Optional.of("An"),
            Optional.empty(),
            Optional.of("Bình"),
            Optional.empty(),
            Optional.of("Chi")
        );

        List<String> names = lookups.stream()
            .flatMap(Optional::stream)
            .toList();

        System.out.println(names); // [An, Bình, Chi]
    }
}
~~~

`Optional.stream()` returns a 0-element Stream when the Optional is empty, or a 1-element Stream when present. `flatMap(Optional::stream)` flattens all results cleanly without `isPresent()` + `get()`.

A Java 8 alternative is:

~~~java
List<String> names = lookups.stream()
    .filter(Optional::isPresent)
    .map(Optional::get)
    .toList();
~~~

This compiles on Java 17+, though `Optional::stream` is more concise and avoids calling `get()` directly. Because `Stream.toList()` requires Java 16+, replace the terminal operation with a compatible collector on Java 8.

### What If the List Contains a `null` `Optional` Reference?

Filter out null Optional references first:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Optional;

List<Optional<String>> raw = Arrays.asList(
    Optional.of("A"), null, Optional.empty()
);

List<String> valid = raw.stream()
    .filter(Objects::nonNull)
    .flatMap(Optional::stream)
    .toList();

System.out.println(valid); // [A]
~~~

`Optional.empty()` is a valid object; a variable of type `Optional` holding `null` **violates Optional design conventions**. Fix the producer returning null Optionals rather than relying indefinitely on downstream null filtering.

## 12. Exercise 10 — `null` in `collect` Results and Data Policies

**Level:** Intermediate.

**Requirement:** A Stream may contain `null` elements. Compare two ways of creating an unmodifiable List and show how to keep nulls out of the result.

**Solution:**

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectNullExercise {
    public static void main(String[] args) {
        List<String> acceptsNull = Stream.of("A", null, "B")
            .toList();

        System.out.println(acceptsNull); // [A, null, B]

        // The snippet below throws NullPointerException:
        // List<String> fails = Stream.of("A", null, "B")
        //     .collect(Collectors.toUnmodifiableList());

        List<String> cleaned = Stream.of("A", null, "B")
            .filter(Objects::nonNull)
            .collect(Collectors.toUnmodifiableList());

        System.out.println(cleaned); // [A, B]
    }
}
~~~

Both `Stream.toList()` and `Collectors.toUnmodifiableList()` **return unmodifiable Lists**, yet they **differ on `null`**:

| Collection Method | Mutable List? | Allows `null` Elements? |
| --- | --- | --- |
| `Stream.toList()` | No | Yes |
| `Collectors.toUnmodifiableList()` | No | No; throws NPE |
| `Collectors.toCollection(ArrayList::new)` | Yes | Yes, per ArrayList contract |
| `Collectors.toList()` | Not guaranteed | Do not rely on implementation behavior when null policy is critical |

**Do not equate an unmodifiable List with a non-null List.** If you want to reject nulls as invalid data, relying on a collector's NPE works as a guard, though raising a clear domain exception is usually better.

### Testing According to Policy

~~~java
List<String> noNulls = Stream.of("A", null, "B")
    .filter(Objects::nonNull)
    .toList();

if (noNulls.size() != 2 || noNulls.contains(null)) {
    throw new AssertionError("Nulls must not be kept");
}
~~~

Here the output is an unmodifiable list preserving `A` before `B` because the Stream source has encounter order.

## 13. Exercise 11 — `groupingBy` and `toMap` When Keys or Values May Be `null`

**Level:** Intermediate.

**Requirement:** Each employee record has a name and a department, where department may be null. Count employees by department, placing missing departments into `"UNASSIGNED"`. Then build a lookup Map by name, excluding records without a name.

**Solution:**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class NullableKeysExercise {
    record Employee(String name, String department) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
            new Employee("An", "Engineering"),
            new Employee("Bình", null),
            new Employee("Chi", "Engineering"),
            new Employee(null, "Finance")
        );

        Map<String, Long> countByDepartment = employees.stream()
            .collect(Collectors.groupingBy(
                e -> e.department() == null
                    ? "UNASSIGNED"
                    : e.department(),
                TreeMap::new,
                Collectors.counting()
            ));

        System.out.println(countByDepartment.get("Engineering")); // 2
        System.out.println(countByDepartment.get("UNASSIGNED")); // 1
        System.out.println(countByDepartment.get("Finance")); // 1

        Map<String, String> byName = employees.stream()
            .filter(e -> e.name() != null)
            .collect(Collectors.toMap(
                Employee::name,
                e -> e.department() == null
                    ? "UNASSIGNED"
                    : e.department()
            ));

        System.out.println(byName.get("Bình")); // UNASSIGNED
    }
}
~~~

`groupingBy` in standard Java **forbids classifiers returning `null`**; it can throw `NullPointerException`. The pattern above substitutes an explicit key before entering the Map. If the system could have a real department literally named `"UNASSIGNED"`, use an enum or a tagged key type to avoid sentinel ambiguity.

`Collectors.toMap(keyMapper, valueMapper)` throws `IllegalStateException` on duplicate keys; names are assumed unique here for illustration. It also cannot store arbitrary `null` values; the pattern converts null departments into a valid string.

### When the Source List Contains `null` `Employee` Elements

If the List itself can hold null elements, add `filter(Objects::nonNull)` before `Employee::name` or `Employee::department`. `List.of(...)` forbids null elements; `Arrays.asList(...)` or external sources can contain them.

**Extension experiment:** If an employee with `name == null` is not permitted to be skipped by business rules, replace `filter` with a validation step throwing an exception containing the row/index context.

## 14. Exercise 12 — Ordered Search Rules and Empty Sources

**Level:** Intermediate.

**Requirement:** A task list is ordered by priority. Write a method returning the first task with `priority >= 5` as `Optional<Task>`. Ensure absence is preserved without inventing a dummy task.

**Solution:**

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class OptionalTaskExercise {
    record Task(String code, int priority) {}

    static Optional<Task> firstHighPriority(List<Task> tasks) {
        Objects.requireNonNull(tasks, "tasks");

        return tasks.stream()
            .filter(Objects::nonNull)
            .filter(task -> task.priority() >= 5)
            .findFirst();
    }

    public static void main(String[] args) {
        List<Task> tasks = List.of(
            new Task("A", 2),
            new Task("B", 8),
            new Task("C", 9)
        );

        System.out.println(
            firstHighPriority(tasks).map(Task::code)
        ); // Optional[B]

        System.out.println(
            firstHighPriority(List.of())
        ); // Optional.empty
    }
}
~~~

With `List.stream()`, encounter order reflects list order. `findFirst` selects the first matching task **in input order**. If the list is not already sorted by the desired priority rule, `findFirst` does not sort it automatically.

To find the **highest-priority task** rather than the **first task meeting a threshold**, use `max(Comparator.comparingInt(Task::priority))` or sort explicitly:

~~~java
Optional<Task> highest = tasks.stream()
    .filter(Objects::nonNull)
    .max(java.util.Comparator.comparingInt(Task::priority));

// On the sample data: Optional[Task[code=C, priority=9]].
~~~

### Does Parallelism Change the Answer?

`parallelStream().findFirst()` still honors encounter order if the source is ordered. `parallelStream().findAny()` is free to return any matching element; do not use `findAny` when "first" is required.

If the source is `unordered()` or inherently lacks encounter order, `findFirst` does not guarantee returning the "first in the original list". When no element matches, both `findFirst` and `findAny` return an empty Optional, never `null`.

## 15. Capstone Exercise — Order Report from Incomplete Data

**Level:** Intermediate.

**Practical prompt:** An API returns a list of orders; occasionally the list reference itself is `null`. Inside, there may be `null` `Order` elements, missing order IDs, missing regions, or missing amounts. The system requires:

1. If the source is `null`, by convention **there is no data to report**; return an empty result.
2. Drop `null` objects, `null`/blank IDs, and orders without an amount.
3. Map `null`/blank regions to `"UNKNOWN"`.
4. Compute the valid order count and `long` total amount per region; sort keys for readable reporting.
5. Find the **ID of the first valid order** with amount at least 150, keeping the result as an `Optional`.
6. Do not mutate the source, use shared counters, or reuse a Stream after a terminal operation.

**Complete Solution:**

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class IncompleteOrdersReport {
    record Order(String id, String region, Long amount) {}

    record Report(
        long validCount,
        Map<String, Long> amountByRegion,
        Optional<String> firstLargeOrderId
    ) {}

    static Report analyze(List<Order> source) {
        // Exercise-specific convention: null source == empty source.
        List<Order> valid = Optional.ofNullable(source)
            .orElseGet(List::of)
            .stream()
            .filter(Objects::nonNull)
            .filter(o -> o.id() != null && !o.id().isBlank())
            .filter(o -> o.amount() != null)
            .toList();

        Map<String, Long> totals = valid.stream()
            .collect(Collectors.groupingBy(
                o -> o.region() == null || o.region().isBlank()
                    ? "UNKNOWN"
                    : o.region().strip(),
                TreeMap::new,
                Collectors.summingLong(Order::amount)
            ));

        Optional<String> firstLargeId = valid.stream()
            .filter(o -> o.amount() >= 150L)
            .map(Order::id)
            .findFirst();

        // Expose only a structurally unmodifiable Map view.
        return new Report(
            valid.size(),
            Collections.unmodifiableMap(totals),
            firstLargeId
        );
    }

    public static void main(String[] args) {
        List<Order> raw = Arrays.asList(
            new Order("O1", "South", 120L),
            null,
            new Order(" ", "North", 50L),
            new Order("O2", null, 75L),
            new Order("O3", "South", null),
            new Order("O4", "South", 200L)
        );

        Report report = analyze(raw);

        System.out.println(report.validCount()); // 3
        System.out.println(report.amountByRegion());
        // {South=320, UNKNOWN=75}
        System.out.println(report.firstLargeOrderId());
        // Optional[O4]

        Report empty = analyze(null);
        System.out.println(empty.validCount()); // 0
        System.out.println(empty.amountByRegion()); // {}
        System.out.println(empty.firstLargeOrderId());
        // Optional.empty
    }
}
~~~

### Why Does This Solution Meet Every Requirement?

- `Optional.ofNullable(source).orElseGet(List::of)` converts only a **`null` source reference** into an empty List per the problem rule.
- `filter(Objects::nonNull)` eliminates **`null` `Order` objects** before reading fields.
- The next two filters drop missing/blank IDs and missing amounts without treating `null` as amount 0.
- `groupingBy(..., TreeMap::new, summingLong(...))` produces a key-sorted report; the classifier always returns a non-null key.
- `findFirst()` returns `Optional<String>` when no order qualifies. No fake sentinel like `"NONE"` can be mistaken for a real ID.
- `valid.stream()` is called **twice**, opening a fresh Stream each time from a materialized List rather than invoking two terminals on one Stream.
- `Collections.unmodifiableMap(totals)` prevents mutating the Map through `Report`. No other reference to `totals` is leaked here, and `Order` is a record with immutable components (`String` and `Long`). Note this is still a **structurally unmodifiable view**, not a deep-immutability guarantee for arbitrary object types.

### Other Policies May Also Be Valid

This exercise chooses to **discard records missing ID or amount**. In real payment pipelines, those may be critical errors requiring you to **collect an error list** or halt processing. Likewise, negative amounts might represent refunds; never filter out negatives unless required. `Collectors.summingLong` can also overflow `long`; large financial volumes require bounds or overflow-checked arithmetic.

If you must **avoid materializing an intermediate list**, use a custom collector or combined statistics, though this solution prioritizes clarity and safety at the intermediate level.

## 16. Edge-Case Testing Checklist

For every pipeline processing incomplete data, verify at least these scenarios. Avoid cramming everything into one giant function; split tests by input and output contracts:

| Test Scenario | Expected Behavior |
| --- | --- |
| `null` source | Per policy: throw error or treat as empty |
| `List.of()` source | Empty result / empty Optional, no NPE |
| List containing only `null`s | Filtered cleanly or rejected; never invoke methods on null |
| `null`s interspersed with valid items | Valid items retained per rules |
| Nullable fields inside records | Normalized or routed to error path before collectors |
| `findFirst` with no matching element | `Optional.empty()` or explicit fallback |
| `findFirst` hitting a `null` element | Prevent null from being selected directly |
| `average` on empty `IntStream` | `OptionalDouble.empty()` |
| `reduce` without identity on empty source | `Optional.empty()` |
| `reduce` with identity on empty source | Returns identity, e.g., `0` for addition |
| `allMatch` on empty source | `true`; add non-empty check if required |
| `toUnmodifiableList` encountering `null` | Throws NPE; filter or fail explicitly beforehand |
| `groupingBy` classifier returning `null` | Throws NPE; substitute valid key or fail fast |
| `toMap` encountering duplicate keys | Throws `IllegalStateException` without merge function |
| Large-number sums | Account for overflow risks |
| Parallel with side effects | Never depend on callback order or shared mutable state |

### A Small Dependency-Free Test Suite

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class MissingDataChecks {
    static Optional<String> firstValid(List<String> source) {
        return Optional.ofNullable(source)
            .orElseGet(List::of)
            .stream()
            .filter(Objects::nonNull)
            .map(String::strip)
            .filter(s -> !s.isEmpty())
            .findFirst();
    }

    public static void main(String[] args) {
        if (firstValid(null).isPresent()) {
            throw new AssertionError("Null source must return empty");
        }

        if (firstValid(List.of()).isPresent()) {
            throw new AssertionError("Empty list must return empty");
        }

        if (firstValid(Arrays.asList(null, "  ", " An "))
                .filter("An"::equals)
                .isEmpty()) {
            throw new AssertionError("Valid element was dropped");
        }

        System.out.println("PASS");
    }
}
~~~

This checks three cases: missing source object, valid empty source, and interleaved null/blank entries. As problems grow, name test cases after specific business rules and add checks for duplicate keys, numeric overflow, and reordered inputs.

## 17. Anti-Patterns to Avoid

### 17.1. Calling `stream()` Directly on a Nullable Source

~~~java
List<String> source = null;

// source.stream().count(); // NullPointerException.
~~~

If `null` is allowed by contract, convert it to an empty List/Stream. If `null` is an error, fail explicitly with `Objects.requireNonNull` and a clear message.

### 17.2. Calling Methods on Elements Before Filtering `null`

~~~java
// Broken when null elements exist:
// source.stream().map(String::strip).filter(Objects::nonNull);
~~~

Filter `null` before any method that can throw NPE, or use `flatMap(x -> Stream.ofNullable(x))` where appropriate.

### 17.3. Turning an Empty Optional into a Real Value Without Checking Semantics

~~~java
double average = java.util.stream.IntStream.empty()
    .average()
    .orElse(0.0);

// 0.0 here is a fallback, not a measured average.
~~~

When the two states must stay distinct, preserve `OptionalDouble` until presentation.

### 17.4. Believing `findAny` and `findFirst` Automatically Skip `null`

~~~java
// Can throw NPE when the selected element is null:
// java.util.stream.Stream.of((String) null).findAny();
~~~

If the policy is to skip nulls, add `filter(Objects::nonNull)` before the search terminal operation.

### 17.5. Using `orElse` with Expensive Calls

~~~java
// loadFromNetwork() runs even when the Optional is present:
// String value = found.orElse(loadFromNetwork());

// Defer fallback evaluation:
// String value = found.orElseGet(() -> loadFromNetwork());
~~~

`orElseGet` defers only the **Supplier body**. If you compute the fallback into a local variable before the lambda, the work still runs eagerly.

### 17.6. Reusing a Stream After a Terminal Operation

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<String> once = List.of("A", "B").stream();
long count = once.count();

// once.findFirst(); // Cannot reuse a consumed Stream.
~~~

Each independent terminal query requires a fresh Stream from the source or a `Supplier<Stream<T>>` producing valid Streams.

## 18. Self-Check Questions and Extension Exercises

1. **Is an empty `List` the same as a `null` `List` reference?** No. An empty List is a valid object; calling `stream()` on `null` throws NPE.
2. **How many elements does `Stream.ofNullable(null)` produce?** 0 elements.
3. **How many elements does `Stream.of((String) null)` produce?** 1 element, and that element is `null`.
4. **Why must `filter(Objects::nonNull)` precede `map(String::strip)`?** Because `String::strip` cannot be invoked on a `null` reference.
5. **Does `findFirst()` return `null` when nothing matches?** No; it returns `Optional.empty()`.
6. **Is `findFirst()` safe if the first element is `null`?** No; it can throw NPE if it selects `null`.
7. **How does `Optional.ofNullable(value)` differ from `Optional.of(value)` when `value == null`?** `ofNullable` returns an empty Optional; `of` throws NPE.
8. **How does `orElse(default())` differ from `orElseGet(() -> default())`?** The first evaluates its argument eagerly before the call; the second runs the Supplier only if the Optional is empty.
9. **When required data is missing, should you return `"UNKNOWN"` or throw an error?** Follow the contract; when data is mandatory, prefer `orElseThrow` or an explicit error model.
10. **What does `IntStream.empty().average()` return?** `OptionalDouble.empty()`.
11. **What does `IntStream.empty().sum()` return?** `0`.
12. **Why does `allMatch` return `true` on an empty Stream?** Because there is no counterexample element.
13. **What does `flatMap(Optional::stream)` do?** Converts each Optional into a 0/1-element Stream and flattens them.
14. **Do `toList()` and `toUnmodifiableList()` share the same `null` policy?** No. `toList()` allows nulls; `toUnmodifiableList()` forbids nulls.
15. **Does `groupingBy` automatically create a group for a classifier returning `null`?** No; standard Java throws NPE.
16. **Does `findAny` on a parallel stream guarantee returning the first element?** No; it may return any matching element.
17. **Why is `Optional` helpful when computing an average over potentially empty data?** It preserves the distinction between "no data" and "an actual average of 0".
18. **Can a pipeline that already ran `count()` be reused to run `findFirst()`?** No; you must open a new Stream.

**Extension Exercise A:** Modify the incomplete-orders exercise to also return a `List<String> invalidIds` recording bad IDs instead of silently dropping incomplete records. Be careful to distinguish `null` records from records with `id == null`.

**Extension Exercise B:** Add a `currency` field to orders. Never add amounts in different currencies without a valid conversion rate. Design a Map keyed by `(region, currency)` or nested grouping to avoid invalid cross-currency sums.

**Extension Exercise C:** Write `Optional<String> findNormalizedEmail(List<Customer>)` accepting a `null` list, `null` `Customer` elements, and `null`/blank emails. When no valid email exists, return `Optional.empty`, never `null` or a dummy string.

**Key takeaway:** The Stream API does not repair missing data automatically. Define **explicit policies at every layer**: `null` source, `null` element, nullable field, empty Stream, and empty Optional. `filter`, `Stream.ofNullable`, and `Optional.stream` express "skip absent values"; `orElse`, `orElseGet`, and `orElseThrow` express "substitute or fail". A strong pipeline behaves accurately on both clean data and edge cases, not merely avoiding exceptions on happy-path inputs.
