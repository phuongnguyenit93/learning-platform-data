# Referencing Instance Methods via Type Name in Java

## 1. Concept and purpose

**Referencing an instance method via a type name** (reference to an instance method of an arbitrary object of a particular type) has the form:

```java
TypeName::instanceMethod
```

Examples: `String::trim`, `String::length`, `String::startsWith`, `String::compareToIgnoreCase`, and `List<String>::size`. This is an **unbound instance method reference**. The object receiving the call (the receiver) is supplied when the functional interface's method is executed.

```java
Function<String, String> trimText = String::trim;
String result = trimText.apply("  Java  "); // "Java"
```

In the call `trimText.apply(...)`, the argument `"  Java  "` acts as the receiver of `trim()`. Java executes a call equivalent to `"  Java  ".trim()`. The expression `String::trim` itself **does not call** `trim()` when created.

This feature has existed since Java 8 and is commonly used with `Function`, `Predicate`, `BiPredicate`, `Comparator`, custom functional interfaces, and Stream pipelines. Its goal is to express "call this method on the object passed in" concisely when the operation already exists as a method.

## 2. Parameter mapping: the receiver comes first

Conceptually, when an instance method is declared as:

```java
ResultType instanceMethod(Arg1 a, Arg2 b);
```

then the reference `TypeName::instanceMethod` can match a single abstract method (SAM) that accepts, in order:

