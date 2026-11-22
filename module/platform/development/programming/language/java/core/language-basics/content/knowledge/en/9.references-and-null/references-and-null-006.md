# `==` on References Checks for the Same Object — Java 17+

## 1. Goal: "Same Object" Differs from "Same Content"

In Java, the `==` operator has different meanings depending on the **operand types**:

- For **primitive values**, `==` compares values according to the rules of the corresponding primitive type.
- For **two comparable references**, `==` returns `true` when **both references point to the exact same object**, or **both are `null`**. It does not automatically compare each field, each character, or each array element.

~~~java
int x = 10;
int y = 10;
System.out.println(x == y); // true: same int value

String first = new String("Java");
String second = new String("Java");
System.out.println(first == second);      // false: two different objects
System.out.println(first.equals(second)); // true: same string content
~~~

**Focus:** `==` on references answers the question **"are these two variables currently pointing to the exact same object?"**, rather than **"do these two objects have identical data?"**.

To keep the examples easy to verify, this lesson uses Java 17+, a custom class, strings, arrays, and `record` to distinguish **object identity** and **value equality**.

## 2. Each Reference Variable Holds a Reference Value

Consider the class:

~~~java
static final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}
~~~

Inside a method:

~~~java
Box a = new Box(10);
Box alias = a;
Box b = new Box(10);

System.out.println(a == alias); // true
System.out.println(a == b);     // false
~~~

Why?

1. The first `new Box(10)` creates an instance and assigns that instance's reference to `a`.
2. `alias = a` **copies the reference**, without calling `new`, so `alias` and `a` point to the original instance.
3. The second `new Box(10)` creates **another instance**, so `b` does not share identity with `a`, even though both `a.value` and `b.value` equal `10`.

Diagram illustrating relationships, **not memory addresses**:

~~~mermaid
flowchart LR
  A["a"] --> X["Box #1: value = 10"]
  C["alias"] --> X
  B["b"] --> Y["Box #2: value = 10"]
~~~

| Expression | Result | Reason |
|---|---|---|
| `a == alias` | `true` | Both references point to the same object |
| `a == b` | `false` | Two `new` calls create two separate Boxes |
| `a.value == b.value` | `true` | Both `int` fields have the same value |
| `alias == b` | `false` | Two different objects |

**There is no rule that "matching fields make `==` true"** for references.


## 3. When Do Aliases Affect Identity Comparisons?

`Box alias = a;` makes `a == alias` evaluate to `true`; modifying `alias.value` does not change the result because both still point to the same object. After `alias = new Box(99);`, the comparison becomes `false` even though `a` was not modified. This is a relationship between the **current reference values** and identity, independent of whether two objects have matching fields.

## 4. `null`: When Neither Reference Points to an Object

`null` is a special reference value representing **not pointing to any object**.

~~~java
Box first = null;
Box second = null;
Box actual = new Box(5);

System.out.println(first == second); // true
System.out.println(first == actual); // false
System.out.println(actual != null);  // true
~~~

**Important point:** `null == null` evaluates to `true` in terms of reference comparison; it does **not** mean Java creates "a null object" that both point to.

Checking for `null` before dereferencing is a proper and common use case for `==`:

~~~java
static void printBox(Box box) {
    if (box == null) {
        System.out.println("No box");
        return;
    }
    System.out.println(box.value);
}
~~~

On the other hand:

~~~java
Box box = null;
// System.out.println(box.value); // If executed, throws NullPointerException
~~~

accessing a field through a `null` reference causes a runtime error.

**Distinguish from an unassigned local variable**:

~~~java
Box box;
// System.out.println(box == null); // Compile error: box has not been assigned a value
box = null;
System.out.println(box == null); // true
~~~

Declaring `Box box;` does not automatically initialize a local variable to `null`. The **definite assignment** rule still applies.

## 5. `String`: Why Content Should Be Compared Using `equals`

For text data, the intention is usually to compare **content**:

~~~java
String a = new String("Hello");
String b = new String("Hello");

System.out.println(a == b);      // false: two separate String instances
System.out.println(a.equals(b)); // true: same character content
~~~

**`String.equals`** is defined by the String class to compare the corresponding character sequences. It differs from the `==` operator on references.

### The String Pool Trap

~~~java
String a = "Java";
String b = "Java";

System.out.println(a == b); // true
~~~

Two **identical string literals** are *interned* according to Java's rules, so in this example they point to the same interned `String`.

However, **never rely on that `true` result as a way to check content** in general code:

~~~java
String literal = "Java";
String created = new String("Java");

