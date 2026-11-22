# Selecting Overloaded Methods by Target Type in Java Method References

A **method reference** is an expression referring to an existing method using `::` syntax to provide an implementation for a **functional interface**. When the method name is **overloaded**, Java must determine which version is compatible with the **target type** in the usage context.

For example, if there are two methods `render(String)` and `render(int)`, the expression `Codec::render` does not by itself determine which method is selected. A target type such as `Function<String, String>` or `IntFunction<String>` supplies the functional method signature so the compiler can check and select the matching overload.

**Key point:** overload selection for a method reference happens **at compile time**, based on the target type, argument types, reference form, and Java's method resolution rules. It does not re-select arbitrarily based on the runtime type of each argument when invoking the functional method.

This lesson helps you:
- Explain why the same `Type::method` can point to different overloads in different target types.
- Distinguish `ClassName::staticMethod`, `receiver::instanceMethod`, `ClassName::instanceMethod`, and `ClassName::new`.
- Read the SAM signature accurately to predict which overload is selected.
- Recognize *ambiguous method reference*, *ambiguous method call*, and missing-target-type errors.
- Use explicitly typed variables, intentional casts, or explicit lambdas to resolve ambiguity.

## 1. The target type defines the contract the method reference must satisfy

Consider the functional interface `Function<T,R>` in `java.util.function`. It has a single abstract method:

```java
R apply(T input);
```

This is an **illustrative signature**, not a standalone Java program. When declaring:

```java
java.util.function.Function<String, String> f = Codec::render;
```

the compiler sees the target type is `Function<String,String>`, equivalent to a contract taking a `String` and returning a `String`. It must find a method named `render` on `Codec` whose input and output types match that target type. If `Codec` has overloads `render(String)` and `render(int)`, the `render(String)` overload is selected.

Conversely:

```java
java.util.function.IntFunction<String> g = Codec::render;
```

`IntFunction<String>` has the functional method `String apply(int value)`, so the `render(int)` overload matches.

The two lines above are illustrative snippets using the `Codec` class defined in the next complete example.

**A method reference is a poly expression:** it generally needs a functional interface as a target type from an assignment, method parameter, `return` statement, or cast. The method name on the right of `::` is not enough to determine the entire expression's type.

## 2. Java 17 example: same method reference, two overloads selected

Save to **`StaticOverloadReferenceDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntFunction;

class Codec {
    static String render(String text) {
        return "String:" + text;
    }

    static String render(int number) {
        return "int:" + number;
    }
}

public class StaticOverloadReferenceDemo {
    public static void main(String[] args) {
        Function<String, String> textRenderer = Codec::render;
        IntFunction<String> numberRenderer = Codec::render;

        System.out.println(textRenderer.apply("Java"));
        System.out.println(numberRenderer.apply(7));

        // Explicit lambda for the same choice in the String case.
        Function<String, String> explicit = text -> Codec.render(text);
        System.out.println(explicit.apply("Lambda"));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 StaticOverloadReferenceDemo.java
java StaticOverloadReferenceDemo
```

**Exact stdout:**

```text
String:Java
int:7
String:Lambda
```

Line-by-line explanation:

1. `textRenderer` has target type `Function<String,String>`; the functional method takes `String`, so `Codec.render(String)` is selected.
2. `numberRenderer` has target type `IntFunction<String>`; the functional method takes `int`, so `Codec.render(int)` is selected.
3. The lambda `text -> Codec.render(text)` has `text` inferred as `String`, so the `render(text)` call also selects the `String` overload.

Even though the code shares the syntax `Codec::render`, the two assignments create functional objects with different contracts. Subsequent `apply` calls follow each interface's functional method.

## 3. Reading the functional method signature accurately

To determine the overload, first write out the target type's SAM signature rather than guessing from variable names:

| Target type | Functional method signature | Input form the referenced method must match |
| --- | --- | --- |
| `Function<String,String>` | `String apply(String x)` | One `String`, result convertible to `String`. |
| `IntFunction<String>` | `String apply(int x)` | One `int`, returns `String`. |
| `BiFunction<String,Integer,String>` | `String apply(String x,Integer y)` | Two compatible parameters after type conversion rules. |
| `Supplier<String>` | `String get()` | No parameters, returns `String`. |
| `Consumer<String>` | `void accept(String x)` | One parameter; reference must fit a `void` return contract. |

Signatures are simplified for readability. The functional method of a generic interface actually undergoes type parameter substitution and compatibility rules per the Java Language Specification.

**Do not select based solely on parameter count.** If `render(String)` and `render(int)` exist, both take one parameter, yet the target type distinguishes them by argument type. If multiple methods match, Java continues applying rules to find applicable methods and select the *most specific* method, considering type conversions, generics, and related compatibility conditions.

The return value must also match the functional method; disallowed checked exceptions can also make the reference invalid. However, **Java does not allow overloading two methods that differ only in return type** with the same parameter list. Return type is not a mechanism for declaring overloads based solely on result.

## 4. Four forms of method references and the role of the receiver parameter

| Syntax | Meaning | How it maps to the SAM |
| --- | --- | --- |
| `Type::staticMethod` | Static method reference | SAM arguments supply the static method's arguments. |
| `receiver::instanceMethod` | Reference to an instance method on a known receiver | Receiver is fixed; SAM arguments supply the remaining arguments. |
| `Type::instanceMethod` | Unbound instance method reference | Usually the first SAM argument is the receiver; subsequent arguments go to the method. |
| `Type::new` | Constructor reference | Selects a constructor matching the SAM signature. |

This is a mental model for common cases. With `Type::name`, Java also checks static or instance search forms per JLS rules; if a method is overloaded and can match multiple forms, verify the exact target type and compiler result. Do not always assume `Type::name` can only be static.

In particular, `receiver::method` keeps the receiver you supply when **creating the method reference**; whereas `Type::instanceMethod` has no fixed receiver and must receive it via the functional method invocation.

## 5. Java 17 example: overloads on an instance method

Save as **`InstanceOverloadReferenceDemo.java`**:

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;

class Labeler {
    String mark(String text) {
        return "Text:" + text;
    }

    String mark(int number) {
        return "Number:" + number;
    }
}

