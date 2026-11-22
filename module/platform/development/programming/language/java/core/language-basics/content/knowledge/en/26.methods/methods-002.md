# Method Definition vs. Method Call — Java 17+

## 1. Two Different Operations

**Method definition** (*method declaration/definition*) is writing the name, parameter types, return type, and body to specify **how** a task will be performed. **Method invocation** (calling a method) is requesting that task to be executed at a specific location in the program.

~~~java
static void greet() {                    // DEFINITION
    System.out.println("Hello!");
}

public static void main(String[] args) {
    System.out.println("Start");
    greet();                               // CALL
    greet();                               // CALL again
    System.out.println("End");
}
~~~

**Exact stdout when running the class containing the code above:**

~~~text
Start
Hello!
Hello!
End
~~~

- The `static void greet() { ... }` part only **describes** the method; the declaration itself does not print `Hello!`.
- Each call `greet();` executes the method body **once**.
- When the `greet` body finishes, control flow returns **immediately after the call site**.
- `main` is also a method defined in code. When running an application normally, the Java launcher/JVM invokes `main` as the entry point.

**Key Takeaway:** *Definition = what the method does; call = when to run it, and with what data.*

## 2. Structure of a Method Definition

~~~java
static int add(int a, int b) {
    int result = a + b;
    return result;
}
~~~

| Component | Code | Meaning |
|---|---|---|
| Modifier | `static` | Allows calling via the class, without needing an instance |
| Return type | `int` | The return value is an `int` integer |
| Method name | `add` | The name used when calling |
| Parameter list | `int a, int b` | Two **formal parameters** with names and types |
| Method body | `{ ... }` | Statements that run when the method is called |
| Return statement | `return result;` | Returns the result and ends the call |

**Corresponding call:**

~~~java
int total = add(2, 5);
System.out.println(total);
~~~

**Exact stdout:**

~~~text
7
~~~

At the call site, `2` and `5` are **arguments**, used to initialize **parameters** `a` and `b` for that call. `add(2, 5)` is an expression whose value is `7`; `int total = ...` stores the result into a variable.

Do not write the type keyword `int` to declare argument types at the call site:

~~~java
// WRONG: add(int 2, int 5);
// RIGHT: add(2, 5);
~~~

## 3. Defining Alone Does Not Mean Automatic Execution

~~~java
public final class DefineOnlyDemo {
    static void announce() {
        System.out.println("ANNOUNCE");
    }

    public static void main(String[] args) {
        System.out.println("MAIN");
        // announce() is never called.
    }
}
~~~

**Exact stdout:**

~~~text
MAIN
~~~

Compiling with `javac` checks the program and produces the class file, **without calling** `announce()`. Running `java` into `main` also does not automatically call `announce()` when there is no invocation statement.

Only if you add `announce();` inside `main` will the line `ANNOUNCE` appear at runtime. This rule applies to both `void` methods and value-returning methods.

Exceptions related to **class initialization and startup mechanisms** do not change this rule: static initializers/constructors are different mechanisms, not every method you define running automatically.

## 4. Control Flow During a Method Call

~~~mermaid
flowchart TD
    A["main: before the call"] --> B["Evaluate arguments"]
    B --> C["Invoke method and create call context"]
    C --> D["Execute method body"]
    D --> E["return value or finish void"]
    E --> F["Return to call site"]
    F --> G["Continue with next statement"]
~~~

Example:

~~~java
static int square(int x) {
    System.out.println("inside square");
    return x * x;
}

public static void main(String[] args) {
    System.out.println("before");
    int value = square(3);
    System.out.println("result=" + value);
    System.out.println("after");
}
~~~

**Exact stdout:**

~~~text
before
inside square
result=9
after
~~~

The line `inside square` appears between `before` and `result` because the method body runs **during the evaluation of the call**. After `return`, the assignment `value = 9` completes and `main` executes the remaining statements.

Each call normally has its own set of parameters and local variables. Multiple consecutive calls do not share local variables just because they use the same method name.

