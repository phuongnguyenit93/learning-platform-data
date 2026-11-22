# Using a Debugger to Observe this, Fields, Parameters, and Objects in Java 17+

> **Module:** Java Core — class/object  
> **Group:** Design and Practice  
> **Direct Topic:** Using a debugger to observe `this`, fields, parameters, and objects  
> **Environment:** JDK 17+; instructions for using an IDE debugger or `jdb` included in the JDK.

## 1. Learning Outcomes

After this lesson, learners can **pause a program at a specific statement, select a stack frame, view the current values of `this`, fields, parameters, local variables, and related objects**, and then track changes when stepping through each statement.

The most important scenarios:

- In the constructor `Person(String name)`, distinguish the **parameter `name`** from the **field `this.name`**.
- In the method `account.deposit(int amount)`, see that `this` points to the **account receiving the call**; each call on a different object has a different `this`.
- When a method receives a parameter of a class type, see that the parameter is a **copy of the reference value**: you can modify the object through that reference, but reassigning the parameter to a new object does not change the caller's reference variable.
- See which methods are active on the **call stack** and which variables belong to which **frame**.
- Know when to use **Step Over**, **Step Into**, **Step Out**, **Resume**, **Variables**, **Watches**, and **Evaluate Expression**.
- Read the **object graph** through the debugger: which object a field points to; whether two references point to the same instance.
- Avoid mistakenly thinking a **static field** is each individual object's own field, and avoid believing that every getter/toString call in the debugger is always harmless.
- Use `javac -g` to preserve **local variable debug information**, and then carry out a reproducible `jdb` hands-on session without depending on a single IDE.

**A debugger lets you observe one specific execution; it does not by itself prove that every other execution has the same data or the same thread ordering.** It must be combined with knowledge of Java semantics, assertions, and tests.

## 2. How Does a Debugger Differ from System.out.println?

`System.out.println` provides logs at pre-written locations. A debugger lets you set a **breakpoint** to pause right before/after an appropriate step in the program, inspect the available variables, and then continue statement by statement.

| Need | Print/log | Debugger |
| --- | --- | --- |
| View a field at a known place | Add a print statement | Select stack frame, open object fields |
| Know which method called the running method | Add a log or stack trace | View Call Stack/Frames directly |
| View a local variable in a method | Must modify source/logs | Variables pane or `jdb`'s `locals` |
| See the difference between same-named field/parameter | Print both `name` and `this.name` | Same frame, view both expressions |
| Enter a called method | Insert extra logs inside the callee method | Step Into |
| Skip details of a called method | Manually reduce logs | Step Over |
| Return to the caller | Add a log after the call | Step Out |
| Track object mutation through multiple aliases | Print multiple values | Inspect object graph and identity |
| Observe another thread | Manually insert thread ID logs | Threads/Frames pane or `threads` in `jdb` |
| Store long-term production information | Yes, suitable for logs/telemetry | Does not replace production logging/monitoring |

Debugging is very useful when **learning Java Core**, because you can observe rules rather than only reading definitions. However, when a bug involves a race/concurrency condition or only appears in production, breakpoints can alter timing; logs, tests, profilers, and additional tools are needed.

## 3. Mental Model: Stack Frame, Local, Parameter, Field, and Object

Example:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int amount) {
        int before = value;
        value += amount;
        System.out.println(before + " -> " + value);
    }
}
~~~

This is a **class fragment**, without `main` yet.

Suppose the caller has `Counter first = new Counter(10)` and calls `first.add(3)`. When paused inside the `add` method, imagine:

~~~text
Call stack:
  [current frame] Counter.add(amount=3)
      this ------------> Counter object #A
      amount = 3        | value = 10 (before addition)
      before = 10       |
  [caller frame] SomeMain.main(...)
      first -----------> same Counter object #A

Heap (illustrative model):
  Counter object #A
      value: 10
~~~

**Relationships to remember:**

1. `this` is a reference to the **object receiving the instance method call**.
2. `amount` is a **local parameter of the current invocation**, not a field.
3. `before` is a **local variable** in the current frame, existing according to the method's scope/liveness.
4. `value` is an **instance field** located inside object #A; multiple method calls on the same object act on that field.
5. `first` is a local variable of the **caller frame**, not a local of `add`.
6. The debugger displays frames so you can choose a context. To view `first`, switch to the caller frame; to view `amount`, select the `add` frame.
7. Labels such as object #A/#B are only illustrative notations, **not object IDs guaranteed by standard Java or RAM addresses that a debugger is required to print**.

### 3.1. A Field Is Not a Local Variable

A field belonging to an instance (`this.value`) exists with the object. A local variable (`before`) belongs to an invocation/scope. A second method call has a new local `before`, even though it still uses the same field value.

### 3.2. A Parameter Is Also a Local Variable of the Call

Each invocation has its own parameter value. If the Java method `add(int amount)` is called sequentially with 3 and then 5, the two calls do not share a single parameter slot carrying business state.

### 3.3. An Object Can Be Referenced by Multiple Frames

If the caller holds `first` while the callee holds `this`, the two references can point to the same object. The debugger displays them in different frames, yet mutations go to the same heap object.

### 3.4. Do Not Interpret Debugger Views as an Absolute Heap Layout

IDEs often display fields, references, and object labels in their own format. This is a **UI representation of Java values**. The JVM may optimize allocations, field layouts, references, and stack maps; do not treat object ID labels or positions in the Variables pane as a guaranteed binary memory layout.

## 4. Preparing the Environment for Debugging

You need a JDK 17 or later, not just a minimal JRE, to use `javac` and `jdb`.

Check in the terminal:

~~~bash
java -version
javac -version
jdb -help
~~~

The commands above are tool commands; the specific version, help text, and exit status depend on the installed JDK, so this lesson **does not provide a fixed stdout** for them.

### 4.1. Compiling with Sufficient Debug Information

~~~bash
javac -g -encoding UTF-8 DebuggerBasicsDemo.java
~~~

The `-g` flag tells the compiler to generate debugging information, including **source lines, source file, and local variable data** per `javac`'s standard options.

By default, javac usually already generates line number and source file information, but **does not necessarily generate local variable name tables**. Therefore, when you want to use `jdb locals` or view parameters by their original names in a debugger, you should **use `-g`**.

You can specify details explicitly:

~~~bash
javac -g:lines,vars,source -encoding UTF-8 DebuggerBasicsDemo.java
~~~

This is an example of a valid `javac` flag. With IDEs, the build system usually already configures debug symbols; check the build settings if local variable names do not appear.

### 4.2. Source Must Match the Running Class File

A very common mistake is editing the Java file but running/debugging an old `.class` file. Before starting, recompile the correct source and check the classpath/module path the IDE is using.

### 4.3. Prefer Debug Instead of Run in the IDE

In IntelliJ IDEA, Eclipse, the VS Code Java extension, or another IDE, choose the appropriate **Debug** configuration instead of Run. Set a breakpoint on an executable line. Button names and shortcuts may vary by version/keyboard scheme, but the concepts of Breakpoints, Frames, Variables, and Step commands are similar.

### 4.4. A Breakpoint Is Not a One-Time Statement in Source

A breakpoint is a request from the debugger; it does not directly alter Java source semantics the way adding `System.out.println` does. However, pausing the program can affect timing, lock contention, and interactions with other threads.

## 5. Complete Program 1 — this, Shadowed Fields, and Parameters

Create the file **`DebuggerBasicsDemo.java`**:

~~~java
public class DebuggerBasicsDemo {
    static final class Meter {
        private int count;

        Meter(int count) {
            this.count = count;
        }

        int add(int count) {
            int before = this.count;
            this.count = Math.addExact(this.count, count);
            return before;
        }

        int count() {
            return count;
        }
    }

    public static void main(String[] args) {
        Meter first = new Meter(10);
        Meter second = new Meter(100);

        int beforeFirst = first.add(3);
        int beforeSecond = second.add(5);

        System.out.println("First before = " + beforeFirst);
        System.out.println("First now = " + first.count());
        System.out.println("Second before = " + beforeSecond);
        System.out.println("Second now = " + second.count());
        System.out.println("Different objects = " + (first != second));
    }
}
~~~

Compile and run normally:

~~~bash
javac -g -encoding UTF-8 DebuggerBasicsDemo.java
java DebuggerBasicsDemo
~~~

**Exact stdout:**

~~~text
First before = 10
First now = 13
Second before = 100
Second now = 105
Different objects = true
~~~

### 5.1. Constructor Parameter Shadows the Field

In `Meter(int count)`, the expression `count` refers to the parameter by default. `this.count` refers to the field of the Meter being constructed. The statement `this.count = count` copies the parameter value into the field.

