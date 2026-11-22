# Stack-based machine: opcode, operands, and program counter

## 1. From a line of Java to execution steps in the JVM

When reading Java, we often see an expression like:

```java
int result = (a + b) * 2;
```

In a normally compiled program, the JVM executes a sequence of **bytecode instructions** describing small steps: taking values from variables, pushing them onto the **operand stack**, adding two numbers, pushing the constant 2, multiplying, and then storing the result back into a variable. The JVM is therefore called a **stack-based virtual machine**.

An example of bytecode modeling the expression above:

```text
iload_0      ; push the value of local variable a onto the operand stack
iload_1      ; push the value of local variable b onto the operand stack
iadd         ; pop the two ints on top of the stack, add them, push the result
iconst_2     ; push the int constant 2
imul         ; pop the two ints on top of the stack, multiply them, push the result
istore_2     ; pop the result off the stack, write it to local variable result
```

Three concepts throughout the lesson:

- **Opcode** (*operation code*) tells the JVM what operation to perform: `iadd`, `iload_0`, `goto`, `invokevirtual`…
- **Operand** is the data that the operation uses: it can be values already on the **operand stack**, or bytes **accompanying the opcode** such as a local variable index, a constant number, a constant pool index, or a branch offset.
- **Program counter (PC)** helps the execution thread determine the **current bytecode instruction**. Branching changes the next execution location; a method call creates a new frame for the called method.

This is a virtual machine model at the **bytecode** level, which does not mean the computer's real CPU must run using a stack. A JVM such as HotSpot can interpret bytecode or JIT-compile it into machine code that uses CPU registers. The semantics that must be preserved are the semantics defined by the JVM specification.

## 2. Components to distinguish: frame, locals, operand stack, and PC

A JVM thread has its own **JVM stack**; each method call creates a new **frame**. A frame contains information related to a single invocation, including a **local variable array** and an **operand stack**. According to the JVMS, each thread also has its own **PC register**.

```text
Running thread
├── PC register: address of the JVM instruction currently being executed
└── JVM stack (stack of method calls)
    ├── Frame of the current method (on top)
    │   ├── Local variables: slot 0, 1, 2, ...
    │   ├── Operand stack: [..., top element]
    │   └── Reference to the class's runtime constant pool
    ├── Frame of the caller method
    └── Older frames
```

### 2.1. JVM stack differs from operand stack

Two concepts share the word "stack" but have different responsibilities:

| Component | What does it contain? | When does it change? |
| --- | --- | --- |
| **JVM stack** of a thread | The **frames** of active method calls | Method call → create/push frame; return → corresponding frame terminates |
| **Operand stack** inside a frame | Intermediate values that instructions are operating on | `iload` pushes value, `iadd` pops operands, `istore` pops result |
| **Local variables** inside a frame | Slots containing the method's parameters and local values | `iload` reads, `istore` writes, `iinc` updates slot |
| **PC register** of a thread | Position of the JVM instruction currently being executed in the current context | Advances to next instruction, branches, executes calls… |

Do not equate the **operand stack** with the `java.util.Stack` data structure or with the **call stack** shown in a stack trace. `java.util.Stack` is a library class; the two execution structures are parts of the JVM model.

### 2.2. Local variables are indexed slots

The method `static int sum(int a, int b)` typically places `a` in local slot 0 and `b` in slot 1. An instance method typically has `this` in slot 0; parameters start from the following slots. `long` and `double` values occupy **two local variable slots**, while most other types occupy one slot.

Conceptual example:

```text
static int sum(int a, int b)
locals:
  [0] a = 3
  [1] b = 4
  [2] result (written later)

int Person.compute(int n)
locals:
  [0] this   (reference)
  [1] n      (int)
```

A slot index is not a source variable name. The compiler can reuse slots across different scopes. When `javap -c` displays `iload_0`, the number `0` is the **local index**, not the value of the variable.

### 2.3. Operand stack is a temporary working area

Instructions pop/push values according to the **LIFO (last in, first out)** rule. Use the following notation to simulate:

```text
[]            = empty stack
[3]           = value 3 on top
[3, 4]        = 4 on top, 3 directly below
[7]           = result after iadd pops 3 and 4
```

Each method has `max_stack` in the `Code` attribute to bound the required operand stack depth; `max_locals` bounds the number of local slots. These are **per-method limits**, not the amounts always present at every point in time.

An `int` or a reference typically occupies one stack unit; `long` and `double` belong to **category 2** and occupy two units. Instructions such as `dup`, `pop`, and `swap` have strict rules regarding categories, so two-unit values cannot be arbitrarily rearranged like one-unit values.

## 3. How is a JVM instruction encoded?

Instruction layout:

```text
+-----------+-------------------------------+
| opcode    | operand bytes if needed       |
| 1 byte    | 0, 1, 2 or more bytes         |
+-----------+-------------------------------+
```

