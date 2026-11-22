# String Concatenation with `+` and Converting Values to Text in Java 17+

## 1. Goal and basic rule

In Java, the `+` operator has **two different roles**:

- **Numeric addition** when the operands are numeric types and there is no string concatenation context.
- **String concatenation** when **at least one operand of the `+` operation being evaluated is a `String`**. The other operand is converted into text form and appended to the string.

~~~java
int quantity = 3;
int price = 40;

System.out.println(quantity + price);       // 43
System.out.println("quantity=" + quantity);  // quantity=3
System.out.println("total=" + quantity * price); // total=120
~~~

String concatenation returns a **`String`** without changing the data type of the original variables. For example, `quantity` remains an `int` after participating in the expression `"quantity=" + quantity`.

**Note:** the `+` rule applies once the expression has been parsed according to **operator precedence and parentheses**; having a `String` on the same line does not automatically turn every `+` into string concatenation.

## 2. When an expression mixes numbers and strings

`"sum=" + a + b` concatenates the two numeric values onto the label one by one, whereas `"sum=" + (a + b)` adds the two numbers first and then converts the sum to text. If there are multiple calculation steps, extracting `int sum = a + b;` makes both the math and the message easier to verify.

The rule of having a `String` applies to **each `+` after expression grouping**, not by turning every numeric addition on the same line into concatenation. The next lesson analyzes left-associativity, precedence, evaluation order with side effects, and the difference between `+=` and ordinary assignment in depth.

## 3. Converting primitives to text

When concatenated with a `String`, Java performs **string conversion** to represent the other value:

~~~java
int count = 7;
long size = 12L;
double ratio = 1.5;
boolean enabled = true;
char grade = 'A';

System.out.println("count=" + count);   // count=7
System.out.println("size=" + size);     // size=12
System.out.println("ratio=" + ratio);   // ratio=1.5
System.out.println("enabled=" + enabled); // enabled=true
System.out.println("grade=" + grade);   // grade=A
~~~

For primitive types, the corresponding `String.valueOf(...)` methods are an **explicit** and reusable way to convert:

~~~java
String countText = String.valueOf(7);
String flagText = String.valueOf(false);
String gradeText = String.valueOf('A');

System.out.println(countText); // 7
System.out.println(flagText);  // false
System.out.println(gradeText); // A
~~~

**Distinguish value from formatting:** `String.valueOf(1.5)` produces `"1.5"`, without automatically adding units, percentages, or rounding to two decimal places. Displaying values according to business rules is a separate concern.

For `char`, `+` **does not always concatenate characters**:

~~~java
System.out.println('A' + 'B');         // 131
System.out.println("chars=" + 'A' + 'B'); // chars=AB
~~~

The expression `'A' + 'B'` is **numeric addition** on two `char` values (widened to `int`): 65 + 66 = 131. On the next line, each `char` participates in a `+` that has a `String` operand, so they are concatenated as text.

## 4. `null`, objects, and the `toString()` method

When a reference value is concatenated into a string:

- If the reference is `null`, the resulting text is `"null"`.
- If it is not `null`, Java converts the value to string form according to string conversion semantics, typically relying on the object's `toString()`.

~~~java
String missing = null;
Object item = null;

System.out.println("missing=" + missing); // missing=null
System.out.println("item=" + item);       // item=null
~~~

For types you define yourself, **override `toString()`** if you want a meaningful description:

~~~java
final class Product {
    private final int id;

    Product(int id) {
        this.id = id;
    }

    @Override
    public String toString() {
        return "Product#" + id;
    }
}

// Inside a method:
Product product = new Product(7);
System.out.println("product=" + product); // product=Product#7
~~~

You should not rely on the default `Object.toString()` to produce user-facing text: the result usually contains the class name and a hexadecimal hash code, not stable business content.

**`null` does not become a string on its own.** `String missing = null;` is a null reference; only upon concatenation/conversion does the string `"null"` appear. Therefore, decide according to requirements whether to display `"null"`, an empty string, a dash, or a “no data” message.

A safe explicit conversion example:

~~~java
Object value = null;
System.out.println(String.valueOf(value)); // null
~~~