When the debugger pauses in the constructor, inspect **both `count` and `this.count`**. If paused before the assignment statement, the field `this.count` still has the default value 0; after Step Over executes the assignment, it has the value 10 or 100.

### 5.2. The Same Name in Method `add` Has Two Meanings

In `add(int count)`:

- `count`: the amount to add, which is a **parameter**.
- `this.count`: the current count stored on the object.
- `before`: a local copy of the field value before the update.

In the invocation `first.add(3)`, you see parameter=3 and field=10 before the update statement. In `second.add(5)`, parameter=5 and field=100. It is the same method body, but with two different receivers.

### 5.3. What Happens After Step Over

Set a breakpoint at:

~~~java
this.count = Math.addExact(this.count, count);
~~~

Before execution, `this.count` is still 10/100. After Step Over on that exact line, the field becomes 13/105. Parameter `count` remains 3/5; local `before` remains 10/100.

### 5.4. Why Is `first != second` true?

Two `new Meter` calls create two different object references according to the semantics of this program. `this` in the two calls is not the same, and changing the field on object first does not change the field on second.

## 6. Debugger Actions in an IDE: Workflow for Reading the Variables Pane

With the `DebuggerBasicsDemo` program:

1. Open the file and set a breakpoint at the statement `this.count = Math.addExact(...)` in `Meter.add`.
2. Choose **Debug** for the main class `DebuggerBasicsDemo`.
3. When the program pauses at the breakpoint, look at **Call Stack/Frames**. The current frame is `Meter.add`, and the caller is `DebuggerBasicsDemo.main`.
4. In **Variables**, find `this`, parameter `count`, and local `before`.
5. Expand `this` to see the field `count`.
6. Use **Evaluate Expression** or Watch to compare `count`, `this.count`, `before`, and `this == first` if the caller variable appears in an appropriate frame context. `first` is usually not visible when you have the `Meter.add` frame selected; to view `first`, select the `main` frame.
7. Choose **Step Over** to run the addition and observe the new field count.
8. Choose **Resume/Continue** to reach the `second.add(5)` call; compare `this` and the field.
9. Select the `main` frame while the program is paused, and observe that `first` and `second` exist at the same time.
10. Remove the breakpoint or continue until the end of the program.

**Note:** whether a step occurs before or after a side effect depends on **breakpoint placement and line mapping**. If you set a breakpoint on a statement, it usually pauses **before that statement completes**. When a single Java line compiles into multiple bytecodes, the IDE may step you through multiple positions depending on the stepping mode. Verify by checking the field before and after.

### 6.1. The Variables Pane and Watch Expressions Differ

The Variables pane usually lists the variables visible in the frame along with object fields. A Watch is an **expression you explicitly ask to evaluate**, for example `this.count` or `first == second`.

A Watch may be evaluated multiple times each time the program pauses; avoid expressions with side effects.

### 6.2. Do Not Evaluate a Parameter Name in the Caller Frame and Think It Is “Lost”

`count` in `Meter.add` belongs to the callee frame; when switching to `main`, that variable is not a local of main. Some IDEs display symbols from the current frame, so you must select the right frame before analyzing.

### 6.3. Object Labels in the Debugger Are Not equals Semantics

An IDE may display Meter@hash-like-label. That label is not a fixed business identity promised by Java. To check whether references are the same, use `==` between references; to check domain values, use the fields/accessors/equals according to the contract.

## 7. Practicing with jdb — the JDK Command-Line Debugger

If you do not use an IDE, you can use **`jdb`** to set breakpoints and view frames/variables.

Compile:

~~~bash
javac -g -encoding UTF-8 DebuggerBasicsDemo.java
~~~

Launch:

~~~bash
jdb DebuggerBasicsDemo
~~~

After jdb starts and displays the prompt, enter the commands **line by line inside jdb**:

~~~text
stop in DebuggerBasicsDemo$Meter.add
run
where
locals
print count
print this.count
print before
next
print this.count
cont
~~~

This is an **example of interactive usage**. Prompt/debugger diagnostics, line numbers, thread IDs, object IDs, and exact stopping locations **must not be treated as fixed stdout**. Nested class name syntax in bytecode typically uses `$`: `DebuggerBasicsDemo$Meter`.

### 7.1. `stop in`

`stop in DebuggerBasicsDemo$Meter.add` requests pausing when entering method add. You can also set a breakpoint by source line using the syntax `stop at ClassName:lineNumber` if you know the line mapping.

### 7.2. `run`

Runs the target program in the debug session. When a breakpoint is hit, jdb pauses and allows interaction.

### 7.3. `where`

Displays the stack trace of the current thread/frame. It helps show that execution is in `Meter.add` and who called it from `main`.

### 7.4. `locals`

Displays the local variables/arguments permitted by the debug information and frame state. If local names do not appear, check `javac -g`, the right class file, and the stopping location (before a variable is initialized, its value cannot yet be read reliably).

### 7.5. `print` and `dump`

`print count` evaluates the parameter/local expression; `print this.count` evaluates the field. `dump this` can be useful when inspecting object fields. Expression evaluation commands can interact with application code; only use safe expressions when troubleshooting.

### 7.6. `next`, `step`, `step up`, and `cont`

- `next`: steps over a call in the same frame (Step Over).
- `step`: steps into an eligible call (Step Into).
- `step up`: runs until leaving the current method (Step Out).
- `cont`: continues until another breakpoint/event.

Corresponding commands may pause at different points due to source maps, bytecode, exceptions, or other threads; the semantic model is the core point.

### 7.7. Distinguishing IDE Watch from jdb's `watch`

In an IDE, a Watch is usually an **evaluated expression**. In `jdb`, the `watch` command usually relates to **field access/modification watchpoints** (for example, `watch all Class.field`), **not** creating a Watch-expression pane. Do not learn a command from one tool and apply it to the other.

### 7.8. On Windows PowerShell

The command `jdb DebuggerBasicsDemo` runs normally if the JDK is in PATH. The string `DebuggerBasicsDemo$Meter.add` is **typed inside the jdb interactive prompt** in the example, so it is not interpolated by PowerShell as a variable. If you embed a name containing `$` into a shell command yourself, pay attention to shell-specific quoting.

## 8. Step Over, Step Into, Step Out: What Do You See?

Suppose:

~~~java
int total = calculatePrice(quantity, unitPrice);
System.out.println(total);
~~~

At a breakpoint on the line calling `calculatePrice`:

| Action | Meaning | Typically Expected Observation |
| --- | --- | --- |
| Step Into | Enter the called method | Frame `calculatePrice` and parameters appear |
| Step Over | Run the method as a unit and pause at the caller's next step | `total` has the return value |
| Step Out | From inside the callee, run until the callee returns to the caller | Caller frame becomes current again |
| Resume | Continue to the next breakpoint/event | The program runs through other statements |
| Pause/Suspend | Pause the running execution | May stop at an unpredictable location |
| Run to Cursor | Run to the user-selected location if execution reaches there | Used to skip detailed steps |
| Drop Frame/Restart Frame (if supported by the IDE) | Attempt to return to the previous frame | May **not undo side effects** that already occurred |

### 8.1. Step Into Can Enter JDK/Library Code

If debugging `Math.addExact`, Step Into may enter JDK internals when source is attached and the debugger does not filter it. If the goal is to view an object field before/after an update, Step Over is usually more appropriate.

### 8.2. Step Out Does Not “Undo” the Callee

It continues execution until the callee returns. Mutations to the heap inside the callee still persist; the caller continues with the updated object state.

### 8.3. Drop Frame Is Not a Transaction Rollback

Some IDEs support “Drop Frame” or “Restart Frame”, but prior calls to methods with side effects, I/O, increments, or DB updates **are not automatically rolled back**. Practice on test data when using powerful execution-control tools.

### 8.4. Choosing an Action Based on the Question You Are Asking

- “Are the parameter values passed into the method correct?” → Step Into + inspect the frame.
- “What does this calculation return?” → Step Over.
- “Who called me and which object are they holding?” → Stack + select the caller frame.
- “Why did the field change between two lines?” → Breakpoint before/after the mutation, then Step Over.
- “Does another method have a side effect?” → Step Into or a method breakpoint.

## 9. `this` Points to the Current Object, Not to the Class Name

In an instance method:

~~~java
class Wallet {
    private int amount;

    Wallet(int amount) {
        this.amount = amount;
    }

    void topUp(int amount) {
        this.amount += amount;
    }
}
~~~

`this` is a reference to the exact Wallet object receiving the call. If there are two wallets A/B, each call to `topUp` has a different `this`.

### 9.1. `this.field` Is Especially Useful When a Name Is Shadowed

