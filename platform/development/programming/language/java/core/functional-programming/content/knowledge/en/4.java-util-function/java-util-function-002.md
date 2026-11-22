# Predicate<T> for true or false conditions in Java

**`Predicate<T>`** is a functional interface in the `java.util.function` package representing a conditional check on an object of type `T`. Its core method `boolean test(T value)` returns `true` or `false`. Predicates let you pass checking rules as data: they can be assigned to variables, accepted as parameters, combined into larger conditions, and used when processing collections or Streams.

For example, rules like "non-empty string", "price at most 300", and "valid object" can each be represented by a Predicate. The strength of this style is **separating checking logic from where the logic is used**, so the same rule can be reused.

After this lesson, you can:
- Define and invoke a `Predicate<T>` using a lambda or method reference.
- Combine conditions with `and`, `or`, `negate`, `Predicate.not`, and `isEqual`, and understand short-circuiting.
- Use Predicates with `Stream.filter`, `anyMatch`, `allMatch`, `noneMatch`, and deterministic examples.
- Avoid null errors, side effects, and hard-to-read rules, and choose properly among `Predicate<T>`, `Function<T, Boolean>`, `BiPredicate<T,U>`, `IntPredicate`, and related interfaces.

## 1. Contract and meaning of Predicate<T>

You can picture the essential part of the interface as follows:

```java
@FunctionalInterface
public interface Predicate<T> {
    boolean test(T value);
    // In addition, there are default and static composition methods.
}
```

This is a **simplified version for explanation**, not a full copy of the JDK declaration. `@FunctionalInterface` allows a lambda to serve as the implementation of the single abstract method `test`.

- `T` is the input type, such as `String`, `Integer`, `Customer`, or `Product`.
- `test(T value)` takes one value and returns a **primitive `boolean`**. There is no `null` result.
- A `true` result means the condition defined by the author is satisfied; `false` means it is not satisfied.
- `Predicate` only defines **the contract of taking one value and returning a boolean**; it does not automatically check for null, does not guarantee a pure function, does not cache results, and does not guarantee thread safety.

Common ways to declare one:

```java
Predicate<Integer> positive = n -> n > 0;
Predicate<String> startsWithJ = text -> text.startsWith("J");
Predicate<String> blank = String::isBlank;
```

The three lines above are **illustrative code snippets** that require `import java.util.function.Predicate;` and must be placed in a method or suitable declaration context. The lambda `n -> n > 0` takes an `Integer` and returns a boolean; the method reference `String::isBlank` has a signature compatible with `String -> boolean`.

**Note on generics:** `Predicate<Integer>` takes an `Integer` object; the `>` operator uses unboxing to compare numbers. For large integer streams, `IntPredicate` can avoid boxing/unboxing.

## 2. Complete example: calling test and handling null

Save as **`PredicateBasicsDemo.java`**:

```java
import java.util.function.Predicate;

public class PredicateBasicsDemo {
    public static void main(String[] args) {
        Predicate<String> hasText =
                text -> text != null && !text.isBlank();

        Predicate<String> startsWithJ =
                text -> text != null && text.startsWith("J");

        System.out.println("Java có chữ: " + hasText.test("Java"));
        System.out.println("Khoảng trắng có chữ: " + hasText.test("   "));
        System.out.println("null có chữ: " + hasText.test(null));
        System.out.println("Java bắt đầu J: " + startsWithJ.test("Java"));
        System.out.println("Kotlin bắt đầu J: " + startsWithJ.test("Kotlin"));
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 PredicateBasicsDemo.java
java PredicateBasicsDemo
```

**Exact stdout:**

```text
Java có chữ: true
Khoảng trắng có chữ: false
null có chữ: false
Java bắt đầu J: true
Kotlin bắt đầu J: false
```

`text != null && !text.isBlank()` uses the short-circuit `&&` operator: when `text == null`, the `isBlank()` side is not called. This makes the predicate handle null inputs intentionally. Conversely, `String::isBlank` when called with null can throw `NullPointerException`, because it must invoke an instance method on an object.

Each call to `test(...)` is **one evaluation of the condition**. Assigning a lambda to a variable does not run `test` by itself; calling `test` again may re-run the entire logic.

## 3. Combining Predicates with and, or, and negate

`Predicate<T>` has default methods to build new Predicates:

| Method | Result | Evaluation condition |
| --- | --- | --- |
| `p.and(q)` | True when both `p` and `q` are true | Calls `p.test(x)` first; only calls `q.test(x)` when `p` is true. |
| `p.or(q)` | True when at least one condition is true | Calls `p.test(x)` first; only calls `q.test(x)` when `p` is false. |
| `p.negate()` | Negates the result of `p` | Returns the opposite logical result when called. |