The opcode is encoded as **one byte** and indicates the kind of operation. Many instructions have **operand bytes** immediately following the opcode; instruction length is not fixed. These bytes can represent an immediate number, a local index, a constant pool index, or a branch offset.

Examples:

| Mnemonic | Meaning | Operands encoded after opcode? |
| --- | --- | --- |
| `iconst_2` | Push int constant 2 | No |
| `iload_0` | Read local slot 0 of type int and push onto stack | No: index 0 is in the opcode name |
| `iload 5` | Read local slot 5 of type int | Yes: local index |
| `bipush 100` | Push integer 100 from a signed byte immediate | Yes: one byte |
| `sipush 1000` | Push a signed short immediate | Yes: two bytes |
| `ldc #k` | Load an appropriate constant from the runtime constant pool | Yes: index into the constant pool |
| `iinc 2, 1` | Increment int local slot 2 by 1 | Yes: local index and signed increment |
| `if_icmpge target` | Compare two ints and branch if the condition holds | Yes: relative branch (signed offset) |
| `invokestatic #k` | Invoke a static method via symbolic reference | Yes: index into the constant pool |

**Two meanings of "operand" must be clearly separated:**

1. **Runtime operands of the operation:** for example, `iadd` takes **two int values already on the operand stack**. The bytecode of `iadd` does not directly contain those two numbers.
2. **Operands encoded in the instruction:** for example, `bipush 100` has a byte containing 100, `iload 5` contains a local index, and `goto` contains a branch displacement.

Therefore, the statement "`iadd` has no operands" is only true when talking about **operand bytes after the opcode**. In terms of **computational semantics**, `iadd` still requires two operands on the stack.

### 3.1. Mnemonic is not raw bytecode

`iload_0`, `iadd`, and `invokevirtual` are **human-readable names** for opcodes in a disassembly. The `javap` tool turns opcode bytes into mnemonics and prints additional operands as numbers, class/method names, or comments resolved from the constant pool.

With `javap -c`:

```text
  0: iload_0
  1: iload_1
  2: iadd
```

The numbers **0, 1, 2** at the start of each line are **bytecode offsets**, not opcodes and not Java line numbers. The fact that the offset goes 0 → 1 → 2 in this example is because all three instructions are one byte long.

### 3.2. Different ways to load constants

- `iconst_m1`, `iconst_0` … `iconst_5`: load very small int constants, requiring no operand bytes.
- `bipush`, `sipush`: signed 8-bit / 16-bit immediates, with the result pushed as `int`.
- `ldc`: loads a supported constant from the constant pool, such as a string or number.
- `ldc_w`: larger constant pool index form than `ldc`.
- `ldc2_w`: used with category-2 constants such as `long` and `double` according to instruction rules.

The compiler chooses the appropriate form; one should not infer that a statement like `int n = 100;` must always emit `bipush` across every compiler or every optimization.

### 3.3. Not every instruction has a fixed length

Instructions such as `tableswitch` and `lookupswitch` have **padding** to align jump data and carry multiple pairs/offsets. `wide` modifies how operands of certain local-variable-related instructions or `iinc` are decoded to support larger indices/counters. `goto_w` has a wider branch offset than `goto`.

Consequence: **the PC does not increment by a fixed number after every opcode**. If an instruction is 3 bytes long and execution proceeds sequentially, the next offset is typically 3 bytes away; if there is a branch, the PC points to a completely different location.

## 4. Core opcode groups of a stack-based machine

| Group | Representative opcodes | What changes |
| --- | --- | --- |
| Constant loading | `iconst_0`, `bipush`, `ldc`, `aconst_null` | Pushes a value onto the operand stack |
| Local loading | `iload`, `aload`, `lload`, `iload_0` | Reads a local slot → pushes onto stack |
| Local storing | `istore`, `astore`, `lstore`, `istore_1` | Pops a value from stack → writes to local slot |
| Arithmetic | `iadd`, `isub`, `imul`, `idiv`, `ladd` | Pops operands, computes, pushes result |
| Type conversion | `i2l`, `l2i`, `d2i` | Pops value, converts per JVM rules, pushes result |
| Stack management | `pop`, `dup`, `swap`, `dup2` | Reorders/duplicates/discards stack values by category |
| Comparison/branching | `ifeq`, `if_icmpgt`, `ifnull`, `goto` | Reads condition from stack, may change execution position |
| Invocation/return | `invokestatic`, `invokevirtual`, `invokeinterface`, `ireturn`, `return` | Passes arguments, creates/completes method call |
| Fields | `getstatic`, `putstatic`, `getfield`, `putfield` | Reads/writes field, consumes/pushes reference and value |
| Objects/arrays | `new`, `newarray`, `anewarray`, `iaload`, `iastore`, `arraylength` | Creates object, accesses array, uses reference |
| Type check/exceptions | `checkcast`, `instanceof`, `athrow` | Checks reference type or throws exception |
| Synchronization | `monitorenter`, `monitorexit` | Operates on monitor per JVM rules |

