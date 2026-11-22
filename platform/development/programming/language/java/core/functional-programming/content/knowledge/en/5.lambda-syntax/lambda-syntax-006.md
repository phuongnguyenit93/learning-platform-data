# Using `var` in Lambda Parameters and Consistency Requirements in Java

## 1. What is `var` in a lambda used for?

Starting from **Java 11**, Java allows declaring parameters of a lambda expression using `var`. This is the **Local-Variable Syntax for Lambda Parameters (JEP 323)** feature, extending the `var` syntax that was added for local variables in Java 10.

For example, the following three expressions are all valid and perform the same addition of two integers if the target type is `BinaryOperator<Integer>`:

~~~java
java.util.function.BinaryOperator<Integer> a = (x, y) -> x + y;
java.util.function.BinaryOperator<Integer> b = (Integer x, Integer y) -> x + y;
java.util.function.BinaryOperator<Integer> c = (var x, var y) -> x + y;
~~~

These are illustrative statements placed inside a method or initializer block. With `a` and `c`, the parameter types are inferred from the functional interface. With `b`, the types are written explicitly as `Integer` and must be compatible with the target type.

**Most important takeaway:** `var` in lambda parameters **does not create a target type on its own** and **does not turn Java into a dynamically typed language**. The compiler still needs to know which *functional interface* is being implemented; from its single abstract method (*single abstract method*, SAM), it determines the type of each parameter.

`var` is especially useful when you need to declare an **annotation** or a modifier such as `final` on a lambda parameter while still letting the compiler infer the type. It is not required and does not inherently make a lambda run faster.

## 2. Three ways to write lambda parameters

With a functional interface taking two `String`s:

~~~java
java.util.function.BiFunction<String, String, String> join1 =
        (left, right) -> left + ":" + right;

java.util.function.BiFunction<String, String, String> join2 =
        (String left, String right) -> left + ":" + right;

java.util.function.BiFunction<String, String, String> join3 =
        (var left, var right) -> left + ":" + right;
~~~

All three ways are valid; `join1.apply("a", "b")`, `join2.apply("a", "b")`, and `join3.apply("a", "b")` all return `"a:b"`.

| Style | Example | How are parameter types determined? |
|---|---|---|
| No type written (*implicitly typed*) | `(left, right) -> ...` | Inferred from the target type's SAM |
| Explicit type (*explicitly typed*) | `(String left, String right) -> ...` | Written directly, must match the SAM |
| Using `var` (*inferred with var*) | `(var left, var right) -> ...` | Still inferred from the SAM; provides a place for annotations/modifiers |

The third style is a lambda with **inferred-type** parameters just like the first style, even though syntactically it has the `var` keyword. `var` does not mean a parameter can arbitrarily switch from `String` to `Integer` on each call.

If the SAM has two different types, parameters written with `var` **do not have to share the same type**:

~~~java
java.util.function.BiFunction<String, Integer, String> repeat =
        (var text, var times) -> text.repeat(times);
~~~

In this case, `text` is inferred as `String` and `times` as `Integer`. The `String.repeat(int)` method takes `int`, so `times` is unboxed to `int` when called. `repeat.apply("ha", 3)` returns `"hahaha"`.

## 3. Consistency rule: either all use `var`, or none do

When a lambda has two or more parameters, Java **does not allow mixing parameter declaration styles** in the same list. If you use `var` for one parameter, **every other parameter must also use `var`**.

### 3.1. Valid forms

~~~java
// Illustrative statements, all valid:
java.util.function.BiFunction<Integer, Integer, Integer> add1 =
        (a, b) -> a + b;

java.util.function.BiFunction<Integer, Integer, Integer> add2 =
        (Integer a, Integer b) -> a + b;

java.util.function.BiFunction<Integer, Integer, Integer> add3 =
        (var a, var b) -> a + b;
~~~

All parameters in a single lambda share the same *declaration style*: untyped, explicitly typed, or all using `var`.

### 3.2. Mixing `var` with untyped parameters: error

~~~java
// INTENTIONALLY INVALID — does not compile:
java.util.function.BiFunction<Integer, Integer, Integer> wrong =
        (var a, b) -> a + b;
~~~

Here `a` is declared with `var`, while `b` has only a name. The two styles cannot be mixed in the same list. To fix, use `(var a, var b)` or `(a, b)`.

### 3.3. Mixing `var` with explicit types: error

~~~java
// INTENTIONALLY INVALID — does not compile:
java.util.function.BiFunction<Integer, Integer, Integer> wrong =
        (var a, Integer b) -> a + b;
~~~

Similarly, `(Integer a, var b)` is invalid. Use `(Integer a, Integer b)` or `(var a, var b)`. The fact that both types ultimately resolve to `Integer` **does not** make the mixed syntax valid.

