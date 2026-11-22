# Declared Type Determines the Values a Variable Can Hold

> **Java core — language-basics / Variables and Constants**  
> **Environment:** JDK 17 or later.  
> **Objective:** Understand how the declared type constrains the values assignable to a variable; distinguish primitive and reference variables, type conversions, type inference with `var`, and reassignment rules with `final`.

## 1. A Variable Has a Type from the Moment It Is Declared

Java is a **statically typed** language. When declaring:

~~~java
int age = 20;
String name = "Lan";
boolean active = true;
~~~

the compiler knows `age` has type `int`, `name` has type `String`, and `active` has type `boolean`. Any subsequent assignment must be **compatible with the declared type**, rather than freely turning `age` into a string variable.

Basic structure: `Type variableName = initialValue;`. For example, `int count = 3;` consists of the type `int`, name `count`, and initializer expression `3`. A local variable can be declared first and assigned later, but it must be **definitely assigned before being read**:

~~~java
int count;
count = 3;
System.out.println(count); // 3
~~~

This differs from object fields, which receive default values when the object is created; do not infer that an unassigned local variable defaults to `0`.

## 2. Primitive Types: Holding a Value in the Type's Domain

Java has eight primitive types. A primitive variable holds a **value** of that kind, not a reference to an object:

| Type | Values it can hold | Example |
| --- | --- | --- |
| `byte` | Signed integer -128 to 127 (8-bit) | `byte level = 100;` |
| `short` | Signed integer -32768 to 32767 (16-bit) | `short pages = 500;` |
| `int` | Signed integer -2147483648 to 2147483647 (32-bit) | `int amount = 10_000;` |
| `long` | 64-bit signed integer | `long total = 3_000_000_000L;` |
| `float` | 32-bit IEEE 754 floating-point number, finite precision | `float rate = 1.5f;` |
| `double` | 64-bit IEEE 754 floating-point number, finite precision | `double ratio = 1.5;` |
| `char` | A single UTF-16 code unit, from `'\u0000'` to `'\uffff'` | `char grade = 'A';` |
| `boolean` | Only `true` or `false` | `boolean ready = true;` |

`char` does not guarantee holding every Unicode character completely: some code points outside the BMP require **two** UTF-16 code units. `float` and `double` also include special values like NaN and infinity; they are not exact decimal types for all monetary calculations.

For decimal integer literals exceeding the `int` range, add the `L` suffix to create a `long` literal:

~~~java
long visitors = 3_000_000_000L;  // Valid.
// long wrong = 3_000_000_000;  // Invalid: default int literal is too large.
~~~

`boolean` does not automatically convert to `0`/`1`; `int flag = true;` is a type error.

## 3. Reference Types: The Declared Type Limits What Objects Are Pointed To

`String`, arrays, classes, interfaces, records, etc., are **reference types**. A reference variable holds a **reference** to a compatible object (or `null`), rather than directly containing the entire object the way a primitive variable holds a number.

~~~java
String title = "Java";
CharSequence text = title;           // String implements CharSequence.
Number number = Integer.valueOf(42); // Integer is a Number.
number = Double.valueOf(2.5);       // Double is also a Number.
Object item = "book";
item = Integer.valueOf(7);          // Integer is also an Object.
~~~

A variable declared as `Number` can point to an `Integer` or a `Double` because both are compatible with `Number`. **The declared type of the variable remains `Number`** after reassignment, even though the runtime type of the object changes.

The compiler also restricts which methods can be called based on the **reference type at the call site**:

~~~java
CharSequence text = "Java";
System.out.println(text.length()); // Valid: CharSequence has length().
// text.substring(1);              // Invalid: CharSequence does not declare substring().
~~~

The actual object may be a `String`, but the compiler does not automatically allow calling every `String`-specific method through a `CharSequence` variable. When an operation genuinely depends on the runtime type, check first—for instance with Java 17 syntax `if (item instanceof Integer i) { ... }`.

`null` can be assigned to a reference variable like `String name = null;`, but cannot be assigned to a primitive `int`. Calling a method on a `null` reference can cause a `NullPointerException`.

## 4. Valid Assignments, Widening, and Narrowing

| Situation | Example | Outcome |
| --- | --- | --- |
| Same type | `int x = 10; x = 20;` | Valid |
| Integer widening | `byte b = 100; int x = b;` | Valid, preserves value |
| `int` to `long` | `int x = 100; long y = x;` | Valid |
| Narrowing with cast | `int x = 130; byte b = (byte) x;` | Syntactically valid, **b = -126** because only the low 8 bits are kept |
| Floating-point to integer with cast | `int n = (int) 3.9;` | Valid, **n = 3** (fractional part is discarded) |
| Assigning a string to a number | `int x = "10";` | **Compile error** |
| Assigning a number to boolean | `boolean b = 1;` | **Compile error** |
| Assigning supertype to subtype | `Object o = "Hi"; String s = o;` | **Compile error** without an appropriate cast/type check |

