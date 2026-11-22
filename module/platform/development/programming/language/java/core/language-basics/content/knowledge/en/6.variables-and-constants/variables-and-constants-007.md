# `final` on Variables and the Single-Assignment Rule in Java 17+

## 1. Exact Meaning of `final` on a Variable

A regular Java variable can be reassigned if its type and scope allow it. When placing **`final`** on a declaration, the variable can receive **at most one valid assignment along each execution path**; once assigned, that variable itself cannot be reassigned.

~~~java
int normal = 10;
normal = 20; // Valid

final int limit = 10;
// limit = 20; // COMPILE ERROR: cannot assign a value to final variable limit
~~~

This applies to primitive variables such as `int` and `boolean`, as well as reference variables such as `StringBuilder`, arrays, or objects. However, **`final` locks reassignment of the variable, not making the object it points to immutable**.

| Code pattern | Meaning | Outcome |
|---|---|---|
| `int x = 1; x = 2;` | Normal variable, reassignable | Valid |
| `final int x = 1;` | Variable assigned once | Valid |
| `final int x = 1; x = 2;` | Second assignment to a final variable | Compile error |
| `final int x; x = 1;` | Declared first, first assignment later | Valid |
| `final int x; System.out.println(x);` | Read before being assigned | Compile error |
| `final StringBuilder b = new StringBuilder(); b.append("A");` | Mutating object state, not reassigning `b` | Valid |

**Dual rule:** a `final` variable must be **definitely assigned before being read** (*definitely assigned*) and **definitely unassigned before each assignment to it** (*definitely unassigned*). `javac`'s checker analyzes the program's execution paths.

## 2. Initialize Immediately or Assign Later: Blank Final

The most common style is declaring and initializing together:

~~~java
final double taxRate = 0.10;
final boolean production = true;
final String title = "Java";
~~~

Java also allows a **blank final local variable**: declaring it without an initial value, then assigning it later:

~~~java
static int calculate(boolean premium) {
    final int price;
    if (premium) {
        price = 200;
    } else {
        price = 100;
    }
    return price;
}
~~~

Although there are **two different assignment statements** in the source code, on **each run** only **one branch** executes. Thus every path to `return price` assigns the variable exactly once, so the program is valid.

~~~java
// Invalid: one path leaves price unassigned
final int price;
if (premium) {
    price = 200;
}
// System.out.println(price); // Cannot read when premium might be false
~~~

If two assignments could happen **sequentially** on the same path, the compiler rejects it:

~~~java
// Invalid:
final int number;
number = 5;
// number = 5; // Even with the same value, it is still a second assignment
~~~

**More accurate than saying "`final` must be assigned once":** it cannot be assigned **more than once on an execution path**; if its value is read, it must be guaranteed to have been assigned. For an unused blank final local that is never read, Java does not force a pointless assignment.

## 3. Loops: `final` Variables Cannot Be Repeatedly Updated

In a standard loop, the counter variable usually has to change:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

You cannot simply add `final` to `i`:

~~~java
// Invalid: i++ attempts to reassign a final variable
// for (final int i = 0; i < 3; i++) { }
~~~

A **blank final** assigned inside the body of a `while` loop is also usually invalid if the loop can run multiple times: the compiler cannot guarantee each assignment happens on a path where the variable is still unassigned.

Conversely, an **enhanced for** loop can declare a `final` element variable:

~~~java
int sum = 0;
for (final int value : new int[] {1, 2, 3}) {
    sum += value;
}
System.out.println(sum); // 6
~~~

Each iteration has an element variable for that iteration; inside the **loop body**, you cannot write `value = 99;`. You can still reassign `sum` because `sum` is not `final`.


## 4. `final` Locks Variable Reassignment, Not the Object

~~~java
final int count = 5;
// count++; // Error: attempting to reassign a primitive variable

final int[] scores = {10, 20};
scores[0] = 99; // Valid: changing an element of the array object
// scores = new int[] {30}; // Error: attempting to reassign scores
~~~

For a primitive, not being able to reassign the variable also means the primitive value stays constant. For a reference, the **variable's reference** stays fixed, while the object can still be mutable. This does not automatically provide thread safety or deep immutability; the dedicated lesson on `final` references demonstrates this with aliases, `StringBuilder`, and collections. A `final String label = null;` variable is still valid, but once assigned `null`, it cannot be reassigned.

## 5. `final` on Method Parameters and Local Variables

You can mark a parameter `final`:

~~~java
static int doubleOf(final int value) {
    // value = 7; // Compile error
    return value * 2;
}
~~~

`final` does not prevent the method from **reading** the passed-in value. It only disallows reassigning the `value` parameter inside the method body.

For a reference parameter:

~~~java
static void addMark(final StringBuilder text) {
    text.append("!");      // Valid, mutates the object
    // text = new StringBuilder(); // Invalid, reassigns the parameter
}
~~~

