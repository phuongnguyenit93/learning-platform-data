# Comparing Inference with Diamond, `var`, and Explicit Type Arguments in Java Generics

## 1. Similarly Concise Syntax, Three Mechanisms Answering Three Different Questions

Java offers several syntaxes that reduce repeating type names. Three forms often appear side by side:

```java
List<String> names = new ArrayList<>();           // Diamond <>
var scores = new ArrayList<Integer>();            // var
var values = new ArrayList<>();                    // Combining var and diamond
List<String> empty = List.<String>of();            // Explicit type argument of method
```

This is an illustrative snippet; it requires importing `java.util.List` and `java.util.ArrayList` and placing it inside a method to compile.

At a glance, they all seem to "let Java guess the type." Yet their roles differ:

- **Diamond `<>`** appears on a generic class constructor call. The compiler infers the **type arguments of the instantiated class**, based on constructor arguments and target context if present.
- **`var`** appears in a **local variable declaration**. The compiler infers the **static type of the variable** from the initializer expression, after which the variable remains statically type-checked as usual.
- **Explicit type arguments** such as `new ArrayList<String>()` or `Collections.<String>emptyList()` specify the exact type parameters to use at a class constructor or generic method call. They clarify intent or guide inference when surrounding context is insufficient.

Key takeaway:

> `<>` and `var` are not synonymous. In `List<String> list = new ArrayList<>()`, the left-hand side supplies context to infer `String`. In `var list = new ArrayList<>()`, there is no left-hand side supplying `String`; with this zero-argument constructor, Java infers the element type as `Object`.

Therefore, writing concisely **does not always preserve the same type information** used by the compiler. To assess safety and readability, examine **which sources of information the compiler uses for inference**.

## 2. Background: Generic Type Parameter, Type Argument, and Static Type

The declaration `ArrayList<E>` has one type parameter `E`. When used as:

```java
new ArrayList<String>()
```

`String` is the **type argument** explicitly written for `E`. With:

```java
new ArrayList<>()
```

the compiler infers the appropriate argument for `E`.

The initializer expression then has a static type. That static type can subsequently be used to infer the type of a local variable declared with `var`, though `var` itself is **not a type argument** of `ArrayList`.

Simplified illustration:

```text
Class declaration:  ArrayList<E>
                           |
Constructor:        new ArrayList<>()  -- infers E
                           |
Expression:         ArrayList<String>   -- if context specifies String
                           |
Variable decl:      var list = ...      -- infers list's type from expression
```

The diagram only outlines inference relationships; the Java compiler enforces stricter rules regarding *target typing*, applicability, and type inference in the Java Language Specification.

Also distinguish:

- **Static type** determines which calls and assignments the compiler accepts.
- **Runtime class** is determined by the actual instantiated object. `ArrayList<String>` and `ArrayList<Integer>` share the same runtime class `ArrayList`.
- Java Generics use **type erasure**, yet that does not diminish the compile-time type-checking value of `var` and diamond.

## 3. Diamond `<>`: Inferring Constructor Type Arguments

### 3.1. Form with a target type

Classic example:

```java
List<String> names = new ArrayList<>();
```

The left-hand side has type `List<String>`. The constructor `ArrayList<>()` can be inferred into an expression assignable to `List<String>`; in this simple case, the element type argument of `ArrayList` is `String`.

Written out fully:

```java
List<String> names = new ArrayList<String>();
```

Both forms express the same typing intent in source code: `names` is `List<String>`. Diamond eliminates repeating `<String>` on the right-hand side.

Similarly:

```java
Map<String, Integer> counts = new HashMap<>();
Set<Long> ids = new HashSet<>();
```

Requires importing those classes from `java.util`. In these declarations, the target type on the left supplies type information to the constructor.

### 3.2. Constructor arguments can also supply information

If the constructor receives typed data:

```java
var copied = new ArrayList<>(List.of("An", "Binh"));
```

`List.of("An", "Binh")` has element type `String` via generic method inference. The constructor `ArrayList(Collection<? extends E>)` accepts that collection, giving the compiler information to infer `E` accordingly.

