# Target types of lambdas, method references, and conditional expressions

## Learning objectives

After this lesson, you will be able to:

- Understand **target typing** and **poly expressions** during the semantic analysis step of the Java compiler.
- Explain how `javac` finds the appropriate **functional interface** to check lambda expressions and method references; distinguish syntax, target type, the **SAM** signature, and the expression's type.
- Analyze contexts such as variable assignment, argument passing, method return, casting, and generic inference.
- Explain why conditional expressions `condition ? a : b` sometimes pass a target type down to both branches and sometimes determine their own type independently, especially when branches contain lambdas or method references.
- Identify and resolve compile errors caused by unresolvable overloads, missing functional-interface targets, or incompatible parameter or return types.
- Compile and test illustrative Java 17+ programs yourself using `javac` and `java`.

In Java, **not every expression has a type completely determined from the literal characters written**. Some expressions need information from *the use site*. That is the central focus of this lesson.

## 1. Target typing: context determines the required type

Consider the following two lines:

~~~java
IntUnaryOperator twice = value -> value * 2;
Predicate<Integer> positive = value -> value > 0;
~~~

Both lambdas use a parameter named `value`, yet the compiler interprets it under **different target types**:

| Expression | Target type | Single Abstract Method (SAM) | Inferred parameter type | Result type |
| --- | --- | --- | --- | --- |
| `value -> value * 2` | `IntUnaryOperator` | `int applyAsInt(int operand)` | `int` | `int` |
| `value -> value > 0` | `Predicate<Integer>` | `boolean test(Integer t)` | `Integer` | `boolean` |

In this example, `IntUnaryOperator` belongs to `java.util.function` and uses primitive `int`. `Predicate<Integer>` has reference parameter type `Integer`; in the comparison expression, Java can unbox it to `int`.

### Poly expressions and standalone expressions

- **Poly expression**: the expression's type or validity depends on a target type supplied by context. Lambdas and method references are classic cases: they require a functional-interface target.
- **Standalone expression**: its type is determined from the expression itself according to language rules, and only afterward is checked for convertibility to the outer required type. For example, literal `42` has type `int`. Many conditional expressions belong to this group.

This distinction appears immediately in compiler errors:

~~~java
// The lines below only illustrate errors and do not belong to a runnable program.
var operation = x -> x + 1;    // Error: lambda has no target type.
Object anything = x -> x + 1; // Error: Object is not a functional interface.
~~~

`var` requires the compiler to infer the local variable's type from its initializer, yet a lambda **does not carry a specific functional interface type on its own** for the compiler to infer. Similarly, a lambda cannot be assigned directly to `Object` because that target type has no SAM. The valid way is specifying a functional interface:

~~~java
IntUnaryOperator operation = x -> x + 1;
Object anything = (IntUnaryOperator) (x -> x + 1);
var inferred = (IntUnaryOperator) (x -> x + 1);
~~~

On the second and third lines, casting to `IntUnaryOperator` provides the target type; the resulting cast expression can then be assigned to `Object` or used as an initializer so `var` infers `IntUnaryOperator`.

### Contexts that commonly provide a target type

| Context | Example | Where does the target type come from? |
| --- | --- | --- |
| Variable assignment/initialization | `Runnable r = () -> run();` | Variable type `Runnable` |
| Argument passing | `execute(() -> run());` | Formal parameter type of `execute` after overload resolution |
| `return` | `return x -> x + 1;` | Return type of the enclosing method |
| Cast | `(Runnable) () -> run()` | Type inside the cast |
| Array initialization | `new Runnable[] { () -> run() }` | Element type `Runnable` |
| Branches of a reference poly conditional | `Runnable r = flag ? () -> run() : () -> stop();` | Target type propagated into the branches |

The lines with `run()`/`stop()` in the table only **illustrate syntax inside a class having the corresponding methods**, not standalone Java files.

Do not infer that any equals sign or call always supplies a single unique functional interface: if overloads exist, generics have not yet been inferred, or the target type is not a functional interface, the compiler must resolve additional constraints before accepting the lambda.

## 2. Functional interfaces and SAM are the foundation of target typing

Lambdas and method references are assigned to a **functional interface**, meaning an interface with exactly one *abstract method* counted according to Java rules. `default` methods, `static` methods, and certain methods matching public methods of `Object` do not increase the count of abstract methods to be implemented.

Example of a custom interface:

~~~java
@FunctionalInterface
interface IntTransformer {
    int transform(int input);
}
~~~

`@FunctionalInterface` tells the compiler to check the functional interface condition. This annotation helps catch changes that break “functional” status; an interface satisfying the rules can still be a functional interface even without the annotation.

Assigning a lambda:

~~~java
IntTransformer triple = input -> input * 3;
~~~