**Note on widening:** converting from integer types to `float`/`double` can lose precision for large values, even though no cast is required. **A cast does not guarantee the value stays intact**; it only permits a specific type conversion.

A practical compile-time exception: `byte b = 100;` is valid because `100` is an `int` constant expression within the `byte` range; however:

~~~java
int number = 100;
// byte b = number;  // Error: number is an int variable, not a constant expression.
// byte b = 128;     // Error: exceeds byte range.
~~~

Do not equate **a currently small value** with the compiler allowing every narrowing assignment.

## 5. Compilable and Runnable Java 17+ Program

Create the file **DeclaredTypeDemo.java**:

~~~java
public class DeclaredTypeDemo {
    public static void main(String[] args) {
        byte small = 100;
        int quantity = small;
        long revenue = 3_000_000_000L;
        double average = quantity / 4.0;
        boolean available = true;
        char grade = 'A';

        CharSequence text = "Java 17";
        Number number = Integer.valueOf(42);
        number = Double.valueOf(2.5);

        Object item = "book";
        item = Integer.valueOf(7);

        byte narrowed = (byte) 130;
        int whole = (int) 3.9;

        var inferred = 10; // Compiler infers int.
        inferred = 12;
        final int MAX = 20;

        System.out.println("quantity=" + quantity);
        System.out.println("revenue=" + revenue);
        System.out.println("average=" + average);
        System.out.println("available=" + available + ", grade=" + grade);
        System.out.println("text=" + text);
        System.out.println("number=" + number);
        System.out.println("item=" + item);
        System.out.println("narrowed=" + narrowed + ", whole=" + whole);
        System.out.println("inferred=" + inferred + ", MAX=" + MAX);

        if (item instanceof Integer value) {
            System.out.println("nextItem=" + (value + 1));
        }
    }
}
~~~

In a terminal (Bash, PowerShell, or Command Prompt) in the directory containing the file:

~~~bash
javac -encoding UTF-8 DeclaredTypeDemo.java
java DeclaredTypeDemo
~~~

**Expected output:**

~~~text
quantity=100
revenue=3000000000
average=25.0
available=true, grade=A
text=Java 17
number=2.5
item=7
narrowed=-126, whole=3
inferred=12, MAX=20
nextItem=8
~~~

Reading the output: `quantity` receives the `byte` value as an `int`; `number` keeps its declared type `Number` while pointing to a `Double` object when printed; `narrowed` illustrates lossy narrowing conversion; `item instanceof Integer value` checks the object's type before using `value` as an `Integer`.


## 6. `var` Preserves Static Typing; `final` Restricts Reassignment

`var` enables type inference from the initializer in supported positions, but the inferred type remains fixed:

~~~java
var count = 10;    // int
count = 20;        // Valid
// count = "twenty"; // Type error
// var unknown = null; // Cannot infer type from null alone
~~~

`final` is a constraint on **how many times a variable can be assigned**, independent of its declared type:

~~~java
final Number max = Integer.valueOf(10);
// max = Double.valueOf(3.5); // Error: final disallows reassignment
~~~

Therefore, the question "is this value **assignable because the types are compatible?**" is different from "**is this `final` variable still allowed to be assigned?**" Control-flow assignment rules for `final` and object mutability are covered in depth in two dedicated lessons.

## 7. Common Pitfalls and Self-Check

| Code snippet | Issue | Fix |
| --- | --- | --- |
| `long n = 3_000_000_000;` | Decimal literal lacks `L` and is too large for `int` | `3_000_000_000L` |
| `byte b = 128;` | Outside `byte` range | Use a wider type or an in-range value |
| `int x = 3.9;` | `double` does not automatically narrow to `int` | Check if `(int) 3.9` is actually intended |
| `String s = 100;` | `int` is not directly assignable to `String` | `String.valueOf(100)` |
| `var x = 10; x = "A";` | `var` already inferred `int` | Use a variable of an appropriate type, do not assign a different type |
| `CharSequence t = "Hi"; t.substring(1);` | Declared type does not have `substring` method | Use `String` when needed, or safely check/cast |
| `String s = null; s.length();` | `null` reference has no object to invoke methods on | Check for `null` or design to avoid null |

### Short Exercises

1. Predict the type and value of `var x = 5L;`, then try assigning `x = 6;` and `x = "6";`. Why do the outcomes differ?
2. Explain why `byte b = 100;` compiles, whereas `int x = 100; byte b = x;` does not.
3. Create `Number n = Integer.valueOf(3);` and then assign `Double.valueOf(3.5)`. Does the declared type of `n` change?
4. Try `final StringBuilder b = new StringBuilder(); b.append("OK");`. Distinguish mutating the object from reassigning the reference.
5. In `DeclaredTypeDemo`, try replacing `(byte) 130` with `(byte) 127` and predict the output.

**Takeaway:** For **primitives**, the declared type determines the value range and representation. For **references**, the declared type limits compatible objects and accessible members through the variable; the actual object can be a subtype. `var` only helps infer a fixed type; `final` only restricts reassigning the variable. Every assignment must pass Java's type rules.