Here the `String.valueOf(Object)` overload is selected. Do not write an untyped `String.valueOf(null)` in example code: the `String.valueOf(char[])` overload is a subtle detail that can cause confusion and throw an exception when passed a null array.

## 5. Concatenating arrays: display elements, not references

A common mistake is concatenating an array directly into a `String` and expecting to see its elements:

~~~java
int[] numbers = {2, 4, 6};
System.out.println("numbers=" + numbers); // Not "numbers=[2, 4, 6]"
~~~

An array is an object; the default `toString()` representation of an array usually looks like an array type descriptor and a hash, such as `[I@...`. The hash part depends on the run; **do not** include it in fixed expected output.

To display the contents of a one-dimensional array, use `java.util.Arrays.toString`:

~~~java
int[] numbers = {2, 4, 6};
System.out.println("numbers=" + java.util.Arrays.toString(numbers));
// numbers=[2, 4, 6]
~~~

For multidimensional arrays, `Arrays.deepToString` may be needed when elements are nested object arrays.

**Special case `char[]`:**

~~~java
char[] letters = {'J', 'a', 'v', 'a'};
System.out.println(String.valueOf(letters)); // Java
System.out.println(java.util.Arrays.toString(letters)); // [J, a, v, a]
~~~

`String.valueOf(char[])` has a dedicated overload that creates text from **the contents of the elements**. Meanwhile, `"text=" + letters` is string concatenation on an array reference and **should not be used** if the goal is converting the entire array into the text `Java`.

Notably, `System.out.println(letters)` also has an overload taking `char[]` so it can print `Java`; this does **not** mean every concatenation with an array behaves the same way. Call the conversion API intentionally.

## 6. Concatenation does not modify old String objects

`String` is immutable. The expression `message + "!"` produces a new text value; `message += "!"` also **reassigns the `message` variable** to hold that result:

~~~java
String original = "Hi";
String updated = original + "!";
System.out.println(original); // Hi
System.out.println(updated);  // Hi!
~~~

With `final String name = "Lan";`, `name += "!";` is a compile error because it attempts to reassign a `final` variable. The compiler/JVM may optimize concatenation within an expression, so Java does not prescribe that each `+` must allocate a specific number of objects. The lesson on immutability distinguishes object content from reference reassignment in detail.


## 7. When building text across multiple steps

A short concatenation with `+` is easy to read. When content grows across loops or branches, you can use `StringBuilder` and finish with `toString()`:

~~~java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        builder.append("|");
    }
    builder.append("item").append(i);
}
System.out.println(builder.toString()); // item1|item2|item3
~~~

`append` mutates the builder without reassigning a `String` on every step. A builder is well-suited when building text across many steps, though it is not mandatory for every `+` expression. The editing API, cost comparison, and `String.join` are the dedicated focus of the `StringBuilder` lesson.


## 8. Rule-based formatting: String.format and Locale

`String.valueOf` and `+` handle converting/joining values, **not precision control over report formatting**. If you need a specific number of decimal places, alignment, or display rules, you can use `String.format`:

~~~java
String twoDecimals = String.format(
        java.util.Locale.ROOT, "%.2f", 12.5);
System.out.println(twoDecimals); // 12.50
~~~

Here `%.2f` requests displaying **two digits after the decimal point**. `Locale.ROOT` selects a stable formatting rule for the example; for a user interface, choose a `Locale` appropriate for the target audience rather than ignoring localization by default.

| Syntax | Example | Meaning |
|---|---|---|
| `"count=" + count` | `count=7` | Simple string concatenation |
| `String.valueOf(count)` | `7` | Convert value to string |
| `String.format(Locale.ROOT, "%.2f", 12.5)` | `12.50` | Specify number of displayed decimal digits |
| `Arrays.toString(numbers)` | `[2, 4, 6]` | Display elements of a 1D array |
| `builder.append(...).toString()` | Text built step by step | Multiple appends |

Display formatting **does not turn binary floating-point numbers into exact decimal numbers**. For example, `0.1 + 0.2` still has binary representation error even if you format the result as `0.30`. If exact decimal currency calculations are required, consider `BigDecimal` or an integer type representing the smallest unit, along with rounding rules.

