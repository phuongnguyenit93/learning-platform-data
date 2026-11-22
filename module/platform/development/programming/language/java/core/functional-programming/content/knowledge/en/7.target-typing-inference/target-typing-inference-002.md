# Assignment, Argument Passing, Return, and Cast Contexts for Lambdas in Java

A lambda expression in Java **does not have a standalone type from its syntax alone**. The compiler needs a suitable **target type**, usually a functional interface, to determine parameter types, return type, and validate the lambda body. The target type appears in several contexts, especially **assignment**, **method argument passing**, **return statements**, and **casting**.

This is a core principle of Java 8+ and still applies in Java 17+: the exact same lambda such as `x -> x.length()` may be valid in one position and fail to compile in another, depending on the **SAM** (single abstract method) required by the context. Understanding this rule helps you read compiler error messages, design APIs that accept lambdas, and avoid unnecessary casts or type declarations.

## 1. Why Does a Lambda Need a Target Type?

Consider the expression:

~~~java
text -> text.length()
~~~

Standing alone, the expression does not tell us what type `text` has. If `text` is a `String`, `length()` returns `int`; if another type has a compatible `length()` method, the semantics could differ. Java does not assign a "generic function type" to a lambda expression and wait to convert it later.

The target type provides the **function descriptor** for the lambda:

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Here the compiler knows:

1. The target type is Function<String, Integer>.
2. The abstract method apply(String) accepts String and returns Integer.
3. The variable text in the lambda is inferred as String.
4. The call text.length() returns int, which can be **boxed** into Integer.

Conversely:

~~~java
// DOES NOT COMPILE: missing functional interface target.
var length = text -> text.length();
~~~

Although Java has allowed `var` for local variables since Java 10, **`var` does not create a target type for a lambda initializer**. Likewise, `Object` is not a functional interface, so a lambda cannot be assigned directly to `Object`:

~~~java
// DOES NOT COMPILE:
Object action = () -> System.out.println("hello");
~~~

To store it as an `Object`, you must give the lambda a target type first:

~~~java
Object action = (Runnable) () -> System.out.println("hello");
~~~

The cast to `Runnable` is what supplies the target type, and the resulting object can then be assigned to `Object`. When you want to call `run()`, you must use the appropriate type:

~~~java
((Runnable) action).run();
~~~

The two snippets above are illustrative code placed inside a method; a complete runnable example is in Section 9.

## 2. The Functional Interface Determines the Lambda Signature

A functional interface has one effective abstract method. A lambda must match the **parameter count**, **parameter types**, **return compatibility**, and **checked exception constraints** of the function descriptor.

| Target Type | SAM | Compatible Lambda |
| --- | --- | --- |
| Runnable | void run() | () -> System.out.println("go") |
| Supplier<String> | String get() | () -> "ready" |
| Consumer<String> | void accept(String) | text -> System.out.println(text) |
| Predicate<String> | boolean test(String) | text -> !text.isBlank() |
| Function<String,Integer> | Integer apply(String) | text -> text.length() |
| BiFunction<Integer,Integer,Integer> | Integer apply(Integer,Integer) | (a,b) -> a+b |
| Comparator<String> | int compare(String,String) | (left,right) -> left.compareTo(right) |

With the target type determined, either `(text) -> ...` or `text -> ...` can be used for a single parameter. With two or more parameters, parentheses are required. Inferred parameters do not need `String` or `Integer` written out; if you write explicit types, they must match the descriptor.

For example:

~~~java
java.util.function.Predicate<String> nonEmpty =
    (String text) -> !text.isEmpty();
~~~

This case and `text -> !text.isEmpty()` have the same behavior under the same target type.

**Important limitation:** not every interface annotated with `@FunctionalInterface` can be used with a lambda. If the SAM itself declares its own type parameter such as `<T> T identity(T x)`, the function descriptor is generic and a Java lambda cannot directly implement that generic abstract method. This differs from `Function<T,R>`, where the type parameters are at the interface level and are specialized by the target type.

