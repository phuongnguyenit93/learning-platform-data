# Evaluation Order of the Receiver and Arguments in Java

## Learning Objectives

After this lesson, you will be able to:

- Identify the **receiver object** (*receiver* or *target object*) and **argument expressions** in a Java method call.
- Explain the runtime evaluation rule: **determine/evaluate the receiver expression first (if necessary), then evaluate the arguments from left to right, and only then transfer control into the method body**.
- Accurately predict the outcome when the receiver expression or arguments have side effects: printing to the console, incrementing a counter, assigning variables, or mutating objects.
- Explain what happens if the receiver is `null`, the receiver expression throws an exception, or an argument fails to evaluate.
- Recognize the `static` case where there is no receiver object at runtime, yet calling a static method via an expression can still cause that expression to be evaluated.
- Distinguish **expression evaluation order** from **compile-time type checking/overload resolution**, **dynamic dispatch**, and **execution order inside the method body**.
- Write code that minimizes unpredictable side effects and use intermediate variables to express the intended order.

## 1. Calls with a Receiver and Argument List

In the Java expression:

~~~java
service.process(loadId(), calculateAmount());
~~~

- `service` is the expression that determines the **receiver**, that is, the object on which the instance method `process` is called.
- `loadId()` is the **first argument expression**.
- `calculateAmount()` is the **second argument expression**.
- `process` is the method selected according to the language rules and executed after the required components have been evaluated.

This is **illustrative code**, not a standalone runnable program: to compile it, there must be a `service` variable of an appropriate type, the methods `loadId()` and `calculateAmount()`, and the `process` signature.

An example of a similar call where the receiver is a more complex expression:

~~~java
findService().process(loadId(), calculateAmount());
~~~

Here, `findService()` is the receiver expression: it must be evaluated to obtain a reference value **before** Java begins evaluating `loadId()` and `calculateAmount()` according to the rules of method invocation.

**Rule of thumb:** for an instance method whose receiver is an expression, the conceptual sequence is **receiver → argument 1 → argument 2 → ... → method execution**. If a step terminates abnormally due to an exception, subsequent steps may not occur.

## 2. What Order Does Java Specify?

According to the Java Language Specification (JLS), section **15.12.4 — Run-Time Evaluation of Method Invocation**, the runtime method invocation process is described sequentially:

1. **Compute Target Reference (If Necessary)**: compute the receiver/target reference when the invocation form requires it; the receiver expression is evaluated before the arguments.
2. **Evaluate Arguments**: evaluate the argument expressions strictly in **left-to-right** order; the computed values are used for the formal parameters.
3. **Check Accessibility of Type and Method** at runtime in the cases specified by the specification.
4. **Locate Method to Invoke**: determine the corresponding method implementation; for an instance invocation, a `null` target causes a `NullPointerException` at this appropriate stage.
5. **Create Frame, Synchronize, Transfer Control**: perform the necessary steps before entering the method body.

From the perspective of writing application Java, you usually only need three main points: **compute the receiver first → evaluate all arguments in sequence → begin invoking the implementation**. This sequence is mandated by the language and cannot be arbitrarily reordered by the compiler or JIT in a way that changes the observable behavior of a valid single-threaded program.

**Distinguishing phases:** the compiler has already analyzed types and selected the method at the source level according to overload rules before the program runs. Printing a log line from `findService()`, reading variable values, or throwing an exception when evaluating an argument only happens **at runtime**.

An additional note on terminology: a call written with a simple name such as `execute(x)`, with `this.execute(x)`, with `TypeName.staticMethod(x)`, or with `super.execute(x)` has different receiver forms. Not every call has to execute an explicit receiver-producing expression; the left-to-right principle applies to whichever expressions need to be evaluated in the corresponding call.

## 3. Complete Java 17+ Example: Receiver First, Arguments Left to Right

Save the file **`EvaluationOrderDemo.java`**:

~~~java
public class EvaluationOrderDemo {
    static final class Worker {
        private final String name;

        Worker(String name) {
            this.name = name;
        }

        void execute(int first, int second) {
            System.out.println("method " + name + " received " + first + "," + second);
        }
    }

    static Worker createReceiver() {
        System.out.println("1. receiver");
        return new Worker("W");
    }

