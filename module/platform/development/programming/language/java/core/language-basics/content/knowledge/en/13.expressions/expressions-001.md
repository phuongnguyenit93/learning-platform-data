# Expressions Produce a Value and Have a Compile-Time Type — Java 17+

## 1. Lesson Objectives

In Java, an **expression** is a syntactic construct evaluated according to the rules of the language. For a value-producing expression, the result has **a value**, and the compiler determines the **type of the expression** before the program runs.

~~~java
int a = 7;
int b = 3;

int sum = a + b;       // Expression a + b has type int, value 10
boolean larger = a > b; // Expression a > b has type boolean, value true
String label = "Java"; // String literal has type String, value "Java"
~~~

Three points to distinguish:

1. **Static type (*compile-time type*)**: determined by the compiler from operands, operators, declarations, and context.
2. **Runtime value**: the concrete result when the expression is evaluated, depending on current data.
3. **Actual object (*runtime object*)**: for a non-null reference expression, the object that the reference value points to may belong to a subclass of the static type.

For example, `a + b` always has type `int` in the declarations above; if `a` and `b` change, the **value** can change, but the **expression type does not change**.

> Important exception: a `void` method invocation is considered an expression, yet it **does not produce a value for further use**. An expression can also fail to complete normally if it throws an exception. Therefore, saying "every expression always returns a value" is overly absolute.

## 2. How Does an Expression Differ from a Statement?

A value-producing expression can be:

~~~java
42               // int literal
2 + 3            // int addition
"Hi".length()    // Method invocation returning int
a > b            // Comparison returning boolean
new StringBuilder("A") // Creates an object, yielding a reference value
~~~

These lines are **expression fragments**, not necessarily valid standalone Java statements if copied directly into a method.

A **statement** expresses an action in the flow of execution: variable declaration, assignment, branching, looping, `return`, etc.

~~~java
int result = 2 + 3;         // Declaration statement; initializer is an expression
System.out.println(result); // Expression statement: method invocation
if (result > 4) {           // if statement; condition is a boolean expression
    System.out.println("ok");
}
~~~

**Not every expression can stand alone as a statement.**

~~~java
// 2 + 3; // Invalid: plain addition is not a valid statement expression
~~~

Some groups of expressions **are allowed to be used as statements** (*statement expressions*): assignments, increments/decrements, certain method invocations, and class instance creation expressions:

~~~java
result = 10;             // Assignment expression used as a statement
result++;                // Increment expression used as a statement
System.out.println(result); // Method invocation used as a statement
new StringBuilder("A");   // Class instance creation expression as a statement
~~~

**Remember:** statement and expression are not synonymous concepts. A single statement can contain multiple sub-expressions.

## 3. How Is an Expression's Type Determined?

The compiler applies Java type rules, for example:

| Expression | Static type | Example value |
|---|---|---|
| `10` | `int` | `10` |
| `10L` | `long` | `10` |
| `2.5` | `double` | `2.5` |
| `2.5f` | `float` | `2.5` |
| `'A'` | `char` | UTF-16 code unit `'A'` |
| `true` | `boolean` | `true` |
| `"Java"` | `String` | Text `Java` |
| `a + b` with a,b `int` | `int` | For example `10` |
| `a > b` with a,b `int` | `boolean` | For example `true` |
| `"Hi".length()` | `int` | `2` |
| `new int[3]` | `int[]` | Reference to a new array |
| `new StringBuilder()` | `StringBuilder` | Reference to a new object |

Do not guess the type from a variable name or how a printed value looks. Look at **the declared types of operands, the kind of literal, the method signature**, and **the type-conversion context**.

Reasoning diagram:

~~~mermaid
flowchart TD
    A["Java expression"] --> B["Determine operand types / signature / literal"]
    B --> C["Apply operator and conversion rules"]
    C --> D["Static type at compile time"]
    D --> E["Compiler checks usage context"]
    E --> F["At runtime: evaluate and produce a value if completed normally"]
~~~

The diagram illustrates the **logical process of typing and evaluation**, not a mandatory internal JVM diagram.

## 4. Arithmetic Expressions: Type Does Not Necessarily Match the Receiving Variable's Type