The compiler uses the SAM `int transform(int input)` to infer:

1. The lambda must have **one matching parameter**.
2. The inferred parameter has type `int`.
3. The body `input * 3` produces an `int` result, matching the SAM return type.
4. At runtime, `triple.transform(4)` gets result `12`.

This is a **compile-time compatibility** check. A lambda is not a class `IntTransformer` defined in source right at that location, and you do not have to write a manual anonymous class.

### 2.1 Lambdas are not tied to an arbitrary method's name or shape

One lambda can be compatible with **multiple functional interfaces** that have matching SAMs. For example:

~~~java
Runnable a = () -> System.out.println("x");
java.util.concurrent.Callable<String> b = () -> "x";
java.util.function.Supplier<String> c = () -> "x";
~~~

The lambdas above are checked against their individual targets. However, this does not allow writing a lambda expression **without a target type** and treating it as implicitly belonging to some “natural” interface.

Some familiar functional interfaces in `java.util.function`:

| Interface | SAM | Use case |
| --- | --- | --- |
| `Runnable` (in `java.lang`) | `void run()` | No parameters, returns no value |
| `Supplier<T>` | `T get()` | No parameters, returns a value |
| `Consumer<T>` | `void accept(T value)` | Takes one value, returns no value |
| `Function<T,R>` | `R apply(T value)` | Transforms one value into another |
| `Predicate<T>` | `boolean test(T value)` | Tests a condition |
| `IntUnaryOperator` | `int applyAsInt(int value)` | Transforms primitive `int` |
| `Comparator<T>` | `int compare(T a, T b)` | Compares two values |

**The SAM return type also matters.** `Runnable r = () -> 42;` is an error: literal `42` is not a *statement expression* suitable for a `void`-returning lambda. Conversely, `Supplier<Integer> s = () -> 42;` is valid because the SAM expects an `Integer` value (which can be boxed from `int`).

### 2.2 Lambda types depend on the SAM, not parameter names

The following two lambdas have the same effect under `IntUnaryOperator`:

~~~java
IntUnaryOperator first = n -> n + 1;
IntUnaryOperator second = number -> number + 1;
~~~

Renaming `n` to `number` does not change the parameter type or return value. Lambda parameter names serve only source-level scoping; the compiler checks shape, types, and body against the functional target.

## 3. Comprehensive example: same expression syntax, multiple target types

Create the file **`TargetTypingDemo.java`** with JDK 17+:

~~~java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class TargetTypingDemo {
    public static void main(String[] args) {
        IntUnaryOperator twice = n -> n * 2;
        Predicate<String> longName = s -> s.length() > 3;
        Function<String, Integer> size = String::length;
        Supplier<String> message = () -> "Xin chao Java";

        System.out.println("twice(4) = " + twice.applyAsInt(4));
        System.out.println("longName(Java) = " + longName.test("Java"));
        System.out.println("size(code) = " + size.apply("code"));
        System.out.println(message.get());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 -d out TargetTypingDemo.java
java -cp out TargetTypingDemo
~~~

Exact stdout:

~~~text
twice(4) = 8
longName(Java) = true
size(code) = 4
Xin chao Java
~~~

Explanation of how the compiler flows from context into the expression:

- With `twice`, the target type provides signature `int -> int`. `n` is interpreted as `int`; `n * 2` is valid and returns `int`.
- With `longName`, the target type `Predicate<String>` expects `String -> boolean`; therefore `s.length() > 3` is a valid boolean expression.
- With `size`, target `Function<String,Integer>` requires a `String -> Integer` transformation. The method reference `String::length` uses `String` as receiver and returns `int`, which is boxed into `Integer`.
- With `message`, the SAM `Supplier<String>.get()` takes no arguments and returns `String`.

**Common error:** if `Function<String,Integer> size` is changed to `Function<Integer,String> size` while keeping `String::length`, the compiler cannot match the target's parameter type `Integer` with the `String` receiver required by the method reference. Having a method of that name exist is not enough; **receiver, parameter count, parameter types, and return type** must all be compatible.

## 4. Lambdas: how does the compiler check parameters and body?

### 4.1 Inferred parameters vs explicitly declared parameters

When the target is clear:

~~~java
IntUnaryOperator implicit = x -> x + 1;
IntUnaryOperator explicit = (int x) -> x + 1;
~~~

Both are valid. With `implicit`, `x` gets type `int` from the target. With `explicit`, the compiler checks whether the declared `int` type matches the SAM.

A type-error example:

~~~java
// Illustrates compile error only:
IntUnaryOperator wrong = (String x) -> x.length();
~~~

`IntUnaryOperator` expects an `int` parameter, yet the lambda declares `String`, so it is incompatible. Only fixing the body or renaming the variable will not resolve this conflict.

### 4.2 `var` in lambda parameter lists differs from `var` in initializers

Since Java 11, `var` can be used to declare lambda parameters when the target is already known:

~~~java
java.util.function.BinaryOperator<Integer> add = (var a, var b) -> a + b;
~~~

Here the compiler still needs the target `BinaryOperator<Integer>` to determine the types of the two parameters. Using `var` in the parameter list **does not allow a standalone lambda to infer a functional interface on its own**.

Within the same lambda parameter list, one cannot arbitrarily mix explicitly declared types with inferred types or `var`, e.g., `(var a, Integer b) -> a + b` is invalid.

### 4.3 Body compatibility with `void`-returning or value-returning SAMs

Examples:

~~~java
Runnable print = () -> System.out.println("Hello");
Supplier<Integer> answer = () -> 42;
java.util.function.Consumer<String> consume = s -> System.out.println(s);
java.util.function.Function<String, Integer> measure = s -> s.length();
~~~

- A lambda targeting a `void`-returning SAM must have a **void-compatible** body.
- A lambda targeting a value-returning SAM must have a **value-compatible** body, producing a result convertible to the required return type.
- For block lambdas, every valid `return` must obey the return type: e.g., `return 42;` for a value-returning SAM and `return;` for a void-returning SAM. The compiler also checks control-flow paths.

Here are two valid block lambdas, illustrative code snippets inside a class/method:

~~~java
Runnable task = () -> {
    System.out.println("begin");
    System.out.println("end");
};

Supplier<Integer> makeNumber = () -> {
    int a = 20;
    int b = 22;
    return a + b;
};
~~~

An expression lambda such as `s -> s.length()` uses a method invocation, which is a *statement expression*; so depending on the target and overload context, the body can be considered void-compatible (discarding the result) or value-compatible (taking the result). This very property creates overloaded calls that are easily ambiguous.

### 4.4 Checked exceptions still must be compatible with the SAM

A lambda can throw a checked exception only when the SAM signature/exception-checking rules permit it.

Illustrative example inside a method allowed to throw exceptions:

~~~java
java.util.concurrent.Callable<String> read = () -> {
    throw new java.io.IOException("No data");
};
~~~

`Callable.call()` declares `throws Exception`, so the lambda can throw `IOException`. Meanwhile:

~~~java
// Error: Supplier.get() does not declare checked IOException.
java.util.function.Supplier<String> read = () -> {
    throw new java.io.IOException("No data");
};
~~~

Compiler flags or using a method reference do not automatically make checked exceptions disappear. You must handle the exception, use an appropriate interface, or provide an adapter with explicit rules.

## 5. In which contexts do target types appear?

### 5.1 Assignment context

~~~java
Predicate<String> nonEmpty = text -> !text.isEmpty();
~~~

The target sits right on the left of `=`. If changed to `Predicate<Integer>`, the body `text.isEmpty()` becomes invalid because `Integer` has no `isEmpty()` method.

### 5.2 Invocation context

When a call has a matching overload, the method's formal parameter provides the target:

~~~java
import java.util.function.IntUnaryOperator;

public class InvocationTargetDemo {
    static int evaluate(IntUnaryOperator transform) {
        return transform.applyAsInt(5);
    }

    public static void main(String[] args) {
        System.out.println(evaluate(x -> x * 3));
    }
}
~~~

Run:

~~~bash
javac -d out InvocationTargetDemo.java
java -cp out InvocationTargetDemo
~~~

Stdout:

~~~text
15
~~~

The compiler knows `evaluate` accepts `IntUnaryOperator`, so `x` is `int`. When multiple overloads exist, the compiler needs to evaluate expression compatibility against each candidate and apply specific method selection rules; sometimes no single unique target exists.

### 5.3 Return context

Inside a method returning a functional interface, the expression used at `return` receives its target from the return type:

~~~java
import java.util.function.IntUnaryOperator;

public class ReturnTargetDemo {
    static IntUnaryOperator transform(boolean negate) {
        return negate ? x -> -x : x -> x + 1;
    }

    public static void main(String[] args) {
        System.out.println(transform(true).applyAsInt(5));
        System.out.println(transform(false).applyAsInt(5));
    }
}
~~~

Compile/run:

~~~bash
javac -d out ReturnTargetDemo.java
java -cp out ReturnTargetDemo
~~~

Stdout:

~~~text
-5
6
~~~

The return type of `transform` is `IntUnaryOperator`, so both lambdas in the conditional expression are checked against this target. If the return type is changed to `Object` while still returning the lambdas directly, the compiler will not automatically pick a functional interface from them.

### 5.4 Cast context

~~~java
var operation = (IntUnaryOperator) (x -> x * 2);
System.out.println(operation.applyAsInt(5));
~~~

This is an illustrative snippet that must be placed inside a method with `IntUnaryOperator` imported. The cast provides the target and the result has type `IntUnaryOperator`, hence `var` can infer the variable type. Casting a lambda to a different functional interface causes parameters/body to be re-checked against the new target's SAM.

### 5.5 Array initializer context

~~~java
Runnable[] tasks = {
        () -> System.out.println("one"),
        () -> System.out.println("two")
};
~~~

Each element must be compatible with `Runnable`. There is no general rule that “any literal or collection automatically infers an interface” — in the array above, the `Runnable[]` component type itself supplies the target.

### 5.6 Generic invocation and target inference

See the standalone example **`GenericTargetDemo.java`**:

~~~java
import java.util.function.Function;

public class GenericTargetDemo {
    static <T, R> R mapOne(T source, Function<T, R> mapper) {
        return mapper.apply(source);
    }

    public static void main(String[] args) {
        String result = mapOne(21, n -> "value=" + n);
        System.out.println(result);
    }
}
~~~

~~~bash
javac -d out GenericTargetDemo.java
java -cp out GenericTargetDemo
~~~

Stdout:

~~~text
value=21
~~~

The compiler uses the value `21`, the `Function<T,R>` type of the second argument, the lambda body, and the `String` assignment context together to solve type inference constraints. This is a **combined semantic checking** process; it should not be described simply as “the compiler guesses the type from the name `n`”.

API calls such as `stream().map(String::length)` work by the same principle: the generic method provides the formal functional interface, and the compiler checks the method reference based on the stream element type and the result type to be inferred.

## 6. Method references also need a target type

A method reference uses `::` syntax. It is not an immediate invocation at the write site; it expresses an operation that can be assigned to a functional interface. The compiler needs a target SAM to determine how to match the receiver, parameters, and return type of the referenced method.

There are four common forms:

| Form | Example | How to interpret |
| --- | --- | --- |
| Static method reference | `Integer::parseInt` | Target supplies parameters to pass to the static method |
| Instance method reference with existing receiver (*bound*) | `word::toUpperCase` | Receiver `word` is already fixed; target supplies remaining parameters |
| Instance method reference via type (*unbound*) | `String::length` or `String::concat` | The first SAM parameter can serve as the receiver |
| Constructor reference | `StringBuilder::new`, `String[]::new` | Target supplies parameter count/types needed for the constructor or array creation |

### 6.1 Program illustrating the four forms

Create the file **`MethodReferenceTargetDemo.java`**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;

public class MethodReferenceTargetDemo {
    static String greet(String name) {
        return "Hello " + name;
    }

    public static void main(String[] args) {
        Function<String, String> staticMethod =
                MethodReferenceTargetDemo::greet;

        String word = "java";
        Supplier<String> bound = word::toUpperCase;

        ToIntFunction<String> unbound = String::length;
        BiFunction<String, String, String> concat = String::concat;

        Supplier<StringBuilder> constructor = StringBuilder::new;
        IntFunction<String[]> arrayConstructor = String[]::new;

        System.out.println(staticMethod.apply("An"));
        System.out.println(bound.get());
        System.out.println(unbound.applyAsInt("code"));
        System.out.println(concat.apply("Ja", "va"));
        System.out.println(constructor.get().append("ok"));
        System.out.println(arrayConstructor.apply(3).length);
    }
}
~~~

~~~bash
javac -d out MethodReferenceTargetDemo.java
java -cp out MethodReferenceTargetDemo
~~~

Exact stdout:

~~~text
Hello An
JAVA
4
Java
ok
3
~~~

Analysis:

- `MethodReferenceTargetDemo::greet` points to a static method taking `String` and returning `String`; matches `Function<String,String>`.
- `word::toUpperCase` is a **bound reference**, with receiver `word` already known; matches `Supplier<String>` because `toUpperCase()` needs no extra arguments and returns `String`.
- `String::length` with `ToIntFunction<String>` uses **the input string as receiver**, thus matching `String -> int`.
- `String::concat` with `BiFunction<String,String,String>` uses the first `String` as receiver and the second `String` as the argument to `concat`.
- `StringBuilder::new` matches the no-arg constructor under `Supplier<StringBuilder>`.
- `String[]::new` takes an `int` length to create an array; matches `IntFunction<String[]>`.

An easily confused point is the difference between:

~~~java
String word = "java";
Supplier<String> bound = word::toUpperCase;
Function<String, String> unbound = String::toUpperCase;
~~~

`bound.get()` takes no arguments because the receiver is already bound in the expression `word::...`. `unbound.apply("hello")` requires a string argument as its receiver. Having the same method name with different target SAMs is valid.

### 6.2 Overloaded method references are resolved via target

For example, `Integer::parseInt` has multiple overloads in the Java API. When assigning:

~~~java
java.util.function.ToIntFunction<String> parser = Integer::parseInt;
~~~

the target expects one `String` and returns `int`. The compiler locates the `parseInt` overload compatible in arity, parameter types, and result type. You do not write overload disambiguation with special syntax inside the method reference.

Conversely, if the target requires parameter types or a return type that cannot be adapted, the compiler reports no suitable method found even though `Integer.parseInt` definitely exists. **“A method with that name exists” is not enough**.

A method reference may be classified as *exact* or *inexact* for certain overload resolution steps; referencing an overloaded method may require a target to select among candidates. Consequently, when an outer call is also overloaded, the two selection layers can interact and lead to ambiguity errors.

### 6.3 Method references and lambdas can express equivalent operations

Two expressions:

~~~java
ToIntFunction<String> lengthByLambda = s -> s.length();
ToIntFunction<String> lengthByReference = String::length;
~~~

can both return string length. Yet not every lambda can be replaced by a method reference without re-checking target, overloads, receiver, exceptions, and generic types. One should not treat switching syntax as a guaranteed valid transformation in every circumstance.

### 6.4 Generic APIs using target typing for method references

Standalone example **`StreamReferenceDemo.java`**:

~~~java
import java.util.List;

public class StreamReferenceDemo {
    public static void main(String[] args) {
        List<Integer> lengths =
                List.of("A", "Java", "lambda")
                        .stream()
                        .map(String::length)
                        .toList();
        System.out.println(lengths);
    }
}
~~~

~~~bash
javac -d out StreamReferenceDemo.java
java -cp out StreamReferenceDemo
~~~

Stdout:

~~~text
[1, 4, 6]
~~~

`Stream.map` accepts a `Function<? super T, ? extends R>`. When the stream holds `String`, the reference `String::length` is checked as a conversion from `String` to a value compatible with `R`. The `int` type is boxed to `Integer`; context and generic inference produce a list of `Integer`. `Stream.toList()` has existed since Java 16, so this example is valid for Java 17+.

## 7. Overload resolution: why is the target sometimes ambiguous?

When multiple methods share the same name with different formal parameters, `javac` must decide which overload is invoked. The lambda/method reference may then need a target from the overload — while the compiler simultaneously needs to inspect the expression to select the overload. Java has specific rules for checking **potential compatibility**, **applicability**, and **most specific method**; it does not simply glance at the lambda's return type and pick arbitrarily.

### 7.1 A lambda compatible with two functional interfaces

The following example **intentionally does not compile**:

~~~java
import java.util.function.Supplier;
import java.util.concurrent.Callable;

class AmbiguousCall {
    static void use(Supplier<String> source) {}
    static void use(Callable<String> source) {}

    static void example() {
        use(() -> "done"); // Error: cannot determine a unique overload.
    }
}
~~~

Both `Supplier<String>.get()` and `Callable<String>.call()` take zero parameters and return `String`. The lambda `() -> "done"` fits both; there is no sufficient reason for the compiler to pick one automatically.

Resolve by **casting to the intended interface** or using an explicitly typed variable:

~~~java
use((Supplier<String>) () -> "done");

// Inside a method with the types imported:
Supplier<String> supplier = () -> "done";
use(supplier);
~~~

Both fixes illustrate valid calls inside class `AmbiguousCall`, though running requires adding `main` or using them in another program. Casting does not “pick the lambda's type after the lambda already has a type”; it provides the target type right when the compiler checks the lambda.

### 7.2 Two overloads whose SAMs take the same parameters but have different return types

Another case:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

class BodyCompatibilityExample {
    static void choose(Consumer<String> consumer) {}
    static void choose(Function<String, Integer> function) {}

    static void example() {
        // Possibly ambiguous: s.length() is a method invocation,
        // which can be used as a statement expression
        // or as a value expression.
        choose(s -> s.length());
    }
}
~~~

This is an **error-illustration snippet**, not a file intended to run. An expression-form lambda whose body is the method call `s.length()` can satisfy a `void` requirement by discarding the result or satisfy expecting an `Integer` value after boxing. With both overloads considered together, such a call may fail to pick a unique method.

To express intent, write:

~~~java
choose((Function<String, Integer>) String::length);

choose((Consumer<String>) s -> {
    System.out.println(s);
});
~~~

Or assign the lambda/method reference to an explicitly typed variable before passing it to the overloaded method. Adding a cast in the right place is usually less ambiguous than accidentally altering the body.

### 7.3 Target typing differs from choosing overloads by outer return type

Java has no general rule that “looks at the receiving variable type and always picks an overload by return type”. Overload selection relies primarily on name, parameter set, applicability, and most-specific rules. When generic inference or poly arguments participate, context can contribute constraints; however, you must not assume that simply wanting a `String` result makes the compiler pick an overload returning `String`.

An easily controlled approach: provide an explicit interface target for the lambda/method reference or redesign the API so overloads do not have nearly indistinguishable SAMs.

## 8. Conditional expressions `?:` and target types

Syntax:

~~~java
condition ? whenTrue : whenFalse
~~~

Java classifies conditional expressions into different categories under language rules. The key point here: a **reference conditional expression** can be a **poly expression** when appearing in an *assignment context* or *invocation context*. In that case, the outer target type is propagated down into both branches.

Not every `?:` is a poly expression. **Boolean** or **numeric** conditional expressions are classified and typed according to their own rules, normally as standalone expressions; one cannot infer that whenever `?:` appears, a target type will govern every branch the way it does for lambdas.

### 8.1 Two lambdas in a reference conditional

File **`ConditionalTargetDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class ConditionalTargetDemo {
    static int evaluate(IntUnaryOperator operation, int value) {
        return operation.applyAsInt(value);
    }

    public static void main(String[] args) {
        boolean increase = args.length > 0;

        IntUnaryOperator direct =
                increase ? x -> x + 1 : x -> x * 2;

        System.out.println("direct = " + direct.applyAsInt(4));

        int viaArgument = evaluate(
                increase ? x -> x + 1 : x -> x * 2,
                4
        );
        System.out.println("argument = " + viaArgument);
    }
}
~~~

Compile/run **without arguments**:

~~~bash
javac -d out ConditionalTargetDemo.java
java -cp out ConditionalTargetDemo
~~~

Stdout:

~~~text
direct = 8
argument = 8
~~~

Run **with any single argument**:

~~~bash
java -cp out ConditionalTargetDemo yes
~~~

Stdout:

~~~text
direct = 5
argument = 5
~~~

Explanation:

- In initializer `IntUnaryOperator direct = ...`, the target type is `IntUnaryOperator`. Both lambda branches are checked against SAM `int -> int`.
- In call `evaluate(...)`, the first parameter has type `IntUnaryOperator`. This type is used to check the poly conditional expression and its branches.
- Both branches are valid, yet only **the branch chosen at runtime** is evaluated per `?:` semantics.
- The compiler type-checks **both branches at compile time**; runtime conditions do not make a mistyped branch valid.

### 8.2 Without a target, the compiler cannot infer a functional interface

The following snippet is **intentionally invalid**:

~~~java
// Snippet illustrating a compile-time error:
boolean increase = true;
var operation = increase ? x -> x + 1 : x -> x * 2;
~~~

`var` does not supply a concrete functional interface for the two lambdas. A lambda has no standalone type for the compiler to conjure a common target type out of thin air.

This can be fixed with an explicit type on the left:

~~~java
IntUnaryOperator operation =
        increase ? x -> x + 1 : x -> x * 2;
~~~

Or supply targets via casts before using `var`:

~~~java
var operation = increase
        ? (IntUnaryOperator) (x -> x + 1)
        : (IntUnaryOperator) (x -> x * 2);
~~~

After casting, both branches are expressions with determined types. In a `var` initializer, the compiler has enough information to compute the type of the conditional expression and infer the variable type. Casting both branches is unnecessary if another design supplies an appropriate target, though explicit casts make the example clearer.

### 8.3 Same `?:`, yet branches have independent types

With primitive numeric operands:

~~~java
Number number = true ? 1 : 2L;
System.out.println(number.getClass().getSimpleName());
~~~

This snippet, placed inside a method, prints:

~~~text
Long
~~~

Because this is a **numeric conditional expression**, numeric promotion rules for `int` and `long` produce a value of type `long`, which is then boxed to `Long` for assignment to `Number`. The outer type `Number` does not cause the compiler to arbitrarily pick `Integer` on branch `1`. Do not confuse this mechanism with propagating targets into lambdas.

A reference conditional with two already-typed expressions can receive a target when in an assignment/invocation context:

~~~java
CharSequence text = true ? "Java" : new StringBuilder("JVM");
~~~

Both branches are convertible to `CharSequence`; the expression fits this target. However, if written as `var text = ...`, the compiler must infer the type from the condition and branches themselves under separate rules; do not assume the variable has the exact type `CharSequence` as in the explicitly declared example.

### 8.4 Lambdas/method references in `?:` branches

A conditional expression can choose between:

- Two lambdas.
- One lambda and one method reference.
- Two method references.
- One lambda and `null`, with an appropriate reference target.

Example inside a method importing `IntUnaryOperator`:

~~~java
IntUnaryOperator choose = flag
        ? x -> x + 1
        : Math::abs;
~~~

When `flag` is `false`, the compiler can match method reference `Math::abs` to type `int -> int`. When `flag` is `true`, the lambda branch shares the same target. This snippet is not a standalone program because variable `flag` needs to be declared.

### 8.5 Precedence and syntax

Do not rely on “eyeballing” multi-operator expressions to deduce targets. In particular, nesting `?:`, method invocations, casts, and lambdas easily causes scope confusion. Add parentheses whenever an expression is complex:

~~~java
IntUnaryOperator strategy = flag
        ? (x -> x + 1)
        : (x -> x * 2);
~~~

Parentheses here make the branches visually clear without altering the functional target. With casts, parentheses clearly determine whether a cast applies to the whole lambda or only part of the expression. Keeping examples simple and introducing explicitly typed intermediate variables is a good way to diagnose compiler errors.

## 9. Interaction among generic inference, conditionals, and overloads

An expression can be subject to multiple constraint sources:

1. The compiler identifies candidate overloads that may apply.
2. For generic methods, the compiler creates type inference variables and gathers constraints.
3. Lambdas/method references need a sufficiently concrete target type to check parameter count, body, result, and exceptions.
4. Reference poly conditionals propagate the target down to branches when contextual conditions hold.
5. The compiler finalizes method selection and types per language rules; if no unique/valid solution exists, it reports a compile-time error.

This is an explanatory model, not a guarantee that the compiler always executes an algorithm in exact five linear steps. The Java specification defines multiple interacting steps for applicability, inference, and most-specific resolution.

### Example: generic transform with a conditional expression

Create the file **`GenericConditionalDemo.java`**:

~~~java
import java.util.function.Function;

public class GenericConditionalDemo {
    static <T, R> R apply(T input, Function<T, R> operation) {
        return operation.apply(input);
    }

    public static void main(String[] args) {
        boolean upper = args.length > 0;

        String result = apply(
                "java",
                upper ? String::toUpperCase : String::toLowerCase
        );

        System.out.println(result);
    }
}
~~~

Compile/run:

~~~bash
javac -d out GenericConditionalDemo.java
java -cp out GenericConditionalDemo
~~~

Stdout:

~~~text
java
~~~

When running `java -cp out GenericConditionalDemo yes`:

~~~text
JAVA
~~~

At the `apply` call, the compiler infers the types of `T` and `R` from the `String` input, from the transformation in `Function<T,R>`, and from the assignment to `String`. The reference poly conditional is checked in the parameter context `Function<T,R>`; each method reference must conform to that function type. With the result here, both method references accept `String` as receiver and return `String`.

### Example: overloads altering target clarity

If an API has two overloads both accepting nearly equivalent functional interfaces, the target is no longer obvious. With code like:

~~~java
// Java-style pseudocode illustrating an overload case:
static void execute(java.util.function.Supplier<String> action) {}
static void execute(java.util.concurrent.Callable<String> action) {}

static void example() {
    // execute(() -> "OK"); // Ambiguous between two overloads.
    execute((java.util.function.Supplier<String>) () -> "OK");
}
~~~

The same lambda can be checked against multiple SAMs. Casting before the call clarifies which method is selected. If you own the API, you can design clearer method names so users are not forced to cast repeatedly.

## 10. Common compiler errors

| Symptom | Semantic cause | Fix |
| --- | --- | --- |
| “lambda expression needs an explicit target type” or “lambda expression not expected here” | No valid functional-interface target | Declare variable/return/parameter with a functional interface type or add the right cast |
| `var f = x -> x + 1` fails to infer type | `var` cannot synthesize a SAM from a lambda initializer | `IntUnaryOperator f = x -> x + 1` |
| `Object o = () -> 1` errors | `Object` is not a functional interface | `Object o = (Supplier<Integer>) () -> 1` |
| “incompatible parameter types in lambda expression” | Lambda declares parameters differing from the SAM signature | Check arity, types, and explicit/implicit parameters |
| “bad return type in lambda expression” | Body does not return a type compatible with the SAM | Choose an appropriate interface or fix body/return |
| “incompatible thrown types” | Body/method reference throws checked exceptions not permitted by the SAM | Handle the exception or use an interface declaring appropriate throws |
| “invalid method reference” | Receiver, overload, arity, or return type does not match SAM | Check referenced method, target, and bound/unbound form |
| “reference to ... is ambiguous” | Multiple overloads apply without a unique choice | Cast to the desired interface or use an intermediate variable |
| `var f = flag ? lambda1 : lambda2` errors | Conditional lacks a functional-interface target type for the lambdas | Place a functional type on the left or cast the branches |
| Conditional with `int` and `long` yields an unexpected type | This is a numeric conditional using numeric promotion rules | Distinguish numeric/boolean/reference conditionals, check boxing |
| Method reference has the right name yet fails to compile | Target checks parameter count/types, receiver, result, and throws | Write an equivalent explicitly typed lambda to spot the mismatch |

### How to handle confusing compiler messages

1. **Locate the expression.** Is the lambda/method reference in an assignment, return, argument, cast, or `?:` branch?
2. **Identify the target.** Write down the concrete functional interface type and SAM signature, including generic type arguments.
3. **Match arity and types.** Count parameters; for `Type::instanceMethod`, remember the first parameter may act as the receiver.
4. **Check the body.** Does it return a value, of what type, and are there checked exceptions?
5. **Consider overloads.** If two candidates exist, assign the lambda to a variable already having a functional type or add a cast to check each candidate separately.
6. **Consider `?:`.** Is it a numeric, boolean, or reference conditional? Is it in an assignment/invocation context propagating a target into branches?
7. **Check Java version limits.** For example, `var` in lambda parameters requires Java 11+, `Stream.toList()` requires Java 16+.

Read diagnostics across the entire error line and caret position; exact wording can differ across `javac` versions. Do not infer runtime/JVM errors from type errors already caught by the compiler before execution.

## 11. Practice exercises

### Exercise 1 — Identify the target of each expression

Given an illustrative snippet inside a method with corresponding imports:

~~~java
Runnable a = () -> System.out.println("A");
Supplier<Integer> b = () -> 10;
Predicate<String> c = s -> s.isBlank();
Function<String, Integer> d = String::length;
~~~

**Answers:**

- `a` has SAM `void run()`, lambda takes no arguments and returns void.
- `b` has SAM `Integer get()`, literal `10` is boxed.
- `c` has SAM `boolean test(String s)`.
- `d` has SAM `Integer apply(String s)`, uses `String` as receiver and then boxes `int`.

### Exercise 2 — Why does `var` reject lambdas?

~~~java
// Illustrating error:
var f = x -> x + 1;
~~~

**Answer:** A lambda is a poly expression requiring a functional interface as target. Just `var` on the left-hand side provides no functional type. Fix:

~~~java
IntUnaryOperator f = x -> x + 1;
~~~

### Exercise 3 — Find the error in a method reference

~~~java
// Illustrating error:
Function<Integer, String> wrong = String::toUpperCase;
~~~

**Answer:** For the unbound instance method `String::toUpperCase`, the target parameter must provide a `String` receiver, not `Integer`. Valid way:

~~~java
Function<String, String> upper = String::toUpperCase;
~~~

### Exercise 4 — Predict both branches

With `ConditionalTargetDemo` in section 8, predict stdout with no arguments and with one argument.

**Answer:** Without arguments: `direct = 8` and `argument = 8`. With an argument: `direct = 5` and `argument = 5`. The target type of both branches does not change; only branch selection changes.

### Exercise 5 — Resolve overload ambiguity

Two overloads accept `Supplier<String>` and `Callable<String>`. Why is `use(() -> "done")` ambiguous? How can it be resolved?

**Answer:** The same lambda is compatible with both targets. Explicitly cast to one of the two interfaces or assign to a variable of that type before calling `use`.

### Exercise 6 — Numeric conditional vs poly conditional

Consider:

~~~java
Number value = true ? 1 : 2L;
~~~

**Answer:** Both branches are numeric operands `int`/`long`; the expression has type `long` via numeric promotion, then boxes to `Long` when assigned to `Number`. The left-hand context does not propagate `Number` into each branch in the manner of a reference poly conditional.

## 12. Checklist before concluding a lambda/method reference is valid

- [ ] The expression site has a genuine **functional-interface target**, or an appropriate cast is present.
- [ ] The interface satisfies the functional interface definition with the required SAM.
- [ ] Parameter count and types of the lambda/method reference match the SAM.
- [ ] The body has a compatible return type, `void`/value form, and checked exceptions.
- [ ] For a method reference, the static, bound instance, unbound instance, or constructor form is correctly identified.
- [ ] If overloaded, all candidates have been considered and it is clear why the call has a unique choice.
- [ ] If `?:` is present, reference poly conditionals are distinguished from numeric/boolean conditionals.
- [ ] If generics are present, type inference constraints and necessary boxing/unboxing are confirmed.
- [ ] Test-compiled on the target JDK, rather than guessing solely from syntax.

## 13. Knowledge summary

**Target typing is the relationship between context and expression.** Lambdas and method references need a functional-interface target so the compiler can verify the SAM; they do not possess an arbitrary standalone type solely from their written syntax. A reference conditional `?:` can pass the target down to both branches in assignment/invocation contexts, allowing selection between two lambdas or method references. Yet numeric/boolean conditionals operate under separate type rules, and overloads or generic constraints can make target selection ambiguous.

When encountering an error, trace backward from **use site → target type → SAM signature → parameters/body/return/throws → overload/conditional/generic**. This analytical approach explains compile-time causes far better than randomly changing parentheses or casts until errors disappear.