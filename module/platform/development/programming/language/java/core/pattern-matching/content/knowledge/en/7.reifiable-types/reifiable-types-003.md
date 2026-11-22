# Reifiable Types in `instanceof`

> **Module:** Java Core Pattern Matching → Generics and reifiable types. This lesson uses **Java 17** rules (Java 16+ relaxed a restriction on `instanceof`). Examples labeled **ERROR** are code that intentionally does not compile; the standalone, runnable program is in section 8.

## Objectives

After this lesson, you will be able to explain what a **reifiable type** is, identify which generic types retain enough information to be checked at runtime, choose the right way to write `instanceof` and type patterns in Java 17, and avoid confusing container-class checks with element-type checks. You will also learn an **important exception since Java 16**: certain checks with *non-reifiable* parameterized types still compile validly when **the static type of the left-hand expression** allows a safely checked downcast.

## 1. Why does `instanceof` relate to reifiable types?

Java is a language with **generic types**: `List<String>` and `List<Integer>` are two distinct static types, helping the compiler prevent type-unsafe operations in source code. However, **type erasure** removes most information about type arguments (`String`, `Integer`) when compiling to bytecode.

For example:

~~~java
java.util.List<String> words = java.util.List.of("Java");
java.util.List<Integer> numbers = java.util.List.of(42);
~~~

At runtime, the JVM sees two objects that implement `List`; it does not have a reliable runtime "stamp" indicating whether the generic argument of each reference is `String` or `Integer`. Therefore, an `instanceof List<String>` check cannot simply be interpreted as "the JVM verifies that every element of the list is a `String`".

A **reifiable type** is a type whose representation information is fully available at runtime according to the formal definition in the **Java Language Specification (JLS) `4.7**. These types are suitable for ordinary runtime type checks, for example `String`, `List<?>`, `String[]`.

Separate two concepts:

- **Static type (compile-time type)** of the left-hand expression: the type the compiler sees, for example `Object`, `List<Integer>`, or `List<?>`.
- **Target type to test on the right-hand side of `instanceof`**: the type or pattern matched against the value at runtime, for example `List<?>` or `ArrayList<Integer>`.

Not just any generic type name appearing after `instanceof` is valid; the condition also depends on the **left-hand static type** and the Java version.

## 2. Which types are reifiable?

According to JLS `4.7, a type is **reifiable** if it belongs to one of the following categories:

1. A **non-generic** class or interface type declaration, such as `String` or `Runnable`.
2. A parameterized generic type in which **all type arguments are unbounded wildcards (`?`)**, such as `List<?>` or `Map<?, ?>`.
3. A **raw type**, such as `List` or `Map` (retained for legacy code compatibility).
4. A **primitive type**, such as `int` and `boolean`, under the general definition of reifiability.
5. An **array type** whose element type is reifiable, such as `String[]`, `List<?>[]`.
6. A nested type whose type-name components are all reifiable under the JLS conditions.

Note specific to Java 17: even though `int` is classified as reifiable by the JLS, **`instanceof` in Java 17 only accepts reference target expressions and reference types according to the operator's rules**, so `x instanceof int` is **invalid**. Reifiability is a property of a *type*, not a license to use that type in every syntactic position.

| Type | Reifiable? | Reason |
| --- | --- | --- |
| `String`, `Number`, `Runnable` | Yes | Non-generic class/interface |
| `List<?>` | Yes | All type arguments are unbounded wildcards |
| `Map<?, ?>` | Yes | Both arguments are `?` |
| `List` | Yes | Raw type, but loses generic checking when used |
| `String[]`, `List<?>[]` | Yes | Array element type is reifiable |
| `List<String>` | **No** | Concrete argument `String` is erased |
| `List<Integer>` | **No** | Concrete argument `Integer` is erased |
| `List<? extends Number>` | **No** | Bounded wildcard, not `?` |
| `List<? super String>` | **No** | Bounded wildcard |
| `Map<String, ?>` | **No** | Not *all* arguments are `?` |
| Type variable `T` in `<T>` | **No** | Type `T` is not fully available at runtime |
| `List<String>[]` | **No** | Component `List<String>` is non-reifiable |

**Note:** Reifiable does not mean "a type that carries all domain information". `List<?>` is reifiable, but it only confirms that the object belongs to a `List` implementation; **it does not confirm the type of each element**.

## 3. Common way to write `instanceof` when the input is `Object`

There are two closely related forms:

~~~java
Object input = java.util.List.of("a", "b");

boolean oldForm = input instanceof java.util.List<?>;

if (input instanceof java.util.List<?> items) {
    System.out.println(items.size()); // items has type List<?>.
}
~~~

- `input instanceof List<?>` is a **type comparison**, returning `boolean`.
- `input instanceof List<?> items` is a **type pattern**, which both checks and declares the variable `items` with static type `List<?>` if the match succeeds.
- `items` does not yet have type `List<String>`. When retrieving an element with `items.get(0)`, you are only safely allowed to treat it as an `Object`; if you want to know whether it is a `String`, you must check separately.
- `input == null` does not match; both type comparison and type pattern in Java 17 return `false` when the input is `null`.

From `Object`, this is the reliable check when you have no static evidence about generic arguments. The wildcard form should generally be preferred over the raw type:

~~~java
Object input = java.util.List.of(1, 2);

// Valid, but uses a raw type:
if (input instanceof java.util.List) {
    System.out.println("Có một danh sách");
}

// Preferred:
if (input instanceof java.util.List<?> elements) {
    System.out.println("Kích thước: " + elements.size());
}
~~~

Raw `List` can produce warnings and lose generic checking in other operations, whereas `List<?>` accurately expresses that we **do not yet know the element type**.

## 4. Why is `Object instanceof List<String>` rejected?

The following snippet **intentionally does not compile** in Java 17:

~~~java
Object input = java.util.List.of("a", "b");

if (input instanceof java.util.List<String> words) { // ERROR
    System.out.println(words.get(0));
}
~~~

The type-comparison version is also rejected under the same condition:

~~~java
Object input = java.util.List.of("a", "b");

boolean ok = input instanceof java.util.List<String>; // ERROR
~~~

**It is not because the object happens to contain Strings or Integers.** The error occurs because the compiler only knows the static type of `input` is `Object`. A cast from `Object` to `List<String>` cannot fully check the `<String>` part at runtime; it is an *unchecked cast*, so `instanceof` does not permit such a test from an `Object` source.

If you want to know whether an `Object` is a list and contains only `String`s, you need two separate steps:

~~~java
Object input = java.util.List.of("a", "b");

if (input instanceof java.util.List<?> items) {
    boolean allStrings = items.stream()
            .allMatch(item -> item instanceof String);
    System.out.println(allStrings);
}
~~~

Step one confirms the object is a `List`. Step two actually checks **each present element**. For an empty list, `allMatch` returns `true` by the logical property of the universal quantifier "all"; that still **does not prove a runtime generic argument `String`**. Distinguish between "every current element is a string" and "the object carries the generic type `List<String>` at runtime".

## 5. Exception since Java 16: a non-reifiable RHS can still be valid

This is a particularly important point, often overlooked in older tutorials.

