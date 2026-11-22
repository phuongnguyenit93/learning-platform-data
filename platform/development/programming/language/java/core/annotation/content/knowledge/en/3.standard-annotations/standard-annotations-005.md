# @SafeVarargs: Usage Conditions and Responsibilities with Varargs in Java

## 1. What Problem Does `@SafeVarargs` Solve?

In Java, **varargs** allows a method to accept a variable number of arguments using the `T...` syntax:

```java
static void print(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

You can call `print("Java", "JVM")`; in terms of execution, a varargs parameter is represented as **an array** (`String[]`). When the varargs element is a **non-reifiable** type, such as `List<String>` or a type parameter `T`, the combination of generics and arrays can lead to **heap pollution**.

```java
static void inspect(List<String>... groups) {
    // In source syntax, groups has type List<String>[].
}
```

With `List<String>...`, the compiler cannot guarantee that the array created at every call site preserves the `String` type argument at runtime: due to **type erasure**, the JVM only knows that the array elements belong to the `List` class, not whether they are `List<String>` or `List<Integer>`. If code modifies the array through a broader alias, data of the wrong type can slip in.

`@SafeVarargs` is a standard annotation in `java.lang`, used for **the method or constructor author to promise that the body handles the varargs parameter safely**. When placed validly, this annotation helps prevent `unchecked` warnings arising from varargs having a non-reifiable element type, at both the declaration site and associated call sites.

The core point: **`@SafeVarargs` does not make Java perform stronger type checks at runtime**. It is an assurance made by the developer. If the assurance is false, the program can still encounter a `ClassCastException` or other erroneous behavior.

## 2. Understanding the Cause: Non-Reifiable Types, Arrays, and Heap Pollution

### 2.1. Reifiable and Non-Reifiable

A **reifiable** type is a type whose necessary type information can still be determined at runtime. Typical examples: `String`, `int`, `String[]`, and `List<?>` (unbounded wildcard). A **non-reifiable** type does not retain enough type parameter information after erasure, such as `List<String>`, `List<Integer>`, or a type parameter `T`.

With the declaration `List<String>... groups`:

1. The varargs form is handled as a `List<String>[]` parameter array in source code.
2. At runtime, the array holds `List` objects; there is no check on whether elements inside the list are actually `String`.
3. Java arrays are **covariant**: a `List[]` array can be viewed through a variable of type `Object[]`.
4. A write operation through `Object[]` can place a `List<Integer>` into what the source code trusts to be `List<String>`.

### 2.2. How Does Heap Pollution Occur?

Here is an **intentionally unsafe** example illustrating the mechanism; do not place `@SafeVarargs` on this method:

```java
import java.util.List;

class UnsafeExample {
    static void broken(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        String text = groups[0].get(0); // ClassCastException
        System.out.println(text);
    }
}
```

In the example above, `alias[0] = List.of(42)` passes the runtime array type check because the value is still a `List`. Then, `groups[0].get(0)` is accessed in code as a `String`, yet actually returns an `Integer`; the implicit cast leads to a `ClassCastException`.

**An explicit invalid cast is not required** to cause heap pollution; creating an alias of the varargs array is enough to open the path to an unsafe write. The compiler may warn at some steps, though not every error-causing path is detected.

## 3. Conditions for Placing `@SafeVarargs`

Java 17+ allows this annotation on **constructors with varargs** and on **methods with varargs** belonging to one of the three groups `static`, `final`, or `private`.

| Declaration Site | Valid? | Explanation |
|---|---|---|
| `static void m(T... xs)` | Yes | `static` method cannot be overridden |
| `final void m(T... xs)` | Yes | `final` instance method cannot be overridden |
| `private void m(T... xs)` | Yes, since Java 9 | `private` instance method cannot be overridden |
| Constructor `C(T... xs)` | Yes | Constructor cannot be overridden |
| Regular `void m(T... xs)`, overridable | No | Not `static`, `final`, or `private` |
| `void m(T[] xs)` without `...` | No | This is a regular method, not a varargs declaration |
| Method without a varargs parameter | No | `@SafeVarargs` is only for declarations with varargs |

The annotation has `@Target({ElementType.CONSTRUCTOR, ElementType.METHOD})`, so it is not attached directly to a class, field, or parameter. The **presence of varargs is mandatory**, and according to Java syntax, the varargs parameter must be at the end of the parameter list. `@SafeVarargs` cannot turn a `T[]` method into a varargs method.

Examples of declarations that are valid regarding **annotation placement** (the degree of safety still depends on the body):

```java
import java.util.List;