Difference from zero-argument `new ArrayList<>()`: in the copy example, the **constructor argument** supplies a useful constraint even without a target type on the left-hand side.

### 3.3. Diamond is not a sign of a raw type

```java
List<String> a = new ArrayList<>(); // Checked generic.
List b = new ArrayList();           // Raw type.
```

The two lines mean different things:

- The first line uses generics with diamond; `a` has type `List<String>`.
- The second uses raw `List` and raw `ArrayList`, dropping type-argument checks at the use site and potentially emitting `rawtypes`/`unchecked` warnings.

Do not omit `<...>` on both sides assuming you retain the same level of type safety.

## 4. `var`: Compiler Infers Local Variable Type from Initializer

`var` has been supported for **local variable type inference** since Java 10. Example:

```java
var name = "Mai";
var count = 3;
var list = new ArrayList<String>();
```

In these three lines, the compiler infers static types `String`, `int`, and `ArrayList<String>` respectively. Once declared, they do not become "dynamic" variables that can freely change types.

```java
var value = "hello";
// value = 10; // Compile error: value has type String.
```

The second statement is intentionally commented out to illustrate the error.

### `var` does not mean "no generics"

A variable:

```java
var strings = new ArrayList<String>();
```

has static type `ArrayList<String>`. Consequently:

```java
strings.add("valid");
// strings.add(123); // Compile error.
```

Using `var` **does not strip** `<String>` from the initializer expression.

### `var` cannot be used in every declaration position

`var` is restricted to Java-specified positions, notably local variables with initializers; it cannot substitute for arbitrary fields, method parameters, or return types.

Invalid examples:

```java
// These lines are error examples only:
// var field;                  // Fields cannot use var like this.
// var local;                  // Local variable missing initializer.
// var nothing = null;         // Cannot infer type from standalone null.
// var array = {1, 2, 3};      // Short-form array initializer missing target type.
```

A valid local array can be written `var array = new int[] {1, 2, 3};`.

Since Java 11, `var` is also permitted in lambda parameters under applicable rules, though that is a separate context from the comparison here.

## 5. The Biggest Pitfall: Combining `var` with `new ArrayList<>()`

This is an experiment worth running directly:

Create file **`VarDiamondDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class VarDiamondDemo {
    public static void main(String[] args) {
        List<String> targeted = new ArrayList<>();
        targeted.add("Java");

        var inferredFromExplicit = new ArrayList<String>();
        inferredFromExplicit.add("Generics");

        var withoutTarget = new ArrayList<>();
        withoutTarget.add("text");
        withoutTarget.add(123);

        System.out.println(targeted.get(0));
        System.out.println(inferredFromExplicit.get(0));
        System.out.println(withoutTarget.get(0));
        System.out.println(withoutTarget.get(1));

        Object value = withoutTarget.get(0);
        System.out.println(value.getClass().getSimpleName());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac VarDiamondDemo.java
java VarDiamondDemo
```

Stdout:

```text
Java
Generics
text
123
String
```

### Why does `withoutTarget` accept both `String` and `Integer`?

With:

```java
var withoutTarget = new ArrayList<>();
```

the compiler receives no `List<String>` target context on the left because the left-hand side is `var`. The zero-argument `ArrayList()` constructor also supplies no data to infer a specialized element type. In this situation, type parameter `E` is inferred as `Object`, giving the variable static type `ArrayList<Object>`.

Therefore:

```java
withoutTarget.add("text");  // String is an Object.
withoutTarget.add(123);     // Integer is also an Object.
```

Both calls are valid. This is not "`var` changing the list's type after the first add." The type was fixed **right at the declaration line**.

For the exact same reason:

```java
// Intentionally invalid:
String text = withoutTarget.get(0);
```

is a compile error: `get(0)` on `ArrayList<Object>` has static type `Object` and cannot be implicitly assigned to `String`.

**Note:** `var` does not downgrade every generic to `Object`. It simply reflects the type of the **initializer**. If the initializer already carries sufficient type information, such as `new ArrayList<String>()` or `new ArrayList<>(List.of("a"))`, that type information is preserved.

