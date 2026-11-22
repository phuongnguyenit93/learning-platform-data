# Downcast Compatibility in Java Patterns

## 1. What Is the “Downcast Compatibility” Condition?

When writing `value instanceof Dog dog`, Java must answer **two different questions**:

1. **At compile time:** given the **static type** of the expression `value` and the **target type** `Dog`, is this check valid in the type system?
2. **At runtime:** is the value referenced by `value` actually an object compatible with `Dog`? If so, Java initializes the pattern variable `dog` and the condition evaluates to `true`; otherwise, the condition evaluates to `false`.

The first question is the subject of **downcast compatibility** in Java pattern syntax. It is a **compile-time** filter, not a guarantee that the `instanceof` expression will evaluate to `true`.

In **Java 17**, [JLS §14.30.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1) specifies that an expression `e` is compatible with a type pattern of type `T` if `e` is **downcast compatible** with `T` according to [JLS §5.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5). Practically speaking, the compiler must find a suitable reference type conversion that **does not rely on an unchecked narrowing reference conversion**. This rule allows meaningful type checks while preventing cases that are guaranteed to be incompatible or require assuming generic type arguments that the runtime cannot verify.

The name “downcast compatible” **does not mean** a pattern can only be written from a superclass variable to a subclass. The type system also considers classes, interfaces, arrays, generics, and other reference conversions. Specifically for `instanceof` type patterns, Java 17 also has an additional rule: a pattern that is trivially true based solely on the static type may be rejected as a **redundant check**.

Starting in **Java 21**, JLS §14.30.3 describes a type pattern as *applicable* at type `T` when `T` is **checked cast convertible** to the pattern's type. Java 21 also supports record patterns and patterns in `switch`. Therefore, when reading documentation across multiple versions, you should match the terminology and rules to the version you are compiling against; the basic `instanceof` examples in this article use Java 17, and the record pattern examples use Java 21.

## 2. Distinguishing Convertibility, Matching, and Explicit Casting

Consider the hierarchy:

```text
Animal
├── Dog
└── Cat
```

And the declarations:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}
```

With a variable of static type `Animal`:

```java
Animal animal = new Dog();

if (animal instanceof Dog dog) {
    System.out.println("Matched Dog");
}
```

The compiler **accepts** the check because a reference of type `Animal` can perfectly well hold a `Dog` object. When the program runs, the actual object is indeed a `Dog`, the pattern matches, and the variable `dog` is initialized.

Change the object to `new Cat()`:

```java
Animal animal = new Cat();

if (animal instanceof Dog dog) {
    // Does not enter this branch.
}
```

The code still **compiles** because the static type is still `Animal`; however, on this run the pattern does not match, so `dog` is not initialized for use in the success branch.

With an explicit cast:

```java
Animal animal = new Cat();

// Dog dog = (Dog) animal; // Compiles, but throws ClassCastException at runtime.
```

`(Dog) animal` instructs the runtime to perform the cast and can throw `ClassCastException`. By contrast, `animal instanceof Dog dog` checks first; if it does not match, it evaluates to `false` and skips the `if` body, so the check itself does not cause a `ClassCastException` due to an incompatible object type.

| Concept | When is it determined? | Example `Animal animal = new Cat();` |
| --- | --- | --- |
| Is the pattern compatible with the static type? | Compile time | `animal instanceof Dog dog` is valid |
| Does the value match the type pattern? | Runtime | `false` because the object is `Cat` |
| Is the pattern variable bound to a value? | When the runtime match succeeds | No `dog` is available |
| Does an explicit cast succeed? | May require a runtime check | `(Dog) animal` throws `ClassCastException` |

**Key takeaway:** *being allowed to check* is different from *the check succeeding*; a pattern is a conditional check, whereas an explicit cast can fail with an exception.

## 3. Cases the Compiler Allows or Rejects

### 3.1. From Supertype to Subtype: Valid If It Can Happen

```java
Object source = "Java";

if (source instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

`Object` can hold a reference to `String`. Although not every `Object` is a `String`, the expression is meaningful and valid. This is the most familiar example of a “downcast”-style check.

Similarly, `Animal` can hold a `Dog`, and an `Animal` can hold a subclass instance of `Dog`; the pattern `Dog dog` still matches the descendant object because inheritance is transitive.

### 3.2. Two Clearly Disjoint Class Types: Compile-Time Error

```java
String input = "Java";

// INVALID: String and Integer are two final classes with no common objects.
// if (input instanceof Integer number) {
//     System.out.println(number);
// }
```

`String` is `final` and is not an `Integer`, so the compiler can prove that no object can be both a `String` and an `Integer`. Here, Java **does not** allow the check to run and return `false`; it rejects the syntax at compile time.

You must consider the **static type of the expression**, not just guess the runtime value. If the variable is declared as `Object`, the check `obj instanceof Integer number` is valid because an arbitrary `Object` might be an `Integer`.

### 3.3. Two Sibling Classes With No Common Objects

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}