## 3. Assignment Context

Assignment provides the most direct target type.

~~~java
java.util.function.Function<String, Integer> length =
    String::length;

java.util.function.Predicate<Integer> positive =
    number -> number > 0;

java.lang.Runnable report =
    () -> System.out.println("completed");
~~~

In all three cases, the type of the variable on the left-hand side is the target type. No cast on the lambda is needed. A method reference like `String::length` is also a **poly expression**, checked against the target type in the same way.

### 3.1. Target Type and Result Conversions

~~~java
java.util.function.Function<String, Number> size =
    text -> text.length();
~~~

The expression `text.length()` returns `int`. Java can box `int` to `Integer` and perform reference widening from `Integer` to `Number` according to type-compatibility rules in a lambda's return context. Therefore, a lambda returning `int` does not force the target to be `Function<String,Integer>`.

Conversely:

~~~java
// DOES NOT COMPILE: int is not compatible with result type Long.
java.util.function.Function<String, Long> invalid =
    text -> text.length();
~~~

There is no direct implicit conversion from the `int` result of `length()` to `Long` via a valid boxing chain here; use `(long) text.length()` if you want a `Long` result, or use `ToLongFunction<String>` if you want a primitive `long`.

### 3.2. A Lambda Object Can Be Reused After Assignment

~~~java
java.util.function.Function<String, String> normalize =
    text -> text.trim();

String name = normalize.apply("  An  ");
~~~

A lambda expression is checked against its target type at declaration; afterward, the value of type `Function<String,String>` can be passed elsewhere. This is different from expecting an untyped lambda to infer itself from an invalid context.

### 3.3. Limitations of `var`

Invalid:

~~~java
// DOES NOT COMPILE.
var normalize = text -> text.trim();
~~~

Valid:

~~~java
java.util.function.UnaryOperator<String> normalize =
    text -> text.trim();

var copiedReference = normalize;
~~~

On the second declaration, `var` infers its type **from the already-typed variable `normalize`**, not by inferring a target type directly for a lambda.

Since Java 11, you can use `var` in **lambda parameter declarations** if a target type exists:

~~~java
java.util.function.Function<String, String> upper =
    (var text) -> text.toUpperCase();
~~~

Here `(var text)` does not mean the lambda infers its own standalone type. The target `Function<String,String>` still determines that `text` is `String`. When using `var` in lambda parameters, you must follow the consistency rule and not arbitrarily mix `var` parameters with implicit or explicit parameter types in the same list.

## 4. Invocation Context (Argument Passing)

When calling a method that has a functional interface parameter, the **formal parameter** supplies the target type for the lambda:

~~~java
static String transform(
        String value,
        java.util.function.UnaryOperator<String> operation) {
    return operation.apply(value);
}
~~~

Call:

~~~java
String result = transform("java",
    text -> text.toUpperCase());
~~~

The compiler knows the second parameter requires `UnaryOperator<String>`, which has SAM `String apply(String)`. Therefore `text` is `String` and the result `text.toUpperCase()` is also `String`.

You do not have to create a `UnaryOperator` variable beforehand:

~~~java
java.util.function.UnaryOperator<String> upper =
    text -> text.toUpperCase();

String result = transform("java", upper);
~~~

Both ways are behaviorally equivalent. Use an inline lambda when the behavior is short and clear, or assign a variable when you need reuse or a descriptive name.

### 4.1. Custom Functional Interfaces Also Work

~~~java
@FunctionalInterface
interface StringRule {
    boolean accept(String text);
}

static boolean check(String value, StringRule rule) {
    return rule.accept(value);
}
~~~

Call:

~~~java
boolean valid = check("Java", text -> !text.isBlank());
~~~

Here **StringRule** is the target type, not `Predicate<String>`, even though the two interfaces have similar function descriptors. Java does not treat two differently named functional interfaces as having an inheritance or substitution relationship. A lambda is only converted to the specific target type chosen by the compiler.

