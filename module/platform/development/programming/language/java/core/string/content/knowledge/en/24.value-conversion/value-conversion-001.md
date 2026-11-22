# String.valueOf with Primitives and Objects in Java

## 1. Lesson Objectives

`String.valueOf(...)` is a group of **static methods** in `java.lang.String` used to create a string representation from a value. It is especially useful when converting `boolean`, `char`, integer types, floating-point types, or an object to a `String` for display, message concatenation, or passing into an API that accepts strings.

After this lesson, you will be able to:
- Distinguish the `valueOf` overloads for **primitives**, `Object`, and `char[]`.
- Understand when a value is represented by a predefined string and when `toString()` is called.
- Explain why `String.valueOf((Object) null)` returns `"null"`, whereas `String.valueOf((char[]) null)` throws an error.
- Know how to represent arrays and numeric data when `valueOf` does not meet the desired formatting.
- Choose correctly among `String.valueOf`, `Objects.toString`, `Integer.toString`, and `String.format` depending on the purpose.

## 2. Overloads of String.valueOf

Common declarations in Java 17:

```java
public static String valueOf(boolean b);
public static String valueOf(char c);
public static String valueOf(int i);
public static String valueOf(long l);
public static String valueOf(float f);
public static String valueOf(double d);

public static String valueOf(Object obj);
public static String valueOf(char[] data);
public static String valueOf(char[] data, int offset, int count);
```

Java selects an overload based on the **compile-time type of the expression** along with method invocation resolution rules. Then each overload produces the corresponding string content.

| Input value | Typical overload | Example | Result |
| --- | --- | --- | --- |
| `boolean` | `valueOf(boolean)` | `String.valueOf(true)` | `"true"` |
| `char` | `valueOf(char)` | `String.valueOf('J')` | `"J"` |
| `byte`, `short` | `valueOf(int)` via widening | `String.valueOf((byte) 7)` | `"7"` |
| `int` | `valueOf(int)` | `String.valueOf(-42)` | `"-42"` |
| `long` | `valueOf(long)` | `String.valueOf(5000000000L)` | `"5000000000"` |
| `float` | `valueOf(float)` | `String.valueOf(1.25f)` | `"1.25"` |
| `double` | `valueOf(double)` | `String.valueOf(2.5d)` | `"2.5"` |
| `Object` | `valueOf(Object)` | `String.valueOf((Object) null)` | `"null"` |
| `char[]` | `valueOf(char[])` | `String.valueOf(new char[]{'A','B'})` | `"AB"` |

**There is no dedicated overload for `byte` or `short`**; the corresponding primitive argument can be widened to `int`. Wrapper types such as `Integer`, `Boolean`, or `Double` are **objects** when you pass a variable of wrapper type; Java can select the `Object` overload via reference conversion, and the output representation typically remains the same as the string form of the value.

A special case is the **character array `char[]`**. It is not a single primitive `char` and is handled by a dedicated overload.

## 3. Converting Primitive Types

### Boolean: only "true" and "false"

```java
String yes = String.valueOf(true);    // "true"
String no = String.valueOf(false);    // "false"
```

These are two lowercase strings defined by Java rules, independent of locale. `String.valueOf(boolean)` does not translate to "Yes/No" or "True/False"; localization must be done separately.

### Char: creating a String from a single character

```java
char initial = 'K';
String text = String.valueOf(initial); // "K"
```

A `char` in Java is a **UTF-16 code unit**, which does not always represent a complete Unicode character. Characters outside the Basic Multilingual Plane (for example, many emojis) require a surrogate pair; if you have a Unicode code point, you can use `Character.toChars(codePoint)` and then create a string from the `char[]` array.

```java
int codePoint = 0x1F600;
String emoji = String.valueOf(Character.toChars(codePoint));
// A String containing emoji U+1F600
```

### Integers: signed decimal form when needed

```java
String quantity = String.valueOf(125);       // "125"
String negative = String.valueOf(-12L);      // "-12"
String small = String.valueOf((short) 8);    // "8"
```

The default format of `valueOf` for integers is **decimal**, without automatically adding thousands separators or leading zeros. If you need another radix, use the appropriate API:

```java
String hex = Integer.toHexString(255); // "ff"
String binary = Integer.toBinaryString(5); // "101"
String base16 = Integer.toString(255, 16); // "ff"
```

### Floating-point numbers: default representation, not a fixed display pattern

