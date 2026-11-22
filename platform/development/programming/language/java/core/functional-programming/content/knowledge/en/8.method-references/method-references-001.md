# Method References and Their Equivalence to Lambdas in Java

## 1. What is a method reference?

A **method reference** is an expression using `::` to refer to an existing method or constructor and convert it into an implementation of a **functional interface**. Instead of writing a lambda just to call another method, you can refer directly to that method.

For example, the two expressions below have the same meaning for a `String` parameter:

~~~java
Function<String, String> a = s -> s.trim();
Function<String, String> b = String::trim;
~~~

Both `a.apply("  Java  ")` and `b.apply("  Java  ")` return `"Java"`. However, `String::trim` does not invoke `trim()` immediately at the declaration site: it creates a value whose type is a functional interface, so that the method is invoked when the interface's single abstract method (SAM) is executed.

The scope of this article is **the relationship between method references and lambdas**: how they are converted, how the compiler binds parameters, where they are equivalent, and what important differences exist. Lambdas, functional interfaces, and the Stream API are used as illustrative context.

## 2. The target type determines whether a method reference is valid

Java does not have an independent "method reference" type for storage. Like a lambda, a method reference is a **poly expression**: the compiler must know the *target type* is a functional interface, such as `Function<T,R>`, `Consumer<T>`, `Supplier<T>`, `Predicate<T>`, `Comparator<T>`, or an interface you define.

- `Function<String, Integer>` has the SAM `Integer apply(String s)`: takes a `String`, returns an `Integer`.
- `ToIntFunction<String>` has the SAM `int applyAsInt(String s)`: takes a `String`, returns an `int`.
- `Consumer<String>` has the SAM `void accept(String s)`: takes a `String`, does not need a return value.
- `Supplier<List<String>>` has the SAM `List<String> get()`: takes no parameters, returns a list.

Examples:

~~~java
Function<String, Integer> parse = Integer::parseInt;
ToIntFunction<String> length = String::length;
Consumer<String> print = System.out::println;
Supplier<List<String>> createList = ArrayList::new;
~~~

`Integer::parseInt` selects the overload compatible with `String -> Integer` (the `int` value is boxed into `Integer`). `String::length` takes a `String` object as the receiver and returns `int`. `System.out::println` already has a specific print stream bound as its receiver. `ArrayList::new` invokes the constructor when `get()` is called.

Note: these snippets assume `import java.util.*;` and `import java.util.function.*;`; the complete program in section 5 can be compiled standalone.

## 3. Four forms of method references and their corresponding lambdas

### 3.1. `static` method: `TypeName::staticMethod`

~~~java
Function<String, Integer> ref = Integer::parseInt;
Function<String, Integer> lambda = s -> Integer.parseInt(s);
~~~

Here the SAM parameter `s` is passed as the first argument to the static method. If the method has multiple parameters, they are forwarded in the corresponding order:

~~~java
BinaryOperator<Integer> maxRef = Math::max;
BinaryOperator<Integer> maxLambda = (a, b) -> Math.max(a, b);
~~~

The target type helps the compiler choose the overload; you cannot understand an overloaded reference just by looking at the method name while ignoring the SAM signature.

### 3.2. Instance method of a known object: `expression::instanceMethod`

~~~java
Consumer<String> ref = System.out::println;
Consumer<String> lambda = value -> System.out.println(value);
~~~

This is a **bound receiver**: the expression to the left of `::` is evaluated when *creating* the method reference, and the resulting object is kept as the receiver for subsequent calls. With `System.out::println`, no extra receiver parameter is needed in the SAM; `accept(value)` passes `value` to `println(value)` on the captured print stream.

Another example:

~~~java
String prefix = "Hello ";
Function<String, String> ref = prefix::concat;
Function<String, String> lambda = suffix -> prefix.concat(suffix);
~~~

In this example, calling `apply("Java")` on both gives `"Hello Java"`. Local variables captured by a lambda must be final or *effectively final*; see more on the difference in **receiver evaluation timing** in section 6.

### 3.3. Unbound instance method: `ReferenceType::instanceMethod`

