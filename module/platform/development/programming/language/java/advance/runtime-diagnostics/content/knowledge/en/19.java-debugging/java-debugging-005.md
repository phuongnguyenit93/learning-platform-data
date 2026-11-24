# 19.5. Breakpoints, Stepping, Stack Frames, Local Variables, and Conditions Requiring Debug Information

When debugging Java, a breakpoint lets you **pause execution at a location supported by the JVM/debugger**, then inspect the call stack, local variables, objects, and thread states. However, the debugger does not "directly read" the source lines open in your IDE to execute them: the JVM runs **the bytecode of the classes actually loaded**. The ability to map bytecode back to source, pause at a line, and display variable names depends on **debug information inside `.class`**, class versions, source paths, and runtime state.

This lesson distinguishes **breakpoints, step into/over/out, stack frames, and local variables**, and explains exactly **when debug information is needed**. Examples run on Java 17+ with `javac`, `javap`, and `jdb`; IDEs like IntelliJ IDEA, Eclipse, or VS Code have different UIs, yet the underlying principles based on the Java Platform Debugger Architecture (JPDA) are similar.

## 1. Mental Model: Source Code, Bytecode, Debugger, JVM

A typical debug flow:

```text
DebugFrameDemo.java
       │ javac (with or without -g)
       ▼
DebugFrameDemo.class
  ├─ bytecode + method/field descriptors (for execution)
  ├─ SourceFile (if present)
  ├─ LineNumberTable (if present)
  └─ LocalVariableTable / LocalVariableTypeTable (if present)
       │
       ▼
JVM runs loaded class ─── JDWP/JVMTI ─── debugger (IDE / jdb)
      │ suspend thread                        │
      └── stack frame, bytecode location ─────┘ display lines/variables
```

JPDA has three related components:

- **JDI — Java Debug Interface:** API for the debugger to control and query the JVM, threads, breakpoints, stack frames, and variables.
- **JDWP — Java Debug Wire Protocol:** communication protocol between the debugger and the debugged JVM, commonly using sockets for remote attach.
- **JVMTI — JVM Tool Interface:** runtime-side interface for agents/debuggers to perform observation/control operations.

IDEs typically wrap these APIs into buttons like **Resume**, **Step Into**, **Step Over**, **Step Out**, **Frames**, **Variables**, and **Evaluate Expression**. Button labels and shortcuts vary across IDEs, so do not assume any shortcut is a Java standard.

**Core distinction:** the newest source file on your machine does not necessarily match the `.class` the JVM is running. A debugger may highlight a "right-named" source line while the mapping is shifted after an out-of-sync build/deploy. When state makes no sense, verify the **loaded bytecode** and debug attributes before suspecting the JVM computed wrongly.

## 2. What Is a Breakpoint and What Types Are Commonly Used?

A breakpoint is a condition causing the debugger to ask the VM to **report an event and/or suspend** when execution reaches a matching location. A source-line breakpoint is normally mapped to a **bytecode position (code index) inside a method** via `LineNumberTable`. Not every source line has its own executable instruction.

| Breakpoint type | When it triggers | What it is used for | Caveats |
| --- | --- | --- | --- |
| **Line breakpoint** | When a thread reaches the bytecode location corresponding to a source line. | Inspect variable values before/after a specific operation. | Requires line mapping and executable code; comments, imports, and declarations without emitted code usually cannot hold one. |
| **Method entry breakpoint** | When a matching method is invoked. | Start watching a method when the exact line is unknown. | Can still work without line mapping, yet frequent calls cause heavy overhead. |
| **Conditional breakpoint** | When reaching a location and the condition expression evaluates to true. | Pause only for cases like `orderId == 42`. | Expression is evaluated by the debugger; can burn CPU, invoke code, cause side effects, or throw exceptions. |
| **Exception breakpoint** | When an exception type is thrown (per caught/uncaught configuration). | Find where an error originates instead of only where it is caught. | Exceptions may be thrown frequently as normal control flow. |
| **Field watchpoint** | When reading/writing a watched field (if supported by debugger/VM). | Find where state mutates unexpectedly. | Not the same as a local-variable watch; overhead can be high. |
| **IDE logpoint/tracepoint** | When hitting a location and the IDE logs info instead of pausing (per config). | Investigate high request volumes with minimal disruption. | Still incurs instrumentation/evaluation cost and risks exposing sensitive data. |

A breakpoint **is not guaranteed to hit only once**: a line inside a loop can execute thousands of times, multiple threads can pass through the same method, and a class can be loaded multiple times by different class loaders.

### Why Might a Breakpoint Fail to Pause?