Common prefixes indicate the JVM value type: `i` for `int`, `l` for `long`, `f` for `float`, `d` for `double`, `a` for **reference** in instructions like `aload`/`astore`. However, **not every instruction with prefix `a` follows the same pattern**; always read the specific opcode definition.

Do not treat this table as a list of **all** JVM bytecodes. Its purpose is to recognize how instructions operate on locals, the operand stack, and control flow; specialized instructions have additional conditions on types, structure, and exceptions.

## 5. Accurately simulating `iload`, `iadd`, `imul`, and `istore`

Suppose we have a static method with two parameters:

```java
static int combine(int a, int b) {
    int result = (a + b) * 2;
    return result;
}
```

With typical bytecode from `javac` on Java 17:

```text
0: iload_0
1: iload_1
2: iadd
3: iconst_2
4: imul
5: istore_2
6: iload_2
7: ireturn
```

Suppose we call `combine(3, 4)`. Before the first instruction, locals contain `a = 3` and `b = 4`, and the operand stack is empty.

| PC offset | Instruction | Stack before → after (top on right) | Relevant locals |
| ---: | --- | --- | --- |
| 0 | `iload_0` | `[] → [3]` | `slot0=3` |
| 1 | `iload_1` | `[3] → [3,4]` | `slot1=4` |
| 2 | `iadd` | `[3,4] → [7]` | Unchanged |
| 3 | `iconst_2` | `[7] → [7,2]` | Unchanged |
| 4 | `imul` | `[7,2] → [14]` | Unchanged |
| 5 | `istore_2` | `[14] → []` | `slot2=14` |
| 6 | `iload_2` | `[] → [14]` | `slot2=14` |
| 7 | `ireturn` | `[14] → []` in callee | Returns `14` to caller |

At **offset 2**, `iadd` pops the two numbers in order from the operand stack and pushes their sum. At **offset 4**, `imul` pops `7` and `2` and pushes `14`. At **offset 5**, `istore_2` empties the operand stack by storing `14` into local slot 2.

With the `ireturn` instruction, the value is transferred as the result of the method call: the caller receives `14` at the corresponding position on the **caller's operand stack**, while the callee frame terminates. There is no single shared operand stack for all methods.

### 5.1. Why is `max_stack = 2` in this method?

In the table, the maximum depth of the operand stack is **2 units**: `[3, 4]` or `[7, 2]`. `max_locals` requires **3 slots** to hold `a`, `b`, and `result`. `javap -v` typically displays the corresponding metadata for `combine`:

```text
stack=2, locals=3, args_size=2
```

The line above is representative of `javap` output for a typical `javac` version; if inspecting actual output, compare it against the actual code rather than relying on a printout from another environment.

**Do not calculate `max_stack` by counting the program's variables.** It is the maximum stack level used while executing bytecode within the frame, not the number of declared variables or the number of frames on the call stack.

### 5.2. Trying an expression with non-commutative operators

`isub` and `idiv` require attention to value order. If the stack is `[a, b]` (with `b` on top), then `isub` computes `a - b` and `idiv` computes `a / b` according to JVM integer division rules.

Example:

```text
iconst_5     → [5]
iconst_2     → [5, 2]
isub         → [3]       // 5 - 2, not 2 - 5
```

Do not describe the stack generically as "taking the top as the left operand"; the operand order of each instruction is explicitly specified.

## 6. PC register and bytecode offset: what is being counted?

The **Program Counter (PC) register** is private state belonging to **each JVM thread**. In the JVMS model, when a thread is executing a **non-native** method, the PC contains the address of the JVM instruction currently being executed. If the current method is **native**, the value of the PC register is **undefined**.

This is not a guarantee that the PC is a directly readable Java variable, nor does it mean applications should guess PC numbers from a stack trace. The PC is a component of the **JVM execution model**, not an ordinary query API like `Thread.currentThread()`.

### 6.1. Reading the three columns in `javap` output

```text
  0: iload_0
  1: iload_1
  2: iadd
  3: iconst_2
  4: imul
  5: istore_2
  6: iload_2
  7: ireturn
```

- **To the left of `:`:** bytecode offset, measured in bytes from the start of the method's `code[]`.
- **To the right:** opcode mnemonic (and operands if any).
- **PC:** logically points to the thread's currently executing JVM instruction, so it can be related to these offsets when analyzing bytecode.

Do not confuse **bytecode offset** with **instruction index**. If an instruction at offset 1 is 3 bytes long, the next instruction may start at offset 4. Offsets do not necessarily increase uniformly by one.

### 6.2. Sequential execution, branching, and method calls

