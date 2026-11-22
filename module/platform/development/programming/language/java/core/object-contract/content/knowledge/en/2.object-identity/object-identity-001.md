# A Reference Variable Is Different from the Referenced Object in Java

## Learning Objectives

After this lesson, you can distinguish a **reference variable** from an **object**, explain why two variables can point to the same object, predict the effects of assignment and state mutation, and understand `null`, `==`, and passing object parameters in Java. This is the foundation for avoiding bugs caused by accidentally sharing a mutable object.

## 1. Two Different Concepts

Consider the declaration:

```java
Box first = new Box(10);
```

- `Box` is a reference type. `first` is **a variable** that can hold a reference value pointing to a `Box` object or the value `null`.
- `new Box(10)` creates an **object** (an entity with identity and state). The object's `value` field is initially `10`.
- The `=` operator assigns the **reference value** of the new object to the variable `first`; the variable `first` is not that object itself.
- `first.value` accesses the object's field through the reference currently held in `first`.

You can picture it as:

```text
Reference variable                Object
first ─────────────────────────► Box { value = 10 }
```

This is a **logical relationship diagram**, not a guarantee about the physical location of the variable or the object in JVM memory. The compiler/JVM may optimize how storage is laid out; what must be firmly understood is that **a reference variable and an object are two conceptually different entities**.

A primitive variable such as `int count = 10;` directly stores the primitive value `10`. By contrast, with `Box first`, the value of `first` is a **reference to** the `Box` object, not the entire data of `Box`.

## 2. Multiple Variables Can Reference the Same Object

Consider:

```java
Box first = new Box(10);
Box alias = first;
Box sameValue = new Box(10);
```

Diagram:

```text
first ───────────┐
                 ├──────────────► Box A { value = 10 }
alias ───────────┘

sameValue ──────────────────────► Box B { value = 10 }
```

Here:

- `first` and `alias` are **two different variables**, but their reference values both point to **Box A**.
- The statement `Box alias = first;` **copies the reference value**; it does not create a copy of the object and does not execute `new`.
- `sameValue` references **Box B**: a different object, even though its initial state (the `value` field) matches Box A.
- Therefore, **the number of reference variables does not mean the same number of objects**.

Two objects can have the same state yet different identities. Conversely, two different variables can reference one single object.

## 3. Mutating State and Reassigning a Variable Are Two Different Operations

Run the following standalone example with **Java 17+**.

**File `ReferenceVsObjectDemo.java`:**

```java
public class ReferenceVsObjectDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;
        Box sameValue = new Box(10);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == sameValue: " + (first == sameValue));

        alias.value = 20;
        System.out.println("first.value: " + first.value);

        alias = new Box(30);
        System.out.println("first.value after reassignment: " + first.value);
        System.out.println("alias.value: " + alias.value);

        alias = null;
        System.out.println("first still references an object: " + (first != null));
        System.out.println("alias == null: " + (alias == null));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac ReferenceVsObjectDemo.java
java ReferenceVsObjectDemo
```

**Exact output:**

```text
first == alias: true
first == sameValue: false
first.value: 20
first.value after reassignment: 20
alias.value: 30
first still references an object: true
alias == null: true
```

Step-by-step analysis:

1. After `Box alias = first;`, both `first` and `alias` point to Box A. `first == alias` returns `true`.
2. The second `new Box(10)` creates Box B. `first == sameValue` returns `false`, even though both objects currently have `value = 10`.
3. `alias.value = 20;` **mutates the field of Box A**. Reading through `first.value` also sees `20` because `first` still points to the very same Box A.
4. `alias = new Box(30);` **reassigns the variable `alias`** so that it points to Box C. It does not change Box A and does not change what `first` references.
5. `alias = null;` only clears the reference held in **the variable `alias`**. `first` still points to Box A. Box C can become unreachable if no other strong reference holds it.

Short comparison:

| Statement | What is changed | What does not automatically change |
| --- | --- | --- |
| `Box b = a;` | Variable `b` receives a copy of the reference from `a` | No new object is created |
| `b.value = 20;` | The state of the object referenced by `b` | Does not reassign `b` or `a` |
| `b = new Box(30);` | The reference value stored in `b` | The old object and variable `a` |
| `b = a;` (again) | `b` references `a`'s object again | Does not copy the object's fields |
| `b = null;` | The value in `b` becomes `null` | Does not destroy the object immediately; other references still exist |

Easily confused terms: **“changing the object”** means modifying the state of the referenced entity; **“changing the reference variable”** means modifying the reference value stored in the variable.

## 4. What Does `==` Compare for References?

For two operands of compatible reference types for comparison, `==` returns `true` when they reference **the same object**, or when both are `null`. This is a **reference identity** comparison, not an automatic field-by-field comparison.

Example:

```java
Box a = new Box(1);
Box b = a;
Box c = new Box(1);

// a == b is true: the same object.
// a == c is false: two different objects.
// a == null is false.
```

The snippet above is illustrative, assuming the `Box` class is declared as in the complete example in section 3.

Distinguish from `equals(Object)`:

- `a == b` asks: **Is it the same object?**
- `a.equals(b)` asks: **According to the class's rules, are the two objects considered equal?**
- The default implementation of `Object.equals` compares identity just like `==`. A class can override `equals` to compare values/semantics; for example, `String` compares string content.
- You cannot infer `a == b` from `a.equals(b) == true`. Two independent objects can be equal in content yet still have different identities.
- If `a` can be `null`, calling `a.equals(b)` will cause a `NullPointerException`. When you need equality comparison with `null` handling, you can use `java.util.Objects.equals(a, b)`.

**Avoid using `==` to check `String` content**, even though two `String` variables may sometimes share the same reference due to interning. Sharing a reference in one situation does not turn `==` into a content comparison. Similarly, avoid inferring identity from the fact that Java may reuse certain wrapper objects.

`System.identityHashCode(obj)` can be useful for diagnostics, but it is **not a memory address** and is **not guaranteed to be unique** across all objects; do not use it in place of `==` to determine identity.

## 5. `null` Is a Reference Value, Not an Object

`Box box = null;` means `box` currently **does not reference any object**. There is no “null object” to access.

```java
Box box = null;

System.out.println(box == null);  // true
// System.out.println(box.value); // If uncommented: NullPointerException.
```

Check `box != null` before accessing if the variable might be `null`.

Assigning `box = null` does not immediately invoke the garbage collector and does not destroy the previous object. An object only **becomes eligible** for collection when it is no longer reachable through strong references from appropriate roots of the program. When collection happens, if at all, is decided by the JVM; do not design logic that depends on when an object is reclaimed.

## 6. Passing Object Parameters: Java Always Passes by Value

For parameters of reference types, Java **passes a copy of the reference value** to the parameter variable inside the method. Therefore:

- The method can use the copied reference to **mutate the state of the same object** that the caller also references.
- If the method **reassigns the parameter** to another object or `null`, the reference variable on the caller side **is not reassigned**.
- This is still **pass-by-value**, not pass-by-reference in the sense of the method receiving the caller's variable itself.

**File `PassingReferenceDemo.java`:**

```java
public class PassingReferenceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box parameter) {
        parameter.value = 7;
    }

    static void reassign(Box parameter) {
        parameter = new Box(99);
        System.out.println("inside reassign: " + parameter.value);
    }

    public static void main(String[] args) {
        Box original = new Box(1);

        mutate(original);
        System.out.println("after mutate: " + original.value);

        reassign(original);
        System.out.println("after reassign: " + original.value);
    }
}
```

```bash
javac PassingReferenceDemo.java
java PassingReferenceDemo
```

**Exact output:**

```text
after mutate: 7
inside reassign: 99
after reassign: 7
```

In `mutate(original)`, `parameter` and `original` both point to the initial object, so modifying `parameter.value` is visible through `original`. In `reassign(original)`, `parameter = new Box(99)` only changes the value of the **local parameter**, so `original` still points to the object with `value = 7`.

