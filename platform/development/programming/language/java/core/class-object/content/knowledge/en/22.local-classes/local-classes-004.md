# Distinguishing Capturing a Variable's Value from Modifying the Referenced Object's State

**Module:** Java Core – class/object  
**Group:** Local classes  
**Example environment:** Java 17+.

## 1. Core Takeaway Before Learning the Details

When a local class uses a local variable or parameter from the enclosing scope, the **captured** variable must be `final` or **effectively final**. For a primitive variable, the local class uses the primitive value. For a reference variable, the local class uses **the reference value pointing to the object**. There is no rule stating that the referenced object must be immutable.

Therefore, the following two operations are fundamentally different:

~~~java
StringBuilder text = new StringBuilder("A");

class Reader {
    String read() {
        return text.toString();
    }
}

text.append("B");             // VALID: modifies the object.
 // text = new StringBuilder("C"); // Invalid if uncommented.
~~~

This is **an illustrative code snippet inside a method**, not a standalone program. `text.append("B")` changes the object's content but does not reassign the local variable `text`. If the assignment `text = ...` is uncommented, `text` loses its effectively final status and the compiler does not allow Reader to capture it.

Rule to remember:

**Not reassigning a local variable captured by a local class** is a language restriction.  
**Not modifying the state of the referenced object** is a separate requirement, present only when dictated by the object/API/application design.

This lesson explains the capture mechanism across primitives/references, effectively final, aliasing, object lifetime, outer class fields, arrays and collections, snapshots versus live references, anonymous classes/lambdas, loops, concurrency, checking compile errors, and standalone runnable examples.

## 2. What Is a Local Class?

A local class is a class declared inside a block, commonly found inside a method or constructor:

~~~java
class Report {
    String format(String value) {
        String prefix = "Result";

        class Formatter {
            String render() {
                return prefix + ": " + value;
            }
        }

        return new Formatter().render();
    }
}
~~~

This is a **class fragment**, without `main`. `Formatter` is a local class. It uses `prefix` (a local variable) and `value` (a method parameter). Neither is reassigned after receiving its value, so both are effectively final.

A local class:

- Has a name in the local lexical scope, and is not a top-level public type.
- Can have instance fields, constructors, methods, and methods implementing interfaces.
- Can use locals/parameters from the enclosing scope that are eligible for capture.
- Can continue to exist after the method that declared it returns, if an instance remains reachable.
- Does not automatically create an immutable snapshot of all objects it references.
- Differs from a **non-static member inner class**, a class declared directly at the member level; and differs from a **static nested member class**.

The fact that a local class can still use information after the enclosing method finishes does not mean the JVM must keep the method's stack frame intact. The compiler/runtime may implement captured values in its own way; code must rely on **semantics**, not on synthetic field names.

## 3. Java Variables, Values, and Object Identity

For reference variables:

~~~java
StringBuilder a = new StringBuilder("A");
StringBuilder b = a;
b.append("B");
System.out.println(a); // AB
~~~

The two variables `a` and `b` hold the same **reference value** and point to the same object:

~~~text
a ──┐
    ├──> StringBuilder object "A" ── append ──> "AB"
b ──┘
~~~

The assignment `b = a` copies the reference value, not the object. This is **aliasing**.

For primitives:

~~~java
int a = 4;
int b = a;
b++;
System.out.println(a); // 4
System.out.println(b); // 5
~~~

The primitive variables `a` and `b` have independent values. There is no shared `int object` such that `b++` would change `a`.

### 3.1. Implications When Capturing

If a local class captures `int offset = 4`, it can use the value 4 when running its method. If a local class captures `StringBuilder text`, it holds a reference to the same mutable StringBuilder object that the caller or enclosing code can continue modifying.

Therefore, a reference value remaining stable **does not mean the referent's state always remains stable**.

### 3.2. `final` Does Not Mean Immutable

~~~java
final StringBuilder builder = new StringBuilder("A");
builder.append("B");       // Valid.
builder.setCharAt(0, 'C');  // Valid.
// builder = new StringBuilder(); // Invalid.
~~~

`final` forbids reassigning the local variable `builder`. It does not forbid StringBuilder methods from modifying its internal character sequence.

The same applies to:

- `final List<String> list = new ArrayList<>();` and then `list.add(...)`.
- `final int[] numbers = {1};` and then `numbers[0]++`.
- `final Map<String,Integer> map = new HashMap<>();` and then `map.put(...)`.
- `final MutableBox box = new MutableBox(1);` and then `box.value = 2`.