System.out.println(literal == created);      // false
System.out.println(literal.equals(created)); // true
~~~

`new String("Java")` creates a new String object; its content is still `Java`, but its identity differs from the interned literal.

**Practice:** use `equals` when you want to check whether two strings have the same content. When a variable might be `null`, consider a null-safe comparison:

~~~java
String input = null;

System.out.println("OK".equals(input));           // false
System.out.println(java.util.Objects.equals(input, "OK")); // false
~~~

Do not call `input.equals(...)` when `input` can be `null`; invoking a method on null throws `NullPointerException`.

## 6. `equals()` Is Not the `==` Operator

`==` is a Java language operator. By contrast, `equals(Object)` is a **method** declared in `java.lang.Object`, and a class can **override** it to provide content-comparison criteria.

~~~java
static final class NumberBox {
    final int number;

    NumberBox(int number) {
        this.number = number;
    }
}

NumberBox a = new NumberBox(7);
NumberBox b = new NumberBox(7);

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // false: equals is not overridden
~~~

If a class **does not override `equals`**, the default implementation from `Object` only returns true for the same object. Do not assume that `equals` always compares fields.

If business logic requires value-based comparison, you can define `equals`/`hashCode` for the class yourself, or use a type that already supports appropriate value equality.

### `record` in Java 17: A Clear Example of Value Equality

~~~java
record Point(int x, int y) {}

Point p = new Point(1, 2);
Point q = new Point(1, 2);
Point alias = p;

System.out.println(p == q);       // false
System.out.println(p.equals(q));  // true
System.out.println(p == alias);   // true
~~~

A simple `record` automatically provides `equals` and `hashCode` based on the record's components. Yet **`==` still compares identity**, without turning into a content comparison merely because the type is a `record`.

> **Note:** A record's component-based `equals` does not automatically make mutable reference components immutable or force array comparison by content. For a record containing an array, pay special attention because an array's default `equals` compares identity.

## 7. Arrays: Same Elements Do Not Mean Same Array Object

~~~java
int[] first = {2, 4, 6};
int[] second = {2, 4, 6};
int[] alias = first;

System.out.println(first == second); // false
System.out.println(first == alias);  // true
~~~

Each independent array initialization creates an array object. To **compare the contents of one-dimensional arrays**, use `java.util.Arrays.equals`:

~~~java
System.out.println(java.util.Arrays.equals(first, second)); // true
~~~

For nested arrays, `Arrays.deepEquals` may be needed if the structure warrants it.

Like other objects, `first.equals(second)` on an array **does not compare elements**; `Object.equals` defaults to identity comparison.

**Do not confuse** `Arrays.equals` with `==`: the content-comparison API inspects each element according to the array type's rules, whereas `==` on references only determines whether it is a single object or not.

## 8. Wrappers, Autoboxing, and Caching: Do Not Use `==` to Compare Values

Wrapper types such as `Integer` or `Long` are **objects**, not their corresponding primitives:

~~~java
Integer left = Integer.valueOf(500);
Integer right = Integer.valueOf(500);

System.out.println(left.equals(right)); // true
~~~

You should not check `left == right` intending to compare the number 500: `==` on two variables of type `Integer` compares **references**, and the result can be affected by caching/API implementation.

Some boxed values have guaranteed or common caching so `==` occasionally returns `true`; that is precisely why this bug is **hard to catch** if you only test a few small values.

Distinguish two situations:

~~~java
Integer boxed = 500;
int primitive = 500;

System.out.println(boxed.equals(primitive)); // true (parameter is boxed)
System.out.println(boxed == primitive);      // true (unboxed then numerically compared)
~~~

In the comparison `boxed == primitive`, an `int` operand causes the wrapper to be **unboxed**, and then Java performs numeric comparison; it is not reference identity. If `boxed == null`, unboxing in this expression can throw `NullPointerException`.

**Rule:** for wrappers, if you want to compare contents, use `equals`, `Objects.equals`, or convert to primitive with null handling; do not rely on identity.


## 9. Checking Identity Across Method Calls

Reference parameters are **copied by value**. A method can mutate a shared object without changing `==` between aliases; if the method reassigns the parameter with `new Box(...)`, the reference in the caller's variable remains unchanged. Identity checks must be based on the **references at the time of comparison**, not on whether a method previously received an argument.

## 10. Comparison Selection Table