~~~java
ToIntFunction<String> ref = String::length;
ToIntFunction<String> lambda = s -> s.length();
~~~

This is an **unbound receiver**: the first parameter of the SAM itself provides the receiver object. The remaining parameters of the SAM become the actual arguments to the method in order.

~~~java
Comparator<String> ref = String::compareToIgnoreCase;
Comparator<String> lambda = (left, right) -> left.compareToIgnoreCase(right);
~~~

`Comparator.compare(left, right)` has two parameters: `left` serves as the receiver of `compareToIgnoreCase`, and `right` is passed into the method. Therefore, it **must not** be mistakenly inferred as a static call `String.compareToIgnoreCase(left, right)`.

### 3.4. Constructor and array constructor: `TypeName::new`

~~~java
Supplier<ArrayList<String>> listRef = ArrayList::new;
Supplier<ArrayList<String>> listLambda = () -> new ArrayList<>();

Function<char[], String> textRef = String::new;
Function<char[], String> textLambda = chars -> new String(chars);

IntFunction<String[]> arrayRef = String[]::new;
IntFunction<String[]> arrayLambda = n -> new String[n];
~~~

A constructor reference does not create an object at the time `listRef`, `textRef`, or `arrayRef` is declared; the object/array is created when the SAM is called. Which constructor overload is chosen depends on the parameter types and return type of the SAM. With `String[]::new`, `n` is the array length.

## 4. How far should "equivalent to a lambda" be understood?

In terms of **mapping parameters to a method call**, each of the forms above has a lambda expression that expresses the same operation. For instance:

| Method reference | Lambda expressing the call | Parameter binding |
| --- | --- | --- |
| `Integer::parseInt` | `s -> Integer.parseInt(s)` | All parameters go to the static method |
| `printer::println` | `s -> printer.println(s)` | Receiver is already bound, `s` is the argument |
| `String::length` | `s -> s.length()` | `s` serves as the receiver |
| `String::compareToIgnoreCase` | `(a, b) -> a.compareToIgnoreCase(b)` | `a` serves as the receiver, `b` is the argument |
| `ArrayList::new` | `() -> new ArrayList<>()` | Invokes the no-arg constructor |
| `String[]::new` | `n -> new String[n]` | `n` is the array length |

It **does not mean** that syntactically swapping between the two forms always preserves the entire program behavior. You must consider receiver evaluation timing, `null` handling, overloads, target type, exceptions, and any additional operations in the lambda body. A method reference is simply a concise way to delegate to a method/constructor; it does not replace every lambda.

## 5. Complete runnable Java 17+ example