### 4.2. Generic Methods and Argument Type Inference

A generic method often uses a callback:

~~~java
static <T, R> R convert(
        T input,
        java.util.function.Function<? super T, ? extends R> function) {
    return function.apply(input);
}
~~~

You can call:

~~~java
Integer length = convert("hello", text -> text.length());
~~~

The compiler combines information from the argument `"hello"` (relating to `T`), the assignment type `Integer` (relating to `R`), and the lambda. Do not think of the machine as "running the lambda first to find the type"; Java solves the type-constraint problem at compile time.

A method reference can also be inferred from context:

~~~java
int count = convert("hello", String::length);
~~~

For a lambda or method reference in a generic method, sometimes the compiler does not have enough information due to overloads or type constraints. The usual solution is to specify the target type via a typed variable, a type witness on the generic method, or an intentional cast, while also improving the API design if it is overly ambiguous.

### 4.3. Overloads and Ambiguity

Because a lambda can be compatible with multiple functional types, overloading sometimes causes errors:

~~~java
static void use(java.util.function.Function<String,String> fn) { }
static void use(java.util.function.UnaryOperator<String> fn) { }

// May cause ambiguity if written simply as:
use(text -> text.trim());
~~~

Even though `UnaryOperator<String>` extends `Function<String,String>`, most-specific method selection rules may resolve the overload based on signature structure; you should not assume that every overload involving two similar interfaces is ambiguous. An example that definitely requires distinguishing two independent target types:

~~~java
@FunctionalInterface
interface A { String go(String input); }

@FunctionalInterface
interface B { String go(String input); }

static void perform(A action) { }
static void perform(B action) { }

// DOES NOT COMPILE: the same lambda is compatible with both A and B.
perform(text -> text.trim());

// Specify the desired target type:
perform((A) (text -> text.trim()));
~~~

These snippets illustrate structures within the same class; the intentionally invalid line is only for analysis and is not part of the runnable program in Section 9.

**Good practice:** avoid overloading an API solely by functional interfaces of the same shape when callers need to pass lambdas. If a clear choice is needed, give the two methods different names, use a typed callback variable, or cast to express intent. A cast resolves the context when truly needed, rather than being a cure-all for every type-inference error.

## 5. Return Context

If a method has a functional interface return type, a lambda expression in a **return** statement is checked against that type:

~~~java
static java.util.function.Supplier<String> greeting() {
    return () -> "READY";
}
~~~

There is no need to assign the lambda to an intermediate variable. The method `greeting()` returns a `Supplier<String>`, and calling `greeting().get()` is what executes the behavior and returns `String`.

An example with a parameter:

~~~java
static java.util.function.Predicate<String> minLength(int minimum) {
    return text -> text.length() >= minimum;
}
~~~

The lambda captures the variable `minimum`. Because `minimum` is a parameter that is never reassigned in the method, it is effectively final and can be captured. Call:

~~~java
java.util.function.Predicate<String> atLeast4 = minLength(4);
System.out.println(atLeast4.test("Java")); // true
~~~

Distinguish **returning a lambda** from **executing a lambda**:

- `minLength(4)` creates/returns a `Predicate<String>` value.
- `atLeast4.test("Java")` is what applies the condition.
- The `minimum` variable is captured when the lambda is created, so each call to `minLength` with a different argument can produce a rule with a different threshold.
- If a lambda captures a mutable object, the effectively final requirement applies only to the local reference variable; the object itself can still be mutated.

### 5.1. Return Branches Can Share the Same Target Type

~~~java
static java.util.function.UnaryOperator<String> formatter(boolean trim) {
    if (trim) {
        return text -> text.trim();
    }
    return text -> text.toUpperCase();
}
~~~

Both lambdas are checked against **UnaryOperator<String>**, even though they perform two different behaviors. The return type must express the contract that the caller actually uses.

### 5.2. Return Type `Object` Does Not Supply a Lambda Target Type