- **Class not yet loaded:** the debugger may mark the breakpoint pending/deferred and bind it when the class loads.
- **Non-executable line:** comments, imports, declarations, or compiler-eliminated code have no matching bytecode location.
- **Missing/stripped line debug info:** lacking `LineNumberTable` prevents accurate source-line mapping.
- **Source differs from deployed class:** line 25 in current source is different code from the running class.
- **Different class loader or module:** the same class name can exist across multiple loaders; the breakpoint bound to the wrong copy.
- **Code path not taken:** `if` condition is false, method never called, or thread already exited.
- **Filters/conditions/suspend policy:** IDE condition did not match, breakpoint disabled, or only another thread was paused.
- **Build optimization/instrumentation:** bytecode transformed by agents, obfuscators, build tools, or generated code shifts locations unexpectedly.

Do not toggle breakpoints randomly to "fix" the issue. Read "verified/unverified" indicators, verify PID, classpath/module-path, class loader, and inspect `javap` on the **actual artifact used to run**.

## 3. Stepping: Step Into, Step Over, Step Out, and Resume

Once the JVM is paused at a breakpoint, stepping actions help trace the execution path:

| Action | Simple meaning | Appropriate question |
| --- | --- | --- |
| **Step Into** | Advances to the next source step, potentially entering a called method. | "What does this call do inside?" |
| **Step Over** | Runs through method calls on the current line, then pauses at the next step in the **current frame** if any. | "How did values change after the method returned?" |
| **Step Out** | Continues until the **current frame's method** returns, then pauses in the caller when possible. | "What result did the call site receive?" |
| **Resume/Continue** | Continues until the next breakpoint/exception/stop event. | "Does it still reproduce at this spot?" |
| **Run to Cursor** (IDE) | Sets a target to run to the selected location, subject to tool support. | "Skip unrelated lines." |

In `jdb`:

- `step` advances to the next line, **potentially entering another method**.
- `next` advances to the next line in the **current frame**.
- `cont` resumes execution.
- `step up` (in `jdb` versions that support it) executes until the current method returns; verify with your `jdb`'s own `help`.

**Do not misunderstand Step Over as "skipping execution of the called method."** The method still runs in full—it can perform I/O, throw exceptions, spawn threads, hit other breakpoints, or cause side effects; the debugger merely avoids stepping line by line inside that method.

Likewise, do not misunderstand **Step Out** as "skipping the remaining code." The remaining statements still execute until the method returns or unwinds via exception.

### Why Does Clicking Step Into Not Enter the Line I Wanted?

The current line may contain **multiple calls** and the debugger enters whichever executes first; the call may be native or a filtered library; the compiler may emit bridge/synthetic methods; lambdas/method references pass through generated code; or source mapping maps one line to multiple bytecode instructions. Many IDEs support **Smart Step Into** to pick a specific call, though that is an IDE feature rather than general Java syntax.

When stack traces show `lambda$...`, `access$...`, `$Proxy...`, or generated frames, understand that compilers/frameworks can generate intermediate methods/classes. This does not automatically indicate an error; inspect the actual logic and debug mapping.

## 4. Stack Frames: "Which Method Am I In, and Who Called It?"

Each Java thread has its own call stack. When a method is invoked, the runtime creates a **stack frame** for that invocation. A frame holds the necessary execution state, including local-variable slots, operand stack, and caller return information; the debugger presents accessible data in the suspended frame.

Example:

```text
Thread "main" at breakpoint in calculateSubtotal(...)
┌────────────────────────────────────────────┐
│ frame #0: DebugFrameDemo.calculateSubtotal │ ← current frame
│           quantity=3, price=7, raw=21      │
├────────────────────────────────────────────┤
│ frame #1: DebugFrameDemo.main              │ ← caller
│           quantity=3, price=7              │
└────────────────────────────────────────────┘
```

*This is an illustrative diagram after `raw` has been assigned; it is not fixed `jdb` output.*

- **Top frame** is the currently executing or paused method, usually closest to the breakpoint.
- **Caller frame** is where the current method was invoked; caller variables can be viewed if metadata is available.
- **Selecting a frame** in the debugger only switches the context you are viewing/evaluating; it does not rewind the JVM in time.
- The same method can appear multiple times across frames due to **recursion**, each invocation having its own local values.
- **Local variables** belong to **one method invocation** (one frame), unlike instance fields on an object or static fields on a class.

When the thread resumes, the stack advances: frames vanish when methods return, exceptions unwind the stack, or execution enters new methods. Never hold onto an old JDI `StackFrame`/variable object and use it after the thread resumes; JDI may throw `InvalidStackFrameException`.

### How Is a "Stack Frame" Different from a "Java Stack Trace"?

A **suspended stack frame** is a live snapshot of an execution point where locals can be inspected if metadata exists. A **stack trace logged from an exception** usually consists mainly of class/method names, source files, and line numbers (if available); it **does not print all local variables**. An exception stack trace is neither a heap dump nor a history of every method ever called.

With async code (`CompletableFuture`, executors, reactive chains), the worker running a callback has **that worker's stack**. The method that submitted the task from another thread may already have returned or be waiting elsewhere; it does not automatically sit beneath the callback in the call stack. To connect a logical call chain across threads, use trace/correlation IDs, async stack tooling, or proper instrumentation rather than looking only at one thread's `where`.