With a local class, a variable might not be declared with the `final` keyword and still be **effectively final** if it satisfies the rules regarding assignments.

## 4. Definition of Effectively Final

A local variable or method/constructor parameter is *effectively final* when, according to Java's rules, the variable is not impermissibly reassigned after being appropriately initialized. The compiler examines the entire flow of the program, not just a few lines before the local class.

Valid:

~~~java
int base = 10;

class Adder {
    int add(int x) {
        return x + base;
    }
}
~~~

`base` is assigned once and never changed, so Adder can read it.

Intentionally **does not compile**:

~~~java
int base = 10;

class Adder {
    int add(int x) {
        return x + base;
    }
}

base = 20; // No longer effectively final.
~~~

Even though the assignment occurs after the class declaration, the reassignment causes the captured variable to no longer be effectively final. There is no exception such as "assigning only after creating the local-class object is allowed".

Operations such as `base++`, `++base`, `base += 1`, or `base = base + 1` all change the local variable itself and can cause capture to be rejected by the compiler.

### 4.1. Does Not Need to Be a Compile-Time Constant

~~~java
int base = Integer.parseInt("7");

class Adder {
    int add(int x) {
        return x + base;
    }
}
~~~

Valid if base is not reassigned. The result of `Integer.parseInt` is computed at runtime, not as a constant expression; *effectively final* is different from *compile-time constant*.

### 4.2. Some Variables Without an Initializer Can Still Be Effectively Final

~~~java
int selected;
if (flag) {
    selected = 10;
} else {
    selected = 20;
}

class Reader {
    int read() {
        return selected;
    }
}
~~~

This is a **fragment** assuming `flag` has already been declared. The paths assign selected appropriately before use; under the rules for definite assignment/effectively final, this approach can be valid. Do not assume that only variables with an initializer directly at the declaration can be captured.

### 4.3. Capture Does Not Turn a Reference Variable into an Immutable Object

~~~java
List<String> values = new ArrayList<>();

class Reader {
    int size() {
        return values.size();
    }
}

values.add("A");   // Valid.
 // values = new ArrayList<>(); // Invalid if uncommented.
~~~

Changing the contents of the List is not the same as reassigning `values`.

## 5. Complete Program 1 — Captured Primitive and Mutable Reference

File **`CaptureValuesDemo.java`**:

~~~java
public class CaptureValuesDemo {
    public static void main(String[] args) {
        int version = 17;
        StringBuilder text = new StringBuilder("A");

        class Reader {
            String read() {
                return "version=" + version + ", text=" + text;
            }
        }

        Reader reader = new Reader();
        System.out.println("Before = " + reader.read());

        text.append("B");
        System.out.println("After append = " + reader.read());

        StringBuilder alias = text;
        alias.append("C");
        System.out.println("After alias = " + reader.read());

        System.out.println("Same reference = " + (alias == text));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CaptureValuesDemo.java
java CaptureValuesDemo
~~~

**Exact stdout:**

~~~text
Before = version=17, text=A
After append = version=17, text=AB
After alias = version=17, text=ABC
Same reference = true
~~~

**Explanation:**

1. `version` is an effectively final int. Reader uses 17.
2. `text` is an effectively final reference and is not reassigned.
3. `text.append("B")` modifies the mutable object.
4. `alias = text` creates a second reference variable pointing to the same object.
5. `alias.append("C")` continues to modify the object that Reader reads.
6. `alias == text` is true because they have the same identity; the local class does not automatically create a copy of the StringBuilder.

If you need to capture the text content at the exact moment Reader is created, you must create a String snapshot or another suitable representation, rather than relying solely on effectively final.

## 6. Complete Program 2 — Shared List Modified from Both Sides

File **`LocalListSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LocalListSharingDemo {
    public static void main(String[] args) {
        int id = 7;
        List<String> tags = new ArrayList<>(List.of("red"));

        class TagReader {
            String read() {
                return id + ":" + tags;
            }

            void add(String value) {
                tags.add(value);
            }
        }

        TagReader reader = new TagReader();

        System.out.println("Initial = " + reader.read());

        tags.add("blue");
        System.out.println("Outside mutation = " + reader.read());

        reader.add("green");
        System.out.println("Inside mutation = " + reader.read());
        System.out.println("Original list = " + tags);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocalListSharingDemo.java
java LocalListSharingDemo
~~~

**Exact stdout:**

~~~text
Initial = 7:[red]
Outside mutation = 7:[red, blue]
Inside mutation = 7:[red, blue, green]
Original list = [red, blue, green]
~~~

`tags` is not reassigned, so the capture is valid. However, the List is still mutable. `tags.add` outside and `reader.add` inside the local class modify **the exact same List**, so the contents are updated in both places.

### 6.1. What If the List Is Unmodifiable?

~~~java
List<String> tags = List.of("red");

class Reader {
    void add() {
        tags.add("blue");
    }
}
~~~

This is a fragment that can **compile**, because tags is effectively final. However, if Reader.add is called, the List created by the `List.of` method will throw `UnsupportedOperationException` when `add` is invoked. This is **runtime API behavior**, not a capture compile error.

### 6.2. Does `final` Protect the List's Contents?

No. `final` and effectively final control variable reassignment; whether the List is mutable or unmodifiable is determined by the List object and API.

## 7. Comparing Variable Reassignment Expressions and Object Mutation

| Expression | Reassigns captured local variable? | Conclusion when the variable is captured |
| --- | --- | --- |
| `int count = 1;` | Variable initialization | Can be captured if not reassigned |
| `count++;` | Yes | Invalid for a captured local |
| `count += 1;` | Yes | Invalid for a captured local |
| `list = new ArrayList<>();` | Yes | Invalid if list is not effectively final |
| `list.add("x");` | No | Valid for capture; depends on List mutability |
| `builder.append("x");` | No | Valid for capture |
| `builder = new StringBuilder();` | Yes | Invalid for that capture |
| `array[0]++;` | Does not reassign array variable | Valid if index/type are valid |
| `array = new int[3];` | Yes | Invalid for a captured local |
| `box.value++;` | Does not reassign box variable | Valid if the field is accessible/mutable |
| `map.put(key, value);` | Does not reassign map variable | Valid if the Map supports put |
| `owner.counter++;` | Changes an object field | Not subject to the local-capture rule for the owner reference |

A practical tip: look at **the target being updated**. `box.value++` updates a field, whereas `box++` is not valid for an object reference; `number++` updates the primitive local variable itself. Both syntax and data type matter.

## 8. A Local Class Instance Can Outlive the Method

A local class can implement an interface and be returned through an interface reference. Even after the method that created the class finishes, the object can still use the captured values.

File **`CaptureLifetimeDemo.java`**:

~~~java
public class CaptureLifetimeDemo {
    static Runnable create(String label, StringBuilder buffer) {
        int lengthAtCreation = buffer.length();

        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        label + "|" + lengthAtCreation + "|" + buffer);
            }
        }

        return new Task();
    }

    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        Runnable task = create("job", source);

        source.append("B");
        task.run();

        source.append("C");
        task.run();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CaptureLifetimeDemo.java
java CaptureLifetimeDemo
~~~

**Exact stdout:**

~~~text
job|1|AB
job|1|ABC
~~~

### 8.1. Analyzing the Three Captured Values

- `label` is a reference parameter to the immutable String `"job"`.
- `lengthAtCreation` is the primitive int value 1 determined before create returns.
- `buffer` is a reference parameter to the mutable StringBuilder that the caller's `source` also references.

After create finishes, lengthAtCreation is still used by Task as 1. However, buffer still points to the object that source is mutating, so the text changes from AB to ABC.

### 8.2. Lifetime of Captured Objects

A still-reachable Task can continue keeping the StringBuilder (and any mutable child objects reachable from it) alive longer than the execution time of the create method. The garbage collector considers object reachability, not just when the local method finishes.

This is why care is needed when capturing a very large List, a domain aggregate containing many objects, or a resource owner with a special lifecycle.

### 8.3. Do Not Depend on Compiler-Generated Fields

The compiler may store captured values using synthetic fields/constructor arguments in the generated class. Details such as field names are not a public contract for the application. What you should rely on is that Task can use the captured values without needing the original stack frame to remain active.

## 9. Outer Instance Fields Are Not Restricted Like Captured Locals

A local class defined inside an instance method can access fields of the enclosing instance if scope and access permit. These fields **are not local variables**, so they can change without causing the compiler to report an effectively final error.

File **`OuterFieldCaptureDemo.java`**:

~~~java
public class OuterFieldCaptureDemo {
    static final class CounterOwner {
        private int count;

        Runnable createTask() {
            int step = 2;

            class Task implements Runnable {
                @Override
                public void run() {
                    count += step;
                    System.out.println("Count = " + count);
                }
            }

            return new Task();
        }

        int current() {
            return count;
        }
    }

    public static void main(String[] args) {
        CounterOwner owner = new CounterOwner();
        Runnable task = owner.createTask();

        task.run();
        task.run();

        System.out.println("Owner state = " + owner.current());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OuterFieldCaptureDemo.java
java OuterFieldCaptureDemo
~~~

**Exact stdout:**

~~~text
Count = 2
Count = 4
Owner state = 4
~~~

`step` is a captured local primitive and is not reassigned. `count` is a field of the CounterOwner object. `count += step` modifies the **instance field**, not the local variable step. Both Task.run calls mutate owner.count from 0 to 2 and then to 4.

### 9.1. Instance Context Versus Static Context

A local class in an instance method can use outer instance state according to the rules. A local class in a static method **does not have an automatic enclosing outer instance**; to access an instance field, it must have an explicit object reference.

### 9.2. Static Fields Are Also Not Captured Locals

A static field belongs to the runtime class and is not constrained by the effectively final requirement like a local variable of the enclosing method. However, static mutable state has different scope and concurrency behavior; you should not turn a local variable into a static field just to avoid a compile error.

## 10. Holder Objects for Mutable State: Valid but With Trade-Offs

To have a counter change across invocations of a local class method, you can use a mutable holder:

~~~java
int[] counter = {0};

class Task {
    int next() {
        return ++counter[0];
    }
}
~~~

`counter` is effectively final because it holds an unchanged array reference. `counter[0]` is a modifiable array element. This approach complies with the capture rule, but it introduces **shared mutable state**.

File **`CapturedHolderDemo.java`**:

~~~java
public class CapturedHolderDemo {
    public static void main(String[] args) {
        int[] counter = {0};
        StringBuilder log = new StringBuilder();

        class Counter {
            int next() {
                int value = ++counter[0];
                log.append(value).append(";");
                return value;
            }
        }

        Counter counterObject = new Counter();

        System.out.println("First = " + counterObject.next());
        System.out.println("Second = " + counterObject.next());
        System.out.println("Counter = " + counter[0]);
        System.out.println("Log = " + log);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CapturedHolderDemo.java
java CapturedHolderDemo
~~~

**Exact stdout:**

~~~text
First = 1
Second = 2
Counter = 2
Log = 1;2;
~~~

**Note:** a single-element array is not thread-safe on its own, provides no synchronization, and is usually less expressive than a state object with a named API. If the counter belongs to an object, a field of that object may be a better choice. If an atomic counter across threads is needed, consider `AtomicInteger`.

## 11. A Captured Reference Does Not Mean a Content Snapshot

Suppose a local class needs to print a list **according to its state at the time the task is created**, while the source may change.

If it captures the mutable List directly, the task sees subsequent changes. If an immutable structural snapshot is taken, the task can use the initial state.

File **`CaptureSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CaptureSnapshotDemo {
    public static void main(String[] args) {
        List<String> live = new ArrayList<>(List.of("A"));
        List<String> snapshot = List.copyOf(live);

        class Observer {
            void print() {
                System.out.println("Live = " + live);
                System.out.println("Snapshot = " + snapshot);
            }
        }

        Observer observer = new Observer();

        live.add("B");
        observer.print();

        System.out.println("Same object = " + (live == snapshot));

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot unmodifiable");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CaptureSnapshotDemo.java
java CaptureSnapshotDemo
~~~

**Exact stdout:**

~~~text
Live = [A, B]
Snapshot = [A]
Same object = false
Snapshot unmodifiable
~~~

### 11.1. Both Variables Are Effectively Final

`live` and `snapshot` are not assigned new references, so Observer captures both. The difference is **the object each variable points to**:

- `live` is a mutable ArrayList that continues to be modified.
- `snapshot` is an unmodifiable structural snapshot created by `List.copyOf`.

### 11.2. `List.copyOf` Does Not Deep-Copy Elements

In this program, the List contains immutable Strings, so the snapshot is suitable. If the List contained MutablePerson instances, the snapshot List could still share the MutablePerson objects; someone else modifying a Person would affect the data observed through the snapshot.

When you want a deeper snapshot, you must copy the mutable elements or use immutable value DTOs.

### 11.3. An Unmodifiable View Is Not Necessarily a Snapshot

`Collections.unmodifiableList(live)` returns a view that cannot be modified through the view itself, yet it can still reflect additions or removals on the backing `live` list. Do not equate an unmodifiable view with an independent structural snapshot. `List.copyOf(live)` meets the goal in the example if null/elements are suitable.

### 11.4. Snapshotting a StringBuilder

If you want to capture the text at the time the task is created:

~~~java
StringBuilder builder = new StringBuilder("A");
String fixedText = builder.toString();

class Reader {
    String read() {
        return fixedText;
    }
}
~~~

Now modifying builder afterward does not change fixedText because String is immutable. There is no need to copy the entire StringBuilder if you only care about the String content at creation time.

## 12. Capturing in Loops

A common scenario is creating multiple local class objects inside a loop.

### 12.1. A Basic-for Index Is Not Effectively Final With `i++`

~~~java
for (int i = 0; i < 3; i++) {
    class Job {
        int index() {
            return i; // Intentionally does not compile.
        }
    }
}
~~~

`i` is incremented on each iteration, so it is not effectively final.

The right way is to create a separate local variable in each iteration:

~~~java
for (int i = 0; i < 3; i++) {
    final int index = i;

    class Job {
        int index() {
            return index;
        }
    }

    tasks.add(new Job());
}
~~~

This is a fragment assuming `tasks` has already been declared with an appropriate type. Each `index` during a single execution of the loop body is assigned once and holds that iteration's value.

### 12.2. Enhanced-for Variable

An enhanced-for iteration variable has per-iteration semantics; if it is not reassigned in the body, it can be captured by a local class. Do not infer that a basic-for `i` and an enhanced-for `item` have the same assignment rules.

### 12.3. Complete Program — Separate Captured Values per Iteration

File **`LoopCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    interface Printable {
        void print();
    }

    public static void main(String[] args) {
        List<Printable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            final int index = i;

            class IndexPrinter implements Printable {
                public void print() {
                    System.out.println("Index = " + index);
                }
            }

            tasks.add(new IndexPrinter());
        }

        for (String color : List.of("red", "blue")) {
            class ColorPrinter implements Printable {
                public void print() {
                    System.out.println("Color = " + color);
                }
            }

            tasks.add(new ColorPrinter());
        }

        for (Printable printer : tasks) {
            printer.print();
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
~~~

**Exact stdout:**

~~~text
Index = 0
Index = 1
Index = 2
Color = red
Color = blue
~~~

Each IndexPrinter object holds its own index from the iteration that created it. ColorPrinter also uses the value of the enhanced-for variable in the corresponding iteration. This Java demo does not exhibit the issue where every IndexPrinter reads basic-loop `i = 3` after the loop finishes, because `i` is not captured directly.

## 13. Local Class, Anonymous Class, and Lambda

All three forms can use local/parameter values from the enclosing scope, subject to the final/effectively final constraint:

~~~java
int factor = 2;
StringBuilder text = new StringBuilder("A");
~~~

**Local class:**

~~~java
class Printer implements Runnable {
    public void run() {
        System.out.println(factor + ":" + text);
    }
}
~~~

**Anonymous class:**

~~~java
Runnable anonymous = new Runnable() {
    public void run() {
        System.out.println(factor + ":" + text);
    }
};
~~~

**Lambda:**

~~~java
Runnable lambda = () ->
        System.out.println(factor + ":" + text);
~~~

The three fragments share a suitable enclosing scope. None of the forms automatically deep-copies the StringBuilder. If text.append("B") is executed before running, all of them can print `2:AB`.

### 13.1. Differences in `this`

- In an instance method of a local/anonymous class, `this` refers to the executing inner-class instance.
- In a lambda, `this` has the lexical semantics of the enclosing context; there is no lambda-specific `this` as in an anonymous class.
- In a static enclosing context, there is no implicit enclosing instance this to reference freely.

This difference matters when code both reads captured locals and accesses outer instance fields. However, **the final/effectively final restriction on captured local variables** remains a common rule.

## 14. Complete Program — Three Forms Observing the Same Object

File **`LocalAnonymousLambdaDemo.java`**:

~~~java
public class LocalAnonymousLambdaDemo {
    public static void main(String[] args) {
        int factor = 2;
        StringBuilder shared = new StringBuilder("A");

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println("Local = " + factor + ":" + shared);
            }
        }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("Anonymous = " + factor
                        + ":" + shared);
            }
        };

        Runnable lambda = () ->
                System.out.println("Lambda = " + factor + ":" + shared);

        shared.append("B");

        new LocalTask().run();
        anonymous.run();
        lambda.run();
    }
}
~~~

Command:

~~~bash
javac -encoding UTF-8 LocalAnonymousLambdaDemo.java
java LocalAnonymousLambdaDemo
~~~

**Exact stdout:**

~~~text
Local = 2:AB
Anonymous = 2:AB
Lambda = 2:AB
~~~

All three hold the primitive factor and the same StringBuilder reference. The append mutation gives the shared object the content AB; there is no reassignment of any captured variable.

## 15. Concurrency: Effectively Final Does Not Mean Thread-Safe

If a local class captures a mutable object and the task runs on other threads, the fact that the local reference is not reassigned **does not protect mutations** of the object.

Example:

~~~java
int[] counter = {0};

class Task implements Runnable {
    public void run() {
        counter[0]++;
    }
}
~~~

If multiple threads run the same Task or multiple Tasks capture the same array, `counter[0]++` is a non-atomic read-modify-write operation and updates can be lost. An effectively final `counter` only keeps the reference value stable.

### 15.1. AtomicInteger Provides Appropriate Operations

File **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        int step = 2;
        AtomicInteger total = new AtomicInteger();

        class Worker implements Runnable {
            @Override
            public void run() {
                total.addAndGet(step);
            }
        }

        Runnable task = new Worker();
        Thread one = new Thread(task);
        Thread two = new Thread(task);

        one.start();
        two.start();

        one.join();
        two.join();

        System.out.println("Total = " + total.get());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

**Exact stdout:**

~~~text
Total = 4
~~~

`total` is an effectively final reference to AtomicInteger. Both threads use `addAndGet(2)`, an atomic operation according to the API; main waits for both using `join` before reading. The result 4 does not depend on which thread runs first.

### 15.2. Atomic State Differs from a Reassignable Local Variable

`AtomicInteger` allows changing **the object's state via a thread-safe API**, which does not mean Java allows reassigning the local `total` after capture.

### 15.3. Remaining Issues

A complex object with multiple fields sharing an invariant may still require locking, immutable state replacement, or another protocol. `AtomicInteger` does not automatically make an entire object graph thread-safe. Nor do `volatile` or `final` references automatically guarantee proper memory visibility for all mutable child fields.

## 16. Parameter Capture and Reassignment

Method parameters used from a local class must be effectively final under the same rules as captured locals.

Valid:

~~~java
static Runnable create(String label) {
    class Task implements Runnable {
        public void run() {
            System.out.println(label);
        }
    }
    return new Task();
}
~~~

Intentionally does not compile:

~~~java
static Runnable invalid(String label) {
    class Task implements Runnable {
        public void run() {
            System.out.println(label);
        }
    }
    label = label.trim(); // Changes a captured parameter.
    return new Task();
}
~~~

A readable approach is to create a new snapshot/normalized local:

~~~java
static Runnable normalized(String input) {
    String value = input.trim();

    class Task implements Runnable {
        public void run() {
            System.out.println(value);
        }
    }
    return new Task();
}
~~~

The snippets above are **method fragments**, not standalone files.

For a reference parameter such as `List<String> items`, `items.add("X")` modifies the object without **reassigning the parameter items**; the class can capture items if the variable remains effectively final. You need to check whether the List is mutable and whether the API allows add.

## 17. Shadowing: Which Variable Is Read When Names Collide?

A local class can declare a field with the same name as a local variable of the method. Name lookup inside the class body may select the field, rather than the expected local variable.

~~~java
void demo() {
    int initial = 10;

    class Reader {
        int current = 20;

        int sum() {
            return initial + current;
        }
    }

    System.out.println(new Reader().sum()); // 30
}
~~~

This is a method fragment using two distinct names so it is unambiguous: `initial` is the captured local, and `current` is the instance field.

If both are named `value`, the expression `value` inside the class can refer to the class's own field due to shadowing. There is no syntax like `method.this.value` to turn a method's local variable into an outer field. `Outer.this` specifies an enclosing **instance** when valid, not a local activation record. Using distinct names or creating an effectively final alias with a different name is a maintainable approach.

## 18. Common Mistakes to Distinguish Properly

1. **Reassigning a captured local:** compile-time effectively final error.
2. **Mutating a captured List:** may be valid with respect to capture, but if the List is unmodifiable, it throws UnsupportedOperationException at runtime.
3. **Reassigning a captured method parameter:** compile-time error if the parameter is not effectively final.
4. **`counter++` on a captured local primitive:** capture error; different from `box.value++`.
5. **`array[0] = ...`:** mutates an array element without changing the local reference; can be valid.
6. **Using a static field just to bypass the rule:** the code may compile, but scope/lifetime and concurrency semantics change.
7. **Assuming a final reference means an immutable object:** a mutable referent still changes.
8. **Assuming a local class copies the object on capture:** Java does not automatically deep-copy objects.
9. **Assuming List.copyOf deep-copies elements:** it copies the structure; mutable elements can still be shared.
10. **Using Collections.unmodifiableList(source) as a snapshot:** it is a view that can reflect source mutations.
11. **Capturing basic-for i with i++:** i is not effectively final; use a per-iteration snapshot.
12. **Running a task after the method and thinking captured values are lost:** the task can still use the captured values.
13. **Ignoring GC lifetime:** a returned closure-like object can keep a mutable graph reachable.
14. **Not synchronizing mutable shared state across threads:** effectively final does not provide atomicity for the referent.
15. **Confusing an outer instance field with a captured local variable:** a field can change without violating the effectively final rule.
16. **Mixing up shadowed fields with locals:** accidentally reading a field instead of the captured variable.
17. **Assuming the compiler generates a synthetic field with a specific name:** that is not a stable public API.
18. **Confusing lambda lexical this with anonymous-class this:** the semantics differ even though capture rules are similar.
19. **Treating live sharing as always a bug:** it can be the intended design with a clear owner/contract.
20. **Assuming a snapshot always requires deep-copying everything:** immutable values can be shared safely.

## 19. Self-Check Exercises with Answers

**Question 1.** Can a local class capture a variable not declared `final`?

**Answer:** Yes, if the variable is effectively final and satisfies scope/definite assignment rules.

**Question 2.** When a StringBuilder variable is captured, is `append` allowed?

**Answer:** Yes; append modifies the object and does not reassign the captured variable.

**Question 3.** When a StringBuilder variable is captured, is assigning it to `new StringBuilder()` allowed?

**Answer:** No, if doing so makes the variable no longer effectively final.

**Question 4.** With `final List<String> names = new ArrayList<>()`, is calling `names.add` forbidden by final?

**Answer:** No; final forbids reassigning the reference, not mutating the List.

**Question 5.** Can a local class increment a captured local `int counter` using `counter++`?

**Answer:** No; modifying a local primitive variable violates effectively final.

**Question 6.** Can a local class increment `holder[0]` if holder is a captured int[]?

**Answer:** Yes for capture, because it modifies an array element rather than reassigning the holder variable; thread safety is a separate concern.

**Question 7.** Does copying a `StringBuilder` reference into another variable create a new StringBuilder object?

**Answer:** No; it creates an alias to the same object.

**Question 8.** When a primitive int is copied between two variables, do they share a mutable object?

**Answer:** No; int is a primitive value.

**Question 9.** Can a local class returned from a method still read a captured parameter?

**Answer:** Yes; the object retains the captured value according to Java semantics.

**Question 10.** If a parameter references a mutable StringBuilder and the caller modifies it after the method returns, will the local class see it?

**Answer:** It can see it because it is the same referent; capture does not create a snapshot.

**Question 11.** Does an outer instance field need to be effectively final for a local class to modify it?

**Answer:** No; the rule for capturing locals/parameters is different from accessing instance fields.

**Question 12.** Why is `count += step` in CounterOwner valid?

**Answer:** count is an owner instance field, and step is an effectively final captured local.

**Question 13.** Does a local class inside a static method automatically have Outer.this?

**Answer:** No, there is no implicit outer instance.

**Question 14.** Does a captured mutable List always print its contents at the time of capture?

**Answer:** No. It can reflect subsequent mutations because it is the same object reference.

**Question 15.** What does `List.copyOf(source)` protect?

**Answer:** An unmodifiable structural snapshot; it does not deep-copy arbitrary mutable elements.

**Question 16.** Is `Collections.unmodifiableList(source)` always detached from source?

**Answer:** No; it is typically a view that reflects modifications to source through an alias.

**Question 17.** Does `List.of("A").add("B")` fail because of capture or because of the collection?

**Answer:** Because of the unmodifiable collection API, typically throwing UnsupportedOperationException when running add.

**Question 18.** Can a basic-for index `i` in `for (int i=0; i<3; i++)` be captured directly?

**Answer:** No, because i is incremented and is not effectively final.

**Question 19.** What is the way to capture the index for each iteration?

**Answer:** Create `final int index = i` inside the loop body and capture index.

**Question 20.** Can an enhanced-for variable be captured?

**Answer:** Yes, when it is not reassigned in the body and satisfies Java's rules for each iteration.

**Question 21.** Do lambdas and local classes have the same constraint regarding effectively final captured locals?

**Answer:** Yes; they differ in other semantics such as this.

**Question 22.** Is `this` inside a lambda the same as an anonymous class's this?

**Answer:** No; a lambda has lexical this semantics, whereas an anonymous class has its own instance this.

**Question 23.** Is a captured int[] automatically thread-safe?

**Answer:** No. `counter[0]++` is not automatically atomic.

**Question 24.** Can a captured AtomicInteger be used for concurrent increments?

**Answer:** Yes, through atomic APIs such as addAndGet, but not because the captured variable is effectively final.

**Question 25.** Why can a captured mutable object live longer than the enclosing method?

**Answer:** A still-reachable local-class object can continue holding a reference to the mutable referent.

**Question 26.** Should you use a static counter just to bypass the compiler capture rule?

**Answer:** Generally no; static state carries different scope, lifetime, and concurrency behavior.

**Question 27.** When a field and a local have the same name, does an unqualified identifier always refer to the captured local?

**Answer:** No; field shadowing/name resolution can select the field.

**Question 28.** When you want a task to use a StringBuilder's text at creation time, what should you capture?

**Answer:** Capture an immutable String snapshot from `builder.toString()`.

**Question 29.** When you want a task to always read the latest List, what can you capture?

**Answer:** A mutable List reference, if live sharing is the intended contract and ownership/thread safety are managed.

**Question 30.** What is the core distinction of this lesson?

**Answer:** A captured local variable must keep its variable value without reassignment; meanwhile, a mutable object that the reference points to can still change its state through aliases.

## 20. Code Review Checklist

1. In which scope is the local class declared?
2. Which local variables/parameters are captured?
3. Are they final or effectively final?
4. Is there any reassignment/`++`/`+=` on the captured local itself?
5. Is the captured type a primitive or a reference?
6. If it is a reference, is the object mutable?
7. Are there other aliases that can modify the object?
8. Do you want live updates or a fixed snapshot?
9. If a snapshot is desired, has a defensive copy been made at the boundary?
10. Do nested mutable elements require a deep copy?
11. Is an unmodifiable view being mistaken for a snapshot?
12. Are String/Instant or immutable value types used to reduce copying?
13. Is a local-class object returned from the method and extending data lifetime?
14. Is an outer instance field being misunderstood as a captured local?
15. Is a static context missing an enclosing instance?
16. Are basic-for indices snapshotted per iteration?
17. Is the enhanced-for variable reassigned?
18. Are there shadowed field/local names?
19. Is there a holder array used merely to bypass the compiler while creating hidden mutable state?
20. Does the captured mutable object run across multiple threads?
21. Are the necessary atomic/locking/safe-publication protocols in place?
22. Are compile-time capture errors distinguished from runtime collection errors?
23. Do tests modify the object after capture and then read from the local class?
24. Do tests prove that the snapshot does not change when the source changes?
25. Are ownership, live state, and object lifetime clearly documented?

## Conclusion

A Java local class **captures the value of a local variable/parameter**; it does not automatically freeze every object that the variable references. For a primitive, the captured value is a primitive value; for a reference type, the captured value is a reference to the object. The `final`/*effectively final* rule controls **reassignment of the local variable**, and does not prevent methods such as `list.add`, `builder.append`, or assignments to fields/array elements from modifying the referent's state.

If the application needs to update state through a local class, use an owner/holder with a clear mutation contract and handle concurrency if needed. If fixed state at task creation time is needed, snapshot it into immutable values or appropriate defensive copies. Always distinguish **variable**, **reference value**, **object identity**, **mutable state**, and **lifetime**; this is the key to properly understanding capture in local classes, anonymous classes, and lambdas in Java 17+.
