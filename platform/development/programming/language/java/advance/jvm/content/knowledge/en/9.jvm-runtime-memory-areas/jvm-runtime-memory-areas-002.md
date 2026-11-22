# The pc Register and JVM Stack During Thread Execution

When the JVM runs a Java method, it must know **which bytecode instruction is currently being executed** and **where the method invocation state resides**. The two foundational components in the JVM model are:

- **`pc register` (program counter register)**: **per-thread** state used to represent the position of the JVM instruction currently being executed.
- **`JVM stack` (Java Virtual Machine stack)**: a **per-thread** stack containing the **frames** of active method invocations.

A thread entering `main`, calling `service()`, and then calling `calculate()` transitions through different frames. `pc` indicates the thread's current instruction; the JVM stack holds local variables, the operand stack, and the information needed to return to the caller or handle exceptions. Understanding both is what explains nested calls, recursion, stack traces, `StackOverflowError`, context switching between threads, and why `-Xss` is not synonymous with heap size.

This article uses the model from **JVMS Java SE 17 §2.5.1–§2.5.2 and §2.6**; examples are compiled with Java 17+. The terms `pc` and frame below are first and foremost **JVM semantics**, not a claim that HotSpot always stores them in a physical CPU register or a single contiguous RAM region.

## 1. Placing the pc register and JVM stack in the overall runtime data areas

The JVMS distinguishes between **per-thread** data areas and those **shared across threads**:

| JVM Data Area | Scope | Role in this article |
| --- | --- | --- |
| **pc register** | **One per thread** | Tracks the JVM instruction currently running in that thread |
| **JVM stack** | **One per thread** | Holds the frames of active invocations |
| **Frame** | Belongs to one method invocation in one thread | Local variables, operand stack, dynamic linking, return/exception state |
| **Heap** | Shared across the JVM | Holds objects and arrays; multiple frames can hold references to the same object |
| **Method area** | Shared across the JVM | Class data, method code, and related information |
| **Run-time constant pool** | Data associated with each class/interface, in a JVM-managed area | Symbolic references used by bytecode in frames |
| **Native method stacks** | Dependent on the JVM/implementation and thread/native invocation | Supports executing native code if used by the implementation |

Do not conflate the **operand stack** inside a frame with the **JVM stack** containing frames: they have a nested relationship but are at different levels.

```text
                       One JVM
     +------------------------------------------+
     | Heap, method area, runtime constant pools|
     |        (shared among threads)            |
     +------------------------------------------+
           ^                         ^
           | references / metadata   |
    +-----------------+      +-----------------+
    | Thread A        |      | Thread B        |
    | pc register A   |      | pc register B   |
    | JVM stack A     |      | JVM stack B     |
    |  [frame m3]     |      |  [frame n2]     |
    |  [frame m2]     |      |  [frame n1]     |
    |  [frame m1]     |      |                 |
    +-----------------+      +-----------------+
```

For example, local slot 1 of a frame belonging to thread A and local slot 1 of a frame belonging to thread B **are not the same slot**. However, if they contain references pointing to **the same object on the heap**, both threads can still read/write that object's state. **Thread-private stacks do not mean all referenced data is thread-safe.**

## 2. The pc register: what is the exact model?

According to JVMS §2.5.1, **each JVM thread has its own pc register**, created along with the thread. At any point, a thread is executing the code of a single method. If that method is **not native**, the pc register contains the **address of the JVM instruction currently being executed** in that method.

This gives the JVM its own control model for threads: thread A can be at the `iadd` opcode of `compute`, while thread B is at the `invokevirtual` opcode of `service`.

### What if the thread is executing a native method?

When the current method is **native**, the JVMS specifies that the value of the pc register is **undefined**. This is a very important statement:

- One must not claim that the JVM pc of a thread running a JNI/native method always points to "the last bytecode".
- A **native machine-code** instruction address and the JVM pc register in JVMS semantics are **two different concepts**.
- A native call may interact with C/C++, the OS stack, or VM native mechanisms, but that implementation detail **does not change** the fact that the JVM pc register is specified as undefined while in a native method.

### Is the pc register a hardware instruction pointer?

Not necessarily. The JVM is an **abstract virtual machine**. An interpreter may manage bytecode position using a BCI (bytecode index)/internal pointer; a JIT may compile the method to machine code. The physical CPU has its own instruction pointer, whereas the JVMS contract defines the **logical pc state of a JVM thread**. You cannot ask `Thread.currentThread()` to directly return this pc register value as a public Java field.

### pc, bytecode index (BCI), and source line

| Concept | Meaning | Example |
| --- | --- | --- |
| JVM thread `pc` | Position of the JVM instruction **currently executing** in the JVM model | Instruction belonging to `calculate()` of the current frame |
| **BCI / bytecode offset** | Offset in **bytes** from the start of a method's `code[]` | `0: iload_0`, `1: iconst_1`, `2: iadd` |
| **Source line** | Line in the Java file according to debug metadata | `Calculator.java:12` |
| CPU instruction pointer | Native instruction address of the CPU/JIT/interpreter | Implementation detail, not a direct Java BCI |