## 5. Local Variables and Visibility Scope

To debug `int subtotal` or `String customerId`, distinguish:

| Data | Where it lives semantically | Typical way to debug |
| --- | --- | --- |
| Method **parameter** | Input of a single invocation/frame. | Open current frame; parameter names may need `LocalVariableTable` for the debugger to display properly. |
| **Local variable** | Declared inside a method/block, with scope and lifetime. | `Variables`/`locals`, only at code locations where the variable is considered visible. |
| **Instance field** | Belongs to a Java object. | Expand `this` or an object reference to inspect fields; not a "local" in this sense. |
| **Static field** | Belongs to a class, shared across instances per class-loader identity. | Inspect via class/debugger; may involve multiple threads. |
| Lambda **captured variable** | Value/reference captured when constructing a lambda per Java rules. | May appear under synthetic fields/structures rather than directly as a local. |
| **Operand stack/temporary slot** | Internal bytecode state. | Not necessarily named in source; debugger cannot show it as a Java local. |

A local has **lexical scope** in Java source, whereas `LocalVariableTable` metadata describes **code index ranges** so the debugger knows its name, type, and slot. When paused **before the first assignment line**, a variable may be uninitialized or not yet reported visible; after stepping with `next` past that line, it holds an inspectable value.

Do not assume every displayed value is "already computed." If the debugger pauses at the start of:

```java
int total = compute(subtotal);
```

then `total` may **not be assigned yet**. Step with `next` to execute the statement before inspecting `total`. Never edit locals in the debugger while forgetting that the edit changes execution; many IDEs allow `Set Value` only when JDI/VM supports it and the variable is in a valid slot.

### Why Does the IDE Report "Variable not available" or `AbsentInformationException`?

Different causes require different actions:

1. **Missing local debug info:** the `.class` file lacks `LocalVariableTable`; JDI's `StackFrame.visibleVariables()` can throw `AbsentInformationException`.
2. **Variable not yet in scope or out of scope:** current code location falls outside the variable's live range.
3. **Call returned or thread resumed:** the prior frame was destroyed/invalidated.
4. **Inside a native frame:** there is no Java local-variable table like normal bytecode methods.
5. **Compiler/JIT/lambda instrumentation:** the debugger lacks a clear mapping to a source expression; names may be optimized/reinterpreted or un-evaluatable.
6. **Source/artifact mismatch:** a local named `discount` in newer source did not exist in older bytecode.

Missing local metadata does not mean **the JVM lacks internal values**. It means the debugger UI lacks reliable information to map bytecode slots to **source names** at that location.

## 6. Debug Information in Class Files: Three Groups to Remember

`javac` can embed extra debug attributes into `.class` files:

| Attribute | Role | Practical impact |
| --- | --- | --- |
| `SourceFile` | Original source filename (e.g., `DebugFrameDemo.java`). | Helps debuggers/stack traces identify the source file; **does not embed the entire source file**. |
| `LineNumberTable` | Maps bytecode offsets to source line numbers. | Enables line breakpoints, stepping, and line numbers in stack traces. |
| `LocalVariableTable` (and sometimes `LocalVariableTypeTable`) | Maps slots to names/types/scopes of locals and parameters. | Enables `locals`/Variables to display names and values in the current frame. |
| `MethodParameters` | Formal parameter names and flags for reflection when compiled with `-parameters`. | **Does not replace `LocalVariableTable`** for inspecting all local variables. |

Attributes such as `SourceFile`, `LineNumberTable`, and `LocalVariableTable` are **optional information** in class files. `-g:none` still produces a valid class with bytecode, methods, fields, and mandatory metadata for JVM execution; it does not "erase method names" or turn code into an absolute mystery.

### Default `javac` Differs from `javac -g`

A critical point in **Oracle/OpenJDK javac 17**:

- **Default without `-g`:** the compiler typically records **`lines` and `source`**, yet **does not record local variable debug information**.
- **`-g`:** records full `lines,vars,source`, including local variable info.
- **`-g:lines,source`:** records line numbers and source file without requesting local-variable info.
- **`-g:vars`:** records local variable info, without **requiring line numbers/source file**; unsuitable if you want full source-line debugging.
- **`-g:none`:** emits none of those debug information groups.
- **`-parameters`:** adds formal method parameter name metadata for reflection; **does not replace `-g`**.

For builds needing line-by-line debugging and variable inspection, choose **`javac -g`** (or `-g:lines,vars,source`) on test/staging artifacts. Running plain `javac Demo.java` lets line breakpoints work while `locals` in `jdb` lacks local names.

Do not confuse compiler `-g` with Java launcher `-agentlib:jdwp`: **`-g` determines metadata packaged at compile time**, whereas the **JDWP agent** enables debuggers to attach to a **running JVM**. The two options complement each other and do not replace one another.