    static int argument(String label, int value) {
        System.out.println(label);
        return value;
    }

    public static void main(String[] args) {
        createReceiver().execute(
                argument("2. first argument", 10),
                argument("3. second argument", 20)
        );
        System.out.println("4. after invocation");
    }
}
~~~

Compile and run from the directory containing the file, with JDK 17 or higher:

~~~bash
javac EvaluationOrderDemo.java
java EvaluationOrderDemo
~~~

**Exact stdout** output:

~~~text
1. receiver
2. first argument
3. second argument
method W received 10,20
4. after invocation
~~~

Why is the output in this order?

1. Java must evaluate `createReceiver()` to obtain a reference to the `Worker("W")` object. Therefore, the line `1. receiver` appears first.
2. Java evaluates `argument("2. first argument", 10)`, prints the second line, and gets the result `10`.
3. Java evaluates `argument("3. second argument", 20)`, prints the third line, and gets the result `20`.
4. After obtaining the argument values, Java executes `execute(10,20)` on the `Worker("W")` object. Only then does the method body print the line `method W received 10,20`.
5. The call completes normally, and `main` continues and prints `4. after invocation`.

This is a **behaviorally mandated order**. Changing the written position of the two `argument(...)` calls will change their evaluation order.

### 3.1. Do Not Confuse Parameters with Argument Expressions

In the declaration `void execute(int first, int second)`, `first` and `second` are **formal parameters**. Meanwhile, the `argument(...)` calls are **argument expressions**. The expressions are evaluated completely before their values are passed into the parameters. The body of `execute` receives the two values `10` and `20`; it does not re-invoke the expressions that produced those values.

### 3.2. An Argument Can Be a Nested Expression

For example:

~~~java
worker.execute(convert(load()), other());
~~~

Java evaluates the receiver expression `worker`, then completes the entire first argument expression `convert(load())` (including the nested call `load()`) before starting the second argument expression `other()`. Inside the first argument expression, Java's expression evaluation rules continue to apply; there is no interleaving such as “half of the first argument, half of the second argument”.

This is an **illustrative snippet** requiring the corresponding methods and data types; it is not a standalone runnable file.

## 4. The Receiver Is Determined Before Arguments Modify Variables

A subtle case: a reference variable can be reassigned **while evaluating an argument**, yet the receiver computed beforehand will remain the original reference.

Save **`ReceiverSnapshotDemo.java`**:

~~~java
public class ReceiverSnapshotDemo {
    static final class Box {
        final String label;

        Box(String label) {
            this.label = label;
        }

        void describe(Box other) {
            System.out.println("receiver=" + this.label
                    + ", argument=" + other.label);
        }
    }

    public static void main(String[] args) {
        Box current = new Box("OLD");
        current.describe(current = new Box("NEW"));
        System.out.println("current variable=" + current.label);
    }
}
~~~

Run:

~~~bash
javac ReceiverSnapshotDemo.java
java ReceiverSnapshotDemo
~~~

Output:

~~~text
receiver=OLD, argument=NEW
current variable=NEW
~~~

Steps that occur:

1. Java evaluates `current` **to the left of `.describe`**, retaining the reference value to the `Box("OLD")` object as the receiver of **the call being executed**.
2. Java begins evaluating the argument `current = new Box("NEW")`; the assignment makes **the variable `current`** point to the new object, and the assignment expression returns the new reference to serve as the argument.
3. The body of `describe` runs on the **OLD** receiver, while the parameter `other` receives the **NEW** object.
4. After the call, the `current` variable in `main` still references NEW.

This is not a phenomenon of “Java saving a snapshot of the entire object”. Java only retains **the already-determined receiver reference value**. If the OLD object has its state mutated via another reference while evaluating an argument, the method can still observe the new state of that same OLD object. Clearly distinguish **retaining a reference** from **copying an object**.

### 4.1. Example with `String` and Assignment in an Argument

~~~java
String text = "one";
boolean starts = text.startsWith(text = "two");
System.out.println(starts);
System.out.println(text);
~~~

This is a **snippet placed inside a method**, not a standalone program. Result:

~~~text
false
two
~~~

The receiver `text` of `startsWith` is evaluated while it is still `"one"`; the argument expression `text = "two"` runs afterward, so `startsWith` checks whether `"one"` starts with `"two"` (resulting in `false`). After the call, the `text` variable holds a reference to `"two"`.

