# Generic Methods and Overload Resolution in Java

## 1. Problem: When multiple methods share a name, which one does Java choose?

In Java, **method overloading** allows declaring multiple methods with the same name but different parameter lists. A **generic method** declares its own type parameters such as `<T>` and lets the compiler infer types at each call site. Combining these two mechanisms with boxing, primitive widening, varargs, lambdas, and method references produces overload-resolution cases that can be surprising.

Example:

```java
static String choose(Object value) { return "Object"; }
static String choose(String value) { return "String"; }
```

With `choose("Java")`, the compiler picks `choose(String)`. Yet when a generic overload is present:

```java
static <T> String option(T value) {
    return "generic";
}
static String option(CharSequence value) {
    return "CharSequence";
}
```

`option("Java")` on Java 17 chooses the method taking `CharSequence`, even though the generic method could infer `T = String`.

You need to understand three independent layers:

1. **Validity of overload declarations**: do two signatures conflict after type erasure?
2. **Compile-time overload resolution**: which candidates are applicable, in which invocation phase, and which is most specific?
3. **Runtime behavior**: after the compiler has chosen a method signature, instance overriding can dispatch based on the runtime object, yet runtime never re-selects an overload just because the actual object belongs to a subclass.

This lesson uses Java 17, including runnable examples, intentionally non-compiling examples, and ways to fix `ambiguous`, `name clash`, or `inference variable ... has incompatible bounds`.

## 2. Overloading differs from overriding

**Overloading** picks a method based on name and the compile-time static types of the argument list.

```java
static String render(Object x) { return "Object"; }
static String render(String x) { return "String"; }

Object text = "Java";
System.out.println(render(text)); // Object
```

The actual object is a `String`, but the variable `text` has static type `Object`, so the compiler does not choose the `(String)` overload. If pattern matching is used:

```java
if (text instanceof String s) {
    System.out.println(render(s)); // String
}
```

then `s` has static type `String`, leading to a different selection.

**Overriding**, on the other hand, is a subclass providing an implementation for an inherited method with a compatible signature. After overload resolution chooses a signature, an instance method call can be dispatched at runtime to the proper override based on the object's class. Do not equate the two mechanisms.

### 2.1. Return types do not create independent overloads

Two declarations differing only in return type are invalid:

```java
// Intentionally does not compile:
// static String load(int id) { return "A"; }
// static Integer load(int id) { return id; }
```

Java does not permit the same name and parameter list differing only by return type. This does not contradict the fact that **target type** can influence generic type inference within an expression; those are two separate rules.

### 2.2. Candidates must be visible and accessible

The compiler only considers candidates matching scope/accessibility at the call site. A `private` overload inaccessible from external code cannot become a candidate. When analyzing an API, start from the methods actually accessible in the caller's context.

## 3. Generic methods declare their own type variables

```java
static <T> T identity(T value) {
    return value;
}
```

The type variable `T` belongs to the **method**, not necessarily to the enclosing class. Caller:

```java
String s = identity("Java");
Integer n = identity(10);
```

The compiler infers `T` from arguments, bounds, and where applicable from the expression's **target type**. Generic inference does not mean `T` exists as a separate runtime class after erasure.

A bounded method:

```java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
```

can accept `Integer` or `Double`, but cannot accept `String`. When a generic candidate has an unsatisfied bound, the compiler must exclude that candidate from the set of applicable methods.

### 3.1. `<T>` is not the wildcard `?`

`<T>` links the same type variable across multiple positions:

```java
static <T> T first(List<T> items) {
    return items.get(0);
}
```

Whereas:

```java
static int size(List<?> items) {
    return items.size();
}
```

does not need to tie the element type to a return type, so a wildcard is appropriate.

Overload resolution evaluates generic methods according to their real type constraints; there is no rule saying “a method with `<T>` is always preferred because it is more flexible”.

## 4. Three phases of checking applicability

To understand typical selections, use Java's three-phase method invocation model:

1. **Strict fixed-arity invocation**: considers methods applicable with a fixed number of parameters without boxing/unboxing under loose invocation.
2. **Loose fixed-arity invocation**: if the first phase finds no applicable candidates, also considers conversions such as boxing/unboxing.
3. **Variable-arity invocation**: if still no candidates are found, considers varargs methods as variable-argument invocations.

In the first phase that produces applicable methods, the compiler proceeds to choose the **most-specific method** according to Java's rules. It does not move on to a later phase simply because a candidate there looks convenient.