~~~java
int a = 7;
int b = 2;

int whole = a / b;       // int / int expression: type int, value 3
double alsoWhole = a / b; // Still int arithmetic: value 3, then converted to 3.0
double fractional = (double) a / b; // double / double: value 3.5

System.out.println(whole);      // 3
System.out.println(alsoWhole);  // 3.0
System.out.println(fractional); // 3.5
~~~

**Why doesn't `alsoWhole` become 3.5?** The division `a / b` is performed according to the type of the **expression** (`int`); only afterward is the result `3` widened to `double` for assignment.

Writing `(double) a / b` causes the division to be carried out in `double` from the start, thereby preserving the fractional part.

**Do not use the target variable's type to infer backward what computation occurred.** With `var`, the type is also inferred from the initializer:

~~~java
var result = a / b; // result has type int
~~~

`var` never makes an expression automatically pick a wider type.

## 5. Numeric Promotion: byte, short, char Usually Promote to int

A normal addition between two `byte` variables produces an expression of type `int`:

~~~java
byte left = 100;
byte right = 20;

int sum = left + right; // Expression result is int
System.out.println(sum); // 120

// byte invalid = left + right; // Compile error: int does not implicitly narrow to byte
~~~

Key points:

- Both variables are `byte`, but the **binary numeric promotion** rule promotes them to `int` before addition.
- The compiler does not infer "because the result 120 fits in a byte, the expression type will be byte."
- To convert back to `byte`, an appropriate cast is needed **along with** your own range check if overflow is not allowed.

With `char`:

~~~java
char letter = 'A';
int nextCodeUnit = letter + 1; // Result is int, value 66
char nextLetter = (char) nextCodeUnit;
System.out.println(nextLetter); // B
~~~

With a `double` operand, a mixed arithmetic expression is normally promoted to `double`:

~~~java
double mixed = 7 + 0.5;
System.out.println(mixed); // 7.5
~~~

There is no primitive numeric widening/narrowing conversion from or to `boolean`.

## 6. Compile-Time Type Does Not Guarantee Avoiding Overflow

~~~java
long wrong = 2_000_000_000 + 2_000_000_000;
long right = 2_000_000_000L + 2_000_000_000;

System.out.println(wrong); // -294967296
System.out.println(right); // 4000000000
~~~

On the first line:

1. Both literals have type `int`.
2. The `int + int` expression has type `int` and **overflows** during addition.
3. Only then is the overflowed `int` value converted to `long` for assignment.

The second line has its first operand of type `long`, so the addition has type `long` from the start.

**The compiler knows the expression type, but it does not automatically prove that an arithmetic expression satisfies business bounds.** If you need to detect `int` overflow, you can use `Math.addExact(int, int)` where appropriate: the method throws `ArithmeticException` if the sum exceeds the `int` range.

## 7. Comparisons and Logic: boolean Type

Numeric comparison operators return `boolean`:

~~~java
int a = 7;
int b = 3;
boolean greater = a > b;
boolean equal = a == b;

System.out.println(greater); // true
System.out.println(equal);   // false
~~~

The logical operators `&&`, `||` yield a `boolean` result and **short-circuit** once the result is determined:

~~~java
int divisor = 0;
boolean safe = divisor != 0 && 10 / divisor > 1;

System.out.println(safe); // false, does not divide by 0
~~~

If the first operand `divisor != 0` is false, Java **does not evaluate** the `10 / divisor > 1` part. This shows that **having a static type** does not mean every sub-expression is executed on every run.

**The `if` syntax requires a condition expression of type `boolean`** (or a `Boolean` suitably unboxed); it does not accept an integer as a condition:

~~~java
// if (1) { ... } // Compile error: int is not boolean
if (a > b) {
    System.out.println("a is greater than b");
}
~~~

## 8. String Concatenation Is Also an Expression of Type String

The `+` operator can either add numbers or concatenate `String`s. The semantics depend on operand types and evaluation order.

~~~java
int a = 7;
int b = 3;

System.out.println("result=" + a + b);   // result=73
System.out.println("result=" + (a + b)); // result=10
~~~

`+` is left-associative:

- `"result=" + a + b` starts with a `String` → concatenates as `String` step by step.
- `"result=" + (a + b)` performs numeric addition inside parentheses first, then concatenates the result 10.