## 5. Arguments, Parameters, and Evaluation Order

Java evaluates arguments in **left-to-right** order before the method body is invoked.

~~~java
static int trace(String tag, int value) {
    System.out.println("argument " + tag);
    return value;
}

static int sum(int left, int right) {
    System.out.println("inside sum");
    return left + right;
}

// Inside main:
int result = sum(trace("LEFT", 2), trace("RIGHT", 5));
System.out.println("result=" + result);
~~~

**Exact stdout:**

~~~text
argument LEFT
argument RIGHT
inside sum
result=7
~~~

Execution flow:

1. Evaluate `trace("LEFT", 2)`, yielding `2`.
2. Evaluate `trace("RIGHT", 5)`, yielding `5`.
3. Call `sum(2, 5)`, execute the body of `sum`, and return `7`.
4. Assign `result = 7`, then print the result.

**Common mistake:** thinking `sum` starts running before the argument expressions are evaluated.

## 6. `return` and `void` Methods

Two common forms:

~~~java
static int doubleValue(int value) {
    return value * 2;
}

static void printMessage(String text) {
    System.out.println(text);
}
~~~

How to call:

~~~java
int number = doubleValue(4);
printMessage("value=" + number);
~~~

**Exact stdout:**

~~~text
value=8
~~~

- A method of type `int` must produce an appropriate return value on every normally completing path according to Java rules; `return value;` also **ends** the method.
- A `void` method provides no value to assign; it can end when execution reaches the end of the body, or use `return;` to exit early.
- You can call a value-returning method as a statement and ignore its value: `doubleValue(4);` is valid, though you should usually check why the result is unused.
- `int x = printMessage("Hi");` **does not compile**, because a `void` method does not return an `int`.

`System.out.println` is also a **method call**, not syntax for creating a new method.

## 7. `static` and Instance Methods

A **`static` method** belongs to the class and can be called through the class name:

~~~java
Math.max(3, 7);
~~~

An **instance method** is called on an object:

~~~java
String word = "Java";
System.out.println(word.length());
~~~

Example of a class with state:

~~~java
static final class Counter {
    private int count;

    int increase(int step) {
        count += step;
        return count;
    }
}

// Inside main:
Counter counter = new Counter();
System.out.println(counter.increase(2));
System.out.println(counter.increase(3));
~~~

**Exact stdout:**

~~~text
2
5
~~~

`increase` is only a definition inside class `Counter`. `new Counter()` creates an object with `count = 0`; only the **call** `counter.increase(...)` increments `count`.

Calling an instance method requires an appropriate object. In a `static` context, you cannot write `increase(2)` as if it were a static method of the outer class when there is no `Counter` object.

## 8. Methods Can Call Other Methods

~~~java
static int twice(int value) {
    return value * 2;
}

static int fourfold(int value) {
    int first = twice(value);
    return twice(first);
}
~~~

Calling `fourfold(3)` causes `twice(3)` to return 6, then `twice(6)` returns 12. Java executes the calls sequentially and returns to the calling method after each result.

**Note:** defining `twice` and `fourfold` does not automatically trigger those calls. Only when `fourfold(3)` is actually called do the inner calls take place.

If methods keep calling each other endlessly without a stopping condition (infinite recursion), the program can cause a `StackOverflowError`. This is an issue when **executing calls**, not merely from having multiple definitions.

## 9. Effect of a Call Under Pass-by-Value and References

A call evaluates argument expressions and uses the results to initialize **separate parameters**. Modifying a primitive parameter does not change the caller's variable:

~~~java
static void replaceLocal(int value) { value = 100; }
int original = 5;
replaceLocal(original);
System.out.println(original); // 5.
~~~

For object parameters, the copied value is a **reference**: two variables can point to the same mutable object.

~~~java
static void addMark(StringBuilder text) { text.append("!"); }
StringBuilder message = new StringBuilder("Hi");
addMark(message);
System.out.println(message); // Hi!
~~~