### 3.4. Cannot mix explicit types and untyped parameters either

Even before `var` was supported, the expression `(String a, b) -> ...` was invalid: it mixes an explicitly typed parameter with a name-only parameter.

Remember this rule by the **syntax of the entire list**, not by whether the parameters happen to have the same data type.

## 4. Using `var` with one parameter: parentheses are required

For a lambda with exactly one parameter, Java allows **omitting parentheses** if only a single parameter name is written:

~~~java
java.util.function.Function<String, Integer> length1 = text -> text.length();
java.util.function.Function<String, Integer> length2 = (text) -> text.length();
java.util.function.Function<String, Integer> length3 = (var text) -> text.length();
java.util.function.Function<String, Integer> length4 = (String text) -> text.length();
~~~

**Invalid:**

~~~java
// INTENTIONALLY INVALID — when using var, parentheses cannot be omitted:
java.util.function.Function<String, Integer> wrong = var text -> text.length();
~~~

The parentheseless form `text -> ...` can only be used when the parameter is **a single bare identifier**, without `var`, explicit type, annotation, or modifier. If `var` is needed, you must write `(var text) -> ...`.

For a lambda with **no parameters**, always use empty parentheses `() -> ...` and no `var`:

~~~java
java.util.function.Supplier<String> message = () -> "ready";
~~~

There is no syntax like `(var) -> ...`, because `var` must accompany an actual parameter name.

## 5. Complete Java 17 program: same target type, three uses of `var`

Save the following code in the file **`LambdaVarDemo.java`**:

~~~java
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaVarDemo {
    public static void main(String[] args) {
        Function<String, Integer> length = (var text) -> text.length();
        BiFunction<Integer, Integer, Integer> sum = (var a, var b) -> a + b;
        Predicate<String> nonBlank =
                (var text) -> text != null && !text.isBlank();

        List<String> words = List.of("Java", "FP", "lambda");
        words.forEach((var word) ->
                System.out.println(word + ":" + length.apply(word)));

        System.out.println("sum=" + sum.apply(2, 3));
        System.out.println("nonBlank=" + nonBlank.test("  "));
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac LambdaVarDemo.java
java LambdaVarDemo
~~~

Exact stdout result:

~~~text
Java:4
FP:2
lambda:6
sum=5
nonBlank=false
~~~

**Analysis:**

1. `Function<String, Integer>` has SAM `Integer apply(String)`, so in `(var text) -> text.length()`, `text` has type `String`.
2. `BiFunction<Integer, Integer, Integer>` has SAM `Integer apply(Integer, Integer)`, so `a` and `b` are inferred as `Integer`. The `+` operator triggers unboxing when summing, and the result is boxed per the return contract.
3. `Predicate<String>` has SAM `boolean test(String)`, so the `nonBlank` expression checks for `null` and empty/blank strings; for a two-space string it returns `false`.
4. `List<String>.forEach` takes `Consumer<? super String>`; thus `word` is inferred as `String`. The `(var word)` syntax does not change the list traversal order.
5. Using `var` on parameters does not change how `apply`, `test`, or `accept` are called. The lambda still follows the contract of the corresponding functional interface.

In this example, removing `var` and writing `text -> ...`, `(a, b) -> ...`, `word -> ...` still produces equivalent behavior.

## 6. Why is `var` useful when you want to attach annotations?

A practical reason JEP 323 allowed `var` in lambdas is to **preserve type inference while still having full parameter declaration syntax for adding annotations**.

For example, you might want to mark a parameter in source code for static analysis tools or annotation processors:

~~~java
@Marker var input
~~~

This is a parameter declaration part and must be inside the lambda's parentheses, such as `(@Marker var input) -> ...`. The annotation must be defined and have an appropriate `@Target`; `@Marker` in the example is just an illustrative name.

If you only write the shorthand lambda `input -> ...`, there is no full parameter declaration site to attach `@Marker`. You could write the explicit type `(@Marker String input) -> ...`, but sometimes you want the compiler to infer the type because it is long, generic, or already obvious from the target type. In that case, `(@Marker var input) -> ...` fits well.

### Runnable program: annotations and `final` with `var`

Save as **`LambdaAnnotationDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.SOURCE)
@interface NonEmptyContract {}

public class LambdaAnnotationDemo {
    public static void main(String[] args) {
        Function<String, String> normalized =
                (@NonEmptyContract var text) -> text.trim();

        BiFunction<String, String, String> join =
                (@NonEmptyContract final var left, var right) ->
                        left + "-" + right;

        Predicate<String> check =
                (@NonEmptyContract var text) -> !text.isEmpty();

        System.out.println(normalized.apply("  Java  "));
        System.out.println(join.apply("type", "safe"));
        System.out.println(check.test(""));
    }
}
~~~

Compile and run:

~~~bash
javac LambdaAnnotationDemo.java
java LambdaAnnotationDemo
~~~

Stdout:

~~~text
Java
type-safe
false
~~~

**Explanation:**

- `@Target(ElementType.PARAMETER)` allows `@NonEmptyContract` to be applied to parameter declarations; `RetentionPolicy.SOURCE` means the annotation is intended for source/compile-time and is not retained for querying at runtime.
- `(@NonEmptyContract var text)` lets Java infer the `String` type from `Function<String, String>`, while allowing an annotation on the parameter.
- `(@NonEmptyContract final var left, var right)` is valid: **both parameters use `var`**. `final` and the annotation are modifiers; they do not turn `left` into an explicitly typed parameter. `final` prevents reassigning the `left` parameter variable inside the lambda body.
- `@NonEmptyContract` in the example is **only a marker**, not automatically checking for empty strings or rejecting `null`. An annotation name is not a validation mechanism; if actual checking is needed, there must be corresponding logic or annotation-processing tooling.
- `check.test("")` still returns `false` even though the parameter has an annotation. This clearly illustrates that an annotation does not automatically alter the lambda's behavior.

Do not assume that every annotation on a lambda parameter will always be present when using reflection: that depends on target, retention, compilation, and metadata placement. In this example, the retention is `SOURCE`, so **runtime querying is not expected**.

## 7. `var` and `final`: consistent in **type**, not required to have identical modifiers

The "all use `var`" rule applies to the **parameter type declaration form**, not requiring every parameter to have the exact same annotations or modifiers.

Illustrative forms:

~~~java
java.util.function.BiFunction<String, String, String> combine1 =
        (var left, var right) -> left + right;

java.util.function.BiFunction<String, String, String> combine2 =
        (final var left, var right) -> left + right;

java.util.function.BiFunction<String, String, String> combine3 =
        (final var left, final var right) -> left + right;
~~~

All three are valid in Java 17+. `final` in a parameter declaration prevents reassigning that parameter itself, but **does not make the referenced object immutable**. For example, if the inferred type is `List<String>`, `final var list` still allows `list.add(...)` if the list is mutable.

Do not treat `final` as a way to "fix" a mixed-style parameter list: `(final var left, String right)` still violates the consistency requirement.

## 8. `var` is inferred **from the target type**, not inferred backward from the lambda body alone

A lambda does not have an independent type outside of context. The following example is **invalid**:

~~~java
// INTENTIONALLY INVALID: cannot infer a target type for the lambda expression.
var fn = (var value) -> value.length();
~~~

`var` on the **local variable on the left** needs to infer a concrete type from the initializer expression. However, the lambda on the right itself needs a functional interface *target type* to know what type `value` has. Neither side has enough information to infer a matching contract.

**The fix** is to provide a target type:

~~~java
java.util.function.ToIntFunction<String> fn =
        (var value) -> value.length();
~~~

Here `ToIntFunction<String>` defines the SAM `int applyAsInt(String)`; parameter `value` has type `String` and the expression `length()` returns `int`.

Do not confuse `var` on a **local variable** with `var` on a **lambda parameter**:

| Position | Example | Role |
|---|---|---|
| Local variable | `var count = 10;` | Infers variable type from initializer, here `int` |
| Lambda parameter | `(var s) -> s.length()` | Infers `s`'s type from the target functional interface's SAM |
| Local variable initialized with a lambda | `var f = (var s) -> ...;` | **Invalid** if there is no target type context for the lambda |

You can use `var` to store **an object that already has a functional interface type**, such as `var f = (java.util.function.Function<String, Integer>) (var s) -> s.length();` because the cast provides a target type for the lambda, though this style is usually harder to read than an explicit type declaration.

### Generics and type inference

With `Function<List<String>, Integer>`, the parameter `(var values)` is understood as `List<String>`; its elements are still `String`. `var` does not erase generic information present in the target type. However, the usual limitations of Java generics (type erasure, wildcards, bounds) still apply.

### Overloading is not automatically resolved by `var`

If a method has multiple overloads accepting functional interfaces with signatures that could both match a lambda, adding `var` to parameters does not guarantee selecting an overload. You may have to provide an explicitly typed variable or cast to a specific functional interface.

## 9. Situations where you should not use `var` mechanically

**Do not use `var` just to shorten code.** `(var x) -> x * 2` is longer than `x -> x * 2`. When there are no annotations or modifiers, the untyped style is usually shorter and easier to read.

**Consider `var` when there are annotations or `final`.** `(@NonNull var input) -> ...` avoids repeating a complex type if the project already has appropriate annotations; however, an annotation name without validation does not make data safer.

**Do not use `var` to hide a confusing API.** If the target type is unclear, name the functional interface, declare an explicitly typed variable, or use an appropriate method reference. `var` does not improve an API with too many ambiguous overloads.

**Do not expect this feature in Java 8 or Java 10.** Java 10 supports `var` for local variables within certain scopes, but `var` in **lambda parameters** was only standardized starting in **Java 11**. For applications targeting Java 17+, the examples in this lesson are valid.

## 10. Common mistakes to avoid

| Mistake | Invalid example | Fix |
|---|---|---|
| Mixing `var` and untyped parameters | `(var x, y) -> ...` | `(var x, var y) -> ...` or `(x, y) -> ...` |
| Mixing `var` and explicit types | `(var x, String y) -> ...` | Both `var` or both `String` if matching SAM |
| Omitting parentheses around `var` in a 1-parameter lambda | `var x -> ...` | `(var x) -> ...` |
| Using `var` instead of a target type | `var f = (var x) -> ...` | Assign lambda to `Function<...>`, `Predicate<...>`, etc. |
| Attaching an undeclared annotation or wrong target | `(@Missing var x) -> ...` | Define/import annotation and check `@Target` |
| Assuming `var` means `Object` | `(var x)` is always `Object` | Actual type follows the SAM's parameter, which can be primitive or reference |
| Assuming `final var` makes the object immutable | `(final var list) -> ...` | `final` only prevents reassigning the parameter variable |
| Using `var` to work around lacking a functional interface | An interface with two independent SAMs | Fix the interface/target type design; `var` does not change the SAM count |

For syntax errors, the compiler may report multiple cascading errors. Check the lambda declaration line and the **target type** before changing logic inside the lambda body.

## 11. A workflow for reading and checking lambdas with `var`

When encountering `(var a, var b) -> a + b` in a codebase, you can check in order:

1. **Find the target type:** is the variable declared as `BiFunction`, `BinaryOperator`, a custom functional interface, or a method parameter?
2. **Find the SAM:** how many parameters does the single abstract method take and of what types; what type does it return?
3. **Infer each parameter's type:** `var a` and `var b` take their types by position in the SAM, not because `a + b` "wants" a particular type.
4. **Check syntax consistency:** if one parameter uses `var`, all other parameters must also use `var`.
5. **Check annotations/modifiers:** is the annotation valid on parameters; is a `final` parameter reassigned in the body?
6. **Check the lambda body:** are the expression/result and checked exceptions compatible with the SAM and usage context?
7. **Run compilation:** for example using `javac --release 17` to ensure syntax belongs to the intended Java version.

This checklist separates three easily confused concerns: **parameter syntax**, **type inference**, and **lambda behavior**. Using `var` only changes how parameters are declared; it does not automatically solve any logic issues inside the lambda body.

## 12. Self-check questions

1. Is `(var a, var b) -> a + b` valid in Java 11+ with target type `BiFunction<Integer,Integer,Integer>`? What types do `a` and `b` have?
2. Why is `(var a, b) -> ...` invalid even though the compiler could know both parameters from the SAM?
3. If you want an annotation on a lambda parameter while still letting the compiler infer the type, what syntax should you use?
4. Does `(final var a, var b) -> ...` violate the "both use `var`" requirement?
5. Why does `var fn = (var s) -> s.length();` lack enough type information?
6. With `BiFunction<String,Integer,String>`, do the two parameters `(var text, var count)` have to have the same type?
7. Does Java 10 support `var` in lambda parameters?
8. Does the annotation named `@NonEmptyContract` in the example automatically reject empty strings?

**Answers:** (1) Yes, both are `Integer`. (2) Java forbids mixing lambda parameter declaration forms. (3) `(@MyAnnotation var parameter) -> ...`, with a valid annotation. (4) No: both parameter types are still declared with `var`. (5) The lambda has no target functional interface. (6) No: `text` is `String`, `count` is `Integer`. (7) No, that feature arrived in Java 11. (8) No, the illustrative annotation has no validation logic.

## 13. Official references

- [JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): motivation for bringing `var` syntax to lambda parameters while keeping consistency rules and allowing annotations.
- [Oracle Java 11 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/11/language/local-variable-type-inference.html): cases for using `var` in lambdas and examples disallowing mixed styles.
- [Java Language Specification Java SE 17, `15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): grammar and type inference of lambda parameters.

**Key takeaway:** `var` in a lambda is **syntax for inferring parameter types from the SAM**, not a new kind of data type. **Within the same lambda parameter list, if `var` is used, it must be used for all parameters**. The `var` form requires parentheses, and this feature is supported since Java 11; its standout benefit is being able to write annotations or `final` while preserving type inference.