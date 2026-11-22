# Identifier Rules and Case Sensitivity in Java

## 1. What is an identifier?

An **identifier** is a name chosen by a programmer for an element in Java code: a variable, method, class, interface, package, parameter, or constant. For example:

~~~java
int itemCount = 3;                 // itemCount: variable name
String customerName = "Lan";      // customerName: variable name
~~~

In the declaration `public class IdentifierDemo`, `IdentifierDemo` is a class name. In `System.out.println(itemCount)`, `System`, `out`, `println`, and `itemCount` are names used to reference different components; the dot `.` is a member access symbol, **not part of a single identifier**.

**Two questions to separate:**

1. Is the name **valid according to Java syntax**?
2. Is the name **meaningful and aligned with conventions**?

A name can be valid yet hard to read, such as `a1` or `$x`. Conversely, `item-count` looks like a name written in prose, but **is not a valid single Java identifier**.

## 2. First character and subsequent character rules

A regular identifier must follow Java's character rules:

- The first character must be one that Java allows to **start an identifier** (typically a Unicode letter, `_`, or `$`).
- Subsequent characters may include valid starting characters, digits, and certain other Unicode characters allowed by Java.
- It cannot contain spaces, `-`, `.`, `@`, or operator symbols as part of the same identifier.
- An identifier cannot be a **keyword prohibited in that position**, the literals `true`, `false`, `null`, or the special identifier **standalone `_`** (reserved since Java 9).
- Java is **case-sensitive**: `total`, `Total`, and `TOTAL` are three different names.

| Proposed name | Valid as a regular variable name? | Explanation |
|---|---|---|
| `count` | Yes | Starts with a letter |
| `count2` | Yes | Digit in a subsequent position |
| `_count` | Yes | Leading underscore is allowed |
| `$count` | Yes | `$` is allowed by Java, though it should not be overused |
| `sốLượng` | Yes | Java supports many Unicode letters |
| `2count` | No | Starts with a digit |
| `item-count` | No | `-` is interpreted as a subtraction operator, not part of the identifier |
| `item count` | No | Contains whitespace |
| `item.count` | Not *one* identifier | Consists of two identifiers and `.` |
| `_ ` | No | Standalone `_` is a reserved symbol |
| `class` | No | Java keyword |
| `true`, `null` | No | Reserved literals, cannot be used as variable names |

**Details:** The actual Unicode rules are described by checks equivalent to `Character.isJavaIdentifierStart(int)` and `Character.isJavaIdentifierPart(int)`, but **character checks alone are not enough**: keywords and certain reserved names must still be excluded, and syntactic context must be considered. Do not use a simple ASCII regex to conclude that all Unicode identifiers are invalid.

## 3. How is Java case-sensitive?

Java is a **case-sensitive** language. Changing a single character from uppercase to lowercase can change it into **another identifier** or cause an error because the name cannot be found.

~~~java
int price = 100;
int Price = 200;

System.out.println(price); // 100
System.out.println(Price); // 200
~~~

Both declarations can coexist in the same scope because their names differ, but naming things this way easily causes confusion and should generally be avoided.

Similarly:

- `String` is a standard library class name; `string` is not automatically understood as `String`.
- `println` and `printLn` are not the same method name.
- `getName` and `getname` are two different names.
- `Customer` and `customer` are two different names (if declared).
- `TRUE` can be a regular variable name, whereas `true` is a boolean literal.

Example of a mismatched name:

~~~java
int total = 10;
// System.out.println(Total); // Compile error: variable Total does not exist
~~~

`javac` usually reports `cannot find symbol` for `Total`. The fix is to use **`total`** matching the declaration, rather than arbitrarily renaming across multiple places.

**Do not confuse `case-sensitive` with how operating systems store files.** Windows and Linux file systems may handle letter casing in filenames differently, yet **variable/class/method names in Java remain case-sensitive**.

## 4. Keywords, literals, and restricted names

A name can use completely valid characters and still be rejected because it collides with a **reserved word** or appears in a **restricted syntactic context**:

- `class`, `int`, `return`, `const`, `goto` are reserved keywords and cannot be used as variable names.
- `true`, `false`, `null` are **literals**, not keywords, yet cannot serve as variable names either.
- `var`, `record`, `yield`, `sealed`, `permits` are subject to specific contextual rules; for example, `int var = 7;` is valid, while `var` is restricted in a type name position.
- Standalone `_` has been reserved since Java 9, but `_count` and `__` are valid names on Java 17.

~~~java
int _count = 5;
int __ = 6;
int var = 7;
// int _ = 8;      // Invalid: _ stands alone.
// int class = 9;  // Invalid: class is a keyword.
~~~

The key point when **checking identifier names** is to separate character validation from checking reserved words and usage position. The lessons on contextual keywords and `_`/`const`/`goto` analyze these cases in greater depth.

## 5. Runnable Java 17 example: similar yet distinct names

Create a file named **`IdentifierDemo.java`** with exact contents:

~~~java
public final class IdentifierDemo {
    private IdentifierDemo() {}

    public static void main(String[] args) {
        int count = 2;
        int Count = 5;
        int _count = 7;
        int $count = 9;
        int sốLượng = 3;

        System.out.println("count = " + count);
        System.out.println("Count = " + Count);
        System.out.println("_count = " + _count);
        System.out.println("$count = " + $count);
        System.out.println("soLuong = " + sốLượng);
    }
}
~~~

Open a terminal in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 IdentifierDemo.java
java -cp . IdentifierDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\IdentifierDemo.java
java -cp . IdentifierDemo
~~~

Expected output:

~~~text
count = 2
Count = 5
_count = 7
$count = 9
soLuong = 3
~~~

From this program:

- `count` and `Count` are not the same variable.
- `_count` and `$count` are syntactically valid, though not conventional choices for naming application variables.
- `sốLượng` is valid because Java supports Unicode; the `-encoding UTF-8` flag helps the compiler read UTF-8-saved source code accurately.
- The class name `IdentifierDemo` must match the source file `IdentifierDemo.java` because it is a top-level `public class`. When running in class mode, use the class name `IdentifierDemo` without adding `.java`.

**Practical recommendation:** although Java allows many Unicode characters, in projects involving multiple tools and countries, development teams typically agree on naming styles that are easy to type, easy to search, and compatible with project conventions. This is a **convention**, not a Java syntax limitation.

## 6. Intentionally creating errors and reading compiler messages

Create a test file named **`BadIdentifiers.java`**:

~~~java
public class BadIdentifiers {
    public static void main(String[] args) {
        int 2items = 4;
        int total-price = 100;
        int class = 3;
        int _ = 5;
    }
}
~~~

Command:

~~~bash
javac --release 17 BadIdentifiers.java
~~~

**Result:** `javac` **fails to produce a new class file** for this invalid code; it will report syntax/keyword errors. The exact wording and reported line numbers may vary by JDK.

How to fix those invalid declarations:

~~~java
int items2 = 4;
int totalPrice = 100;
int classNumber = 3;
int _value = 5;
~~~

These fixed names are all valid. However, **simply renaming is not enough for the program to be business-logic correct**: you still need to choose names that carry the actual meaning of each value.

### Errors from wrong letter casing

~~~java
int maxScore = 100;
// System.out.println(maxscore); // Invalid: maxscore is not declared
System.out.println(maxScore);     // Valid
~~~

If you encounter `cannot find symbol: variable maxscore`, compare the characters against the declaration line; do not assume Java converted the name to lowercase.

## 7. Distinguishing mandatory rules from naming conventions

Java permits many valid names, yet clean code should follow consistent conventions. Common conventions in Java:

| Element | Common convention | Example |
|---|---|---|
| Variables and parameters | `lowerCamelCase` | `itemCount`, `unitPrice` |
| Methods | `lowerCamelCase` | `calculateTotal()`, `isAvailable()` |
| Classes and interfaces | `UpperCamelCase` | `OrderService`, `Runnable` |
| `static final` constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_PORT` |
| Packages | Lowercase, parts separated by `.` | `com.example.catalog` |
| Enum types | `UpperCamelCase` | `OrderStatus` |
| Enum constants | Typically `UPPER_SNAKE_CASE` | `PENDING`, `IN_PROGRESS` |

**Valid syntax does not mean following the table is mandatory.** For example, a variable named `MAX_RETRIES` is valid even without `static final`; however, using uppercase like a constant will mislead readers. Conversely, the compiler does not require every class name to begin with an uppercase letter.

Avoid overly short or obscured names (`x1`, `aaa`, `temp2`) when there is no clear reason. For very short loops, `i` or `j` remains acceptable when the context is obvious.

### Distinguishing a qualified name from a single identifier

~~~java
package com.example.catalog;

public class OrderService {
    public int calculateTotal(int unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

`com.example.catalog` is a **qualified package name**, consisting of the identifiers `com`, `example`, and `catalog` separated by `.`. The dot does not turn the entire sequence into a single identifier.

`OrderService`, `calculateTotal`, `unitPrice`, and `quantity` are all individual identifiers, each playing a role in the declaration.

## 8. Unicode and special characters: use correctly but cautiously

Java supports many non-ASCII Unicode characters in variable/class names:

~~~java
int sốLượng = 2;
int giá = 15;
int thànhTiền = sốLượng * giá;
System.out.println(thànhTiền); // 30
~~~

If the source is saved as UTF-8, compile with `javac -encoding UTF-8` (combined with `--release 17` when needed). Whether the console displays Unicode properly also depends on the terminal and system configuration; **readability of names in source code** and **output rendering capability** are two different things.

Do not assume **every character that looks like a letter** is accepted by Java or normalized identically. For instance, an accented letter may have different Unicode representations; inconsistent usage easily makes code harder to search and review. Within a team, using a consistent character set/convention can be more important than utilizing every character Java permits.

### Why does Java allow `$`?

The `$` character is valid in names, yet **Java conventions discourage using it in programmer-created identifiers**; some code generation tools or nested class names may also use `$`. Learners should prefer `itemCount` over `$itemCount` to keep code readable and avoid ambiguity with tool-generated names.

## 9. Same name, different scope: do not confuse with case sensitivity

Within **one block**, you cannot declare two local variables with the same name:

~~~java
int count = 1;
// int count = 2; // Invalid: local variable count is already defined
int Count = 2;    // Valid syntactically, but easily confusing
~~~

Beyond the name, Java also considers **scope** and **context**. A method parameter, field, and local variable may have different naming/collision rules.

Example of field name shadowing:

~~~java
class Box {
    private int size = 10;

    void show(int size) {
        System.out.println(size);      // Parameter size
        System.out.println(this.size); // Object's field
    }
}
~~~

Calling `new Box().show(4)` prints `4` then `10`. Both are named `size`, but `this.size` explicitly refers to the field. This case is **name shadowing**, not a mechanism where Java ignores letter casing.

## 10. Common practical errors

| Symptom | Issue to check | Fix |
|---|---|---|
| `cannot find symbol` on a variable name | Wrong letter case, typo, out of scope | Check the declared name and scope |
| `';' expected` or syntax error near a name | Name contains `-`, spaces, or unusual symbols | Use a valid identifier, e.g. `totalPrice` |
| `<identifier> expected` | Name in wrong position, starts with a digit or keyword | Choose a Java-valid name |
| `as of release 9, '_' is a keyword` (or equivalent message) | Used standalone `_` | Rename to `_value` or a meaningful name |
| `variable x is already defined` | Declared two variables with the same name where forbidden | Use a meaningful distinct name or remove the duplicate declaration |
| `class IdentifierDemo is public, should be declared ...` | Source filename and top-level public class do not match | Name the file `IdentifierDemo.java` |
| Source with Unicode names compiles incorrectly | Encoding mismatch | Save as UTF-8 and use `-encoding UTF-8` |
| Class/method with different casing is missing | Java distinguishes `Demo` from `demo`, `run` from `Run` | Fix the exact casing at declaration/call site |

When fixing an error, **do not mass-replace names just to silence the compiler**. Renaming a class, method, or public API may also require updating referencing sites and corresponding filenames.

## 11. Exercises with answers

### Exercise A — which names are valid?

Classify the following when used as **variable names** in Java 17: `age`, `Age`, `age2`, `2age`, `_age`, `_`, `$age`, `class`, `true`, `total-price`.

**Answer:** valid: `age`, `Age`, `age2`, `_age`, `$age`. Invalid: `2age` (starts with digit), `_` (reserved), `class` (keyword), `true` (literal), `total-price` (contains minus sign).

### Exercise B — predict the output

~~~java
int score = 10;
int Score = 20;
System.out.println(score + Score);
~~~

**Answer:** `30`. `score` and `Score` are two separate variables, not the same variable written in different casing.

### Exercise C — fix the case-sensitivity error

~~~java
String customerName = "Lan";
// System.out.println(customername);
~~~

**Answer:** use `customerName` in the `println` call, or rename consistently everywhere. Java does not treat `customername` as identical to `customerName`.

### Exercise D — meaningful naming

Rename `a`, `b`, and `c` in an order total calculation so a reader can infer their meaning.

**Suggested answer:** `unitPrice`, `quantity`, `subtotal`. Meaningful names reflect the data and formula, even though the compiler itself does not enforce them.

### Exercise E — Unicode and naming rules

Is `int sốLượng = 2;` invalid solely because the name contains Vietnamese diacritics?

**Answer:** No; it is a valid identifier. Source code should be saved as UTF-8, with consistent encoding and team conventions. There is no need to switch to ASCII solely for syntactic validity.

## 12. Completion checklist

- [ ] Explain what an identifier is and how it differs from separators/operators.
- [ ] Know that digits may appear later, but not as the normal starting character of a name.
- [ ] Distinguish `count`, `Count`, and `COUNT` in Java.
- [ ] Recognize that keywords, literals `true`/`false`/`null`, and standalone `_` are invalid as variable names.
- [ ] Know that `_` and `$` can be **part** of a name, while keeping conventions in mind.
- [ ] Know that Java supports Unicode identifiers, not limited to `A-Z`/`a-z`.
- [ ] Apply `lowerCamelCase`, `UpperCamelCase`, and `UPPER_SNAKE_CASE` to the right roles by convention.
- [ ] Compile and run `IdentifierDemo.java` on JDK 17+; output matches the expected table.
- [ ] Independently locate `cannot find symbol` errors caused by wrong casing and invalid naming errors.
- [ ] Distinguish **wrong name**, **duplicate name in scope**, and **field name shadowing**.

**Conclusion:** A Java identifier must use valid characters, not collide with words reserved in that syntactic context, and be written with **exact letter casing**. Language rules determine which names can compile; naming conventions make programs clear, consistent, and maintainable.