Dog dog = new Dog();

// INVALID: no subclass/superclass relationship between Dog and Cat.
// if (dog instanceof Cat cat) { }
```

With a variable of static type `Dog`, checking against `Cat` is invalid. However, if the variable has static type `Animal`, that check is valid:

```java
Animal animal = new Dog();

if (animal instanceof Cat cat) {
    // Syntactically valid, but does not match on this run.
}
```

Therefore, you cannot conclude validity solely from “the actual object is a `Dog`.” **The compiler uses the static type** to decide whether the check could possibly succeed in some situation.

### 3.4. Redundant Checks With `instanceof` Type Patterns

```java
String value = "Java";

System.out.println(value instanceof Object); // true (traditional type test)

// INVALID in Java 17: type pattern Object obj is guaranteed to match every non-null String.
// if (value instanceof Object obj) {
//     System.out.println(obj);
// }
```

Java 17 does not allow using the type pattern `Object obj` when the static type `String` is already a subtype of the pattern's type, because this is a redundant pattern check under `instanceof` rules. The fact that `String` can be converted to `Object` **does not mean** every pattern syntax is valid.

**How to fix:** if you already know the static type and want a supertype variable, assign directly: `Object obj = value;`. If you need to branch on the actual subtype, use a variable with a broader static type, such as `Object input`, and then check `input instanceof String text`.

## 4. Interfaces: Compatible Even Without Direct Implementation

Java allows a **non-final** class to be extended by a new class that implements additional interfaces. Therefore, checking against an interface can be valid even if the superclass does not directly `implements` that interface.

```java
interface Tagged {}

class OpenBase {}

class TaggedChild extends OpenBase implements Tagged {}

OpenBase value = new TaggedChild();

if (value instanceof Tagged tag) {
    System.out.println("Tagged"); // Tagged
}
```

The compiler allows this because an instance of a subclass of `OpenBase` can also implement `Tagged`; in the example above, it is indeed a `TaggedChild`.

Conversely, if a **final** class does not implement an interface, no subclass can add that interface:

```java
interface Tagged {}
final class FixedBase {}

FixedBase value = new FixedBase();

// INVALID: FixedBase is final and does not implement Tagged.
// if (value instanceof Tagged tag) { }
```

In Java 17, the rules for **disjoint** types also consider `sealed` relationships and the list of permitted subclasses/interfaces. Thus, do not assume an error simply because “this class does not `implements` the interface”; you must consider whether a valid subclass could exist.

**Practical use:** when handling a behavioral role (such as `Runnable`), `value instanceof Runnable runnable` is usually more appropriate than checking all concrete classes that might implement that role.

## 5. Generic Types and Why Unchecked Narrowing Must Be Avoided

This is the most commonly misunderstood aspect of **downcast compatibility**.

### 5.1. Cannot Infer `List<String>` From an `Object`

```java
Object value = java.util.List.of("Java");

// INVALID: from Object, cannot safely check the String type argument.
// if (value instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

The generic type argument of `List<String>` is not fully retained for runtime checking (type erasure). From the static type `Object`, checking directly for `List<String>` would rely on an **unchecked** narrowing reference conversion; that is not a valid condition for writing the type pattern `List<String> strings` in this case.

You can check a **reifiable** type using a wildcard:

```java
Object value = java.util.List.of("Java");

if (value instanceof java.util.List<?> elements) {
    System.out.println(elements.size()); // 1
}
```

Here, `List<?>` confirms that the runtime value is a `List`, without asserting the type of each element. To use an element as a `String`, check it separately:

```java
if (value instanceof java.util.List<?> elements
        && !elements.isEmpty()
        && elements.get(0) instanceof String first) {
    System.out.println(first.toUpperCase()); // JAVA
}
```

The right-hand side of `&&` is safe because the preceding checks have already matched. Even if the first element is a `String`, that **does not prove every element of the List is a String**.

### 5.2. Some Type Patterns With Generic Parameters Are Still Valid

```java
java.util.List<Integer> numbers =
        new java.util.ArrayList<>(java.util.List.of(2, 4));

if (numbers instanceof java.util.ArrayList<Integer> actual) {
    System.out.println(actual.get(0)); // 2
}
```

