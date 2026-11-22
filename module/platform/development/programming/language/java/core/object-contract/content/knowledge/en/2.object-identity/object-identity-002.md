# The `==` and `!=` Operators on References in Java

## Lesson Objectives

After this lesson, you can:

- Explain the difference between **object identity** and **logical equality (equality by value or state)**.
- Predict the result of `==` and `!=` when two reference variables point to the same object, two different objects, or `null`.
- Choose `==`, `!=`, `equals()`, or `Objects.equals()` for the right situation.
- Recognize common pitfalls with `String`, wrapper types, arrays, `enum`, and `record`.

## 1. What Is a Reference and What Does `==` Actually Compare?

A reference-type variable can hold a reference to an object or the value `null`. Two variables can point to **one object**, even though they have two different names. Conversely, two objects can have completely identical data yet still be **two separate objects**.

For two compatible reference-type operands:

- `a == b` returns `true` if both reference **the exact same object**, or **both are `null`**; otherwise it returns `false`.
- `a != b` is the negation of `a == b`: it returns `true` when the two references are not identical.
- The result is the primitive type `boolean`. There is no implicit call to `equals()` when using `==` or `!=` on two references.
- Assigning one reference variable to another **copies the reference value**, not the object.

Example:

```java
Object original = new Object();
Object alias = original;       // Same object
Object another = new Object(); // Different object

System.out.println(original == alias);   // true
System.out.println(original == another); // false
System.out.println(original != another); // true
```

Even though two `new Object()` creations produce objects of the same type with no distinct fields to tell them apart, they still have different identities. This comparison does not rely on field contents, displayed memory addresses, variable names, or `hashCode()` results.

### `==` with Primitive Types Is a Different Comparison

When both operands are compatible primitive values, such as `int` or `boolean`, `==` compares **values**. Therefore, always determine the types of both operands before reasoning about the result:

```java
int x = 42;
int y = 42;
System.out.println(x == y); // true: compares int values

Integer boxedX = 42;
Integer boxedY = 42;
System.out.println(boxedX == boxedY); // true: two references to a cached Integer
```

Both lines print `true`, but due to **two different mechanisms**. The wrapper section below clarifies the limits of caching.

## 2. Complete Example, Compiled and Run with Java 17+

Save the following content to `IdentityOperatorsDemo.java`. This is a standalone program in which `Pair` is a `record` nested inside the class.

```java
import java.util.Arrays;

public class IdentityOperatorsDemo {
    record Pair(int left, int right) {}

    public static void main(String[] args) {
        Object first = new Object();
        Object alias = first;
        Object second = new Object();

        System.out.println("same object: " + (first == alias));
        System.out.println("different objects: " + (first != second));

        Object missing = null;
        System.out.println("missing == null: " + (missing == null));
        System.out.println("missing != first: " + (missing != first));

        String s1 = "java";
        String s2 = "java";
        String s3 = new String("java"); // Used only to demonstrate identity
        System.out.println("literal == literal: " + (s1 == s2));
        System.out.println("literal == new: " + (s1 == s3));
        System.out.println("literal.equals(new): " + s1.equals(s3));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        int[] arrayAlias = arrayA;
        System.out.println("array == alias: " + (arrayA == arrayAlias));
        System.out.println("array == array: " + (arrayA == arrayB));
        System.out.println("Arrays.equals: " + Arrays.equals(arrayA, arrayB));

        Pair p1 = new Pair(1, 2);
        Pair p2 = new Pair(1, 2);
        System.out.println("record ==: " + (p1 == p2));
        System.out.println("record.equals: " + p1.equals(p2));
    }
}
```

In the terminal (with JDK 17 or higher installed):

```bash
javac IdentityOperatorsDemo.java
java IdentityOperatorsDemo
```

Standard output:

```text
same object: true
different objects: true
missing == null: true
missing != first: true
literal == literal: true
literal == new: false
literal.equals(new): true
array == alias: true
array == array: false
Arrays.equals: true
record ==: false
record.equals: true
```

Comparing each group: `alias` and `arrayAlias` reuse an existing object; each `new` statement creates a new object; `String`'s `equals()` compares character sequences; `Arrays.equals` compares elements of two `int[]` arrays; and `record` automatically provides `equals()` based on its components. In the `s1`/`s2` case, two string literals with the same content are shared by Java via interning.