One Java source line can map to **multiple** instructions; an instruction can correspond to a source line via `LineNumberTable`, or a class may lack debug line numbers. `javap -c` displays BCI; `javap -l` can display line/local tables. These tables are **not** an API to read the exact pc of an arbitrary thread at any point in time.

## 3. The JVM stack: a stack of frames, not a heap

According to JVMS §2.5.2, each JVM thread has a **private JVM stack**, created at the same time as the thread, storing **frames**. The JVM stack does not directly allow arbitrarily fetching a local variable belonging to another thread's frame using normal Java code.

Some characteristics:

1. **LIFO**: calling a new method usually results in a new frame becoming the current frame; when the method finishes, that frame is exited and the caller resumes.
2. **Each invocation has one frame**: the same method called recursively three times is three invocations, and therefore has three separate frames with separate locals.
3. **Each frame has its own operand stack**: there is no single shared operand stack for all methods/threads.
4. **The stack stores method state, not entire objects**: local/reference operands can point to objects on the heap.
5. **JVM stacks can be fixed-size or dynamically sized depending on the implementation**, and frame memory may be allocated from the heap or elsewhere in a conforming implementation. Do not assume the JVMS requires frames to be physically contiguous memory blocks.
6. **The stack terminates with the thread** at the lifecycle model level. How the JVM/OS reclaims native memory and optimizes storage is an implementation detail.

### Nested call frames

Suppose:

```java
public static int first(int x) {
    return second(x) + 1;
}
public static int second(int x) {
    return third(x) * 2;
}
public static int third(int x) {
    return x + 3;
}
```

These are **three illustrative methods** that need to be placed in a class to compile. When `first(4)` calls `second(4)` and then `third(4)`:

```text
Top of JVM stack
+---------------------+
| frame third(4)      | <- CURRENT when third executes
| locals: x=4         |
| operand stack ...   |
+---------------------+
| frame second(4)     | <- paused waiting for third to return a value
| locals: x=4         |
| operand stack ...   |
+---------------------+
| frame first(4)      | <- paused waiting for second
| locals: x=4         |
| operand stack ...   |
+---------------------+
Bottom of JVM stack
```

When `third` returns `7`, the `third` frame is no longer the current frame; `second` receives the result, computes `14`, and returns it to `first`; `first` adds 1 to get `15`. Every `x` belongs to its own frame, even though all values equal `4`.

### "Thread stack", "call stack", and "operand stack" are easily conflated

- **JVM stack / Java call stack**: the model managing active method frames in a thread.
- **Operand stack**: the area inside **each frame**, used for bytecode computation; bounded by `max_stack`.
- **Native/OS stack**: the area that native code and the VM itself may use according to the system; its physical relationship with Java frames depends on the JVM and thread type.
- **Heap**: the place holding objects/arrays allocated under JVM semantics. References to objects can reside in locals/operand stack; there is no rule that "all primitives live only on the stack, all references live only on the heap".

## 4. What is inside a frame?

JVMS §2.6 describes a **frame** as containing:

- **Local variable array**: numbered slots storing the receiver `this` (if an instance method), parameters, and local values.
- **Operand stack**: a LIFO area holding operands and intermediate results for JVM instructions.
- **A reference to the run-time constant pool** of the class containing the method: used to support **dynamic linking**, resolving symbolic references in instructions such as field access, method invocation, and object creation.
- **Information for normal/abrupt method completion**, including returning to the caller or handling/propagating exceptions per JVM rules.

The `.class` file provides a `Code` attribute with `max_locals` and `max_stack` bounds for a method with code. Each method invocation creates its own frame state according to these bounds.

| Part of the frame | How is it read from bytecode? | Common misconception |
| --- | --- | --- |
| Local variables | `iload`, `istore`, `aload`, `astore`, `lload`... | Assuming local index always equals parameter order in source |
| Operand stack | `iconst`, `iadd`, `invoke*`, `dup`, `pop`... | Assuming each thread has only one shared operand stack |
| Dynamic linking | `getfield`, `invokevirtual`, `invokestatic`... via the constant pool | Assuming a frame already holds fixed native addresses for all symbolic references |
| Return state | `ireturn`, `areturn`, `return`, etc. | Assuming the callee keeps running after return |
| Exception handling | Exception table, `athrow`, JVM instruction errors | Assuming an exception always terminates the entire thread |

### Local slots: category 1 and category 2 values