Comparison table:

| Expression | Static type | Value |
|---|---|---|
| `7 + 3` | `int` | `10` |
| `"7" + 3` | `String` | `"73"` |
| `"result=" + 7 + 3` | `String` | `"result=73"` |
| `"result=" + (7 + 3)` | `String` | `"result=10"` |

Java **does not automatically parse numeric strings** to turn `"7" + "3"` into addition yielding 10. To turn text into numbers, you must use an API such as `Integer.parseInt` and handle malformed input.

## 9. Method Invocations: Expression Type Follows the Return Signature

~~~java
static int twice(int value) {
    return value * 2;
}

// In main:
int answer = twice(6);
System.out.println(answer); // 12
~~~

The expression `twice(6)` has type **`int`**, because the method `twice` is declared to return `int`. The compiler does not need to run the method to know that type.

Similarly:

~~~java
var length = "Java".length(); // Inferred as int
var message = String.valueOf(123); // Inferred as String
~~~

If a method is declared to return `Object`, then **the static type of the method invocation expression is `Object`**, even though the returned object at runtime might be a `String`:

~~~java
static Object makeText() {
    return "Java";
}

// In main:
Object value = makeText(); // Type of expression makeText() is Object
System.out.println(value.toString()); // Java
// value.length(); // Compile error: Object does not declare length()
~~~

**Do not use the actual runtime value to assume method-call rights at compile time.** The static reference type is the contract the compiler uses.

## 10. Static Type of a Reference vs. Actual Class at Runtime

~~~java
class Animal {
    String sound() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }

    void fetch() {}
}
~~~

Inside a method:

~~~java
Animal pet = new Dog();

System.out.println(pet.sound()); // woof
// pet.fetch(); // Compile error: static type Animal has no fetch()
~~~

Explanation:

- The expression `new Dog()` has static type `Dog` and creates a reference to a `Dog` instance.
- The variable `pet` has declared type **`Animal`**, receiving that reference via widening reference conversion.
- When writing `pet.sound()`, the compiler allows the call because `Animal` declares `sound()`; at runtime, **dynamic dispatch** selects the overridden implementation in `Dog`.
- `pet.fetch()` does not compile because the static type `Animal` has no `fetch()` method, even though the actual object is a `Dog`.

**Static type** governs which members are accessible; **runtime class** determines the implementation of an overridden instance method.

## 11. Overload Resolution Picks by Static Type at Compile Time

~~~java
static void describe(Object value) {
    System.out.println("Object overload");
}

static void describe(String value) {
    System.out.println("String overload");
}
~~~

With:

~~~java
Object value = "Java";
String text = "Java";

describe(value); // Object overload
describe(text);  // String overload
~~~

Both variables may point **to the same String object**, yet the compiler selects the overload based on the **static type of the argument**:

- `value` has type `Object`: selects `describe(Object)`.
- `text` has type `String`: selects `describe(String)`.

**Do not confuse overload resolution with override dispatch:**

| Mechanism | Primary decision | Timing |
|---|---|---|
| **Overload**: multiple methods with the same name, different parameters | Applicable signature by static type of arguments | Compile time |
| **Override**: subclass redefines an instance method | Implementation by runtime object | Runtime |

An expression's type may be decided early by the compiler, but that does not mean Java ignores polymorphism at execution time.

## 12. Assignment Expressions Also Have a Type and Value

The assignment `=` is an expression: it updates the variable and yields a value of the left-hand variable's type.

~~~java
int count = 1;
int result = (count = 4) + 2;
System.out.println(count);  // 4
System.out.println(result); // 6
~~~

Similarly, `++count` and `count++` yield expression values after and before incrementing the variable, respectively. These examples show that **static type and value** do not describe all runtime behavior: an expression can also mutate state. When an update does not need to sit inside a calculation, separate it into its own statement.

## 13. Conditional Expression `?:` Has Rules for Determining Type

~~~java
boolean enabled = true;
double selected = enabled ? 1 : 2.5;
System.out.println(selected); // 1.0
~~~