This example is also used by the JLS to illustrate determining the target reference before evaluating arguments.

## 5. If the Receiver Is `null`, Arguments Are Still Evaluated Before Throwing NPE

A very common misconception is that the JVM will immediately throw a `NullPointerException` upon encountering `nullReceiver.method(argument())` and skip `argument()`. For a **normal instance method invocation**, the standard procedure is: compute the receiver (which may evaluate to `null`), **then evaluate the arguments**, and then check the receiver reference when locating the method to invoke. Therefore, side effects of the arguments can still appear **before** the NPE.

Save **`NullReceiverDemo.java`**:

~~~java
public class NullReceiverDemo {
    static final class Handler {
        void handle(int code, String label) {
            System.out.println("method body");
        }
    }

    static Handler missing() {
        System.out.println("receiver evaluated");
        return null;
    }

    static int first() {
        System.out.println("first argument evaluated");
        return 1;
    }

    static String second() {
        System.out.println("second argument evaluated");
        return "ready";
    }

    public static void main(String[] args) {
        try {
            missing().handle(first(), second());
        } catch (NullPointerException expected) {
            System.out.println("caught NullPointerException");
        }
    }
}
~~~

Run:

~~~bash
javac NullReceiverDemo.java
java NullReceiverDemo
~~~

Output:

~~~text
receiver evaluated
first argument evaluated
second argument evaluated
caught NullPointerException
~~~

The line `method body` **does not appear** because `handle` is not executed on a `null` receiver. However, `first()` and `second()` **did run** before the exception was thrown.

**Boundary of this rule:** if an error arises **during the evaluation of the receiver expression itself**, Java stops right at that error and does not begin evaluating arguments. For example, if `missing()` itself throws an exception instead of returning `null`, the arguments will not be evaluated. `null` being returned normally and an expression throwing an exception are **two different situations**.

## 6. An Exception in the Receiver or an Argument Halts Evaluation of the Rest

Java's execution rules include the concept of **abrupt completion**: if an expression throws an exception (or terminates abnormally according to the applicable rules) while being evaluated, the subsequent parts that depend on that expression will not be evaluated in the invocation at hand.

### 6.1. Receiver Throws an Exception: Arguments Do Not Run

Save **`ReceiverFailureDemo.java`**:

~~~java
public class ReceiverFailureDemo {
    static final class Worker {
        void run(int value) {
            System.out.println("method body");
        }
    }

    static Worker target() {
        System.out.println("receiver begins");
        throw new IllegalStateException("receiver failed");
    }

    static int argument() {
        System.out.println("argument begins");
        return 10;
    }