## 9. Converting data to text vs parsing text

The two conversion directions are not the same:

~~~java
int number = 42;
String text = String.valueOf(number);   // int -> String
int restored = Integer.parseInt(text); // String -> int

System.out.println(text);              // 42
System.out.println(restored + 1);      // 43
~~~

`Integer.parseInt("42")` can convert valid data into a number, whereas `Integer.parseInt("forty-two")` throws `NumberFormatException`. When reading user input, separate validation/exception handling is required.

This matters when `+` expressions are misunderstood:

~~~java
String x = "10";
String y = "20";

System.out.println(x + y); // 1020
System.out.println(Integer.parseInt(x) + Integer.parseInt(y)); // 30
~~~

Concatenating two strings containing digits does not automatically turn them into numbers. Java has no rule to “auto-parse numbers” just because text looks like a number.

## 10. Complete, standalone Java 17 example

Save the content below into the file **`StringConcatDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class StringConcatDemo {
    private StringConcatDemo() {}

    static final class Product {
        private final int id;

        Product(int id) {
            this.id = id;
        }

        @Override
        public String toString() {
            return "Product#" + id;
        }
    }

    public static void main(String[] args) {
        int a = 3;
        int b = 40;

        System.out.println("numeric=" + (a + b));
        System.out.println("left associative=" + a + b);
        System.out.println("number first=" + (a + b) + " units");
        System.out.println("mixed=" + 1 + 2 + 3);
        System.out.println("grouped=" + (1 + 2 + 3));

        System.out.println("char math=" + ('A' + 'B'));
        System.out.println("char text=" + 'A' + 'B');
        System.out.println("primitive=" + a + "," + true + "," + 'X');

        Object missing = null;
        System.out.println("null=" + missing);
        System.out.println("valueOf(null)="
                + String.valueOf((Object) null));

        char[] letters = {'J', 'a', 'v', 'a'};
        int[] numbers = {2, 4, 6};
        System.out.println("char array=" + String.valueOf(letters));
        System.out.println("int array=" + Arrays.toString(numbers));

        Product product = new Product(7);
        System.out.println("object=" + product);

        String original = "A";
        String updated = original + "B";
        System.out.println("immutable=" + original + "/" + updated);

        StringBuilder builder = new StringBuilder();
        for (int i = 1; i <= 3; i++) {
            if (i > 1) {
                builder.append("|");
            }
            builder.append("item").append(i);
        }
        System.out.println("builder=" + builder);

        System.out.println("format="
                + String.format(Locale.ROOT, "%.2f", 12.5));
        System.out.println("floating sum=" + (0.1 + 0.2));
    }
}
~~~

Use **JDK 17 or later** and open a terminal in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 StringConcatDemo.java
java -cp . StringConcatDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\StringConcatDemo.java
java -cp . StringConcatDemo
~~~

**Expected output:**

~~~text
numeric=43
left associative=340
number first=43 units
mixed=123
grouped=6
char math=131
char text=AB
primitive=3,true,X
null=null
valueOf(null)=null
char array=Java
int array=[2, 4, 6]
object=Product#7
immutable=A/AB
builder=item1|item2|item3
format=12.50
floating sum=0.30000000000000004
~~~

The program uses only the JDK; the output above is the expected output you can compare against when running on Java 17+. It does not depend on random object hashes, keyboard input, or the system default locale.

## 11. Common mistakes and fixes

| Code / symptom | Problem | Correct approach |
|---|---|---|
| `"sum=" + a + b` produces `sum=340` | `+` concatenates left-to-right after `String` | `"sum=" + (a + b)` |
| `"value=" + 1 + 2` produces `value=12` | `1` and `2` were appended to the string | `"value=" + (1 + 2)` if addition is intended |
| `'A' + 'B'` produces 131 | Adds `char` code units, does not join text | `"" + 'A' + 'B'` or use String |
| `"items=" + intArray` | Array reference representation, not elements | `Arrays.toString(intArray)` |
| `"word=" + charArray` | Concatenating array reference is not the `valueOf(char[])` overload | `String.valueOf(charArray)` |
| `String.valueOf(null)` behaves unexpectedly | `char[]` overload can surprise callers | Specify `(Object) null` if `"null"` is wanted |
| `name += "!"` on a `final` variable | `+=` reassigns the variable | Create another result variable |
| Concatenating inside a loop thousands of times | Many intermediate results, hard-to-control cost | `StringBuilder` |
| `"10" + "20"` produces `1020` | Strings do not auto-parse into numbers | Parse input then add `int`s |
| Using `+` to force 2 decimal digits | String concatenation does not control formatting | `String.format(Locale, "%.2f", value)` |
| `String.valueOf(someObject)` lacks useful info | Object does not override `toString()` properly | Define meaningful text via method/API |
| `"value=" + nullable` displays `null` to users | String conversion differs from UI expectations | Handle null into a business placeholder |

**Do not mask data errors with text representation:** if an `int` has already overflowed before concatenation, `"total=" + overflowed` simply prints the **already wrong result**. Check operand ranges/types before computing and format last.

## 12. Exercises with answers

### Exercise A — precedence and associativity of `+`

~~~java
System.out.println("x=" + 10 + 20);
System.out.println("x=" + (10 + 20));
System.out.println(10 + 20 + " items");
~~~

**Answer:**

~~~text
x=1020
x=30
30 items
~~~

### Exercise B — `char` numeric addition or character concatenation?

~~~java
System.out.println('A' + 1);
System.out.println("A" + 1);
~~~

**Answer:**

~~~text
66
A1
~~~

`'A'` is a `char` with numeric value 65 so adding `1` gives 66; `"A"` is a `String` so it concatenates the number to `A1`.

### Exercise C — printing an integer list

~~~java
int[] scores = {7, 8};
System.out.println("scores=" + java.util.Arrays.toString(scores));
~~~

**Answer:** `scores=[7, 8]`. Use `Arrays.toString` rather than concatenating the array directly.

### Exercise D — `null` and display

~~~java
Object value = null;
System.out.println("value=" + value);
System.out.println(String.valueOf(value));
~~~

**Answer:**

~~~text
value=null
null
~~~

If the application does not want the word `null`, handle missing data before displaying instead of expecting `+` to choose a placeholder automatically.

### Exercise E — multiple concatenations

Create the string `A-B-C` from the values `"A"`, `"B"`, `"C"`.

**Simple answer:** `String joined = "A" + "-" + "B" + "-" + "C";`.

**Answer when looping is needed:**

~~~java
String[] parts = {"A", "B", "C"};
StringBuilder sb = new StringBuilder();
for (String part : parts) {
    if (sb.length() > 0) {
        sb.append("-");
    }
    sb.append(part);
}
System.out.println(sb); // A-B-C
~~~

## 13. Self-assessment checklist

- [ ] Know when `+` is numeric addition and when it is `String` concatenation.
- [ ] Understand `+` is left-associative and use parentheses to add before concatenating.
- [ ] Know how to convert `int`, `double`, `boolean`, `char` to text.
- [ ] Distinguish string concatenation from `String.valueOf(...)`.
- [ ] Know `null` becomes text `"null"` but is not itself a `String`.
- [ ] Know objects should have an appropriate `toString()` when a description is needed.
- [ ] Use `Arrays.toString` for arrays and `String.valueOf(char[])` for character arrays.
- [ ] Understand `String` is immutable and `+=` reassigns the variable.
- [ ] Choose `StringBuilder` for repeated concatenation without prematurely optimizing every `+`.
- [ ] Use `String.format` with an appropriate `Locale` when explicit formatting is required.
- [ ] Distinguish converting numbers to strings from parsing strings into numbers.
- [ ] Compile and run `StringConcatDemo.java` with `javac`/`java`, comparing all output.

**Conclusion:** The `+` operator is convenient for combining values into a `String`, but you must read the **evaluation order** properly so you do not confuse numeric addition with text concatenation. Use `String.valueOf`, `Arrays.toString`, `toString()`, `StringBuilder`, and `String.format` when they make the intent of conversion, building, or formatting clear and verifiable.