Example:

```java
Predicate<Integer> atLeast18 = age -> age >= 18;
Predicate<Integer> atMost65 = age -> age <= 65;
Predicate<Integer> workingAge = atLeast18.and(atMost65);

boolean ok = workingAge.test(25); // true
boolean tooYoung = atLeast18.negate().test(16); // true
```

This is an illustrative snippet. `and`, `or`, and `negate` **return a new Predicate**, without mutating the original Predicate object. You can still reuse `atLeast18` and `atMost65` separately after creating `workingAge`.

The `and` and `or` methods are **short-circuiting when `test` is called**; this matters if the right-hand side is expensive or only safe when the left-hand side holds. For instance:

```java
Predicate<String> nonNull = text -> text != null;
Predicate<String> longText = text -> text.length() >= 5;
Predicate<String> safeLongText = nonNull.and(longText);
boolean result = safeLongText.test(null); // false, does not call longText
```

**Distinguish Predicate creation time from `test` call time:** the argument expression `q` in `p.and(q)` is evaluated when `and` is called according to Java rules. However, `q.test(value)` is only called when the combined Predicate is executed and short-circuiting permits.

When `other` is null, `p.and(null)` and `p.or(null)` throw `NullPointerException` immediately when creating the composition.

## 4. Runnable example: observing short-circuit order

Save as **`PredicateShortCircuitDemo.java`**:

```java
import java.util.function.Predicate;

public class PredicateShortCircuitDemo {
    public static void main(String[] args) {
        Predicate<String> longEnough = text -> {
            System.out.println("Kiểm tra độ dài: " + text);
            return text.length() >= 4;
        };

        Predicate<String> startsJ = text -> {
            System.out.println("Kiểm tra chữ J: " + text);
            return text.startsWith("J");
        };

        Predicate<String> rule = longEnough.and(startsJ);

        System.out.println("Hi: " + rule.test("Hi"));
        System.out.println("Java: " + rule.test("Java"));
    }
}
```

Run command:

```bash
javac -encoding UTF-8 PredicateShortCircuitDemo.java
java PredicateShortCircuitDemo
```

**Exact stdout:**

```text
Kiểm tra độ dài: Hi
Hi: false
Kiểm tra độ dài: Java
Kiểm tra chữ J: Java
Java: true
```

For `"Hi"`, `longEnough` returns false so `startsJ` does not run. For `"Java"`, the left side is true so the right side continues to be checked.

For `p.or(q)`, the opposite rule applies: once `p` returns true, Java skips `q.test(x)`. For `p.negate()`, the result after checking is flipped from true to false or vice versa. **Do not write tests or record data depending on how many times sub-predicates are called** if that count is not part of the business contract; short-circuiting can cause some predicates not to run.

## 5. Predicate.not and Predicate.isEqual

Alongside default methods, `Predicate` has useful static methods.

### 5.1. Predicate.not

Since Java 11, `Predicate.not(Predicate<? super T> target)` creates a negated Predicate. This is especially concise with method references:

```java
List<String> nonBlank = java.util.List.of("Java", "", "Stream")
        .stream()
        .filter(java.util.function.Predicate.not(String::isBlank))
        .toList();
// nonBlank = [Java, Stream]
```

This is an illustrative snippet; `toList()` has been available since Java 16 so it runs on Java 17+. `Predicate.not(String::isBlank)` is equivalent in intent to `((Predicate<String>) String::isBlank).negate()`, without needing an awkward cast at the `filter` call site.

`Predicate.not` does not automatically make a method reference null-safe: if the Stream contains null, calling `String::isBlank` can still throw an exception. To remove null first, use `filter(java.util.Objects::nonNull)` before checking `isBlank`.

### 5.2. Predicate.isEqual

`Predicate.isEqual(targetRef)` creates a Predicate that checks whether the input value equals `targetRef` using `Objects.equals` semantics:

```java
Predicate<String> isJava = Predicate.isEqual("Java");
boolean exact = isJava.test("Java");    // true
boolean other = isJava.test("Kotlin");  // false

Predicate<String> isNull = Predicate.isEqual(null);
boolean missing = isNull.test(null);    // true
```

This is an illustrative snippet with `import java.util.function.Predicate;`. `isEqual` compares **equality via `equals`**, not reference identity via `==`. This method is suitable when you want to express "matches a fixed value", including null, without writing a lambda manually.

## 6. Predicate in Stream: filter and terminal operations

Stream APIs accept Predicates in several places:

| API | Role of Predicate | Return type |
| --- | --- | --- |
| `filter(predicate)` | Keeps elements where `test` returns true. | A new `Stream<T>`. |
| `anyMatch(predicate)` | Does at least one element match? | `boolean`. |
| `allMatch(predicate)` | Do all elements match? | `boolean`. |
| `noneMatch(predicate)` | Do no elements match? | `boolean`. |
| `takeWhile(predicate)` | Takes the contiguous prefix still matching the condition, following encounter order if any. | A new `Stream<T>`. |
| `dropWhile(predicate)` | Drops the contiguous prefix still matching the condition, following encounter order if any. | A new `Stream<T>`. |

`filter`, `takeWhile`, and `dropWhile` are **intermediate operations** so they only build the pipeline without traversing the entire source on their own. `anyMatch`, `allMatch`, and `noneMatch` are **terminal operations** that can short-circuit early once the result is determined.

On an empty Stream, `anyMatch` is **false**, while `allMatch` and `noneMatch` are both **true**. The latter two results are "vacuously true" cases because no element causes the condition to fail; do not mistake them for having found valid data.

### Java 17 example: filtering products by multiple conditions

Save as **`PredicateStreamDemo.java`**:

```java
import java.util.List;
import java.util.function.Predicate;

public class PredicateStreamDemo {
    record Product(String name, String category, int price, boolean available) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Java Book", "Book", 250, true),
                new Product("USB", "Tech", 120, true),
                new Product("Notebook", "Book", 80, false),
                new Product("Clean Code", "Book", 320, true)
        );

        Predicate<Product> isBook =
                product -> "Book".equals(product.category());
        Predicate<Product> affordable =
                product -> product.price() <= 300;
        Predicate<Product> inStock = Product::available;

        Predicate<Product> eligible =
                isBook.and(affordable).and(inStock);

        List<String> names = products.stream()
                .filter(eligible)
                .map(Product::name)
                .toList();

        System.out.println("Đủ điều kiện: " + names);
        System.out.println("Có sản phẩm phù hợp: "
                + products.stream().anyMatch(eligible));
        System.out.println("Không phải sách: "
                + products.stream()
                        .filter(isBook.negate())
                        .map(Product::name)
                        .toList());
        System.out.println("Danh mục khớp: "
                + Predicate.isEqual("Book").test(products.get(0).category()));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 PredicateStreamDemo.java
java PredicateStreamDemo
```

**Exact stdout:**

```text
Đủ điều kiện: [Java Book]
Có sản phẩm phù hợp: true
Không phải sách: [USB]
Danh mục khớp: true
```

Explanation:
1. `isBook`, `affordable`, and `inStock` are independent; `eligible` requires all three conditions to hold.
2. "Java Book" is a Book, priced at 250, and in stock, so it is kept.
3. "Notebook" is a Book with a low price, but `available == false`; "Clean Code" is in stock, but price 320 exceeds 300.
4. "USB" is not a Book, so it appears in the result of `isBook.negate()`.
5. `anyMatch(eligible)` returns true because at least one product matches. This terminal **can stop early**, unlike traversing and collecting all matching elements with `toList()`.

The example uses `record` (officially supported since Java 16), `List.of`, and `Stream.toList`, so it fits Java 17.

## 7. Predicate purity, performance, and maintainability

### Prefer conditions without side effects

Normally, a Predicate should only read its input and compute a `boolean`. For example, `p -> p.price() <= limit` is easier to predict than a predicate that both checks and logs, modifies a collection, increments a counter, or calls an external service.

You can write a predicate with side effects, but you need to think carefully: in a Stream, the pipeline is lazy and terminal operations can stop early; with a parallel stream, calls can run across multiple threads in an uncertain order. Therefore, never use the number of Predicate invocations as a substitute for required recording logic. When you need to process each element with side effects, design a transparent flow and use an appropriate terminal operation.

### Order conditions appropriately

In `cheap.and(expensive)`, if `cheap` returns false, `expensive` does not run. Placing a cheap, safe check with high rejection power first often saves work, **provided reordering preserves semantics**. When predicates have side effects or can throw exceptions, changing the order can change observable behavior.

```java
Predicate<String> safe = text -> text != null;
Predicate<String> containsJava = text -> text.contains("Java");
Predicate<String> valid = safe.and(containsJava);
```

In this illustrative snippet, `safe` must come first to avoid calling `contains` on null. A predicate only returns false rather than reporting the reason for failure; if business logic needs multiple error messages, use a richer validation result model.

### Scope of data captured in a lambda

```java
int minLength = 5;
Predicate<String> longEnough = value -> value.length() >= minLength;
```

