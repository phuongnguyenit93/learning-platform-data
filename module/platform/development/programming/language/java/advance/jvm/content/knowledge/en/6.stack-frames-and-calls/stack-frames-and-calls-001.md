# Every call creates a frame: local variables, operand stack, and dynamic linking

## 1. Understanding what a frame is and why each call needs its own frame

When Java code calls a method, the JVM needs to remember **the parameters and local variables of that call**, where to place intermediate values during computation, how to look up references to classes/fields/methods, and where to resume when the method finishes. According to the **Java Virtual Machine Specification (JVMS) `2.6`**, each method invocation creates a new **frame** according to the JVM model, and that frame exists until the invocation completes normally or completes abruptly due to an exception.

A frame contains three core components:

1. **Local variables array**: slots numbered from 0 to store `this` (for instance methods), parameters, and local/temporary values.
2. **Operand stack**: a LIFO stack for loading values, performing computations, preparing arguments, and receiving the results of method invocations.
3. **Reference to the run-time constant pool** of the class/interface defining the current method: supports **dynamic linking** from symbolic references in the class file to runtime entities.

The frame also participates in passing the **return value**, resuming the caller's execution point, and handling **exceptions**. The JVM may store additional implementation-specific information; **the three components above are the specification model**, which does not force HotSpot or another JVM to place each frame as a separate native memory block with a layout identical to textbook diagrams.

### Illustrating a call chain

~~~text
A Java thread, in chronological order:

main() starts
  Thread's JVM stack:
  ┌─────────────────────────────────────┐
  │ frame(main)    <-- current frame    │
  └─────────────────────────────────────┘

main() calls calculate(4)
  ┌─────────────────────────────────────┐
  │ frame(calculate) <-- current frame  │
  ├─────────────────────────────────────┤
  │ frame(main)                         │
  └─────────────────────────────────────┘

calculate(4) calls add(4, 4)
  ┌─────────────────────────────────────┐
  │ frame(add)   <-- current frame      │
  ├─────────────────────────────────────┤
  │ frame(calculate)                    │
  ├─────────────────────────────────────┤
  │ frame(main)                         │
  └─────────────────────────────────────┘

add() returns 8 -> frame(add) ends.
calculate() receives 8, adds 1, returns 9 -> frame(calculate) ends.
main() continues with the value 9.
~~~

**Each call is a different frame**, even when calling the same method again. Within a thread, only the frame of the **currently executing** method is the current frame according to the JVMS model; when another method is called, the caller's frame is suspended and the callee's frame becomes current.