public class InstanceOverloadReferenceDemo {
    public static void main(String[] args) {
        Labeler labeler = new Labeler();

        // Bound reference: receiver labeler is fixed.
        Function<String, String> text = labeler::mark;
        IntFunction<String> number = labeler::mark;

        // Unbound reference: Labeler is the first SAM parameter.
        BiFunction<Labeler, String, String> unbound = Labeler::mark;

        System.out.println(text.apply("Hello"));
        System.out.println(number.apply(12));
        System.out.println(unbound.apply(labeler, "Java"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 InstanceOverloadReferenceDemo.java
java InstanceOverloadReferenceDemo
```

**Exact stdout:**

```text
Text:Hello
Number:12
Text:Java
```

With `labeler::mark`, target `Function<String,String>` selects `mark(String)`, and target `IntFunction<String>` selects `mark(int)`. With `Labeler::mark`, the functional method of `BiFunction<Labeler,String,String>` has two arguments: `Labeler` as the receiver and `String` as the argument to `mark(String)`.

If you write `BiFunction<Labeler,Integer,String> intUnbound = Labeler::mark;`, the compiler can use unboxing from `Integer` to `int` to match the `mark(int)` overload; this illustrates the role of type conversion rules when matching, even when the two signatures are not character-for-character identical.

## 6. Constructor references also select overloads by target type

A class's constructors can be overloaded. `ClassName::new` uses the functional method signature to select the constructor with a matching parameter list.

Complete example, save as **`ConstructorOverloadReferenceDemo.java`**:

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Supplier;

record Entry(String name, int score) {
    Entry() {
        this("unknown", 0);
    }

    Entry(String name) {
        this(name, 0);
    }
}

public class ConstructorOverloadReferenceDemo {
    public static void main(String[] args) {
        Supplier<Entry> noArgs = Entry::new;
        Function<String, Entry> oneArg = Entry::new;
        BiFunction<String, Integer, Entry> twoArgs = Entry::new;

        Entry a = noArgs.get();
        Entry b = oneArg.apply("Lan");
        Entry c = twoArgs.apply("Mai", 9);

        System.out.println(a.name() + ":" + a.score());
        System.out.println(b.name() + ":" + b.score());
        System.out.println(c.name() + ":" + c.score());
    }
}
```

Compile/run on Java 17:

```bash
javac -encoding UTF-8 ConstructorOverloadReferenceDemo.java
java ConstructorOverloadReferenceDemo
```

**Exact stdout:**

```text
unknown:0
Lan:0
Mai:9
```

- `Supplier<Entry>` has a no-arg `get()`, selecting the `Entry()` constructor.
- `Function<String,Entry>` has `apply(String)`, selecting `Entry(String)`.
- `BiFunction<String,Integer,Entry>` has `apply(String,Integer)`; the second parameter is unboxed to `int` to call the canonical constructor `Entry(String,int)`.

The example uses `record`, officially supported since Java 16. `Entry` is a package-private record in the same source file as the public demo class.

## 7. When overloads of the method receiving a method reference make the call ambiguous

There are **two levels of overloading** to distinguish:

1. **Overloads of the referenced method**, such as `Renderer.show(String)` and `Renderer.show(int)`.
2. **Overloads of the method accepting the functional interface argument**, such as `accept(Function<String,String>)` and `accept(IntFunction<String>)`.

Even when each target type individually selects a `show` overload unambiguously, the compiler may still be unable to choose an `accept` overload when the argument is just `Renderer::show` without enough context to distinguish the two receiving overloads.

Example **intentionally not compiling**, just to see the issue:

```java
// Suppose Renderer has static show(String) and show(int).
// Suppose accept is overloaded for Function<String,String> and IntFunction<String>.
accept(Renderer::show); // may fail: ambiguous method call
```

Do not expect to "wait until runtime to know the value": at compile time, the method reference argument can match multiple signatures and the compiler must select the `accept` call via overload resolution rules.

### Complete Java 17 example: adding a target type to resolve ambiguity

Save as **`OverloadedReceiverDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntFunction;

class Renderer {
    static String show(String text) {
        return "S:" + text;
    }

    static String show(int value) {
        return "N:" + value;
    }
}

public class OverloadedReceiverDemo {
    static void accept(Function<String, String> handler) {
        System.out.println("string -> " + handler.apply("Java"));
    }

    static void accept(IntFunction<String> handler) {
        System.out.println("int -> " + handler.apply(5));
    }

    public static void main(String[] args) {
        // accept(Renderer::show); // INTENTIONALLY DOES NOT COMPILE: ambiguous

        // Cast provides a target type for the method reference and selects the accept overload.
        accept((Function<String, String>) Renderer::show);
        accept((IntFunction<String>) Renderer::show);

        // Or store in a variable with an explicitly declared type.
        Function<String, String> selected = Renderer::show;
        accept(selected);
    }
}
```

Run:

```bash
javac -encoding UTF-8 OverloadedReceiverDemo.java
java OverloadedReceiverDemo
```

**Exact stdout:**

```text
string -> S:Java
int -> N:5
string -> S:Java
```

The line `accept(Renderer::show)` is **left as a comment** so the complete program still runs. That line causes ambiguity because both `accept` overloads are valid candidates: one accepts a `String -> String` function, and one accepts `int -> String`.

A cast or an explicitly typed variable resolves this at two levels: choosing the target type for `Renderer::show`, and simultaneously selecting the corresponding `accept` overload. This also makes the API intent clear to readers.

## 8. Method references need a target type; they cannot create a type with var

You cannot ask `var` to infer a functional interface from a standalone method reference:

```java
// INTENTIONALLY WRONG: method reference has no target type.
var f = Renderer::show;

// INTENTIONALLY WRONG: Object is not a functional interface.
Object f2 = Renderer::show;
```

`var` requires an initializer expression that already has a definite type; a method reference is typically a poly expression needing a target type. `Object` declares no functional method, so it is not a valid target type either.

Valid approaches:

```java
java.util.function.Function<String, String> f = Renderer::show;
var inferred = f;
var explicitlyTyped = (java.util.function.IntFunction<String>) Renderer::show;
```

This is an **illustrative snippet**; `Renderer` must have the method declarations as in the full program above. `inferred` takes the type of `f`, while the cast supplies the target type for `explicitlyTyped`. Both have a valid source of type information.

## 9. When a single target type is still not enough: multiple overloads are applicable

Having a target type does not guarantee every method reference is valid. If multiple overloads of the referenced method itself are applicable and the most-specific selection rule cannot distinguish them, **the method reference is still ambiguous**.

Example **intentionally not compiling**:

```java
class Ambiguous {
    static String choose(CharSequence value) {
        return "text";
    }

    static String choose(java.io.Serializable value) {
        return "serializable";
    }
}

// String implements both CharSequence and Serializable.
java.util.function.Function<String, String> f = Ambiguous::choose;
// Error: neither overload is clearly more specific between the two parameters above.
```

In this example, the target type states that the SAM input is `String`. Yet `String` is convertible to both `CharSequence` and `Serializable`; these two types have no direct subtype relationship that makes one overload more specific, so the reference cannot uniquely choose one.

If business logic needs one of the two overloads, you can write a lambda with a cast **on the method call argument**:

```java
java.util.function.Function<String, String> chooseText =
        value -> Ambiguous.choose((CharSequence) value);
```

Here the call inside the lambda receives an argument of type `CharSequence`, so the compiler selects `choose(CharSequence)`. This differs from merely casting **the method reference itself** to `Function<String,String>`: the target type would still accept `String`, so it would remain ambiguous.

**Point to distinguish:** in section 7, *overloads of the callback-receiving method* caused ambiguity, even though each individual target could select the referenced method. In this section, there is only **one** target type, yet *overloads of the referenced method* are themselves ambiguous.

## 10. Type conversions, generics, and return values

Java does not compare signatures mechanically by type name alone. When checking a method reference, the compiler also considers rules involving:

- **Primitive widening** in applicable contexts, such as `int` to `long`.
- **Boxing/unboxing**, such as `Integer` and `int`.
- **Reference widening**, such as `String` to `CharSequence`.
- **Generic methods** and type inference, if the referenced method has type parameters.
- **Varargs** and the phases of finding applicable methods.
- **Return compatibility** with the functional method, along with checked exception constraints.

In complex cases, do not use a rule of thumb like "always prefer primitive types" or "always prefer exact match" in place of the official rules. Java's overload resolution process has ordered applicability phases and the *most specific* concept; the actual choice depends on the full signature and target context.

Example using generics:

```java
java.util.function.UnaryOperator<String> trim = String::trim;
java.util.function.Function<String, Integer> length = String::length;
```

These two method references are valid because the target types supply the necessary receiver and result types. This illustrative snippet only explains target typing, not two overloads of the same name.

**Return values are not always required in the same way.** `void`-returning functional methods have their own compatibility rules, so do not conclude a method reference is invalid just because the underlying method has a return type; check the return-adaptation rules for that target type.

## 11. Workflow for reading errors and choosing the right overload

When a reference like `Service::convert` fails to compile, proceed step by step:

1. **Write the target type explicitly:** e.g., `Function<String,Integer>`, without letting `var` or caller overloads obscure the context.
2. **Write down the functional method signature:** parameter count, parameter types, return type, and checked exceptions.
3. **Identify the reference form:** static, bound instance, unbound instance, or constructor; for unbound instance, note the first SAM receiver parameter.
4. **List the matching overloads of the method name** in the right class (and applicable inherited methods).
5. **Check type conversions and most-specific:** distinguish no applicable overload, a single applicable overload, or multiple ambiguous overloads.
6. **Check whether the caller is overloaded:** two overloads of the callback-receiving method may both fit the method reference.
7. **Clarify intent:** use an explicitly typed functional interface variable, a cast to the functional interface, or a lambda calling a specific overload via a cast argument when needed.
8. **Recompile** and run representative unit tests for `String`, `int`, or the actual types needed.

If an explicit lambda makes the code easier to read, using it is completely reasonable. Method references are not mandatory in every situation; the goal is to keep the type contract clear and correct.

## 12. Common misconceptions

1. **"The method reference name decides the overload by itself."** False. `Codec::render` needs a target type to know the matching call shape.
2. **"Overloads are chosen based on the runtime object."** False for standard overload resolution; compile-time argument types and target type decide the overload. Dynamic dispatch of overridden instance methods is a separate mechanism.
3. **"One target type always eliminates ambiguity."** False. Multiple applicable overloads may have no single most-specific method.
4. **"A method reference is always equivalent to taking the address of a fixed method, needing no context."** False. It is a poly expression in most contexts and needs a target type to resolve.
5. **"`String::method` is always a static reference."** False. It can be an unbound instance method reference depending on the signature and applicability rules.
6. **"`receiver::method` and `Type::method` take the same number of SAM arguments."** False for unbound instance methods: the SAM also takes the receiver as its first argument.
7. **"Overloading depends only on parameter count."** False. Parameter types, generics, and conversions also matter.
8. **"Changing the return type is enough to overload a method."** False. Java does not allow two methods with the same parameter list differing only in return type.
9. **"Casting to `Function` always resolves every ambiguity."** False. A cast resolves a missing target type or caller overloads; if the referenced method itself is ambiguous for that target, the call must be clarified.
10. **"`var f = Type::method` will guess a reasonable interface."** False. `var` does not synthesize a target type from a method reference.

## 13. Self-check

**Question 1.** `Codec` has `render(String)` and `render(int)`. Which line selects the `int` overload?

```java
java.util.function.Function<String, String> a = Codec::render;
java.util.function.IntFunction<String> b = Codec::render;
```

**Answer:** `b`, because the functional method of `IntFunction<String>` takes `int`.

**Question 2.** When writing `BiFunction<Labeler,String,String> f = Labeler::mark;`, what role does the first argument of `f.apply(...)` play?

**Answer:** It is the `Labeler` receiver on which to invoke the instance method `mark`; the second `String` argument is passed into the method.

**Question 3.** Why can `accept(Renderer::show)` be ambiguous when `accept` has two overloads taking `Function<String,String>` and `IntFunction<String>`?

**Answer:** Both target types have a matching method reference, and Java must uniquely choose an `accept` overload. Cast the method reference to the desired interface or assign it to an explicitly typed variable.

**Question 4.** Which constructor does `Supplier<Entry> f = Entry::new` select when `Entry` has 0-, 1-, and 2-parameter constructors?

**Answer:** The no-arg constructor `Entry()`, because the functional method `get()` has no arguments.

**Question 5.** If both `Ambiguous.choose(CharSequence)` and `Ambiguous.choose(Serializable)` are present, why can `Function<String,String> f = Ambiguous::choose` be rejected?

**Answer:** `String` is compatible with both parameter types with no single most-specific overload. The target type is clear, yet the underlying method remains ambiguous.

**Question 6.** What is a quick way to distinguish an error from the referenced method vs. a caller overload error?

**Answer:** Assign the method reference to an explicitly typed functional interface variable. If the assignment itself fails, check the signature and overloads of the referenced method. If the assignment succeeds but passing it directly to an overloaded method fails, check the caller's overloads and target type selection.

**Takeaway:** For overloaded method references, start from **the functional method signature of the target type**, identify the receiver and arguments, and then apply Java's overload rules. The target type clarifies overloads in many cases, though it does not eliminate all ambiguity when multiple candidates are equally applicable.