## 7. Java 17+ — Hands-On Program for Breakpoints, Frames, and Locals

Save as **`DebugFrameDemo.java`**:

```java
public final class DebugFrameDemo {
    private static final int DELIVERY_FEE = 5;

    public static void main(String[] args) {
        int quantity = 3;
        int unitPrice = 7;

        int subtotal = calculateSubtotal(quantity, unitPrice);
        int total = addDeliveryFee(subtotal);

        System.out.println("total=" + total);
    }

    private static int calculateSubtotal(int quantity, int unitPrice) {
        int raw = quantity * unitPrice;
        int discount = quantity >= 3 ? 2 : 0;
        int afterDiscount = raw - discount;

        return afterDiscount;
    }

    private static int addDeliveryFee(int subtotal) {
        int total = subtotal + DELIVERY_FEE;
        return total;
    }
}
```

Deterministic calculation: `3 × 7 = 21`, minus `2` gives `19`, plus `5` delivery fee gives `24`.

Compile with **full debug information** and run normally (JDK 17+):

```bash
mkdir -p out
javac -g -d out DebugFrameDemo.java
java -cp out DebugFrameDemo
```

**Exact stdout:**

```text
total=24
```

If the program does not print `total=24` outside the debugger, verify the classpath and source file before debugging; avoid using a debugger to mask errors caused by running the wrong artifact.

### 7.1. Debugging with an IDE

In any Java IDE supporting JDWP/JDI:

1. Open the project containing the source, ensure **JDK 17+** is used, and build the exact class being run. Start in debug mode and pause at `int raw = quantity * unitPrice;`.
2. When paused at the start of the line, check `quantity=3`, `unitPrice=7` inside **frame `calculateSubtotal`**. `raw` may not be assigned yet, depending on position.
3. Press **Step Over** once to execute the `raw` assignment, then confirm `raw=21`.
4. Step Over across `discount` and `afterDiscount`; at positions after those lines, verify `discount=2` and `afterDiscount=19`.
5. Use **Step Out** to return to `main`: observe `subtotal=19` after the call completes.
6. On the `addDeliveryFee(subtotal)` call line, use **Step Into** to enter the method, verify `subtotal=19`; Step Over to compute `total=24`; Step Out back to `main` and Resume.
7. Open **Frames/Call Stack** while paused inside `calculateSubtotal`; select `main` to inspect the caller's locals, then switch back to the current frame.

When a variable becomes visible depends on source line/bytecode location; do not conclude a value is "wrong" when the debugger is still paused **before** the assignment. If the IDE stops on the next line or jumps past step targets, check step filter settings and compiler mapping.

### 7.2. Debugging with `jdb` and JDWP on Localhost

To observe the debugger in terminals, use **two terminals** on the **test machine**. Terminal 1 starts the JVM with JDWP, paused before entering `main`:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 \
  -cp out DebugFrameDemo
```

- `transport=dt_socket`: debugger connects over a socket.
- `server=y`: JVM opens a listening socket.
- `suspend=y`: JVM waits for debugger connection/resume before executing `main`.
- `address=127.0.0.1:5005`: listens only on this machine's IPv4 loopback, avoiding exposing a debug port to the network.

Terminal 2 connects with **the JDK's `jdb`**, pointing source path to the directory containing `DebugFrameDemo.java`:

```bash
jdb -attach 127.0.0.1:5005 -sourcepath .
```

After connecting, enter each command at the `jdb` prompt (these are **not** Bash commands):

```text
stop in DebugFrameDemo.calculateSubtotal
cont
where
locals
print quantity
print unitPrice
next
locals
print raw
up
locals
down
cont
```

Meaning:
- `stop in ...` sets a **method entry breakpoint** (may be deferred until the class loads).
- `cont` lets execution run to that breakpoint.
- `where` prints the Java stack trace of the **suspended thread**.
- `locals` shows visible locals/parameters if `-g` supplied metadata.
- `print quantity`, `print unitPrice` inspect variable values in the current frame.
- `next` executes past the paused statement and stops at the next source location in the matching frame; afterward `raw` is expected to be `21`.
- `up`/`down` (when available in your `jdb`'s `help`) select caller/callee frames to read context, **without rolling execution backward**.
- `cont` resumes so the program finishes and prints `total=24`.

**`jdb`** output (prompts, thread IDs, line numbers, message ordering) depends on JDK and session; no fixed log output is guaranteed. For a method breakpoint right on entering `calculateSubtotal`, inspect `quantity` and `unitPrice` first, and check `raw` only **after** stepping past its assignment line.

To practice a **line breakpoint**, replace `stop in ...` with `stop at DebugFrameDemo:<line-number>` using the **actual** line number in your source. Examples avoid hardcoding line numbers because adding/removing comments shifts them. `jdb` supports method `stop in Class.method` and line `stop at Class:line` per JDK 17 docs.

**Security:** JDWP is a highly sensitive JVM control interface. Use it only in controlled environments, bind loopback, and never expose or forward the port unprotected. A debugger can read sensitive data, pause threads, or alter state inside the JVM. Never use `address=*:5005` in production merely for convenience.

## 8. Self-Checking `-g` with `javap`

To know what metadata a `.class` file contains, use `javap` instead of guessing from an IDE. Use the **same source** compiled into separate directories so builds do not overwrite one another:

```bash
mkdir -p build/default build/full build/none build/partial