Along a branch-free path, the JVM advances to the next instruction. However, there are three other fundamental situations:

1. **Branching:** `if…` or `goto` transfers control to a target instruction; the PC corresponds to the chosen target.
2. **Method calls:** `invoke…` sets up a new call, a frame for the called method is activated; when it returns, the caller resumes at the point after the call according to execution semantics.
3. **Exceptions:** when an error/`athrow` occurs, control may transfer to a valid exception handler; if there is no handler in the frame, the frame may complete abruptly and the search for a handler continues in the caller.

The PC does not "increment steadily until it hits the end of the class file." Each method has its own `code[]`, and the JVM has specific rules for decoding instructions, resolving branch targets, and transferring control flow.

### 6.3. Does a multithreaded JVM have one PC or many PCs?

Each JVM thread has **its own PC register**, because threads may be executing instructions in different methods or at different positions within the same method. The JVM stack and the operand stacks within frames are also tied to their respective threads.

```text
Thread A                             Thread B
PC → methodA, offset 12             PC → methodB, offset 5
JVM stack A                         JVM stack B
  frame methodA                       frame methodB
    locals / operand stack              locals / operand stack
```

Two threads can share the heap and objects, but **do not share PC registers or active execution frames**. The scheduler may pause/resume a thread; OS scheduling behavior and runtime implementation details do not change the PC rules in the JVM model.

## 7. Branch operands: moving the PC by relative offset

Many branch instructions such as `ifeq`, `if_icmpge`, or `goto` use a **relative branch offset**, calculated from the **address of the branching opcode**, not from the address of the next instruction.

Example diagram with hypothetical offsets:

```text
 0: iconst_0
 1: istore_1
 2: iload_0
 3: ifle       12
 6: iconst_1
 7: istore_1
 8: goto       12
11: nop
12: iload_1
13: ireturn
```

**This is an illustrative diagram, not a claim that real `javac` must emit this exact sequence.** For example, the branch at offset 3 to offset 12 has a logical offset of **12 - 3 = +9** bytes. If a `goto` at offset 8 jumps to 12, the corresponding offset is **+4** bytes.

`javap` usually prints the **absolute target offset** directly, such as `ifle 12`, sparing the reader from manually decoding the signed branch displacement stored in the class file. In raw bytecode, the branch operand of `ifle` is a **16-bit** signed integer (two bytes); `goto_w` uses a 32-bit signed offset.

At a conditional branch, the verifier and runtime must ensure the target is a valid instruction boundary, not falling in the middle of another instruction's operand bytes. Execution flow must obey type and operand stack rules at merge points.

### 7.1. `if…` consumes values on the stack

For example, the expression `if (n == 0)` may compile to:

```text
iload_0          ; stack [] → [n]
ifeq target      ; pop n; if n == 0, jump
```

After `ifeq` checks the condition, the value `n` has been **popped off the operand stack** on both paths; it does not stay there automatically. Some opcodes compare **one** value against 0/null (`ifeq`, `ifnull`), while `if_icmp…` compares **two** int values from the stack.

### 7.2. Loops require backward branches

A `for` loop can generate a branch to a lower offset to check the loop condition. In this case, the PC goes to an **earlier** instruction rather than increasing forever.

```text
[Initialization] → [Condition check] → false → [Exit loop]
                         |
                       true
                         v
                    [Loop body]
                         |
                     [Update]
                         |
                         +--------→ [Condition check]
```

Depending on the compiler, `for` may emit a `goto` back to the top of the loop, or use a conditional branch instruction to jump back. The core structure remains a **control flow graph** with a back edge; there is no special "loop" instruction in the sense that every loop uses a single specific opcode.

### 7.3. `tableswitch` and `lookupswitch`

These two instructions are used for appropriate forms of `switch`:

- `tableswitch` describes multiple targets over a relatively contiguous range of integer values.
- `lookupswitch` represents key/target value pairs; suitable for sparse key cases depending on compiler strategy.

Both have padding and multi-byte branch operands; their length depends on the number of cases. Do not claim that every `switch` in Java uses `tableswitch`; the compiler chooses based on semantics, key density, and code-generation strategy.

## 8. Method calls: passing arguments via stack and switching frames

Consider:

```java
static int twice(int x) {
    return x * 2;
}

static int caller() {
    return twice(4);
}
```

In `caller`, the compiler can push the value 4 onto the operand stack and then use `invokestatic` to call `twice`. The caller provides arguments as described by the **method descriptor**. Upon invocation:

```text
Caller frame:
  ... operand stack [4]
             |
             | invokestatic twice:(I)I
             v
Callee frame twice:
  local slot 0 = 4
  operand stack = []
  ... executes iload_0, iconst_2, imul, ireturn ...
             |
             | result 8
             v
Caller frame:
  ... operand stack [8]
```