Exact details also involve generic inference, *pertinence to applicability*, wildcards, functional interface specificity, and access rules. The three-phase model is a mental organizer, not the entirety of the JLS algorithm.

## 5. Primitive widening, boxing, and generic methods

Given:

```java
static String widen(long x) {
    return "long";
}

static <T> String widen(T value) {
    return "generic";
}
```

With `widen(7)`, argument `7` is primitive `int`; widening `int -> long` is accepted in the strict phase. The generic method takes reference type `T`, which requires boxing `int -> Integer`, so the `(long)` overload is chosen.

With `widen(Integer.valueOf(7))`, the argument is already an `Integer` reference. The generic method accepts it without unboxing, whereas the `(long)` overload requires unboxing/widening. In the tested example, the compiler picks the generic overload.

Result:

```text
widen=long,generic
```

**Lesson:** there is no rule saying “generic methods always lose to non-generic methods”. Static types and invocation phases determine the outcome.

### 5.1. Do not assume arbitrary wrapper conversions

`int -> long` is primitive widening. `int -> Integer` is boxing. However, not every conversion between primitives and wrappers is chained arbitrarily by the compiler. When `no suitable method found` is reported, check the **exact conversions permitted** for each overload.

## 6. Most-specific: generic method vs. concrete parameter

Consider:

```java
static <T> String option(T value) {
    return "generic:" + value.getClass().getSimpleName();
}

static String option(CharSequence value) {
    return "CharSequence";
}
```

`option("Java")` picks `(CharSequence)` in this case. `option(7)` cannot pass an `Integer` to `CharSequence`, so it picks generic.

Verified output:

```text
option=CharSequence,generic:Integer
```

The compiler does not simply infer `T = String` and declare it the “closest” parameter. Applicable-method and most-specific rules across generic and non-generic candidates must be applied per the JLS.

Another example:

```java
static String choose(Object x) { return "Object"; }
static String choose(String x) { return "String"; }
```

`choose("Java")` picks `(String)`, which is more specific than `(Object)`. `choose(7)` picks `(Object)` after boxing, because no `(String)` overload applies.

### 6.1. When should you place a concrete overload alongside a generic fallback?

Usually only when the semantics genuinely differ and callers understand it. A generic fallback can make an API harder to read if overload selection changes based on a variable's static type:

```java
CharSequence text = "Java";
option(text); // CharSequence
```

If you want behavior dispatched by the runtime object type, overloading is not runtime polymorphism. Consider visitor, strategy, pattern matching, or proper instance overriding.

## 7. Fixed arity and generic varargs

```java
static String shape(String value) {
    return "fixed";
}

@SafeVarargs
static <T> String shape(T... values) {
    return "varargs:" + values.length;
}
```

When calling `shape("x")`, the fixed method `(String)` is chosen. With `shape("x", "y")`, the fixed method does not accept two arguments, so generic varargs applies.

Result:

```text
shape=fixed,varargs:2
```

**However:** a varargs method can still participate in a fixed-arity invocation when the caller passes a matching array:

```java
static void send(String... values) {
    System.out.println(values.length);
}

String[] existing = {"A", "B"};
send(existing); // Passing an existing array.
```

Therefore, do not oversimplify the rule into “a method with `...` is always skipped if a method without `...` exists”. Check the applicability phase and concrete argument count.

### 7.1. Generic varargs and warnings

`T...` is an array parameter in source code; `T` is non-reifiable. If the body or call site risks heap pollution, `javac` may emit a warning. `@SafeVarargs` can be used on eligible and genuinely safe methods/constructors; the annotation does not make generic varargs reifiable.

In the `shape` example above, the static method only reads length and does not let the array escape or write wrong types, so `@SafeVarargs` is justified.

## 8. Lambdas have no type independent of a target

A lambda is checked against a **target functional interface type**, rather than having an independent function class in Java source:

```java
UnaryOperator<String> clean = s -> s.strip();
```

When a call is overloaded:

```java
target(s -> s.strip());
```

the compiler must inspect **each candidate method** and its corresponding target functional interface before deciding the proper overload. If two candidates can both accept the lambda without a *most specific* winner, the call can be ambiguous. `var clean = s -> s.strip();` is invalid because the initializer does not supply a target functional interface.

In this chapter, the focus of this section is **consequences for overload resolution**; the full target-typing process belongs to the previous lesson. Next, we compare candidates like `Function` and `UnaryOperator` to see what the compiler actually selects.