If you want the caller to receive a replacement object, the method can **return the new reference**, and the caller explicitly assigns the result: `original = createReplacement(original);`. You cannot achieve that merely by reassigning the parameter inside a `void` method.

## 7. `final` Fixes the Reference Variable, Not the Object

Declaration:

```java
final Box fixed = new Box(5);
fixed.value = 6; // Valid: mutates the object's state.
```

`final` prevents the variable `fixed` from being reassigned after initialization. It **does not automatically make the object immutable**. With the declaration above, `fixed = new Box(7);` will cause a **compile-time error** if added to the program.

To make an object immutable, you must design its state and API appropriately (for example, providing no state-mutating operations; protecting fields that hold mutable objects when necessary). That is a property of the **object/class design**, distinct from a **reference variable** being declared `final`.

## 8. Practical Connection: Aliasing and Side Effects

The phenomenon where multiple references point to the same object is called **aliasing**. With a mutable object, changes made through one reference path can cause other places to observe the new state.

For example, in a shopping cart management program, if two components receive the same cart object and one component modifies the product list, the other component also sees the change. This can be intentional by design (shared state) or a bug (unintended).

When reading an API that accepts/returns mutable objects, ask:

1. Does the API accept or return **the same object**, or create a **copy**?
2. Is the caller allowed to mutate that object?
3. Will mutating through one reference affect another component holding the same reference?

A regular assignment `copy = original;` **does not create an independent copy**. If separate data is needed, there must be a copying mechanism appropriate for the class, and you must understand shallow/deep copying when the object contains other mutable references. There is no assignment syntax that automatically deep-copies an arbitrary object.

## 9. Common Misconceptions

| Misconception | Correct Explanation |
| --- | --- |
| “Two variables are two objects.” | Two variables can reference the same object. |
| “`b = a` copies the object's fields.” | It copies the **reference value**; no new object is created. |
| “`b.value = 9` reassigns `b`.” | It modifies the state of the object currently referenced by `b`. |
| “`b = new Box(9)` makes `a` switch objects if `a == b` was true before.” | Only `b` changes its reference; `a` stays the same. |
| “`==` compares the content of objects.” | For references, `==` compares **identity**. |
| “Object parameters are passed by reference.” | Java copies the **reference value** into the parameter variable; it is still pass-by-value. |
| “`final` makes the object immutable.” | `final` on a variable only forbids reassigning that variable. |
| “`x = null` destroys the object immediately.” | It only changes the value of `x`; the object may still be referenced elsewhere. |

## 10. Self-Check

Assume `Box` has an `int value` field and a constructor taking an integer as in the previous examples.

**Scenario A**

```java
Box a = new Box(1);
Box b = a;
b.value = 3;
```

Question: What is `a.value`? What is `a == b`?

**Answer:** `a.value == 3` and `a == b` is `true`, because `a` and `b` reference the same object that was mutated.

**Scenario B**

```java
Box a = new Box(1);
Box b = a;
b = new Box(2);
```

Question: What are `a.value`, `b.value`, and `a == b`?

**Answer:** `1`, `2`, and `false`, respectively. Reassigning `b` does not modify the old object and does not reassign `a`.

**Scenario C**

```java
Box a = new Box(1);
Box b = a;
a = null;
```

Question: Is the original object necessarily unreachable?

**Answer:** No. `b` still points to that object. Setting `a` to `null` does not affect `b`.

**Scenario D**

A method receives `Box parameter` and executes `parameter = new Box(8);`. Does the caller's variable change its reference?

**Answer:** No. The parameter holds a copy of the caller's reference value; the assignment only updates the local parameter.

## Key Takeaway

**A reference variable holds a reference value; an object is the referenced entity.** Assignment between two reference-type variables copies the reference value, which can create aliases. Modifying **object state** through one alias is visible through other aliases; **reassigning a variable** only changes where that variable points. Distinguishing these two operations helps you understand `==`, `null`, `final`, parameter passing, lifecycle management, and side effects when sharing mutable objects.
