# The `null` Literal and Where `null` Cannot Be Assigned — Java 17+

`null` is a Java **literal** representing that a reference **does not point to any object or array**. It is not the string `"null"`, not the number `0`, and not the default value of every data type.

Main rule: **`null` can be assigned to variables of reference types, but cannot be assigned directly to variables of primitive types.** Being syntactically valid to assign does not guarantee safety when using the value afterward.

## 1. Which types can be assigned `null`?

| Target type | Example | Valid in Java 17? | Why |
| --- | --- | --- | --- |
| Class | `String text = null;` | Yes | `String` is a reference type |
| Wrapper class | `Integer number = null;` | Yes | `Integer` is an object, different from `int` |
| Array | `int[] numbers = null;` | Yes | An array itself is a reference type |
| Interface | `Runnable task = null;` | Yes | Variable holds a reference to an object implementing the interface |
| Enum or record | `Status s = null;` when `Status` is an enum | Yes | Both are reference types |
| Parameterized reference type | `java.util.List<String> list = null;` | Yes | Variable holds a list reference |
| Primitive | `int n = null;` | **No** | `int` requires an integer value |
| Primitive | `boolean ok = null;` | **No** | `boolean` requires `true` or `false` |
| Primitive | `char c = null;` | **No** | `char` requires a character code value |
| Local variable using `var` | `var x = null;` | **No** | Compiler cannot infer a type from a standalone `null` initializer |

The remaining primitive types `byte`, `short`, `long`, `float`, and `double` also **do not accept `null` directly**. `void` is not a variable type that stores values; a `void` method cannot use `return null;`.

**Language detail:** the `null` literal is the only value of the *null type*. The null type has no name for you to declare a variable directly. Java permits converting this value to a compatible reference type, but not to a primitive type.

## 2. Runnable Java 17 example

Create a UTF-8 file named **`NullLiteralDemo.java`**:

~~~java
import java.util.Objects;

public class NullLiteralDemo {
    static String displayName(String name) {
        return name == null ? "(khong co ten)" : name;
    }

    static int lengthOrZero(String text) {
        return text == null ? 0 : text.length();
    }

    public static void main(String[] args) {
        String name = null;
        Integer boxedCount = null;
        int[] numbers = null;
        String[] names = {"Mai", null};

        System.out.println("nameIsNull=" + (name == null));
        System.out.println("boxedIsNull=" + (boxedCount == null));
        System.out.println("arrayIsNull=" + (numbers == null));
        System.out.println("elementIsNull=" + (names[1] == null));

        System.out.println("display=" + displayName(name));
        System.out.println("lengthOrZero=" + lengthOrZero(name));
        System.out.println("stringNull=" + "null".equals(name));
        System.out.println("objectsEquals=" + Objects.equals(name, null));

        try {
            System.out.println("length=" + name.length());
        } catch (NullPointerException ex) {
            System.out.println("dereference=NullPointerException");
        }

        try {
            int count = boxedCount; // Automatic unboxing Integer -> int.
            System.out.println("count=" + count);
        } catch (NullPointerException ex) {
            System.out.println("unboxing=NullPointerException");
        }
    }
}
~~~

Open **Windows PowerShell** or **Linux/Bash** in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NullLiteralDemo.java
java NullLiteralDemo
~~~

**Expected output:**

~~~text
nameIsNull=true
boxedIsNull=true
arrayIsNull=true
elementIsNull=true
display=(khong co ten)
lengthOrZero=0
stringNull=false
objectsEquals=true
dereference=NullPointerException
unboxing=NullPointerException
~~~

Explanation:

- `String`, `Integer`, and `int[]` are all reference types, so variables can hold `null`.
- The `names` array is **not null**, yet the **element** `names[1]` can be null because the element type is `String`.
- `name.length()` compiles validly, yet calling a method on a null reference throws `NullPointerException` at runtime.
- `int count = boxedCount;` also compiles validly: the compiler inserts an *unboxing* operation from `Integer` to `int`. However, because the wrapper is null, the unboxing operation throws `NullPointerException`.
- `Objects.equals(name, null)` safely compares when one or both arguments are null; `"null".equals(name)` compares a string literal with a null reference and therefore returns `false`.

In the example, `try/catch` is used solely to **demonstrate the two runtime errors** without halting the program immediately. In real applications, validate and handle input data before accessing or unboxing.

## 3. **Compile-time** errors vs. **runtime** errors

The lines below are **intentionally invalid**, for learning only; do not add them to a running program:

~~~java
// int quantity = null;       // Invalid: null does not convert to int.
// boolean enabled = null;    // Invalid: null does not convert to boolean.
// char letter = null;        // Invalid: null does not convert to char.
// var unknown = null;        // Invalid: cannot infer type.
// int[] values = {null};     // Invalid: int element does not accept null.
~~~

Conversely, the following lines are **type-valid**:

~~~java
Integer quantity = null;
Boolean enabled = null;
Character letter = null;
String inferred = null;
Integer[] values = {null};
~~~

Distinguish two kinds of arrays:

~~~java
int[] a = null;           // Valid: array reference holds null.
int[] b = new int[2];     // Primitive elements have value 0.
String[] c = new String[2]; // Reference elements default to null.
~~~

Here `a.length` will throw `NullPointerException` because **`a` itself is null**. `b[0]` equals `0`; `c[0]` equals `null`. Using the same term "default value" does not mean all types receive the same value.

## 4. `null` is not the same as an empty or default value

| Value | Meaning |
| --- | --- |
| `null` | No object/array reference |
| `""` | An existing `String` with length 0 |
| `"null"` | A `String` consisting of four letters `n-u-l-l` |
| `0` | Integer value 0 |
| `false` | Boolean value false |
| `new int[0]` | An array object of length 0, **not null** |

Use `text == null` when you need to know whether a reference exists. Use `text.isEmpty()` when you already know `text` is not null and want to check for an empty string. You can combine them:

~~~java
if (text == null || text.isEmpty()) {
    System.out.println("Thieu noi dung");
}
~~~

The `||` operator is **short-circuiting**: if `text == null` is true, Java does not call `text.isEmpty()` on the right-hand side, thereby avoiding a `NullPointerException`.

When comparing `String` content, use `Objects.equals(a, b)` to handle null cases, or `"OK".equals(value)` when the literal is guaranteed non-null. The `==` operator between two reference-type variables compares **whether they hold the same reference**, not their content.

## 5. Using `null` in return values, parameters, and generics

~~~java
static String findName(boolean found) {
    return found ? "Mai" : null; // Valid: returns String.
}

static int findCount() {
    return 0; // Cannot return null for int.
}

static void show(String value) {
    System.out.println(value == null ? "(empty)" : value);
}
~~~

- You can call `show(null)` because the parameter has the reference type `String`.
- `return null;` is valid when the return type is a reference type, such as `String`, but invalid for `int` or a `void` method.
- With generics, `java.util.List<String> items = null;` is valid; however, calling `items.size()` will throw `NullPointerException`.
- Also distinguish a **null list reference** from an **existing list containing null elements**. For example, `new java.util.ArrayList<String>()` is an existing list; some APIs accept null elements, whereas `List.of(null)` will throw `NullPointerException`.

If you prefer not to return null to signal "not found", you can consider `Optional<String>` with `Optional.empty()` or `Optional.ofNullable(value)`. `Optional` is an API choice and does not itself alter the rules of the `null` literal.

## 6. Self-check exercises

**Exercise 1:** Between `String s = null;` and `String s = "";`, on which can `s.length()` be called safely right away?

*Answer:* The empty string `""`: result 0. With `null`, the call throws `NullPointerException`.

**Exercise 2:** Why does `Integer number = null;` compile, while `int number = null;` does not?

*Answer:* `Integer` is a reference type; `int` is primitive. If you unbox a null `Integer`, the error occurs **at runtime**.

**Exercise 3:** Is `String[] names = {null};` valid? What about `char[] chars = {null};`?

*Answer:* The first is valid because the element type is `String`; the second is not because `char` elements are primitive.

**Exercise 4:** Fix `var data = null;` while keeping a placeholder for a `String` value later.

*Answer:* Use `String data = null;` to state the type explicitly; `var` cannot infer a type from `null`.

**Exercise 5:** Predict `"null".equals((String) null)` and `Objects.equals(null, null)`.

*Answer:* `false` and `true`, respectively.

## Memory checklist

- [ ] `null` is a literal, **not** a number, false, or the string `"null"`.
- [ ] `null` can be assigned to reference types, **not** directly to primitives.
- [ ] `var x = null` cannot infer a type in Java 17.
- [ ] An array itself can be null; elements of a primitive array cannot.
- [ ] A valid `null` assignment does not mean method calls or unboxing are safe.
- [ ] Distinguish compile-time errors from `NullPointerException` at runtime.
- [ ] Use `== null` checks, short-circuit `||`, and `Objects.equals` where appropriate.

**Conclusion:** `null` represents the **absence of a reference**. Java allows it where a reference type is expected, but rejects it where a primitive value is required. Once code compiles, check for null before dereferencing or unboxing to prevent runtime errors.