## 9. `Function` and `UnaryOperator` in overload resolution

`UnaryOperator<T>` extends `Function<T,T>`. Consider:

```java
static String target(Function<String, String> action) {
    return "Function:" + action.apply(" hi ");
}

static String target(UnaryOperator<String> action) {
    return "UnaryOperator:" + action.apply(" hi ");
}
```

With:

```java
target(s -> s.strip());
```

Java chooses `UnaryOperator<String>` in the tested example because subtype/specificity rules apply. Output:

```text
target=UnaryOperator:hi
```

This does not mean a particular functional interface name always wins; changing type relationships between interfaces or the lambda body can yield a different outcome.

### 9.1. Lambda + generic type inference

```java
static <T> T convert(T input, UnaryOperator<T> action) {
    return action.apply(input);
}
```

Call:

```java
String output = convert(" java ", String::strip);
```

The compiler infers `T = String`; the method reference has target `UnaryOperator<String>` and the result is `"java"`.

Important principle: when the compiler analyzes a lambda/method reference in a generic invocation, type variables and expected functional interface types constrain each other. Inference errors sometimes surface at the call containing the lambda rather than inside the method body.

## 10. `Supplier` and `Callable` can create ambiguity

`Supplier<String>` has abstract method `String get()`. `Callable<String>` has abstract method `String call() throws Exception`. Both take no parameters and return a String value.

```java
static String decide(Supplier<String> s) {
    return "Supplier:" + s.get();
}

static String decide(Callable<String> c) throws Exception {
    return "Callable:" + c.call();
}
```

The call:

```java
// Intentionally does not compile:
decide(() -> "ok");
```

becomes ambiguous because the lambda fits both target types, with no most-specific winner under these signatures. The compiler reports:

```text
error: reference to decide is ambiguous
```

Fixes:

```java
decide((Supplier<String>) () -> "ok");
```

Or:

```java
Supplier<String> supplier = () -> "ok";
decide(supplier);
```

Both approaches explicitly state the target functional interface. Using a named variable is usually easier to read if the lambda is complex or reused multiple times.

### 10.1. `Supplier` is not preferred simply for throwing no checked exceptions

The fact that `Callable.call()` declares `throws Exception` does not create a “prefer Supplier” rule for every lambda returning `String`. Do not rely on checked exception signatures as an overload-disambiguation trick.

### 10.2. Use distinct method names when you control the API

Two overloads accepting unrelated interfaces with the same lambda shape often make an API awkward to use. If one method means “provide a value” and the other means “execute a task that may throw”, names like `supply(...)` and `callChecked(...)` can be better than two `decide(...)` overloads.

## 11. `Consumer` and `Function`: statement-expression lambdas

A lambda whose body is a method invocation can be both **void-compatible** and **value-compatible**, because a method invocation is a *statement expression*.

Given:

```java
static void use(Consumer<String> c) { }
static void use(Function<String,String> f) { }
```

The call:

```java
// Does not compile:
use(s -> s.trim());
```

is reported as ambiguous by `javac --release 17`. Even though `trim()` returns `String`, a method-invocation expression can also be used as a statement discarding its result, so the lambda is compatible with both `Consumer<String>` and `Function<String,String>`.

### 11.1. Block lambdas clarify intent

To select `Consumer<String>`:

```java
use(s -> {
    s.trim();
});
```

The block does not return a value.

To select `Function<String,String>`:

```java
use(s -> {
    return s.trim();
});
```

The block returns `String`.

In the verified program:

```text
function=Function:abc
consumer=Consumer
```

For long-term clarity, avoid defining two overloads taking `Consumer` and `Function` with the same input type if they are frequently called with statement-expression lambdas.

### 11.2. `-Xlint:overloads` warns about risky APIs

For the overload pair above, `javac --release 17 -Xlint:all` emits the warning:

```text
[overloads] ... is potentially ambiguous with ...
```

Even when current call sites use explicit blocks, this warning flags **the API's potential to cause ambiguity at other call sites**. It is not a runtime error.

## 12. Method references also require a target type

A method reference is not a method object carrying a fixed functional interface:

```java
String::strip
```

must be interpreted against a target such as `UnaryOperator<String>`.

If a class has overloads:

```java
static <T> T echo(T value) {
    return value;
}

static String echo(String value) {
    return "special:" + value;
}
```