This is a tool to express the intent "this parameter will not be replaced". It does **not** prevent the caller from holding a reference to the same object and observing state changes.

## 6. `final` Fields: Must Finish Initialization in the Right Place

A `final` field can be initialized at its declaration site:

~~~java
class Config {
    final int maxAttempts = 3;
}
~~~

Or left blank at declaration and initialized in the constructor, commonly called a **blank final instance field**:

~~~java
class User {
    private final int id;

    User(int id) {
        this.id = id; // Constructor assigns the field for the first time
    }

    int id() {
        return id;
    }
}
~~~

**Every valid constructor must ensure uninitialized `final` fields are assigned before the constructor completes normally.** If a class has multiple constructors, initialization paths must be designed consistently; none may skip assignment or assign twice. An instance initializer can be used where appropriate, but you must not try to reassign an already initialized field.

With **`static final`**, the value can be assigned at declaration or via a **static initializer**:

~~~java
class Environment {
    static final String APP_NAME;
    static {
        APP_NAME = "Study";
    }
}
~~~

An unassigned `static final` field must be validly initialized during static initialization; it cannot wait until `main` is called to be arbitrarily assigned.

**Difference from regular fields:** a regular `int` field defaults to `0`, but a blank `final` field still must satisfy explicit assignment requirements upon completing initialization. Do not treat JVM default zeroing as an excuse to skip initializing `final` fields.

## 7. `final` Does Not Always Mean Compile-Time Constant

A value assigned once **is not necessarily a compile-time constant**:

~~~java
final int fixed = 10;                    // Constant expression: 10
final int inputLength = "hello".length();// Value from a method call
~~~

`fixed` is an example of a primitive `final` variable initialized with a **constant expression**. `inputLength`, however, requires a method call; `final` only ensures the variable is not reassigned, **it does not turn a method call into a constant expression**.

In Java, a *constant variable* has a stricter definition: a `final` variable of primitive type or `String`, initialized with a constant expression. Understanding this distinction explains why certain places requiring compile-time constants (such as traditional `case` labels) do not accept every `final` variable.

Example:

~~~java
final int ten = 10;
final int eleven = Integer.parseInt("11");

// Valid in switch:
int x = 10;
switch (x) {
    case ten -> System.out.println("TEN");
    default -> System.out.println("OTHER");
}
// Cannot use eleven as a compile-time constant case label.
~~~

Do not equate `final`, `static final`, and "immutable object": they are related concepts, but **not synonymous**.

## 8. `final` and Lambdas: Effectively Final

Java 17 allows a lambda/anonymous class to **capture** a local variable if it is declared `final` **or is effectively final** (never reassigned after its valid initialization/assignment).

~~~java
int factor = 4; // Not written as final, but never reassigned
java.util.function.IntUnaryOperator times =
        value -> value * factor;
System.out.println(times.applyAsInt(3)); // 12
~~~

Even though `factor` does not say `final`, the compiler sees it is never reassigned and allows capturing it.

If you add `factor = 5;` after the declaration, the variable is no longer effectively final and the lambda using it will fail to compile. The fix is to design fixed captured values, or if mutable state is truly needed, model an appropriate state-managing object. Do not arbitrarily wrap mutable variables in an array just to bypass the compiler check.

## 9. Standalone Runnable Java 17 Program

Create the exact file **`FinalOnceDemo.java`**:

~~~java
public final class FinalOnceDemo {
    private static final int MAX_RETRIES = 3;
    private static final String APP_NAME;

    static {
        APP_NAME = "Study";
    }

    private final int id;
    private final StringBuilder label;

    private FinalOnceDemo(int id) {
        this.id = id;
        this.label = new StringBuilder("item");
    }

    static String classify(int score) {
        final String outcome; // Blank final local
        if (score >= 50) {
            outcome = "PASS";
        } else {
            outcome = "FAIL";
        }
        return outcome;
    }

    static int twice(final int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        final int attempts = 2;
        System.out.println("attempts=" + attempts);
        System.out.println("max=" + MAX_RETRIES);
        System.out.println("app=" + APP_NAME);
        System.out.println("pass=" + classify(70));
        System.out.println("fail=" + classify(40));

        FinalOnceDemo object = new FinalOnceDemo(7);
        object.label.append("-updated"); // Mutable object
        System.out.println("id=" + object.id);
        System.out.println("label=" + object.label);

        final int[] counts = {1, 2};
        counts[0] = 9; // Not reassigning the counts variable
        System.out.println("array=" + counts[0] + "," + counts[1]);

        final StringBuilder text = new StringBuilder("A");
        text.append("B");
        System.out.println("ref=" + text);
        System.out.println("twice=" + twice(5));

        int sum = 0;
        for (final int value : new int[] {1, 2, 3}) {
            sum += value;
        }
        System.out.println("sum=" + sum);

        int factor = 4; // Effectively final: never reassigned
        java.util.function.IntUnaryOperator multiply =
                number -> number * factor;
        System.out.println("lambda=" + multiply.applyAsInt(3));
    }
}
~~~

