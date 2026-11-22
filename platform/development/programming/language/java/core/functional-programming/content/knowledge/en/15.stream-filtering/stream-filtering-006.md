# Combining Filtering Conditions with Predicate in Java

## 1. Goal: turning conditions into composable functions

When filtering a list with Java Stream, the condition passed to `filter` has type `Predicate<T>`. This is a **functional interface** that takes a value of type `T` and returns `boolean` through its single abstract method:

```java
boolean test(T value);
```

Therefore, an expression like `item -> item.price() >= 20` is a condition that can be stored, named, reused, combined, or passed to an API. Instead of cramming the entire rule into one long lambda, we can separate each condition and combine them using:

- `and(...)`: **both** conditions must be true.
- `or(...)`: **at least one** condition is true.
- `negate()`: inverts the true/false value of the condition.
- `Predicate.not(...)` (Java 11+): a static way to negate a Predicate, convenient with method references.

When combining, it is important to understand **the type of the object being filtered**, **evaluation order**, and **short-circuiting**. A condition that depends on non-null data must be placed after the null check in an `and` composition, otherwise it may throw an exception.

## 2. From a single lambda to named Predicates

Suppose an application manages products with a name, price, and stock status. A filter can express the condition “in stock, price from 20 to 60” as follows:

```java
Predicate<Product> inStock = Product::available;
Predicate<Product> minPrice = p -> p.price() >= 20;
Predicate<Product> maxPrice = p -> p.price() <= 60;

Predicate<Product> eligible = inStock.and(minPrice).and(maxPrice);
```

This is an **illustrative snippet**, assuming `Product` is a record or class with `available()` and `price()` methods; `java.util.function.Predicate` needs to be imported.

The common type of all four variables is `Predicate<Product>`. Each call to `test(product)` returns a boolean value:

```text
eligible(product)
    = inStock(product) && minPrice(product) && maxPrice(product)
```

The caller does not need to know whether the condition was written as a lambda, a method reference, or a class implementing `Predicate`. It simply calls `test` through the contract.

Truth table for two conditions A and B:

| A | B | A AND B | A OR B | NOT A |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

This is standard boolean logic, but the `Predicate` API also determines **when the second condition is called**, via short-circuiting.

## 3. Complete Java 17+ example: `and`, `or`, `negate` with `Stream.filter`

Save the file `PredicateCompositionDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class PredicateCompositionDemo {
    record Product(String name, int price, boolean available) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Pen", 15, true),
                new Product("Book", 40, true),
                new Product("Bag", 80, false),
                new Product("Cable", 60, true)
        );

        Predicate<Product> inStock = Product::available;
        Predicate<Product> minPrice = p -> p.price() >= 20;
        Predicate<Product> maxPrice = p -> p.price() <= 60;

        Predicate<Product> eligible =
                inStock.and(minPrice).and(maxPrice);
        Predicate<Product> unavailable = inStock.negate();
        Predicate<Product> cheapOrUnavailable =
                minPrice.negate().or(unavailable);

        System.out.println("Eligible: " +
                products.stream()
                        .filter(eligible)
                        .map(Product::name)
                        .toList());

        System.out.println("Unavailable: " +
                products.stream()
                        .filter(unavailable)
                        .map(Product::name)
                        .toList());

        System.out.println("Cheap or unavailable: " +
                products.stream()
                        .filter(cheapOrUnavailable)
                        .map(Product::name)
                        .toList());
    }
}
```

Compile/run:

```bash
javac PredicateCompositionDemo.java
java PredicateCompositionDemo
```

Exact output:

```text
Eligible: [Book, Cable]
Unavailable: [Bag]
Cheap or unavailable: [Pen, Bag]
```

Explanation of each filter:

- `inStock.and(minPrice).and(maxPrice)` keeps only products that are in stock, with price not below 20 and not above 60. `Book` (40) and `Cable` (60) satisfy all three.
- `inStock.negate()` keeps products with `available() == false`. Only `Bag`.
- `minPrice.negate().or(unavailable)` means “price below 20 **or** out of stock”. `Pen` (15) and `Bag` (out of stock) are kept.
- `Stream.filter` keeps the input element as-is if the Predicate returns `true`; it **does not transform the element into a boolean**. After filtering, `map(Product::name)` converts the remaining elements into names.
- With a sequential stream backed by a §List§ created in the order above, `toList()` preserves encounter order: the names are printed in their order in `products`.

If you want to use `Predicate.not(inStock)` instead of `inStock.negate()`, the logical check result is likewise the negation of `inStock.test(product)`.

## 4. Short-circuit mechanism: which condition actually runs?

The default method `and` is described by the rule:

```text
left.and(right).test(x)
    ≈ left.test(x) && right.test(x)
```

The `or` rule:

```text
left.or(right).test(x)
    ≈ left.test(x) || right.test(x)
```

The `≈` symbol denotes equivalent behavior at the boolean level and evaluation order (this is pseudocode, not API source code). Specifically:

- With `and`, the left Predicate is always evaluated first; **if the left returns false, the right is not called**.
- With `or`, the left Predicate is always evaluated first; **if the left returns true, the right is not called**.
- With `negate`, the original Predicate is called and the boolean is inverted; exceptions from the original Predicate still propagate out.
- There is no guarantee that all composed Predicates will run for every element. The number of calls depends on the short-circuit branch.

Compositions form a new Predicate; the condition body is only evaluated when the application calls `test(...)`, or when a Stream terminal operation actually consumes elements.

### Execution order logging example

Create `PredicateShortCircuitDemo.java`:

```java
import java.util.function.Predicate;

public class PredicateShortCircuitDemo {
    public static void main(String[] args) {
        Predicate<String> nonNull = s -> {
            System.out.println("check-null: " + s);
            return s != null;
        };
        Predicate<String> longEnough = s -> {
            System.out.println("check-length: " + s);
            return s.length() >= 3;
        };
        Predicate<String> startsJ = s -> {
            System.out.println("starts-J: " + s);
            return s.startsWith("J");
        };
        Predicate<String> containsA = s -> {
            System.out.println("contains-a: " + s);
            return s.contains("a");
        };

        Predicate<String> safeLength = nonNull.and(longEnough);
        System.out.println("null result=" + safeLength.test(null));
        System.out.println("Java result=" + safeLength.test("Java"));
        System.out.println("or result=" +
                startsJ.or(containsA).test("Java"));
    }
}
```

Run:

```bash
javac PredicateShortCircuitDemo.java
java PredicateShortCircuitDemo
```

Output:

```text
check-null: null
null result=false
check-null: Java
check-length: Java
Java result=true
starts-J: Java
or result=true
```

There is no `check-length: null` log because `nonNull.test(null)` returns `false` and `and` stops. There is no `contains-a: Java` log because `startsJ.test("Java")` returns `true` and `or` stops.

This is also why **the order of conditions cannot be changed arbitrarily when they have data dependencies, exceptions, or side effects**. In pure logic, A AND B has the same boolean value as B AND A, but the order of `test` calls can make the two executions behave differently. The same principle applies to OR.

## 5. Safe filtering when data can be `null`

Suppose the input data list contains null values, empty strings, or whitespace-only strings. To select strings that are non-null, non-blank, and contain “Java” or “Spring”, we must first ensure that methods like `isBlank()` and `contains()` are only called on non-null strings.

Safe pattern:

```java
Predicate<String> nonBlank =
        s -> s != null && !s.isBlank();

Predicate<String> aboutJavaOrSpring =
        s -> s.contains("Java") || s.contains("Spring");

Predicate<String> accepted =
        nonBlank.and(aboutJavaOrSpring);
```

If `s == null`, the `nonBlank` condition returns false and `aboutJavaOrSpring` does not run. If written in reverse:

```java
// Avoid when input may be null:
Predicate<String> unsafe =
        aboutJavaOrSpring.and(nonBlank);
```

then `unsafe.test(null)` throws a `NullPointerException` because `contains(...)` is called before the null check.

### Java 17+ program with a list containing null