Before Java 16, **type comparison** after `instanceof` required the reference type to be reifiable. **Starting in Java 16**, this requirement was relaxed: certain non-reifiable parameterized types can still be used if **the left-hand expression is downcast-compatible with the type being tested**. Java 17 JLS `15.20.2 explicitly gives the following example.

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> values = new ArrayList<>();
boolean check = values instanceof ArrayList<Integer>; // VALID since Java 16.
System.out.println(check); // true
~~~

Here:

- `List<Integer>` is the **static type of the target**; the compiler already knows the type argument `Integer` of the reference.
- `ArrayList<Integer>` is a more specific implementation class of `List<Integer>`; casting between these two types **is checked by a runtime class test**, while the match of `<Integer>` is already established by static type information.
- Runtime checks whether the object is an `ArrayList`; **it does not read or check that every element is an `Integer`**.
- If `values` actually refers to another `List` implementation, the valid test still returns `false`.

The corresponding type pattern form is also valid:

~~~java
List<Integer> values = new ArrayList<>();

if (values instanceof ArrayList<Integer> actual) {
    System.out.println(actual.size()); // actual has type ArrayList<Integer>.
}
~~~

**Do not generalize this into "Java 17 allows all generics in instanceof".** The next snippet **intentionally does not compile**:

~~~java
List<Integer> values = new ArrayList<>();

boolean wrong = values instanceof ArrayList<String>; // ERROR: incompatible generics.
~~~

The compiler knows from `List<Integer>` that the target does not have a valid downcast to `ArrayList<String>` under Java's typing rules. Changing the implementation class name or assuming runtime values cannot bypass this check.

### How can a non-reifiable type appear after `instanceof` and still be valid?

There are three questions to answer:

1. **What is the static type of the left-hand expression?** `Object` is different from `List<Integer>`.
2. **What is the target type tested on the right-hand side?** `List<?>` is reifiable; `ArrayList<Integer>` is non-reifiable.
3. **Is there a valid checked downcast between the two types?** If valid, Java 17 can accept it even when the RHS is non-reifiable; if the conversion can only be unchecked or the generic arguments conflict, the compiler rejects it.

**Quick comparison:**

~~~java
Object obj = new ArrayList<Integer>();
// obj instanceof ArrayList<Integer>; // ERROR: Object lacks generic evidence.

List<Integer> typed = new ArrayList<>();
boolean ok = typed instanceof ArrayList<Integer>; // OK: static type retains Integer.
~~~

This is why it is accurate to say **"reifiable is usually the right choice for runtime checks from Object"**, instead of wrongly stating that **every RHS of instanceof must always be reifiable**.

## 6. Distinguishing type comparison and type pattern in Java 17

The two variants of `instanceof` have different additional rules:

~~~java
List<Integer> input = new ArrayList<>();

boolean b = input instanceof List<Integer>; // Valid: type comparison.
~~~

However, with the **pattern match operator** in **Java 17**, if the static type of the target expression is already a **subtype of the pattern type**, the compiler rejects a pattern that always matches any non-`null` value:

~~~java
List<Integer> input = new ArrayList<>();

if (input instanceof List<Integer> items) { // ERROR in Java 17.
    System.out.println(items.size());
}
~~~

The fix in this case is simply to use `input` directly. This is the **unconditional pattern** restriction in Java 17, which is **different** from the reifiability restriction. Do not confuse it with `List<Integer> input instanceof ArrayList<Integer> actual` in section 5: when the target is the `List` interface, it is **not guaranteed** to be an `ArrayList`.

**Version note:** Java 21 adjusts the rules for unconditional patterns. In this lesson, all conclusions about errors on type patterns covering the entire static type are explicitly scoped to **Java 17**, and should not be mechanically applied to all newer JDKs.

## 7. Arrays and type variables: two more easily confused cases

### 7.1. Arrays with reifiable element types

~~~java
Object a = new String[] {"a", "b"};
System.out.println(a instanceof String[]); // true

Object b = new java.util.List<?>[] {
    java.util.List.of("x"),
    java.util.List.of(10)
};
System.out.println(b instanceof java.util.List<?>[]); // true
~~~

`String[]` and `List<?>[]` are both reifiable. However, with `List<?>[]`, runtime can only verify the shape of **an array of lists**, not what element types are **inside each List**.

Types like `List<String>[]` are **non-reifiable**, and cannot be created directly with `new List<String>[n]`. This mechanism prevents certain cases of *heap pollution* because arrays support runtime component-type checking whereas generic arguments are erased.

### 7.2. Type variable `T` is not a runtime target type for `instanceof`

The following snippet **intentionally does not compile** in Java 17:

~~~java
static <T> boolean check(Object input) {
    return input instanceof T; // ERROR: no runtime type T to check.
}
~~~

If the type to check comes from a runtime parameter, you can use `Class<T>`:

~~~java
static <T> boolean isType(Object value, Class<T> type) {
    return type.isInstance(value);
}

System.out.println(isType("Java", String.class)); // true
System.out.println(isType(42, String.class));     // false
~~~

This is only an **illustrative snippet in a class/method context**, not a standalone program. `Class<T>.isInstance` checks a **runtime class**, and does not provide `List<String>.class`. Java does not support class literals containing concrete type arguments such as `List<String>.class`.

### 7.3. `null` and primitive types

In Java 17:

- `null instanceof List<?>` is `false` when written in a valid expression context.
- `input instanceof List<?> items` does not initialize `items` when `input == null`.
- `int` is a primitive type listed as reifiable by JLS `4.7, but `instanceof int` **is not supported in Java 17**. For boxed integers, checking the reference type `Integer` is valid when the source static type permits it.

## 8. Complete program: checking the right types within the right limits (Java 17)