# Default: usually includes lines and source, omits vars
javac -d build/default DebugFrameDemo.java

# Emit full line/source/local variable debug info
javac -g -d build/full DebugFrameDemo.java

# Omit those debug attributes
javac -g:none -d build/none DebugFrameDemo.java

# Only source + line numbers
javac -g:lines,source -d build/partial DebugFrameDemo.java
```

Inspect each artifact:

```bash
javap -l -p -classpath build/default DebugFrameDemo
javap -l -p -classpath build/full DebugFrameDemo
javap -l -p -classpath build/none DebugFrameDemo
javap -l -p -classpath build/partial DebugFrameDemo

# To inspect full attributes and bytecode locations:
javap -v -p -classpath build/full DebugFrameDemo
```

Expected metadata types (not fixed line numbers):

| Build | `SourceFile` | `LineNumberTable` | `LocalVariableTable` | Impact when debugging |
| --- | --- | --- | --- | --- |
| Default `javac` on JDK 17 | Yes | Yes | Usually **no** | Line breakpoints/stack traces have line numbers; `locals` may lack variable names. |
| `javac -g` | Yes | Yes | Yes | Convenient for line stepping and inspecting locals/parameters. |
| `javac -g:none` | No | No | No | Method breakpoints may still work; cannot reliably map lines or variable names. |
| `javac -g:lines,source` | Yes | Yes | No | Has line numbers, lacks local variable metadata. |
| `javac -g:vars` | Not requested | Not requested | Yes | Has local names, yet source-line breakpoints still lack mapping without `lines`. |

`javap -l` primarily prints **line and local variable tables**, while `javap -v` also lists class attributes like `SourceFile`. In full-debug output, look for:

```text
LineNumberTable:
  line ...: ...
LocalVariableTable:
  Start  Length  Slot  Name          Signature
  ...    ...     ...   quantity      I
  ...    ...     ...   unitPrice     I
  ...    ...     ...   raw           I
```

The `...` markers are structural placeholders, **not verbatim copy-pasted output** from a real run. Actual start/length/slot and line numbers must be read from the real artifact.

### What `javap` Tells You and What It Does Not

`LineNumberTable` stores PC → line mappings inside a method, not **the entire source code**. `LocalVariableTable` stores names, types, slots, and bytecode ranges, not a log of variable values over time. `SourceFile` is just a filename, **not the source contents**. Therefore, keep source aligned with the build so the IDE opens the right lines.

Non-`javac` compilers (Kotlin, Scala, Groovy), bytecode weaving steps, obfuscation, shrinking, or ProGuard can alter debug attributes and names. Inspect classes **after the final build step**, not just intermediate `javac` outputs. If obfuscated, store mapping files securely.

## 9. `-parameters` Is Not Equivalent to Local Debug Info in a Debugger

`javac -parameters` emits the `MethodParameters` attribute so the Java Reflection API can retrieve **parameter names** of methods/constructors, e.g. `Executable.getParameters()`. However, it does not record the name of `int raw` inside the method body.

You can compile:

```bash
javac -parameters -g:none -d build/none DebugFrameDemo.java
javap -v -p -classpath build/none DebugFrameDemo
```

In this build, `MethodParameters` can appear for methods with parameters even though `LineNumberTable` and `LocalVariableTable` are disabled. That means a reflection framework sees parameter names while an IDE does not necessarily have enough data for line breakpoints and viewing `raw`. Conversely, `-g` helps local debugging without guaranteeing every reflection API reports `isNamePresent() == true` unless `-parameters` is also passed.

If the goal is **both reflection and full source debugging** in a test environment, you can use:

```bash
javac -g -parameters -d out DebugFrameDemo.java
```

Do not blindly change compiler flags in production builds; debug metadata can enlarge artifacts and make internals easier to read if someone obtains the binary, though it does not turn Java bytecode into secret data on its own.

## 10. Conditional Breakpoints: Picking the Right Moment and Avoiding Side Effects

A conditional breakpoint can use an expression like:

```java
quantity == 3 && unitPrice == 7
```

This is an **expression entered in the IDE's conditional breakpoint configuration UI**, not a standalone program. When execution reaches that location, the IDE suspends only if the condition holds according to the debugger mechanism.

Points to consider:

- The condition must reference **variables visible in the breakpoint's frame**. Placed at the top of `main`, `quantity` is not yet declared/assigned, so the expression may fail to evaluate.
- A condition on a hot line executed millions of times can cause massive overhead because the debugger evaluates it on every hit.
- Never call methods with side effects like `order.setStatus(...)` or `repository.save(...)` inside a conditional breakpoint.
- Even seemingly harmless getters can lazy-load, lock, or make network calls; prefer pure expressions, fields/primitives/simple comparisons.
- Conditions can throw exceptions (`null`, index out of bounds), preventing the debugger from pausing as expected; check IDE evaluation error logs.
- Never log/display tokens, passwords, or PII if debugging production data.

A **hit-count breakpoint** ("pause on the Nth pass") is better when inspecting a specific iteration. An **exception breakpoint** is better when catching where `throw` happens; conditions only fit matching a specific input. Do not default to conditional breakpoints inside every loop.

With JDK 17 `jdb`, `stop at` and `stop in` are the basic forms. Convenient "conditional breakpoint" support depends on the debugger/IDE; never assume `stop ... if ...` syntax is universally supported in `jdb`.

## 11. Exception Breakpoints: Caught vs. Uncaught

Java can throw and catch an exception within the same request. Setting a breakpoint only on a `catch` clause may not show **where the exception originated**. Debuggers offer a mode to pause when an exception of interest is **thrown**, even if ultimately caught, depending on "caught/uncaught" settings.

Standalone example `ParseDebugDemo.java`:

```java
public final class ParseDebugDemo {
    public static void main(String[] args) {
        try {
            parsePositive("0");
        } catch (IllegalArgumentException ex) {
            System.out.println("handled=" + ex.getMessage());
        }
    }

