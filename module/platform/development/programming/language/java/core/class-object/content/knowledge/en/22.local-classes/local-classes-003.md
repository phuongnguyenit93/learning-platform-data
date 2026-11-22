# Accessing `final` and `effectively final` Local Variables from a Local Class in Java

A **local class** is a class declared inside a block, such as a method body, a constructor, or a statement block. In addition to having its own fields and methods, a local class can also **use local variables and parameters** from its enclosing scope. Java imposes an important requirement: **a local variable or parameter referenced from the body of a local class must be `final` or `effectively final`** and must satisfy the *definite assignment* rule at the point of use.

`final` is a modifier you write explicitly; `effectively final` is a property the compiler infers from how the variable is assigned. A variable without the `final` keyword can still be captured if, within its scope, the variable **is not reassigned under the rules Java applies to effectively final variables**. Conversely, `final StringBuilder builder` can point to a `StringBuilder` that can still be modified: `final` prohibits **reassigning the variable**; it does not make **the target object immutable**.

This lesson belongs to **Java core - class-object**, section **Local Classes**; its scope is how a local class references data outside it, rather than memorizing the `final` keyword in general. The examples use **Java 17+** and clearly distinguish complete programs from illustrative snippets; each standalone runnable program has a filename, `javac`/`java` commands, and deterministic stdout.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Identify a **local class declaration** and the scope in which the class name is visible.
2. Distinguish between a **local variable**, a **method parameter**, an **instance field**, a **static field**, and a **local class's own field**.
3. Explain why a local class is allowed to use `final` or `effectively final` local variables.
4. Distinguish between **reassigning a reference** and **mutating the referenced object**.
5. Predict compile-time errors when a captured local variable is reassigned.
6. Understand cases where a variable is assigned once across `if` branches, standard `for` loops, and enhanced `for` loops.
7. Explain how a local object continues to use captured values after its enclosing method returns.
8. Distinguish `this` inside a local class from `Outer.this`, and handle shadowing.
9. Compare local classes with lambdas, anonymous classes, and static nested classes in terms of capture.
10. Write methods that return an interface whose implementation is a local class, avoiding exposing unnecessary implementation types.
11. Test the output and behavior when a captured variable is a reference to a mutable object.
12. Understand why `effectively final` **does not automatically mean thread safety**.

## 2. Identifying a Local Class by Its Declaration Location

A simple example:

~~~java
public class Example {
    void execute() {
        int base = 10;

        class Adder {
            int add(int value) {
                return base + value;
            }
        }

        Adder adder = new Adder();
        System.out.println(adder.add(5));
    }
}
~~~

This is a **valid illustrative class**, without a `main` method yet. `Adder` is a **local class** because it is declared inside the body of the `execute()` method. The name `Adder` can be used within the valid scope of the block containing the declaration, but **cannot be used as a type name outside that scope** like a regular public API.

The variable `base` is not declared `final`, but it is not reassigned after receiving the value 10, so it is **effectively final**. `Adder.add()` is allowed to reference `base`.

Unlike a local class:

- **Top-level class** is declared at the file/package level.
- **Member class** is declared inside a class/interface, not inside a method block.
- **Non-static inner member class** has an enclosing object via a member relationship.
- **Static nested member class** does not have an implicit enclosing instance.
- **Anonymous class** creates an instance from an unnamed class body.
- **Lambda expression** is an expression implementing a functional interface; it has closely related capture rules, but its `this` semantics differ from those of an anonymous/local class.

**A local class is also a type of nested class**, but the identifying feature here is **its placement inside a block** and its ability to reference local variables from that scope.

## 3. Complete Program 1 — Capturing an Effectively Final Variable

Create the file **`LocalCaptureBasicsDemo.java`**:

~~~java
public class LocalCaptureBasicsDemo {
    public static void main(String[] args) {
        int base = 10;
        final String prefix = "result=";

        class Calculator {
            int plus(int amount) {
                return base + amount;
            }

            void print(int amount) {
                System.out.println(prefix + plus(amount));
            }
        }

        Calculator first = new Calculator();
        Calculator second = new Calculator();

        first.print(3);
        second.print(7);
        System.out.println("different objects="
                + (first != second));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LocalCaptureBasicsDemo.java
java LocalCaptureBasicsDemo
~~~

**Exact stdout:**

~~~text
result=13
result=17
different objects=true
~~~

Here, `base` is **effectively final**, while `prefix` is **explicitly final**. Both variables are validly used by the local class `Calculator`. The two `new Calculator()` calls create **two different objects**; however, both read the same captured values from that invocation of `main`.

You should not think of `base` as becoming a **static field**, or that every Calculator across all method invocations uses a shared mutable local memory slot. Java only guarantees capture behavior at the language level; how the compiler stores captured values is not an API contract that an application should rely on.

## 4. `final` and `effectively final`: An Easy-to-Apply Definition

`final` is written explicitly:

~~~java
final int limit = 5;
final String label = "Java";
~~~

Variables initialized as above **cannot be reassigned** under Java's rules. In contrast:

~~~java
int limit = 5;
String label = "Java";
~~~

these two variables do **not** have the `final` modifier, but can be considered effectively final if subsequent uses/assignments within scope satisfy the JLS rules: they are not reassigned after initialization. For a local variable without an initializer, Java allows single-assignment patterns that conform to *definite assignment* while remaining effectively final.

Operations that easily break the effectively final condition:

~~~java
int number = 5;
number = 6;       // Reassignment.
number++;         // Increment is a variable update.
number += 2;      // Compound assignment updates the variable.
~~~

This is a **valid illustrative snippet on its own**, but after those updates, `number` is **no longer effectively final** in the sense that it can be captured from a local class. Java does not evaluate "whether the final value is still 5 or actually changed" by analyzing business intent; the compiler evaluates assignment rules.

A variable declared `final` does not allow such updates after it has been initialized. When you need to change data meaningfully, create a **new result variable**, or design mutable state with clear ownership instead of trying to reassign the captured variable.

## 5. Why Does Java Enforce This Capture Constraint?

A normal local variable has a lifetime tied to **each method/block invocation**. Meanwhile, a local-class object can be returned out of the method and outlive that invocation.

~~~text
Call method makeTask(...)
    |
    | create local variable text
    | declare local class Task using text
    | create Task object
    v
method returns Task as interface Runnable
    |
    | stack frame of makeTask ends
    v
Task.run() still needs the captured value of text
~~~

If source code allowed reassigning a local variable repeatedly as state automatically linked to an object that has escaped the method, lifetime/observability and race issues would arise that are very hard to explain. The final/effectively final requirement keeps Java's capture behavior clear: a local class uses the **captured value**, not a local variable slot that can be reassigned later.

Do not infer from the diagram that the JVM is required to generate a specific field with a particular name or some wrapper object. The compiler is free to use any valid implementation strategy; the Java Language Specification defines **program behavior and validity**, and does not promise a specific bytecode shape across all compilers.

## 6. Complete Program 2 — An Object Outliving the Method Call

Create the file **`EscapingLocalClassDemo.java`**:

~~~java
public class EscapingLocalClassDemo {
    static Runnable makeTask(String user) {
        int attempt = 3;

        class GreetingTask implements Runnable {
            @Override
            public void run() {
                System.out.println("user=" + user
                        + ",attempt=" + attempt);
            }
        }

        return new GreetingTask();
    }

    public static void main(String[] args) {
        Runnable first = makeTask("An");
        Runnable second = makeTask("Binh");

        first.run();
        second.run();
        first.run();
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 EscapingLocalClassDemo.java
java EscapingLocalClassDemo
~~~

**Stdout:**

~~~text
user=An,attempt=3
user=Binh,attempt=3
user=An,attempt=3
~~~

`GreetingTask` is a local class inside the **static method** `makeTask`; that does not prevent it from capturing `user` and `attempt`, because these are parameters/locals of the method invocation rather than instance fields of an enclosing object.

Each call to `makeTask` has **its own set of source values**, so `first` remembers An while `second` remembers Binh. After the method returns, the `Runnable` instances still work. There is no need to make `attempt` a static variable, nor is there any need to allocate an enclosing instance just to hold captured local values.

## 7. Capturing Method Parameters Also Requires Effectively Final

Method or constructor parameters are essentially also variables with limited scope. When a local class reads a **method parameter**, the `final` or `effectively final` rule applies.

~~~java
static Runnable makeMessage(String message) {
    class Printer implements Runnable {
        @Override
        public void run() {
            System.out.println(message);
        }
    }

    return new Printer();
}
~~~

This is a **valid illustrative method** when placed inside a Java class. The parameter `message` is not reassigned in the method, so it is effectively final.

If you add:

~~~java
// INTENTIONALLY INVALID illustration when added to the method above:
// message = message.trim();
~~~

the method will not compile if the local class body still references `message`. That assignment makes the parameter no longer effectively final, even if you perform the assignment **before** creating Printer and assume Printer only needs the final value.

To normalize the input, create a **new local value**:

~~~java
static Runnable makeTrimmedMessage(String message) {
    String normalized = message.trim();

    class Printer implements Runnable {
        @Override
        public void run() {
            System.out.println(normalized);
        }
    }
    return new Printer();
}
~~~

This is a valid illustrative method when placed inside a class; `normalized` is assigned only once, so it can be captured. The fact that `message.trim()` requires message to be non-null is a separate input condition.

## 8. Complete Program 3 — Capturing Parameters and Normalized Data

Create the file **`ParameterCaptureDemo.java`**:

~~~java
public class ParameterCaptureDemo {
    static Runnable printRepeated(String raw, int count) {
        if (raw == null || count < 0) {
            throw new IllegalArgumentException("invalid input");
        }

        String normalized = raw.trim();

        class MessagePrinter implements Runnable {
            @Override
            public void run() {
                StringBuilder builder = new StringBuilder();
                for (int i = 0; i < count; i++) {
                    builder.append(normalized).append("!");
                }
                System.out.println(builder);
            }
        }

        return new MessagePrinter();
    }

    public static void main(String[] args) {
        Runnable first = printRepeated(" Hi ", 2);
        Runnable second = printRepeated(" Java ", 1);

        first.run();
        second.run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ParameterCaptureDemo.java
java ParameterCaptureDemo
~~~

**Stdout:**

~~~text
Hi!Hi!
Java!
~~~

`raw`, `count`, and `normalized` are not reassigned. The local class only actually uses `count` and `normalized`, so those are the two variables that get captured. `raw` is used by the method for normalization before creating the object; it does not need to be captured directly.

The variable `i` inside the `run()` method **is not captured from an outer scope**: it is a local loop variable belonging to `run()` itself. It can be incremented normally in the loop, because the effectively final constraint being discussed only arises when a local variable/parameter is **referenced from the body of another local/inner class or a lambda**.

## 9. Reassigning a Variable Before or After a Local Class Is a Problem

A common misconception: "As long as I reassign the variable before `new Task()`, it can surely be captured." That is incorrect. The compiler checks **how the variable is assigned within the relevant scope**, rather than relying on an execution order you assume is safe.

A snippet that **intentionally does not compile**:

~~~java
public class InvalidReassignmentExample {
    public static void main(String[] args) {
        int number = 1;
        number = 2;

        class Show {
            void print() {
                System.out.println(number); // compile-time error
            }
        }

        new Show().print();
    }
}
~~~

The error is on `number`: it was given an initializer of 1 and then reassigned to 2, so it is not effectively final. The fact that the local class itself does not write `number = ...` **cannot rescue** a variable that has already been reassigned in the enclosing method.

Another snippet that **also intentionally does not compile**:

~~~java
public class InvalidLaterAssignmentExample {
    public static void main(String[] args) {
        int number = 1;

        class Show {
            void print() {
                System.out.println(number); // compile-time error
            }
        }

        number = 2;
        new Show().print();
    }
}
~~~

Even though the second assignment comes **after the class declaration**, it still breaks effectively final. Both code blocks are marked as **compile-error examples**, not demos meant to be run.

**How to fix:** keep the captured variable from being reassigned and move the result into a differently named variable, or use a state holder with a clear mutation policy if the application genuinely needs mutable state.

## 10. Complete Program 4 — Computing a New Value in Another Variable

Create the file **`NewLocalValueDemo.java`**:

~~~java
public class NewLocalValueDemo {
    public static void main(String[] args) {
        int original = 4;
        int doubled = original * 2;

        class Printer {
            String describe() {
                return "original=" + original
                        + ",doubled=" + doubled;
            }
        }

        Printer printer = new Printer();
        System.out.println(printer.describe());
        System.out.println("sum=" + (original + doubled));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 NewLocalValueDemo.java
java NewLocalValueDemo
~~~

**Stdout:**

~~~text
original=4,doubled=8
sum=12
~~~

The local variables `original` and `doubled` are assigned only once and are captured. If the goal is to compute another value, `int doubled = original * 2` is usually clearer in intent than `original *= 2` followed by trying to use `original` in a local class.

This is a very useful technique when normalizing input, computing configuration values, creating callbacks, and passing behavior to another API: **a new result variable both makes intent clear and preserves the capture requirement**.

## 11. A `final` Variable Does Not Mean an Immutable Object

Consider:

~~~java
final StringBuilder buffer = new StringBuilder("A");
buffer.append("B");
~~~

These two statements are **valid**. The `final` modifier forbids writing `buffer = new StringBuilder("C")` after initialization, yet still allows `append` to modify **the referenced StringBuilder itself**.

Similarly:

~~~java
java.util.List<String> names =
        new java.util.ArrayList<>();
names.add("An");
~~~

If the variable `names` is not **reassigned**, it can be effectively final; calling `names.add(...)` to mutate the list's state is not a reassignment of the `names` variable.

Distinguish three layers:

| Layer | Example | What can change? |
| --- | --- | --- |
| Local variable/reference | `builder = anotherBuilder` | The `builder` variable points to a different object |
| Referenced object | `builder.append("X")` | The contents of the existing StringBuilder |
| State of the local-class object | `task.times++` inside Task | Task's own field |

The final/effectively final rule governs **the captured variable layer**. It does **not** freeze the object graph or forbid all state mutation elsewhere.

## 12. Complete Program 5 — Capturing a Reference, Mutating the Object

Create the file **`MutableReferenceCaptureDemo.java`**:

~~~java
public class MutableReferenceCaptureDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");

        class Reporter {
            void show() {
                System.out.println("text=" + builder);
            }
        }

        Reporter reporter = new Reporter();
        reporter.show();

        builder.append("B");
        reporter.show();

        builder.append("C");
        reporter.show();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MutableReferenceCaptureDemo.java
java MutableReferenceCaptureDemo
~~~

**Exact stdout:**

~~~text
text=A
text=AB
text=ABC
~~~

The `builder` variable still points to **the same object**, so it is effectively final. The `append` calls modify the state of that StringBuilder; `Reporter` observes the changing contents.

**There is no contradiction** with capturing: the local class is not reading "a reassigned local variable". It holds a reference value to an object whose internal state can change.

This approach can be useful in a state-holder model, but it can also introduce **aliasing**: multiple places mutating the same object that Reporter holds. If you need an immutable snapshot of the data, create `String snapshot = builder.toString()` and capture `snapshot` instead of capturing the StringBuilder itself.

## 13. A Value Snapshot vs. Sharing a Mutable Holder

A local class that captures `int count = 5` receives an unchanging primitive value under the capture rule. By contrast, if it captures `int[] state = {5}`, what is captured is the **reference to the array**; the caller can still assign `state[0] = 9`.

Diagram:

~~~text
Local variable state (reference is not reassigned)
         |
         v
      int[] A [5]        <-- later A[0] is modified to 9
         ^
         |
 Local-class object uses the same reference to A
~~~

If you want the local class to observe **the value at creation time**, store a snapshotted primitive/immutable string. If you want it to observe **changing state**, use an intentionally managed holder. In particular, if multiple threads access the holder, proper synchronization mechanisms are needed.

## 14. Complete Program 6 — Primitive Snapshot and Mutable Array

Create the file **`CapturedArrayDemo.java`**:

~~~java
public class CapturedArrayDemo {
    public static void main(String[] args) {
        int snapshot = 5;
        int[] mutableCell = {5};

        class Reader {
            void print() {
                System.out.println("snapshot=" + snapshot
                        + ",cell=" + mutableCell[0]);
            }
        }

        Reader reader = new Reader();
        reader.print();

        mutableCell[0] = 9;
        reader.print();

        mutableCell[0] = 12;
        reader.print();
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 CapturedArrayDemo.java
java CapturedArrayDemo
~~~

**Stdout:**

~~~text
snapshot=5,cell=5
snapshot=5,cell=9
snapshot=5,cell=12
~~~

`snapshot` is an effectively final local primitive: it is always 5 in the program. `mutableCell` is also effectively final at **the reference-variable level**, while the array object changes sequentially from 5 to 9 and then 12.

You should not "work around the effectively final rule" by wrapping every variable in a single-element array and updating it arbitrarily. While syntactically valid, that approach **hides mutable state** and makes code harder to understand, especially with callbacks or concurrency. If you need state, define a named type/holder with clear invariants and ownership.

## 15. Blank `final`: Single Assignment Along Control Flow

A final variable **does not have to have an initializer directly at its declaration**. A **blank final local** can be assigned after declaration along appropriate control-flow paths, as long as the compiler can prove definite assignment before use and there is no illegal reassignment.

~~~java
final int fee;
boolean premium = true;

if (premium) {
    fee = 20;
} else {
    fee = 5;
}

class Receipt {
    int total(int base) {
        return base + fee;
    }
}
~~~

This is a valid illustrative Java snippet if placed inside a method. `fee` is assigned exactly once on each execution path, so `Receipt` can reference it. The `final` keyword does not mean you must write a hard-coded value in every case.

A local variable not declared `final` but assigned in a similar way **can also be effectively final** if it satisfies the JLS rules (including the rules for definite assignment and definite unassignment). Do not assume that any assignment inside an `if` branch automatically breaks effectively final.

## 16. Complete Program 7 — final and effectively final After `if`

Create the file **`ConditionalCaptureDemo.java`**:

~~~java
public class ConditionalCaptureDemo {
    public static void main(String[] args) {
        boolean premium = true;

        final int fixedFee;
        if (premium) {
            fixedFee = 20;
        } else {
            fixedFee = 5;
        }

        int discount;
        if (premium) {
            discount = 3;
        } else {
            discount = 0;
        }

        class Receipt {
            int total(int base) {
                return base + fixedFee - discount;
            }
        }

        Receipt receipt = new Receipt();
        System.out.println("fee=" + fixedFee);
        System.out.println("discount=" + discount);
        System.out.println("total=" + receipt.total(100));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConditionalCaptureDemo.java
java ConditionalCaptureDemo
~~~

**Exact stdout:**

~~~text
fee=20
discount=3
total=117
~~~

`fixedFee` is a blank final. `discount` is not declared final, but each `if/else` branch assigns it exactly once before capture, and there are no reassignments afterward: in this example, it is allowed to be captured as effectively final.

If one branch does not initialize `discount` and the code still uses it, that is a separate **definite assignment issue**. The compiler must know that the variable has a value on every path reaching the read, regardless of effectively final status.

## 17. Standard `for` Loops: The Index Changes So It Is Not Effectively Final

A typical indexed loop:

~~~java
for (int i = 0; i < 3; i++) {
    // i is updated by i++.
}
~~~

The variable `i` is incremented on each iteration, so it is **not effectively final**. If a local class in the loop body tries to access `i` directly and that object could be retained, the compiler rejects it:

~~~java
// SNIPPET THAT INTENTIONALLY DOES NOT COMPILE when the error is uncommented:
for (int i = 0; i < 3; i++) {
    class InvalidTask {
        void run() {
            // System.out.println(i);
            // i is not effectively final due to i++ in the for loop.
        }
    }
}
~~~

The right pattern is to declare **a new snapshot variable on each iteration**:

~~~java
for (int i = 0; i < 3; i++) {
    int capturedIndex = i;

    class Task {
        void run() {
            System.out.println(capturedIndex);
        }
    }

    new Task().run();
}
~~~

Each execution of the loop body has a local `capturedIndex` initialized from the current value of `i`, and never reassigned. It is effectively final and validly used by the local class.

**Note:** this differs from merely writing `final int capturedIndex = i;` in terms of capture validity; both explicit final and effectively final are valid. Adding `final` can help emphasize intent, though it is not always mandatory.

## 18. Complete Program 8 — Each Iteration Retains Its Own Index

Create the file **`LoopCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int capturedIndex = i;

            class IndexTask implements Runnable {
                @Override
                public void run() {
                    System.out.println("index=" + capturedIndex);
                }
            }

            tasks.add(new IndexTask());
        }

        System.out.println("task count=" + tasks.size());
        for (Runnable task : tasks) {
            task.run();
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
~~~

**Stdout:**

~~~text
task count=3
index=0
index=1
index=2
~~~

The tasks run **after the loop that created the tasks has finished**. Each task still prints the exact index of the iteration that created it, because each `capturedIndex` variable has its own value and qualifies for capture.

A common mistake is wanting all tasks to directly reference the same incrementing `i` variable in the for loop. Java does not allow capturing that variable in a local/inner class, avoiding a common class of bugs seen in languages with different capture semantics.

## 19. Enhanced `for`: The Element Variable Has More Favorable Rules

With an enhanced for loop:

~~~java
for (String word : java.util.List.of("A", "B")) {
    class Printer {
        void run() {
            System.out.println(word);
        }
    }
    new Printer().run();
}
~~~

This is a valid Java snippet when placed inside a method. The enhanced-for variable `word` is declared per iteration according to the language rules, and if you do not reassign it in the body, it can be captured from a local class.

Unlike `i++` in a basic for loop, here there is no operation in your code updating the `word` variable. However, if you write `word = word.toLowerCase();` inside the body, that variable no longer satisfies effectively final for capture.

A local class can still capture **the reference value to a mutable element** in an enhanced for loop; if the element is a mutable object, changes inside the object can still be seen by the corresponding tasks.

## 20. Complete Program 9 — Capturing an Enhanced-For Element

Create the file **`EnhancedForCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class EnhancedForCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (String word : List.of("Java", "Core")) {
            class WordTask implements Runnable {
                @Override
                public void run() {
                    System.out.println("word=" + word);
                }
            }
            tasks.add(new WordTask());
        }

        for (Runnable task : tasks) {
            task.run();
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnhancedForCaptureDemo.java
java EnhancedForCaptureDemo
~~~

**Stdout:**

~~~text
word=Java
word=Core
~~~

Both WordTask objects are invoked **after the loop**, yet they still read the corresponding value from each enhanced-for iteration. Because String is immutable, there is no risk of another thread modifying the internals of the referenced String object.

Do not generalize that every variable appearing in a loop can be captured. Check **whether the variable is reassigned**, **which scope** it is declared in, and whether the compiler determines that it is properly initialized.

## 21. Name Scope of a Local Class: Where Can It Be Used?

The name of a local class is scoped only to the **block** containing its declaration and the lexical scope rules; it does not become a member type that can be written as `Outer.LocalType` from anywhere.

~~~java
class Processor {
    Runnable create() {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println("work");
            }
        }
        return new Task();
    }
}
~~~

This is a valid illustrative class. A caller can hold the result as a `Runnable`, but **cannot** declare `Processor.Task task` in another class as with a static nested class, because `Task` is not a member type of Processor.

To expose usability, return an **appropriate interface or superclass**. If the caller needs to know the concrete class, consider moving it to a member nested class or a top-level class with explicit visibility.

A local class can be used multiple times **within its valid scope**, but its name is not exposed in the API outside the method.

## 22. Complete Program 10 — Returning an Interface, Hiding the Local Type

Create the file **`LocalStrategyDemo.java`**:

~~~java
interface IntOperation {
    int apply(int value);
}

public class LocalStrategyDemo {
    static IntOperation adding(int delta) {
        class AddOperation implements IntOperation {
            @Override
            public int apply(int value) {
                return value + delta;
            }
        }

        return new AddOperation();
    }

    public static void main(String[] args) {
        IntOperation add7 = adding(7);
        IntOperation add2 = adding(2);

        System.out.println("add7 to 3=" + add7.apply(3));
        System.out.println("add7 to 5=" + add7.apply(5));
        System.out.println("add2 to 3=" + add2.apply(3));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocalStrategyDemo.java
java LocalStrategyDemo
~~~

**Exact stdout:**

~~~text
add7 to 3=10
add7 to 5=12
add2 to 3=5
~~~

`AddOperation` is only an implementation inside the body of `adding`. The caller uses the `IntOperation` interface, neither needing nor seeing the local type name outside the scope.

The parameter `delta` is captured because it is not reassigned. Each call to `adding` creates a local-class object that remembers the corresponding delta value.

**When should you use it?** When the behavior needs multiple methods, state, or a clearer structure than a simple lambda, a local class can be a good fit. When you only need one method of a functional interface with minimal code, a lambda is usually more concise. Do not force a local class into every callback just to demonstrate variable capture.

## 23. A Local Class's `this` Is Not the Enclosing Object's `this`

If a local class is inside an instance method of an Outer class:

- `this` inside a method of the **local class** is the local class instance.
- `Outer.this` in the context of an inner/local class with a matching enclosing Outer instance is the **Outer object**.
- Private members of Outer can be accessed according to the rules, though if a name is shadowed by a local field, a qualified reference is needed.
- Local variables and method parameters are not **fields of Outer** and are not accessed via `Outer.this.localVariable`.

Example:

~~~java
class Host {
    private String label = "outer";

    Runnable create() {
        int number = 2;

        class Task implements Runnable {
            private String label = "local";

            @Override
            public void run() {
                System.out.println(this.label);
                System.out.println(Host.this.label);
                System.out.println(number);
            }
        }

        return new Task();
    }
}
~~~

This is a valid illustrative class; the local variable `number` is captured, whereas `Host.this.label` reads an instance field of the enclosing Host object—a **different** mechanism.

## 24. Complete Program 11 — Shadowing and `Outer.this`

Create the file **`LocalThisAndOuterDemo.java`**:

~~~java
final class Host {
    private final String label;

    Host(String label) {
        this.label = label;
    }

    Runnable create(String name) {
        int length = name.length();

        class Task implements Runnable {
            private final String label = "LOCAL";

            @Override
            public void run() {
                System.out.println("local=" + this.label);
                System.out.println("host=" + Host.this.label);
                System.out.println("argument=" + name);
                System.out.println("length=" + length);
            }
        }

        return new Task();
    }
}

public class LocalThisAndOuterDemo {
    public static void main(String[] args) {
        Host host = new Host("H");
        host.create("AB").run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LocalThisAndOuterDemo.java
java LocalThisAndOuterDemo
~~~

**Stdout:**

~~~text
local=LOCAL
host=H
argument=AB
length=2
~~~

Inside Task, `this.label` is a field of the local-class object; `Host.this.label` is a private field of Host associated with the local class instance because it was created in an instance context.

`name` is a method parameter and `length` is a local variable: they are captured because they are effectively final. You cannot use `Host.this.length`, because `length` is not a field of Host.

If a local class is created inside a **static method**, there is no `Host.this` there; however, the local class can still capture effectively final locals/parameters of the static method.

## 25. A Local Class in a Static Method Still Captures Local Variables

A local class **does not need an enclosing instance** to use effectively final variables from a static method:

~~~java
class Tasks {
    private static final String PREFIX = "task:";

    static Runnable build(String label) {
        int version = 17;

        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        PREFIX + label + "/" + version);
            }
        }

        return new Task();
    }
}
~~~

This is a valid illustrative class. `Task` can access `PREFIX` (static field), `label` (captured parameter), and `version` (captured local).

However, if Task's code needs an instance field `Tasks.owner` of a specific Tasks object, it must have an appropriate reference. **The effectively final rule does not create an enclosing object** and does not make instance members static.

## 26. Generic Methods: A Local Class Can Use the Method's Type `T`

A local class can be declared inside a generic method and use a type parameter in scope, unlike a static nested **member** class, which does not automatically inherit the type parameter of an enclosing generic class.

~~~java
class Factory {
    static <T> java.util.function.Supplier<T> fixed(T value) {
        class Holder implements java.util.function.Supplier<T> {
            @Override
            public T get() {
                return value;
            }
        }
        return new Holder();
    }
}
~~~

This is valid Java code. `Holder` is a local class inside a generic method and is allowed to use `T` from the method's lexical scope. It captures the parameter `value` because the parameter is not reassigned.

Because Java generics use **type erasure**, do not infer that each `T` produces a different runtime class. We analyze the behavior of typed references according to static type rules.

## 27. Complete Program 12 — Generic Local Class and Capturing `T`

Create the file **`GenericLocalClassDemo.java`**:

~~~java
import java.util.function.Supplier;

public class GenericLocalClassDemo {
    static <T> Supplier<String> describe(T value) {
        String prefix = "got:";

        class Description implements Supplier<String> {
            @Override
            public String get() {
                return prefix + value;
            }
        }

        return new Description();
    }

    public static void main(String[] args) {
        Supplier<String> text = describe("java");
        Supplier<String> number = describe(42);

        System.out.println(text.get());
        System.out.println(number.get());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericLocalClassDemo.java
java GenericLocalClassDemo
~~~

**Exact stdout:**

~~~text
got:java
got:42
~~~

In the method `describe(T value)`, the parameter `value` and the local `prefix` are effectively final; the local class is allowed to use both. The String concatenation expression `prefix + value` uses Java's object-to-string conversion mechanism; in this demo, String and Integer produce deterministic results.

A local type can be more complex if it declares its own type parameters, but for this lesson on capture, what matters is **the type names in scope** and **the reassignment condition of captured variables**.

## 28. Local Classes vs. Lambdas and Anonymous Classes

Local classes, anonymous classes, and lambdas can all reference effectively final locals/parameters from their enclosing scope. However, **do not treat them as identical**:

| Mechanism | Local class | Anonymous class | Lambda |
| --- | --- | --- | --- |
| Has a class name inside the block? | Yes | No | Does not declare a named class body |
| Creates an implementation of an interface? | Yes | Yes | Yes, if the target is a functional interface |
| Local/parameter capture | Final/effectively final | Final/effectively final | Final/effectively final |
| `this` inside the behavior body | Local-class instance | Anonymous-class instance | `this` of the lexical enclosing context |
| Can have multiple custom methods | Yes | Yes, within anonymous class constraints | Does not define a class with multiple methods |
| Can be returned as an interface | Yes | Yes | Yes |
| Need to pay attention to `Outer.this` | Yes, when an enclosing instance applies | Yes, when an enclosing instance applies | Uses the lexical context |

Choose based on complexity: a local class is suitable when you need a type **named inside a block** and a substantial implementation; a lambda is suitable for short behavior of a functional interface; an anonymous class works when you need a dedicated instance body without needing a type name.

Do not try to write `this` inside a lambda as if `this` were a new lambda object. Also, do not rely on a JVM-generated class name for a lambda as a stable API.

## 29. Complete Program 13 — Local Class, Anonymous Class, and Lambda

Create the file **`ThreeCaptureFormsDemo.java`**:

~~~java
public class ThreeCaptureFormsDemo {
    public static void main(String[] args) {
        String word = "Java";

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println("local=" + word);
            }
        }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" + word);
            }
        };

        Runnable lambda =
                () -> System.out.println("lambda=" + word);

        new LocalTask().run();
        anonymous.run();
        lambda.run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ThreeCaptureFormsDemo.java
java ThreeCaptureFormsDemo
~~~

**Stdout:**

~~~text
local=Java
anonymous=Java
lambda=Java
~~~

`word` is effectively final, so all three forms can use it. If you add `word = "Other";` in the method, the compiler will not allow any of the three behavior bodies to reference `word` under the capture rule.

The example intentionally does not examine `this` or lambda identity to avoid mistakenly treating those as the explanation for the final/effectively final condition. Differences regarding `this` matter when the body actually accesses an enclosing instance.

## 30. Capturing Is Not a Multithreaded Synchronization Mechanism

The fact that the compiler allows capturing an effectively final reference **does not mean the target object is thread-safe**:

~~~java
java.util.List<String> shared =
        new java.util.ArrayList<>();

class Task implements Runnable {
    @Override
    public void run() {
        shared.add("x");
    }
}
~~~

This is an **illustrative class snippet inside a method**, valid if the `shared` variable is in scope and not reassigned. It does not automatically guarantee safety when multiple threads invoke `run()` on the tasks or modify the ArrayList concurrently.

Several points to keep distinct:

- The `shared` variable is captured **as a reference value**; it is effectively final itself.
- The `ArrayList` object remains mutable, and its operations are not automatically synchronized.
- Reading/writing data across threads must satisfy the Java Memory Model; a local class does not provide locking by itself.
- If you only need an immutable snapshot, you can capture `List.copyOf(source)` with immutable elements as part of the contract.
- If you need shared counters, use `AtomicInteger`, synchronization, or an appropriate concurrency utility.

With an `AtomicInteger`, the reference variable holding it can be final/effectively final, while `incrementAndGet()` updates the **state of the AtomicInteger** safely according to the concurrency API contract.

## 31. Complete Program 14 — Intentionally Capturing `AtomicInteger`

Create the file **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();

        class IncrementTask implements Runnable {
            @Override
            public void run() {
                counter.incrementAndGet();
            }
        }

        Thread first = new Thread(new IncrementTask());
        Thread second = new Thread(new IncrementTask());

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("counter=" + counter.get());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

**Exact stdout after both threads successfully `join()`:**

~~~text
counter=2
~~~

`counter` is effectively final because the reference is not reassigned, yet the AtomicInteger object can still be updated. `incrementAndGet` performs an atomic update per the API. The two threads may execute in different orders, but once `join()` completes, each thread has incremented once; the printed value is 2.

**Do not use this result to conclude** that capturing a reference variable makes every mutable object thread-safe. The safety here comes from **AtomicInteger** and waiting for the threads to finish, not from the fact that the local class is allowed to capture.

## 32. Common Pitfall: Using a Single-Element Array to "Bypass" final

A coding pattern occasionally seen:

~~~java
int[] result = {0};

class Counter {
    void increment() {
        result[0]++;
    }
}
~~~

This snippet is valid inside a method. Because the `result` reference variable is not reassigned, it is effectively final, while the array element still changes.

However, it is often hard to read and is no true substitute for proper state design:

- `result[0]` obscures the fact that it is a state container.
- There are no invariants or methods expressing the meaning of the state.
- If multiple tasks hold the same array, they share mutations.
- `result[0]++` is **not atomic**, so multithreaded use can lose updates.
- For a long-lived callback API, an explicit state object or an appropriate concurrency class is usually easier to maintain.

Prefer creating a class with clear responsibilities (`Counter`, `Progress`) or using `AtomicInteger` when that fits the requirement. If you only need a computed value, **creating a new local result before capture** is simpler.

## 33. Shadowing Does Not Break Access, but Changes What a Name Resolves To

If a local class has a field with the same name as a variable in the method, **name resolution** can cause the simple name to point to the local class's field instead of the outer local variable. Because Java has no syntax like "`MethodName.this.localVariable`", it is best to **avoid using the same name** if you need both.

Example:

~~~java
class Parent {
    private int level = 10;

    void method() {
        int localLevel = 5;

        class Child {
            private int level = 20;

            void print() {
                System.out.println(level);
                System.out.println(this.level);
                System.out.println(Parent.this.level);
                System.out.println(localLevel);
            }
        }

        new Child().print();
    }
}
~~~

This is a valid definition. `level` refers to Child's field (20), `Parent.this.level` refers to Parent's private field (10), and `localLevel` refers to the method's local variable (5).

If you declare a local variable also named `level`, Child's field can shadow that name inside Child's body; you **cannot** simply write `Parent.this.level` to get the local variable because `Parent.this.level` is always **Parent's field**. Using a different name makes the distinction clearer.

## 34. Definite Assignment Is a Separate Requirement from Effectively Final

A variable might not be reassigned yet still **not be initialized on every execution path** before the local class reads it. Java checks *definite assignment*:

~~~java
// SNIPPET THAT INTENTIONALLY DOES NOT COMPILE:
void bad(boolean condition) {
    int value;
    if (condition) {
        value = 5;
    }

    class Printer {
        void print() {
            System.out.println(value); // not definitely assigned
        }
    }
}
~~~

If `condition` is false, `value` has no value yet. Therefore, the compiler does not allow reading it inside Printer, even though no code reassigns it after Printer is declared.

Fix it by assigning once on every control-flow path:

~~~java
void good(boolean condition) {
    int value;
    if (condition) {
        value = 5;
    } else {
        value = 0;
    }

    class Printer {
        void print() {
            System.out.println(value);
        }
    }

    new Printer().print();
}
~~~

This is a **valid method snippet** when placed inside a class. `value` is both definitely assigned before being read and effectively final.

There are three distinct checks: **is the variable in scope**, **has it been assigned before use**, and **does it satisfy final/effectively final for capture**. Each check can produce a separate compile-time error.

## 35. Performance and Design Questions

A local class can be used to encapsulate behavior tied to a few variables inside a method without needing a public type. However:

- Each `new LocalTask()` can create a separate object according to `new` semantics.
- Capturing large references can keep **the target object reachable** as long as the task retains the reference.
- Using a local class for overly long functionality makes the method hard to read.
- Returning a local implementation via an interface hides implementation details, though the API should document the actual contract.
- For long-lived callbacks, consider lifecycle, cancellation, and shared mutable state management.
- Do not optimize by converting effectively final locals into mutable arrays without measuring first.
- If you are only passing a short function, a lambda can reduce boilerplate; if you need multiple methods and dedicated state, a local class can be easier to understand.

Regarding memory: **capturing an object reference can help keep the object reachable**. The `final` keyword/effectively final does not cause the object to be collected earlier. This is especially important to keep in mind for callbacks/listeners stored in long-lived registries.

## 36. Compile-Time Error Table and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Local class reads a variable reassigned with `=` | Not effectively final | Read a new snapshot variable assigned once |
| Local class reads a variable updated with `++` | Not effectively final | Capture a copy of the index/value |
| Capturing a parameter normalized by reassignment | Parameter is not effectively final | `String normalized = input.trim()` |
| Using a local variable with an unassigned branch | Not definitely assigned | Assign a value on every path used |
| Wanting `return counter++` in a local method | Outer local `counter` is mutated | Design a holder with clear ownership |
| Capturing `for (int i...; i++)` directly | Index changes across loop iterations | `int snapshot = i` in the body |
| Capturing an enhanced-for variable and reassigning it | Iteration variable is not effectively final | Create a new local or avoid reassigning it |
| Treating `final List` as an immutable list | Final locks the reference, not the list | Immutable snapshot/defensive copy |
| Using a captured ArrayList across multiple threads | Race condition on the mutable list | Concurrency API or synchronization |
| Assuming `this` inside a local class is Outer | `this` refers to the local object | `Outer.this` if applicable |
| Trying to use a local class name from another method | Local class type is out of scope | Return an interface or promote to a member class |
| Thinking `effectively final` applies to all fields | This is a capture rule for locals/parameters | Distinguish fields from locals |
| Capturing a reference to a still-mutable builder | Tasks share mutable state | Snapshot as a String/immutable DTO if needed |
| Modifying a local variable after defining Task but before run | Capture is still invalid | Do not reassign the captured variable |
| Using `final` to "achieve thread safety" | Does not synchronize a mutable object | `AtomicInteger`, locks, or an immutable model |

You should not fix a compile error by turning a local variable into a **global static field**: doing so changes data from being **per-method-invocation** to **class-wide shared data**, which can introduce concurrency and lifecycle bugs worse than the original error.

## 37. Step-by-Step Procedure for Solving Local Variable Capture Questions

For a question asking "Does this Java snippet compile, and what does it print?", follow these steps in order:

1. Find the **local class**: which method/block is it inside?
2. List **the variables that are not fields of the local class** which the body actually reads.
3. For each variable, determine whether it is a **local variable**, **formal parameter**, **field**, or static member.
4. For locals/parameters, check scope and *definite assignment*.
5. Check whether the variable is **reassigned, incremented/decremented, or updated via compound assignment** along any relevant path.
6. If final/effectively final is satisfied, determine the **captured value** for that method invocation.
7. If the variable is a reference, also trace the **referenced object**: does another method modify that object?
8. If there are multiple method invocations, distinguish that each invocation has **its own set of local values**.
9. If there is a loop, distinguish the basic-for index from a body snapshot and from an enhanced-for iteration variable.
10. When the local class uses `this`, distinguish the local-class object from the enclosing `Outer.this`.
11. If the object runs after the method finishes or on another thread, examine lifecycle and concurrency separately.
12. Only after verifying that the compiler allows it should you trace stdout statement by statement in execution order.

**Most importantly:** an effectively final error is **compile-time**. Do not invent an imaginary stdout for a program with a compile-time error and conclude "it will print the last value".

## 38. Self-Practice Exercises

**Question 1.** A variable `int n = 5;` is not reassigned afterward. Can a local class in the same method read `n` even without writing `final`?

**Question 2.** If `n = 6;` is added before creating the local-class object, how does the answer change?

**Question 3.** If the reassignment `n = 6;` is placed **after** the local class declaration, does that resolve the error?

**Question 4.** `final StringBuilder b = new StringBuilder("A");`, followed by calling `b.append("B")`. Can variable b still be captured by a local class, and what content does the local class see?

**Question 5.** `List<String> list = new ArrayList<>(); list.add("X");`. Does calling `add` by itself make the list variable no longer effectively final?

**Question 6.** A local class reads the formal parameter `name`. If the method writes `name = name.trim()`, will it compile? Write how to fix it.

**Question 7.** `final int x;` is assigned `x=1` in the if branch and `x=2` in the else branch. Can a local class use x after the if/else?

**Question 8.** A variable `int x;` is only assigned in the if branch, with no else, and a local class reads x after the if. What error occurs?

**Question 9.** Why does `for (int i=0;i<3;i++)` not allow a local class to capture i directly inside the body?

**Question 10.** What approach allows creating three Runnables that remember 0, 1, and 2 respectively inside a basic for loop?

**Question 11.** In an enhanced for loop `for(String word : words)`, can word be captured if it is not reassigned?

**Question 12.** Can a local class created inside a static method capture locals of that static method?

**Question 13.** Can a local class created inside an instance method read a `private int field` of the enclosing object? Via what expression if there is a name collision?

**Question 14.** What object is `this` inside an instance method of a local class?

**Question 15.** If a local class is returned as the Runnable interface, does the caller need to know the local class name to call `run()`?

**Question 16.** After a method returns a Runnable created by a local class, local variables in the original stack frame can no longer be accessed as direct local variables. Why can the Runnable still use the captured values?

**Question 17.** You capture `int[] state = {0}` and multiple threads update `state[0]++`. Does the fact that state is effectively final make the update atomic?

**Question 18.** Does capturing `AtomicInteger count` and calling `incrementAndGet` violate effectively final for the count variable?

**Question 19.** Do local classes and lambdas share the same final/effectively final capture rule? Does `this` have the exact same meaning?

**Question 20.** Why can it be a problem if a long-lived listener captures a large object?

**Question 21.** Can a local class inside a generic method `<T> T process(T input)` use `T` in scope?

**Question 22.** If a local class body does not reference local variable `x`, does reassigning x make the local class declaration invalid with respect to capture?

**Question 23.** Why can a class with an instance field `int total` update `total++` in a method, whereas a captured local `int total` cannot be reassigned?

**Question 24.** When a local class uses the name `value` that collides between a local-class field and an enclosing method variable, does the simple name necessarily refer to the outer local variable?

### Answers and Explanations

1. Yes, `n` is effectively final.
2. No; `n` is reassigned and loses its eligibility for capture.
3. No; the compiler still checks reassignments within the relevant scope.
4. Yes. The reference b is not reassigned; if `append` is called before reading, the local class sees `"AB"`.
5. No; `add` mutates the object without reassigning the local variable list.
6. No, if the local class reads the parameter name; use `String normalized = name.trim()` and capture normalized.
7. Yes, if each path assigns exactly once and definite assignment is satisfied.
8. The variable is not definitely assigned on the condition=false path.
9. Because `i++` makes i not effectively final.
10. On each iteration write `int capturedIndex = i;`, and have the local class capture this snapshot variable.
11. Yes, according to the enhanced-for iteration variable rules when it is not reassigned.
12. Yes, a static context does not prohibit capturing local variables/parameters.
13. Yes, under access/enclosing-instance rules; use `Outer.this.field` when you need to specify the receiver explicitly.
14. The instance of the local class itself.
15. No; the Runnable interface is the external API, so the caller only needs `run()`.
16. The required values are captured according to Java semantics, independent of whether the stack frame remains alive.
17. No. `state[0]++` is not atomic, and the mutable array has a race condition.
18. No. The increment modifies the AtomicInteger's state, without reassigning the count reference variable.
19. They have similar capture rules; `this` in a lambda follows the lexical enclosing context, unlike a local/anonymous object.
20. The captured reference can keep the object reachable longer than expected.
21. Yes, the type parameter T belongs to the appropriate lexical scope of the generic method.
22. No, only variables actually referenced from the local class are subject to that capture rule.
23. An instance field is member state rather than a local variable needing capture; it can be mutated if the method and visibility allow it.
24. No. Name resolution and shadowing can select the local class's field; use distinct names for clarity.

## 39. Checklist Before Finishing the Practice Exercise

- Have you made clear that this is a **local class inside a block**, not a static nested member class?
- Is the local class name only used within its valid scope?
- Is every captured local/parameter **final or effectively final**?
- Is the variable definitely assigned before the body reads it?
- Are there no reassignments/++/compound assignments on captured variables?
- If a new value needs to be computed, did you put it in a **new variable** instead of reassigning a captured variable?
- Have you distinguished an **unchanging reference variable** from a **still-mutable object**?
- For `List`, arrays, builders, and mutable DTOs, have you determined whether aliasing is intentional?
- For basic for loops, did you snapshot the index per iteration?
- For enhanced for loops, did you ensure the element variable is not reassigned?
- If the local class is returned through an interface, does the caller avoid depending on the local class name outside its scope?
- If the local class uses `this`, is it understood as referring to the local object?
- If an enclosing instance is needed, is `Outer.this` used in a valid context?
- If the local class is in a static method, do you avoid assuming an enclosing Outer object exists?
- If threads are involved, have you chosen an appropriate mutable holder/concurrency API?
- Have you verified the stdout of **compilable** programs without assuming output for intentionally erroneous code?
- Have you tried at least one case of a method returning a local implementation, one mutable reference case, and one loop capture case?

## 40. Official Reference Documentation (Java 17)

- [JLS 17 §14.3 — Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): local class declaration locations, scope, and capture conditions.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): definition of final/effectively final variables and assignment.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): initialization rules before reading.
- [JLS 17 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): scope of local classes and local variables.
- [JLS 17 §6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): resolution of colliding names.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing-instance relationship.
- [JLS 17 §15.8.4 — Qualified `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): meaning of `Outer.this`.
- [JLS 17 §15.27.2 — Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2): capture rules and lexical context in lambdas.
- [JLS 17 §14.14.2 — Enhanced for Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.14.2): enhanced-for iteration variables.
- [Java SE 17 — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): interface used to expose local implementations.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): example of intentionally managing concurrent mutable state.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): creating a snapshot that does not support list-level mutation when collection data needs to be captured safely.

**Conclusion:** a local class can use **a local variable or parameter** from its enclosing scope when that variable is `final` or **`effectively final`** and has been validly assigned. `effectively final` requires no keyword—only writing code that does not reassign the variable under JLS rules. When capturing a reference, the referenced object can still be mutable; therefore, manage aliasing, ownership, and concurrency separately. If a value needs to be computed across multiple steps, place **the completed result into a new variable** and capture that. When storing long-lived callbacks or using loops, clearly determine **the value for each invocation/iteration** and **the lifetime of captured objects**.