`this.amount` always selects the receiver's field. The bare `amount` in `topUp(int amount)` selects the parameter due to shadowing. In the debugger, evaluate both to catch a bug like:

~~~java
amount = amount + amount;
~~~

The line above only modifies the local parameter, without changing the field. Code intended to increase the balance usually needs `this.amount = this.amount + amount` or `this.amount += amount`.

### 9.2. Not Every Bare Name Is a Parameter

If no local/parameter shadows the name, `amount` in an instance method can automatically refer to the field `this.amount`. To teach and check shadowing clearly, use `this.amount` in the source if there is a same-named parameter.

### 9.3. In a Constructor, this Points to the Object Being Initialized

The object already has a `this` reference when the constructor body runs, though subclass fields may not yet be finished initializing at certain stages. Do not call overridable methods from a superclass constructor and assume subclass state is already ready.

### 9.4. A Static Method Has No `this`

In `public static void main(String[] args)`, there is no instance receiver. You cannot write `System.out.println(this)` directly inside a static method. To inspect an object, view a local reference such as `wallet` or select an instance frame called from main.

## 10. Complete Program 2 — Shadowing Bug and Fix

File **`ShadowingDebugDemo.java`**:

~~~java
public class ShadowingDebugDemo {
    static final class Score {
        private int points;

        Score(int points) {
            this.points = points;
        }

        void wrongAdd(int points) {
            points = points + 5; // Only changes the parameter.
        }

        void rightAdd(int points) {
            this.points = this.points + points;
        }

        int points() {
            return points;
        }
    }

    public static void main(String[] args) {
        Score score = new Score(10);

        score.wrongAdd(3);
        System.out.println("After wrongAdd = " + score.points());

        score.rightAdd(3);
        System.out.println("After rightAdd = " + score.points());
    }
}
~~~

Compile and run:

~~~bash
javac -g -encoding UTF-8 ShadowingDebugDemo.java
java ShadowingDebugDemo
~~~

**Exact stdout:**

~~~text
After wrongAdd = 10
After rightAdd = 13
~~~

### 10.1. Suggested Breakpoints

Set breakpoints on `points = points + 5` and on `this.points = this.points + points`. In wrongAdd, track parameter `points` before/after: 3 → 8; field `this.points` remains 10.

### 10.2. In rightAdd

Parameter `points` is 3; field `this.points` before the update line is 10. After Step Over, the field becomes 13. The parameter does not change on its own.

### 10.3. Detecting the Bug with Two Watches

Add the two expressions `points` and `this.points` to Watches. If you only view one entry named points without knowing whether it is a local or a field, it is very easy to misunderstand the cause.

### 10.4. Scope of the Parameter

After the method returns, the frame and parameter `points` disappear; the object's field still holds the updated state. When the caller checks `score.points()`, it reads the object field, not the old parameter.

## 11. Java Always Passes by Value — Even When the Value Is a Reference

This is the topic most easily misunderstood by learners when using a debugger.

When calling:

~~~java
update(myBox);
~~~

and the parameter is `Box box`, Java **copies the value of the reference** `myBox` into the invocation's parameter `box`. Therefore, initially both references point to the **same object**. However, the **parameter variable** is a separate variable in the callee.

Two completely different operations:

1. `box.value = 20`: mutates the object referenced by both caller/callee; the caller sees the change.
2. `box = new Box(99)`: reassigns the parameter reference to another object; the caller's variable `myBox` still points to the original object.

Do not call Java “pass-by-reference” just because mutations through reference parameters are observed by the caller. The reference **value** is passed **by value**.

### 11.1. Why Should You Inspect Both the Caller's and Callee's Variables?

In the callee, you see `box` change its reference after the assignment; in the caller, you see `myBox` still holds the original object. Select two different stack frames to compare.

### 11.2. A Method Return Also Does Not Automatically Change the Caller Variable

A method can return a new reference; the caller only receives it if it **reassigns it**:

~~~java
myBox = replace(myBox);
~~~

If you call `replace(myBox)` and discard the result, the caller's reference does not change (unless replace has side effects on the original object).

## 12. Complete Program 3 — Mutation Through an Alias and Reassigning a Parameter

File **`ReferenceParameterDebugDemo.java`**:

~~~java
public class ReferenceParameterDebugDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(Box parameter) {
        parameter.value += 5;
        System.out.println("Inside changed = " + parameter.value);

        parameter = new Box(999);
        System.out.println("Inside reassigned = " + parameter.value);
    }

    public static void main(String[] args) {
        Box original = new Box(10);
        Box alias = original;

        change(alias);

        System.out.println("Original value = " + original.value);
        System.out.println("Alias value = " + alias.value);
        System.out.println("Still same object = "
                + (original == alias));
    }
}
~~~

Compile/run:

~~~bash
javac -g -encoding UTF-8 ReferenceParameterDebugDemo.java
java ReferenceParameterDebugDemo
~~~

**Exact stdout:**

~~~text
Inside changed = 15
Inside reassigned = 999
Original value = 15
Alias value = 15
Still same object = true
~~~

### 12.1. Breakpoint 1: Start of `change`

In the `change` frame, parameter points to the same Box object as `alias` and `original` in the caller frame. Field `value` is initially 10.

### 12.2. Breakpoint 2: After `parameter.value += 5`

The field on the original object becomes 15. Both caller references `original` and `alias` observe the new value if the code accesses it after the callee returns.

### 12.3. Breakpoint 3: After `parameter = new Box(999)`

The callee parameter points to a new object with value=999. The caller references still point to the old object with value=15. If the debugger displays object labels, you will see the parameter label change, while the caller labels do not change.

### 12.4. Variable Names Do Not Follow the Object

An object does not “know” whether it is named original, alias, or parameter. These are names of references in different frames/scopes. References can point to the same heap object or to different objects.

### 12.5. The Debugger Shows Aliases, but Does Not Change Pass-by-Value Semantics

Although both caller/callee see the same object for a period of time, the reference parameter is still a **copy of the reference value**. This is why reassigning the parameter does not propagate the assignment back to the caller.

## 13. Object Graph: Reading Reference Fields in the Variables Pane

When inspecting an object, not only read primitive fields, but also expand reference fields:

~~~text
main frame
  order  ---> Order
                id = "O-1"
                customer ---> Customer
                                 name = "Lan"
                lines ------> ArrayList
                                 [0] ---> Line
                                            sku = "BOOK"
                                            qty = 2
~~~

This is an **illustrative diagram**. IDEs may display the tree, nodes, collection size, and synthetic internals differently.

### 13.1. Two levels of nesting

An `Order` holding a `Customer` reference does not mean every Customer attribute lives inline inside Order. Expand the nested object to view Customer fields separately.

### 13.2. Watch Out for Reference Cycles

If Parent holds Child and Child holds Parent, the debugger may display the same object again cyclically. It usually has a mechanism to prevent infinite expansion, but do not conclude there are infinite objects just because the same object appears in multiple branches.

### 13.3. One Object Pointed to by Two Fields

If `order.billingAddress == order.shippingAddress`, the two fields share an object. A mutation through billingAddress can be observed through shippingAddress, if Address is mutable.

### 13.4. Where to Check Identity

To answer “is it the same object?”, evaluate `left == right`. For objects, `==` compares reference identity. Do not use `equals` if the question is object identity, because equals can be overridden to compare values.

### 13.5. Be Careful of Automatic toString() Calls in the IDE

Many IDEs allow customizing object display using `toString()` or renderers. That can execute application code at the pause point. If toString performs I/O/locking or mutates state, inspecting an object can cause side effects. Just expand raw fields when you want a purer evaluation.

## 14. Complete Program 4 — Reference Fields, Aliasing, and Defensive Copy