then:

```java
UnaryOperator<String> stringEcho =
        GenericOverloadDemo::echo;

Function<Integer, Integer> intEcho =
        GenericOverloadDemo::echo;
```

can resolve the same name `echo` to different methods. With target `UnaryOperator<String>`, the `(String)` overload is chosen; with target `Function<Integer,Integer>`, the generic method applies.

Verified output:

```text
reference=special:z,5
```

### 12.1. Method references can also be ambiguous

If you have:

```java
static String text() { return "x"; }
static void execute(Supplier<String> s) { }
static void execute(Callable<String> c) { }
```

then:

```java
// When placed in the same class:
// execute(MyClass::text);
```

can be ambiguous because both functional interfaces match a zero-parameter static method returning `String`. You must specify the target:

```java
Supplier<String> textSupplier = MyClass::text;
execute(textSupplier);
```

Or use an appropriate cast. Do not expect switching a lambda to a method reference to eliminate ambiguity automatically.

## 13. `null` and reference overloads

```java
static String select(String x) { return "String"; }
static String select(Integer x) { return "Integer"; }
```

The call:

```java
// Does not compile:
select(null);
```

has two applicable candidates (`String` and `Integer`) with no subtype relationship to pick a unique winner. `javac` reports:

```text
error: reference to select is ambiguous
```

To choose the `(String)` overload:

```java
select((String) null);
```

Or create a variable with static type String:

```java
String value = null;
select(value);
```

Note that resolving the overload does not guarantee the method body accepts null. If the method dereferences the null value, the program can still throw `NullPointerException`.

## 14. Type erasure and `name clash`

A generic method:

```java
static <T> void inspect(List<T> items) { }
```

has a parameter type that erases to raw `List`. If in the same class you add:

```java
static void inspect(List<String> items) { }
```

the compiler reports:

```text
error: name clash: inspect(List<String>) and
<T>inspect(List<T>) have the same erasure
```

Similarly:

```java
// Also invalid if in the same class:
static void read(List<String> strings) { }
static void read(List<Integer> integers) { }
```

The two methods differ only in type arguments `String` and `Integer`, yet after erasure both take a `List` parameter. Java does not allow defining two such overloads.

**Difference:** `ambiguous` usually concerns a **call site** that multiple valid overloads can accept; `name clash` concerns **declarations** that cannot coexist.

### 14.1. How to fix a name clash

No caller-side cast can fix a declaration error. Consider:

- One shared generic method.
- Semantically clear method names: `inspectStrings`, `inspectNumbers`.
- A `Class<T>` parameter or strategy/handler if you genuinely need to specify how to process elements.
- Splitting responsibilities into concrete classes implementing a generic interface.

Bridge methods generated by the compiler to preserve overriding after erasure do not allow you to manually write two same-erasure overloads.

## 15. Complete Java 17 example

Create the file **`GenericOverloadDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.function.*;

public class GenericOverloadDemo {
    static String choose(Object value) {
        return "Object";
    }

    static String choose(String value) {
        return "String";
    }

    static <T> String option(T value) {
        return "generic:" + value.getClass().getSimpleName();
    }

    static String option(CharSequence value) {
        return "CharSequence";
    }

    static String widen(long value) {
        return "long";
    }

    static <T> String widen(T value) {
        return "generic";
    }

    static String shape(String value) {
        return "fixed";
    }

    @SafeVarargs
    static <T> String shape(T... values) {
        return "varargs:" + values.length;
    }

    static <T> T convert(T input, UnaryOperator<T> action) {
        return action.apply(input);
    }

    static String target(Function<String,String> fn) {
        return "Function:" + fn.apply(" hi ");
    }

    static String target(UnaryOperator<String> fn) {
        return "UnaryOperator:" + fn.apply(" hi ");
    }

    static String task(Runnable action) {
        action.run();
        return "Runnable";
    }

    static String task(Callable<String> action) throws Exception {
        return "Callable:" + action.call();
    }

    static String decide(Supplier<String> source) {
        return "Supplier:" + source.get();
    }

    static String decide(Callable<String> source) throws Exception {
        return "Callable:" + source.call();
    }

    static <T> T echo(T value) {
        return value;
    }

    static String echo(String value) {
        return "special:" + value;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("choose="
                + choose("Java") + "," + choose(7));
        System.out.println("option="
                + option("Java") + "," + option(7));
        System.out.println("widen="
                + widen(7) + "," + widen(Integer.valueOf(7)));
        System.out.println("shape="
                + shape("x") + "," + shape("x", "y"));
        System.out.println("convert="
                + convert(" java ", String::strip));
        System.out.println("target="
                + target(s -> s.strip()));
        System.out.println("task="
                + task(() -> "fromCallable"));
        System.out.println("decision="
                + decide((Supplier<String>) () -> "ok"));
        System.out.println("echo="
                + echo("hello") + "," + echo(42));

        UnaryOperator<String> f1 = GenericOverloadDemo::echo;
        Function<Integer,Integer> f2 = GenericOverloadDemo::echo;
        System.out.println("reference="
                + f1.apply("z") + "," + f2.apply(5));
    }
}
```

