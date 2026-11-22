# Recognizing Lambdas and Method References in API Calls — Java 17+

## 1. Spotting Syntax That Passes a Behavior to an API

When reading Java code, two common forms are:

~~~java
words.forEach(word -> System.out.println(word));
words.forEach(System.out::println);
~~~

Both pass a **behavior** to the `forEach` API: for each element, call `println`. The first form is a **lambda expression** with the `->` symbol; the second is a **method reference** with the `::` symbol.

You do not need to know every functional programming technique upfront to read them. Ask three questions:

1. Which method is the API calling (`forEach`, `map`, `removeIf`, `sort`, ...)?
2. What kind of behavior does the API require (what does it take, what does it return)?
3. How does the lambda or method reference supply that behavior?

**Key point:** a lambda or method reference produces a value of an appropriate **functional interface** type; creating it usually **does not execute the behavior body yet**. The API or a call to the corresponding abstract method triggers the behavior when appropriate.

## 2. Lambda: `parameter -> expression` or `parameter -> { ... }`

~~~java
x -> x * 2

(String text) -> text.length()

name -> {
    System.out.println("Hello " + name);
}
~~~

- To the left of `->` is the **parameter** list. A single parameter with an inferred type can omit parentheses: `x -> ...`; multiple parameters must use `(a, b) -> ...`.
- To the right is an **expression** or a **block**. If you need to return a value from a block, use `return expression;` when the target type expects a result.
- Parameter types are usually inferred from the **target type context** (*target typing*).

Example:

~~~java
java.util.function.IntUnaryOperator doubleIt = x -> x * 2;
System.out.println(doubleIt.applyAsInt(3));
~~~

**Exact stdout:**

~~~text
6
~~~

`IntUnaryOperator` has one abstract method `applyAsInt(int)`: it takes an integer and returns an integer. The lambda above is the implementation of that behavior.

## 3. Functional Interfaces Are the Target Type

A **functional interface** has exactly **one abstract method to implement** (*single abstract method / SAM*), excluding methods from `Object`. It may still have `default` or `static` methods.

| Functional interface | Primary method | Read as |
|---|---|---|
| `Consumer<T>` | `accept(T)` → `void` | Accepts a value to process, returns no result |
| `Predicate<T>` | `test(T)` → `boolean` | Checks a true/false condition |
| `Function<T,R>` | `apply(T)` → `R` | Transforms one value into another |
| `Supplier<T>` | `get()` → `T` | Supplies a value with no arguments |
| `Comparator<T>` | `compare(T,T)` → `int` | Determines the ordering of two elements |
| `Runnable` | `run()` → `void` | Action taking no arguments and returning no value |

When you see `items.removeIf(s -> s.isBlank())`, you can infer `removeIf` expects a `Predicate`, so the lambda must yield a `boolean`. When you see `items.forEach(s -> System.out.println(s))`, the API expects a `Consumer`, so the behavior needs no return value.

**Not every interface can serve as a target type for a lambda**: an interface with multiple independent abstract methods is not a SAM. The `@FunctionalInterface` annotation helps the compiler verify declaration intent, though lambdas do not require the interface to carry that annotation.

## 4. Method Reference: `::` Instead of a Forwarding Lambda

A method reference uses an **existing** method or constructor to satisfy a functional interface contract.

| Form | Example | Semantically equivalent lambda |
|---|---|---|
| Static method | `Integer::parseInt` | `s -> Integer.parseInt(s)` |
| Instance method of an existing object | `System.out::println` | `s -> System.out.println(s)` |
| Instance method of a passed-in object | `String::length` | `s -> s.length()` |
| Constructor | `StringBuilder::new` | `() -> new StringBuilder()` |

~~~java
java.util.function.Function<String, Integer> length = String::length;
System.out.println(length.apply("Java"));
~~~

**Exact stdout:**

~~~text
4
~~~

In `String::length`, the **receiving object** is the argument `"Java"`, so the API behaves like `s -> s.length()`.

For a method reference bound to a specific object:

~~~java
String prefix = "Hi ";
java.util.function.Function<String, String> greet = prefix::concat;
System.out.println(greet.apply("Java"));
~~~

**Exact stdout:**

~~~text
Hi Java
~~~

`prefix::concat` binds the receiver `prefix` when creating the method reference. It does not copy the `String` or call `concat` immediately. **Do not write `String::length()`**: a method reference takes only the method name after `::`, without call parentheses.

## 5. Reading `forEach`, `map`, `removeIf`, and `sort`