class ValidDeclarations {
    @SafeVarargs
    static <T> void staticMethod(T... values) {}

    @SafeVarargs
    final <T> void finalMethod(List<T>... values) {}

    @SafeVarargs
    private <T> void privateMethod(List<T>... values) {}

    @SafeVarargs
    ValidDeclarations(List<String>... values) {}
}
```

The following declarations are **intentionally invalid** and do not compile:

```java
class InvalidDeclarations {
    @SafeVarargs
    void overridable(String... values) {} // Invalid: overridable instance method

    @SafeVarargs
    static void fixedArity(String[] values) {} // Invalid: does not use ...

    @SafeVarargs
    static void noVarargs() {} // Invalid: no varargs parameter
}
```

Note: a method in a `final class` does not automatically satisfy the `final` condition of `@SafeVarargs` if the method itself is not declared `final`, `static`, or `private`. When declaring a public instance method, place `final` directly on the method if you want to use this annotation.

## 4. Responsibilities When Promising That Varargs Are Safe

Being syntactically allowed to place the annotation is **not enough** to assert that the method is truly safe. Before adding `@SafeVarargs`, the author needs to review **every path of the varargs array**:

1. **Do not write elements of the wrong type into the array**: avoid casting via `Object[]`, raw types, or unchecked casts and then writing values that do not match the expected type parameter.
2. **Do not expose the varargs array to code that could modify it**: avoid returning it directly, storing the array reference in accessible state, or passing the array to untrusted APIs/callbacks that might retain and mutate the array.
3. **Do not forward the array to another method without understanding that method's safety contract**: a secondary call may expose, retain, or mutate the very array that the current method is guaranteeing.
4. **Maintain correctness during refactoring**: if the code previously only read the array but later adds a cast, stores it, or forwards it, you must re-verify the `@SafeVarargs` promise.
5. **Inspect every path**, including exceptions, lambdas/closures that capture references, and helpers accepting `Object[]` or raw `List[]`; the fact that existing tests run does not prove type safety.

A common safe pattern is to **only read each element and copy its contents into a new structure**, without returning or sharing the original varargs array:

```java
@SafeVarargs
static <T> List<T> combine(List<? extends T>... parts) {
    List<T> output = new ArrayList<>();
    for (List<? extends T> part : parts) {
        output.addAll(part);
    }
    return output;
}
```

`output` is a new list, not the `parts` array. The method reads the input lists according to the generic contract and adds elements to an output list of the same type; it does not write to `parts[i]` and does not spread aliases of the `parts` array.

**A note on caller responsibility:** `@SafeVarargs` guarantees how the *implementation* handles the varargs array. It does not legitimize mistyped data that a caller intentionally creates using raw types, unchecked casts, or other unsafe actions. Also, do not use the annotation to hide warnings before investigating the source of the warnings.

## 5. Compilable and Runnable Java 17+ Example

Create the `Main.java` file with the following complete content:

```java
import java.util.ArrayList;
import java.util.List;