The snippet above is valid in Java 17. Because `numbers` **already has static type `List<Integer>`**, the compiler can accept a checked narrowing conversion from `List<Integer>` to `ArrayList<Integer>`. The runtime check verifies that it is an `ArrayList`; the consistency of the `Integer` type argument is already established in the static type system, rather than the JVM checking every element for `Integer` during `instanceof`.

Comparison:

| Expression static type | Pattern type | Valid? | Explanation |
| --- | --- | --- | --- |
| `Object` | `String text` | Yes | Can be checked-cast to String |
| `Animal` | `Dog dog` | Yes | Animal can point to Dog |
| `String` | `Integer n` | No | Two final types with no common objects |
| `Object` | `List<?> xs` | Yes | Can check the List itself |
| `Object` | `List<String> xs` | No | Requires unchecked narrowing on generic type |
| `List<Integer>` | `ArrayList<Integer> xs` | Yes | Type argument is already compatible from static type |
| `String` | `Object obj` | No for Java 17 type patterns | Redundant pattern check because static type is a subtype |

**Do not assume** that all generic patterns are forbidden. What matters is whether the **source–target type pair** has a checked conversion accepted by the language.

## 6. `null` and the Difference Between Casting and Patterns

With `null`, Java clearly distinguishes between an explicit cast and `instanceof`:

```java
Object value = null;

System.out.println(value instanceof String); // false

if (value instanceof String text) {
    // Does not execute; text is not initialized from null.
}

String casted = (String) value; // Valid, casted is still null.
```

The cast `(String) null` succeeds and evaluates to `null`. By contrast, `null` **does not match the type pattern `String text`** in `instanceof`. This `false` result causes no error and does not bind `null` to `text` for use in the success branch.

This is a sharp illustration of the following:

- **Compile-time type validity** does not determine whether a pattern value will match.
- **Casting can accept null**, whereas **`instanceof` type patterns refuse to match null**.
- You do not need to write `value != null && value instanceof String text` just to avoid `NullPointerException`: the `instanceof` operator is already null-safe.

With Java 21 record patterns (in a later section), a record containing a `null` component can cause the **component type pattern** not to match, even when the record object itself is non-null.

## 7. Java 17: Complete Standalone Runnable Program

Save the following program to **`DowncastPatternDemo.java`**:

```java
public class DowncastPatternDemo {
    static class Animal {
        final String name;

        Animal(String name) {
            this.name = name;
        }
    }

    static final class Dog extends Animal implements Runnable {
        Dog(String name) {
            super(name);
        }

        String bark() {
            return "woof";
        }

        @Override
        public void run() {
            // Demo for Runnable execution capability.
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    static String describe(Animal value) {
        if (value instanceof Dog dog) {
            return "Dog:" + dog.name + ":" + dog.bark();
        }

        if (value instanceof Cat cat) {
            return "Cat:" + cat.name;
        }

        return value == null ? "null" : "Animal:" + value.name;
    }

    public static void main(String[] args) {
        Animal[] animals = {
            new Dog("Rex"),
            new Cat("Miu"),
            new Animal("Base"),
            null
        };

        for (Animal a : animals) {
            System.out.println(describe(a));
        }

        Animal pet = new Dog("Rex");
        if (pet instanceof Runnable runnable) {
            System.out.println("implements Runnable=" + (runnable != null));
        }

        java.util.List<Integer> numbers =
            new java.util.ArrayList<>(java.util.List.of(2, 4));

        if (numbers instanceof java.util.ArrayList<Integer> values) {
            System.out.println("first=" + values.get(0));
        }

        Object any = java.util.List.of("x");
        if (any instanceof java.util.List<?> items) {
            System.out.println("size=" + items.size());
        }

        Object other = "text";
        System.out.println("other is Dog=" + (other instanceof Dog));
    }
}
```

Use **JDK 17+** to compile and run:

```bash
javac --release 17 DowncastPatternDemo.java
java DowncastPatternDemo
```

Output:

```text
Dog:Rex:woof
Cat:Miu
Animal:Base
null
implements Runnable=true
first=2
size=1
other is Dog=false
```

Explanation:

1. With `new Dog("Rex")`, `Animal` can downcast to `Dog` and the actual value matches, so it prints `Dog:Rex:woof`.
2. With `new Cat("Miu")`, the pattern `Dog dog` is **valid but does not match**; the pattern `Cat cat` matches.
3. With `new Animal("Base")`, neither subtype pattern matches; the code handles the supertype.
4. With `null`, the type patterns do not match, so the final branch returns the string `"null"`.
5. Even though `pet` is declared as `Animal`, the runtime `Dog` object implements `Runnable`, so the interface pattern is valid and matches.
6. From `List<Integer>` to `ArrayList<Integer>`, the compiler has enough generic information to accept the specific pattern; the actual object is an `ArrayList`, so it prints the first element `2`.
7. With `Object any`, the `List<?>` pattern checks `List` at runtime and outputs `size=1`.
8. `Object other` holds a `String`, so the `Dog` pattern is valid for the source type `Object` but evaluates to `false` at runtime.

This example uses `instanceof` type patterns that became standard in Java 16; `--release 17` is sufficient and `--enable-preview` is not needed.

## 8. Java 21+: Record Patterns Check Compatibility Per Component

Java 21 extends pattern matching with **record patterns** and patterns in `switch`. In addition to compatibility between the selector type and the record type, the compiler also checks each record component's pattern against the declared component type.

For example, the record `Envelope(Object content)` has a component with static type `Object`. The pattern `Envelope(String text)` is applicable because the `Object` component can hold a `String`:

```java
record Envelope(Object content) {}

Object input = new Envelope("Java");

if (input instanceof Envelope(String text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

This is an **illustrative snippet in a context where `Envelope` is declared**, requiring Java 21+. First, the runtime checks whether `input` is an `Envelope`; then it extracts the component and checks whether the component is a `String`. Only when **all relevant parts match** does the whole pattern succeed and `text` become usable.

Complete runnable example: save as **`PatternRecordDemo.java`**.

```java
public class PatternRecordDemo {
    record Envelope(Object content) {}