~~~java
List<String> names = List.of("An", "Binh");
names.forEach(System.out::println);
~~~

`forEach` takes a `Consumer<String>` and performs an action for each element. For this list, stdout is:

~~~text
An
Binh
~~~

Common APIs:

| Call | Reading |
|---|---|
| `names.forEach(System.out::println)` | Calls `println` on each element |
| `names.stream().map(String::length)` | Creates a stream of each `String`'s length |
| `mutable.removeIf(String::isBlank)` | Removes elements matching the predicate "empty or whitespace-only string" |
| `mutable.replaceAll(s -> s.toUpperCase())` | Replaces each element with its uppercase form |
| `mutable.sort(Comparator.comparingInt(String::length))` | Sorts by ascending length |

**Distinguish execution timing:** `Collection.forEach` performs its action when called. With `Stream.map`, building the pipeline is normally **lazy**; the transformation function is applied when a terminal operation runs, such as `toList()` or `forEach()`.

**Distinguish mutability:** `List.of(...)` returns an unmodifiable list; calling `removeIf`, `replaceAll`, or `sort` on it can throw `UnsupportedOperationException`. If you need to mutate the list, use `new ArrayList<>(List.of(...))`. The result of `Stream.toList()` in Java 16+ also disallows structural modification of the resulting list.

## 6. Why Lambdas Are Not Always Replaced by Method References

Both forms are normally equivalent when the lambda **merely forwards its argument** to one method:

~~~java
words.stream().map(word -> word.length()).toList();
words.stream().map(String::length).toList();
~~~

However, lambdas are very useful when extra computation or multiple steps are needed:

~~~java
words.stream().map(word -> word.trim().toUpperCase()).toList();
~~~

This snippet is not equivalent to a single method reference like `String::trim` because of the uppercase step. You can extract the logic into a named method `normalize` and write `ClassName::normalize` when the operation is reused.

**Watch out for overloads:** `System.out::println` has multiple overloads; Java picks the version matching the target type, such as `Consumer<String>`. You cannot treat a method reference as an "untyped" value in every context; it needs an appropriate target functional interface.

## 7. Variable Capture and Basic Errors

A lambda can use an outer local variable if that variable is `final` or **effectively final** (never reassigned):

~~~java
int threshold = 3;
java.util.function.Predicate<String> longEnough =
        text -> text.length() >= threshold;
System.out.println(longEnough.test("Java"));
~~~

**Exact stdout:**

~~~text
true
~~~

If you later write `threshold = 5;` in the same method, the lambda capturing `threshold` above will **fail to compile**, because the variable is no longer effectively final.

Distinguish **reassigning a reference** from **mutating an object's contents**: an effectively final local reference can still point to a mutable object, so a callback might observe state changes on that object. This can make code harder to reason about, especially in parallel streams; at an introductory level, prefer functions without unexpected side effects.

A lambda `x -> x + 1` is not a named method to call via `x(...)`; it is invoked through its functional interface, such as `op.applyAsInt(5)`.

## 8. Complete Java 17+ Program