## 6. Comparing the Same Intent Across Four Declarations

Suppose the goal is a list of strings that allows adding `"A"` and `"B"` while the compiler rejects `123`.

| Declaration | Static type of variable | Satisfies intent? |
|---|---|---|
| `List<String> x = new ArrayList<>();` | `List<String>` | Yes |
| `List<String> x = new ArrayList<String>();` | `List<String>` | Yes, though repeats `<String>` |
| `var x = new ArrayList<String>();` | `ArrayList<String>` | Yes; ties to concrete implementation type |
| `var x = new ArrayList<>();` | `ArrayList<Object>` | No, if you want elements restricted to `String` |

Two differences worth highlighting:

1. **Specificity of the variable's type.** `List<String>` uses the `List` interface; `var x = new ArrayList<String>()` infers the concrete class `ArrayList<String>`. Both are type-safe generics, but they differ in implementation coupling.
2. **Information fed into inference.** Writing `<String>` once on the **left-hand side** suffices for diamond to infer, whereas with `var` that information must come from the **initializer** or constructor arguments.

When you want an API where `ArrayList` can easily be swapped for `LinkedList`, declaring `List<String>` on the left generally communicates intent better. When initialization is verbose yet obvious from the initializer, `var` can reduce noise.

## 7. `var` + Diamond Still Infers Correctly When the Constructor Has Data

Create file **`DiamondFromArgumentsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondFromArgumentsDemo {
    public static void main(String[] args) {
        var first = new ArrayList<>(List.of("A", "B"));
        var second = new ArrayList<>(List.of(10, 20));

        String name = first.get(0);
        Integer number = second.get(0);

        first.add("C");
        second.add(30);

        System.out.println(name);
        System.out.println(number);
        System.out.println(first);
        System.out.println(second);
    }
}
```

Run:

```bash
javac DiamondFromArgumentsDemo.java
java DiamondFromArgumentsDemo
```

Stdout:

```text
A
10
[A, B, C]
[10, 20, 30]
```

In this example:

- `List.of("A", "B")` is inferred as a list of strings.
- `new ArrayList<>(...)` accepts `Collection<? extends E>` to determine `E`.
- Variable `first` is inferred as `ArrayList<String>`.
- Variable `second` is inferred as `ArrayList<Integer>`.

The compiler can therefore verify `String name = first.get(0)` and `Integer number = second.get(0)`.

Do not memorize a false rule like "diamond always produces Object elements." The outcome depends on **inference constraints from target types, constructor arguments, and inference rules**.

## 8. Explicit Constructor Type Arguments vs. Diamond

In Java:

```java
new ArrayList<String>()
new ArrayList<>()
```

`<String>` in the first expression provides **explicit type arguments for the generic class**. `<>` in the second instructs the compiler to infer them.

With context:

```java
List<String> names = new ArrayList<>();
```

diamond is usually concise and clear. However, in:

```java
var names = new ArrayList<String>();
```

specifying `String` on the constructor carries real meaning because `var` provides no left-hand target type.

You can write:

```java
ArrayList<String> names = new ArrayList<String>();
```

without error. However, this repeats `String`; it is generally only warranted to spell out full types for readers or when maintaining compatibility with very old Java versions.

**Do not confuse** class constructor type arguments with method type argument syntax. `new ArrayList<String>()` differs grammatically in placement from `Collections.<String>emptyList()`.

## 9. Explicit Type Arguments on Generic Methods

Type inference applies to more than constructors. A **generic method** can declare its own type parameters:

```java
static <T> T identity(T input) {
    return input;
}
```

When calling `identity("Java")`, the compiler infers `T = String` from the argument. You can specify the type argument explicitly with:

```java
GenericMethodWitnessDemo.<String>identity("Java")
```

Standalone example, file **`GenericMethodWitnessDemo.java`**:

```java
import java.util.Collections;
import java.util.List;

public class GenericMethodWitnessDemo {

    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        String inferred = identity("Java");
        String explicit =
                GenericMethodWitnessDemo.<String>identity("Generics");

        List<String> contextual = Collections.emptyList();
        var withoutContext = Collections.emptyList();
        var withWitness = Collections.<String>emptyList();

        System.out.println(inferred);
        System.out.println(explicit);
        System.out.println(contextual.size());
        System.out.println(withoutContext.size());
        System.out.println(withWitness.size());
    }
}
```

Run:

```bash
javac GenericMethodWitnessDemo.java
java GenericMethodWitnessDemo
```

Stdout:

```text
Java
Generics
0
0
0
```

The three `Collections.emptyList()` calls have different types **in source code**:

- `List<String> contextual = Collections.emptyList();` has target type `List<String>`, so the compiler infers `T` compatible with `String`.
- `var withoutContext = Collections.emptyList();` has no target type from the variable declaration, and the method takes no arguments to supply further constraints. Here `T` is inferred as `Object`, giving the variable type `List<Object>`.
- `var withWitness = Collections.<String>emptyList();` supplies the **type witness** `<String>` on the method call, giving the variable type `List<String>`.

All three lists returned by `Collections.emptyList()` are empty; stdout alone does not prove their generic types. To observe the difference, try assigning the results to variables with conflicting type requirements and observe the compiler's response.

### Inference does not change the generic declaration

The generic method still has **one declaration** `<T> List<T> emptyList()`. Inferring `String`, `Integer`, or `Object` at individual call sites does not generate separate overloads or runtime classes for each `T`.

## 10. Empty `List.of()` Calls: Where `var` Easily Loses Intent

`List.of()` creates a list that cannot be modified structurally. Its **zero-argument** overload has no elements to aid type inference.

Compare:

```java
List<String> a = List.of();
var b = List.of();
var c = List.<String>of();
```

Predictions:

- `a` has static type `List<String>` from the left-hand context.
- `b` has static type `List<Object>` because neither context nor element arguments supply `String`.
- `c` has static type `List<String>` from the `<String>` type witness.

Unlike `new ArrayList<>()`, lists from `List.of()` disallow `add(...)`, so type differences are easily tested via a method expecting `List<String>` or assigning to a typed variable.

Standalone example **`EmptyListInferenceDemo.java`**:

```java
import java.util.List;

public class EmptyListInferenceDemo {

    static void showStrings(List<String> values) {
        System.out.println("strings=" + values.size());
    }

    public static void main(String[] args) {
        List<String> a = List.of();
        var b = List.of();
        var c = List.<String>of();

        showStrings(a);
        showStrings(c);
        System.out.println(b.size());

        // showStrings(b); // Error: b has type List<Object>.
    }
}
```

Run:

```bash
javac EmptyListInferenceDemo.java
java EmptyListInferenceDemo
```

Stdout:

```text
strings=0
strings=0
0
```

Lesson: With a **generic factory method that has no typed inputs**, a target type or explicit type argument is usually how you state the expected result type.

## 11. Two `<...>` Brackets in Two Different Places

Look at these two expressions:

```java
List<String> first = new ArrayList<>();
List<String> second = Collections.<String>emptyList();
```

The angle brackets play different roles in the two examples:

- `new ArrayList<>()`: diamond on a **class instance creation expression**; the compiler infers the type parameter of class `ArrayList<E>`.
- `Collections.<String>emptyList()`: `<String>` is an **explicit type argument for the generic method** `emptyList<T>()`.

A generic class can simultaneously have its own generic constructors or generic instance methods, so you cannot deduce from bracket count alone that they always control the same type parameter.

Simple example:

```java
class Pair<L, R> {
    Pair(L left, R right) {
    }

    <U> U echo(U value) {
        return value;
    }
}
```

Here `L` and `R` belong to the **class**, while `U` belongs to the **method**. `new Pair<>("x", 1)` infers `L`, `R`; `pair.<Boolean>echo(true)` sets `U = Boolean`. The two mechanisms interact, yet operate at distinct declaration sites.

## 12. Combined Example: Independent Generic Class and Generic Method

Create file **`CombinedInferenceDemo.java`**:

```java
public class CombinedInferenceDemo {

    static class Pair<L, R> {
        private final L left;
        private final R right;

        Pair(L left, R right) {
            this.left = left;
            this.right = right;
        }

        L left() {
            return left;
        }

        R right() {
            return right;
        }

        <U> U echo(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> first = new Pair<>("age", 21);

        var second = new Pair<>("score", 99);

        String label = first.left();
        Integer score = second.right();

        String message = second.echo("ok");
        Boolean flag = second.<Boolean>echo(true);

        System.out.println(label);
        System.out.println(score);
        System.out.println(message);
        System.out.println(flag);
    }
}
```

Compile and run:

```bash
javac CombinedInferenceDemo.java
java CombinedInferenceDemo
```

Stdout:

```text
age
99
ok
true
```

Analysis:

1. `first` has target type `Pair<String,Integer>`, so diamond on the constructor infers types matching the target.
2. `second` has no target type from `var`, yet the constructor receives `"score"` and `99`, which suffices to infer `L = String`, `R = Integer`.
3. `second.right()` consequently has static type `Integer`.
4. `second.echo("ok")` infers **the method's `U`** from the argument as `String`.
5. `second.<Boolean>echo(true)` calls the same method while explicitly specifying `U = Boolean`. It does not change `L` or `R` of `Pair`.

If you try `Pair<String,Integer> wrong = new Pair<>("age","twenty");`, the compiler must reject it because the second argument does not match target type `Integer`. That is a concrete benefit of target typing and type checking.

## 13. When Does `var` Expose the Concrete Class Instead of the Interface?

Look at the two declarations:

```java
List<String> list = new ArrayList<>();
var list2 = new ArrayList<String>();
```

- `list` has static type **interface** `List<String>`.
- `list2` has static type **concrete class** `ArrayList<String>`.

This does not automatically make `list2` less type-safe; both reject non-`String` elements. The difference lies in visibility of implementation-specific members, readability, and implementation coupling.

Example:

```java
var concrete = new java.util.ArrayList<String>();
java.util.List<String> abstraction = new java.util.ArrayList<>();
```

Both variables point to an `ArrayList` object at runtime, but the second declaration explicitly states "I only need the `List` contract."

For long-lived or widely used APIs, declaring the interface on the left usually establishes cleaner dependency boundaries. For short-lived local variables, `var` can be reasonable when the type is immediately clear without forcing readers to guess.

**Do not conclude that** `var` is like `Object`. `var concrete = new ArrayList<String>()` has the full type `ArrayList<String>`, not `Object`, raw `ArrayList`, or `ArrayList<Object>`.

## 14. Target Typing Contexts: Assignment, Return, and Method Calls

The compiler can draw a **target type** from the context surrounding a generic expression:

```java
List<String> list = new ArrayList<>();
```

Here, assignment supplies the target type.

A method with an explicit return type also establishes context:

```java
static List<String> createNames() {
    return new ArrayList<>();
}
```

In a method call, the method parameter can provide the target type:

```java
static void consume(List<String> names) {
    System.out.println(names.size());
}

static void demo() {
    consume(new ArrayList<>());
}
```

The two snippets above are illustrative method declarations without an enclosing class or `main`; place them inside a class to compile.

Therefore, the rule "diamond only looks at the left-hand side" is incomplete. Diamond can leverage multiple valid contexts defined by Java's type inference system, alongside information from constructor arguments.

**`var` is a special context:** When writing `var x = expression;`, the compiler must determine the type of `expression` itself to form `x`'s type. There is no `List<String>` declaration on the left to feed `String` into inferring the initializer's type arguments.

## 15. Inference from Generic Method Expressions and Type Witnesses

Consider the method:

```java
static <T> T choose(T first, T second) {
    return first;
}
```

The compiler can use both arguments to infer `T`, and in suitable contexts also incorporate constraints from the result.

Standalone program example **`ChooseInferenceDemo.java`**:

```java
public class ChooseInferenceDemo {

    static <T> T choose(T first, T second) {
        return first;
    }

    public static void main(String[] args) {
        String selected = choose("red", "blue");

        var inferred = choose(10, 20);

        Number asNumber =
                ChooseInferenceDemo.<Number>choose(10, 2.5);

        System.out.println(selected);
        System.out.println(inferred);
        System.out.println(asNumber);
    }
}
```