- `int`, `float`, and reference belong to computational **category 1**, each value requiring **one slot**.
- `long` and `double` belong to **category 2**, each value requiring **two slots** in the local-variable array and contributing two units of depth on the operand stack.
- `byte`, `short`, `char`, and `boolean` are represented/processed in an appropriate computational form, typically as `int` on the operand stack/locals.
- **Instance** methods normally place the receiver `this` at local slot **0**, followed by parameters; **static** methods have no hidden receiver.
- A `long` at slot 1 occupies slots 1–2; the next parameter cannot use slot 2 as an independent value.

Example method:

```java
static long mix(int count, long amount, double factor) {
    return amount + count;
}
```

This is an **illustrative method**. In a static method, `count` is at slot 0, `amount` uses slots 1–2, and `factor` uses slots 3–4 even though it is not used in the body. The compiler may add local slots if needed; `max_locals` must at minimum cover all parameters per the descriptor. The operand stack for `ladd` can hold two `long` values at once, totaling **4 slots**.

## 5. How do pc and the JVM stack coordinate during a method call?

Model of a single invocation:

1. The caller is in the **current frame** and pc reflects the position of the call instruction, e.g., `invokestatic`.
2. The caller pushes the arguments (and receiver if an instance method) onto the **caller's operand stack** matching the descriptor.
3. The JVM performs the invocation, determines the target method via the appropriate resolution/selection mechanism, and sets up a **new frame** for the callee (unless the implementation uses optimizations that preserve behavior).
4. The callee becomes the **current method/current frame**; arguments are transferred into the callee frame's locals at the corresponding slot indices.
5. The thread's logical pc represents the instruction currently executing in the callee. The caller pauses at the call site while the callee executes.
6. When the callee performs a **normal return**, the callee frame is exited; if there is a return value, the caller receives it on the **caller's operand stack**; the caller then continues at the next part after the call.
7. If the callee completes **abruptly** due to an exception, the JVM searches for an exception handler in the current frame or unwinds to the caller according to the exception table and propagation rules.

Key point: pc **belongs to the thread**, not a separate pc that can run concurrently for each frame. The caller state needed to resume is preserved through the invocation/return mechanism; the thread's pc moves along with the execution flow transitioning to the callee.

### Which opcodes can a method use to return?

| Return type | Typical instruction | Effect |
| --- | --- | --- |
| `void` | `return` | Does not push a return value |
| `int` and small primitive types in JVM representation | `ireturn` | Returns a category 1 value |
| `long` | `lreturn` | Returns category 2 |
| `float` | `freturn` | Returns category 1 |
| `double` | `dreturn` | Returns category 2 |
| Object/array reference | `areturn` | Returns a category 1 reference |

The callee does not "copy its entire frame" to the caller. Normally only the **return value** is passed under stack semantics, while the callee's locals/operand stack and method-specific state end with that frame.

## 6. Java 17 in practice: two nested calls and bytecode

Create the file **`FrameCallDemo.java`**:

```java
public class FrameCallDemo {
    static int square(int value) {
        return value * value;
    }

    static int addSquare(int first, int second) {
        int temp = square(first);
        return temp + second;
    }

    public static void main(String[] args) {
        System.out.println("result=" + addSquare(3, 4));
    }
}
```

Compile/run:

```bash
javac --release 17 -g FrameCallDemo.java
java FrameCallDemo
javap -c -v -p FrameCallDemo
```

**Stdout of `java FrameCallDemo`**:

```text
result=13
```

Because `square(3) = 9` and `addSquare(3,4) = 9 + 4 = 13`.

### Following the frames from `main` to `square`

```text
A. main
   operand stack: ... arguments (3, 4) for addSquare
   invokedynamic/println allowing concatenation/printing may appear depending on compiler

B. entering addSquare
   locals: [first=3, second=4, temp not yet assigned]
   iload_0  -> [3]
   invokestatic square:(I)I
       |
       v
C. entering square
   locals: [value=3]
   iload_0  -> [3]
   iload_0  -> [3, 3]
   imul     -> [9]
   ireturn  -> caller receives 9

D. returning to addSquare
   operand stack after calling square: [9]
   istore_2 -> []; locals[temp]=9
   iload_2  -> [9]
   iload_1  -> [9,4]
   iadd     -> [13]
   ireturn  -> main receives 13
```

This is a **model of the relevant opcodes**. `javap` will have offsets, constant-pool indices, and the exact instructions in `main`; the string concatenation `"result=" + ...` may be lowered by the Java 17 compiler into `invokedynamic` with `StringConcatFactory`. The correctness of `square` and `addSquare` does not depend on this concat choice.

### Excerpt of typical disassembly structure

```text
static int square(int);
  Code:
    stack=2, locals=1, args_size=1
       0: iload_0
       1: iload_0
       2: imul
       3: ireturn

static int addSquare(int, int);
  Code:
    stack=2, locals=3, args_size=2
       0: iload_0
       1: invokestatic  #...  // Method square:(I)I
       4: istore_2
       5: iload_2
       6: iload_1
       7: iadd
       8: ireturn
```