File **`ObjectGraphDebugDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ObjectGraphDebugDemo {
    static final class Item {
        String name;

        Item(String name) {
            this.name = name;
        }
    }

    static final class Cart {
        private final List<Item> items;

        Cart(List<Item> items) {
            this.items = new ArrayList<>(items);
        }

        List<Item> items() {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        Item item = new Item("Book");
        List<Item> source = new ArrayList<>();
        source.add(item);

        Cart cart = new Cart(source);

        System.out.println("Same element = "
                + (source.get(0) == cart.items().get(0)));

        item.name = "Notebook";
        System.out.println("Cart item name = "
                + cart.items().get(0).name);

        source.add(new Item("Pen"));
        System.out.println("Source count = " + source.size());
        System.out.println("Cart count = " + cart.items().size());
    }
}
~~~

Compile/run:

~~~bash
javac -g -encoding UTF-8 ObjectGraphDebugDemo.java
java ObjectGraphDebugDemo
~~~

**Exact stdout:**

~~~text
Same element = true
Cart item name = Notebook
Source count = 2
Cart count = 1
~~~

### 14.1. Why Is Same element true?

The Cart constructor copies the **List structure** but keeps **references to the Item objects**. `source.get(0)` and `cart.items().get(0)` still point to the same Item instance.

### 14.2. Why Does Cart See Notebook?

`item.name = "Notebook"` mutates the shared Item object. Although Cart copied the List, it did not deep-copy the Item elements.

### 14.3. Why Is Source count=2, Cart count=1?

The caller adds a new Item to the source list after Cart construction. Cart has its own ArrayList, so its structure does not change. This is an example of a **shallow copy**.

### 14.4. What Should the Debugger Inspect?

- `source`: size and element references.
- `cart`: field `items` pointing to a different List.
- `source.get(0) == cart.items().get(0)`: true.
- `item.name` through both paths: same value.
- Step over `source.add(...)`: the source list changes, the cart list does not change.

### 14.5. Value When Designing Domain Objects

Observing the object graph helps detect a getter returning a mutable internal collection or a constructor that only copies structure while containing mutable elements. Protecting object invariants requires clear ownership, not just private fields.

## 15. Static Fields Differ from Instance Fields When Viewing in a Debugger

A `static` field belongs to the **class**, not to each individual instance. IDE debuggers usually have a separate **Static Fields** section or allow evaluating `ClassName.field`. `this` only has meaning in an instance frame.

Example:

~~~java
class Ticket {
    static int created;
    final int id;

    Ticket() {
        created++;
        id = created;
    }
}
~~~

When two tickets are created sequentially, `Ticket.created` is shared and reaches 2. Fields `ticket1.id` and `ticket2.id` belong to each object, and can be 1 and 2 respectively.

### 15.1. Do Not Look at a Static Field Under a Single Object and Assume It Is Its Own State

Some IDEs display static members in the object view for convenience, yet the semantics remain class-level state. Evaluate `Ticket.created` instead of `ticket1.created` to reflect the true meaning.

### 15.2. A Static Method Has No `this` Receiver

In `main`, you can view `Ticket.created`, but there is no `this`. To view an instance id, inspect the variable `first` or `second`.

### 15.3. Shared Static Fields Also Have Race Conditions

If multiple threads increment `created++` together without synchronization, updates can be lost. The debugger pausing threads can mask a race; use a concurrent-safe design when needed, and do not draw conclusions from a single debug run alone.

## 16. Complete Program 5 — static vs instance fields

File **`StaticInstanceDebugDemo.java`**:

~~~java
public class StaticInstanceDebugDemo {
    static final class Ticket {
        static int created;

        final int id;
        int uses;

        Ticket() {
            created++;
            id = created;
        }

        void use() {
            uses++;
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket();
        Ticket second = new Ticket();

        first.use();
        first.use();
        second.use();

        System.out.println("Created = " + Ticket.created);
        System.out.println("First ID = " + first.id);
        System.out.println("Second ID = " + second.id);
        System.out.println("First uses = " + first.uses);
        System.out.println("Second uses = " + second.uses);
    }
}
~~~

Compile/run:

~~~bash
javac -g -encoding UTF-8 StaticInstanceDebugDemo.java
java StaticInstanceDebugDemo
~~~

**Exact stdout:**

~~~text
Created = 2
First ID = 1
Second ID = 2
First uses = 2
Second uses = 1
~~~

### 16.1. What to Look For When the Debugger Pauses in `use()`

`this` points to first/second in turn. `this.uses` changes independently on the receiver. `Ticket.created` does not change with `use()`, because that method does not create a new ticket.

### 16.2. Creating Two Objects Increments the Shared Counter

The constructor is called on each object and updates static Ticket.created. This is a single-thread example so that IDs are deterministic, not a production-ready concurrent ID generator.

### 16.3. What If a Java Class Is Reloaded by a Different Classloader?

Class identity and static state are tied to the class loader. A single JVM can have distinct copies of the “same class name” across different loaders. You do not need to handle this in a basic debugging lesson, but when debugging modular/plugin applications, check the classloader if static state differs from expectations.

## 17. Constructor Debugger: Default Fields and Initialization Order

An object's instance fields are initialized according to Java initialization rules. In a constructor chain, the debugger helps show when each field has been assigned.

Example of a child class extending a parent class:

~~~java
class Base {
    protected int baseValue;

    Base(int n) {
        this.baseValue = n;
    }
}

class Child extends Base {
    private int childValue = 2;

    Child(int n) {
        super(n);
        this.childValue = n * 2;
    }
}
~~~

These are fragments.

### 17.1. When Paused Inside the Base Constructor

`this` still points to the final object being created (the Child instance), yet Child-specific initialization may not be finished yet. The debugger may allow expanding `this` to see subclass fields still at their default values.

### 17.2. When Returning to the Child Constructor

After the superclass constructor, Java proceeds through Child's instance field initializers/instance initializer blocks and then the constructor body in standard order. If you Step over the assignment `childValue = n * 2`, you will see the field change.

### 17.3. Do Not Call an Overridable Method from a Constructor Just to Print Diagnostics

A superclass constructor calling a method can dispatch to a subclass override before subclass fields are fully initialized, creating confusing bugs. The debugger can help observe that, but you should not intentionally design constructors around this behavior.

## 18. Complete Program 6 — Stepping Through a Constructor Chain

File **`ConstructorStepDemo.java`**:

~~~java
public class ConstructorStepDemo {
    static class Base {
        int baseValue;

        Base(int value) {
            System.out.println("Base field initially = " + baseValue);
            baseValue = value;
            System.out.println("Base field after = " + baseValue);
        }
    }

    static final class Child extends Base {
        int childValue = 2;

        Child(int value) {
            super(value);
            System.out.println("Child initial = " + childValue);
            childValue = value * 2;
            System.out.println("Child after = " + childValue);
        }
    }

    public static void main(String[] args) {
        Child child = new Child(5);

        System.out.println("Final base = " + child.baseValue);
        System.out.println("Final child = " + child.childValue);
    }
}
~~~

Run:

~~~bash
javac -g -encoding UTF-8 ConstructorStepDemo.java
java ConstructorStepDemo
~~~

**Exact stdout:**

~~~text
Base field initially = 0
Base field after = 5
Child initial = 2
Child after = 10
Final base = 5
Final child = 10
~~~

### 18.1. Breakpoint Inside the Base Constructor

At the line printing “Base field initially”, `this.baseValue` is still 0. Even though the dynamic type of the receiver is Child, subclass field initialization is still not something to rely on while the Base constructor is executing.

### 18.2. Breakpoint After `super(value)`

Observe baseValue=5; the Child field initializer sets childValue=2 before the body statement prints “Child initial”.

### 18.3. Breakpoint After the Child Field Assignment

After `childValue = value * 2`, the value becomes 10. Parameter value remains 5, not changed by the field assignment.

### 18.4. Watch Out for the “before super” Order

In Java 17, a subclass constructor must invoke the superclass constructor according to constructor invocation rules. You cannot freely access `this`/subclass instance fields before `super(...)` in standard syntax. Set breakpoints at locations that are actually valid in the source.

## 19. Call Stack: Tracing Objects and Parameters Across Method Layers

If the call chain is:

~~~text
main()
    -> controller.handle(request)
         -> service.process(request)
              -> account.withdraw(amount)
~~~

When paused inside withdraw, the Call Stack displays frames from the current callee to the callers. To find out where amount came from:

1. Check `amount` in the withdraw frame.
2. Move up to the `service.process` frame and inspect the local/parameter that service passed.
3. Move up to `controller.handle` and inspect the request fields/derived values.
4. Note where the value was unexpectedly transformed.

### 19.1. Selecting a Frame Does Not Alter Execution

Moving the selection from the withdraw frame to the controller frame to inspect variables **does not run the program backward**. It only changes the display/evaluation context.

### 19.2. A Method Call Can Change the Argument

For example, the controller receives 100, the service applies a discount to make it 90, and withdraw receives 90. When the debugger selects each frame, local values can differ by design. Do not conclude that 100 “was passed incorrectly by Java”.

### 19.3. Parameters Can Hold the Same Reference Value Across Multiple Frames

If the request object is passed from controller→service→domain without copying, each frame has its own reference pointing to the same object. If the service modifies `request.status`, the controller can see the change.

### 19.4. Optimized Frames and Native Code

In JIT-optimized code, the debugger may not always reconstruct every local variable value due to optimizations, or some frames may have no source. Use a debug build and source symbols when needed; do not assume every VM allows identical inspection at all times.

## 20. Complete Program 7 — Polymorphism: Runtime Receiver and Caller Frame

File **`PolymorphismDebugDemo.java`**:

~~~java
public class PolymorphismDebugDemo {
    abstract static class Job {
        final String id;

        Job(String id) {
            this.id = id;
        }

        abstract String execute();
    }

    static final class PrintJob extends Job {
        PrintJob(String id) {
            super(id);
        }

        @Override
        String execute() {
            return "print:" + id;
        }
    }

    static final class SaveJob extends Job {
        SaveJob(String id) {
            super(id);
        }

        @Override
        String execute() {
            return "save:" + id;
        }
    }

    static String dispatch(Job job) {
        return job.execute();
    }

    public static void main(String[] args) {
        Job first = new PrintJob("P1");
        Job second = new SaveJob("S2");

        System.out.println(dispatch(first));
        System.out.println(dispatch(second));
        System.out.println("Same runtime type = "
                + (first.getClass() == second.getClass()));
    }
}
~~~

Compile/run:

~~~bash
javac -g -encoding UTF-8 PolymorphismDebugDemo.java
java PolymorphismDebugDemo
~~~

**Exact stdout:**

~~~text
print:P1
save:S2
Same runtime type = false
~~~

### 20.1. Breakpoint Inside `dispatch(Job job)`

The static type of the parameter is Job. When first is passed, the runtime object has type PrintJob; when second is passed, the runtime object has type SaveJob.

### 20.2. Step Into `job.execute()`

Java virtual dispatch selects PrintJob.execute or SaveJob.execute based on the runtime object type. Select the callee frame to see `this` inside the concrete override.

### 20.3. `this` Does Not Turn Into a Separate Base-Class Object

When entering PrintJob.execute, the receiver is **the same PrintJob instance** that the caller holds through a reference of type Job. Accessing the inherited `id` still takes place within that same object according to the Java object model.

### 20.4. The Debugger's Dynamic Type Does Not Replace the Compiler's Static Type

The compiler only allows calling methods declared through the static type Job (and accessible), unless pattern matching/casting is used. The concrete runtime type displayed by the debugger is observational information; it does not make the source compiler allow arbitrary access to every subtype method.

## 21. Local Scope, Shadowing, and “variable not available”

When the debugger shows a variable as “not available” or it does not appear in the list, a few causes are:

- The variable has not yet entered lexical scope.
- The declaration statement may not have executed yet.
- The debug build is missing the local variable table (use `javac -g`).
- The wrong stack frame is selected.
- The compiler/JIT optimized/eliminated it or did not preserve the value in a way the debugger can display.
- The source does not match the class file.
- The variable is captured in a lambda/anonymous class and represented differently from a regular local.

### 21.1. Parameters and Locals Differ from Fields in Lifecycle

A field does not disappear when a method returns if the object remains reachable. A parameter/local belonging to a frame is no longer observable as a local of that invocation after it returns. A reference value can continue to exist via a field/capture or be returned, but the old local variable does not stay attached to the object.

### 21.2. Block Scope

~~~java
if (ready) {
    int local = 10;
    System.out.println(local);
}
// local is not valid here.
~~~

This is a fragment. When the debugger is on a line outside the block, the name local may no longer be in scope. Do not try to read an out-of-scope local and conclude it was “garbage collected”: **a variable's scope differs from the reachability of the object it once referenced**.

### 21.3. Lambda Capture

A lambda can capture an effectively final local, causing the value to continue existing inside the lambda object after the method that created the lambda returns. When debugging, the compiler may represent captured values via the lambda's fields/synthetic structures. This still obeys Java semantics; do not rely on synthetic field names as an API.

## 22. Record: Inspecting Components, Accessors, and Object Value Semantics

A Java record declares components in the header:

~~~java
record Point(int x, int y) {
}
~~~

A record has private final component fields and public accessors `x()`, `y()`. In the debugger, you can see the x/y fields; this is the state of the record object. There are no default setters that modify component fields.

### 22.1. Do Not Confuse the Local `moved` with Mutating the State of `original`

~~~java
Point moved = new Point(original.x() + 2, original.y());
~~~

creates another record; original does not change. Use the debugger to inspect the original/moved references and components.

### 22.2. Equal Values Differ from Identity

Two `new Point(2,3)` records can be `equals` true thanks to generated equality, yet their references are not `==` if two separate objects are created. Debugger object labels may differ, matching the different identity despite equal values.

## 23. Complete Program 8 — Inspecting Records and Object Equality

File **`RecordDebuggerDemo.java`**:

~~~java
public class RecordDebuggerDemo {
    record Point(int x, int y) {
    }

    static Point moveRight(Point point, int delta) {
        return new Point(point.x() + delta, point.y());
    }

    public static void main(String[] args) {
        Point original = new Point(2, 3);
        Point equalValue = new Point(2, 3);
        Point moved = moveRight(original, 2);

        System.out.println("Original = " + original);
        System.out.println("Equal values = "
                + original.equals(equalValue));
        System.out.println("Same instance = "
                + (original == equalValue));
        System.out.println("Moved = " + moved);
        System.out.println("Original still = " + original);
    }
}
~~~

Run:

~~~bash
javac -g -encoding UTF-8 RecordDebuggerDemo.java
java RecordDebuggerDemo
~~~

**Exact stdout:**

~~~text
Original = Point[x=2, y=3]
Equal values = true
Same instance = false
Moved = Point[x=4, y=3]
Original still = Point[x=2, y=3]
~~~

### 23.1. Inspecting Inside `moveRight`

Parameter `point` is a reference value to the original record. Parameter `delta` is primitive int=2. The method creates a new Point(4,3), without changing original.

### 23.2. Selecting the main Frame After Step Out

`original` and `moved` are two different references, both of type Point. When opening their fields, original has x=2 and moved has x=4.

### 23.3. Why Is original.equals(equalValue) true while == Is false?

Generated record equality is based on component values (with the corresponding rules), while `==` compares reference identity. The debugger helps observe two identical values on two different objects.

## 24. NullPointerException: Selecting the Right Frame and Inspecting the Access Chain

An expression such as:

~~~java
person.address().city().length()
~~~

has multiple steps. Null could be person, the address() result, the city() result... **Do not fix it by sprinkling null checks randomly without first determining the contract.**

### 24.1. How to Find Where It Is Null

1. Pause on the line causing NullPointerException, or enable an **exception breakpoint** for NullPointerException.
2. Look at the Call Stack and select the first application frame that has source.
3. Inspect `person`; if non-null, inspect `person.address()`; then `city()`.
4. Be careful: calling getter methods in Evaluate Expression can execute code and cause side effects. If getters are not pure, inspect fields directly or set breakpoints inside the getters.
5. Identify the business cause: is null valid according to the API, missing data, incorrect initialization, or a caller violating the contract?
6. Fix it at the appropriate boundary: constructor validation, Optional/nullable contract, or state handling.

### 24.2. Exception Breakpoints in the IDE

Many IDEs allow pausing **when an exception is thrown** even if the code catches it. The UI name may be Exception Breakpoint, Java Exception Breakpoint, or Break on Caught/Uncaught. Choose caught/uncaught to match your needs; do not assume all IDEs have the same defaults.

### 24.3. Helpful NPE messages

Java 17 can generate a message describing the expression that caused the NPE depending on runtime/configuration, but do not use the exact message as portable output. If you need stable stdout, catch the exception and print a message explicitly defined by your code.

## 25. Complete Program 9 — null in the Object Graph

File **`NullDebugDemo.java`**:

~~~java
public class NullDebugDemo {
    record Address(String city) {
    }

    record Person(String name, Address address) {
    }

    static int cityLength(Person person) {
        return person.address().city().length();
    }

    public static void main(String[] args) {
        Person valid = new Person("Lan", new Address("Hue"));
        Person missing = new Person("Mai", null);

        System.out.println("Valid length = " + cityLength(valid));

        try {
            cityLength(missing);
        } catch (NullPointerException ex) {
            System.out.println("Missing address detected");
        }

        System.out.println("Missing name = " + missing.name());
    }
}
~~~

Commands:

~~~bash
javac -g -encoding UTF-8 NullDebugDemo.java
java NullDebugDemo
~~~

**Exact stdout:**

~~~text
Valid length = 3
Missing address detected
Missing name = Mai
~~~

### 25.1. Breakpoint Right Before Dereferencing

In `cityLength`, inspect `person`, and then `person.address()`. The invocation with valid has an Address object with city="Hue"; the invocation with missing has address=null.

### 25.2. Why Does Catch Handle It Without Fixing the Object?

Catch only handles the exception. It does not turn missing.address into a valid Address. Subsequent code can still call `missing.name()` because the Person object is non-null.

### 25.3. Fixing Through the Contract

If the address is required, the Person constructor needs `Objects.requireNonNull(address)`, rejecting an invalid object from the start. If address is optional, the cityLength method should return a defined fallback/result or report a business validation error. Avoid merely “catching NPE and continuing” in production.

## 26. Watches and Evaluate Expression: Powerful Tools, but with Side Effects

A Watch like `this.balance` is usually a field read. However, the expression:

~~~java
account.withdraw(100)
~~~

**will execute a method**, which can modify the state being debugged. A getter can also lazy-load data, update counters, or acquire locks depending on its implementation.

### 26.1. Expressions to Prefer

- `this.field`.
- `parameter`, `local`.
- `left == right`.
- `list.size()` if you understand the implementation and accept the method call.
- `record.x()` if the accessor is pure according to the contract.
- `object.getClass().getName()` if you need the concrete type, recognizing this is still a method evaluation.

### 26.2. Expressions That Require Caution

- `iterator.next()`: changes the iterator position.
- `list.remove(...)`: mutates state.
- `account.withdraw(...)`: mutates the domain object.
- `stream.count()` on a one-shot stream: can consume the stream.
- custom `toString()`: can execute application code, I/O, or locks.
- `future.get()`: can block while paused, causing a deadlock if a worker needs to run.
- Calls to HTTP/database: have side effects outside the JVM and cannot be undone with Restart Frame.

### 26.3. Conditional Breakpoints Can Also Evaluate Expressions

A pure condition like `balance < 0` can be safe. However, `expensiveMethod()` in a condition may run on every breakpoint hit, altering timing and causing side effects. IDEs usually have options such as **Suspend all threads / Suspend thread**, logpoints, or conditions; choose appropriately and measure overhead.

### 26.4. “Debugger changed the bug”

If the bug disappears when you set a breakpoint, suspect a race, timing, initialization ordering, or timeout issue. A breakpoint does not prove the bug does not exist. Combine with tests and concurrency diagnostics.

## 27. Breakpoints: Choosing the Right Kind for Your Question

| Breakpoint Type | When to Use | Notes |
| --- | --- | --- |
| Line breakpoint | You know the suspicious statement | Place on an executable line |
| Method breakpoint | Want to pause every time a method is called | May have higher overhead than a line breakpoint |
| Conditional breakpoint | Only pause when amount < 0 or an id matches | The condition may be evaluated many times |
| Exception breakpoint | Trace NPE/IllegalStateException | Can pause even on caught exceptions |
| Field watchpoint | Want to know where a field is read/written | Depends on debugger/VM support and overhead |
| Logpoint/tracepoint | Want to record data without suspending like a line breakpoint | Still has evaluation overhead |
| Run to Cursor | Skip the current code section to a target position | Not guaranteed to reach if control flow branches |

### 27.1. Do Not Place a Breakpoint Only in a Getter If the Field Is Modified Elsewhere

To find out **who writes to the field**, use a field modification watchpoint if the tool supports it, or locate all writes and set breakpoints. Debugging at the getter only shows the state being read.

### 27.2. A Field Watchpoint Differs from a Native Debugger's Data Breakpoint

Java Debug Interface/JDWP has field access/modification events on VMs with appropriate support. An IDE may generally call this Data Breakpoint, Field Watchpoint, or Watchpoint. Check the specific semantics; do not assume a hardware watchpoint like in a C/C++ debugger.

### 27.3. Breakpoint Hit Counts and Filters

If a method is called millions of times, use a hit count or condition so it does not pause too often. Do not let a condition call an expensive API or access shared state without understanding the concurrency impact.

## 28. Observing Threads and Object Consistency

In a program with multiple threads, the same object field can be read/written by multiple execution contexts. A debugger can:

- Suspend only the thread that hits the breakpoint.
- Suspend all threads depending on configuration.
- Allow selecting each thread and its own call stack.
- Show field values changing if other threads keep running.

### 28.1. Observing a Field Does Not Prove There Is No Race

Seeing `counter.value == 10` once at a breakpoint does not guarantee the increment is safe across all interleavings.

### 28.2. Suspending All Threads Can Mask a Race

If every thread is paused when a breakpoint hits, the interleaving changes compared to production. If only one thread is suspended, other threads can continue modifying the object while you inspect it. Both modes have tradeoffs.

### 28.3. Thread-Local Variables and Shared Fields Differ

Each thread has its own call stacks/locals for method invocations; two threads can simultaneously hold references to a **shared heap object**. Do not confuse two frames having a variable named `counter` with two separate counters.

### 28.4. Synchronization Establishes Happens-Before/Visibility Under the Java Memory Model

If the code uses `synchronized` or atomic utilities properly, appropriate visibility/atomicity guarantees can be established. A debugger is only an observation tool; it does not replace synchronization primitives.

## 29. Complete Program 10 — Shared Object Across Multiple Threads

File **`ThreadDebuggerDemo.java`**:

~~~java
public class ThreadDebuggerDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int value() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter shared = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 100; i++) {
                shared.increment();
            }
        };

        Thread first = new Thread(work, "worker-A");
        Thread second = new Thread(work, "worker-B");

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("Final = " + shared.value());
        System.out.println("Same target = "
                + (first != second));
    }
}
~~~

Run:

~~~bash
javac -g -encoding UTF-8 ThreadDebuggerDemo.java
java ThreadDebuggerDemo
~~~

**Exact stdout:**

~~~text
Final = 200
Same target = true
~~~

### 29.1. Breakpoint Inside `Counter.increment`

Execution can pause in worker-A or worker-B depending on scheduling. Select the Threads pane to see the active thread's name. There is no guarantee which thread hits the breakpoint first.

### 29.2. `this` in Both Worker Frames

If both call `shared.increment()`, the receiver `this` points to the same Counter object. However, each thread has its own local `i` in the lambda invocation loop.

### 29.3. Why Is Final Always 200 in the Demo?

Increment is `synchronized` on the same shared Counter object; two threads each call it 100 times; main waits for `join` to complete before printing. There are no lost updates with this synchronization.

### 29.4. Why Is "Same target" true Even Though the Name Seems Misleading?

The expression printed in the demo is `first != second`, checking that **the two Thread objects are different**. The label "Same target" can easily be confused with the Runnable target being shared; interpret the true line strictly according to the expression. When learning the debugger, you should change the label to "Distinct threads" to avoid confusion. Having both threads share the Counter is established through the captured variable `shared` in the same Runnable.

### 29.5. Limitations of the Demo

This is a simple lock example, not a throughput benchmark. Running under a debugger can lengthen execution; do not take timing from it as a measure of production performance.

## 30. Reading `this` in Interface Default Methods, Lambdas, and Nested Classes

### 30.1. Instance Method of an Interface Default

When a class implements an interface with a default method, `this` in the default method is a reference to the implementation object receiving the call. It is not an instance of the interface (an interface is not instantiated directly).

### 30.2. `this` in a Lambda

In a **lambda body**, `this` has the meaning of the lexical enclosing instance of the context where the lambda is created, **not necessarily a "lambda object"**. In a static method, you cannot use `this` just because you are writing a lambda.

### 30.3. `this` in an Anonymous Inner Class

In an anonymous class body, `this` points to the anonymous instance, unlike the lexical `this` in a lambda. To access the outer instance, use the form `OuterClass.this` where valid.

### 30.4. The Variables Pane May Display Synthetic Fields

Captured locals and enclosing instances can be represented by the compiler via synthetic members. Internal names vary by compiler/version; rely on Java language semantics rather than hard-coding synthetic field names.

## 31. Complete Program 11 — Lambdas and Anonymous Classes View `this` Differently

File **`ThisCaptureDebugDemo.java`**:

~~~java
public class ThisCaptureDebugDemo {
    private final String name;

    ThisCaptureDebugDemo(String name) {
        this.name = name;
    }

    Runnable lambda() {
        return () -> System.out.println(
                "Lambda this = " + this.name);
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        "Anonymous this = "
                        + getClass().getSimpleName());
                System.out.println(
                        "Outer this = "
                        + ThisCaptureDebugDemo.this.name);
            }
        };
    }

    public static void main(String[] args) {
        ThisCaptureDebugDemo demo =
                new ThisCaptureDebugDemo("outer");

        demo.lambda().run();
        demo.anonymous().run();
    }
}
~~~

Compile/run:

~~~bash
javac -g -encoding UTF-8 ThisCaptureDebugDemo.java
java ThisCaptureDebugDemo
~~~

**Reliable stdout of the program:**

~~~text
Lambda this = outer
Anonymous this = 
Outer this = outer
~~~

### 31.1. Why Is the Anonymous this Line Blank After the Equals Sign?

In a normal anonymous class, `getClass().getSimpleName()` returns an empty string because an anonymous class has no simple name. That is Java reflection behavior consistent with the example. Do not rely on auto-generated binary class names such as `ThisCaptureDebugDemo$1`.

### 31.2. Debugger for the Lambda

When paused at the print in the lambda, `this` according to lexical context is the ThisCaptureDebugDemo object. It has the field `name="outer"`.

### 31.3. Debugger for the Anonymous Runnable

`this` in `run()` is the anonymous Runnable instance. To view the outer object, evaluate `ThisCaptureDebugDemo.this` as allowed by Java scope.

### 31.4. Why Does This Guide Relate to Aliasing?

A lambda or anonymous class can hold a reference to the enclosing object. If kept in a long-lived registry, it can extend the lifetime of the outer object. The debugger can show the reference path/capture, even though synthetic field details depend on the compiler.

## 32. Failure Cases: Breakpoint Does Not Pause or Values Do Not Match Expectations

### 32.1. Placing a Breakpoint on a Line Without Bytecode

For example, a closing brace, comment, or optimized-away variable declaration may not create a suitable location. Place it on a statement that actually executes, such as a field assignment, method call, or conditional branch.

### 32.2. Wrong Class/Package/Main Configuration

Sometimes the IDE is debugging another module or another Java process. Check the main class, classpath, module, working directory, and JDK version.

### 32.3. Source Differs from the Class File

Cleanly rebuild the relevant parts and ensure the debug session uses the new compiled output; if the source is mismatched, debugger line mapping can make the pause location misleading.

### 32.4. Missing Debug Symbols

Use `javac -g`. If the built class file does not contain local variable information, the debugger may be able to view fields or method signatures, but will not display local names/values as in the source.

### 32.5. Selecting the Wrong Stack Frame

If you are in the `main` frame, there is no `this` of the instance method `add`; if you are in the `add` frame, you cannot read main's local `first` directly as if in the same scope.

### 32.6. Getter/toString Changes State

Some IDEs evaluate properties or custom renderers automatically. Check **auto expression evaluation**/toString rendering settings if inspecting causes the application to change behavior.

### 32.7. Objects Appear to Have the Same Label

Some IDEs display the same class name and field values for multiple objects. To determine identity, evaluate `==` or inspect reference identity through the tool. Do not infer it from identical class/type names.

### 32.8. Encountering a Race Only When Not Debugging

The debugger can alter scheduling. Use stress/concurrency tests, lock ordering reviews, thread dumps, and logging with correlation IDs. Do not “fix” it with random sleeps because that may only mask the bug.

### 32.9. Source Has Overloaded Methods

A method breakpoint may pause on multiple overloads depending on the IDE. `jdb stop in Class.method` requires checking the resolved target; set a specific line breakpoint when you want to distinguish signatures.

### 32.10. Native Frames or Methods Without Source

You may not be able to Step Into source if JDK/library source is not attached or the method is native. This does not make bytecode/runtime behavior wrong; it only limits debugger observation.

## 33. Debugger Anti-Patterns

1. **Looking only at a single variable `count` and not distinguishing between the field and the parameter.**
2. **Treating `this` like a class name instead of a reference to the receiver object.**
3. **Believing that a reference variable is passed by reference.**
4. **Assigning a parameter to a new object and expecting the caller variable to change.**
5. **Assuming a local and a field live in the same scope.**
6. **Confusing static fields with instance-specific fields.**
7. **Looking only at equal values and concluding two objects have the same identity.**
8. **Looking only at object IDs and concluding equals is false.**
9. **Using Evaluate Expression to call a mutating domain operation.**
10. **Setting a conditional breakpoint with expensive I/O expressions.**
11. **Using Drop Frame expecting to roll back database/file writes.**
12. **Failing to select the right thread/frame before reading locals.**
13. **Seeing null in a reference path and assuming by default that the root object is null.**
14. **Not reading the constructor initialization order.**
15. **Using default `javac` and believing all local names must appear.**
16. **Failing to rebuild the class file after editing the source.**
17. **Keeping a breakpoint on a hot path and using elapsed time as a benchmark.**
18. **Not distinguishing the exception throw point from the catch location.**
19. **Assuming a getter is always pure with no side effects.**
20. **Not realizing an unmodifiable List still has mutable elements.**
21. **Treating the entire object graph as one large object instead of multiple references.**
22. **Evaluating stream/iterator methods in the debugger, causing state to change.**
23. **Not thinking about lambda capture keeping the outer object reachable.**
24. **Not checking thread states and lock ownership when debugging a deadlock.**
25. **Using a single debug run as proof that the code has no concurrency bug.**
26. **Looking at a non-null local without considering an alias that can mutate the same object.**
27. **Treating console debugger diagnostics as Java program stdout.**
28. **Trying to memorize every IDE shortcut instead of understanding Step commands and the frame model.**
29. **Modifying values with the debugger and forgetting to reset/re-run test data.**
30. **Stopping where a field has already changed and guessing the culprit instead of tracing the write path.**

## 34. Suggestion Table: “If You Want to Know X, Observe Y”

| Question | Breakpoint/Expression |
| --- | --- |
| What inputs did the constructor receive? | Breakpoint at the constructor; view parameters |
| What value is the field currently holding? | `this.field` in the instance frame |
| Why did the field not change after assignment? | Check shadowing `field` vs `this.field` |
| Which object is the method running on? | Inspect `this` and select the receiver at the caller |
| Do two variables point to the same object? | `a == b` |
| Why does a mutation inside the method affect the caller? | Parameter reference and caller alias share the same referent |
| Why does reassigning the parameter not affect the caller? | Compare references in caller/callee frames |
| Where does the static counter belong? | `TypeName.counter` |
| Who called a method? | Call Stack/`where` |
| Who modifies the field? | Field modification watchpoint or breakpoints at writes |
| What happens inside the nested method? | Step Into |
| Only need the result of the nested method? | Step Over |
| Return to the caller after the callee? | Step Out |
| Where does the NPE appear? | Exception breakpoint + inspect dereference chain |
| Which nested List/DTO does the object contain? | Expand the object graph in Variables |
| Does the List snapshot retain a mutable element alias? | Compare references `==` and inspect child fields |
| What is the runtime type of a base-class reference? | `obj.getClass()` or debugger concrete type |
| Was a record replaced or mutated? | Compare original/moved references, fields |
| Bug disappears when breakpoints are enabled? | Check race/timing, stress tests |
| Local variable is not displayed? | `javac -g`, right frame/scope/source symbols |

## 35. Review Questions with Answers

**Question 1.** In an instance method, what is `this`?

**Answer:** A reference to the object receiving the current method call.

**Question 2.** Can `this` be used in static main?

**Answer:** No. A static method has no receiver instance.

**Question 3.** In constructor `Person(String name)`, how do `name` and `this.name` differ?

**Answer:** `name` is the constructor parameter; `this.name` is the instance field of the object being created.

**Question 4.** To inspect a shadowed field, what expression should you write in the debugger?

**Answer:** Compare `name` with `this.name` in the right frame.

**Question 5.** Does `this` change when calling the same method on two different objects?

**Answer:** Yes, the receiver reference of each invocation points to the object on which the call was made.

**Question 6.** Does a callee's local variable automatically appear in the caller frame?

**Answer:** No; they belong to different stack frames/scopes.

**Question 7.** When a method takes `Box parameter`, what does Java pass?

**Answer:** A copy of the reference value to the Box object, following pass-by-value.

**Question 8.** Does assigning `parameter = new Box(...)` change the caller variable?

**Answer:** No; it only changes the callee's local reference.

**Question 9.** Can modifying `parameter.value` affect the caller?

**Answer:** Yes, if the caller and parameter both reference a mutable object.

**Question 10.** What does `a == b` check for references?

**Answer:** Reference identity — whether they refer to the same object.

**Question 11.** Is `a.equals(b)` always equivalent to `a == b`?

**Answer:** No; classes can override equals to compare values.

**Question 12.** Does a static field belong to each individual instance?

**Answer:** No; it belongs to the class identity, shared among instances according to the classloader/runtime context.

**Question 13.** Why should you use `javac -g` when learning jdb?

**Answer:** To compile with more complete local variable names/debug information for inspection.

**Question 14.** How does Step Into differ from Step Over?

**Answer:** Step Into enters the called method; Step Over executes the call and pauses at the next step in the caller.

**Question 15.** What does Step Out do?

**Answer:** Continues until the current method returns to the caller, without undoing side effects.

**Question 16.** What does the Call Stack show?

**Answer:** The chain of active frames/method invocations of the selected thread.

**Question 17.** Does switching the selected frame make the program run backward?

**Answer:** No; it only changes the observation/evaluation context.

**Question 18.** Why is a local not displayed?

**Answer:** It may not have entered or may have left scope, debug symbols may be missing, the frame/source may be wrong, or it may have been optimized away.

**Question 19.** Can a debugger automatically evaluate toString?

**Answer:** Depending on the IDE/settings, yes; a custom toString can run application code.

**Question 20.** Can Evaluate Expression change object state?

**Answer:** Yes, if the expression calls methods with side effects.

**Question 21.** Is a conditional breakpoint calling a network method safe?

**Answer:** You should not assume so; evaluation can take time and affect the program.

**Question 22.** If a and b have the same class name and identical fields, are they definitely the same object?

**Answer:** No; use reference identity `a == b`.

**Question 23.** Does a record have default setters for component fields?

**Answer:** No; record component fields are final, and accessors read the value.

**Question 24.** Can two Point records with the same x/y have equals true while == is false?

**Answer:** Yes, if they are two separate instances whose component values are equal.

**Question 25.** When paused inside the Base constructor of Child, are subclass fields always finished yet?

**Answer:** No; constructor/init order needs to be observed properly.

**Question 26.** Why is the overridden method selected even though the reference's static type is Base?

**Answer:** Virtual dispatch based on the runtime receiver type.

**Question 27.** With a NullPointerException, what should you inspect first?

**Answer:** The exception throw site, the stack frame, and the related chain of reference dereferences.

**Question 28.** Java 17 can print a Helpful NPE message; should you hard-code the exact text into tests?

**Answer:** No when you want portable output; the message can depend on runtime/config.

**Question 29.** When debugging two threads, can `this` be the same object?

**Answer:** Yes, if both call an instance method on a shared receiver.

**Question 30.** Can a breakpoint mask a concurrency bug?

**Answer:** Yes, because it alters scheduling/timing.

**Question 31.** Is Watch in an IDE the same as jdb's watch command?

**Answer:** Not entirely. An IDE Watch usually evaluates an expression, whereas jdb's watch relates to field watchpoints.

**Question 32.** Why should you not read a variable by calling `iterator.next()` in the debugger?

**Answer:** Because it has the side effect of advancing the iterator position, changing the execution being debugged.

**Question 33.** Can you “undo” a DB transaction using Drop Frame?

**Answer:** No; the tool does not automatically roll back side effects outside the process.

**Question 34.** Why can a callback/lambda extend an object's lifetime?

**Answer:** It can capture a reference to an outer object and be stored in a longer-lived owner.

**Question 35.** To see a field change after a statement, what do you do?

**Answer:** Set a breakpoint before the mutation, inspect the field, Step Over the statement, and inspect the field again.

**Question 36.** Does a local disappearing after return mean the referent object has been GC'd?

**Answer:** No; the object may still have other references, and reclamation is decided by GC.

**Question 37.** Does a debugger replace unit tests?

**Answer:** No; a debugger observes one execution, while tests automatically verify behavior across many cases.

**Question 38.** When stdout and the Variables pane seem to contradict each other, what must you check?

**Answer:** Which statement the breakpoint is before/after, which frame/thread is selected, whether source/build match, evaluation side effects, buffered output, and timing.

**Question 39.** Which command makes jdb display the call stack?

**Answer:** `where` inside the interactive session.

**Question 40.** What is the most important rule when learning the Java Core debugger?

**Answer:** Always distinguish between **locals/parameters in a frame**, **the receiver's `this`**, **instance/static fields**, and **references to heap objects**; observe before and after each state mutation instead of guessing.

## 36. Hands-On Exercises

### Exercise 1 — this and Shadowed Names

Create a class `Person` with field name and constructor parameter name. Pause before/after `this.name = name`; record the field and parameter values at each step.

**Hint:** Use `javac -g`; Watch `name` and `this.name`.

### Exercise 2 — Two Objects of the Same Class

Create two `Counter` objects and call increment on each in turn. Pause inside the method; inspect `this`, fields, and caller variables. Prove that the fields of the two objects do not interfere with each other.

**Hint:** Compare `counterA == counterB` in the caller.

### Exercise 3 — Pass-by-Value of References

Using `ReferenceParameterDebugDemo`, capture the state of the parameter and caller reference before/after mutating and reassigning. Explain why the caller only sees the mutation on the original object.

**Hint:** Select different frames in the Call Stack.

### Exercise 4 — Shallow Copy Object Graph

Create a Cart holding a List<Item>, copying the List in the constructor. Mutate an Item from the caller and add a new Item to the source List. Debug both Lists and element references.

**Hint:** Use `==` to identify the shared Item, rather than just looking at strings.

### Exercise 5 — static vs instance

Create a static counter and instance IDs, and pause in the constructor. Observe class-level state increasing when objects are created, then observe each object's independent id.

**Hint:** Evaluate `TypeName.staticField` and `this.instanceField`.

### Exercise 6 — Constructor Chain

Set breakpoints in Base and Child constructors. Track base fields, the child field initializer, and the child constructor body; explain the default values before initialization.

**Hint:** Avoid changing logic or calling an overridable method inside a constructor.

### Exercise 7 — Exception Breakpoint

Create a Person with a nullable Address, call chained accessors, and trigger a NullPointerException. Enable an exception breakpoint; locate the exact null link and fix the invariant at the constructor or method boundary.

**Hint:** Do not use the Helpful NPE message as a fixed stdout.

### Exercise 8 — IDE-Independent jdb

Compile `DebuggerBasicsDemo.java` with `javac -g`. Open `jdb DebuggerBasicsDemo`, set `stop in DebuggerBasicsDemo$Meter.add`, and use `where`, `locals`, `print count`, `print this.count`, and `next`.

**Hint:** Read the right frame and remember the debugger transcript varies by class line numbers/JDK.

### Exercise 9 — Multithreading

Run `ThreadDebuggerDemo` with a breakpoint inside synchronized increment. Select each thread stack; identify the separate local loop i and the shared Counter receiver. Try suspend thread vs all threads if the IDE permits.

**Hint:** Do not use the order in which threads hit the breakpoint as expected output.

## 37. Debugger Checklist Before Reporting That You Found the Bug

1. Have you debugged the right compiled class and the right Java process?
2. Has the source been rebuilt after changes?
3. Are local variable debug symbols (`javac -g`) present?
4. Is the breakpoint on a real executable line?
5. Is the right thread selected?
6. Is the right stack frame selected?
7. Which receiver is `this`, or is the method static?
8. Are a parameter/local and a field shadowed with the same name?
9. Are the values observed **before or after** the mutating statement?
10. Have you compared field `this.x` with parameter `x` separately?
11. Have you distinguished the reference value from the referenced object?
12. Are there aliases from caller/callee or nested fields?
13. Have you checked identity using `==` in the right scope?
14. Have you distinguished `equals` from `==`?
15. Is a static field being mistaken for per-instance?
16. Are there nested objects/collections that need expanding?
17. Is there a shallow vs deep copy/defensive copy issue?
18. Is a local out of scope or affected by JIT optimization?
19. Is there uninitialized constructor state?
20. Is there dynamic dispatch to a subtype override?
21. Have you checked the NPE chain and exact null link?
22. Are you calling a mutating method in Watches/Evaluate?
23. Is a custom toString/getter renderer causing side effects?
24. Is the conditional breakpoint too expensive?
25. Is a breakpoint/stepping altering thread scheduling?
26. Are field writes happening in another thread?
27. Do you need a breakpoint on field modification rather than just a line breakpoint?
28. Are you confusing debugger diagnostics with program stdout?
29. Have you used the debugger to identify the root cause and then created a regression test?
30. Have you removed/reverted debug-only evaluations/test values before running in production?

## 38. Summary

When using a debugger to learn and fix Java Core, view a program as having **two interrelated conceptual spaces**: **stack frames** containing parameters, locals, and `this`; **heap objects** containing instance fields and references to other objects. Java source expresses these relationships through variable names, whereas the debugger lets you observe them at a specific execution point.

`this` is always a reference to the **receiver object in an instance context**; `this.field` distinguishes a field from a same-named local/parameter. Java passes **a copy of the reference value** to parameters; mutating an object through an alias can become visible in the caller, whereas reassigning the parameter does not change the caller's reference variable. Static fields belong to the class, not a receiver; records create value-like objects with final component fields; the constructor chain and virtual dispatch determine the actual location of the state/method currently being executed.

Practice **breakpoint → select frame/thread → inspect `this`/fields/parameters/locals → Step Into/Over/Out → compare before/after → find the cause → write a regression test**. Use `javac -g` and `jdb` when you need an IDE-independent approach. When debugging multithreading or calling Evaluate Expression, remember the debugger can affect timing and side effects. It is precisely distinguishing these concepts properly — rather than just looking at a single value in the Variables pane — that builds solid object-oriented Java debugging capability.