Run:

```bash
javac ChooseInferenceDemo.java
java ChooseInferenceDemo
```

Stdout:

```text
red
10
10
```

`<Number>` is an explicit type argument for `choose`, so both `Integer` (from `10`) and `Double` (from `2.5`) can be used via type `Number`. The result has static type `Number`, even though the object selected at runtime is `Integer`.

If you supply an incompatible type witness, the compiler rejects it. Example:

```java
// Intentionally invalid:
String s = ChooseInferenceDemo.<String>choose("a", 42);
```

`42` does not match `String`, so you cannot force the compiler to "infer" wrongly with `<String>`. A type witness is a **type-checking constraint**, not a cast or an instruction to bypass the type system.

### When should you specify explicit type arguments?

Usually the compiler infers them from arguments:

```java
String selected = choose("red", "blue");
```

Writing `<String>` explicitly is typically unnecessary. However, for zero-argument generic factories or when clarifying a common/result type, a type witness helps express intent and eliminate ambiguity.

## 16. `var` and Wildcards: Do Not Confuse an Unknown Type with `Object`

A common need is simply **reading** from a list without needing to know its exact element type. Use `List<?>` for that:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

This is an illustrative method meant to be placed inside a class.

`List<?>` differs from raw `List`:

- `List<?>` remains a generic type with an **unknown** type argument, so the compiler enforces safety constraints. For instance, you cannot arbitrarily add `"a"` to a `List<?>`.
- Raw `List` bypasses generic checking at the use site and can trigger unchecked warnings.
- `List<Object>` has `Object` as its exact element type argument; it cannot directly accept `List<String>` due to invariance.
- `var x = new ArrayList<>()` without data or context typically yields `ArrayList<Object>`, **not** `ArrayList<?>`.

Common error example:

```java
List<String> strings = new ArrayList<>();
// List<Object> objects = strings; // Invalid.
List<?> unknown = strings;         // Valid.
```

Inference with `var` does not alter Java's variance or wildcard rules.

## 17. Cases Where the Compiler Cannot Infer from `var`

Certain uses of `var` are rejected or lead to unintended types:

### Only `null`

```java
// var value = null; // Error: no suitable type to infer.
String value = null; // Valid: target type String is present.
```

### Missing initializer

```java
// var items; // Invalid.
java.util.List<String> items;
items = new java.util.ArrayList<>();
```

A local variable declared with an explicit type name can be assigned later, provided definite assignment rules are met before reading.

### Standalone lambda/method reference without target type

```java
// var predicate = x -> x.length() > 0; // Invalid.
java.util.function.Predicate<String> predicate =
        x -> x.length() > 0;
```

A lambda requires a **functional interface target type**. Although `var` may appear in a lambda's parameter declarations under Java 11+ rules, a lambda expression cannot supply a functional interface type on its own for a `var` initializer.

### Empty diamond

```java
var items = new java.util.ArrayList<>();
```

This line is valid, yet `items` is `ArrayList<Object>`, not `ArrayList<String>` merely because you intend to add Strings later.

### Anonymous classes or expressions with complex inferred types

`var` can infer a type that is overly specific or awkward to name directly. With an anonymous class, local variable inference can retain enough anonymous type information to invoke members directly within scope, unlike declaring an interface on the left.

When types become obscure or an API calls for an abstract contract, spelling out the type on the left usually makes code easier to maintain.

## 18. Diamond and Anonymous Classes: Java Version Notes

Since Java 9, diamond can appear on anonymous classes in language-permitted cases. Still, the compiler imposes conditions on types inferred for anonymous classes (including that inferred types be denotable in source syntax).

Do not pick an arbitrary `new SomeGeneric<>() { ... }` snippet and assume it is always valid; inspect the constructor, inference, and applicable restrictions.

In Java 17+, when the goal is illustrating ordinary diamond and `var`, examples like `new ArrayList<>()` or `new Pair<>("x", 1)` are clearer. Anonymous subclasses also relate to preserving generic superclass metadata, a separate topic from this lesson's type inference focus.