public class Main {
    @SafeVarargs
    static <T> List<T> combine(List<? extends T>... parts) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> part : parts) {
            result.addAll(part);
        }
        return result;
    }

    static class Bundle {
        private final List<String> entries;

        @SafeVarargs
        Bundle(List<String>... parts) {
            List<String> copy = new ArrayList<>();
            for (List<String> part : parts) {
                copy.addAll(part);
            }
            entries = List.copyOf(copy);
        }

        List<String> entries() {
            return entries;
        }

        @SafeVarargs
        private void consume(List<String>... parts) {
            for (List<String> part : parts) {
                System.out.println(part);
            }
        }
    }

    public static void main(String[] args) {
        List<String> merged = combine(
                List.of("Java", "Spring"),
                List.of("JVM"));
        System.out.println("Merged: " + merged);

        Bundle bundle = new Bundle(List.of("A"), List.of("B"));
        System.out.println("Bundle: " + bundle.entries());
    }
}
```

From the directory containing `Main.java`, run:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Output:

```text
Merged: [Java, Spring, JVM]
Bundle: [A, B]
```

In this example:

- `combine()` is a generic static varargs method and does not modify or expose the `parts` array.
- The constructor `Bundle(List<String>... parts)` is allowed to have `@SafeVarargs`; it copies the data into a new list, then uses `List.copyOf` to create an immutable list.
- `consume()` demonstrates `@SafeVarargs` on a private instance method (valid since Java 9); the code compiles, though this method is not called in `main`, so it produces no additional stdout.

The point to understand: the `parts` array can be used within a method without causing heap pollution; the danger appears when array operations or secretly passing an alias of it break expectations about data types.

## 6. Counterexample: Valid Annotation Placement with a False Promise

The following snippet **compiles under `@SafeVarargs` syntax**, but **you should never use the annotation like this in a real application**:

```java
import java.util.List;

class FalsePromise {
    @SafeVarargs // FALSE PROMISE: the body intentionally causes heap pollution
    static void corrupt(List<String>... values) {
        Object[] alias = values;
        alias[0] = List.of(123);
        String text = values[0].get(0); // ClassCastException
        System.out.println(text);
    }
}
```

`corrupt()` is `static` and has `...`, so the annotation placement is valid. However, `alias[0] = List.of(123)` violates the type safety promise. **The compiler does not prove the entire body safe simply by seeing `@SafeVarargs`**. Depending on the warning level, the compiler may also warn about suspicious operations in the body; therefore, `@SafeVarargs` does not mean silencing every warning either.

This example shows why the annotation has a narrow scope of applicability: with an overridden method, a subclass could replace the implementation with unsafe code while callers still receive an assurance from the initial declaration. The `static`, `final`, and `private` rules eliminate the ability to override in that way.

## 7. Which Warnings Are Handled? Distinguishing `@SafeVarargs` and `@SuppressWarnings`

When a method declares varargs with a non-reifiable element type, Java may issue warnings at:

- **Declaration site:** `Possible heap pollution from parameterized vararg type ...` (wording depends on the compiler).
- **Call site:** `Unchecked generic array creation for varargs parameter ...` (the compiler needs to create an array corresponding to the call with generic types).

If the method is truly safe, `@SafeVarargs` eliminates the `unchecked` warnings related to **the declaration** and **those calls**; its effect on call sites is an important difference.

Meanwhile, `@SuppressWarnings("unchecked")` only suppresses the corresponding warning type within **the scope where the annotation is placed**. Placing this annotation in a method is not a varargs promise that has the effect of suppressing warnings at all call sites like `@SafeVarargs`.

| Criterion | `@SafeVarargs` | `@SuppressWarnings("unchecked")` |
|---|---|---|
| Purpose | Promises that non-reifiable varargs are handled safely | Suppresses unchecked warnings within the annotated scope |
| Effect on call sites | Yes, for unchecked warnings caused by varargs array creation | Does not automatically apply to other call sites |
| Placement restrictions | Only eligible varargs constructors/methods | Many kinds of declarations, not restricted specifically to varargs |
| Runtime safety check | No | No |

Do not assume `@SafeVarargs` guarantees the compiler will never warn again. Other warnings such as `rawtypes`, `cast`, or `varargs` in the method body may still appear when `javac -Xlint` is enabled; read them to look for risky code instead of blindly suppressing more warnings.

A contrast example **used to illustrate warnings**, not a standalone `Main.java` program:

```java
static void withoutPromise(List<String>... lists) {
    // Assume the implementation has been reviewed as safe.
    for (List<String> list : lists) {
        System.out.println(list);
    }
}