Commands:

```bash
javac --release 17 -Xlint:all GenericOverloadDemo.java
java GenericOverloadDemo
```

The program compiled successfully on Java 17 with no warnings under `-Xlint:all`. Exact stdout:

```text
choose=String,Object
option=CharSequence,generic:Integer
widen=long,generic
shape=fixed,varargs:2
convert=java
target=UnaryOperator:hi
task=Callable:fromCallable
decision=Supplier:ok
echo=special:hello,42
reference=special:z,5
```

### 15.1. How to interpret each output group

`choose`: the String overload is more specific than Object; when the argument is primitive `7`, boxing turns it into `Integer`, matching Object.

`option`: a generic fallback and a `CharSequence` overload resolve differently for String and Integer; being generic does not grant absolute priority.

`widen`: primitive widening wins in the strict phase for `7`, whereas an `Integer` reference picks generic without needing unboxing.

`shape`: the fixed method accepts one String; generic varargs accepts two Strings.

`convert`: type inference links `String::strip` with `UnaryOperator<String>` and the String input.

`target`: `UnaryOperator<String>` is more specific than `Function<String,String>` in this overload set.

`task`: a lambda returning a string literal is not a void-compatible statement expression, so it matches only `Callable<String>` rather than `Runnable`.

`decision`: casting the lambda to `Supplier<String>` disambiguates which overload to invoke.

`echo`/`reference`: one method name with generic and non-generic overloads is resolved by argument types or target functional interface.

## 16. Five examples that intentionally do not compile

Each snippet below is **a separate file**; do not place them inside the runnable program.

### 16.1. `AmbiguousNull.java`

```java
class AmbiguousNull {
    static String select(String x) { return "s"; }
    static String select(Integer x) { return "i"; }

    static void check() {
        System.out.println(select(null));
    }
}
```

`javac --release 17 AmbiguousNull.java` reports:

```text
error: reference to select is ambiguous
```

Fix with `select((String) null)` or a variable with static type String if business logic permits null.

### 16.2. `AmbiguousLambda.java`

```java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class AmbiguousLambda {
    static void choose(Supplier<String> s) { }
    static void choose(Callable<String> c) { }

    static void check() {
        choose(() -> "hello");
    }
}
```

`javac --release 17 AmbiguousLambda.java` reports:

```text
error: reference to choose is ambiguous
```

Fix with `Supplier<String> s = () -> "hello"; choose(s);` or an appropriate functional interface cast.

### 16.3. `AmbiguousVoidValue.java`

```java
import java.util.function.Consumer;
import java.util.function.Function;

class AmbiguousVoidValue {
    static void use(Consumer<String> fn) { }
    static void use(Function<String, String> fn) { }

    static void test() {
        use(s -> s.trim());
    }
}
```

`javac --release 17 AmbiguousVoidValue.java` reports:

```text
error: reference to use is ambiguous
```

Fix to `use(s -> { s.trim(); });` if you want Consumer, or `use(s -> { return s.trim(); });` if you want Function.

### 16.4. `NameClash.java`

```java
import java.util.List;

class NameClash {
    static <T> void inspect(List<T> items) { }
    static void inspect(List<String> items) { }
}
```

`javac --release 17 NameClash.java` reports:

```text
error: name clash: inspect(List<String>) and
<T>inspect(List<T>) have the same erasure
```

This is a declaration error; the method signature or name must be changed.

### 16.5. `MethodRefAmbiguous.java`

```java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class MethodRefAmbiguous {
    static String text() { return "x"; }
    static void run(Supplier<String> s) { }
    static void run(Callable<String> c) { }

    static void check() {
        run(MethodRefAmbiguous::text);
    }
}
```