`append` modifies the **shared object**; by contrast, `text = new StringBuilder("Other")` only reassigns the parameter variable, not the caller's variable. The main point of this lesson is that **a method body only produces effects when it is called**. The parameters/arguments lesson and the pass-by-value lesson analyze scope, aliasing, arrays, and `final` in greater depth.


## 10. The Same Name Can Lead to Different Method Bodies

~~~java
static String describe(int value) { return "int:" + value; }
static String describe(String value) { return "String:" + value; }

System.out.println(describe(7));    // int:7.
System.out.println(describe("Hi")); // String:Hi.
~~~

Two **definitions** have the same name but different parameter types; each **call** is resolved by the compiler to the matching overload based on the argument expression types. Changing only the return type or parameter variable names does not create a new overload.

This lesson focuses on the relationship *definition → call selection → body execution*. The deep-dive overloading lesson will explain signatures, type widening, boxing, varargs, ambiguous `null`, and generic erasure.


## 11. Complete Java 17+ Program

Create the file with the exact name **`MethodDefinitionCallDemo.java`**:

~~~java
public final class MethodDefinitionCallDemo {
    private MethodDefinitionCallDemo() {}

    static int square(int number) {
        System.out.println("body square " + number);
        return number * number;
    }

    static void greet(String name) {
        System.out.println("body greet " + name);
    }

    static int trace(String tag, int value) {
        System.out.println("arg " + tag + "=" + value);
        return value;
    }

    static int add(int left, int right) {
        System.out.println("body add " + left + "+" + right);
        return left + right;
    }

    static int twice(int value) {
        System.out.println("body twice " + value);
        return value * 2;
    }

    static int fourfold(int value) {
        System.out.println("body fourfold start");
        int first = twice(value);
        int result = twice(first);
        System.out.println("body fourfold end");
        return result;
    }

    static String describe(int value) {
        return "int:" + value;
    }

    static String describe(String value) {
        return "String:" + value;
    }

    static void replaceLocal(int value) {
        value = 100;
        System.out.println("inside local=" + value);
    }

    static void appendMark(StringBuilder builder) {
        builder.append("!");
        System.out.println("inside builder=" + builder);
    }

    static final class Counter {
        private int count;

        int increase(int step) {
            count += step;
            System.out.println("body increase count=" + count);
            return count;
        }
    }

    public static void main(String[] args) {
        System.out.println("main begin");

        int first = square(3);
        System.out.println("square result=" + first);
        System.out.println("square second=" + square(4));

        greet("Mai");

        int total = add(trace("left", 2), trace("right", 5));
        System.out.println("add result=" + total);

        System.out.println("fourfold result=" + fourfold(3));

        System.out.println("overload int=" + describe(7));
        System.out.println("overload String=" + describe("Hi"));

        int original = 5;
        replaceLocal(original);
        System.out.println("outside original=" + original);

        StringBuilder builder = new StringBuilder("Hi");
        appendMark(builder);
        System.out.println("outside builder=" + builder);

        Counter counter = new Counter();
        System.out.println("counter first=" + counter.increase(2));
        System.out.println("counter second=" + counter.increase(3));

        System.out.println("main end");
    }
}
~~~

**Requirements:** JDK 17 or later; open a terminal in the directory containing the file. No Maven, Gradle, libraries outside the JDK, or preview features needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 MethodDefinitionCallDemo.java
java -cp . MethodDefinitionCallDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\MethodDefinitionCallDemo.java
java -cp . MethodDefinitionCallDemo
~~~

### Exact expected stdout

~~~text
main begin
body square 3
square result=9
body square 4
square second=16
body greet Mai
arg left=2
arg right=5
body add 2+5
add result=7
body fourfold start
body twice 3
body twice 6
body fourfold end
fourfold result=12
overload int=int:7
overload String=String:Hi
inside local=100
outside original=5
inside builder=Hi!
outside builder=Hi!
body increase count=2
counter first=2
body increase count=5
counter second=5
main end
~~~

