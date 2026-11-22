# The `public boolean equals(Object)` Signature and Verification with `@Override`

When defining for yourself “whether two objects are equal”, you must **override** the `equals(Object)` method inherited from `java.lang.Object`. The method for this takes the form:

~~~java
@Override
public boolean equals(Object obj) {
    // Implement the equality comparison
}
~~~

The core point of this lesson: the parameter type must be **`Object`**, not the name of the class you are writing. The `@Override` annotation helps the compiler catch cases where you think you have overridden the method, when in fact you declared a different method.

## 1. Understanding Each Component Correctly

- **`equals`** is the method name. Every Java class inherits `equals(Object)` from `Object`, unless an overridden version already exists.
- **`(Object obj)`** is the parameter list: **exactly one parameter** of type `java.lang.Object`. The variable name (`obj`, `other`, `o`, …) can be changed without affecting the override. The `Object` parameter type allows calling via a reference variable of any object type.
- **`boolean`** is the required return type: `true` when the two objects are considered equal, `false` when they are not. Do not use `Boolean`, `int`, or `void`.
- **`public`** is the required access level when overriding a `public` method of `Object`; you cannot narrow it to `protected`, package-private (no modifier), or `private`.
- The overridden method is an **instance method**, not `static`.
- **`@Override`** informs the compiler of your intent to override. If the declaration does not match an overridable method, the program will not compile.

Terminology distinction: in Java, a *method signature* in the language sense consists of **the method name and parameter types**; the return type and access level are not part of the signature under this definition. However, to **validly override** `Object.equals(Object)`, the declaration must still satisfy `public` and `boolean`.

By default, `Object.equals(Object)` only returns `true` if two references point to the same object. Overriding allows defining **value-based equality** appropriate for the data type, such as two books having the same ISBN.

## 2. Why Can't `equals(Book)` Replace `equals(Object)`?

Consider the declaration below (**snippet illustrating an error; not a standalone program**):

~~~java
final class WrongBook {
    private final String isbn;

    WrongBook(String isbn) {
        this.isbn = isbn;
    }

    // Wrong if the goal is to override Object.equals(Object).
    public boolean equals(WrongBook other) {
        return other != null && isbn.equals(other.isbn);
    }
}
~~~

`equals(WrongBook)` is an **overload** because it takes `WrongBook`, which differs from the `Object` parameter type. It **does not override** `Object.equals(Object)`. Therefore:

- `wrongA.equals(wrongB)` can call `equals(WrongBook)` when the expression `wrongB` has static type `WrongBook`.
- `wrongA.equals((Object) wrongB)` instead calls `equals(Object)` inherited from `Object`, so two different instances typically yield `false` even if they have the same ISBN.
- APIs such as `HashSet`, `HashMap`, or `Objects.equals(a, b)` rely on the `equals(Object)` object comparison; a separate overload does not replace that contract.

If you add `@Override` right above `equals(WrongBook)`:

~~~java
@Override
public boolean equals(WrongBook other) {
    return other != null && isbn.equals(other.isbn);
}
~~~

`javac` will **report a compilation error** because this method does not override any method of a superclass or interface in the example. This is the practical benefit of `@Override`: the bug is exposed right at compile time, before running the application.

## 3. Runnable Java 17 Example