The chosen branch determines the **runtime value**, while this `int`/`double` numeric conditional expression has type `double` according to numeric conditional expression rules. Do not infer the type from which branch runs. For reference conditional expressions, Java also has target typing / poly expression rules; there is no universal rule of "always picking the widest type."

## 14. Type Casting and Conversions After the Expression Type Is Known

~~~java
double reading = 7.9;

int truncated = (int) reading; // Cast double -> int
System.out.println(truncated); // 7
~~~

The expression `(int) reading` has type `int`, unlike `reading` which has type `double`. A cast requests an explicit valid conversion; for finite in-range values, converting from `double` to `int` **truncates the fractional part toward zero**, rather than rounding to nearest.

Another case:

~~~java
int value = 130;
byte small = (byte) value;
System.out.println(small); // -126
~~~

The result `(byte) value` has type `byte` but does not preserve the value 130, because narrowing integers can lose data.

**Distinguish three things:**

- **Type checking:** the compiler determines and verifies what kinds of values may be used.
- **Conversion:** Java may transform the representation/value to match the target type.
- **Business validation:** the program must check on its own whether the result meets domain requirements.

The fact that `(int) reading` is syntactically valid does not guarantee the operation is right for currency amounts, quantities, or measurements requiring fractional precision.

## 15. `var` Observes the Compile-Time Type from the Initializer

~~~java
var count = 10;           // int
var title = "Java";       // String
var average = 10 / 4;     // int: value 2
var preciseAverage = 10.0 / 4; // double: value 2.5
~~~

`var` **does not create a dynamically typed variable**: it infers the static type of the initializing expression.

~~~java
var count = 10;
// count = "ten"; // Compile error: count already has type int
~~~

A point to remember:

~~~java
// var unknown = null; // Invalid: the null literal provides no type to infer
String knownType = null;  // Valid: type is explicitly declared
~~~

Java has a notion of the type of the `null` literal and target typing contexts; however, `var unknown = null` by itself lacks sufficient information for a valid inferred local variable type.

With generics:

~~~java
var names = java.util.List.of("Lan", "An"); // List<String>
System.out.println(names.get(0).length()); // 3
// names.add(123); // Compile error: Integer is not String
~~~

Do not confuse **static type checking** with **collection mutability at runtime**. `List.of` creates an unmodifiable list; attempting to add a type-compatible `String` element can still throw `UnsupportedOperationException` at runtime.

## 16. When There Is a Type but No Usable Value

A invocation of a method declared `void` can complete normally yet produce no value for assignment:

~~~java
System.out.println("Hello"); // Valid as a statement expression
// int n = System.out.println("Hello"); // Type error: invocation returns void
~~~

An expression of type `int` can also **fail to return a runtime result** if it throws an exception, such as `10 / denominator` when `denominator == 0`. Types are checked by the compiler, whereas success or failure happens during evaluation; side effects prior to the failure are not automatically rolled back.

## 17. Complete, Runnable Java 17 Example

Create the exact file **`ExpressionValueTypeDemo.java`**:

~~~java
public final class ExpressionValueTypeDemo {
    private ExpressionValueTypeDemo() {}

    static class Animal {
        String sound() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String sound() {
            return "woof";
        }

        void fetch() {
            System.out.println("fetch");
        }
    }

    static int twice(int value) {
        return value * 2;
    }

    static void describe(Object value) {
        System.out.println("overload=Object");
    }

    static void describe(String value) {
        System.out.println("overload=String");
    }