## 3. Comparing with `null` and Checking Before Accessing an Object

`null` indicates no object is referenced. Checking `a == null` or `a != null` is valid and **does not itself throw `NullPointerException`**; they only compare references. `null == null` is `true`; `null != null` is `false`.

```java
String name = null;

if (name == null) {
    System.out.println("No name yet");
}
if (name != null && !name.isBlank()) {
    System.out.println(name);
}
```

In the second condition, `&&` evaluates from left to right and short-circuits: if `name != null` is `false`, `name.isBlank()` is not called. Conversely, calling `name.equals("A")` when `name` is `null` throws `NullPointerException`.

When you want to compare **content** where one or both values may be `null`, use `Objects.equals(a, b)` (requires `import java.util.Objects;`). It returns `true` if both references point to the same object, both are `null`, or `a` is non-`null` and `a.equals(b)` is `true`.

```java
import java.util.Objects;

// Inside a method body:
String a = null;
String b = "Java";
boolean sameContent = Objects.equals(a, b); // false, null-safe
boolean bothAbsent = Objects.equals(null, null); // true
```

This is an **illustrative snippet placed inside a method**, not a standalone Java file because it contains statements outside a class declaration and an `import` statement.

## 4. Why Is `String` a Common Trap?

`String` is a reference type, even though literal syntax like `"Java"` looks value-like. Java uses **string interning** so literals with identical content share a single `String` object. Therefore:

```java
String a = "Java";
String b = "Java";
String c = new String("Java");

System.out.println(a == b);      // true: same interned literal object
System.out.println(a == c);      // false: new creates a different object
System.out.println(a.equals(c));  // true: same character content
```

The goal here is to prove that `==` depends on **identity**, not to check content. Do not write business logic that depends on whether any two strings share the same object. Use `a.equals(b)` when `a` is guaranteed non-`null`; use `Objects.equals(a, b)` when it can be `null`. `equalsIgnoreCase` is a separate option when case-insensitive string comparison is needed, with `String`'s own comparison rules.

`new String("Java")` is only meant for teaching here; in application code, there is usually no need to create a copy from a literal. If you explicitly call `intern()`, you obtain the canonical string representation for that content, but you should not use that operation as a general replacement for content comparison.

## 5. Wrappers and Autoboxing: Consider the Type of Each Operand

`Integer`, `Long`, `Boolean`, and other wrappers are classes, so if **both operands are wrapper references**, `==` checks identity. For `Integer`, Java guarantees that boxing/`Integer.valueOf` shares objects for values from **-128 to 127**. Caching behavior for larger values can differ across deployment environments and configurations, so you must not rely on `==` to compare numeric values of wrappers.

```java
Integer a = 127;
Integer b = 127;
Integer c = 1_000;
Integer d = 1_000;

System.out.println(a == b);      // true: guaranteed for value 127
System.out.println(c.equals(d));  // true: same value 1000
// Do not infer that c == d is always false across all environments.
```

If one operand is `Integer` and the other is `int`, numeric comparison can **unbox** the wrapper to `int`, then compare values:

```java
Integer boxed = 5;
int primitive = 5;

System.out.println(boxed == primitive); // true: unboxes then compares int
```

However, unboxing a `null` wrapper reference causes `NullPointerException`:

```java
Integer boxed = null;
int primitive = 5;
// boolean result = boxed == primitive; // Throws NullPointerException at runtime
```

Therefore, do not apply a mechanical rule like “whenever there is a wrapper, `==` always compares references”; **the actual types of both operands** determine whether conversion/unboxing occurs. When you want to compare two wrappers by value and allow `null`, `Objects.equals(a, b)` is usually clearer.

## 6. Arrays, `record`, and `enum`

**Arrays:** Two arrays with the same elements are still two different objects. `arr1 == arr2` only determines whether they are the exact same array. For one-dimensional arrays of primitives, use `Arrays.equals(arr1, arr2)` to compare elements; for multidimensional arrays, consider `Arrays.deepEquals`. For object arrays, `Arrays.equals` compares elements using `equals()` with `null` handling, and does not automatically deep-compare nested structures.