Create the file **`EqualsSignatureDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualsSignatureDemo {

    private static final class Book {
        private final String isbn;

        Book(String isbn) {
            this.isbn = Objects.requireNonNull(isbn);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Book other)) {
                return false;
            }
            return isbn.equals(other.isbn);
        }

        @Override
        public int hashCode() {
            return isbn.hashCode();
        }
    }

    // Intentionally declare a wrong overload to observe the difference.
    private static final class WrongBook {
        private final String isbn;

        WrongBook(String isbn) {
            this.isbn = Objects.requireNonNull(isbn);
        }

        public boolean equals(WrongBook other) {
            return other != null && isbn.equals(other.isbn);
        }
    }

    public static void main(String[] args) {
        Book first = new Book("ISBN-1");
        Book sameIsbn = new Book("ISBN-1");
        Book different = new Book("ISBN-2");
        Object asObject = sameIsbn;

        System.out.println(first.equals(sameIsbn));
        System.out.println(first.equals(asObject));
        System.out.println(first.equals(null));
        System.out.println(first.equals("ISBN-1"));
        System.out.println(first.equals(different));

        Set<Book> books = new HashSet<>();
        books.add(first);
        books.add(sameIsbn);
        books.add(different);
        System.out.println(books.size());

        WrongBook wrongA = new WrongBook("ISBN-1");
        WrongBook wrongB = new WrongBook("ISBN-1");
        Object wrongAsObject = wrongB;
        System.out.println(wrongA.equals(wrongB));
        System.out.println(wrongA.equals(wrongAsObject));
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac EqualsSignatureDemo.java
java EqualsSignatureDemo
~~~

**Expected output:**

~~~text
true
true
false
false
false
2
true
false
~~~

Step-by-step explanation:

1. Two `Book` objects that are different instances but have the same ISBN return `true` because `Book.equals(Object)` compares the `isbn` value.
2. The variable `asObject` has static type `Object` but still invokes the **overridden version at runtime** of `Book`; the result is still `true`.
3. `null` and the string `"ISBN-1"` are not `Book` instances, so they yield `false`.
4. Two `Book` instances with different ISBNs yield `false`.
5. `HashSet` keeps only two distinct books by ISBN because `equals(Object)` and `hashCode()` are consistent.
6. With `WrongBook`, the first call selects the `equals(WrongBook)` overload and prints `true`; the second call receives an argument of type `Object`, selects the inherited `Object.equals(Object)`, and thus prints `false`.

### Why Does the Correct Method Check in That Order?

- `this == obj` quickly handles the same-reference case and ensures an object is equal to itself.
- `obj instanceof Book other` also checks the argument type; `null` does not satisfy `instanceof`, so it safely returns `false`. This pattern matching syntax is supported on Java 17.
- `isbn.equals(other.isbn)` compares the essential data once both are confirmed to be `Book` instances. The constructor uses `Objects.requireNonNull` to guarantee `isbn` is non-null.
- The `Book` class is `final` so the example does not have to handle equality rules with subclasses. Deciding whether to use `instanceof` or `getClass()` in an inheritance hierarchy requires separate consideration to preserve the symmetry of `equals`.

We also write `hashCode()` because two objects considered equal by `equals` must have the same hash code. `@Override` is also useful for this method; however, the focus here remains on verifying the correct **`equals(Object)` signature**.

## 4. Declaration Errors That `@Override` Will Catch

The snippets below are all **intentionally erroneous code fragments**, assuming they reside in a normal class directly inheriting from `Object`. Each snippet is examined independently, not combined into a runnable program:

~~~java
@Override
public boolean equals(Book other) { return true; } // Wrong parameter: overload.
~~~

~~~java
@Override
protected boolean equals(Object other) { return true; } // Narrowing public.
~~~

~~~java
@Override
public Boolean equals(Object other) { return true; } // Wrong return type.
~~~

~~~java
@Override
public static boolean equals(Object other) { return true; } // Cannot override with static.
~~~

~~~java
@Override
public boolean equals(Object other, int mode) { return true; } // Extra parameter.
~~~

For each case, `javac` refuses to compile; the exact error message may vary depending on the error type and compiler version. In particular, the `equals(Book)` case without `@Override` **can still compile**, but fails to achieve the goal of overriding. Therefore, always write the annotation right when declaring the method.

It is also important to distinguish: `@Override` **does not automatically check the logic** inside the method body. A method with the right signature and annotation can still be semantically wrong (for example, comparing the wrong values or violating symmetry or transitivity). Such bugs require testing and adherence to the `equals` contract.

## 5. How to Do a Quick Self-Check in Your Project

When implementing equality for a data class:

1. Type `@Override public boolean equals(Object obj)` accurately; the name `obj` is optional.
2. Let the IDE or `javac` confirm the method actually overrides; do not remove `@Override` just to “make the error go away”.
3. Test the cases of same reference, same value, different value, `null`, and wrong type.
4. In particular, call through an **`Object`-typed variable** to catch overload bugs like the example above.
5. When overriding `equals`, also implement a consistent `hashCode`, then verify the behavior of hash-based collections.

**Key takeaway:** Only `public boolean equals(Object obj)` properly overrides `Object`'s method. `equals(T obj)` (where `T` is your class) is only an overload. `@Override` turns this mistake into a clear compile-time error and should always be present when overriding is intended.