~~~java
// DOES NOT COMPILE: Object is not a functional interface.
static Object missingTarget() {
    return () -> "hello";
}
~~~

If the API returns `Object` by design, you can supply the target type with a cast first:

~~~java
static Object typedThenBoxed() {
    return (java.util.function.Supplier<String>) () -> "hello";
}
~~~

However, this loses type information at the API boundary; if the caller needs a `Supplier`, prefer returning `Supplier<String>` directly. Casting to a functional interface only to store it as `Object` is usually a sign of an unclear design.

## 6. Casting Context

A cast to a functional interface can itself supply the target type:

~~~java
java.lang.Object action =
    (java.lang.Runnable) () -> System.out.println("RUN");
~~~

In the expression `(Runnable) () -> ...`, the compiler knows the lambda must implement `void run()`. The final value is allowed to upcast to `Object` because `Runnable` is a reference type.

You can invoke it directly when the cast is properly parenthesized:

~~~java
((java.util.function.Function<String, String>) String::trim)
    .apply("  done  ");
~~~

When connecting a cast result to another place, distinguish:

1. **A cast supplying a target type to type-check a lambda** at compile time.
2. **Casting an existing object to another interface**, which is only valid at runtime if the object actually implements that interface; otherwise, it can throw `ClassCastException`.

The second case is not a way to arbitrarily convert a `Function` lambda into a `Predicate`:

~~~java
java.util.function.Function<String, String> fn =
    text -> text.trim();

// Can throw ClassCastException if cast through Object:
java.util.function.Predicate<String> wrong =
    (java.util.function.Predicate<String>) (Object) fn;
~~~

The fact that both are functional interfaces does **not** make instances automatically implement every interface with a single-method SAM. To get a different behavior, create a new lambda/method reference with the appropriate target type.

### 6.1. Casts Help Disambiguate Overloads When Needed

~~~java
perform((A) (text -> text.trim()));
~~~

This cast selects target `A` for the lambda, thereby invoking the `perform(A)` overload. You can use a clearly named `A` variable instead of an inline cast:

~~~java
A trimAction = text -> text.trim();
perform(trimAction);
~~~

In business code, a separate variable or method name is usually easier to maintain than long chains of casts.

### 6.2. Casts Do Not Bypass SAM Rules

You cannot cast a lambda to just any interface if the interface does not have a compatible function descriptor:

~~~java
// DOES NOT COMPILE: List is not a functional interface.
Object invalid = (java.util.List<String>) (() -> "hello");
~~~

A cast also does not automatically fix a lambda that takes more parameters than the SAM, returns the wrong type, or throws checked exceptions outside the contract. The target type must be valid and the lambda body must be checked against it.

## 7. Conditional Contexts and Combining Multiple Expressions

Besides the four main contexts, a **conditional expression** can also receive a target type from outside when its branches are lambdas or method references.

~~~java
java.util.function.UnaryOperator<String> normalize =
    strict ? String::trim : String::toLowerCase;
~~~

If `strict` is a `boolean`, the target in the assignment is `UnaryOperator<String>`; both branches are checked against that target. Usage:

~~~java
String result = normalize.apply("  ABC  ");
~~~

If `strict = true`, the result is `"ABC"`; if `false`, with the example string above the result is `"  abc  "`. The two branches do not need to have the same behavior, but they must be type-compatible.

A version without a target will be invalid:

~~~java
// DOES NOT COMPILE: no target type for the lambdas.
var action = strict ? (x -> x.trim()) : (x -> x.toUpperCase());
~~~

You can add an explicit target type on the variable, or cast the branches to the desired functional type when needed. When branches have substantial responsibilities, a method returning a functional interface like `formatter(strict)` can be easier to read.

### 7.1. Array Initializers and Other Positions

When an array has a functional interface component type, each lambda in the initializer receives the target type:

~~~java
Runnable[] tasks = {
    () -> System.out.println("first"),
    () -> System.out.println("second")
};
~~~