`javac --release 17 MethodRefAmbiguous.java` reports:

```text
error: reference to run is ambiguous
```

A method reference also needs an explicit target functional interface; you can assign it to `Supplier<String>` before calling.

The five cases above were tested directly with the Java 17 compiler, all returning non-zero exit status with corresponding diagnostics.

## 17. Program demonstrating clear disambiguation results

Create the file **`OverloadDisambiguationProof.java`**:

```java
import java.util.concurrent.Callable;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

class OverloadDisambiguationProof {
    static String select(String x) {
        return "String";
    }

    static String select(Integer x) {
        return "Integer";
    }

    static String call(Supplier<String> f) {
        return "Supplier:" + f.get();
    }

    static String call(Callable<String> f) throws Exception {
        return "Callable:" + f.call();
    }

    static String apply(Consumer<String> f) {
        f.accept(" abc ");
        return "Consumer";
    }

    static String apply(Function<String,String> f) {
        return "Function:" + f.apply(" abc ");
    }

    public static void main(String[] args) throws Exception {
        System.out.println("null=" + select((String) null));
        System.out.println("lambda="
                + call((Supplier<String>) () -> "done"));
        System.out.println("function="
                + apply(s -> { return s.trim(); }));
        System.out.println("consumer="
                + apply(s -> { s.trim(); }));

        Supplier<String> ref = () -> "value";
        System.out.println("typed=" + call(ref));
    }
}
```

Run:

```bash
javac --release 17 -Xlint:all OverloadDisambiguationProof.java
java OverloadDisambiguationProof
```

Confirmed stdout:

```text
null=String
lambda=Supplier:done
function=Function:abc
consumer=Consumer
typed=Supplier:value
```

The compiler **still emits a warning** `[overloads]` on the `apply(Function<String,String>)` declaration under `-Xlint:all` because the `Consumer`/`Function` overload pair is potentially ambiguous. This proves that writing clear call sites today does not eliminate **API design** risk.

## 18. Distinguishing inference errors from ambiguous overloads

Common diagnostics:

| Compiler diagnostic | Primary meaning | How to resolve |
| --- | --- | --- |
| `reference to ... is ambiguous` | Multiple applicable candidates exist, with no unique winner. | Clarify static type/functional target, rename API, or remove an overload. |
| `no suitable method found` | No candidate applies given arguments/conversions/bounds. | Check overload signatures and actual static types. |
| `inference variable T has incompatible bounds` | Constraints on type variables cannot be solved simultaneously. | Check generic bounds, target type, and arguments/lambdas. |
| `name clash ... same erasure` | Overload declarations collide after erasure. | Fix method declarations, not just casts at call sites. |
| `[overloads] ... potentially ambiguous` | API has overloads taking hard-to-distinguish functional interfaces. | Consider different method names or clearer target types. |
| `ClassCastException` at runtime | A value is used/cast as an incompatible runtime type. | Check raw aliases, unchecked casts, or external data sources. |

**Distinction:** inference and ambiguity errors are usually caught when compiling a call; name clashes are caught directly at declarations. Do not expect runtime to “try” another overload after the compiler reports ambiguity.

### 18.1. Target type can influence generic inference

Example:

```java
static <T> T empty() {
    return null;
}

String s = empty();
Integer i = empty();
```

The compiler can use the assignment's target type to infer the invocation's return type. With nested generic method calls, constraints from the surrounding expression can influence inference.

This **does not** mean you may define two methods differing only by return type. Target-type inference and overload declaration rules are separate mechanisms.

### 18.2. An explicit type witness is not an absolute overload selector

Java permits specifying type arguments in some generic invocations:

```java
String value = GenericOverloadDemo.<String>echo("Java");
```

However, do not assume writing `<String>` always forces the compiler to choose a generic implementation regardless of the overload set. Applicability and specificity are still governed by language rules. When an overloaded API is confusing, renaming or designing transparent signatures is usually better.

## 19. Checklist for determining overloads in real code