## 19. Common Mistakes and Misconceptions

**Mistake 1 — "`var` always infers `Object`."** False. `var text = "a"` infers `String`; `var list = new ArrayList<String>()` infers `ArrayList<String>`.

**Mistake 2 — "`new ArrayList<>()` always creates `ArrayList<Object>`."** False. With a `List<String>` target type or suitable constructor arguments, diamond can infer `String`. It falls back to `Object` when there are no sufficiently specific constraints, such as `var x = new ArrayList<>()`.

**Mistake 3 — "The compiler inspects subsequent `add(...)` calls to determine `E`."** False. A variable's type is fixed at its declaration line and does not change based on subsequent calls.

**Mistake 4 — "`var` is dynamic typing like JavaScript."** False. Java remains statically type-checked; `var x = "a"; x = 1;` is an error.

**Mistake 5 — "Diamond is the same as a raw type."** False. Diamond requests generic argument inference; raw types drop generic type info at the use site.

**Mistake 6 — "`List<?>` is the same as `List<Object>`."** False. A wildcard represents an unknown type argument; `List<Object>` has the concrete type argument `Object`. Java Generics are invariant by default.

**Mistake 7 — "The `<String>` in `Collections.<String>emptyList()` is a cast."** False. It supplies a type argument to a generic method, subject to normal type checking.

**Mistake 8 — "`new ArrayList<String>()` and `Collections.<String>emptyList()` are the same generic syntax."** Not quite. The former applies a type argument to class instance creation; the latter applies it to a generic method invocation.

**Mistake 9 — "If code compiles with `var`, its types will always be obvious to readers."** Not necessarily. `var` can hide that an initializer inferred `Object` or an unintended concrete class. Choose whichever style keeps code clear for maintainers.

**Mistake 10 — "Explicit type arguments generate separate runtime classes per type."** False. Standard Java Generics undergo type erasure. Both explicit and inferred type arguments primarily serve compile-time type checking.

**Mistake 11 — "You can fix any mismatch with an arbitrary type witness."** False. `ChooseInferenceDemo.<String>choose("a", 42)` still fails because the second argument does not satisfy `String`.

**Mistake 12 — "Every generic method depends on a target type."** False. Many methods already get enough information from their input arguments; target type is just one constraint source participating in inference under specific rules.

## 20. Decision Table for Practical Coding

| Goal | Suggested syntax | Why |
|---|---|---|
| Want variable with `List<String>` contract | `List<String> x = new ArrayList<>();` | Explicit interface; diamond uses target type |
| Want `var` while keeping `String` | `var x = new ArrayList<String>();` | Initializer carries the generic argument |
| Copy an already-typed collection | `var x = new ArrayList<>(List.of("a"));` | Constructor argument enables inferring `String` |
| Want an empty unmodifiable list | `List<String> x = List.of();` | Target type supplies `String` |
| Want `var` with an empty generic factory | `var x = List.<String>of();` | Type witness states the type argument explicitly |
| Want a generic utility for many data types | `<T> ...` letting compiler infer from input | Single algorithm, still type-checked |
| Want to state a method type argument explicitly | `Utils.<Number>choose(1, 2.5)` | Guides method inference, not a cast |
| Unknown element type, mostly reading | `List<?> items` | Preserves wildcard safety |
| Expose an API bound to an interface | Declare `List<T>`, `Map<K,V>` at boundaries | Reduces coupling to implementation |
| Keep code concise when type is obvious | `var` for suitable local variables | Less repetition, still type-safe when initializer is explicit |

This table does not dictate a single mandatory style. When choosing between `var` and explicit types, the key criterion is **whether readers can accurately recognize the data type and type contract right at the declaration**.

## 21. Integrated Practice Exercise with Concrete Output