Save the exact code below in **`ReifiableInstanceofDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReifiableInstanceofDemo {

    static String inspect(Object value) {
        if (!(value instanceof List<?> items)) {
            return "not a list";
        }

        int strings = 0;
        for (Object item : items) {
            if (item instanceof String text) {
                strings++;
            }
        }
        return "list size=" + items.size() + ", strings=" + strings;
    }

    static boolean isArrayListOfIntegers(List<Integer> input) {
        // Non-reifiable, but the check is valid because the static type is List<Integer>.
        return input instanceof ArrayList<Integer>;
    }

    static String arrayKind(Object input) {
        if (input instanceof List<?>[] rows) {
            return "array of lists, length=" + rows.length;
        }
        return "not an array of lists";
    }

    public static void main(String[] args) {
        System.out.println(inspect(List.of("A", 10, "B")));
        System.out.println(inspect("not list"));
        System.out.println(inspect(null));

        System.out.println(isArrayListOfIntegers(
                new ArrayList<>(List.of(1, 2))));
        System.out.println(isArrayListOfIntegers(List.of(1, 2)));

        System.out.println(arrayKind(new List<?>[] {
                List.of("X"),
                List.of(7)
        }));
    }
}
~~~

Use JDK 17 or later to compile under Java 17 rules:

~~~bash
javac --release 17 ReifiableInstanceofDemo.java
java ReifiableInstanceofDemo
~~~

**Exact stdout:**

~~~text
list size=3, strings=2
not a list
not a list
true
false
array of lists, length=2
~~~

Reading the output:

1. `List.of("A", 10, "B")` is a `List` with three elements; **two elements** match `String`. A `List<?>` check does not require all elements to have the same type.
2. `"not list"` and `null` both fail to match `List<?>`, so they return `not a list`.
3. `new ArrayList<>(...)` matches `ArrayList<Integer>` when the target is already declared as `List<Integer>`; a list created by `List.of(...)` is not an `ArrayList`, so the next line is `false`.
4. An array of `List<?>` is recognized properly; there is no generic type check performed on the elements inside the two lists.

**Scope of verification:** the example demonstrates that the code compiles and that runtime distinguishes classes/lists as described; it does not turn generic arguments into runtime data.

## 9. Generic casts and a "false sense of safety"

This is a snippet that **intentionally illustrates the risk**; it can run, but should not be used to validate data:

~~~java
Object input = java.util.List.of(7, 8);

@SuppressWarnings("unchecked")
java.util.List<String> unsafe = (java.util.List<String>) input;

// The cast above can pass the runtime List class check;
// the failure usually only surfaces when trying to read an Integer as a String.
String first = unsafe.get(0); // ClassCastException.
~~~

The `@SuppressWarnings("unchecked")` annotation only **hides the warning**; it does not attach the `String` type to the list at runtime. A situation where a generic reference or structure holds values that violate its type contract is a form of *heap pollution* risk.

**Safe approach:** read the input as `List<?>`, check each element, and build a properly typed result list:

~~~java
static List<String> checkedStrings(Object input) {
    if (!(input instanceof List<?> values)) {
        throw new IllegalArgumentException("Not a list");
    }

    List<String> result = new ArrayList<>();
    for (Object item : values) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Not a string: " + item);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
~~~

This is an **illustrative method** placed in a class that has imported `java.util.List` and `java.util.ArrayList`. Given an input containing only strings, it creates a safe, immutable `List<String>` copy **without needing an unchecked cast**. Given a list with an element other than `String`, it throws an intentional exception.

Do not confuse:

- `input instanceof List<?>`: confirms the **container object kind**.
- `item instanceof String`: confirms **one specific element**.
- `(List<String>) input`: asks the compiler to trust a cast that **does not fully check generic arguments**.
- `typedList instanceof ArrayList<Integer>` when the target is already `List<Integer>`: a concrete class test accepted by the compiler based on **static type** evidence, not per-element checking.

## 10. Workflow for choosing the right check

When writing `instanceof` involving generics:

1. **Identify the left-hand static type**: `Object`, `List<?>`, `List<Integer>`, or another type.
2. **Identify the actual goal**: checking whether the object is a list, a concrete implementation class, an array, or checking individual elements.
3. **Prefer reifiable types** if the type arguments are unknown: `List<?>`, `Map<?, ?>`, `List<?>[]`, `String[]`. Avoid raw types whenever possible.
4. **If the RHS is non-reifiable**, ask whether the compiler can prove a safely checked downcast from the static type. For example, `List<Integer>` to `ArrayList<Integer>` is a valid case in Java 17.
5. **If you need element-type guarantees**, check each value and construct a properly typed result; do not treat `instanceof List<?>` or an unchecked cast as proof.
6. **Consider null, a static type that is already a subtype, and the Java version**. `instanceof` on `null` does not match; Java 17 also has rules forbidding unconditional **type patterns**.

### Common misconceptions

- **"Every type after instanceof must be reifiable in Java 17."** False. Java 16 relaxed the requirement for type comparisons; Java 17 can accept `List<Integer> instanceof ArrayList<Integer>`.
- **"Java 17 allows Object instanceof List<String>."** False. `Object` does not guarantee the generic type `String`; the conversion can only be unchecked.
- **"List<?> is List<String> at runtime."** False. An unbounded wildcard retains information about the list class, not about its elements.
- **"List<? extends Number> is just as reifiable as List<?>."** False. Per JLS `4.7, a bounded wildcard does not satisfy the condition "all arguments are unbounded wildcards".
- **"instanceof checks every element."** False. A list containing both `String` and `Integer` still matches `List<?>`.
- **"Raw List is better than List<?> because it is reifiable."** Both are reifiable, but `List<?>` generally preserves better type constraints.
- **"SuppressWarnings makes generic casts safe."** False. The warning is suppressed, but no runtime information is added.
- **"Primitives are reifiable, so instanceof int works in Java 17."** False. Those are two separate language rules.
- **"Patterns and type comparisons share all the same rules."** False. Java 17 rejects certain type patterns already guaranteed by the static type, even when the equivalent type comparison is valid.