Key points:

- `invokestatic` pops the appropriate arguments from the caller's operand stack.
- The called method runs with a **new frame**, having its own locals and operand stack.
- If the callee returns an `int` value via `ireturn`, the caller receives that value onto its own operand stack.
- If the method has return type `void`, the `return` instruction passes no return value to the caller.
- With `invokevirtual` or `invokeinterface`, there is normally also a **receiver reference** along with arguments on the operand stack; linking and dispatch must follow JVM rules.

When encountering `invokevirtual`, the opcode name alone is not enough to know which specific implementation the method dispatches to. The runtime determines the target according to the object's actual class and method invocation rules. A null receiver can lead to a `NullPointerException`; that is a valid runtime error, not an indication that the class file has a wrong opcode.

### 8.1. Descriptors link the operand stack to method signatures

Example descriptors:

```text
(II)I                    // two int parameters, returns int
(Ljava/lang/String;)V    // one String reference, returns void
([I)J                    // one int[] reference, returns long
```

`I` represents `int`, `J` represents `long`, `V` is used for `void` as the return type, `L...;` for class/interface, and `[` for array.

The verifier uses these rules to know how many values and of what types a method-invocation instruction must consume, as well as what return value will appear on the caller's stack. **Category-2 slots** must be accounted for properly with `long`/`double`.

### 8.2. `invoke…` involves the constant pool

Most method-invocation instructions use an **index into the runtime constant pool** of the current class, which holds a symbolic reference or appropriate invocation information. During linking, the JVM resolves references according to its own rules, which can lead to linkage errors if a class/method is invalid or inaccessible.

Do not interpret the operand of `invokevirtual #k` as a "fixed native function address." It is a reference in the class file format so that the JVM can link with the correct semantics.

## 9. References, objects, and arrays in the stack model

A stack-based machine does not only do arithmetic. For objects and arrays, **reference values** are also stored in locals and on the operand stack.

Example:

```java
String word = "Java";
int size = word.length();
```

A typical related opcode sequence:

```text
ldc #k                   ; String constant reference
astore_0                 ; store reference into local slot 0
aload_0                  ; push reference onto operand stack
invokevirtual #method    ; call String.length() on receiver
istore_1                 ; store int result
```

The `#k` and `#method` markers denote illustrative **constant-pool indices**. A compiler may arrange local slots differently depending on how it compiles.

For arrays:

```java
int[] values = new int[2];
values[0] = 9;
int first = values[0];
```

An element write `iastore` requires on the operand stack in the appropriate order: **array reference**, **index**, **int value**. An element read `iaload` requires **array reference** and **index**, and pushes the read value. The runtime also checks for null references, array bounds, and related constraints; some operations may throw `NullPointerException` or `ArrayIndexOutOfBoundsException`.

`aconst_null` pushes a null reference onto the operand stack. It is a meaningful value in the reference type model; the opcode does not create a "null object." Null cannot be used to invoke an instance method without hitting the corresponding runtime check.

### `new` and the uninitialized state

To create an object, typical bytecode has a sequence like:

```text
new MyClass
dup
invokespecial MyClass.<init>:()V
```

The `new` instruction allocates the object and pushes a reference that is **not yet fully initialized** according to verifier rules; `dup` typically duplicates the value on the stack to keep a reference for use after the constructor; `invokespecial` invokes the corresponding constructor. Using an uninitialized reference is strictly constrained; you cannot edit bytecode to skip valid initialization steps and expect the verifier to accept it.

## 10. Complete Java 17+ example: inspecting operand stack and PC with `javap`

Create the file **`StackMachineDemo.java`**:

```java
public final class StackMachineDemo {
    static int combine(int a, int b) {
        int result = (a + b) * 2;
        return result;
    }

    static int sumTo(int n) {
        int total = 0;
        for (int i = 1; i <= n; i++) {
            total += i;
        }
        return total;
    }

    static String describe(int value) {
        return value >= 0 ? "nonnegative" : "negative";
    }

    public static void main(String[] args) {
        System.out.println("combine(3, 4) = " + combine(3, 4));
        System.out.println("sumTo(4) = " + sumTo(4));
        System.out.println("describe(-1) = " + describe(-1));
    }
}
```

From the directory containing the file, run with **JDK 17 or later**:

```bash
javac --release 17 StackMachineDemo.java
java StackMachineDemo
```

**Exact stdout**:

```text
combine(3, 4) = 14
sumTo(4) = 10
describe(-1) = negative
```

The three methods demonstrate different behaviors:

1. **`combine`:** loads locals, pushes onto stack, performs arithmetic, stores local, and returns.
2. **`sumTo`:** uses locals `total` and `i`, increment, comparison, conditional jump, and looping back; the PC does not go straight from offset 0 to the end in a single pass.
3. **`describe`:** checks a condition and selects one of two String constants; the branch determines the next instruction.