In the directory containing the file, use **JDK 17 or later**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FinalOnceDemo.java
java -cp . FinalOnceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FinalOnceDemo.java
java -cp . FinalOnceDemo
~~~

**Expected output:**

~~~text
attempts=2
max=3
app=Study
pass=PASS
fail=FAIL
id=7
label=item-updated
array=9,2
ref=AB
twice=10
sum=6
lambda=12
~~~

Points to verify for yourself:

1. `classify` assigns once in **exactly one** of the two branches, so `final outcome` is valid.
2. `id` and `label` are instance `final` fields assigned when the constructor runs.
3. `APP_NAME` is a `static final` field assigned in the static initializer.
4. `object.label.append(...)`, `counts[0] = 9`, and `text.append(...)` **are not reassignments of `final` variables**.
5. `factor` is effectively final, so it can be used by the lambda.

This is a single self-contained example that can be saved, compiled, and run standalone; no external libraries or build projects are needed.

## 10. Typical Errors and How to Handle Them

| Symptom | Why? | How to fix? |
|---|---|---|
| `final int x = 1; x = 2;` | Second assignment | Assign only once, or remove `final` if it must change |
| `final int x; println(x);` | Reading an unassigned blank final | Definitely assign before reading |
| `final int x; if (c) x = 1; println(x);` | `c=false` branch is unassigned | Add an `else` branch / appropriate handling path |
| `final int x; x = 1; x = 1;` | Reassigning even with the same value | Remove the second assignment |
| `final int i = 0;` then `i++` | Incrementing requires reassigning `i` | Use a non-final counter variable |
| Constructor forgets to assign a blank final field | Initialization not guaranteed on all normal completion paths | Initialize the field or fix the constructor |
| `final List ...` then calling an element-adding API | Can be **valid**; only the object changes | Use an unmodifiable/immutable collection if true immutability is needed |
| Lambda uses a reassigned local variable | No longer effectively final | Extract a fixed captured value or redesign |
| `final String s = null;` then wanting to assign a string | `s` was already assigned `null` once | Choose the right value at initialization; do not use null as a placeholder |
| Using a method-local final as a constant expression when its initializer calls a method | `final` does not turn a call result into a compile-time constant | Use a constant expression where required |

An error like `cannot assign a value to final variable` usually means the compiler detected **the specific variable being reassigned**, not a prohibition on changing anything related to the object.

## 11. Exercises with Answers

### Exercise A — `final` assigned in if/else

~~~java
final String state;
if (ok) {
    state = "ON";
} else {
    state = "OFF";
}
System.out.println(state);
~~~

**Answer:** valid if `ok` is a declared boolean. Every execution path assigns `state` once before printing.

### Exercise B — distinguishing variable and object

~~~java
final StringBuilder sb = new StringBuilder("Hi");
sb.append("!");
// sb = new StringBuilder("Bye");
System.out.println(sb);
~~~

**Answer:** prints `Hi!`; `append` is valid, reassigning `sb` is invalid.

### Exercise C — is a `final` array immutable?

~~~java
final int[] values = {1, 2};
values[0] = 7;
System.out.println(values[0]);
~~~

**Answer:** prints `7`. The variable `values` cannot change its reference, but array elements can still be modified.

### Exercise D — `final` parameter

~~~java
static int plusOne(final int x) {
    // x++; // Invalid
    return x + 1;
}
~~~

**Answer:** `return x + 1;` is valid because it does not modify `x`. `x++` is invalid because it reassigns the `final` parameter.

### Exercise E — capturing in a lambda

~~~java
int factor = 3;
java.util.function.IntUnaryOperator op = x -> x * factor;
// factor = 4;
~~~

**Answer:** valid if no reassignment is added. If `factor = 4;` is uncommented, the compiler rejects the lambda capture because the variable is no longer effectively final.

## 12. Retention Checklist

- [ ] `final` forbids reassigning the **variable** after a valid assignment, not mutating the object by default.
- [ ] A blank final local can be declared first, then assigned once on each valid execution path.
- [ ] A `final` variable must be definitely assigned before being read.
- [ ] Statements `x++`, `x += 1`, and `x = x` are also reassignments.
- [ ] Enhanced for can use `final` for the element variable, unlike a counter needing `i++`.
- [ ] Blank final fields are validly initialized at declaration, in an initializer, or in the appropriate constructor.
- [ ] Distinguish a `final` variable from a **compile-time constant** and an **immutable object**.
- [ ] Understand `final` parameters and effectively final when capturing in lambdas.
- [ ] Compile/run `FinalOnceDemo.java` yourself and explain all output.

**Conclusion:** `final` on a variable guarantees **not reassigning the variable after it has been validly assigned once**. Java enforces this at compile time, including across control-flow branches and initialization paths. For references, `final` fixes the **reference value**, without automatically making the internal data immutable.