Save `NullSafePredicateDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.Predicate;

public class NullSafePredicateDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                null, "", "  ", " Java ", "Spring", "Py");

        Predicate<String> nonBlank =
                s -> s != null && !s.isBlank();
        Predicate<String> relevant =
                s -> s.contains("Java") || s.contains("Spring");

        List<String> result = input.stream()
                .filter(nonBlank.and(relevant))
                .map(String::trim)
                .toList();

        System.out.println(result);
    }
}
```

Compile/run:

```bash
javac NullSafePredicateDemo.java
java NullSafePredicateDemo
```

Output:

```text
[Java, Spring]
```

The example uses `Arrays.asList(...)` because `List.of(...)` **does not accept null elements**. In `filter(nonBlank.and(relevant))`, null and blank elements are eliminated before `relevant.test(...)` is called. Afterward, `map(String::trim)` only operates on the retained strings.

If you do not need to create separate Predicates, you can use:

```java
stream.filter(java.util.Objects::nonNull)
      .filter(Predicate.not(String::isBlank));
```

This is an illustrative pipeline snippet, assuming the variable `stream` has type `Stream<String>` and `Predicate` is imported. `Predicate.not(String::isBlank)` requires Java 11+. **Null must be filtered out first**; using `String::isBlank` directly on a null element will throw an error.

## 6. Composing Predicates in order and logical grouping

With three conditions A, B, C, the following two expressions have different meanings:

```text
(A AND B) OR C       differs from       A AND (B OR C)
```

Since composition methods return a new Predicate, you can describe the exact structure:

```java
Predicate<Product> first =
        conditionA.and(conditionB).or(conditionC);

Predicate<Product> second =
        conditionA.and(conditionB.or(conditionC));
```

This is an **illustrative code snippet** in a context where three `Predicate<Product>` variables already exist.

Because method calls chain from left to right, `conditionA.and(conditionB).or(conditionC)` corresponds to `(A && B) || C`. Meanwhile, `conditionA.and(conditionB.or(conditionC))` corresponds to `A && (B || C)`.

For example, the rule “in stock and (cheap or on sale)” should be expressed as:

```java
Predicate<Product> eligible =
        available.and(cheap.or(onSale));
```

You should not write `available.and(cheap).or(onSale)` if **every** product must be in stock: the latter expression could allow an out-of-stock product that is on sale to pass through.

When combining multiple `negate()` calls, remember De Morgan's laws:

- `!(A && B)` is equivalent to `!A || !B`.
- `!(A || B)` is equivalent to `!A && !B`.

For example, `eligible.negate()` can be used to get all products that **do not satisfy** the eligibility rule. However, a Predicate with a negative-sounding name like `notEligible` should be clearly documented when the condition has multiple branches to avoid misreading the intent.

## 7. Multiple `filter` calls or one `filter` with a composed Predicate?

Two common styles:

```java
List<Product> result = products.stream()
        .filter(inStock)
        .filter(minPrice)
        .filter(maxPrice)
        .toList();
```

and:

```java
Predicate<Product> eligible =
        inStock.and(minPrice).and(maxPrice);

List<Product> result = products.stream()
        .filter(eligible)
        .toList();
```

These are code snippets inside a method, assuming `products` and the Predicates are declared with the appropriate types. With **pure, deterministic conditions without side effects**, they express the same result: keeping only elements that pass all conditions.

However, note:

- Use multiple `filter` calls when you want to present a linear pipeline where each stage is easy to inspect.
- Use a single composed `Predicate` when you want to **name a business rule**, reuse it across multiple collections/APIs, test `test(...)` independently, or express complex OR/NOT logic.
- §filter§ is an intermediate Stream operation: the pipeline is typically evaluated when there is a terminal operation such as `toList()`, `count()`, or `findFirst()`.
- Both `Predicate.and/or` and `Stream.filter` can short-circuit under appropriate conditions; do not attach side effects to a Predicate and assume it will run exactly once for every element in every pipeline, especially parallel pipelines or early-terminating terminal operations.