The local variable `minLength` is captured by the lambda and must be **final or effectively final** (not reassigned after initialization). If you capture a mutable object, the contents of that object can still change; the functional interface itself does not guarantee immutability or thread safety.

### Exceptions

`Predicate.test(T)` does not declare any checked exceptions. If a lambda calls a method that throws a checked exception, you must handle or convert the error by design; you cannot simply declare a lambda that throws a checked exception disallowed by the target type. Runtime exceptions can still propagate when calling `test`.

## 8. When to use Predicate and when to use another interface?

| Interface | Functional method | Appropriate use case |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T)` | Check one object for true/false. |
| `BiPredicate<T,U>` | `boolean test(T,U)` | Check a relationship between two inputs. |
| `IntPredicate` | `boolean test(int)` | Check an `int` without boxing. |
| `LongPredicate` | `boolean test(long)` | Check a primitive `long`. |
| `DoublePredicate` | `boolean test(double)` | Check a primitive `double`. |
| `Function<T,R>` | `R apply(T)` | Transform one value into a result of any type. |
| `Consumer<T>` | `void accept(T)` | Perform an action without returning a result. |
| `Supplier<T>` | `T get()` | Supply a value when called. |

`Function<T, Boolean>` can also represent a check, but it returns the wrapper `Boolean`, which can be null. When the goal is a true/false condition, `Predicate<T>` conveys intent more clearly, returns a primitive `boolean`, and comes with logical composition methods.

Example checking two objects:

```java
java.util.function.BiPredicate<String, String> sameLength =
        (left, right) -> left.length() == right.length();
boolean equal = sameLength.test("Java", "Kotlin"); // false
```

With integers:

```java
java.util.function.IntPredicate positive = number -> number > 0;
boolean ok = positive.test(42); // true
```

Both snippets are illustrative code placed inside a method. The specialized types support `and`, `or`, and `negate` just like the general Predicate, without requiring boxed types for primitive inputs.

## 9. Common mistakes

1. **Confusing a Predicate with a boolean value:** `Predicate<String> p` is a rule; to get the result for an input, call `p.test(input)`.
2. **Assuming `Predicate<T>` handles null automatically:** lambdas that dereference null values will throw `NullPointerException` if there is no prior check.
3. **Writing `p.and(q)` and forgetting to assign the result:** composition creates a new Predicate; it does not update `p`.
4. **Misunderstanding the execution order of `and`/`or`:** the left side is checked first and may skip the right side.
5. **Putting mandatory work inside a Stream Predicate:** the terminal operation may process fewer elements than expected; avoid side effects to ensure stable results.
6. **Assuming `allMatch` on an empty Stream returns false:** in fact, `allMatch` and `noneMatch` both return true for an empty Stream.
7. **Using `String::isBlank` directly on data containing null:** method references do not have automatic null handling.
8. **Creating a huge unreadable Predicate:** split it into named predicates, combine them with `and`/`or`, and test each rule.
9. **Using `Function<T, Boolean>` when an API expects `Predicate<T>`:** these are two different interfaces; `apply` does not directly substitute for `test` without an adapter.
10. **Assuming predicate call order stays the same when running in parallel:** threads and traversal order can differ; rely only on the logical result when predicates meet Stream's non-interference requirements.

## 10. Self-check and exercises

**Question 1.** What is the result of `((Predicate<Integer>) n -> n > 10).test(10)`? **False**, because 10 is not greater than 10.

**Question 2.** Given `Predicate<String> p = s -> s != null; Predicate<String> q = s -> s.length() > 3;`, does `p.and(q).test(null)` throw an exception? **No**: `p.test(null)` returns false, so `q` is not called.

**Question 3.** What do `anyMatch(x -> true)`, `allMatch(x -> false)`, and `noneMatch(x -> true)` return on an empty Stream? Respectively **false**, **true**, **true**.

**Question 4.** If you need to filter names that are non-blank and start with "J", how can you write it?

```java
Predicate<String> usable = name -> name != null && !name.isBlank();
Predicate<String> beginsJ = name -> name.startsWith("J");
Predicate<String> accepted = usable.and(beginsJ);
```

This is an illustrative snippet using `java.util.function.Predicate`. Testing `accepted.test("Java")` yields true; `accepted.test(null)` yields false without throwing an exception.

**Question 5.** If a predicate returns `false`, does the API tell you *why* it failed? **No.** The output is only a `boolean`. When detailed errors are needed, return a separate validation result instead of trying to cram messages into predicate side effects.

**Key takeaway:** `Predicate<T>` is a **checking rule of type `T -> boolean`** that can be passed to APIs and combined with logical operations. Write conditions that are clear, safe with input data, and compatible with short-circuiting during execution.