@SafeVarargs
static void withPromise(List<String>... lists) {
    for (List<String> list : lists) {
        System.out.println(list);
    }
}
```

The first declaration may generate warnings about non-reifiable varargs at both the declaration and the call site. The latter declaration expresses a reviewed promise so that the compiler avoids the unchecked warnings for that case. Do not add the annotation merely to report zero warnings.

## 8. Common Misconceptions and Mistakes

### 8.1. Using `@SafeVarargs` for All Varargs

With `String... values`, `int... numbers`, the element types are inherently reifiable. There is no normal reason to use `@SafeVarargs`; the compiler may warn that the annotation is redundant. Use it when the varargs element can trigger an unchecked warning related to a non-reifiable type.

### 8.2. Thinking `final` on the Array Variable Is Enough

```java
static void demo(final List<String>... lists) {
    Object[] alias = lists;
    alias[0] = List.of(42);
}
```

`final` on the parameter only prevents **reassigning the reference variable** `lists`; it does not prevent modifying elements inside the array. It also does not substitute for the requirement: the annotation requires a **`final` method** (or `static`, `private`, constructor), not a `final` parameter.

### 8.3. Returning the Varargs Array Directly or Storing It in a Field

```java
@SafeVarargs
static <T> T[] leak(T... values) {
    return values; // Exposes the exact array that the caller/method is relying on.
}
```

Although the declaration may compile, returning the original generic array relinquishes control over aliases; the recipient can modify it in an unsafe way. Under strict review principles, this is **not a pattern on which you should confidently place `@SafeVarargs`**. If a result is needed, you should define an API that returns a list or an appropriately copied structure matching your mutability and nullability requirements.

### 8.4. Confusing "No Warnings Emitted" with "Type-Safe"

An improperly annotated method can still throw a `ClassCastException` at runtime. Warnings are the compiler's risk-detection tool; suppressing a warning does not remove the risk or alter runtime array checks.

### 8.5. Forgetting Validity When Changing Access Modifiers

Changing a method from `private` to package-private/public, or removing `final`, can invalidate the eligibility to place `@SafeVarargs`. After refactoring, you must review both overridability and the safety contract of the body.

## 9. Checklist Before Adding the Annotation

- Does the method/constructor **actually use `...`**, or does it only accept an array `[]`?
- If it is a method, is it declared **`static`, `final`, or `private`** (on Java 9+)?
- Is the varargs element type **non-reifiable**, and does the warning to be addressed actually originate from generic varargs?
- Across all execution paths, does the code **only read** or use the elements in accordance with the generic contract, avoiding writes into the array through unsafe aliases?
- Is there any path that **returns, stores, publishes, captures**, or passes the varargs array to a helper in a way that exposes the ability to mutate the array?
- Could future changes break the contract that the annotation promised to **all callers**?

If you cannot answer with confidence, fix the design first: for example, accept a `List<T>` instead of generic varargs, or ensure that data is copied and the array is never exposed. Do not attach `@SafeVarargs` as a mechanical warning-cleanup step.

## 10. Standard References

- [Java SE 17 API — `java.lang.SafeVarargs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): definition, compiler restrictions, meaning of warnings, and heap pollution examples.
- [Java Language Specification — §9.6.4.7 `@SafeVarargs`](https://docs.oracle.com/en/java/javase/specs/jls/se16/html/jls-9.html#jls-9.6.4.7): method author's promise and impact on call-site warnings.
- [Oracle Java Tutorials — Non-Reifiable Types](https://docs.oracle.com/en/java/javase/tutorial/java/generics/nonReifiableVarargsType.html): erasure mechanism, heap pollution, and generic varargs.

**Remember:** `@SafeVarargs` is an **implementation promise** for a varargs method/constructor, permitted by Java on declarations that cannot be overridden. The developer must prove that the code does not corrupt element type soundness through the generic array; the annotation only suppresses a corresponding category of warnings and provides no runtime shield.