You can call `tasks[0].run()` or `tasks[1].run()`. Similarly, a lambda appearing inside an expression that is given a target type in another poly-expression context works if Java's rules allow it. However, do not assume **every expression position** provides a target type: the `var` and `Object` cases already showed the limits.

## 8. Lambda Bodies Are Checked Against `void` or Return Type

The function descriptor determines compatibility with the lambda body.

### 8.1. Expression Body and Statement Body

~~~java
java.util.function.Function<String, Integer> size =
    text -> text.length();
~~~

`size.apply("Java")` returns `Integer` `4`. The same logic with a block body:

~~~java
java.util.function.Function<String, Integer> size =
    text -> {
        int count = text.length();
        return count;
    };
~~~

For void-compatible:

~~~java
java.util.function.Consumer<String> print =
    text -> System.out.println(text);
~~~

Calling `println` is a statement expression matching `Consumer.accept(String)` returning `void`. However, a lambda that produces a result as required by `Function` must produce a suitable return value on every normal completion path.

~~~java
// DOES NOT COMPILE: missing return for Function.
java.util.function.Function<String, Integer> invalid =
    text -> {
        text.length();
    };
~~~

### 8.2. Not Every Expression Body Is Compatible with `Consumer`

For example:

~~~java
// DOES NOT COMPILE: a comparison is not a statement expression.
java.util.function.Consumer<Integer> wrong =
    number -> number > 0;
~~~

`Predicate<Integer>` is the contract needed for this check:

~~~java
java.util.function.Predicate<Integer> positive =
    number -> number > 0;
~~~

Arithmetic or comparison operators that return values cannot arbitrarily serve as a `Consumer` lambda body. If you need a `Consumer` to perform a side effect, use an appropriate method call or assignment and make sure the side effect is clear.

### 8.3. Checked Exceptions Must Still Match

`Runnable.run` and `Function.apply` do not declare `IOException`. A lambda calling a method that can throw `IOException` must catch the error or use a custom functional interface with a matching `throws` clause:

~~~java
@FunctionalInterface
interface IOAction {
    void run() throws java.io.IOException;
}
~~~

With the `IOAction` type, a lambda can directly call a method that declares `throws IOException`. Assignment, argument, return, or cast contexts **do not automatically erase** checked exception rules.

## 9. Complete Runnable Java 17+ Program

This example directly demonstrates the four contexts you need to master:

- **Assignment:** `Function<String,Integer> length = String::length`.
- **Argument passing:** `transform("java", value -> value.toUpperCase())`.
- **Return:** `greeting()` returns `Supplier<String>`, `isNonBlank()` returns `Predicate<String>`.
- **Casting:** creating a `Runnable` via a cast and then assigning it to `Object`; another cast for a method reference right inside an invocation expression.
- It also includes examples of generic invocation, conditional target type, and `var` in a **lambda parameter list**.

Create the file **TargetTypingDemo.java**:

~~~java
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.UnaryOperator;

public class TargetTypingDemo {
    static String transform(String value, UnaryOperator<String> operation) {
        return operation.apply(value);
    }

    static Supplier<String> greeting() {
        return () -> "READY";
    }

    static Predicate<String> isNonBlank() {
        return text -> !text.isBlank();
    }

    static <T, R> R convert(T input, Function<? super T, ? extends R> function) {
        return function.apply(input);
    }

    static void execute(Runnable task) {
        task.run();
    }

    public static void main(String[] args) {
        Function<String, Integer> length = String::length;
        System.out.println("assignment=" + length.apply("Java"));

        System.out.println("argument=" +
            transform("java", value -> value.toUpperCase()));

        System.out.println("return=" + greeting().get());

        Object opaque = (Runnable) () -> System.out.println("cast=RUN");
        execute((Runnable) opaque);

        System.out.println("generic=" +
            convert("hello", String::length));

        UnaryOperator<String> normalize =
            true ? String::trim : String::toLowerCase;
        System.out.println("conditional=" + normalize.apply("  abc  "));

        Predicate<String> valid = isNonBlank();
        System.out.println("predicate=" + valid.test("Java"));

        Function<String, String> explicit =
            (var text) -> text.toUpperCase();
        System.out.println("var-parameter=" + explicit.apply("ok"));

        String castResult =
            ((Function<String, String>) String::trim).apply("  done  ");
        System.out.println("cast-result=" + castResult);
    }
}
~~~