The `#...` in the listing are **placeholders for constant-pool indices**, not verbatim output with a fixed index. Different `javac` versions may choose equivalent opcode sequences. Nevertheless:

- `square` needs two `int`s simultaneously on the operand stack before `imul`: max depth **2**; locals have one parameter of **1 slot**.
- `addSquare` has two `int` parameters and one local `temp`, so `locals=3` is reasonable for typical output; max operand stack is **2**.
- The `invokestatic` opcode in `addSquare` causes the thread to transfer execution to the `square` frame; the `ireturn` opcode transfers the result **9** back to the caller's stack.
- BCI `1` after `iload_0` is not a "pc register of square": it is the instruction offset in **`addSquare`'s code**.

### Tracking at each point in time

| Point in time | Current method | Active frames (bottom → top) | What logical pc represents |
| --- | --- | --- | --- |
| Before calling `addSquare` | `main` | `main` | Instruction in `main` |
| After invoking `addSquare` | `addSquare` | `main → addSquare` | Instruction belonging to `addSquare` |
| After invoking `square` | `square` | `main → addSquare → square` | Instruction belonging to `square` |
| After `square.ireturn` | `addSquare` | `main → addSquare` | Resuming instruction in `addSquare` |
| After `addSquare.ireturn` | `main` | `main` | Resuming instruction in `main` |

The table focuses on the **logical call stack**, without requiring HotSpot to create five physical machine stack structures as shown for each row.

## 7. Recursion: every call to the same method is still a new frame

With recursion, a method calls itself. The method name on the stack may repeat, but **locals are separate**, and pc reflects the instruction in the thread's currently running invocation.

Create the file **`RecursiveFrames.java`**:

```java
public class RecursiveFrames {
    static int countDown(int n) {
        if (n == 0) {
            return 0;
        }
        return 1 + countDown(n - 1);
    }

    public static void main(String[] args) {
        System.out.println("depth=" + countDown(3));
    }
}
```

```bash
javac --release 17 RecursiveFrames.java
java RecursiveFrames
```

**Stdout**:

```text
depth=3
```

At maximum depth:

```text
main()
  countDown(3)  locals[n=3]
    countDown(2) locals[n=2]
      countDown(1) locals[n=1]
        countDown(0) locals[n=0] -> return 0
      -> return 1
    -> return 2
  -> return 3
```

If the same method is called infinitely and the JVM cannot allocate another frame, the result can be **`StackOverflowError`**. The depth at the time of failure is **not fixed**, depending on the JVM, stack settings, frame representation, JIT, system, and runtime conditions. There is no need to run infinite recursion to demonstrate the mechanism; the finite example already proves each invocation has its own local state.

### Why `StackOverflowError` does not mean "the heap is out of memory"

It is a resource error related to the JVM thread's stack, not a default conclusion that the heap is full. Conversely, a program can hit `OutOfMemoryError` because it cannot create/expand a stack or lacks native resources; **the exception type must be read together with its message and context**.

## 8. How do exceptions change the current frame?

A method can terminate via:

- **Normal completion**: a return instruction resumes the caller and passes a result if any.
- **Abrupt completion**: an instruction throws an exception, or the method calls another method and the exception is not handled in the callee.

When an exception occurs, the JVM **does not necessarily discard the entire call stack immediately**. It searches for a matching entry in the current method's **exception table**. If a handler exists, execution continues at **`handler_pc`** within the same frame; if not, the frame completes abruptly, the exception propagates to the caller, and the JVM tries to find a handler at the caller's call site.

### Example of an exception caught in an outer caller

Create **`ExceptionFrames.java`**:

```java
public class ExceptionFrames {
    static int quotient(int numerator, int denominator) {
        return numerator / denominator;
    }

    static int transform(int value) {
        return quotient(10, value) + 1;
    }

    public static void main(String[] args) {
        try {
            System.out.println("good=" + transform(2));
            transform(0);
        } catch (ArithmeticException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
        }
        System.out.println("after");
    }
}
```

```bash
javac --release 17 ExceptionFrames.java
java ExceptionFrames
javap -c -v -p ExceptionFrames
```

**Stdout**:

```text
good=6
caught=ArithmeticException
after
```

Explanation:

1. `transform(2)` calls `quotient(10,2)`, receives `5`, and adds 1 to get `6`.
2. `transform(0)` calls `quotient(10,0)`; `idiv` throws `ArithmeticException`.
3. `quotient` has no matching handler, so the `quotient` frame completes abruptly.
4. `transform` has no matching handler, so the `transform` frame also unwinds.
5. In `main`, there is a `try/catch` protecting the call site; the JVM branches to `main`'s bytecode handler and executes the `catch` block.
6. `main` continues and prints `after`.

The **pc** while in `quotient` reflected `quotient`'s instruction; when the exception is caught in `main`, the current frame and logical pc move to `main`'s handler. One must not infer that "`idiv` failing means the JVM thread must stop".