Command to view disassembly:

```bash
javap -c -p StackMachineDemo
```

The `-c` flag prints method code, and `-p` also shows non-public members. To view a broader structure, use:

```bash
javap -v -p StackMachineDemo
```

`-v` shows the constant pool, method descriptors, `Code` attribute, `stack`/`locals`, frame tables when present, and other class file information.

### 10.1. Disassembly output to compare against `combine`

With JDK 17 `javac` and the exact `combine` code above, the method's opcode section is:

```text
static int combine(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: iconst_2
     4: imul
     5: istore_2
     6: iload_2
     7: ireturn
```

The offsets are **byte offsets in `code[]`**; they are not source line numbers. Following the simulation table in section 5:

```text
PC   instruction     operand stack (after instruction)
0    iload_0          [3]
1    iload_1          [3,4]
2    iadd             [7]
3    iconst_2         [7,2]
4    imul             [14]
5    istore_2         []
6    iload_2          [14]
7    ireturn          terminates frame and returns 14
```

Check your own output when using another compiler: the JVM only requires valid code with correct semantics, not that every compiler emits **the exact same instruction sequence** for a given source. Subsequent JIT optimizations also do not alter the bytecode text that `javap` reads from the `.class` file.

### 10.2. Why does `sumTo` prove the PC can jump backward?

`sumTo(4)` executes:

```text
total = 0
i = 1 → total = 1
i = 2 → total = 3
i = 3 → total = 6
i = 4 → total = 10
i = 5 → condition i <= n is false → return 10
```

When disassembling, look for opcodes in the `if_icmp…`/`if…` group, `goto`, and `iinc` (details depend on the compiler). Some branch targets jump back to previously visited bytecode offsets to continue the loop; eventually the conditional branch moves the PC to the return area. This is how a **control-flow graph** represents loops using basic instructions.

### 10.3. Why doesn't `describe` have to have a "ternary opcode"?

The `?:` operator belongs to Java syntax. The compiler can turn it into a conditional branch, loading a String constant from the constant pool and then `areturn`. In bytecode, there is no requirement for a general opcode named `ternary` to exist. The JVM model executes the steps **compare → branch → load reference → return**.

### 10.4. Checking the constant pool yourself

In `javap -v`, operands of the form `#k` usually reference the constant pool. For the calls in `main`, you will see constant-pool entries or information related to printing to stdout and string concatenation. On Java 17, the compiler may use **`invokedynamic`** for string concatenation; there is no contradiction with the stack model: arguments are still prepared and consumed according to the call's descriptor.

`invokedynamic` is an opcode with its own linking rules; we do not need to explain the entire bootstrap method in this lesson to understand that it **reads operands via the runtime constant pool and consumes values from the operand stack**.

## 11. Branch offset and instruction size: a small simulation exercise

Suppose we have the following bytecode offsets in a **hypothetical** example:

```text
0:  iconst_1
1:  istore_0
2:  iload_0
3:  ifeq          11
6:  bipush        10
8:  istore_0
9:  goto          13
12: nop
13: iload_0
14: ireturn
```

This diagram is only for visualizing instruction sizes and jump paths; if used as a real class file, every target (including offset 11 illustrated above) **must point to a valid opcode boundary**. In this illustrative sequence, offset 11 falls inside the operand bytes of `goto`, so **this is an example of an invalid branch target and would not be valid bytecode**.

Let's fix the target of `ifeq` to offset **12**:

```text
3: ifeq 12  // displacement = 12 - 3 = +9
```

Then, for both branch targets and stack states to be valid, we must ensure every converging path does not violate stack/locals rules. For instance, fixing a displacement only corrects the **target position**; it does not automatically guarantee the entire frame/`StackMapTable` is valid.

A safe learning approach is:

1. First determine **bytecode instruction boundaries** based on the length of each opcode.
2. Compute branch displacement from the **branching opcode offset** to the **target opcode offset**.
3. Check **stack height and verification types** at the target across all paths.
4. If the class format requires stack map frames, verify/update `StackMapTable` accordingly.

This technique is especially important when reading bytecode generated by instrumentation/transformation tools.

## 12. How do data types affect stack operations?

You cannot swap one opcode for another just because both "add two numbers":

| Instruction | Operands on stack | Result |
| --- | --- | --- |
| `iadd` | Two `int`s | `int` |
| `ladd` | Two `long`s | `long` |
| `fadd` | Two `float`s | `float` |
| `dadd` | Two `double`s | `double` |
| `i2l` | One `int` | `long` |
| `l2i` | One `long` | `int` |
| `aload` | A local with an appropriate reference type | Pushes reference |
| `astore` | A reference on the stack | Writes reference to local |