```java
String a = String.valueOf(1.25f); // "1.25"
String b = String.valueOf(2.0d);  // "2.0"
String c = String.valueOf(Double.NaN); // "NaN"
String d = String.valueOf(Double.POSITIVE_INFINITY); // "Infinity"
```

The overloads for `float` and `double` follow the corresponding string representation rules of `Float` and `Double`. Depending on the value, the result may use scientific notation, and the number of digits after the decimal point is not a fixed count.

Do not use `String.valueOf(12.5)` when the requirement is always exactly **two decimal places** or locale-specific grouping separators. In that case, use `String.format(Locale.US, "%.2f", 12.5)` to get `"12.50"` or `NumberFormat` for a locale-aware UI.

`String.valueOf` only determines the **representation**; it does not change the precision of a `float`/`double` value and does not resolve floating-point arithmetic inaccuracies.

## 4. `String.valueOf(Object)`: Object Representation and Null Handling

When the argument has **static type `Object`**, Java selects `valueOf(Object)`. This overload returns the literal string `"null"` if the reference is `null`; if non-null, it calls `toString()` according to the actual runtime class of the object:

```java
Object count = Integer.valueOf(42);
Object missing = null;
System.out.println(String.valueOf(count));   // 42
System.out.println(String.valueOf(missing)); // null
```

Because the result depends on `toString()`, an object may print a custom description or a default form like `Type@hexHash`. This is a textual representation, not serialization or casting to `String`. Calling `obj.toString()` directly on `null` throws a `NullPointerException`.

**Overload trap:** `String.valueOf(null)` with an **uncast null literal** selects the `char[]` overload, which is more specific than `Object`, and thus throws a `NullPointerException`. Write `String.valueOf((Object) null)` if you want the string `"null"`. A dedicated lesson in this chapter on `null` explains the static-type overload resolution mechanism along with casting cases.

## 5. `char[]` Overloads: Extracting Character Content

Unlike `Object`, `char[]` is treated by `String.valueOf` as **text data**:

```java
char[] chars = {'J', 'a', 'v', 'a'};
String entire = String.valueOf(chars);       // "Java"
String middle = String.valueOf(chars, 1, 2); // "av"
```

With the three-parameter overload, `offset` is the starting index, and `count` is the **number of `char` elements** taken from the array. A `null` array causes a `NullPointerException`; an invalid range causes an `IndexOutOfBoundsException`. The created string does not change if the source array is modified afterward. The `char[]` data consists of UTF-16 code units, so slicing by Unicode code points requires determining boundaries properly.

`String.valueOf((Object) chars)` switches to the `Object` overload and prints the array object representation such as `[C@...`, **not** `"Java"`. When focusing on copying and extracting array slices, `String.copyValueOf(char[])` and `new String(char[])` also share the corresponding contract for creating string content.

## 6. Other Arrays Do Not Automatically Convert to Element Lists

`valueOf(char[])` is a special overload. For arrays such as `int[]`, `double[]`, or `String[]`, a normal `valueOf` call takes `Object`, so the default result describes the **array object**, not a list of its elements:

```java
int[] ids = {1, 2, 3};
System.out.println(String.valueOf(ids).startsWith("[I@")); // true
System.out.println(java.util.Arrays.toString(ids));        // [1, 2, 3]

int[][] grid = {{1, 2}, {3, 4}};
System.out.println(java.util.Arrays.deepToString(grid));   // [[1, 2], [3, 4]]
```

Use `Arrays.toString` to inspect elements of a one-dimensional array and `Arrays.deepToString` for nested object arrays. That is an **output formatting** choice, distinct from `valueOf`, which simply relies on the `toString()` of the passed-in object.

## 7. Complete Java 17+ Program

Save the following code to `ValueOfDemo.java` in UTF-8:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;

public class ValueOfDemo {
    private record Product(String code, int quantity) {
        @Override
        public String toString() {
            return code + " x " + quantity;
        }
    }