### When the handler is in the same method

```java
static int safeDivide(int a, int b) {
    try {
        return a / b;
    } catch (ArithmeticException ex) {
        return -1;
    }
}
```

This is an **illustrative method**; place it in a class to compile. If `b=0`, the JVM selects the exception handler **within the `safeDivide` frame itself**, rather than automatically popping that frame. Only when the handler returns `-1` does the method complete normally back to the caller.

### The exception table uses bytecode offsets

For a `Code_attribute`, each handler entry has the form `start_pc`, `end_pc`, `handler_pc`, `catch_type`:

- The protected range is **`[start_pc, end_pc)`** — inclusive of start, exclusive of end.
- `handler_pc` points to the start of the exception-handling instruction.
- The handler receives the exception reference on the operand stack per JVM rules; the first instruction is typically `astore` to store the reference in a local.
- Entries are evaluated in the order defined in the exception table; the first matching entry determines handling.

These `start_pc/end_pc` values in the class file are **BCI offsets**, not the same memory slot as the thread-level "JVM pc register".

## 9. Two threads: two pc registers and two JVM stacks

The specification explicitly states that a JVM can support multiple threads executing concurrently; each thread has its **own pc** and **own stack**.

Example:

```text
Thread "worker"
  pc -> instruction of calculate()
  JVM stack: run() -> calculate()

Thread "main"
  pc -> instruction of main()
  JVM stack: main()
```

The `main` thread cannot directly read the `worker`'s operand stack like reading a Java `List`. However, both can hold references pointing to the same object on the heap and need synchronization when accessing shared state.

### Runnable Java 17: worker holds a frame while main keeps running

Create **`PerThreadStacks.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class PerThreadStacks {

    static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            int value = twice(21);
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            System.out.println("worker=" + value);
        }, "worker-example");

        worker.start();
        ready.await();
        System.out.println("main=ready");

        release.countDown();
        worker.join();
        System.out.println("main=joined");
    }
}
```

```bash
javac --release 17 PerThreadStacks.java
java PerThreadStacks
```

**Stdout of a normal, uninterrupted run**:

```text
main=ready
worker=42
main=joined
```

`CountDownLatch` makes `worker` wait after signaling ready; `main` prints `main=ready` **before** releasing `worker`. `join()` makes `main` print `main=joined` only after `worker` finishes. While `worker` is waiting at `release.await()`, the `worker` JVM thread still has its own call stack related to the task and waiting library methods; the `main` thread has its own frame in `main` code.

This is an example of **two stacks and synchronization**, not a way to measure stack size: `CountDownLatch` and `join` primarily coordinate threads and do not expose the actual pc register.

### Thread-private local state and shared heap objects

`int value = twice(21)` is a local value in the frame running on `worker`; it does not automatically become a local variable of `main`. If a lambda captures a reference to a shared object, that object's data can still be shared state. The JVM has no automatic protection preventing data races just because each thread owns its own stack. When designing concurrency, properly use the Java Memory Model, `volatile`, locks, immutable objects, or concurrent utilities.

## 10. The JVM stack can run out of space: `StackOverflowError` and `OutOfMemoryError`

JVMS §2.5.2 notes two important error categories:

- **`StackOverflowError`**: a computation in a thread requires a larger JVM stack than permitted. Deep recursion is a common example, though not the only source.
- **`OutOfMemoryError`**: if a JVM implementation allows dynamic stack expansion but cannot allocate sufficient memory, or cannot create the initial stack for a new thread due to insufficient memory, this error may occur.

### What is `-Xss`?

On many OpenJDK/HotSpot builds, `-Xss` configures the stack size of Java threads in units such as `k`, `m` (the exact application depends on the runtime/thread type and platform).

Illustrative command example:

```bash
java -Xss1m RecursiveFrames
```

This is only a **configuration** example, not a guarantee of exactly how many times a method can recurse. `-Xss` does not directly set bytecode `max_stack`; `max_stack` is the **operand stack depth in slots** for a method frame in the `Code` attribute, whereas `-Xss` relates to implementation thread-level stack resources.

### Why not use `StackOverflowError` as a business-logic branch?

- The failure point varies by JVM build, OS, optimization, frame shape, and call pattern.
- When the stack is nearly exhausted, even logging or constructing an exception message can hit resource limits.
- Catching `StackOverflowError` and trying to continue as if nothing happened can mask algorithmic bugs or leave state unreliable.
- Better fixes are limiting recursion depth, using an iterative algorithm, programmer-driven tail-recursion transformation where appropriate, or tuning workload/stack settings after measuring.

**Java does not guarantee automatic tail-call/tail-recursion optimization** to eliminate stack growth. Do not write unbounded recursive functions just because "the JIT will probably optimize the tail".

## 11. Comparing the JVM stack with the heap: where do objects live?