| Data / goal | Appropriate check |
|---|---|
| Two primitive `int` variables | `a == b` |
| Whether two references point to the same instance | `a == b` |
| Whether a reference is null | `value == null` or `value != null` |
| Whether two `String`s have the same content | `a.equals(b)` if `a` is guaranteed non-null |
| Two possibly null String values | `Objects.equals(a, b)` |
| Two `int[]` arrays with the same elements | `Arrays.equals(a, b)` |
| Two objects of a custom class with the same data | Override `equals` per contract or use an appropriate value type |
| Two `Integer` wrapper values with the same number | `Objects.equals(a, b)` or `equals` when non-null |
| Two `record`s with the same components | `equals` per the record contract |

This is an **intent-based** table, not a single universal comparison applied blindly whenever variables appear. For `float`/`double` floating-point numbers, there are also separate rules for NaN, signed zero, and approximation error; do not carry reference identity comparison over to floating-point problems.

## 11. Complete Java 17 Example and Run Output

Create a file named exactly **`ReferenceIdentityDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class ReferenceIdentityDemo {
    private ReferenceIdentityDemo() {}

    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    record Point(int x, int y) {}

    static void rebind(Box parameter) {
        parameter = new Box(999);
        System.out.println("inside parameter=" + parameter.value);
    }

    public static void main(String[] args) {
        int number1 = 10;
        int number2 = 10;
        System.out.println("primitive equal=" + (number1 == number2));

        Box first = new Box(10);
        Box alias = first;
        Box twin = new Box(10);
        System.out.println("alias identity=" + (first == alias));
        System.out.println("twin identity=" + (first == twin));
        System.out.println("field values=" + (first.value == twin.value));

        alias.value = 25;
        System.out.println("first after alias=" + first.value);
        System.out.println("twin unchanged=" + twin.value);

        alias = new Box(30);
        System.out.println("identity after rebind=" + (first == alias));
        System.out.println("first after rebind=" + first.value);

        Box absent = null;
        Box alsoAbsent = null;
        System.out.println("two null references=" + (absent == alsoAbsent));
        System.out.println("null vs object=" + (absent == first));
        System.out.println("null safe equals=" + Objects.equals(absent, alsoAbsent));

        String text1 = new String("Java");
        String text2 = new String("Java");
        String textAlias = text1;
        System.out.println("new Strings identity=" + (text1 == text2));
        System.out.println("new Strings contents=" + text1.equals(text2));
        System.out.println("String alias identity=" + (text1 == textAlias));

        String literal1 = "OK";
        String literal2 = "OK";
        System.out.println("interned literals=" + (literal1 == literal2));

        int[] array1 = {1, 2};
        int[] array2 = {1, 2};
        int[] arrayAlias = array1;
        System.out.println("arrays identity=" + (array1 == array2));
        System.out.println("arrays contents=" + Arrays.equals(array1, array2));
        System.out.println("array alias identity=" + (array1 == arrayAlias));

        Point point1 = new Point(1, 2);
        Point point2 = new Point(1, 2);
        System.out.println("records identity=" + (point1 == point2));
        System.out.println("records contents=" + point1.equals(point2));

        Integer boxed = Integer.valueOf(500);
        int primitive = 500;
        System.out.println("boxed vs primitive=" + (boxed == primitive));

        rebind(first);
        System.out.println("caller unchanged=" + first.value);
    }
}
~~~

Open a terminal in the directory containing the file; **JDK 17+** must be installed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ReferenceIdentityDemo.java
java -cp . ReferenceIdentityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ReferenceIdentityDemo.java
java -cp . ReferenceIdentityDemo
~~~

**Exact expected output:**

~~~text
primitive equal=true
alias identity=true
twin identity=false
field values=true
first after alias=25
twin unchanged=10
identity after rebind=false
first after rebind=25
two null references=true
null vs object=false
null safe equals=true
new Strings identity=false
new Strings contents=true
String alias identity=true
interned literals=true
arrays identity=false
arrays contents=true
array alias identity=true
records identity=false
records contents=true
boxed vs primitive=true
inside parameter=999
caller unchanged=25
~~~

The output avoids hash codes, object addresses, or unstable cache implementation details. Points you should verify yourself:

- **Alias:** `first == alias` is initially `true`; modifying `alias.value` changes `first.value` as well.
- **Reassignment:** after `alias = new Box(30)`, `first == alias` is `false`; `first.value` is still `25`.
- **Null:** two `null` references compared with `==` evaluate to `true`, even though there is no `null` object.
- **String:** two independent `new String` calls have different identity, yet `equals` returns true.
- **Array:** two different array objects even though `Arrays.equals` sees matching elements.
- **Record:** `point1 == point2` is false, while `point1.equals(point2)` is true.
- **Wrapper:** `boxed == primitive` performs unboxing for numeric comparison, so it is true.
- **Method:** creating a new Box for the parameter inside `rebind` does not change the object that `first` points to.

## 12. Common Mistakes

| Code snippet / misconception | Issue | Fix |
|---|---|---|
| `new Box(1) == new Box(1)` must be true | Two `new` calls create two objects | Use contract-based content comparison if that is the goal |
| `Box b = a` creates a copy of Box | Assignment only copies the reference value | Needs an explicit copy/object creation mechanism |
| Two objects with matching `value` fields have `==` true | `==` does not compare fields | Compare values or use a well-designed `equals` |
| `"Hi" == new String("Hi")` is true because the text matches | String literal and newly created String differ in identity | `equals` |
| Testing two matching literals and deciding to use `==` for String | String pool causes misleading results | Use `String.equals` |
| `a.equals(b)` with `a == null` | Calling a method on null throws an exception | `Objects.equals(a, b)` |
| `charArray1 == charArray2` to compare elements | `==` compares array objects | `Arrays.equals` |
| `Integer a == Integer b` to compare numbers | Compares identity of boxed objects | Use `equals`/`Objects.equals` |
| `Integer boxed = null; boxed == 1` | Unboxing null throws `NullPointerException` | Check for null first |
| Overriding `equals` and expecting `==` to change behavior | `==` cannot be overridden | Call `equals` where appropriate |
| `rebind(parameter)` makes the caller's variable point to a new object | Java is pass-by-value | Return the new reference and assign on the caller side if needed |
| Looking at `Object.toString()` and thinking it is an address | No physical address guarantee | Reason via identity, not hash/address |

**Be careful about static types:** not every arbitrary pair of references can be written as `a == b`. The compiler requires the operands to have types that allow checking reference equality; some unrelated type pairs may be rejected at compile time. Do not cast recklessly just to force a meaningless comparison.

## 13. Self-Check Exercises (with Answers)

### Exercise A — Same Object or Same Field?

~~~java
Box a = new Box(7);
Box b = a;
Box c = new Box(7);
System.out.println(a == b);
System.out.println(a == c);
System.out.println(a.value == c.value);
~~~

**Answer:**

~~~text
true
false
true
~~~

### Exercise B — Mutating an Alias Then Reassigning

~~~java
Box first = new Box(4);
Box second = first;
second.value = 9;
second = new Box(1);
System.out.println(first.value);
System.out.println(first == second);
~~~

**Answer:**

~~~text
9
false
~~~

### Exercise C — Two Strings with Identical Content

~~~java
String a = new String("ok");
String b = new String("ok");
System.out.println(a == b);
System.out.println(a.equals(b));
~~~

**Answer:**

~~~text
false
true
~~~

### Exercise D — Two Arrays with Matching Elements

~~~java
int[] a = {3, 4};
int[] b = {3, 4};
System.out.println(a == b);
System.out.println(java.util.Arrays.equals(a, b));
~~~

**Answer:**

~~~text
false
true
~~~

### Exercise E — null

~~~java
Object a = null;
Object b = null;
System.out.println(a == b);
System.out.println(java.util.Objects.equals(a, b));
~~~

**Answer:**

~~~text
true
true
~~~

In this example both approaches return true, yet they are **not the same in nature**: `==` compares two null reference values; `Objects.equals` is a null-safe equality check.

## 14. Checklist and Conclusion

- [ ] Know that `==` on primitives differs from `==` on references.
- [ ] Explain why calling `new Box(1)` twice does not create the same identity.
- [ ] Know that `Box alias = first;` only copies the reference.
- [ ] Distinguish mutating an object through an alias from reassigning a reference variable.
- [ ] Understand that `null == null` is true but `null` is not an object.
- [ ] Use `String.equals` instead of `==` when comparing string contents.
- [ ] Know that the string pool can make comparing literals with `==` return true.
- [ ] Know `Arrays.equals` for comparing array contents.
- [ ] Understand that `Object.equals` defaults to identity comparison when a class does not override it.
- [ ] Remember that `record.equals` compares components while `record == record` still compares identity.
- [ ] Avoid using `==` on two wrappers to compare values, watching out for unboxing.
- [ ] Run `ReferenceIdentityDemo.java` with Java 17+ `javac`/`java` and verify all expected output.

**Conclusion:** When applied to Java references, `==` asks **"is it the same object, or are both null?"**. It does **not** automatically check "equal data". When you want to compare contents, choose the appropriate API and equality contract: `String.equals`, `Arrays.equals`, `Objects.equals`, or `equals` provided by the class.
