# How `x.equals(null)` Differs from Calling `equals()` on a `null` Reference

## 1. Two `null` Positions Have Different Meanings

In the expression `x.equals(y)`, `x` is the **receiver reference** of the method call, while `y` is the **argument**. Java must have an object as the receiver to execute an instance method. Therefore, distinguish between:

- **`x` is non-`null`, argument is `null`:** `x.equals(null)` successfully invokes the `equals(Object)` method on the object `x`. According to the `Object.equals` contract, the result must be `false` for every non-`null` `x`.
- **`x` is `null`:** `x.equals(null)` or `x.equals(y)` both throw a `NullPointerException` before any object's `equals` method body can run. The error comes from the **receiver `x`**, not because the argument is `null`.

Quick check: `x.equals(null)` is **not how to check whether `x` is `null`**. The way to check whether a reference is `null` is `x == null` (or `x != null`).

## 2. Relation to the `equals` Contract

`equals` is an instance method declared in `java.lang.Object`, with the signature `public boolean equals(Object obj)`. One requirement of the contract is: for any non-`null` reference `x`, `x.equals(null)` must return `false`.

This is a **rule for `equals` implementations**, not a guarantee that the JVM automatically turns the call into `false` in every situation. A class overriding `equals` against the contract—such as accessing `obj` without checking for `null`—can itself throw a `NullPointerException` even when the receiver `x` is non-`null`. In that case, the bug belongs to that `equals` implementation; it does not change the contract requirement.

Meanwhile, when the receiver `x == null`, Java has no object on which to invoke `equals`. No `equals` implementation ever receives the call; the result is a `NullPointerException`.

## 3. Standalone Runnable Java 17+ Example

Save the following code into the file `EqualsNullDemo.java`:

```java
import java.util.Objects;

public class EqualsNullDemo {
    public static void main(String[] args) {
        String present = "Java";
        String absent = null;

        System.out.println("present.equals(null): " + present.equals(null));
        System.out.println("absent == null: " + (absent == null));
        System.out.println("Objects.equals(absent, null): " + Objects.equals(absent, null));
        System.out.println("Objects.equals(present, absent): " + Objects.equals(present, absent));
        System.out.println("literal.equals(absent): " + "Java".equals(absent));

        try {
            absent.equals(null);
        } catch (NullPointerException ex) {
            System.out.println("absent.equals(null): NullPointerException");
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac EqualsNullDemo.java
java EqualsNullDemo
```

Expected output:

```text
present.equals(null): false
absent == null: true
Objects.equals(absent, null): true
Objects.equals(present, absent): false
literal.equals(absent): false
absent.equals(null): NullPointerException
```

Case-by-case explanation:

- `present.equals(null)` executes because `present` points to a `String`; `String.equals` returns `false` for a `null` argument.
- `absent == null` compares references only, without invoking a method, so it returns `true` and throws no error.
- `Objects.equals(absent, null)` returns `true` because **both arguments are `null`**; this differs from invoking a method on `absent`.
- `Objects.equals(present, absent)` returns `false` because one argument has a value and one argument is `null`.
- `"Java".equals(absent)` returns `false` because the receiver is a string literal guaranteed to be non-`null`.
- `absent.equals(null)` throws `NullPointerException` due to receiver `absent == null`; the program catches the error solely for illustration, not as a pattern for checking `null` in application code.

## 4. Comparing Common Expressions

Suppose variable `x` has type `String` and holds one of two values, `"Java"` or `null`:

| Expression | `x = "Java"` | `x = null` | Meaning |
| --- | --- | --- | --- |
| `x == null` | `false` | `true` | Checks whether the reference is `null` |
| `x.equals(null)` | `false` | `NullPointerException` | Calls `equals` on receiver `x` with argument `null` |
| `Objects.equals(x, null)` | `false` | `true` | Compares two values with `null` handling |
| `"Java".equals(x)` | `true` | `false` | Calls `equals` on a guaranteed non-`null` receiver |

`Objects.equals(a, b)` (in `java.util.Objects`) has logic equivalent to `a == b || (a != null && a.equals(b))`. Thanks to the `a != null` condition, the method safely handles cases where one or both arguments are `null`. When **both are non-`null`**, it still uses `a.equals(b)`, and thus still depends on the correctness of the `equals` implementation.

`x == null` specifically checks for a `null` reference; whereas for two non-`null` objects, `==` compares whether they are the exact same object, while `equals` typically compares equality according to the class's semantics.

## 5. Writing `equals` Properly When the Argument Is `null`

The example below is **part of a class** to illustrate how to override, not a standalone program:

```java
final class Book {
    private final String isbn;

    Book(String isbn) {
        this.isbn = java.util.Objects.requireNonNull(isbn);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Book book)) return false;
        return isbn.equals(book.isbn);
    }

    @Override
    public int hashCode() {
        return isbn.hashCode();
    }
}
```

The expression `other instanceof Book book` evaluates to `false` when `other == null`, so no method is called on the `null` argument. In that case, `bookInstance.equals(null)` returns `false`. Implementing `hashCode()` consistently with `equals()` is also an important part of the object contract, especially when used in `HashMap` or `HashSet`.

Conversely, code such as `other.getClass()` or `other.equals(this)` **before checking `other == null`** can throw `NullPointerException` in `bookInstance.equals(null)`, violating the contract.

## 6. Choosing Expressions in Practice

- To know whether a reference is `null`: use `x == null` or `x != null`.
- To compare two values that may both be `null`: use `Objects.equals(x, y)`; two `null` values are considered equal in this comparison.
- To call `equals` when `x` may be `null`: use `x != null && x.equals(y)` if you want `false` when `x == null`; note this differs from `Objects.equals(x, y)` when **both are `null`**.
- To compare against a fixed constant guaranteed to be non-`null`: you can use `"Java".equals(x)` to avoid a `null` receiver.
- When overriding `equals`, ensure every non-`null` object returns `false` for a `null` argument, while maintaining the rest of the `equals` and `hashCode` contract.

Key point: **`null` in the argument position** is the case `equals` must handle when the receiver exists; **`null` in the receiver position** causes the instance method call to fail with `NullPointerException`.