Java snippet:

```java
static int lengthOf(String value) {
    int n = value.length();
    return n;
}
```

This is an **illustrative method**, not a standalone file.

- The parameter `value` is a **reference** in a local slot of the `lengthOf` frame.
- The `String` object is managed under heap semantics, not "copied in full" into a local slot just because there is a parameter.
- `n` is a local primitive value; the JVM model has a local slot holding the result. With JIT, optimizations may keep it in a CPU register or eliminate unnecessary physical stores.
- Calling `value.length()` uses the operand stack to pass the receiver, then returns `int` to the caller. If `value == null`, dereferencing can throw `NullPointerException`; that does not make pc/stack an object memory area.
- If an object/reference "escapes" the method via return/store, the object can continue to exist after the method frame ends. Heap object lifetime is managed by GC based on reachability, not by whether a particular local frame still exists.

Do not oversimplify to "`new` always forces a physical heap allocation in every JIT build" or "every primitive must reside in thread stack memory". The JVM can optimize allocations via escape analysis/scalar replacement while preserving observable semantics.

### Table to avoid confusing three sizes

| Property | Belongs to | Unit/meaning |
| --- | --- | --- |
| `max_stack` | `Code_attribute` of **one method** | Maximum slots on the method frame's operand stack |
| `max_locals` | `Code_attribute` of **one method** | Number of local-variable slots needed for the frame |
| `-Xss` | JVM implementation configuration | Thread stack size/resource, not number of methods or opcodes |
| `-Xmx` | Heap configuration on many JVMs | Heap limit, does not directly determine a method's `max_stack` |

## 12. Current frame, stack traces, and observation tools

### What does a stack trace show?

`Throwable.getStackTrace()` and `Thread.getStackTrace()`/`StackWalker` allow applications to observe **call information**, typically class name, method name, file, and source line if debug metadata is present. They **do not** provide direct access to read all local variables/operand stack entries of a frame or a thread's raw pc register.

- A stack trace is a **logical snapshot**, not a contiguous sequence of instructions.
- `StackTraceElement.getLineNumber()` represents the source line if available, and can be negative when unknown/native; **it is not an absolute BCI**.
- `StackWalker.StackFrame.getByteCodeIndex()` can provide the BCI when available per the API contract, but it is **not an API to fetch a physical pc address of every thread**.
- JIT/inlining or hidden frames can alter how tools/options display them, though thread execution must still obey Java/JVMS semantics.

### Java 17: `StackWalker` observing the logical frame chain

Create **`StackWalkDemo.java`**:

```java
import java.util.stream.Collectors;

public class StackWalkDemo {
    static String snapshot() {
        return StackWalker.getInstance().walk(frames ->
            frames.filter(f -> f.getClassName().equals("StackWalkDemo"))
                  .map(StackWalker.StackFrame::getMethodName)
                  .limit(4)
                  .collect(Collectors.joining(" -> "))
        );
    }

    static String inner() {
        return snapshot();
    }

    static String outer() {
        return inner();
    }

    public static void main(String[] args) {
        System.out.println(outer());
    }
}
```

```bash
javac --release 17 StackWalkDemo.java
java StackWalkDemo
```

**Expected stdout when running the class above**:

```text
snapshot -> inner -> outer -> main
```

`StackWalker` traverses frames starting from the nearest method (`snapshot`) outward to callers; the filter selects frames of this exact class. `Collectors.joining(" -> ")` only formats a string; the real JVM stack is **not** stored as a Java `String`.

**Observation limitation:** Stack walking tools do not necessarily show all hidden frames or native frames in the same way; behavior observed through this API does not prove HotSpot stores one fixed physical frame per printed line. Do not use trace names/depths as a binary layout contract.

### Tools when the JVM hangs or the stack is deep

Commonly used JDK commands that support diagnostics:

```bash
jcmd <PID> Thread.print
jstack <PID>
javap -c -v -p FrameCallDemo
```

`<PID>` is a **placeholder** for the process ID of the Java process to inspect, not a literal command string to run verbatim. `jcmd`/`jstack` display threads and stack traces (along with states/locks depending on the tool), helping reveal whether a thread is waiting on a lock, sleeping, in a native call, or in which method it is executing. `javap` is a **class file** disassembler, not a real-time profiler.

To inspect specific bytecode instructions, `javap -c` shows **BCI offsets**; to cross-reference source lines/locals, use `javap -l` or `javap -v` when compiled with debug info.

### JIT and the pc register: do not mix three observation layers

| What can be seen | Tool | Valid conclusion |
| --- | --- | --- |
| Bytecode offset of a method | `javap -c` | Instruction position in `Code.code[]` of the class file |
| Active call frames | Stack trace, `StackWalker`, `jcmd Thread.print` | Logical call structure at the time of observation |
| Running native instruction address | Specialized native debugger/profiler | OS/CPU/JIT-level detail, **not identical** to JVM pc |
| Runtime stack memory size | JVM flags, native diagnostics | Thread memory resource, not `max_stack` depth |