The compiler guarantees that the Predicate's parameter type matches the Stream's element type. It does **not** guarantee that the business condition is written correctly, throws no exceptions, or is thread-safe. Those must be evaluated separately.

## 8. Extracting Predicates into reusable factory methods

When an application has optional conditions from a search filter, you can start with a Predicate that always returns true and then compose the conditions provided by the user. This keeps filter-building code easy to test.

Save `DynamicPredicateDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class DynamicPredicateDemo {
    record Employee(String name, String department, int age) {}

    static Predicate<Employee> buildFilter(
            String department, Integer minAge) {
        Predicate<Employee> filter = employee -> true;

        if (department != null && !department.isBlank()) {
            filter = filter.and(
                    employee -> employee.department().equals(department));
        }

        if (minAge != null) {
            filter = filter.and(employee -> employee.age() >= minAge);
        }

        return filter;
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("Anna", "Sales", 28),
                new Employee("Binh", "IT", 34),
                new Employee("Chi", "IT", 22),
                new Employee("Dung", "IT", 40)
        );

        Predicate<Employee> itAdults = buildFilter("IT", 30);
        System.out.println(
                employees.stream()
                        .filter(itAdults)
                        .map(Employee::name)
                        .toList());

        Predicate<Employee> all = buildFilter(null, null);
        System.out.println(
                employees.stream()
                        .filter(all)
                        .map(Employee::name)
                        .toList());
    }
}
```

Run:

```bash
javac DynamicPredicateDemo.java
java DynamicPredicateDemo
```

Output:

```text
[Binh, Dung]
[Anna, Binh, Chi, Dung]
```

Explanation:

1. `employee -> true` is the starting point that always lets elements pass, equivalent to the identity element of AND.
2. When a valid `department` is present, compose the department comparison.
3. When `minAge` is present, compose the age threshold.
4. The returned result is a configured `Predicate<Employee>`, which can be passed to `filter` or used directly via `test`.

The parameters `department` and `minAge` are captured by the lambdas because they are **effectively final** (never reassigned inside the method). There is no need to create a separate Strategy class for these two small conditions.

This is a minimal example. With real-world input, you need to decide whether comparison is case-sensitive, how to handle null in the `department()` field, validate `minAge >= 0`, and bound large datasets. If `employee.department()` can be null, `employee.department().equals(department)` will throw an error; it can be changed to `department.equals(employee.department())` after verifying `department != null`, or use §Objects.equals§.

## 9. `Predicate.not`, `isEqual`, and shorthand forms

### 9.1. `negate()` and `Predicate.not(...)`

Both create a negated Predicate. Example:

```java
Predicate<String> blank = String::isBlank;

Predicate<String> nonBlank1 = blank.negate();
Predicate<String> nonBlank2 = Predicate.not(String::isBlank);
```

This is a declaration inside a method with `java.util.function.Predicate` imported, assuming non-null input data. Both Predicates return true for non-blank strings. `Predicate.not` is especially useful for passing a method reference directly into `Stream.filter(...)`, where writing `String::isBlank.negate()` is not valid syntax.

**Does not handle null automatically:** both `blank.negate()` and `Predicate.not(String::isBlank)` call `String.isBlank()` when testing. If the input can be null, you must compose a null-safe condition in front.

### 9.2. `Predicate.isEqual(...)`

The factory `Predicate.isEqual(targetRef)` creates an equality-checking condition according to `Objects.equals(targetRef, input)`, instead of forcing you to compare references:

```java
Predicate<String> isJava = Predicate.isEqual("Java");
Predicate<String> isNull = Predicate.isEqual(null);

System.out.println(isJava.test("Java")); // true
System.out.println(isJava.test(null));   // false
System.out.println(isNull.test(null));   // true
```

This is a code snippet inside a method. For objects whose `equals` is defined by value, the condition checks equality according to that contract; you should not replace it with `==` when the goal is content comparison. §isEqual(null)§ checks for null input according to §Objects.equals§.

## 10. Generic types and working across multiple APIs that accept Predicate