    private static int parsePositive(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new IllegalArgumentException("must be positive");
        }
        return value;
    }
}
```

Compile and run with JDK 17+:

```bash
javac -g ParseDebugDemo.java
java ParseDebugDemo
```

**Exact stdout:**

```text
handled=must be positive
```

Because `main` catches `IllegalArgumentException`, the program **exits normally**. However, if the debugger is configured to break on **caught exceptions**, you can see the stack frame at `throw new IllegalArgumentException(...)` inside `parsePositive` **before** entering `catch`.

In `jdb`, `catch java.lang.IllegalArgumentException` configures pausing when that exception class is thrown. `ignore java.lang.IllegalArgumentException` stops the debugger from watching it; it **does not** cause the JVM to ignore the exception at runtime. In applications that throw expected exceptions frequently, this breakpoint type can fire very often; narrow the scope and remove the breakpoint when finished.

## 12. Multiple Threads: Which Thread Hit the Breakpoint?

Suppose `main` submits a `Runnable` to a worker. When a breakpoint inside `run()` or a worker-called method triggers:

- The **worker's** call stack holds executor/`ThreadPoolExecutor` frames and the running method; the `main` thread that submitted it does not sit underneath those frames.
- If you select the **main thread** in the Threads panel, the debugger may show it inside `Future.get()` or elsewhere.
- A local `int jobId` in the worker's frame differs from a local in `main`, even if the variable shares a name or object reference.
- If the breakpoint suspends **all threads**, the app can freeze the entire JVM per debugger policy, timing out sockets/databases/health checks; if it suspends only the **event thread**, other threads continue mutating shared state.

Example `AsyncDebugDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class AsyncDebugDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> future = pool.submit(() -> doubleValue(4));
            System.out.println("result=" + future.get());
        } finally {
            pool.shutdown();
        }
    }

    private static int doubleValue(int input) {
        int result = input * 2;
        return result;
    }
}
```

Compile and run:

```bash
javac -g AsyncDebugDemo.java
java AsyncDebugDemo
```

**Exact stdout:**

```text
result=8
```

Set a breakpoint on `int result = input * 2;`. When the worker pauses, inspect **Threads** and then the worker's **Frames**; the caller of `doubleValue` may be lambda/`FutureTask`/executor internals. The main thread may be waiting in `future.get()`. Do not look for `main` beneath `doubleValue` on the worker's stack.

With futures/reactive pipelines, a request can have a **logical call chain** spanning multiple threads/callbacks; a Java stack trace is only one thread's synchronous call chain at observation time. Use correlation IDs/tracing or async debugger support when tracing origin-to-destination relationships.

### Debuggers Can Sometimes Make Bugs Disappear

Breakpoints alter timing. A suspended thread holding a lock can cause another thread to time out; a data race may stop reproducing because scheduler interleaving changed. For concurrency bugs, combine **thread dumps, JFR, correlation-ID logs, and stress tests** instead of relying solely on manual stepping.

Java 17 primarily uses platform threads; virtual threads are a feature in later JDK releases. When debugging newer JDKs, UI/support for virtual threads can differ, so do not blindly carry every JDK 17 debugger assumption onto a newer runtime without checking.

## 13. JIT, Inlining, Lambdas, and Generated Code Make Stepping Counter-Intuitive

HotSpot's JIT can inline methods or optimize execution paths. Debuggers use runtime mechanisms to observe/pause and adjust compiled code state; nevertheless, **source-level stepping does not mean each source line maps to a single machine step**.

Surprising cases:

- A source line with **multiple expressions** or method calls can cause `step into` to enter a different call than expected.
- One source line corresponds to multiple bytecode offsets; stepping may pause on the same line again or skip declaration-only lines.
- Uninitialized or out-of-scope locals become unavailable even though their names appear nearby on screen.
- Lambdas, bridge methods, record constructors, generated proxies, and framework bytecode create frames/method names not written directly in source.
- Exceptions/`finally` blocks and compiler-generated code can route control flow through points that look different from surface syntax.
- When the JVM is inside a native method, Java source-level line/local debugging has different limits.

To check **which bytecode is actually running**, run `javap -c -l -p` on the exact class:

```bash
javap -c -l -p -classpath out DebugFrameDemo
```

Depending on the situation, try **selective Step Into**, narrow step filters, or method-entry breakpoints rather than forcing `step` through hundreds of library frames. You can use `-Xint` to study interpreter behavior in tests, though it dramatically changes performance/timing and must never be treated as a default fix for production bugs.

## 14. When You Have Source Without Debug Info — What Can You Still Do?

In a `-g:none` build:

- The JVM still runs Java bytecode normally; class/method/field descriptors remain for linking and execution.
- You can set **method entry breakpoints** or use appropriate class/method observation tools, depending on JVM/debugger support.
- You can read object/static fields when holding a reference and debug access; not every local variable's source name is required.
- You can run `javap -c -p` to inspect bytecode and pick alternative observation points, even without source line mapping.
- You can add logs/JFR/metrics in another build or reproduce the same bug on **staging built with `-g`**.

However, you cannot recover all local names, filenames, and line mappings **merely by opening the matching source in an IDE** if the bytecode lacks that metadata. Decompilers can reconstruct **synthetic source** to understand control flow, yet cannot restore every original expression/variable and must never be treated as proof of original line numbers.

IDEs may display synthetic names (`var1`, `arg0`) or compiler-specific hints; those names are not always the original source names. Distinguish "the debugger guessed/rendered a value" from "`LocalVariableTable` proving a variable's name and scope."

## 15. Workflow for Investigating a Breakpoint That Does Not Match Code

When the debugger reports **"No executable code found at line"**, an unverified breakpoint, or missing locals:

1. **Verify the real process:** right PID/port, right main class, JDK/vendor, service version, and container/pod?
2. **Verify loaded classes:** classpath/module-path, JAR/module, artifact checksum/version, class loader. Is another copy of `DebugFrameDemo` running?
3. **Verify source:** does the open source file match the exact commit/build of the class? Is the IDE reading an outdated source jar?
4. **Verify debug metadata:** run `javap -v -l -p` on the `.class` file from **the actual build**. Are `SourceFile`, `LineNumberTable`, and `LocalVariableTable` present?
5. **Verify stop location:** does the line have executable code, is the method called, and is the condition true? Is the variable initialized/in scope?
6. **Verify thread state:** is the right thread suspended? Is the selected frame the target method or its caller?
7. **Verify debugger settings:** disabled breakpoints, suspend policy, class/exception filters, evaluation errors, compiler/IDE step filters.
8. **Try a minimal reproduction:** compile a test with `javac -g`, run directly with `java -cp ...`, set a method breakpoint, verify locals/stepping, then return to the complex environment.
9. **Cross-check behavior:** if the bug only triggers under natural timing, use JFR/logging/metrics instead of adding dozens of breakpoints that skew thread scheduling.
10. **Close the debug session:** remove JDWP when no longer needed; never leave ports open or save screenshots/variables containing secrets in public tickets.

### Quick Decision Table

| Symptom | First check | Resolution |
| --- | --- | --- |
| Gray/unbound line breakpoint | `LineNumberTable`, class loaded, source matches build. | Compile `-g`/`-g:lines,source`, verify artifact/executable line. |
| Missing `locals` or JDI `AbsentInformationException` | Does `LocalVariableTable` exist? | Recompile with `-g` or `-g:vars` plus appropriate lines/source; attach to right JVM. |
| Stack trace shows `Unknown Source` or no line numbers | `SourceFile`/`LineNumberTable` in class. | Fix build debug info; copying source alone does not help. |
| Variable reported unavailable | Before assignment, out of scope, or wrong frame? | Step Over to line after assignment; select the right frame. |
| Values differ from open source | Deployed class/JAR out of sync with source? | Check checksums/artifacts, rebuild, and redeploy controlled test. |
| Step Into enters library/framework | Call order, compiler synthetics, step filters. | Smart Step Into (if IDE supports), method breakpoint, select frame. |
| Breakpoint pauses too often / extremely slow | Loops, many threads, conditional evaluation. | Hit count, targeted filters, less intrusive logs/JFR. |
| Main parked at `future.get()`, worker paused in handler | Two threads have separate stacks. | Switch threads in debugger; use tracing across async boundaries. |
| Application times out while paused | Breakpoint suspended all/locks/health checks. | Debug on staging; limit suspend scope and avoid pausing production. |
| Cannot attach | JVM lacks JDWP, wrong bind port, network/permissions. | Enable on localhost/test, verify port and secure JDWP config. |

## 16. Common Misconceptions and How to Fix Your Thinking

- **"If I have Java source, the IDE can always show locals."** False: names/scopes require class metadata, especially `LocalVariableTable`.
- **"Default `javac` always includes all debug info."** False on JDK 17: default includes source/lines, not local vars.
- **"`-parameters` is enough to inspect `int raw` in the debugger."** False: `MethodParameters` gives formal parameter names via reflection, not `LocalVariableTable` for locals.
- **"`-g:none` makes all method breakpoints unusable."** False: line mapping/locals are absent, yet method/class metadata still exists.
- **"Step Over does not execute the called method."** False: the method executes; the debugger just does not step line by line into the new frame.
- **"Step Out skips the remaining statements."** False: remaining statements still execute until return/unwind.
- **"If paused on an assignment line, the left-hand variable already holds the new value."** False: debuggers typically pause **before** the statement executes.
- **"Stack traces always include variable values."** False: normally they only have method/file/line, not locals.
- **"An async callback's caller must appear in the worker's stack."** False: stack frames are per thread; logical traces across threads require dedicated mechanisms.
- **"Breakpoint didn't hit means the bug didn't happen."** Not necessarily: breakpoint may be pending, different class loader, source mismatch, or wrong condition.
- **"Expressions in conditional breakpoints are always safe to evaluate."** False: method evaluations can have side effects, locks, and overhead.
- **"Suspending threads does not affect the application."** False: it easily causes timeouts, deadlocks, and altered race timing.
- **"A remote debug port is just a read-only observation port."** False: JDWP can control/mutate state and must be strictly protected.
- **"`javap` prints the full original source."** False: it inspects bytecode and metadata; `SourceFile` is only a filename.
- **"The debugger can step backward into a returned frame just by clicking Up."** False: Up/Down only selects **frames still present on the suspended thread's stack**.
- **"Pausing the right thread means you understand all concurrency."** False: shared state/locks/other threads may keep running or be suspended depending on policy.

## 17. Practice Checklist

Before a debug session:
- [ ] Know **the build and JVM running**, matching source/commit/JAR.
- [ ] For tasks needing locals and source lines, compile with `javac -g`; verify with `javap -v -p` if metadata seems missing.
- [ ] Distinguish `SourceFile`, `LineNumberTable`, `LocalVariableTable`, and `MethodParameters`.
- [ ] Pick method/line breakpoints with executable bytecode; avoid conditional breakpoints on hot paths.
- [ ] If debugging remotely, bind loopback in a test environment, control access, and never expose JDWP to the Internet.

During a debug session:
- [ ] Check which thread is paused, and whether policy is suspend event thread or suspend all.
- [ ] Open the call stack, pick the right frame, and understand caller/callee.
- [ ] Inspect parameters/locals **after initialization**, within their lexical scope.
- [ ] Use Step Into/Over/Out according to your investigation question; remember methods still execute on Step Over.
- [ ] For async flows, inspect worker threads separately and use correlation/tracing for cross-thread logic.
- [ ] Record needed values while avoiding secrets; distinguish program output from debugger output.

After a debug session:
- [ ] Reproduce with a test or low-intrusion log/JFR to validate the hypothesis.
- [ ] Compare before/after changes on **the same build/workload**.
- [ ] Remove costly breakpoints, close the debug session, and disable JDWP when no longer needed.
- [ ] Never assume the JVM is buggy because source lines "jump oddly" before checking bytecode mapping.

**Remember:** A breakpoint is a **stop point at a bytecode location**, stepping chooses **the next execution boundary**, a stack frame is the context of **one method invocation on one thread**, and local variables have their **own scope and lifetime**. For accurate source-line debugging and local variable names, JDK 17 typically requires **`javac -g`**; opening source in an IDE alone cannot recreate metadata missing from `.class`. Always verify the artifact, right thread/frame, assignment timing, and remote debugger safety.

### Official References

- [Oracle JDK 17 — `javac`: `-g`, `-g:none`, `-g:lines,vars,source`, and `-parameters`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle JDK 17 — `javap`: `-l`, `-c`, `-v`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [Oracle JDK 17 — `jdb`: method/line breakpoints and `step`/`next`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdb.html)
- [Oracle JDK 17 — JPDA connection / `-agentlib:jdwp`](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html)
- [Oracle — JPDA FAQ: `AbsentInformationException` when LocalVariableTable/LineNumberTable are missing](https://www.oracle.com/java/technologies/javase/java-platform-debugger-architecture.html)
- [Oracle JDK 17 — JDI `StackFrame`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdi/com/sun/jdi/StackFrame.html)
- [Java SE 17 JVM Specification — class-file attributes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7)