Because category-2 values occupy two stack units, `long`/`double` must be distinguished when computing `max_stack` and handling instructions like `dup2`. Types such as `byte` or `boolean` are often represented and manipulated as `int` in many JVM instructions, but that does not remove specific checking/conversion rules at boundaries such as array stores or descriptors.

### Category-2 example

```java
static long add(long a, long b) {
    return a + b;
}
```

A valid bytecode form:

```text
lload_0
lload_2
ladd
lreturn
```

Because each `long` parameter uses **two local slots**, `a` starts at slot 0 and `b` at slot 2. Do not write `lload_1` for parameter `b` in this layout. When both `long` values are on the operand stack, they occupy a total of **four units** of stack; the `ladd` operation produces one `long` occupying two units.

For an instance method, slot 0 is also reserved for `this`, so indices shift accordingly. Determine the method's signature and modifiers before inferring the locals layout.

## 13. What does the bytecode verifier check?

The JVM verifier checks **structural and type** constraints so that no valid instruction flow can use the stack/locals in a way that violates an opcode's requirements. Relevant checks include:

- `iadd` receives two values of appropriate verifier type, not a reference such as `String`.
- `aload` reads a local slot holding a valid reference value; `iload` requires an appropriate integer type.
- Every branch target is valid and paths reaching the target have compatible type states.
- The operand stack does not exceed the method's `max_stack` according to the rules.
- The return opcode matches the return type in the method descriptor, e.g. `ireturn` when returning `int`.
- The receiver/arguments of a call match method invocation rules.
- Uninitialized references in constructors are managed according to verifier rules.

`StackMapTable` in the class file declares **verification type states** at key offsets for the verifier to check against the bytecode flow. It is not a stack holding actual values at a specific runtime moment. This metadata assists type verification, not a "program counter."

**The verifier does not prove that a program has no business-logic bugs.** An `idiv` method that passes type checking can still throw `ArithmeticException` when the divisor is 0. Similarly, a type-valid null reference can still throw `NullPointerException` when dereferenced.

If bytecode is incorrectly transformed after compilation, the JVM may reject the class with `VerifyError` or another format/linkage error depending on the nature of the fault. Investigate opcodes, stack states, offsets, class version, and `StackMapTable` before drawing conclusions.

## 14. PC, exceptions, and `athrow`

Execution steps do not always continue from the instruction immediately following the current one. Consider:

```java
static int safeDivide(int a, int b) {
    try {
        return a / b;
    } catch (ArithmeticException ex) {
        return -1;
    }
}
```

With `b = 0`, integer division creates an `ArithmeticException`. The JVM searches for an appropriate handler in the `Code` attribute's **exception table**. If a handler is found in the method, control transfers to the handler's bytecode offset, and the operand stack at the handler receives the exception reference according to exception-handling rules.

Conceptual diagram:

```text
... iload_0, iload_1, idiv ...
               |
           b == 0
               |
               v
       ArithmeticException
               |
               v
  exception table → handler PC
               |
               v
  handler receives exception reference
               |
               v
  returns -1
```

Do not assume the PC always moves to the next instruction after `idiv`. When an exception is thrown and a handler exists, control flow **jumps to the handler**. If no suitable handler exists in the frame, the search continues through the caller's stack frames; a stack trace records the relevant call frames, not a log of all visited PC offsets.

`athrow` is the instruction that throws an object reference of an appropriate exception type. It alters control flow similarly: it is not an ordinary "pop then next PC" operation.

## 15. Is a stack-based JVM always slower than a register-based machine?

**It cannot be concluded from the bytecode model alone.** The JVM's stack-based ISA uses many short instructions like `iload_0`, `iadd`, `istore_1` and represents operands implicitly via the operand stack. This can keep the bytecode format compact and create a relatively CPU-independent execution contract.

However, the JVM can:

- **Interpret:** read opcodes and perform the corresponding operations.
- **JIT-compile:** translate frequently executed bytecode regions into CPU-appropriate machine code, optimizing through intermediate representations, register allocation, inlining, etc.
- **Runtime optimization:** change strategies depending on profile and deployment environment.

Therefore, **the operand stack is a bytecode semantic model**; there is no requirement that every `iadd` must turn into an actual push/pop pair on a hardware stack. A JIT compiler can keep intermediate values in CPU registers in the final machine code.

Any claim about performance requires benchmarking a specific workload, with proper warm-up, considering both startup time and measurement methodology. Counting bytecode instructions is **not enough** to predict execution speed.

## 16. Common mistakes when reading `javap`