A Predicate must be compatible with the type of element being tested. For example, §Stream<String>.filter(...)§ requires an object compatible with `Predicate<? super String>`. Due to contravariance in the input parameter, a Predicate can be declared using a suitable **supertype**:

```java
Predicate<CharSequence> nonEmpty =
        text -> text.length() > 0;

// Valid: CharSequence is a supertype of String.
List<String> accepted = List.of("A", "", "BB").stream()
        .filter(nonEmpty)
        .toList();
```

This is a code snippet inside a method with `List` and `Predicate` imported. The result `accepted` is `["A", "BB"]`.

§Predicate<T>.and§ and §or§ accept `Predicate<? super T>`. Therefore, you can combine a condition declared on a supertype with a condition on a specific element type when the type relationship fits, without raw casts. When the compiler reports an error, check the direction of the type relationship rather than using an unsafe cast just to make the program compile.

Common APIs that accept Predicate: `Stream.filter(Predicate<? super T>)`, `Collection.removeIf(Predicate<? super E>)`, and search operations like `anyMatch`, `allMatch`, `noneMatch` on Stream. Even though they all accept a Predicate, their meanings differ:

- `filter(p)` keeps elements when `p.test(x)` is true.
- `removeIf(p)` **removes** elements from a mutable collection when `p.test(x)` is true.
- `anyMatch(p)` returns a boolean and can stop as soon as a matching element is found.
- `allMatch(p)` can stop as soon as a non-matching element is encountered; on an empty stream it returns true.
- `noneMatch(p)` can stop as soon as a matching element is encountered; on an empty stream it returns true.

Especially with `anyMatch/allMatch/noneMatch`, checks can stop early, so **do not use the number of Predicate invocations as a reliable element-counting mechanism**.

## 11. Primitive Predicates and boxing

If filtering integers, `Predicate<Integer>` works but can incur boxing/unboxing when combined with primitives. Java provides specialized functional interfaces for primitives such as `IntPredicate`, `LongPredicate`, and `DoublePredicate`, which also support `and`, `or`, and `negate` for their respective primitive types.

Java 17+ example:

```java
import java.util.function.IntPredicate;
import java.util.stream.IntStream;

public class IntPredicateDemo {
    public static void main(String[] args) {
        IntPredicate positive = n -> n > 0;
        IntPredicate even = n -> n % 2 == 0;

        System.out.println(
                IntStream.of(-2, 0, 1, 2, 3, 4)
                        .filter(positive.and(even))
                        .boxed()
                        .toList());
    }
}
```

Run:

```bash
javac IntPredicateDemo.java
java IntPredicateDemo
```

Output:

```text
[2, 4]
```

§IntStream.filter§ takes an `IntPredicate`, so the tested argument is `int` instead of `Integer`. §boxed()§ in the example is only used to convert the result into a boxed stream for §toList()§ when displaying, not as a requirement for performing the filter.

## 12. Exceptions, side effects, state, and concurrency

The best Predicates for filtering are typically **stateless**, do not mutate the data source, and return the same result for the same input in a stable context. Java does not enforce that Predicates be pure, but combining Predicates with side effects makes code unpredictable:

- If the left Predicate of `and` returns false, the right Predicate does not run.
- If the left Predicate of `or` returns true, the right Predicate does not run.
- If a Predicate throws an unchecked exception, the exception propagates out of `test` and can cause the terminal operation to fail.
- §Predicate.test§ does not declare checked exceptions. With APIs that throw checked exceptions like §IOException§, you must handle them according to the contract or design a different abstraction; you cannot let a lambda throw an unhandled checked exception and assign it directly to `Predicate<T>`.
- With parallel streams, the filter condition can be executed concurrently on multiple elements. Avoid writing to unsynchronized mutable collections, mutating counters unsafely, or relying on log print order.
- When data or conditions have mutable state, reordering Predicates can change the output and the number of side effects. Ensure conditions have clear semantics before optimizing order.

There is no need to mechanically optimize cost by placing cheap/expensive conditions first. When Predicates have dependencies (such as a null-check before `String::length`), **safety and correctness of ordering are always mandatory constraints**. Only when conditions are independent, pure, and commutable should you consider placing conditions that filter out elements easily and have low cost first, and measure in practice if needed.