**What to observe:** the line `body square 3` appears before `square result=9`, proving the body runs at **call time**. The two `arg left/right` lines appear before `body add`. `fourfold` calls `twice` twice; variable `original` remains 5 after being passed to an `int` parameter; the `StringBuilder` object changes its contents through the method. `Counter` keeps its state because the two calls are performed on the **same object**.

## 12. Common Mistakes

| Mistake | Why is it wrong? | How to fix |
|---|---|---|
| Writing a method and waiting for it to run automatically | A definition is not a call | Call the exact name with `()` where needed |
| Confusing `add(int a, int b)` with `add(2, 3)` | One declares parameters; the other supplies arguments | Distinguish definition syntax and call syntax |
| Omitting `()` when wanting to execute | A standalone method name is not a normal Java call | Write `greet();` |
| Calling with wrong argument count/types | Compilation error | Match the appropriate signature/overload |
| Assigning the result of a `void` method | `void` produces no value | Call standalone, do not assign |
| Thinking `return` only prints or stores a value | `return` ends the method and returns to the caller | Use the result in an expression/assignment |
| Calling an instance method like a static method | Missing an object | Create an instance then call `obj.method()` |
| Thinking assigning to an `int` parameter changes the caller's variable | Java passes arguments by value | Return a new value or update data via API |
| Thinking `StringBuilder` is copied automatically when passed | Reference value points to the same mutable object | Understand mutation vs. parameter reassignment |
| Differing only by return type to overload | Does not create a different signature | Change parameter count/types/order appropriately |
| Assuming `javac` executes all methods | The compiler checks and generates class files | Use `java` and actual calls to run |
| Assuming two definitions with same name/parameters are allowed | Duplicate signature declaration | Rename or create a valid overload |

## 13. Exercises with Answers

### A — Definition and Call

~~~java
static void ping() {
    System.out.println("PING");
}
public static void main(String[] args) {
    System.out.println("START");
}
~~~

**Question:** when running the class, does it print `PING`? **Answer:** no; it only prints `START`. To print `PING`, add `ping();` into `main`.

### B — Counting Calls

~~~java
static void hi() { System.out.println("HI"); }
public static void main(String[] args) {
    hi();
    hi();
}
~~~

**Exact stdout:**

~~~text
HI
HI
~~~

Defined once, but the body executes **twice**.

### C — Parameters and Arguments

~~~java
static int subtract(int a, int b) {
    return a - b;
}
// Inside main:
System.out.println(subtract(10, 3));
~~~

**Answer:** `a` and `b` are parameters; `10` and `3` are arguments; stdout `7`.

### D — `void` or `int`?

~~~java
static void announce() {
    System.out.println("READY");
}
// int n = announce(); // Is this valid?
~~~

**Answer:** no; `announce()` does not return a value. Use `announce();` as a standalone statement.

### E — Objects and State

~~~java
Counter counter = new Counter();
System.out.println(counter.increase(1));
System.out.println(counter.increase(2));
~~~

**Answer:** instance method `increase` updates the same `count` field; with the Counter class from the main program, stdout includes `body increase count=1`, `1`, `body increase count=3`, `3` in order.

## 14. Checklist and Conclusion

- [ ] Distinguish **defining** and **calling** a method.
- [ ] Know how to declare modifier, return type, name, and parameters.
- [ ] Call with `()` and the correct argument list.
- [ ] Understand that a method body runs only when a call is executed.
- [ ] Know `return` returns a result and transfers back to the caller; `void` returns no value.
- [ ] Understand left-to-right argument evaluation order.
- [ ] Distinguish `static` and instance methods.
- [ ] Know that methods can call other methods.
- [ ] Understand pass-by-value, including object reference values.
- [ ] Recognize overloading and signature/method mismatch errors.
- [ ] Run `MethodDefinitionCallDemo.java` with Java 17+ and verify exact stdout.

**Conclusion:** A method definition is a **description of reusable behavior**; a method call **executes that behavior** with concrete arguments, then receives a result or continues after a `void` method. Understanding this difference is foundational for reading Java execution flow accurately.