    public static void main(String[] args) {
        try {
            target().run(argument());
        } catch (IllegalStateException expected) {
            System.out.println("caught: " + expected.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac ReceiverFailureDemo.java
java ReceiverFailureDemo
~~~

Output:

~~~text
receiver begins
caught: receiver failed
~~~

`argument begins` and `method body` do not appear because the evaluation of `target()` is interrupted before a receiver is obtained.

### 6.2. Second Argument Throws an Exception: Third Argument Does Not Run

Save **`ArgumentFailureDemo.java`**:

~~~java
public class ArgumentFailureDemo {
    static final class Target {
        void accept(int a, int b, int c) {
            System.out.println("method body");
        }
    }

    static Target target() {
        System.out.println("receiver");
        return new Target();
    }

    static int first() {
        System.out.println("argument 1");
        return 1;
    }

    static int second() {
        System.out.println("argument 2");
        throw new IllegalArgumentException("bad argument");
    }

    static int third() {
        System.out.println("argument 3");
        return 3;
    }

    public static void main(String[] args) {
        try {
            target().accept(first(), second(), third());
        } catch (IllegalArgumentException expected) {
            System.out.println("caught: " + expected.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac ArgumentFailureDemo.java
java ArgumentFailureDemo
~~~

Output:

~~~text
receiver
argument 1
argument 2
caught: bad argument
~~~

Java computed the receiver, finished evaluating the first argument, and then started the second argument. When `second()` throws `IllegalArgumentException`, Java **does not call `third()`** and **does not enter the `accept` body**. Side effects that already occurred from the receiver and the first argument are not automatically rolled back.

### 6.3. Summary Table of Cases

| Scenario | Is the receiver evaluated? | Are the arguments evaluated? | Does the instance method body run? |
| --- | --- | --- | --- |
| Receiver and arguments all succeed, receiver is not `null` | Yes, if a receiver expression is present | In left → right order | Yes |
| Receiver expression throws an exception | Started, then failed | No | No |
| Receiver returns `null` normally | Yes | Yes, unless an argument itself causes an error | No; after evaluating arguments, an NPE will occur |
| First argument throws an exception | Succeeded earlier | Argument 1 starts and fails; subsequent arguments do not run | No |
| Second argument throws an exception | Succeeded earlier | Argument 1 completes, argument 2 fails, subsequent arguments are skipped | No |
| All arguments complete, but the method body throws an exception | Yes | All complete | Yes, then terminates abnormally |

The table assumes a **normal instance method** call with no other runtime errors such as linkage errors. The “null receiver causes NPE” entry should not be applied to `static` method calls because a static method does not need a receiver instance.

## 7. `static` Calls: With or Without a Receiver Expression?

When calling directly via the **class name**:

~~~java
Math.max(computeA(), computeB());
~~~

Java does not need a `Math` object at runtime; `Math.max` is a static method. The compiler determines that this is a static call, and then the expressions `computeA()` and `computeB()` are evaluated from left to right.

Java still **allows the syntax of calling a static method through an expression** of an appropriate type, even though this is misleading and usually triggers an IDE warning. In that form, the expression to the left of the dot **is still evaluated** to preserve side effects; the resulting reference value is not used as a receiver for the static method. Even a `null` result does not cause an NPE solely from calling the static method.

Save **`StaticInvocationDemo.java`**:

~~~java
public class StaticInvocationDemo {
    static final class Utility {
        static void report(int number) {
            System.out.println("static body=" + number);
        }
    }

    static Utility source() {
        System.out.println("source expression");
        return null;
    }

    static int value() {
        System.out.println("argument expression");
        return 7;
    }

    public static void main(String[] args) {
        source().report(value());
        Utility.report(8);
    }
}
~~~

Run:

~~~bash
javac StaticInvocationDemo.java
java StaticInvocationDemo
~~~

Output:

~~~text
source expression
argument expression
static body=7
static body=8
~~~

`source().report(value())` evaluates `source()` before `value()`. Even though `source()` returns `null`, the static `report` call still runs. This is a consequence of **the method being resolved as static at compile time**; there is no dynamic dispatch through a `null` receiver.

**Recommended style:** always call static methods via the **class name**, such as `Utility.report(8)`, so readers do not assume the method requires an object. Do not deliberately call a static method through an expression just to rely on that expression's side effects.

## 8. Calls on `this`, `super`, and Short Method Names

Not every call has a complex receiver expression:

~~~java
process(first(), second());
this.process(first(), second());
super.process(first(), second());
~~~

These are three **illustrative patterns** in an appropriate class/method context; the `super.process(...)` line is only valid where there is a suitable method accessible via `super`. When there is an instance invocation of the form `process(...)`, the receiver can be implicitly determined from `this` based on context; `this.process(...)` states it explicitly. `super.process(...)` has a mechanism to select the superclass implementation according to Java's rules.

Even without a `findReceiver()` call preceding it, **the argument expressions are still evaluated from left to right**. Do not confuse identifying the receiver with “running the method body”: code inside the method still begins after the arguments finish.

For a constructor `new Item(a(), b())`, the argument expressions are also evaluated from left to right before the constructor body receives the values. A constructor is not a normal instance method; object allocation, calling the superclass constructor, and initializers have their own rules. Therefore, do not mechanically copy the statement “null receiver is checked after arguments” to constructor syntax.

## 9. Side Effects in Arguments: the `++` Operator, Assignments, and References

A common source of bugs is placing multiple expressions that **both read and modify** the same variable in an argument list.

For example:

~~~java
static void show(int first, int second, int third) {
    System.out.println(first + "," + second + "," + third);
}
~~~

Inside a method where `int x = 0;`, the call:

~~~java
show(x++, ++x, x);
System.out.println("x=" + x);
~~~

prints:

~~~text
0,2,2
x=2
~~~

Reason:

1. `x++` returns the old value `0`, **and then** increments `x` to `1`.
2. `++x` increments `x` to `2`, **and then** returns `2`.
3. The third argument reads the current `x`, which is `2`.
4. The `show` method receives the **evaluated values** `0,2,2`.

Java defines the order, so the result is not “undefined behavior” simply because there are multiple `++` operators; however, this code is **hard to read and error-prone**. Using intermediate variables is clearer:

~~~java
int x = 0;
int first = x++;
int second = ++x;
int third = x;
show(first, second, third);
~~~

The two snippets describe the same sequence when placed in separate scopes with the initial state `x = 0`. Do not combine both verbatim into the same block since they both declare `x`.

### 9.1. Reference Evaluation and Mutating Object Contents

Suppose a method takes a `StringBuilder`, and the arguments can mutate that `StringBuilder` object itself. Java evaluates **reference values** in order; however, **the object's state** can be modified by a subsequent argument. For example:

~~~java
static void view(StringBuilder buffer, String snapshot) {
    System.out.println(buffer + " | " + snapshot);
}
~~~

Suppose the code inside a method is:

~~~java
StringBuilder text = new StringBuilder("A");
view(text, text.append("B").toString());
~~~

The output is:

~~~text
AB | AB
~~~

The first argument is evaluated first, but it only holds a **reference** to `text`, without copying the content `"A"`. The second argument calls `append("B")`, mutating the same object into `"AB"` and then creating the `String` snapshot `"AB"`. When the body of `view` runs, `buffer` still points to the modified `StringBuilder` object.

**Takeaway:** “arguments are evaluated from left to right” does not mean the entire state of objects is frozen as soon as each argument is evaluated.

## 10. Varargs Also Preserves Expression Order

With a variable-length parameter `String... items`, the **actual argument expressions** are still evaluated in the order they appear. When the call is processed as variable-arity, Java collects the corresponding values into an array to pass to the final parameter.

Save **`VarargsOrderDemo.java`**:

~~~java
public class VarargsOrderDemo {
    static String label(String name) {
        System.out.println("evaluate " + name);
        return name;
    }

    static void join(String... items) {
        System.out.println("joined=" + String.join("-", items));
    }

    public static void main(String[] args) {
        join(label("A"), label("B"), label("C"));
    }
}
~~~

Compile/run:

~~~bash
javac VarargsOrderDemo.java
java VarargsOrderDemo
~~~

Output:

~~~text
evaluate A
evaluate B
evaluate C
joined=A-B-C
~~~

Using varargs does not cause Java to evaluate the `label(...)` calls in parallel or reverse their order. Passing **a single argument that is already an array**, such as `join(new String[] {"A","B"})`, has a different invocation form with respect to array creation, yet still only one argument expression is evaluated in that call.

There is no need to speculate on memory layout details of the temporary array to explain the observable order of the `label` calls.

## 11. Do Not Confuse Evaluation Order with Overload Resolution and Dynamic Dispatch

Three phases/concepts to keep separate:

| Aspect | When does it primarily occur? | Example |
| --- | --- | --- |
| Determining the matching overload | At **compile time**, based on static types and method applicability rules | Choosing `print(Object)` vs. `print(String)` |
| Evaluating the receiver and argument expressions | At **runtime**, in the order specified by the JLS | `provider().print(createValue())` |
| Selecting the overridden implementation | At **runtime** for instance calls requiring dynamic dispatch | A variable of type `Base` pointing to a `Derived` object, calling an overridden method |

Overloading does not mean Java has to **run all the argument expressions speculatively** to see which method fits. The compiler determines the method from types and expression structure, without needing to execute `createValue()` multiple times. A normal call evaluates the receiver expression and the required arguments strictly according to runtime rules, never repeating them just to decide the overload.

Standalone runnable example **`DispatchOrderDemo.java`**:

~~~java
public class DispatchOrderDemo {
    static class Base {
        void show(Object value) {
            System.out.println("Base.show(Object)");
        }
    }

    static class Derived extends Base {
        @Override
        void show(Object value) {
            System.out.println("Derived.show(Object)");
        }

        void show(String value) {
            System.out.println("Derived.show(String)");
        }
    }

    static Base receiver() {
        System.out.println("receiver");
        return new Derived();
    }

    static String argument() {
        System.out.println("argument");
        return "text";
    }

    public static void main(String[] args) {
        receiver().show(argument());
    }
}
~~~

Compile/run:

~~~bash
javac DispatchOrderDemo.java
java DispatchOrderDemo
~~~

Output:

~~~text
receiver
argument
Derived.show(Object)
~~~

Explanation:

1. `receiver()` is evaluated first and has a **declared return type of `Base`**, even though the actual returned object is `Derived`.
2. The set of applicable overloads at compile time is searched on type `Base`; therefore, the selected signature is `show(Object)`, not the `show(String)` overload declared only in `Derived`.
3. `argument()` is evaluated next and produces a value of type `String`, which is compatible with `Object`.
4. When calling the selected instance method, dynamic dispatch resolves to the **overridden `Derived.show(Object)`** and prints the last line.

You cannot deduce “the runtime object is Derived + the runtime argument is String, so it automatically calls Derived.show(String)”. Overload resolution and dynamic dispatch are two distinct mechanisms.

## 12. Distinguishing Evaluation Rules from Execution Order Across Multiple Threads

The evaluation order rules of **a method invocation expression within a single thread** do not guarantee that all logs from **multiple concurrently running threads** will appear in a single global order. If another worker thread also prints to the console, lines from independent activities may interleave according to scheduling.

What is mandatory here is that Java must preserve **the receiver and argument evaluation semantics** of the same call. Having shared data across threads is further governed by the Java Memory Model, synchronization, and *happens-before* rules; that is a separate topic. Do not use interleaved print output from multiple threads to conclude that the language permits freely reordering side effects within the same call.

Similarly, the compiler/JIT may optimize pure computations as long as the observable result remains consistent with Java's semantics. “Left-to-right evaluation” should not be interpreted as requiring every single operation to always map to a CPU instruction in exact source-code order.

## 13. Common Reasoning Mistakes

| Misconception | What is true |
| --- | --- |
| “Arguments are evaluated before the receiver.” | The expression determining the receiver, when needed, is evaluated **before** the arguments. |
| “If the receiver is null, no arguments run.” | For a normal instance invocation, arguments are still evaluated before a null receiver causes an NPE at the invoke step. |
| “If the receiver throws an exception, the arguments still run.” | A failing receiver halts the call; arguments that have not started are not evaluated. |
| “A failing argument does not affect subsequent arguments.” | When an argument completes abnormally, subsequent arguments do not run; the method body is not invoked. |
| “Parameters are expressions executed inside the method.” | **Argument** expressions run first; parameters receive the values passed in by the call. |
| “Reassigning the receiver variable in an argument changes the receiver of the same call.” | The previously computed target reference is retained for the current call; the assignment only changes the variable afterward. |
| “Evaluating a reference saves a copy of the object's contents.” | Only the reference value is used; subsequent arguments can still modify the referenced object. |
| “Java is allowed to reorder arguments freely for optimization.” | Java must preserve observable semantics and side effects according to the left-to-right rule. |
| “Calling a static method on null always throws an NPE.” | A static method does not need a receiver instance; if the syntax is valid and the receiver expression merely returns null normally, the static call itself does not throw an NPE. |
| “Overloads are decided after running the arguments.” | Overload resolution happens at compile time; runtime values serve the call to the implementation already selected according to language rules. |
| “The receiver has runtime type Derived, so the Derived(String) overload is automatically chosen.” | Overloads are chosen by static type; override dispatch uses the runtime object where applicable. |
| “Side effects of argument 1 are automatically undone if argument 2 fails.” | Java does not roll back normal side effects merely because a later argument throws an exception. |

## 14. Procedure for Reading a Call with Side Effects

When seeing a call such as:

~~~java
factory().work(nextId(), compute(), after());
~~~

You can follow this sequence:

1. **Check compile-time validity**: is there an applicable `work` method for the corresponding argument types? Are the receiver and method accessible?
2. **Identify the receiver expression**: does `factory()` have side effects or can it throw an exception?
3. **Trace arguments from left to right**: `nextId()` → `compute()` → `after()`; for nested expressions, examine the inner order next.
4. **Track modified variables**: assignments, `++`, operations on collections or mutable objects.
5. **Consider where exceptions can arise**: the receiver throwing an exception, an argument throwing an exception, or the receiver simply returning `null` normally.
6. **After the arguments complete**, determine the method implementation being called; note the possibility of dynamic dispatch if it is an instance method.
7. **Finally, examine the method body**: statements inside the method body cannot run before the arguments of that call itself finish.

If side effects make a single expression too hard to read, split it into clear statements:

~~~java
Worker target = createWorker();
int id = nextId();
int amount = calculateAmount();
target.execute(id, amount);
~~~

This illustrative code requires `Worker` and the related methods to be compatible. This is a clear way to express order; however, if `createWorker()` returns `null`, both `nextId()` and `calculateAmount()` still run before Java throws an NPE on the `target.execute(...)` call, matching the rule for a direct instance call when the corresponding argument expressions all complete.

When you **want to stop early if the receiver is null before running argument-computing tasks**, you need an intentional check:

~~~java
Worker target = createWorker();
if (target == null) {
    throw new IllegalStateException("No worker available");
}
int id = nextId();
int amount = calculateAmount();
target.execute(id, amount);
~~~

In that case, the early stop is due to **the `if` statement you wrote yourself**, not because Java automatically checks for `null` before the arguments of a method invocation.

## 15. Self-Check Questions

**Question 1.** For `factory().send(first(), second())`, if all expressions complete normally, what is the evaluation order?  
**Answer:** `factory()` first, `first()` next, then `second()`; only after that is `send` executed.

**Question 2.** `factory()` throws an exception. Do `first()` and `second()` run?  
**Answer:** No. The receiver does not complete normally, so Java halts the call and does not evaluate the arguments.

**Question 3.** `factory()` returns `null` normally; `first()` and `second()` do not fail. In a normal instance invocation, can logs from the two arguments appear before the NPE?  
**Answer:** Yes. Both arguments are evaluated before the `null` receiver leads to an NPE when attempting to invoke the instance method.

**Question 4.** `first()` completes; `second()` throws an exception; does `third()` run in `target.call(first(), second(), third())`?  
**Answer:** No. `third()` does not start and the body of `call` is not executed.

**Question 5.** In `current.describe(current = other)`, on which object does `describe` run if `current` initially points to A and `other` points to B?  
**Answer:** It runs on A, because the receiver is fixed before the argument assigns `current = other`. The passed argument has the reference value B.

**Question 6.** `StringBuilder sb = new StringBuilder("A"); view(sb, sb.append("B").toString());` — why can the first argument see the content `"AB"` inside the body of `view`?  
**Answer:** The first argument is a reference to the same `StringBuilder` object, not a copy of the text. The second argument mutated the object before the method ran.

**Question 7.** Does `Utility u = null; u.staticCall(doWork());` necessarily throw an NPE just because `u` is null?  
**Answer:** No, if `staticCall` is indeed a static method and the syntax is valid. Distinguish errors that might arise from `doWork()` or the static method's body from a null receiver.

**Question 8.** What values does `show(i++, ++i, i)` pass when `i=0`?  
**Answer:** `0, 2, 2` in sequence, because each expression is evaluated from left to right.

**Question 9.** `Base provider()` returns a `Derived` object, where `Derived` overloads `show(String)` while `Base` only has `show(Object)`. Does the call `provider().show("text")` automatically select `Derived.show(String)`?  
**Answer:** No. The overload is selected according to the static type `Base`: `show(Object)`; at runtime it can dispatch to the overridden `Derived.show(Object)` if present.

## References

- Java Language Specification, [§15.12.4 Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.4) — order of target reference, arguments, lookup, and invocation.
- Java Language Specification, [§15.7 Evaluation Order](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.7) — Java expression evaluation rules and preservation of order/side effects.

## Key Takeaways

In a normal instance method call, Java **determines the receiver first**, **evaluates each argument expression in left-to-right order**, and only then executes the call. If the receiver or an argument throws an exception, the remaining steps of the call are skipped; if the receiver simply **returns `null` normally**, the arguments may still be evaluated before an NPE occurs. Determining the receiver early preserves **the reference for the current call** even if an argument reassigns the receiver variable. This order is specified by Java and allows accurate prediction of side effects; however, the most maintainable code is still code that expresses order clearly through naming and intermediate variables when calls become complex.