    public static void main(String[] args) {
        int a = 7;
        int b = 3;
        int sum = a + b;
        boolean greater = a > b;
        System.out.println("sum=" + sum);
        System.out.println("greater=" + greater);

        int whole = a / 2;
        double widenedAfter = a / 2;
        double fractional = (double) a / 2;
        System.out.println("int division=" + whole);
        System.out.println("widen after division=" + widenedAfter);
        System.out.println("double division=" + fractional);

        byte small = 10;
        int promoted = small + 1;
        System.out.println("promoted byte expression=" + promoted);
        System.out.println("mixed expression=" + (a + 0.5));

        System.out.println("concat=" + a + b);
        System.out.println("grouped=" + (a + b));

        int assigned = 1;
        int assignmentResult = (assigned = 4) + 2;
        System.out.println("assignment target=" + assigned);
        System.out.println("assignment result=" + assignmentResult);
        int before = ++assigned;
        int after = assigned++;
        System.out.println("prefix value=" + before);
        System.out.println("postfix value=" + after);
        System.out.println("after increment=" + assigned);

        boolean chooseFirst = true;
        double selected = chooseFirst ? 1 : 2.5;
        System.out.println("conditional selected=" + selected);

        int methodResult = twice(6);
        System.out.println("method expression=" + methodResult);

        Object object = "Java";
        String text = "Java";
        describe(object);
        describe(text);
        System.out.println("object toString=" + object.toString());
        System.out.println("text length=" + text.length());

        Animal pet = new Dog();
        System.out.println("virtual sound=" + pet.sound());

        int[] numbers = {2, 4};
        System.out.println("array element=" + numbers[1]);

        var inferred = "Hi".length();
        System.out.println("var inferred int=" + inferred);

        Integer boxed = 10;
        int unboxedSum = boxed + 2;
        System.out.println("wrapper arithmetic=" + unboxedSum);

        int divisor = 0;
        boolean guarded = divisor != 0 && 10 / divisor > 1;
        System.out.println("short circuit=" + guarded);

        long overflowFirst = 2_000_000_000 + 2_000_000_000;
        long longFirst = 2_000_000_000L + 2_000_000_000;
        System.out.println("overflow first=" + overflowFirst);
        System.out.println("long first=" + longFirst);

        System.out.println("void call completed");
    }
}
~~~

**Requirements:** JDK 17 or newer. Open a terminal in the folder containing `ExpressionValueTypeDemo.java`. No Maven, Gradle, or libraries outside the JDK are needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ExpressionValueTypeDemo.java
java -cp . ExpressionValueTypeDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ExpressionValueTypeDemo.java
java -cp . ExpressionValueTypeDemo
~~~

**Exact expected output:**

~~~text
sum=10
greater=true
int division=3
widen after division=3.0
double division=3.5
promoted byte expression=11
mixed expression=7.5
concat=73
grouped=10
assignment target=4
assignment result=6
prefix value=5
postfix value=5
after increment=6
conditional selected=1.0
method expression=12
overload=Object
overload=String
object toString=Java
text length=4
virtual sound=woof
array element=4
var inferred int=2
wrapper arithmetic=12
short circuit=false
overflow first=-294967296
long first=4000000000
void call completed
~~~

### Checking Each Output Group

- `sum`, `greater`: arithmetic expression yields `int`, comparison expression yields `boolean`.
- Three division lines: the same values are involved, yet the **expression type at the time of division** decides whether the fractional part is kept or discarded.
- `small + 1`: the `byte` operand is promoted to `int`.
- `concat=73` vs. `grouped=10`: a `String` operand changes the meaning of `+`.
- `(assigned = 4) + 2`: assignment is a value-producing expression; prefix/postfix differ in when the update takes effect.
- `conditional selected=1.0`: the numeric `?:` expression has type `double`.
- `describe(object)` and `describe(text)`: overload chosen by **static type**.
- `pet.sound()`: overridden method executes according to the **Dog object** at runtime.
- `var inferred int=2`: `var` infers `int` from the return type of `length()`.
- `short circuit=false`: the divide-by-zero branch is not evaluated.
- Two overflow lines: the addition operator has type `int` or `long` before assignment to the `long` variable.

## 18. Common Mistakes and How to Fix Them