Create file with exact name **`LambdaMethodReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Supplier;

public final class LambdaMethodReferenceDemo {
    private LambdaMethodReferenceDemo() {}

    static String normalize(String raw) {
        return raw.trim().toUpperCase(Locale.ROOT);
    }

    static void printTagged(String value) {
        System.out.println("word=" + value);
    }

    public static void main(String[] args) {
        List<String> raw = List.of(" java ", "go", " rust ");
        List<String> words = raw.stream()
                .map(LambdaMethodReferenceDemo::normalize)
                .toList();
        System.out.println("normalized=" + words);

        List<Integer> lengths = words.stream()
                .map(String::length)
                .toList();
        System.out.println("lengths=" + lengths);

        words.forEach(LambdaMethodReferenceDemo::printTagged);

        List<String> editable = new ArrayList<>(
                List.of("a", "", "bbb", "cc"));
        editable.removeIf(String::isBlank);
        System.out.println("filtered=" + editable);

        editable.replaceAll(s -> s.toUpperCase(Locale.ROOT));
        System.out.println("upper=" + editable);

        editable.sort(
                Comparator.<String>comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder()));
        System.out.println("sorted=" + editable);

        Predicate<String> longEnough = s -> s.length() >= 3;
        System.out.println("predicate=" + longEnough.test("JAVA"));

        Function<String, Integer> measure = String::length;
        System.out.println("function=" + measure.apply("RUST"));

        Consumer<String> printer = System.out::println;
        printer.accept("consumer=hello");

        Supplier<StringBuilder> supplier = StringBuilder::new;
        System.out.println("constructor="
                + supplier.get().append("OK"));

        String prefix = "Hi ";
        Function<String, String> bound = prefix::concat;
        System.out.println("bound=" + bound.apply("Java"));

        IntUnaryOperator doubleIt = n -> n * 2;
        System.out.println("lambda=" + doubleIt.applyAsInt(3));

        List<Integer> integers = List.of("2", "4").stream()
                .map(Integer::parseInt)
                .toList();
        System.out.println("parsed=" + integers);

        Runnable action =
                () -> System.out.println("runnable=executed");
        action.run();
    }
}
~~~

**Requirements:** JDK 17 or later, no Maven, Gradle, or libraries outside the JDK, and no preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 LambdaMethodReferenceDemo.java
java -cp . LambdaMethodReferenceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\LambdaMethodReferenceDemo.java
java -cp . LambdaMethodReferenceDemo
~~~

### Exact expected stdout

~~~text
normalized=[JAVA, GO, RUST]
lengths=[4, 2, 4]
word=JAVA
word=GO
word=RUST
filtered=[a, bbb, cc]
upper=[A, BBB, CC]
sorted=[A, CC, BBB]
predicate=true
function=4
consumer=hello
constructor=OK
bound=Hi Java
lambda=6
parsed=[2, 4]
runnable=executed
~~~

**Explanation:** `map` transforms strings and then takes lengths via a method reference; `forEach` uses a static method reference to `printTagged`. `removeIf` uses the predicate `String::isBlank`, `replaceAll` uses a lambda, and `sort` uses a comparator built from `String::length`. The `Supplier`, `Function`, and `Runnable` examples illustrate behaviors executed when the SAM method or corresponding API runs.

## 9. Exercises, Common Mistakes, and Checklist

| Mistake | Cause | Correct understanding |
|---|---|---|
| Thinking `x -> x * 2` is a computation that runs immediately | A lambda creates behavior to execute later | Requires an appropriate SAM/API call |
| Thinking `String::length` calls `length()` immediately | It is a method reference | Pass as an argument to an API expecting a functional interface |
| Writing `String::length()` | Invalid method reference syntax | `String::length` |
| Using `map` without a terminal operation and expecting effects | Stream pipelines are normally lazy | Call `toList`, `forEach`, ... |
| Calling `removeIf` on `List.of(...)` | The list does not support modification | Use `ArrayList` when mutation is needed |
| Using a lambda without a valid target type | Lambdas require a functional interface | Choose `Predicate`, `Function`, `Consumer`, ... |
| Capturing a local variable and then reassigning it | Not effectively final | Avoid reassigning or redesign |
| Confusing `Consumer` with `Function` | `Consumer` returns no result | Pick the functional interface matching the contract |

**Exercise A:** What does `List.of("A","BB").stream().map(String::length).toList()` return? **`[1, 2]`**.

**Exercise B:** What lambda is `names.forEach(System.out::println)` equivalent to? **`names.forEach(s -> System.out.println(s))`** in a `Consumer<String>` context.

**Exercise C:** What callback type does the `removeIf` API require? **`Predicate<E>`**, which has method `test(E)` returning `boolean`.

**Exercise D:** What does `StringBuilder::new` in `Supplier<StringBuilder>` mean? **A zero-argument behavior that creates a new `StringBuilder` when `get()` is called**, not creating an object just by writing the method reference.

### Checklist

- [ ] Recognize `->` as a lambda and `::` as a method reference.
- [ ] Know that a functional interface is the target type for a lambda/method reference.
- [ ] Distinguish `Consumer`, `Predicate`, `Function`, `Supplier`, `Comparator`, `Runnable`.
- [ ] Read static, bound-instance, unbound-instance, and constructor references.
- [ ] Understand callbacks execute when the API/SAM call triggers them, not when written.
- [ ] Distinguish intermediate stream `map` from terminal `toList`.
- [ ] Recognize which APIs mutate a list vs. which create a new result.
- [ ] Avoid capturing non-effectively-final local variables.
- [ ] Run `LambdaMethodReferenceDemo.java` with JDK 17+ and verify exact stdout.

**Conclusion:** When encountering `list.forEach(x -> ...)` or `stream.map(Type::method)`, read it as **passing a behavior to an API**. A lambda writes the behavior inline; a method reference reuses an existing method or constructor. The API's functional interface type dictates how the behavior receives arguments and returns results.