| Misconception | Correct understanding |
| --- | --- |
| "`0:` is the Java line number" | It is the bytecode offset in the method's `code[]` |
| "Every opcode is one byte so every instruction is one byte" | Opcode is one byte; operands can extend the instruction, switches have variable length |
| "`iadd` has no operands" | No operand bytes, but **pops two values** from the operand stack |
| "`iload_0` loads constant 0" | It **reads local slot 0**; `iconst_0` pushes constant 0 |
| "`istore_2` stores into the second heap object" | It writes to **local slot 2** of the method frame |
| "Operand stack is the call stack" | Operand stack belongs to **each frame**; call stack contains multiple frames |
| "`max_stack` is the maximum number of function calls" | It is the maximum operand stack depth of a method in stack units |
| "PC is a global variable of the JVM" | Each JVM thread has its own PC |
| "PC always increments by 1" | Instructions have varying lengths; branches, method calls, exceptions change control flow |
| "`goto 15` is a +15 offset delta" | `javap` displays the target offset; the class file encodes a relative branch displacement |
| "`long` occupies one local slot like `int`" | `long`/`double` use **two local slots** |
| "JIT code executes the operand stack using a real RAM stack at every opcode" | JIT can map bytecode semantics to CPU registers/machine code |
| "The verifier proves every input runs successfully" | It checks structural/type safety, not the absence of valid runtime exceptions |

Another mistake is taking a `javap` snippet from another method and inferring local positions backward without the method signature. For example, `iload_1` in an instance method may be the first parameter, whereas in a static method it may be the second parameter. You must check **whether `this` is in slot 0**, and note category-2 types.

## 17. Self-practice reading bytecode

### Exercise 1. Reading the operand stack

Given the valid hypothetical bytecode snippet:

```text
0: iconst_3
1: iconst_4
2: iadd
3: iconst_2
4: imul
5: ireturn
```

Write the stack after each instruction and the return result.

**Answer:**

```text
0 → [3]
1 → [3, 4]
2 → [7]
3 → [7, 2]
4 → [14]
5 → return 14
```

### Exercise 2. Distinguishing immediate and runtime operands

Given `bipush 100` and `iadd`. Which instruction has an accompanying operand byte? Which instruction takes values from the operand stack?

**Answer:** `bipush` has an operand byte representing 100 and pushes 100. `iadd` has no operand bytes but consumes two `int` values from the operand stack and pushes their sum.

### Exercise 3. PC and branch displacement

A `goto` opcode is at offset 20, and its target is at offset 7. What is the signed offset conceptually encoded?

**Answer:** `7 - 20 = -13`, measured from the `goto` opcode offset, **not** from the offset immediately after `goto`.

### Exercise 4. Local slots

A static method takes `(long first, double second, int third)`. Which slots do the parameters start at?

**Answer:** `first` is in slots 0–1; `second` is in slots 2–3; `third` is in slot 4. If it were an instance method, the receiver `this` would be in slot 0 and the parameters would shift accordingly.

### Exercise 5. How do `iload_0` and `iconst_0` differ?

**Answer:** `iload_0` reads the `int` value from local slot 0; `iconst_0` pushes the constant value `0` without reading locals.

### Exercise 6. Why can a method with `max_stack=2` still call another method?

**Answer:** `max_stack` bounds the operand stack **within the current frame**. A call creates/activates another frame with the callee's own locals and operand stack; that limit of 2 is not used as the maximum number of frames on the JVM stack.

### Exercise 7. A piece of Java code runs smoothly with input A. Is that enough to conclude the bytecode is always valid?

**Answer:** No. The verifier must check type/flow constraints at the class file level; one specific test does not explore all branches. Conversely, passing verification also does **not** guarantee there are no business-logic runtime errors.

### Exercise 8. Why can't you deduce which CPU registers are used from `javap -c`?

**Answer:** `javap` displays **JVM bytecode**, not machine code after JIT optimization. How the JVM maps the operand stack to CPU registers is a detail of the runtime and execution version.

## 18. Summary and official documentation

The right mental flow when reading bytecode:

```text
instruction offset / PC
          |
          v
Read opcode and operand bytes if any
          |
          v
Check types and operand stack / locals state before instruction
          |
          v
Apply pop, push, load, store, or branch effect
          |
          v
Determine next instruction (sequential, branch, call/return, exception)
          |
          v
Repeat until the method finishes
```

**Opcode** specifies the operation, **operand bytes** carry encoded parameters for certain instructions, the **operand stack** carries runtime operands, **local variables** hold parameters/local values, and the **PC register** identifies the current instruction position of each thread. These components work together to form the JVM's stack-based execution model.

Further reading:

- [JVM Specification 2.5 — Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5): PC register, JVM stacks, and runtime data areas.
- [JVM Specification 2.6 — Frames](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.6): local variables, operand stacks, frames, and how values are passed on call/return.
- [JVM Specification 4.7.3 — Code Attribute](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, the `code[]` bytecode array, and the exception table.
- [JVM Specification 6 — The JVM Instruction Set](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html): semantics, operands, structure, and exceptions of each opcode.
- [`javap` Tool Documentation (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): `-c`, `-p`, and `-v` for reading code/attributes.