Compile and run in the directory containing the file, using JDK 17 or later:

~~~bash
javac TargetTypingDemo.java
java TargetTypingDemo
~~~

Exact stdout:

~~~text
assignment=4
argument=JAVA
return=READY
cast=RUN
generic=5
conditional=abc
predicate=true
var-parameter=OK
cast-result=done
~~~

Line-by-line explanation:

1. `assignment=4`: `String::length` is assigned to `Function<String,Integer>`; `apply("Java")` returns `4`.
2. `argument=JAVA`: `transform` accepts `UnaryOperator<String>`, so the lambda `value -> value.toUpperCase()` knows `value` is `String`.
3. `return=READY`: `greeting` returns `Supplier<String>`; `get()` triggers the lambda.
4. `cast=RUN`: the `Runnable` cast supplies the target for the lambda before assigning to `Object`. Afterward, you must cast back when passing to `execute(Runnable)`.
5. `generic=5`: `convert` infers `T` from `"hello"`, `R` from the method reference `String::length` and the context; the result is `Integer` `5`, which is then concatenated to print.
6. `conditional=abc`: the target `UnaryOperator<String>` applies to both branches of `?:`; since the condition is `true`, `String::trim` is chosen.
7. `predicate=true`: the function returning `Predicate<String>` is used to check that the string `"Java"` is not blank.
8. `var-parameter=OK`: `(var text) -> ...` is valid syntax when `Function<String,String>` is already present as the target.
9. `cast-result=done`: the cast `Function<String,String>` supplies the target type for `String::trim` right inside the expression.

The sample is designed so that **intentionally invalid** code is not mixed into the runnable class. The invalid examples in the lesson are only for explaining the compiler and do not need to be copied into `TargetTypingDemo.java`.

## 10. How the Compiler Resolves Types: A Useful Order of Thought

When you see a lambda, you can trace it using these steps:

1. **Identify the expression's position:** is it being assigned, passed as an argument, returned from a method, or cast?
2. **Find the target type:** `Function<T,R>`, `Predicate<T>`, `Runnable`, or a custom interface?
3. **Read the SAM's function descriptor:** how many parameters? What are their types and return type? Are any checked exceptions allowed?
4. **Infer the lambda parameter types:** match explicit/implicit/`var` parameters against the descriptor.
5. **Check the lambda body:** is the expression or block compatible with the return/`void` type and `throws` of the SAM?
6. **If calling a generic/overloaded method:** inspect type constraints from the arguments and result receiver; are there multiple remaining compatible overloads?
7. **If casting:** determine whether the cast is supplying a target for a new lambda expression or casting an existing runtime object.

This process explains why a lambda like `text -> text.isBlank()` works in `Predicate<String>` but does not work directly in an `Object` or `var` variable.

### 10.1. Side-by-Side Comparison

| Context | Valid | Reason |
| --- | --- | --- |
| Typed assignment | Predicate<String> p = s -> s.isBlank(); | SAM test(String) → boolean |
| Direct var assignment | var p = s -> s.isBlank(); | No | var does not provide a target |
| Argument passing | check("x", s -> s.isBlank()); | Yes, if the formal parameter is Predicate<String> or a compatible interface |
| Return | return s -> s.isBlank(); | Yes, if the method returns Predicate<String> |
| Cast | (Predicate<String>) (s -> s.isBlank()) | Yes | Cast explicitly specifies the target |
| Direct Object assignment | Object p = s -> s.isBlank(); | No | Object is not a functional interface |
| Object assignment after cast | Object p = (Predicate<String>) (s -> s.isBlank()); | Yes | Target is supplied by the Predicate<String> cast |