## 11. Self-Check

**Question 1.** Classify `List<?>`, `List<String>`, `Map<?, ?>`, `Map<String, ?>`, `String[]`, `List<?>[]` into reifiable and non-reifiable. Explain.

**Question 2.** Given `Object input = List.of("a")`, does `input instanceof List<String>` compile in Java 17? What if it is changed to `input instanceof List<?>`?

**Question 3.** Given `List<Integer> values = new ArrayList<>()`, why is `values instanceof ArrayList<Integer>` valid, even though `ArrayList<Integer>` is non-reifiable?

**Question 4.** With the same variable `values`, what happens if the RHS is changed to `ArrayList<String>`? Why?

**Question 5.** Does `input instanceof List<?> items` returning `true` prove that `items.get(0)` is a `String`? Give a practical way to check.

**Question 6.** Why is `List<Integer> values = new ArrayList<>(); values instanceof List<Integer> items` rejected under Java 17, while `values instanceof List<Integer>` (without binding) is accepted?

**Question 7.** `Object array = new List<?>[]{List.of("x"), List.of(42)};`. What does `array instanceof List<?>[]` return? Does it prove the inner lists have the same element type?

**Question 8.** Why can't you use `x instanceof T` inside a generic method `<T> boolean isT(Object x)`? What alternative works when accepting `Class<T>`?

### Answers and Explanations

1. **Reifiable:** `List<?>`, `Map<?, ?>`, `String[]`, `List<?>[]`. **Non-reifiable:** `List<String>`, `Map<String, ?>`. For parameterized generics, all arguments must be unbounded `?`.
2. **`List<String>`: compile error** because an `Object` source cannot be downcast with full checking of the generic argument. **`List<?>`: valid**, evaluates to `true` for `List.of("a")`.
3. `List<Integer>` on the source already carries static evidence of `Integer`; runtime only needs to test whether the implementation is `ArrayList`. This is the relaxation introduced in Java 16.
4. **Compile error**: `ArrayList<String>` is incompatible with the source `List<Integer>` under Java's casting rules.
5. **No**. Read elements as `Object` and then check `item instanceof String text` or check all elements and copy them.
6. In Java 17, a **type pattern covering the static type** is rejected as an unconditional pattern; a type comparison does not declare a pattern variable, so that specific restriction does not apply.
7. **`true`**: it is a `List<?>[]` array. There is no verification of the element types in each individual list.
8. `T` is a type variable whose type-argument information does not fully exist at runtime; you can use `type.isInstance(x)` with a `Class<T> type` parameter to check the runtime class (without verifying generic arguments).

## Official References

- [Java Language Specification 17, `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): type erasure mechanism.
- [Java Language Specification 17, `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): formal definition and categories of reifiable types.
- [Java Language Specification 17, `15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type comparison, pattern matching, compatibility, and changes since Java 16.
- [Java Language Specification 17, `14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): requirements for type patterns and pattern variable types.
- [Java Language Specification 17, `5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): checked/unchecked casting conversions.