Save the file as `MethodReferenceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;

public class MethodReferenceDemo {
    public static void main(String[] args) {
        // Unbound instance method: s -> s.trim()
        Function<String, String> withLambda = s -> s.trim();
        Function<String, String> withReference = String::trim;
        System.out.println("lambda=" + withLambda.apply("  Java  "));
        System.out.println("ref=" + withReference.apply("  Java  "));

        List<String> words = List.of("  Java  ", "  Lambda  ", "  API  ");
        System.out.println(words.stream().map(String::trim).toList());

        ToIntFunction<String> lengthLambda = s -> s.length();
        ToIntFunction<String> lengthReference = String::length;
        System.out.println(
                lengthLambda.applyAsInt("Java")
                        == lengthReference.applyAsInt("Java"));

        // The first parameter of Comparator becomes the receiver of the method.
        List<String> names = new ArrayList<>(List.of("zoe", "Ana", "bob"));
        Comparator<String> ignoreCase = String::compareToIgnoreCase;
        names.sort(ignoreCase);
        System.out.println(names);

        // Constructor reference: () -> new ArrayList<String>()
        Supplier<List<String>> create = ArrayList::new;
        List<String> result = create.get();
        result.add("ok");
        System.out.println(result);

        IntFunction<String[]> createArray = String[]::new;
        System.out.println(createArray.apply(3).length);

        // Bound instance method: s -> System.out.println(s)
        Consumer<String> printer = System.out::println;
        printer.accept("done");
    }
}
~~~

Compile and run:

~~~bash
javac MethodReferenceDemo.java
java MethodReferenceDemo
~~~

Standard output (stdout):

~~~text
lambda=Java
ref=Java
[Java, Lambda, API]
true
[Ana, bob, zoe]
[ok]
3
done
~~~

Explanation: `map(String::trim)` is equivalent to `map(s -> s.trim())` for each source element, and then `toList()` creates the resulting list. `String::compareToIgnoreCase` demonstrates binding the receiver from the first parameter of `Comparator`. `ArrayList::new` creates a new list when `get()` is called; `String[]::new` creates an array when `apply(3)` is called. `System.out::println` is a bound instance method.

## 6. Semantic differences to remember

### 6.1. Receiver evaluation at bound reference creation time

Consider the standalone program `CaptureTimingDemo.java`:

~~~java
import java.util.function.Supplier;

public class CaptureTimingDemo {
    private static int calls;

    private static Greeter makeGreeter() {
        calls++;
        return new Greeter("Hi");
    }

    private record Greeter(String message) {
        String say() {
            return message;
        }
    }

    public static void main(String[] args) {
        Supplier<String> ref = makeGreeter()::say;
        Supplier<String> lambda = () -> makeGreeter().say();

        System.out.println("after creation=" + calls);
        System.out.println(ref.get());
        System.out.println("after reference=" + calls);
        System.out.println(lambda.get());
        System.out.println("after lambda=" + calls);
    }
}
~~~

~~~bash
javac CaptureTimingDemo.java
java CaptureTimingDemo
~~~

~~~text
after creation=1
Hi
after reference=1
Hi
after lambda=2
~~~

`makeGreeter()::say` calls `makeGreeter()` **once when creating the reference**; `ref.get()` only calls `say()` on the stored receiver. `() -> makeGreeter().say()` calls `makeGreeter()` **every time the lambda is invoked**. Therefore, when the expression on the left of `::` has side effects or returns different objects, the two expressions are not completely equivalent.

If the receiver refers to **the same mutable object**, both the method reference and the lambda still observe the latest state of that exact object when the method runs; "binding a receiver" does not mean capturing a copy of the object's state.

### 6.2. `null` and when errors occur

~~~java
String s = null;
Supplier<String> delayed = () -> s.toString(); // Lambda creation succeeds.
// delayed.get();                            // NullPointerException when calling SAM.
// Supplier<String> immediate = s::toString; // NullPointerException immediately on this line.
~~~

With a bound reference `s::toString`, the receiver `s` must be non-`null` immediately when evaluating the reference expression. With the lambda `() -> s.toString()`, the lambda body is only executed when `get()` is called. Meanwhile, an unbound reference `String::toString` can be created without an existing receiver; an error occurs if `apply` is later called with `null` in a way that leads to an instance call.

### 6.3. Lambdas can contain multiple operations; references only point to a compatible call

~~~java
Function<String, String> normalize = s -> s.trim().toUpperCase();
Predicate<String> valid = s -> s != null && !s.isBlank();
~~~

There is no single method reference directly equivalent to the entire `trim` then `toUpperCase` transformation or the two-condition check above, unless you define a method containing that logic and reference it. Lambdas also make it easy to set breakpoints, write multiple statements, catch errors locally, or handle special cases.

### 6.4. Overloads, generics, and target type

~~~java
Function<String, Integer> parse = Integer::parseInt;
ToIntFunction<String> parsePrimitive = Integer::parseInt;
~~~

The same method name, yet two target types yield different result types (boxing is needed for `Function`). With complex overloads, the compiler uses the SAM signature and overload resolution rules to determine the compatible method; sometimes you need to declare a specific type or use a lambda for clarity.

A method reference is not automatically valid for every functional interface. For example, `String::length` is valid for `ToIntFunction<String>`, but **not** suitable for `Supplier<Integer>` because `Supplier.get()` does not provide a `String` as a receiver.

### 6.5. Checked exceptions, return values, and `void`

Both lambdas and method references must conform to the parameter types, return type, and checked exceptions allowed by the SAM. A method reference pointing to a method declared with `throws IOException` cannot be used directly for `Function<String, String>` if the call needs to handle `IOException`, because `Function.apply` does not declare that checked exception. Use an appropriate interface or a lambda with `try/catch` when needed.

Java can ignore the return value of a call in a `void`-returning SAM context if the call is valid as a statement expression; however, you must not assume every return signature is suitable. The compiler is the source of truth for compatibility.

## 7. When to choose a method reference, and when to choose a lambda?

Choose a **method reference** when the entire lambda body simply forwards parameters to a clearly named method or constructor, such as `map(String::trim)`, `forEach(System.out::println)`, `sort(String::compareToIgnoreCase)`, or `Supplier<List<String>> factory = ArrayList::new`. This syntax directly expresses the intent to use an existing operation.

Choose a **lambda** when you need to chain multiple steps, check for `null`, reorder or transform parameters, express complex conditions, handle exceptions, or when a reference makes it hard for readers to identify the receiver/overload. For example, `stream.map(s -> s == null ? "" : s.trim())` expresses a custom policy that `String::trim` does not provide on its own.

A safe way to convert:

1. Identify the functional interface and its actual SAM signature.
2. Write the lambda call with clear parameters, receiver, return type, and checked exceptions.
3. Match it against one of the four `::` forms, noting that for an *unbound* instance method the first SAM parameter is the receiver.
4. Check whether it changes receiver evaluation timing, `null` behavior, or side effects.
5. Only shorten to a method reference if the new version preserves the intent and remains easy to read.

## 8. Common mistakes and how to fix them

| Mistake | Why it is wrong or misleading | How to fix |
| --- | --- | --- |
| Writing `String::trim()` | `::` references the method name, it does not call the method immediately | Use `String::trim` |
| Assigning `String::length` to `Supplier<Integer>` | The SAM does not accept a `String` receiver | Use `ToIntFunction<String>` or `Function<String,Integer>` |
| Assuming `String::compareToIgnoreCase` is static | It is an unbound instance method | Understand it as `(a,b) -> a.compareToIgnoreCase(b)` |
| Thinking `obj::method` evaluates `obj` when calling the SAM | A bound receiver is evaluated when creating the reference | Check side effects and `null` before replacing a lambda |
| Assuming any lambda can be converted to `::` | A lambda can perform multiple operations | Keep the lambda or extract the logic into a clearly named method |
| Ignoring overloads or exceptions | The target type determines which method is selected and its validity | Declare the SAM type explicitly; handle exceptions according to the signature |

## 9. Self-check

**Question 1.** Which lambda does `Function<String, String> f = String::toUpperCase;` correspond to?

Answer: `s -> s.toUpperCase()`. This is an unbound instance method; `s` is the receiver.

**Question 2.** Is `BiFunction<String, String, Boolean> f = String::startsWith;` valid?

Answer: yes. The first parameter is the `String` receiver; the second parameter is the prefix. The corresponding lambda is `(s, prefix) -> s.startsWith(prefix)`; the `boolean` value is boxed into `Boolean` for `BiFunction`.

**Question 3.** Given `Supplier<String> a = makeGreeter()::say;` and `Supplier<String> b = () -> makeGreeter().say();`, which one calls `makeGreeter()` immediately at declaration time?

Answer: `a`. `b` only calls `makeGreeter()` when `get()` runs.

**Question 4.** Why is `String::trim` not directly equivalent to `s -> s == null ? "" : s.trim()`?

Answer: the lambda has a branch to handle `null`, whereas calling `trim()` on a `null` receiver throws `NullPointerException`.

## Takeaways

A method reference is **a compact syntax for a call that can be adapted to a functional interface**, while a lambda expresses a function with a parameter list and an execution body. Equivalence only holds when the target type, parameter mapping, receiver, evaluation timing, exceptions, and observable effects all align. Understanding the four forms `Type::staticMethod`, `object::instanceMethod`, `Type::instanceMethod`, and `Type::new` helps you read and write functional Java code accurately.