| Misconception / error | Cause | Correct approach |
|---|---|---|
| `2 + 3;` is a valid standalone statement | Not every expression is a statement expression | Assign, use the result, or place it in an appropriate context |
| `double avg = 7 / 2;` gives 3.5 | `int / int` division returns `int` | `(double) 7 / 2` |
| `byte result = byteA + byteB;` | Numeric promotion returns `int` | Use `int` or cast with range checks |
| `long total = intA + intB;` always avoids overflow | `int` addition happens before assignment | Widen an operand before adding |
| `"sum=" + 7 + 3` gives `sum=10` | Left-to-right `String` concatenation | `"sum=" + (7 + 3)` |
| `Object x = "Java"; x.length()` | Static type `Object` has no `length` | Declare as `String` or cast with a check |
| `var n = 1;` automatically changes to `long` when needed | `var` infers fixed `int` | Initialize with `1L` or declare as `long` |
| `Integer i = null; int x = i + 1;` | Unboxing `null` at runtime | Check for `null` first |
| `if (10)` is valid because nonzero is truthy | Java requires `boolean` | Write a condition like `10 != 0` |
| `int n = System.out.println("x");` | Method has `void` return type, returns no value | Call as a standalone statement |
| `n = 0; 10 / n` is blocked by the compiler | Types are valid, but runtime value is invalid | Check that the divisor is nonzero |
| Thinking runtime class picks overloads | Overloads resolve by static type | Read the declared types of argument expressions |
| Thinking static type prevents method overriding | Instance methods use dynamic dispatch | Keep overloading and overriding distinct |

**Debugging tip:** when an expression gives an unexpected result, analyze in order: **(1) type of each operand → (2) conversion/operator rules → (3) expression type → (4) runtime value → (5) conversion on assignment**.

## 19. Exercises with Answers

### Exercise A — division and expression type

~~~java
int a = 9;
int b = 4;
double x = a / b;
double y = (double) a / b;
System.out.println(x);
System.out.println(y);
~~~

**Answer:**

~~~text
2.0
2.25
~~~

`a / b` has type `int`; casting the first operand before dividing makes the expression `double`.

### Exercise B — numeric promotion

~~~java
byte value = 12;
var result = value + 1;
System.out.println(result);
~~~

**Answer:** prints `13`; variable `result` has type **int**, not `byte`.

### Exercise C — `+` operator and String

~~~java
System.out.println("value=" + 2 + 3);
System.out.println("value=" + (2 + 3));
~~~

**Answer:**

~~~text
value=23
value=5
~~~

### Exercise D — static type and overloading

~~~java
static void show(Object value) { System.out.println("Object"); }
static void show(String value) { System.out.println("String"); }

// In main:
Object a = "X";
String b = "X";
show(a);
show(b);
~~~

**Answer:**

~~~text
Object
String
~~~

### Exercise E — value-producing assignment expression

~~~java
int n = 1;
int x = (n = 5) * 2;
System.out.println(n);
System.out.println(x);
~~~

**Answer:**

~~~text
5
10
~~~

### Exercise F — when an expression has a type but no usable value

Why does this line fail?

~~~java
// int n = System.out.println("Hello");
~~~

**Answer:** `println` has return type `void`; the call can be used as a statement expression, but it **produces no `int` value to assign**.

## 20. End-of-Lesson Checklist

- [ ] Distinguish between Java expressions and statements.
- [ ] Know that an expression's type is determined by the compiler from operands, operators, and API signatures.
- [ ] Understand that runtime values can change even though the static type remains fixed.
- [ ] Recognize `int`, `long`, `double`, `float`, `char`, `boolean`, and `String` literals.
- [ ] Avoid confusing the receiving variable's type with the type of an intermediate computation.
- [ ] Understand numeric promotion and integer division.
- [ ] Know that comparison/logical expressions have type `boolean`; `&&`/`||` short-circuit.
- [ ] Distinguish numeric addition from `String` concatenation.
- [ ] Know that a method invocation takes the type of its return signature; `void` provides no assignable value.
- [ ] Distinguish a reference's static type from an object's runtime class.
- [ ] Understand compile-time overloading and runtime overriding.
- [ ] Know that assignments, `++`, and `--` produce expression results and side effects.
- [ ] Understand that the `?:` conditional expression is typed according to language rules.
- [ ] Know that `var` infers its static type from the initializer.
- [ ] Remember that the compiler blocks type mismatches but does not guarantee freedom from exceptions or overflow.
- [ ] Compile and run `ExpressionValueTypeDemo.java`, verifying every line of exact expected output.

**Conclusion:** Java expressions do not merely "compute a result": Java assigns them a **static type at compile time**, from which it checks operators, assignments, method calls, and member access. The actual value is computed at runtime and may depend on data, evaluated branches, or the runtime object. Understanding both layers—**static type** and **runtime value**—is foundational for reading, predicting, and debugging Java 17+ expressions.