Create file **`InferencePracticeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class InferencePracticeDemo {

    static <T> List<T> copy(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> one = new ArrayList<>();
        var two = new ArrayList<String>();
        var three = new ArrayList<>();
        var four = new ArrayList<>(List.of("A", "B"));

        one.add("one");
        two.add("two");
        three.add("three");
        three.add(3);
        four.add("C");

        List<String> copied = copy(four);
        var emptyTyped = List.<String>of();

        System.out.println(one);
        System.out.println(two);
        System.out.println(three);
        System.out.println(four);
        System.out.println(copied);
        System.out.println(emptyTyped.size());
    }
}
```

Compile and run:

```bash
javac InferencePracticeDemo.java
java InferencePracticeDemo
```

Stdout:

```text
[one]
[two]
[three, 3]
[A, B, C]
[A, B, C]
0
```

Before running, predict:

1. What is the static type of `one`? **Answer:** `List<String>`.
2. What type is `two`? **Answer:** `ArrayList<String>`.
3. What type is `three`? **Answer:** `ArrayList<Object>`.
4. What type is `four`? **Answer:** `ArrayList<String>`.
5. Why can `copy(four)` return `List<String>`? **Answer:** `List<? extends T>` accepts a compatible element list and the compiler infers `T` from the call and target type.
6. Why is `List.<String>of()` still empty? **Answer:** `<String>` only supplies the type argument; it creates no elements.
7. Does `three.add(3)` change `three`'s type to `ArrayList<Integer>`? **Answer:** No; it was `ArrayList<Object>` from its initializer.

Another quick experiment is replacing:

```java
var three = new ArrayList<>();
```

with:

```java
var three = new ArrayList<String>();
```

Then the compiler rejects `three.add(3)` because the element type is now `String`. That is a direct way to observe the effect of adding an explicit type argument.

## 22. Distinguishing Compile-Time Errors

When encountering an error message, determine which phase it belongs to:

| Erroneous code | Problem | Fix matching intent |
|---|---|---|
| `var x = null;` | No initializer type to infer from | State variable type: `String x = null;` |
| `var f = s -> s.length();` | Lambda lacks a functional interface target type | Declare `Function<String,Integer>` |
| `var x = new ArrayList<>(); String s = x.get(0);` | `E` was inferred as `Object` | Add target `List<String>` or constructor `<String>` |
| `List<Object> x = new ArrayList<String>();` | Generic invariance | Choose `List<String>` or an appropriate wildcard |
| `var x = new ArrayList<String>(); x.add(1);` | `Integer` incompatible with `String` | Add strings only or intentionally adjust element type |
| `List<String> x = List.of(); x.add("a");` | Factory returns an unmodifiable list | Use `new ArrayList<>(List.of())` if mutation is needed |
| `ChooseInferenceDemo.<String>choose("a", 42)` | Type witness conflicts with arguments | Pass `String` arguments or choose a compatible common type |

Type-inference compile errors can look verbose because the compiler solves multiple constraints. Instead of patching with casts or raw types, ask: **what is the expected type, and which context is supplying that information?**

## 23. Key Takeaways

Three complementary mechanisms:

- **Diamond `<>`** infers type arguments when invoking a generic class constructor.
- **`var`** infers the type of a **local variable** from its initializer; the inferred type remains fixed and compiler-checked.
- **Explicit type arguments** such as `new ArrayList<String>()`, `List.<String>of()`, or `Utility.<Number>method(...)` state the intended type explicitly and can guide generic type inference.

`List<String> x = new ArrayList<>()` and `var x = new ArrayList<>()` are easy to confuse, yet the first has target type `String`, whereas the second typically infers `ArrayList<Object>` if the constructor offers no other constraints. Conversely, `var x = new ArrayList<String>()` and `var x = new ArrayList<>(List.of("a"))` preserve `String` type information.

**Choose syntax based on which sources of type information are actually present at the initialization site.** The compiler infers from declarations, arguments, and context; it does not "learn" element types from subsequent `add(...)` calls.

Standard references:

- [Java Language Specification §14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): `var` and local variable type inference rules.
- [Java Language Specification §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): diamond and object instantiation.
- [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): constraint system for type inference.
- [Java Language Specification §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): generic method invocation and explicit type arguments.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): generic type arguments and type relationships.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): why compile-time generics do not create separate runtime classes.