    static String inspect(Object input) {
        return switch (input) {
            case Envelope(String text) -> "text:" + text;
            case Envelope(Integer number) -> "number:" + number;
            case null -> "null input";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(new Envelope("Java")));
        System.out.println(inspect(new Envelope(7)));
        System.out.println(inspect(new Envelope(null)));
        System.out.println(inspect(null));
    }
}
```

Compile/run with **JDK 21+**:

```bash
javac --release 21 PatternRecordDemo.java
java PatternRecordDemo
```

Output:

```text
text:Java
number:7
other
null input
```

Notice the differences:

- `new Envelope("Java")` matches the record pattern containing `String text`.
- `new Envelope(7)` matches the record pattern containing `Integer number`.
- `new Envelope(null)` is **a non-null record**, but its `null` component does not match the `String` or `Integer` type patterns, so it falls into `default`.
- `null` is not a record; it is handled separately by `case null`.

Pattern `switch` branches also have **dominance** rules: a general `case` can make a subsequent specific `case` unreachable. For example, if you place `case Object obj` before `case String text` when both apply to the same selector type, the `String` branch is dominated and the compiler reports an error. That is a different rule from downcast compatibility: **an individual pattern can have a valid type while its position in `switch` is invalid**.

When writing only for Java 17, use `instanceof` type patterns; do not use record pattern syntax or `case String s when ...` because they are not standard features in that version.

## 9. Practical Check: Three Decision Layers

When you encounter a confusing pattern statement, check it in order:

**Layer 1 — Static type of the expression.** For example, with `Object x`, the pattern `String s` can be valid; with `String x`, the pattern `Integer n` is an impossible check and is forbidden. Generic arguments, `final` modifiers, `sealed` relationships, and interfaces can also affect this decision.

**Layer 2 — Whether the pattern is applicable and whether it violates additional rules.** Java 17 rejects redundant `instanceof` type patterns even though converting to a supertype is allowed. Java 21 checks applicability for record/component patterns and dominance of `switch` branches.

**Layer 3 — Whether the runtime value matches.** The object may be the right subtype, the wrong subtype, or `null`. If the type pattern does not match, `instanceof` returns `false`; if it matches, the pattern variable is initialized and Java allows its use along paths where the compiler proves the match succeeded.

Short decision table:

| Case | Compile time | Runtime |
| --- | --- | --- |
| `Animal a = new Dog(); a instanceof Dog d` | Valid | `true`, `d` is bound |
| `Animal a = new Cat(); a instanceof Dog d` | Valid | `false` |
| `Object x = "abc"; x instanceof String s` | Valid | `true`, `s` is bound |
| `Object x = null; x instanceof String s` | Valid | `false` |
| `String x = "abc"; x instanceof Integer n` | Error | Does not run |
| `Object x = List.of("a"); x instanceof List<String> xs` | Error | Does not run |
| `Object x = List.of("a"); x instanceof List<?> xs` | Valid | `true` |
| `String x = "abc"; x instanceof Object o` | Redundant type pattern error (Java 17) | Does not run |

## 10. Common Mistakes and How to Avoid Them

**Mistake 1: Equating `can be cast` with `matches`.** `Animal` can be cast to `Dog`, but an actual `Cat` object is not a `Dog`. Keep compile-time checks separate from runtime checks.

**Mistake 2: Assuming every wrong-type `instanceof` will just return `false`.** For static types proven to have no common objects, Java rejects the check at compile time. To check a value that genuinely has multiple possible types, keep it under an appropriate source type (such as `Object` or a common interface).

**Mistake 3: Using `instanceof List<String>` on an `Object` variable.** Generic arguments are not fully checked at runtime. Use `List<?>`, check individual elements when needed, and preserve safe static generic types from the start of the pipeline.

**Mistake 4: Confusing `null` with a failed cast.** `(Dog) null` yields `null`; `null instanceof Dog dog` returns `false`. A type pattern does not bind a variable to `null`.

**Mistake 5: Forgetting the redundant pattern rule.** Java 17 allows `"abc" instanceof Object` as a type comparison, but rejects `"abc" instanceof Object obj` as a type pattern.

**Mistake 6: Ignoring `final`/`sealed` and interfaces.** A normal class type can have a subclass that implements an interface; a final class cannot. Compatibility must account for whether a common object type can exist.

**Mistake 7: Trying to use a pattern variable in a non-matching branch.** The pattern variable `dog` is only valid in scopes where the compiler proves the pattern matched. Use `if (x instanceof Dog dog)` and work with `dog` in the true branch, or use a guard clause that exits the non-matching branch with `return`.

**Mistake 8: Mixing Java 17 and Java 21 rules.** Java 17 has type patterns for `instanceof`; Java 21 officially supports record patterns and patterns in `switch`. Compile with the exact `--release` level you intend to target.

## 11. Practice Questions

**Question 1.** Given `Animal a = new Cat(); if (a instanceof Dog d) ...`. Is this a compile-time error or does it evaluate to `false`?

*Answer:* It compiles cleanly and evaluates to `false` at runtime. The static type `Animal` can hold a `Dog`, but the actual object this time is a `Cat`.

**Question 2.** Given `String s = "x";`, why is `s instanceof Object` valid, while `s instanceof Object obj` in Java 17 is an error?

*Answer:* The first expression is a traditional type comparison. The second uses a type pattern, which is considered redundant because `String` is already a subtype of `Object`.

**Question 3.** `Object x = List.of("x");`. How do you validly check that `x` is a `List`?

*Answer:* Use `x instanceof List<?> values`. Do not assert `List<String>` solely from a runtime check on `Object`; if you need elements to be `String`, check the elements separately.

**Question 4.** `Object x = null;`. How do the results of `x instanceof Dog dog` and `(Dog) x` differ?

*Answer:* `instanceof` returns `false` and `dog` is not bound; the cast returns `null` (it does not throw `ClassCastException` for a `null` value).

**Question 5.** In Java 21, given `record Box(Object value) {}`, is the pattern `Box(String s)` applicable to a variable of type `Object`? What if the box contains an `Integer`?

*Answer:* Yes: `Object` can be checked as `Box`, and the `Object` component can be checked as `String`. If the runtime component is an `Integer`, the record pattern does not match; the variable `s` is not bound.

## 12. Checklist When Applying in a Project

1. Identify the **static type** of the value being checked.
2. Identify the **target pattern type**, especially class/interface relationships and generic arguments.
3. Check whether the conversion is **checked**, requires **unchecked narrowing**, or is proven impossible.
4. Check construct-specific rules (redundant `instanceof` patterns, `switch` dominance, record components).
5. Handle `null` values separately and account for non-matching runtime branches.
6. Only use the pattern variable in control-flow paths where the pattern has matched.
7. Compile with the target Java version (`--release 17` or `--release 21`).

**Remember:** *Downcast compatibility/applicability decides whether a pattern is allowed to be checked; matching decides whether the actual object matches; flow scoping decides where the bound variable can be used.* These three layers explain most errors with `instanceof` type patterns, generics, and record patterns.

### Official Documentation

- [Java SE 17 JLS §14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1)
- [Java SE 17 JLS §5.5 — Casting Contexts (Downcast Compatible)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5)
- [Java SE 17 JLS §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [Java SE 21 JLS §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