**Do not confuse** the JVM stack (which holds a thread's frames) with the **operand stack** (which resides **inside each frame**). Also do not confuse it with the **heap**, where objects/arrays are typically allocated according to the JVM model. A local variable holding a `reference` can refer to an object on the heap; it is **not** a copy of the entire object.

## 2. The JVM stack and the lifecycle of a frame

According to **JVMS `2.5.2`**, each JVM thread has its **own JVM stack**, created when the thread is formed. Frames of one thread cannot be directly referenced or shared by another thread. Threads can share objects on the heap, but **the local variables and operand stack of each frame** belong to that thread's specific execution.

Abstract process when a Java method calls another Java method:

1. The caller computes the arguments on the operand stack of the **caller frame**.
2. The invoke instruction is executed; the JVM determines the method to call according to bytecode semantics and creates a **frame for the new call**.
3. The arguments (and the receiver `this` if it is an instance method) are placed into the **local variables of the callee frame**. The operand stack of the new frame is initially **empty**.
4. The callee executes the bytecodes, operating on the locals/operand stack of the **callee frame itself**.
5. If the callee `return`/`ireturn`/`areturn`… normally, the callee frame ends; the result, if any, is transferred to the caller's operand stack and the caller continues at the instruction after the invoke.
6. If an exception is not handled in the callee, the callee completes **abruptly**; the JVM searches for an appropriate handler via the exception dispatch mechanism and may continue unwinding previous frames.

A frame is freed upon **call completion**, not by the curly-brace scope of an `if`/`for` block. A loop within **one** method typically reuses **one frame**, whereas each recursive call creates an additional abstract frame.

### A sequential model, not an absolute physical layout

JVMS allows implementations to optimize how frames are allocated and managed. For example, the JIT can **inline** a method, avoiding creating a corresponding standalone native frame at machine-code execution time, as long as program semantics are preserved and proper observability is ensured. Stack traces, debugging, and deoptimization are affected by runtime mechanisms. When saying "each call creates a frame", we are describing the **abstract virtual machine contract**.

According to JVMS, the JVM stack can have a fixed size or be expandable. A call chain that is too deep can cause a `StackOverflowError`; if the implementation cannot allocate/expand the stack as needed, there are situations that cause an `OutOfMemoryError`. Mechanisms such as native stack, `-Xss`, frame layout, and JIT optimizations are details of a specific runtime, not local slots directly controlled by Java source code.

## 3. Local variables array: slot 0, parameters, and local variables

Each frame has a **local variables** array of length `max_locals` slots according to the method's code. Slots are numbered starting from **0**; bytecodes such as `iload_0`, `iload_1`, `istore_2`, `aload_0`… reference indices in the **current frame**.

### Static methods and instance methods

| Method type | First slot | Subsequent slots |
| --- | --- | --- |
| `static int sum(int a, int b)` | `slot 0 = a` | `slot 1 = b`; local variables start after parameters |
| `int sum(int a, int b)` (instance) | `slot 0 = this` | `slot 1 = a`, `slot 2 = b`; then local variables |
| Constructor `MyClass(int n)` | `slot 0 = this` | `slot 1 = n`; then locals/temporaries |

**`this` is not a mandatory separate variable at slot 0 of every method.** A static method has no receiver instance; its slot 0 usually holds the first parameter. A constructor is a type of instance initialization method, having the receiver at slot 0, but the object undergoing initialization must obey special verifier rules.

When a method has multiple parameters, the JVM passes them into consecutive slots according to **type width**, not according to the number of variable names:

- `int`, `float`, `reference` (and values in the one-slot group) use **1 slot**.
- `long` and `double` use **2 consecutive slots**. Bytecode accesses this value from the **lower index**; one must not `lload` from the second slot.
- A `long` value at local slot 1 occupies slots **1 and 2**; the next parameter starts at **slot 3**.
- The second slot of a `long`/`double` is not an independent Java variable of the same value; overwriting one slot can invalidate the contents of the two-slot value.

Diagram of two methods:

~~~java
static int add(int a, int b) {
    int sum = a + b;
    return sum;
}

long blend(long base, double factor, int delta) {
    long total = base + delta;
    return total + (long) factor;
}
~~~

These are **illustrative methods that must reside inside a class**, not a complete standalone runnable Java file.

~~~text
add(int a, int b) — static:
  slot 0: a             int
  slot 1: b             int
  slot 2: sum           int             (commonly used by the compiler)

blend(long base, double factor, int delta) — instance:
  slot 0: this          reference
  slot 1: base          long (slot 1 + slot 2)
  slot 2: second part of base
  slot 3: factor        double (slot 3 + slot 4)
  slot 4: second part of factor
  slot 5: delta         int
  slot 6: total         long (slot 6 + slot 7)
  slot 7: second part of total
~~~

**Not every slot necessarily carries the exact same Java variable name throughout the entire method.** The compiler can use slots for temporary values, reuse slots when live ranges differ, and optimize code. `max_locals` measures the **slot capacity required for the frame**, not the count of variables declared in source. The compiler may choose a different layout in complex cases.

### LocalVariableTable vs. runtime local variables

The locals array is a runtime component according to JVMS. `LocalVariableTable` is an **optional debug attribute** in the class file, helping map slots to variable names and BCI ranges. If compiled with `javac -g:none`, local names may not appear in `javap -l`, but the JVM still has locals and still executes `iload`/`istore` normally.

Do not confuse:

- **`max_locals`**: mandatory locals capacity information when a method has `Code`.
- **`LocalVariableTable`**: optional debug metadata.
- **StackMapTable**: metadata of **verification type frames**, not a table containing all runtime frames currently calling each other.

## 4. Operand stack: where bytecode processes intermediate values

The operand stack of **each frame** is a LIFO (**last in, first out**) stack. When a new frame is created, the operand stack starts **empty**. Subsequent bytecodes:

- Push constants: `iconst_1`, `bipush 10`, `ldc`…
- Load locals: `iload_n`, `aload_n`, `lload_n`…
- Read fields: `getstatic`, `getfield`…
- Pop operands from the top of the stack, compute, and push the result: `iadd`, `imul`, `dadd`…
- Store results into locals: `istore_n`, `astore_n`…
- Prepare receiver/arguments for invoke; receive the return value if the callee returns a value.
- Use a value to branch (`ifeq`, `if_icmpgt`…), store a field, return (`ireturn`), or throw an exception (`athrow`).

### Tracing addition

For `add(int a, int b)`, a compiler like `javac` may generate an equivalent bytecode sequence:

~~~text
0: iload_0
1: iload_1
2: iadd
3: istore_2
4: iload_2
5: ireturn
~~~

This is a **valid illustrative disassembly**. Bytecode offsets/variants may differ by compiler, but instruction semantics are fixed. If `a=4`, `b=4`:

| Opcode | Relevant locals | Operand stack after instruction (left: bottom; right: top) |
| --- | --- | --- |
| Enter method | `slot0=4, slot1=4` | `[]` |
| `iload_0` | Read `a` | `[4]` |
| `iload_1` | Read `b` | `[4, 4]` |
| `iadd` | Locals unchanged | `[8]` |
| `istore_2` | Write `sum=8` | `[]` |
| `iload_2` | Read `sum` | `[8]` |
| `ireturn` | Return 8, frame ends | Value 8 is transferred to the **caller's operand stack** |

When `iadd` runs, it **pops two `int` values** and then pushes one `int` value. One should not imagine the operand stack as an application-created `java.util.Stack`; it is a virtual machine mechanism serving bytecode execution.

### Stack depth does not equal element count

`max_stack` measures maximum depth in **slot units**. `long` and `double` each contribute **two units** of depth; category 1 types contribute one.

For example, when bytecode is holding on the stack:

~~~text
[reference, long, int]

Number of logical values: 3
Depth in slots: 1 + 2 + 1 = 4
~~~

Therefore `max_stack=4` does not mean the method calls four other methods or that the JVM has four frames. It is the maximum depth of the **operand stack inside one frame** according to the `Code` information.

### Type rules and stack manipulation

Bytecode instructions have type constraints:

- `iadd` requires two compatible `int` values.
- `ladd` requires two compatible `long` values.
- `swap` only swaps appropriate **category 1** values; it must not split a `long`/`double` value in half.
- `dup`/`dup2` have usage forms depending on the category of the values on top.
- `checkcast`, `aastore`, method invocations, and other instructions have their own constraints.

The verifier checks the structure and validity of type flow according to JVMS. One cannot arbitrarily take a `long` from two `int`s just because the total size occupies two slots.

## 5. Dynamic linking: how does a frame use the run-time constant pool?

The third concept, often less obvious than locals and the operand stack, is **dynamic linking**. According to **JVMS `2.6.3`**, each frame holds a reference to the **run-time constant pool of the class/interface containing the current method**. Code in a class file can contain **symbolic references** to other classes, fields, and methods.

Java example:

~~~java
static int twice(int value) {
    return add(value, value);
}
~~~

A disassembly might show:

~~~text
0: iload_0
1: iload_0
2: invokestatic #NN  // Method add:(II)I
5: ireturn
~~~

`#NN` is a constant pool index **of the class containing `twice`**; it is not a machine address, source line number, or locals slot. The constant-pool entry leads to the **owner name, method name, and descriptor**. When needed, the VM uses the resolution mechanism to convert this symbolic reference into concrete runtime information.

~~~text
twice() bytecode:
   invokestatic #NN
          |
          v
run-time constant pool (of the class defining twice)
   #NN -> Methodref Example.add:(II)I
          |
          | method resolution (when needed)
          v
resolved runtime method / linking info
          |
          v
invoke add(...) -> create frame(add)
~~~

This is a conceptual model. **Resolution can be performed eagerly or lazily** according to JVMS rules, and the VM can cache the result; there is no requirement that every time `invokestatic` runs it must look up the symbol name from scratch. Furthermore:

- **Resolution** answers which runtime entity a symbolic reference corresponds to; it may need to load/link the involved class and perform access checks.
- **Dynamic dispatch** answers which implementation is selected when calling an overridable method, such as `invokevirtual`/`invokeinterface`. It is related to, but **not identical** to, resolving a symbolic reference.
- **`invokedynamic`** is an opcode with its own call site/bootstrap mechanism; it is **not** another name for "dynamic linking present in every frame".

Therefore, the statement "a frame contains **a reference to the run-time constant pool** to support dynamic linking" is more accurate than "each frame contains a copy of the entire constant pool" or "every call must look up the method table from scratch".

### Distinguishing the run-time constant pool from the operand stack

| Mechanism | What does it contain? | When is it used? |
| --- | --- | --- |
| **Constant pool / run-time constant pool** | Symbolic information, constants, implementation-appropriate resolved references | Linking to fields/methods/classes and loading constants |
| **Local variables** | `this`, parameters, local/temporary values of the call | `iload`, `istore`, `aload`, `lstore`… |
| **Operand stack** | Intermediate values and arguments awaiting operations | Arithmetic, branch, invoke, return |
| **JVM stack** | Sequence of **frames** of the thread | Managing active calls |

Placing these concepts in their proper places is very important when reading `javap -c -v` output and when explaining a linking/verification error.

## 6. Runnable Java 17+ program: observing nested calls

Create file **`FrameTrace.java`**:

~~~java
public class FrameTrace {
    static int add(int left, int right) {
        int sum = left + right;
        return sum;
    }

    static int calculate(int value) {
        int doubled = add(value, value);
        return doubled + 1;
    }

    public static void main(String[] args) {
        int answer = calculate(4);
        System.out.println("result=" + answer);
    }
}
~~~

Using Java 17+:

~~~bash
javac -g FrameTrace.java
java FrameTrace
~~~

**Exact stdout:**

~~~text
result=9
~~~

We have `add(4, 4) = 8`, then `calculate(4) = 8 + 1 = 9`.

### Tracing each frame

**Point A — entering `main`:**

~~~text
frame(main)
  locals: slot0 = args (String[])
  operand stack: []
  link: run-time constant pool of FrameTrace
~~~

**Point B — `main` calls `calculate(4)`:**

~~~text
current frame = frame(calculate)
  locals: slot0 = value = 4
  operand stack: []
  link: run-time constant pool of FrameTrace

suspended caller frame(main)
  locals: slot0 = args
  program execution will continue after invokestatic calculate
~~~

**Point C — `calculate` prepares `add(value, value)`:**

~~~text
frame(calculate) before invoke:
  iload_0  -> operand stack = [4]
  iload_0  -> operand stack = [4, 4]
  invokestatic add:(II)I

new frame(add):
  locals: slot0 = left = 4
          slot1 = right = 4
  operand stack: []       <-- newly created, does not carry over the caller's stack
  link: run-time constant pool of FrameTrace
~~~

**Point D — `add` returns 8:**

~~~text
frame(add):
  compute sum = 8
  ireturn 8
  -> frame(add) ends

frame(calculate) resumes:
  operand stack after invoke = [8]
  istore_1  -> local slot1 = doubled = 8; stack = []
  iload_1, iconst_1, iadd -> [9]
  ireturn 9
  -> frame(calculate) ends
~~~

**Point E — `main` resumes:**

~~~text
frame(main) after calculate(4):
  operand stack = [9]
  istore_1 -> slot1 = answer = 9
  ...
  System.out.println("result=" + answer)
~~~

The last line prints `result=9`. The same **run-time constant pool** of class `FrameTrace` can be **referenced** by different frames, but **the locals and operand stack of each frame are separate**. There is no way `add` could accidentally write directly into `main`'s local `answer` just because both reside on the JVM stack.

### Reading actual bytecode to verify

~~~bash
javap -c -p FrameTrace
javap -v -p FrameTrace
javap -l -p FrameTrace
~~~

Look for:

- `add`: `iload_0`, `iload_1`, `iadd`, `istore_2`, `iload_2`, `ireturn` (per common `javac`).
- `calculate`: two loads of `value`, `invokestatic` to `add:(II)I`, store `doubled`, add 1, `ireturn`.
- `main`: `iconst_4` or equivalent constant load, `invokestatic` to `calculate:(I)I`, store `answer` and code to print `System.out`.
- In `-v` output, each `Code` has `stack=...`, `locals=...` (corresponding to `max_stack` and `max_locals`), along with constant-pool entries for the referenced calls.
- `javac -g` provides debug line/local information usually displayed via `LineNumberTable` and `LocalVariableTable`.

**Do not assume `#N` indices or BCI offsets are identical across all JDKs.** Read the bytecode generated by the exact compiler you just ran, then match `invokestatic #N` with entry `#N` in the constant pool of the **same class file**.

## 7. `long` and `double`: why do local slot indices skip numbers?

The example above uses `int`, so each parameter occupies only one slot. To see **category 2** types, create file **`WideSlots.java`**:

~~~java
public class WideSlots {
    static long mix(long base, double adjustment, int extra) {
        long total = base + extra;
        return total + (long) adjustment;
    }

    public static void main(String[] args) {
        System.out.println("mixed=" + mix(10L, 2.9, 3));
    }
}
~~~

~~~bash
javac -g WideSlots.java
java WideSlots
javap -c -v -p WideSlots
~~~

**Exact stdout:**

~~~text
mixed=15
~~~

Calculation: `10L + 3 = 13L`, `(long) 2.9 = 2L` because Java casting truncates the fractional part toward 0; the final sum is `15L`.

For **static `mix(long,double,int)`**, the initial slots:

| Slot | Content | Notes |
| --- | --- | --- |
| 0–1 | `base: long` | Two slots, accessed by index 0 |
| 2–3 | `adjustment: double` | Two slots, accessed by index 2 |
| 4 | `extra: int` | One slot |
| 5–6 | `total: long` | Two slots, used when the variable is stored |

`max_locals` of this method according to typical bytecode compilers is at least **7**; every compiler strategy must be sufficient to accommodate the used slots. Recognizable opcodes include `lload_0`, `dload_2`, `iload` with index 4, `i2l`, `d2l`, `ladd`, `lstore`, and `lreturn` (order depends on compiler). `lreturn` returns one **`long` value** to the caller; it does not turn two physical slots into two independent return values.

Slot width is only a **JVM storage model**, not a promise of 64-bit address alignment. JVMS does not require `long`/`double` to start at an even slot.

## 8. Recursion: each call to the same method still has its own frame

Recursion makes it clearer why the JVM cannot use a single set of locals for all invocations.

Create file **`RecursiveFrames.java`**:

~~~java
public class RecursiveFrames {
    static int factorial(int n) {
        if (n <= 1) {
            return 1;
        }
        return n * factorial(n - 1);
    }

    public static void main(String[] args) {
        System.out.println("factorial(4)=" + factorial(4));
    }
}
~~~

~~~bash
javac RecursiveFrames.java
java RecursiveFrames
~~~

**Exact stdout:**

~~~text
factorial(4)=24
~~~

According to the JVM model:

~~~text
main()
  factorial(4): local n = 4, waiting for result of factorial(3)
    factorial(3): local n = 3, waiting for result of factorial(2)
      factorial(2): local n = 2, waiting for result of factorial(1)
        factorial(1): local n = 1 -> ireturn 1
      factorial(2): 2 * 1 -> ireturn 2
    factorial(3): 3 * 2 -> ireturn 6
  factorial(4): 4 * 6 -> ireturn 24
main(): prints 24
~~~

Each `factorial` frame has **its own call's `n` value**. As calls go deeper, earlier frames hold their waiting state until receiving the return value, then continue. If there were only a single global variable `n` for all calls, the calculation above could not work properly.

**Unbounded recursion can overflow the stack.** For example, `factorial(-1)` in this program returns 1 immediately due to the condition `n <= 1`; therefore it is **not** a stack overflow example. A method calling itself forever without a stopping condition will exhaust call nesting capacity and may throw `StackOverflowError`. Do not intentionally trigger stack overflow in a production environment to measure limits because actual limits depend on runtime and configuration.

### Tail calls, inlining, and physical frames

Do not infer that "if there are n source calls, the machine always allocates n identical native stack blocks". HotSpot/JIT can inline some calls. Java/JVMS provides no general guarantee that every tail-recursive method is converted into a loop and will not overflow the stack. Use iterative algorithms or appropriate data structures when depth control is needed.

## 9. Normal call completion: returning the result to the caller

According to **JVMS `2.6.4`**, a method completes normally when bytecode executes the appropriate return instruction:

| Opcode | Result type |
| --- | --- |
| `return` | `void`, does not push a result value onto the caller's operand stack |
| `ireturn` | `int` (includes result representation for `boolean`, `byte`, `char`, `short` at the JVM level) |
| `lreturn` | `long` |
| `freturn` | `float` |
| `dreturn` | `double` |
| `areturn` | `reference` |

When the callee completes normally:

1. The result (if any) is **pushed onto the caller's operand stack**.
2. The callee frame is removed from the JVM stack unless the implementation uses another optimized representation while preserving semantics.
3. The caller becomes the current frame again, continuing after the invoke instruction with the **caller's** locals/operand stack state.

Example `int x = add(2, 3);`:

~~~text
caller before invokestatic:
  operand stack = [2, 3]

callee add upon entry:
  locals = [2, 3]
  operand stack = []

callee ireturn 5

caller after invoke:
  operand stack = [5]

caller istore_<n>:
  local x = 5
  operand stack = []
~~~

However, when a call completes due to an **uncaught exception**, **no normal method result** is pushed back to the caller. Abrupt completion is handled separately.

## 10. Exceptions: finding a handler and unwinding frames

According to **JVMS `2.6.5`**, if an instruction throws an exception that the current method does not handle, the invocation completes **abruptly**. The JVM does not run a "hypothetical `ireturn` branch" and pass an arbitrary result to the caller. The exception can propagate across multiple frames until a matching handler is found; if uncaught, it affects the thread and the uncaught exception handling mechanism.

Create file **`ExceptionalFrames.java`**:

~~~java
public class ExceptionalFrames {
    static void bottom() {
        throw new IllegalStateException("boom");
    }

    static void middle() {
        bottom();
    }

    static void top() {
        try {
            middle();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        top();
        System.out.println("continued");
    }
}
~~~

~~~bash
javac -g ExceptionalFrames.java
java ExceptionalFrames
~~~

**Exact stdout:**

~~~text
caught=boom
continued
~~~

Frame flow:

~~~text
main()
  top()
    middle()
      bottom()
        athrow IllegalStateException("boom")
      bottom frame completes abruptly
    middle has no handler -> middle frame completes abruptly
  top has IllegalStateException handler -> executes catch
  top completes normally
main() continues and prints "continued"
~~~

Points to understand:

- `bottom()` does not return a value to `middle()`; `middle()` also does not complete along the normal path.
- The **exception table** in `top`'s `Code` defines the protected code region and handler; it is not merely a static table of "exception names" for the entire JVM.
- When the VM transfers control to a handler, the operand stack has a state according to exception handler rules (containing the exception object for bytecode to process), rather than preserving random intermediate values from before the exception was thrown.
- `finally`, if present, still follows Java's own semantics; do not confuse exception-unwinding with "skipping all finally blocks".

You can inspect:

~~~bash
javap -c -v -p ExceptionalFrames
~~~

In `top`, look for `Exception table`, `astore` to store the exception into a local, and the `getMessage`/`println` calls. Bytecode shape and constant pool indices vary by compiler, but the processing order in the example is deterministic.

## 11. Where do `max_stack` and `max_locals` live in the class file?

According to **JVMS `4.7.3`**, every method with a bytecode body (not `abstract` or `native`) has a `Code` attribute:

~~~text
Code_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 max_stack;
    u2 max_locals;
    u4 code_length;
    u1 code[code_length];
    u2 exception_table_length;
    ...
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

Two important fields:

- **`max_stack`**: maximum depth of the **operand stack** in slots at **any point** during method execution.
- **`max_locals`**: number of slots in the **local variables array**, including the receiver, parameters, and locals/temporaries.

**These numbers are determined by the method's code**, not by measuring the exact number of active frames while the JVM is running. For instance, `stack=2, locals=3` in `javap -v` output are two sizes **inside one frame** for the method being viewed.

The value of `max_stack` can differ from the number of instructions in the method and from the number of parameters. A method hundreds of instructions long that only needs stack depth 2 is still valid; a call with many arguments may need a larger depth.

The JVM's bytecode verifier uses type constraints and class file data to ensure stack/locals manipulation is valid. `StackMapTable` assists verification at control flow points, but is not a runtime snapshot of all running calls.

### `Code` for abstract/native methods?

An `abstract` method has no `Code` body for the JVM to execute. A `native` method has its body in a native language/component through an implementation mechanism, not described by a Java bytecode `Code` attribute. Therefore, the explanation "each call creates a frame with `Code.max_stack/max_locals`" applies directly to **Java bytecode methods that have Code**, while native method invocation additionally involves native method stacks/ABI and runtime details. This does not diminish the meaning of the method invocation model in JVMS.

## 12. Comparing frame, heap, static state, and method area

| Component | Scope | Typical data | Example in article |
| --- | --- | --- | --- |
| **JVM stack** | Per thread | Frames of active calls | `main → calculate → add` |
| **Frame local variables** | Per call | `this`, parameters, local values and references | `left=4, right=4, sum=8` |
| **Frame operand stack** | Per call | Computed values, arguments, pending results | `[4,4] → [8]` |
| **Heap** | Shared in JVM per model | Object and array instances | `new IllegalStateException(...)` |
| **Run-time constant pool** | Associated with class/interface, in the corresponding runtime data area | Symbolic references, constants, link info | `Methodref FrameTrace.add:(II)I` |
| **Static fields** | Associated with class by runtime identity | Class state, dependent on class loader | `static int counter` if declared by program |
| **PC register** | Per thread | Current instruction position when running a Java method | BCI currently executing in `add` |

Object/reference diagram:

~~~text
frame(main).local[1] = reference ──────────┐
                                           v
                                        Heap object
                                           ^
frame(otherMethod).local[0] = reference ────┘
~~~

Two frames can point to the **same object**, so modifying the object via a reference from one thread can affect another thread if thread-safety is not coordinated properly. However, two frames do not automatically share a **locals array** or **operand stack** just because they reference the same object.

When a frame's lifecycle ends, the local references of that frame are no longer live references from that frame. This **does not prove** the associated object is collected by GC immediately: the object may still be referenced elsewhere, GC runs according to runtime policy, and JIT/liveness can affect when an object is actually considered reachable. Do not infer "frame pop = heap object freed immediately".

## 13. Reading a StackTrace without equating it with the operand stack

A Java stack trace typically shows the **method call chain**:

~~~text
java.lang.IllegalStateException: boom
    at ExceptionalFrames.bottom(ExceptionalFrames.java:3)
    at ExceptionalFrames.middle(ExceptionalFrames.java:7)
    at ExceptionalFrames.top(ExceptionalFrames.java:12)
    at ExceptionalFrames.main(ExceptionalFrames.java:19)
~~~

This is an **illustrative call chain diagram**, **line numbers are not guaranteed** if you add/remove lines in the file. The `ExceptionalFrames` program in section 10 catches the exception and **does not print the stack trace itself**; to see the stack trace, you can call `ex.printStackTrace()` in the catch block, in which case the output has more information and usually goes to stderr.

A stack trace displays the **observable frames of the call**, not the entire operand stack or the value of each local slot. A line like `at ...middle(...java:7)` helps locate the call, but does not mean "the operand stack at line 7 contains 7 elements".

Tools such as debuggers, JFR, or `jcmd Thread.print` can assist in analyzing thread/call stacks on a specific runtime. They do not replace the specification regarding locals, operand stack, and constant-pool linking. To see bytecode and slot levels, `javap -c -v -l -p` is a clearer choice.

## 14. Common mistakes and how to correct the understanding

| Misconception | Correct explanation |
| --- | --- |
| "Each Java method only has one frame for the entire application." | **Each invocation** of a method creates an abstract frame; recursion has multiple frames of the same method. |
| "A loop running 100 times means 100 frames." | No, a loop within the same call usually continues within **one frame**. |
| "JVM stack and operand stack are the same." | The JVM stack holds **frames**; each frame contains its own **operand stack**. |
| "Slot 0 is always `this`." | Only for instance methods; static methods use slot 0 for the first parameter if any. |
| "One parameter = one local slot." | `long`/`double` occupy **two** consecutive slots. |
| "`max_stack` is the number of nested method calls." | It is the **operand stack** depth of one method, not the number of frames. |
| "The callee uses the caller's operand stack." | The callee starts with its **own, empty** operand stack; arguments are passed into the callee's locals. |
| "`ireturn` keeps the callee frame so the caller can read locals inside." | It returns a **value** to the caller's stack; the callee frame completes. |
| "Exceptions also return a value via `ireturn`." | An unhandled exception in the callee causes **abrupt completion**, not normal return. |
| "Dynamic linking means every call scans the entire constant pool." | Resolution can be lazy/cached; the frame holds a **reference** to the run-time constant pool. |
| "Dynamic linking = dynamic dispatch = `invokedynamic`." | These are related concepts with **different functions**. |
| "If LocalVariableTable is missing, the JVM has no locals." | Runtime locals still exist; the debug table only holds names/scopes if written by the compiler. |
| "When a frame disappears, all objects from the frame are deleted from the heap." | Objects may still be reachable via other references; GC does not mean frame pop. |
| "The JIT must always allocate a physical native stack frame for each call." | JVMS describes **abstract frames**; implementations can optimize and inline. |

## 15. Self-check exercises

**Question 1.** In `static int add(int x, int y)`, which slots are the parameters in?  
**Answer:** Normally `x` is at slot 0 and `y` is at slot 1; there is no `this` receiver.

**Question 2.** In `long instanceMethod(int a, long b, double c)`, what are the starting local slots of `b` and `c`?  
**Answer:** `slot0=this`, `slot1=a`; `b` starts at slot 2 and occupies slots 2–3; `c` starts at slot 4 and occupies slots 4–5.

**Question 3.** If `main` calls `calculate` and `calculate` calls `add`, what is the current frame when computing `iadd` inside `add`?  
**Answer:** `frame(add)`. The frames of `calculate` and `main` are suspended waiting for the callee.

**Question 4.** After `add(4,4)` ends with `ireturn`, where does the value 8 appear?  
**Answer:** On the **operand stack of the caller frame `calculate`**, and then the caller can store it into local `doubled`.

**Question 5.** Why does `max_stack=4` not mean the method has four frames?  
**Answer:** `max_stack` is the maximum depth **in slots of the operand stack of a single frame**.

**Question 6.** What does `invokestatic #N` reference, and must it look up the symbol again on every call?  
**Answer:** `#N` is a constant-pool index leading to a symbolic method reference; the VM can resolve/cache according to rules, without needing to look it up again every time.

**Question 7.** Do two recursive calls `factorial(4)` and `factorial(3)` share local `n`?  
**Answer:** No. Each invocation has its own frame/locals with `n=4` or `n=3`.

**Question 8.** If `bottom` throws an exception with no handler, does the caller `middle` receive any "method result"?  
**Answer:** No. The call to `bottom` completes abruptly, and the exception continues searching for a handler instead of returning a value via `return`.

**Question 9.** Why does lacking `LocalVariableTable` not make a class file unrunnable?  
**Answer:** Because it is optional debug metadata; `Code.max_locals` along with the bytecode still fully specify the slots needed for execution.

**Question 10.** State the boundary between a method frame and an object on the heap.  
**Answer:** A frame stores the locals/operand stack of **an invocation**; a reference in the frame can point to an object on the heap. The end of a frame does not mean the object is immediately reclaimed.

## 16. Official documentation and how to study further

- [JVMS Java SE 25 — `2.5.2` Java Virtual Machine Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.2): per-thread JVM stack, containing frames.
- [JVMS Java SE 25 — `2.6` Frames](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6): each invoke creates a frame, current frame, lifecycle, and return.
- [JVMS Java SE 25 — `2.6.1` Local Variables](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.1): slots, receiver, parameters, `long`/`double`.
- [JVMS Java SE 25 — `2.6.2` Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.2): LIFO, value types, max depth, and category.
- [JVMS Java SE 25 — `2.6.3` Dynamic Linking](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.3): linking symbolic references via the run-time constant pool.
- [JVMS Java SE 25 — `2.6.4 and `2.6.5](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.4): normal completion, abrupt completion, and passing results/exceptions.
- [JVMS Java SE 25 — `4.7.3` Code Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, bytecode, and exception table.
- [JVMS Java SE 25 — `5` Linking, Loading, and Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): resolution and invocation related to symbolic references.
- [JDK 25 `javap` manual](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): how to use `-c`, `-v`, `-l` to cross-reference locals, operand stack, and Code metadata.

**How to remember:** A **thread** has a **JVM stack**; an **invoke** has a **frame**; a frame has **local variables**, an **operand stack**, and a reference to the **run-time constant pool**; when the callee finishes, the caller continues with the return value or along the exception path. From this model, you can read `javap` without confusing local slots, operand-stack depth, constant-pool indices, and the method call chain.