## 13. Common mistakes when combining filter conditions

1. **Placing a condition that requires non-null data before the null-check.** For example, `s -> s.length() > 2` running on null will throw an error; use `nonNull.and(longEnough)` in the right order.
2. **Confusing `and` with `or`.** “In stock and (cheap or on sale)” must use `available.and(cheap.or(onSale))`.
3. **Omitting grouping parentheses.** `A.and(B).or(C)` is not equivalent to `A.and(B.or(C))`.
4. **Assuming the right-hand Predicate always runs.** `and/or` short-circuits; do not use the right-hand condition to perform mandatory audit logging for every element.
5. **Overly generic lambda types or using raw types.** Declare `Predicate<Product>` and clear condition names; let the compiler catch type errors.
6. **Confusing `filter(p)` with `removeIf(p)`.** One keeps matching elements on a stream; the other removes matching elements from a mutable collection.
7. **Using §==§ to compare String contents.** Prefer `Objects.equals` or `Predicate.isEqual(value)` when value comparison is needed.
8. **Using `Predicate.not(String::isBlank)` directly on a potentially null source.** Negation does not replace a null-guard.
9. **Assuming `filter` runs immediately when chaining the pipeline.** Stream intermediate operations are typically lazy and require a terminal operation. Creating a new Predicate also does not mean `test` has been called.
10. **Relying on side-effect ordering when using parallel streams.** Keep Predicates stateless and safe for concurrent execution.
11. **Chaining Predicates of unrelated types.** A §Predicate<Employee>§ cannot be used directly to filter a §Stream<Product>§.
12. **Confusing boolean results with filtered data.** §filter§ does not turn elements into booleans; it keeps or discards the input objects themselves.

## 14. Self-check exercises

Given the list:

```java
List<Integer> numbers = List.of(-3, -2, 0, 1, 2, 3, 4, 8);
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;
Predicate<Integer> underFive = n -> n < 5;
```

The snippets above are written inside a method and require importing `List` and `Predicate`.

Predict on your own:

1. What does `numbers.stream().filter(positive.and(even)).toList()` return?
2. What does `numbers.stream().filter(positive.and(even.or(underFive))).toList()` return?
3. What is the result of `numbers.stream().filter(positive.and(even).negate()).toList()`?
4. If you replace `positive.and(even)` with `even.and(positive)` on this integer list, does the boolean result differ? What can differ when the two Predicates have side effects?
5. With §Predicate<String> nonNull = Objects::nonNull§ and §Predicate<String> startsJ = s -> s.startsWith("J")§, which composition allows §test(null)§ safely: `nonNull.and(startsJ)` or `startsJ.and(nonNull)`?

**Answers:**

1. `[2, 4, 8]` because those are the positive even numbers.
2. `[1, 2, 3, 4, 8]`: positive and (even or less than 5); 8 satisfies the even branch.
3. `[-3, -2, 0, 1, 3]`: negation of the condition “positive and even”.
4. Same boolean result because both are pure conditions on integers. When Predicates have side effects, call order and call count can differ due to short-circuiting.
5. `nonNull.and(startsJ)` is null-safe: `nonNull` returns false so `startsJ` does not run.

## 15. Practical rules

When building filters, express each condition with **one clearly named Predicate**, then compose them into a boolean expression that accurately reflects the requirement:

```text
keep element = (correct type / non-null)
              AND (satisfies business condition A)
              AND (B OR C)
              AND NOT (forbidden state)
```

For Streams, use `filter(composedPredicate)` to keep matching elements; use `test(value)` when testing an individual value. Read compositions from left to right with awareness of short-circuiting, verify generic types, guard null data before accessing it, and avoid side effects in conditions that may not be called.

**References:** Java SE API `java.util.function.Predicate` (§test§, §and§, §or§, §negate§, §not§, §isEqual§); `java.util.stream.Stream.filter§; `java.util.function.IntPredicate`; Java Language Specification on lambdas, functional interfaces, and short-circuit boolean operators.