**`record`:** Two records with the same component values created by two `new` expressions are two separate objects. `==` returns `false`; the `equals()` generated by `record` checks the components according to the record contract. For example, `new Pair(1, 2).equals(new Pair(1, 2))` is `true` with the `Pair` declaration in section 2.

**`enum`:** Each enum constant is a unique instance of that enum type; hence `==` is well suited for comparing constants and there is no need to call `equals()`. The following example works inside a method body:

```java
enum Status { NEW, DONE }

// Inside a method:
Status current = Status.NEW;
boolean isNew = current == Status.NEW; // true
boolean isDone = current != Status.DONE; // true
```

The final snippet illustrates syntax and meaning; to run it separately, place the `enum` declaration in an allowed scope and the variable statements inside a method.

## 7. Reference Types Must Be Compatible When Writing Comparisons

Java checks the validity of `==`/`!=` at compile time. Two reference operands must satisfy the type rules for equality comparison; not just any two reference types can be placed next to `==`. For example:

```java
String text = "1";
Integer number = 1;
// boolean wrong = text == number; // Compile-time error: incomparable types
Object o = text;
boolean allowed = o == number;    // Type-valid, returns false here
```

The `o == number` case is valid because the expressions can be treated as compatible object references for comparison; it does not mean the two values are converted to strings or numbers to compare content. If you need to compare data of different types, define clear conversion rules before comparing **values**.

## 8. Choosing a Comparison Based on the Question to Answer

| Question | Appropriate Syntax | Meaning |
| --- | --- | --- |
| Do two references point to the same object? | `a == b` | Identity; both `null` also gives `true` |
| Do two references point to different objects? | `a != b` | Negated identity |
| Is the variable absent? | `a == null` | Safe `null` check |
| Does the variable have an object? | `a != null` | Check before accessing |
| Do two `String`s have the same content? | `a.equals(b)` | Use when `a` is non-`null` |
| Are two reference values equal by `equals`, including `null`? | `Objects.equals(a, b)` | Null-safe logical comparison |
| Do two arrays have equal corresponding elements? | `Arrays.equals(a, b)` | Content comparison for one-dimensional arrays |
| Are two enum constants the same? | `status == Status.NEW` | Natural identity comparison for `enum` |

Note: `equals()` is a **method** that a class can override to define equality by state; `==` is a **language operator** and cannot be overloaded. If a class does not override `Object.equals()`, the default method uses identity equivalent to `==`. When overriding `equals()`, you must follow the equality contract and override `hashCode()` consistently; that is a deeper topic of the object contract.

## 9. Common Errors and How to Avoid Them

1. **Using `==` to compare `String` input.** Strings that look identical can be different objects. Choose `equals()` or `Objects.equals()` if you need content comparison.
2. **Assuming two objects with the same fields have `==` equal to `true`.** Two `new` calls create two separate identities; content belongs to `equals()` as defined by the type.
3. **Using `==` on two `Integer`s just because a few tests pass.** Caching can hide bugs. Use value comparison.
4. **Forgetting `null` when calling `equals()` or unboxing.** Check `null`, use `Objects.equals`, or design data not to accept `null` where reasonable.
5. **Confusing `==` with `Arrays.equals`.** `==` asks whether it is the same array object, not whether the elements match.
6. **Inferring identity from `hashCode()`, `System.identityHashCode()`, or displayed addresses.** Hash values are not guaranteed unique per object. To know whether two references point to the same object, use `==`.
7. **Forgetting type compatibility rules.** A `==` comparison between two references of incomparable types may fail to compile, even if you think the result is obviously `false`.

## 10. Self-Check

Predict the following expressions before looking at the explanation:

```java
Object a = new Object();
Object b = a;
Object c = new Object();

String x = new String("ok");
String y = new String("ok");

Integer n = null;

boolean q1 = a == b;
boolean q2 = a != c;
boolean q3 = x == y;
boolean q4 = x.equals(y);
boolean q5 = n == null;
```

**Answer:** `q1 = true` because `a` and `b` are two aliases for one object; `q2 = true` because `c` is a new object; `q3 = false` because two `String` objects were created with `new`; `q4 = true` because the string content is identical; `q5 = true` because `n` is a `null` reference and there is no unboxing here.

**Remember:** for two reference operands, `==`/`!=` answers the question **“is it the same object?”**. When you need to compare data, you must rely on the type's `equals()` contract or an appropriate content-comparison API.