The table illustrates patterns in the exact contexts described; the identifiers `p`, `s`, and `check` must be inside a class/method with appropriate declarations when used in a complete Java program.

## 11. Common Mistakes

**Mistake 1 — thinking a lambda has an inherent `Function` type.** Java does not default every single-parameter lambda to `Function`; a lambda can target `Predicate`, `Consumer`, `UnaryOperator`, or a user-defined interface if the descriptor matches.

**Mistake 2 — using `var` for a variable initialized directly with a lambda.** There is no target type, so compilation fails. Use an explicitly declared functional interface or create a typed callback value first.

**Mistake 3 — assigning a lambda directly to `Object`.** `Object` has no SAM. You must supply a target type first via a variable or cast, though you should avoid losing the functional contract in APIs.

**Mistake 4 — looking only at the method name and ignoring overloads.** A lambda may match multiple SAMs; the compiler must select one overload per Java's rules. If ambiguous, place the callback in an explicitly typed variable or redesign the overloads.

**Mistake 5 — confusing `return` in a method with `return` in a lambda.** Inside a block lambda, `return` returns from that lambda's SAM invocation. It does **not** return from the enclosing method the way some other languages allow.

**Mistake 6 — casting to bypass type errors.** A cast can supply a target type, but it does not make a wrong parameter count, return type, or checked exception valid. Casting through `Object` between two incompatible interfaces can throw `ClassCastException`.

**Mistake 7 — mixing up `var` on a local variable with `var` on a lambda parameter.** `var x = x -> ...` fails for lack of a target; `Function<String,String> fn = (var x) -> ...` works because the target already exists.

**Mistake 8 — choosing the wrong interface for the lambda body.** `Predicate` requires `boolean`, `Function` requires a compatible value, and `Consumer` has a `void` result. A comparison expression `number > 0` cannot arbitrarily be the body of a `Consumer<Integer>`.

**Mistake 9 — assuming a method reference always fits.** `String::length` can target `Function<String,Integer>` or `ToIntFunction<String>`, but cannot be used where `Runnable` is expected because the descriptor takes no parameters.

**Mistake 10 — confusing compile-time inference with runtime behavior.** The compiler resolves the target type and generics at compile time. Invoking the lambda happens afterward; the JVM does not "re-infer" the target type from runtime input values.

## 12. Self-Check Questions

1. Why is `Function<String,Integer> f = s -> s.length();` valid while `var f = s -> s.length();` is invalid?
2. When a method accepts `Predicate<Order>`, from what information does the compiler infer the parameter type `order` in the lambda?
3. Why can a method returning `Supplier<String>` write `return () -> "ready";`, whereas one returning `Object` cannot do the same without a cast?
4. Is the cast `(Runnable) () -> System.out.println("ok")` casting an existing object or supplying a target type for the lambda expression?
5. What causes overloads accepting two interfaces with compatible descriptors to become ambiguous?
6. Why is `(var text) -> text.trim()` valid under the target `Function<String,String>` while `var action = text -> text.trim()` is invalid?
7. In the generic method `convert(T, Function<? super T,? extends R>)`, what information helps the compiler find `T` and `R`?
8. Why is a lambda returning `boolean` suitable for `Predicate<Integer>` but not naturally suitable for `Consumer<Integer>`?
9. If a method reference has multiple overloads, how does the target type help the compiler pick a specific method?
10. When refactoring a lambda from an assignment to a method argument, what SAM compatibility conditions should you re-check?

**Remember:** Lambdas in Java are **contextually typed**. Assignment supplies the type from the left-hand side; method calls supply the type from the parameter; `return` supplies the type from the return declaration; casts supply the type explicitly specified by the author. By understanding function descriptors, generic inference, and overload constraints, you can write concise lambdas while preserving type safety and accurately diagnosing compiler errors.