## 13. When a native method participates in the call stack

In Java 17, many standard APIs may ultimately call native code (via JNI or JDK runtime mechanisms). For example, `Thread.sleep(...)` on some implementations uses internal native logic, but that **does not** allow inferring any bytecode opcodes in the native method body.

In the JVMS model:

1. While executing a **non-native** method, the JVM pc register holds the address of the currently executing JVM instruction.
2. While the current method is **native**, the JVM pc register is specified as **undefined**.
3. A native invocation may use a native method stack or other OS structures depending on the implementation.
4. After the native call returns to Java code, the thread resumes executing JVM instructions with normal frame/pc semantics.

Do not write tooling based on the assumption that "pc is always a BCI even when the thread is in JNI". When reading a stack dump, a line reporting `Native Method` usually describes a **tool-level location**, not a meaningful JVM BCI as in a normal bytecode method.

## 14. What is guaranteed by the JVMS, and what is implementation-dependent?

| Claim | Guarantee level | Reason |
| --- | --- | --- |
| Each JVM thread has its own pc register | **JVMS §2.5.1** | Per-thread control state |
| JVM pc is undefined when current method is native | **JVMS §2.5.1** | Native code is not JVM bytecode |
| Each JVM thread has its own stack | **JVMS §2.5.2** | Managing method frames |
| Each invocation semantically has its own frame | **JVMS §2.6** | Independent locals, operands, and return/exception state |
| `long/double` occupy two stack slots in the JVM model | **JVMS `2.6.2`** | How `max_stack` is counted |
| Normal return passes the return value to the caller | **JVMS `2.6.4`** | Method completion |
| Exceptions can unwind across multiple frames | **JVMS `2.6.5`** | Abrupt completion |
| JVM stack must be a contiguous memory block with fixed layout | **Not guaranteed** | JVMS permits multiple implementation strategies |
| pc register always matches the CPU instruction pointer | **Not guaranteed** | JIT/interpreter/CPU are different layers |
| One Java method always corresponds to one native frame with fixed layout | **Not guaranteed** | JIT/inlining/optimization can change representation |
| `-Xss1m` allows recursion of exactly N times | **Not guaranteed** | Platform, code shape, runtime/JIT |
| Stack traces must print all hidden/native frames identically | **Not guaranteed** | API/tool options and implementation details |

## 15. Common reasoning mistakes

**Mistake 1: "Each method has a pc register."** False: **each thread has one pc register** per the JVMS; the current method/frame changes across invocations.

**Mistake 2: "Each thread has a single operand stack."** False: a thread's JVM stack contains **multiple frames**, and **each frame has its own operand stack**.

**Mistake 3: "Anywhere the word stack appears, it means the JVM stack."** False: the JVM call stack, frame operand stack, and native stack have different roles.

**Mistake 4: "`max_stack = 8` means the thread stack has exactly 8 frames."** False: it is the **maximum depth of 8 slots in the operand stack of a single method frame**.

**Mistake 5: "Every object lives on the JVM stack."** False: frames can hold references to objects; objects themselves have heap semantics and the JVM can optimize physical placement.

**Mistake 6: "A reference is in a local, so that object is thread-private."** False: the same object on the heap can be referenced by multiple threads.

**Mistake 7: "In a native method, pc always points to the bytecode right after the native call."** False: the JVM pc register is **undefined** when the current method is native.

**Mistake 8: "Source line number is the bytecode PC."** False: line numbers map via metadata; BCI is the offset in `code[]`.

**Mistake 9: "An exception always pops all frames and terminates the thread."** False: the JVM searches for a handler in the current frame and then outer frames, and the program can continue.

**Mistake 10: "`StackOverflowError` means the heap is full."** False: it is a condition where the stack exceeds its limit; heap exhaustion is a different issue, though OOME can occur with stack allocation in some implementations.

**Mistake 11: "Increasing `-Xss` completely fixes infinite recursion."** False: it can only delay the failure, without changing the correctness of the algorithm.

**Mistake 12: "A thread context switch makes two threads share pc/registers/locals."** False: separate thread states are managed under thread semantics; the CPU switching which thread runs does not merge frame locals together.

**Mistake 13: "Every `ireturn` returns the callee's entire operand stack."** False: only the required return value is passed per completion rules; the callee frame terminates.

**Mistake 14: "`jstack` shows all local variable values of every frame."** False: stack traces primarily describe method/call positions and possibly locks/state; they are not an arbitrary snapshot of individual locals/operands.

## 16. Workflow for analyzing execution failures using pc and stack

When a Java thread hangs, loops deeply, or throws an exception:

1. **Identify the thread**: which thread is causing the issue, and is its current state `RUNNABLE`, `WAITING`, `BLOCKED`, or another state? Avoid assuming every `RUNNABLE` thread is using 100% CPU.
2. **Capture a stack trace**: `jcmd <PID> Thread.print`, `jstack`, or appropriate logging. Look for repeated methods (recursion), methods waiting on locks/I/O, and the caller/callee chain.
3. **Understand the current frame**: the top method in the trace is usually the closest observable location; the methods below it are still-active callers.
4. **If there is an exception**, determine which method threw the exception and whether the catch handler is in the current method or an outer caller.
5. **Inspect bytecode when suspecting compiler/agent instrumentation**: `javap -c -v -p Class`, checking BCI, `max_stack`/`max_locals`, exception table, and `StackMapTable`.
6. **If `StackOverflowError`**, look for recursion without a base case, a two-method call cycle (A→B→A), or an overly deep call chain; do not just increase stack size.
7. **If `OutOfMemoryError` when creating threads**, investigate the number of threads and native/stack resources; do not immediately conclude `-Xmx` needs to be increased.
8. **If native frames appear**, distinguish the undefined JVM pc in a current native method from native instruction addresses reported by tooling.
9. **If debugging races/concurrency**, remember each thread has its own stack, but references from locals can point to **shared heap objects**; check locks/`volatile`/happens-before.
10. **Distinguish contract from implementation**: what the JVM is required to do differs from how the JIT/OS physically stores frames and pc in practice.

## 17. Self-check quiz

**Q1.** A thread calls `A() → B() → C()`. Are there three pc registers?  
**A:** No. According to the JVMS, each thread has **one pc register**; three active methods create three **logical frames**.

**Q2.** `B` is calling `C`. Are `B`'s locals deleted as soon as `C` starts?  
**A:** No. Frame `B` pauses and retains the state needed to resume after `C`; `C` has its own locals/operand stack.

**Q3.** When `C`'s current method is native, must the JVM pc contain the BCI of caller `B`?  
**A:** No. The JVMS specifies that the JVM pc register is **undefined** when the current method is native.

**Q4.** What do `max_stack=4` and `max_locals=6` mean?  
**A:** One frame of the method requires **at most 4 operand-stack slots** and **6 local-variable slots** per the `Code` attribute; it does not give the number of frames for a thread.

**Q5.** How many slots do `long` and `double` contribute to the JVM operand stack?  
**A:** Each value occupies **two slots** in the JVM model, even though it is one logical value.

**Q6.** A method throws an exception, but the caller has a matching catch. Must the thread die?  
**A:** No. The JVM can unwind frames and then continue at the handler in the caller.

**Q7.** Two threads both call `calculate()`; do they share locals slot 0?  
**A:** No. Each invocation in each thread has its own frame and locals, though they may reference the same heap object.

**Q8.** Is `StackTraceElement.getLineNumber()` the physical pc register address?  
**A:** No. It is source line metadata (if available), not a CPU instruction pointer or raw JVM pc.

**Q9.** Why is `-Xss` not equal to `max_stack`?  
**A:** `-Xss` is a JVM implementation configuration for thread stack resources; `max_stack` is the operand-stack slot depth of **one frame**.

**Q10.** Should you believe that a `javap` output from JDK 17 is the only physical state machine HotSpot is allowed to use?  
**A:** No. `javap` describes **class file bytecode**; the JIT/interpreter may implement things differently while preserving JVM semantics.

## Java SE 17 Standard References

- [JVMS §2.5.1 — The pc Register](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.1): per-JVM-thread pc and native methods.
- [JVMS §2.5.2 — Java Virtual Machine Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.2): per-thread JVM stack, extensibility, and `StackOverflowError`/`OutOfMemoryError`.
- [JVMS §2.5.3 — Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): shared heap.
- [JVMS §2.6 — Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): local variables, operand stack, dynamic linking, normal/abrupt completion.
- [JVMS `2.6.1 — Local Variables](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.1) and [`2.6.2 — Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.2): slot indexes and category-2 values.
- [JVMS §4.7.3 — Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, `code_length`, exception table.
- [JVMS §6.5 — JVM Instruction Set](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): `iload`, `iadd`, `invokestatic`, `ireturn`, `athrow`, and other opcodes.
- [Java SE 17 `StackWalker` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html) and [`StackTraceElement` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): Java-level stack inspection.
- [Java SE 17 `Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): threads, stack traces, and lifecycle.
- [Java SE 17 `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html) and [`jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): disassembly and thread diagnostics.

**Takeaway:** **The pc register is per-thread** and represents the current JVM instruction position; **the JVM stack is also per-thread**, but contains multiple **method frames** with their own locals/operand stacks. Calls/returns/exceptions change the **current frame**; stack traces describe those frames, not a direct memory dump of a CPU PC register. Clearly distinguishing JVMS semantics from how HotSpot/JIT actually stores state helps avoid mistakes in memory, performance, and concurrency analysis.