    public static void main(String[] args) {
        System.out.println("boolean: " + String.valueOf(true));
        System.out.println("char: " + String.valueOf('J'));
        System.out.println("int: " + String.valueOf(-42));
        System.out.println("long: " + String.valueOf(5000000000L));
        System.out.println("float: " + String.valueOf(1.25f));
        System.out.println("double: " + String.valueOf(2.5));

        Product p = new Product("P01", 3);
        System.out.println("object: " + String.valueOf(p));

        Object missing = null;
        System.out.println("null object: " + String.valueOf(missing));
        System.out.println("fallback: " +
                Objects.toString(missing, "(empty)"));

        char[] data = {'J', 'a', 'v', 'a'};
        System.out.println("char array: " + String.valueOf(data));
        System.out.println("char slice: " +
                String.valueOf(data, 1, 2));

        String copy = String.valueOf(data);
        data[0] = 'Z';
        System.out.println("copy preserved: " + copy);

        int[] ids = {1, 2, 3};
        System.out.println("array items: " + Arrays.toString(ids));

        System.out.println("formatted: " +
                String.format(Locale.US, "%.2f", 2.5));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 ValueOfDemo.java
java ValueOfDemo
```

Exact stdout:

```text
boolean: true
char: J
int: -42
long: 5000000000
float: 1.25
double: 2.5
object: P01 x 3
null object: null
fallback: (empty)
char array: Java
char slice: av
copy preserved: Java
array items: [1, 2, 3]
formatted: 2.50
```

These lines illustrate the same method family across multiple input types. For example, the `Product` object uses its own `toString()` method; `char[]` creates a string from character content; `int[]` prints its elements properly with `Arrays.toString`; `String.format` produces two decimal places, unlike `String.valueOf(2.5)`.

## 8. Choosing Between `valueOf`, `toString`, and `Objects.toString`

| Call | Non-null object | Null object |
| --- | --- | --- |
| `String.valueOf(obj)` when `obj` has static type `Object` | Uses `obj.toString()` | String `"null"` |
| `obj.toString()` | Calls `toString()` directly | `NullPointerException` |
| `Objects.toString(obj)` | Uses `toString()` | String `"null"` |
| `Objects.toString(obj, fallback)` | Uses `toString()` | Uses `fallback` (may be null) |

If you want an intentional fallback message, `Objects.toString(value, "(empty)")` is clearer than the string `"null"`. For a variable that is already a `String`, using the variable directly is usually simplest; `String.toString()` returns that same string object. A separate lesson on `toString()` explains overriding, arrays, and per-class representations in detail.

`String.valueOf(obj)` **is not equivalent to casting `(String) obj`**: a cast requires the actual runtime object to be a compatible `String`, whereas `valueOf` creates a textual representation of any object.

## 9. valueOf in String Concatenation and StringBuilder

When concatenating strings with the `+` operator, Java uses string conversion rules corresponding to the argument's type. In many situations, you **do not need to write `String.valueOf(...)` explicitly**:

```java
int count = 3;
String a = "Quantity: " + count;
String b = "Quantity: " + String.valueOf(count);
// Both a and b are "Quantity: 3"
```

The compiler/runtime may optimize string concatenation; do not assume the bytecode of every Java version calls the exact same `String.valueOf` overload. What matters at the language level is the **result rule**, independent of a specific bytecode implementation.

For multiple concatenation steps in a loop, `StringBuilder` is useful:

```java
StringBuilder builder = new StringBuilder();
builder.append("ID=").append(12).append(", active=").append(true);
String result = builder.toString();
// "ID=12, active=true"
```

`StringBuilder.append(...)` also has overloads for primitives and `Object`. There is no need to convert each value with `String.valueOf` before calling `append`, unless you want to control a specific representation.

## 10. When Do You Need a Specialized Formatter or Converter?

### Numeric values with presentation requirements

```java
import java.util.Locale;

double amount = 1234.5;

String raw = String.valueOf(amount); // "1234.5"
String fixed = String.format(Locale.US, "%,.2f", amount);
// "1,234.50"
```

`String.valueOf` does not automatically group thousands, choose a currency unit, or follow a locale. For monetary values, you typically need `BigDecimal` for accurate calculations and `NumberFormat` or an explicit format policy for display.

### Converting a String back into a primitive

`String.valueOf(42)` converts **int → String**, while `Integer.parseInt("42")` converts **String → int**; these are two opposite directions.

```java
String text = String.valueOf(42); // "42"
int back = Integer.parseInt(text); // 42
```

If the data is invalid, `Integer.parseInt(...)` may throw `NumberFormatException`. `valueOf` does not validate whether an arbitrary string is a valid number, because it converts from a typed value to text.

### Converting a String into a domain object

For objects with a custom `toString()`, there is no automatic inverse operation to turn `String.valueOf(object)` back into an object. To convert back, you need an appropriate parser/factory or a serialization format with well-defined rules.

## 11. Common Mistakes

**1. Calling `String.valueOf(null)` and expecting `"null"`.** Because a `char[]` overload exists, a null literal expression selects that overload and throws a `NullPointerException`. Write `String.valueOf((Object) null)` or use an `Object` variable if the goal is the text `"null"`.

**2. Assuming all arrays print their elements.** `char[]` has its own overload, whereas `int[]`/`String[]` use `Object.toString()`. Choose `Arrays.toString` or `Arrays.deepToString` when you need to see the elements.

**3. Calling `toString()` directly when data may be null.** `String.valueOf((Object) ref)` is null-safe in the sense that it returns `"null"`; `ref.toString()` can throw a `NullPointerException`.

**4. Assuming `String.valueOf(double)` always has two decimal places.** Floating-point numbers are represented according to default rules. For fixed precision, grouping separators, or locales, a formatter is required.

**5. Using `String.valueOf(obj)` as a type cast.** The method returns a `String` representing the object; it does not return the original object cast to `String`.

**6. Letting an object's `toString()` expose unintended data.** `valueOf(Object)` delegates to `toString()` and may print a class name + hash code, or sensitive content defined by the class. Design `toString()` intentionally and be careful when logging.

**7. Mixing technical representations with user-facing representations.** `true/false`, decimal points, and `valueOf`'s object output do not automatically adapt to languages or UI conventions.

**8. Confusing the `count` parameter with the end index when slicing `char[]`.** `String.valueOf(chars, 1, 2)` takes **2 characters**, starting from index `1`.

## 12. Practice Exercises

### Exercise 1. Predict the result

```java
String a = String.valueOf(false);
String b = String.valueOf((byte) -5);
String c = String.valueOf(10.0d);
String d = String.valueOf('Z');
```

Answer: `a = "false"`, `b = "-5"`, `c = "10.0"`, `d = "Z"`.

### Exercise 2. Distinguish null handling

Consider the following calls (do not execute simultaneously if a line may throw an exception):

```java
Object x = null;
char[] y = null;

String a = String.valueOf(x);
String b = String.valueOf((Object) null);
// String c = String.valueOf(y);
// String d = String.valueOf(null);
```

Answer: `a` and `b` are the string `"null"`. The calls on the last two lines, if uncommented, will throw a `NullPointerException` because the `char[]` overload is selected.

### Exercise 3. Slice a character array

Given `char[] chars = {'s','t','r','i','n','g'};`. Create the string `"rin"` without using a loop.

```java
char[] chars = {'s', 't', 'r', 'i', 'n', 'g'};
String answer = String.valueOf(chars, 2, 3);
// "rin"
```

### Exercise 4. Print the contents of an integer array

Why does `String.valueOf(new int[]{10, 20})` not return `"[10, 20]"`?

Answer: there is no `int[]` overload; the array is passed as `Object`, and its default representation does not list elements. Use:

```java
String result = java.util.Arrays.toString(new int[]{10, 20});
// "[10, 20]"
```

### Exercise 5. Format a floating-point number

When required to display `2.5` as `"2.50"` on every machine, which approach is appropriate?

```java
String result = String.format(
        java.util.Locale.US, "%.2f", 2.5);
// "2.50"
```

Reason: `valueOf(double)` has no parameter for the number of decimal places, whereas a formatter does.

## 13. Key Takeaways

- **`String.valueOf(...)` is a static method** that returns a string representing the input value.
- Overloads exist for **boolean, char, int, long, float, double, Object, char[]**, and a `char[]` slice.
- **Primitive `byte`/`short`** go through `valueOf(int)` via widening conversion.
- **`String.valueOf(Object)`**: if non-null, it uses `toString()`; if null, it returns the literal string `"null"`.
- **An uncast `null` literal** selects `char[]` and causes a `NullPointerException`. When you need the `Object` overload, specify the type explicitly.
- **`char[]`** is converted from its characters; **other arrays** do not automatically print their elements. Use `Arrays.toString`/`deepToString` when appropriate.
- **`valueOf` is not a locale formatter, data serializer, or string parser.** Choose `String.format`, `NumberFormat`, `Integer.parseInt`, or an appropriate serializer when those requirements apply.

References: [Java SE 17 — String.valueOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#valueOf(java.lang.Object)), [Java SE 17 — Object.toString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#toString()), [Java SE 17 — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html), [Java SE 17 — Objects.toString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#toString(java.lang.Object,java.lang.String)).