1. A receiver of type `TypeName` or a compatible reference type.
2. The arguments `Arg1`, `Arg2` that the instance method requires.
3. A return value compatible with `ResultType` (according to Java's conversion rules).

Mapping diagram:

```text
SAM.apply(receiver, arg1, arg2)
          │         │     │
          ▼         ▼     ▼
       receiver.instanceMethod(arg1, arg2)
```

For example, the same syntax can require a different number of SAM parameters depending on the method signature:

| Method reference | Compatible target type | Equivalent lambda |
| --- | --- | --- |
| `String::length` | `ToIntFunction<String>` | `s -> s.length()` |
| `String::trim` | `Function<String, String>` | `s -> s.trim()` |
| `String::isEmpty` | `Predicate<String>` | `s -> s.isEmpty()` |
| `String::startsWith` | `BiPredicate<String, String>` | `(s, prefix) -> s.startsWith(prefix)` |
| `String::equalsIgnoreCase` | `BiPredicate<String, String>` | `(a, b) -> a.equalsIgnoreCase(b)` |
| `String::compareToIgnoreCase` | `Comparator<String>` | `(a, b) -> a.compareToIgnoreCase(b)` |

Read the `String::startsWith` example: the method `startsWith(String prefix)` has **one** parameter in its declaration, but `BiPredicate.test(String, String)` has **two** parameters: `s` acts as the receiver, and `prefix` is passed to the method. The receiver is not the first parameter in `startsWith`'s declaration; it is the object before the dot when calling the method.

**Note:** Parameter count and return type must be checked against the *target functional interface*. You cannot deduce the full signature just by looking at `TypeName::methodName`, especially when the method is overloaded.

## 3. Standalone compilable Java 17+ example

Create the file `UnboundMethodReferenceDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.ToIntFunction;

public class UnboundMethodReferenceDemo {
    public static void main(String[] args) {
        Function<String, String> trimText = String::trim;
        ToIntFunction<String> countCharacters = String::length;
        BiPredicate<String, String> hasPrefix = String::startsWith;
        BiPredicate<String, String> sameIgnoringCase =
                String::equalsIgnoreCase;
        Comparator<String> compareIgnoringCase =
                String::compareToIgnoreCase;

        System.out.println("trim=" + trimText.apply("  Java  "));
        System.out.println("length=" + countCharacters.applyAsInt("lambda"));
        System.out.println("prefix=" + hasPrefix.test("functional", "func"));
        System.out.println("equal=" + sameIgnoringCase.test("JAVA", "java"));
        System.out.println("compare=" + compareIgnoringCase.compare("api", "API"));

        List<String> words = List.of(" Java ", " API ");
        List<String> normalized = words.stream()
                .map(String::trim)
                .map(String::toLowerCase)
                .toList();
        System.out.println("words=" + normalized);
    }
}
```

Compile and run:

```bash
javac UnboundMethodReferenceDemo.java
java UnboundMethodReferenceDemo
```

Stdout output:

```text
trim=Java
length=6
prefix=true
equal=true
compare=0
words=[java, api]
```

Explanation:

- `trimText.apply("  Java  ")` calls `trim()` on the passed string; the result has no leading/trailing whitespace.
- `countCharacters.applyAsInt("lambda")` calls `length()` on `"lambda"` and returns the `int` value 6. `ToIntFunction` avoids boxing to `Integer` compared to `Function<String, Integer>`.
- `hasPrefix.test("functional", "func")` is equivalent to calling `"functional".startsWith("func")`.
- `sameIgnoringCase.test("JAVA", "java")` compares two strings case-insensitively.
- `Comparator<String>` has the SAM `compare(a, b)`, so `String::compareToIgnoreCase` calls `a.compareToIgnoreCase(b)`.
- Each Stream element becomes the receiver of `trim()` and then `toLowerCase()` in turn; the `map` operations run when the terminal operation `toList()` is executed.

## 4. Comparison with other method reference forms

| Form | Example | Where does the receiver come from? |
| --- | --- | --- |
| `TypeName::instanceMethod` | `String::length` | The first argument when calling the SAM |
| `objectExpression::instanceMethod` | `text::length` | The `text` object specified when creating the reference |
| `TypeName::staticMethod` | `Integer::parseInt` | No receiver; all SAM arguments go straight to the static method |
| `TypeName::new` | `ArrayList::new` | Not a method call; creates a new object |

Comparison example:

```java
String text = "Java";

java.util.function.ToIntFunction<String> unbound = String::length;
java.util.function.IntSupplier bound = text::length;

System.out.println(unbound.applyAsInt("Hello")); // 5
System.out.println(bound.getAsInt());             // 4
```

`String::length` waits for any string when `applyAsInt` is called; `text::length` is already bound to the `text` variable (the object that the `text` expression evaluates to when creating the reference) and therefore `IntSupplier.getAsInt()` needs no parameters. The two methods `applyAsInt` and `getAsInt` belong to **two different functional interfaces**.

Do not confuse `String::length` with `String.length()`; the latter is not valid syntax to call an instance method using only a class name. When calling directly, you must have a receiver, such as `"Java".length()`.

## 5. Target typing, overloads, and generic types

A method reference is an expression that depends on the target type context. The compiler uses the SAM to select the matching method among overloaded versions, and verifies receiver/argument types, return type, and checked exceptions.

For example, `String.substring` has overloads taking one or two integers. Below, the SAM has **two** arguments in total (`String`, `Integer`), so the `substring(int beginIndex)` overload is selected:

```java
java.util.function.BiFunction<String, Integer, String> fromIndex =
        String::substring;

System.out.println(fromIndex.apply("functional", 4)); // tional
```

If you want to use `substring(int beginIndex, int endIndex)` via `String::substring`, the SAM needs three arguments in total: the receiver and two indices. You can declare a custom three-parameter functional interface to express that case; `BiFunction` only suffices for the receiver plus one argument.

Referencing a method on a generic type follows the same rule:

```java
java.util.function.ToIntFunction<java.util.List<String>> listSize =
        java.util.List<String>::size;

System.out.println(listSize.applyAsInt(java.util.List.of("A", "B"))); // 2
```

In the example above, the receiver has type `List<String>` and `size()` needs no arguments other than the receiver.

An example of polymorphism:

```java
java.util.function.ToIntFunction<CharSequence> sequenceLength =
        CharSequence::length;

System.out.println(sequenceLength.applyAsInt("Java"));                  // 4
System.out.println(sequenceLength.applyAsInt(new StringBuilder("ABC"))); // 3
```

`CharSequence::length` uses an instance call dispatched according to the actual object. Both `String` and `StringBuilder` implement `CharSequence`, so the same method reference works with both.

A standalone method reference has no arbitrarily inferred "function type" in Java. For example, `var f = String::length;` **does not compile** because there is no target functional interface to determine the signature. Use `ToIntFunction<String> f = String::length;` or pass it directly to an API with a clear SAM parameter.

## 6. Practical use cases

### Transforming and filtering elements in a Stream

```java
List<String> names = List.of(" Lan ", "", " Minh ");
List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(java.util.function.Predicate.not(String::isEmpty))
        .toList();
// cleaned: [Lan, Minh]
```

In `map`, each string is the receiver of `trim()`. In `filter`, the trimmed string is the receiver of `isEmpty()`. `Predicate.not(...)` negates the condition to drop empty strings. This snippet is illustrative and assumes `java.util.List` is imported.

### Sorting by property or direct comparison

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
Comparator<String> insensitive = String::compareToIgnoreCase;

List<String> items = List.of("pear", "a", "banana");
System.out.println(items.stream().sorted(byLength).toList());
// [a, pear, banana]
```

`comparingInt` needs an `int` key extractor function; `String::length` fits because it takes a `String` receiver and returns `int`. `Comparator<String>` needs two arguments, so `String::compareToIgnoreCase` also fits, but in the role of comparing two objects.

### Separating receiver and business argument

```java
BiPredicate<String, String> containsText = String::contains;

System.out.println(containsText.test("method reference", "reference")); // true
```

The call here is equivalent to `"method reference".contains("reference")`. This style is useful when both the receiver and the method argument are supplied at invocation time.

## 7. Common mistakes and how to avoid them

**1. Miscounting SAM parameters.** For `TypeName::instanceMethod`, you must count the receiver as the **first** parameter of the SAM:

```java
// Wrong: startsWith(String) needs both the receiver and the prefix.
// Predicate<String> p = String::startsWith;

// Right:
BiPredicate<String, String> p = String::startsWith;
System.out.println(p.test("Java", "Ja")); // true
```

**2. Confusing a type-name reference with a reference to a fixed object.** `String::toUpperCase` fits `Function<String, String>`; `"Java"::toUpperCase` fits `Supplier<String>` because no receiver parameter is needed in the SAM.

**3. Forgetting null checks.** In an unbound reference, if the first receiver argument is `null`, at runtime Java will fail with a `NullPointerException`:

```java
ToIntFunction<String> f = String::length;
// f.applyAsInt(null); // Throws NullPointerException when called.
```

Creating `f` does not access a receiver by itself. If data can be null, filter/check it or use a lambda with an explicit null policy, such as `s -> s == null ? 0 : s.length()`.

**4. Thinking `::` can always replace every lambda.** A method reference only fits if the SAM signature is compatible. If you need to reorder parameters, add conditions, handle null, or perform multiple steps, an explicit lambda is usually clearer:

```java
BiPredicate<String, String> beginsWith =
        (prefix, text) -> text.startsWith(prefix);
```

This snippet intentionally takes `prefix` first and then `text`; it cannot be replaced directly with `String::startsWith`, because that form takes `text` first.

**5. Ignoring overloads, return types, and checked exceptions.** Two methods with the same name may differ in argument count/types; Java selects based on the target type. The SAM must also accept the return type (or allow discarding the result in a `void` context) and satisfy checked exception rules. When compiler errors are cryptic, rewrite as a lambda with explicit parameter types to see the actual call.

**6. Misidentifying static methods or constructors.** `Integer::parseInt` has no receiver; `ArrayList::new` creates an object. Do not apply the "first parameter is the receiver" rule to every `TypeName::member` expression when the selected member is a static method.

## 8. Step-by-step process to verify whether a reference is valid

1. Identify the instance method to use and its exact signature, including overloads.
2. Choose a functional interface with the right result type; if the result is primitive, consider `ToIntFunction`, `ToLongFunction`, `ToDoubleFunction` to avoid boxing.
3. Place the receiver as the first SAM parameter, then place the method parameters in order.
4. Check method accessibility, type compatibility, overloads, and checked exceptions.
5. Convert to the equivalent lambda to self-check: `TypeName::m` → `(receiver, args...) -> receiver.m(args...)`.
6. Check whether receiver data can be null, along with execution timing (especially in Streams).

## 9. Self-check exercises

1. Declare a `BiPredicate<String, String>` using `String::endsWith` and test `test("Report.java", ".java")`.
2. For `String::charAt`, find a suitable standard functional interface that accepts the receiver and index, and returns `Character`.
3. Why is `ToIntFunction<String> f = String::length;` valid, while `IntSupplier f = String::length;` is not?

**Hints/answers:** (1) `BiPredicate<String, String> ends = String::endsWith;`, which returns `true`. (2) `BiFunction<String, Integer, Character> charAt = String::charAt;`; Java boxes `char` to `Character` and unboxes `Integer` to `int`. (3) The unbound `String::length` requires a `String` argument in the SAM, but `IntSupplier.getAsInt()` has no parameters.

Key point to remember: with **referencing an instance method via a type name**, the object receiving the call is passed **first** when the functional interface runs. Simply writing the equivalent lambda `receiver -> receiver.method()` (or `(receiver, arg) -> receiver.method(arg)`) lets you verify the exact meaning, parameter count, and data order.