1. **Note the exact static type** of every argument, including generic type arguments and primitive/reference types.
2. **List accessible overloads** at the call site, considering access/scope.
3. For generic methods, check **type variables, bounds, and inference constraints** from arguments/target.
4. Find applicable candidates in the **strict fixed-arity phase**.
5. If none exist, consider the **loose fixed-arity phase** (boxing/unboxing).
6. If still none exist, consider the **variable-arity phase** for varargs.
7. Within the first succeeding phase, compare **most-specific** among candidates.
8. For lambdas/method references, determine the **target functional interface**, descriptor parameters/return, and void/value compatibility.
9. For `null`, check whether reference overloads have a subtype relation that selects a winner.
10. If declarations use different generic arguments, check **erasure/name clash**.
11. If ambiguous, clarify types using a variable, deliberate cast, or new API design; never use raw types to hide errors.
12. Compile on Java 17 with `-Xlint:all`, verifying stdout/diagnostics on minimal examples.

Quick lookup table:

| Call or declaration | Outcome |
| --- | --- |
| `choose("x")` with `(Object)` and `(String)` | `(String)` is more specific. |
| `choose(x)` if variable x has static type `Object` but runtime String | `(Object)` due to compile-time type. |
| `widen(7)` with `(long)` and `<T>(T)` | `(long)` in the example. |
| `widen(Integer.valueOf(7))` | Generic overload in the example. |
| `shape("x")` with `(String)` and `<T>(T...)` | Fixed `(String)`. |
| `shape("x","y")` | Generic varargs. |
| `target(s -> s.strip())` with `Function` and `UnaryOperator` | `UnaryOperator`. |
| `decide(() -> "x")` with `Supplier<String>` and `Callable<String>` | Ambiguous. |
| `use(s -> s.trim())` with `Consumer` and `Function` | Ambiguous. |
| `select(null)` with `(String)` and `(Integer)` | Ambiguous. |
| `inspect(List<String>)` and `<T>inspect(List<T>)` | Name clash after erasure. |

## 20. Self-check questions

**Question 1.** Why does `Object x = "Java"` call the `(Object)` overload instead of `(String)`?

<details>
<summary>Answer</summary>

Overload resolution uses the expression's static type `Object` at compile time. The runtime class `String` does not cause Java to re-select an overload.

</details>

**Question 2.** Why can `widen(7)` pick `(long)` instead of generic `<T>(T)`?

<details>
<summary>Answer</summary>

Primitive widening `int -> long` applies in the strict fixed-arity phase; the generic candidate requires boxing the primitive argument and is considered in a later phase.

</details>

**Question 3.** Are `List<String>` and `List<Integer>` different enough to define two overloads `(List<String>)` and `(List<Integer>)` in the same class?

<details>
<summary>Answer</summary>

No. The erasure of both parameterized types is raw `List`, causing a name clash.

</details>

**Question 4.** Why can `() -> "ok"` be ambiguous when overloads accept `Supplier<String>` and `Callable<String>`?

<details>
<summary>Answer</summary>

Both functional interfaces have a zero-parameter abstract method returning `String`; the lambda has no specific target type yet, so both candidates match without a unique winner. Use a typed variable, cast, or distinct API names.

</details>

**Question 5.** Why can `s -> s.trim()` match both Consumer and Function?

<details>
<summary>Answer</summary>

`trim()` is a method invocation, which is a statement expression. An expression lambda can be both void-compatible and value-compatible. Use a block without return for Consumer, or a block with return for Function.

</details>

**Question 6.** Why can `UnaryOperator<String>` beat `Function<String,String>`?

<details>
<summary>Answer</summary>

`UnaryOperator<T>` extends `Function<T,T>`, so Java considers that subtype/specificity relationship when both target types are applicable.

</details>

**Question 7.** Can you use a caller-side cast to fix a `name clash` between two generic overload declarations?

<details>
<summary>Answer</summary>

No. A name clash is an error on method declarations sharing the same erasure. You must change the method name/signature or redesign the API.

</details>

**Question 8.** Does the method reference `SomeClass::echo` decide its overload on its own without a target type?

<details>
<summary>Answer</summary>

No. A method reference uses its target functional interface; overload resolution of the referenced method depends on the parameter/return types required by the target.

</details>

## 21. Summary

**Overload resolution happens at compile time**, using static types, generic inference, applicable invocation phases, and most-specific selection. Lambdas and method references also need a target functional interface, which can make overloaded APIs ambiguous even when each individual method is valid.

When encountering errors, distinguish three kinds: `ambiguous` at a call site; `name clash` at declarations after erasure; `incompatible bounds` in generic inference. Do not fix them by arbitrarily dropping `<T>` or using raw types. Use explicit static types, block lambdas, named functional interface variables, or redesigned signatures/naming to keep APIs clear and type-safe.