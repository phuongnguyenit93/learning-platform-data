# Code attribute, local variables, operand stack, and return instructions

This lesson belongs to **Java Advance – instrumentation / Class file fundamentals**. The goal is to be able to read a method's bytecode and accurately understand three things that are often confused: **local variables**, **operand stack**, and **return instructions**. This is also prerequisite knowledge before inserting, deleting, or modifying bytecode with an instrumentation tool.

## 1. From a Java method to the `Code` attribute

A `.class` file consists of structures such as the constant pool, field declarations, and the `method_info` list. For a method with a normal Java body, in the attributes list of `method_info` there is **exactly one `Code` attribute**. `abstract` or `native` methods do not have a `Code` attribute. Constructors `<init>` and class initializers `<clinit>` also contain bytecode in `Code` when they have an executable body.

```text
ClassFile
└── methods[]
    └── method_info (name + descriptor + access_flags + attributes[])
        └── Code
            ├── max_stack / max_locals
            ├── code[]                 ← JVM instruction bytes
            ├── exception_table[]      ← protected regions and exception handlers
            └── attributes[]           ← Code metadata
                ├── LineNumberTable
                ├── LocalVariableTable
                └── StackMapTable      (if generated/written)
```

Simplified structure according to the JVM Specification `4.7.3:

```text
Code_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 max_stack;
    u2 max_locals;
    u4 code_length;
    u1 code[code_length];
    u2 exception_table_length;
    { u2 start_pc; u2 end_pc; u2 handler_pc; u2 catch_type; }
        exception_table[exception_table_length];
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
```

- `u1`, `u2`, `u4` are 1-, 2-, and 4-byte unsigned integers respectively in the class file format. `attribute_name_index` references the string `Code` in the constant pool; `attribute_length` is the number of data bytes of the attribute, **excluding** the 6-byte attribute header.
- `max_stack` is the maximum depth of the operand stack, measured in **stack units**; `long`/`double` values (category 2) occupy two units, while category 1 values occupy one. This is not the number of `push` instructions, nor is it a limit of the entire JVM.
- `max_locals` is the number of local variable **slots** that a frame reserves for the method, including parameters and `this` when present. One `long`/`double` occupies two consecutive slots.
- `code_length` is the actual number of bytes in `code[]`, required to be from 1 to 65,535 bytes. The numbers `0:`, `1:`, `2:` that `javap` displays are **bytecode offsets** (positions measured in bytes), not by default instruction sequence numbers; some instructions are longer than one byte.
- `exception_table` describes the handlers. The protected range is `[start_pc, end_pc)` (start inclusive, end exclusive), `handler_pc` is where the handler begins, `catch_type` references the exception type; `catch_type = 0` means the handler catches all exceptions.
- `attributes[]` nested inside `Code` contains additional metadata. `LineNumberTable` maps bytecode offsets to source lines; `LocalVariableTable` records variable names/types/liveness scopes for debuggers; `StackMapTable` provides type state used when the verifier checks control flows. These metadata items are **not** the operand stack or local variables running in memory. A valid method may omit `LocalVariableTable`.

**Distinction:** The `Code` attribute is data in the **class file**; when the JVM invokes a method, the JVM creates a **runtime frame** with a local variable array and an operand stack for that invocation. The same `Code` can be executed by multiple different frames, including during recursion or concurrent execution.

## 2. JVM frame: local variables and operand stack

Each method invocation can be visualized as follows:

```text
                         FRAME of an invocation
   ┌──────────────────────────────┬──────────────────────────────┐
   │ Local variable array         │ Operand stack                │
   │ slot 0, slot 1, slot 2, ...  │  bottom → ... → top (LIFO)   │
   │ holds args, this, temp vars  │  holds operands/intermediates│
   └──────────────────────────────┴──────────────────────────────┘
          ↑ iload/istore/...              ↑ iconst, iadd, invoke, ...
```

### 2.1. Local variables: addressed by slot index

- For an **instance method**, slot `0` holds the `this` reference upon method entry; explicit parameters start at slot `1`. For a **static method**, there is no `this`, and the first parameter starts at slot `0`.
- `int`, `float`, and references occupy one slot; `long` and `double` occupy two slots. `boolean`, `byte`, `char`, and `short` values are represented as type `int` when processed by the corresponding integer instructions.
- `iload_0`, `iload_1`, or `iload n` **reads** an integer slot and **pushes** the value onto the operand stack; `istore_2` or `istore n` **pops** the value at the top of the stack and **writes** it into the slot. The `aload/astore` families are used for references, `lload/lstore` for `long`, `dload/dstore` for `double`, and `fload/fstore` for `float`.
- `iinc index, const` directly modifies an `int` variable in the local variable array without placing operands on the stack. `wide` extends the index/operand width for certain local access instructions when the index is large.
- Slots can be **reused** by variables with non-overlapping liveness scopes. The number of slots in `max_locals` does not necessarily equal the number of variable names in the source code; variable names can also be absent due to missing debug metadata. Reading a slot that has not been initialized along a control flow path is not accepted by the verifier.

For example, for an instance method `public long echo(long value)`: slot `0` holds `this`, and the parameter value `value` uses slots `1` and `2`; therefore `max_locals` must be **at least 3**. The `lload_1` instruction loads a `long` value from two slots, and then `lreturn` returns that value to the caller. With `static long echo(long value)`, the parameter starts at slot `0` and uses slots `0–1`.

### 2.2. Operand stack: LIFO computation

The operand stack does not contain variable names; instructions consume and produce **values** according to the last-in-first-out stack rule. For example:

```text
iconst_2    []       -> [2]
iconst_3    [2]      -> [2, 3]
iadd        [2, 3]   -> [5]
istore_0    [5]      -> []        (write 5 into local slot 0)
iload_0     []       -> [5]
ireturn     [5]      -> end frame, pass 5 to caller
```

In the notation `[2, 3]`, **the right side is the top of the stack**. `iadd` pops two `int` values (popping `3` first, then `2`), adds them, and pushes a new `int`. `istore_0` pops a value from the stack; `iload_0` produces a stack value from a slot. An `invoke*` call pops the receiver object (if needed) and arguments according to the descriptor, then places the return value onto the caller's stack **if** the result is not `void`.

Some useful stack operations when reading or instrumenting bytecode: `dup` duplicates one category 1 value on top, `dup2` duplicates one category 2 value or two appropriate category 1 values, `pop` discards one category 1 value, and `pop2` discards one category 2 value or two category 1 values. You must not use `dup`/`pop` as if `long` and `double` occupied only one unit. `swap` is only valid with two category 1 values.

**Key takeaway:** the local array stores data so it can be read by index, whereas the operand stack is where many computations and calls receive/emit operands. `max_stack` and `max_locals` both reside in `Code` but control **two different resources**.

## 3. Java 17+ experiment: tracing each bytecode

Save the following exact file **`FrameDemo.java`**. This is a complete program that can be compiled and run:

```java
public final class FrameDemo {
    public static int sumPlusOne(int a, int b) {
        int sum = a + b;
        return sum + 1;
    }

    public long echo(long value) {
        return value;
    }

    public static void main(String[] args) {
        System.out.println(sumPlusOne(3, 4));
        System.out.println(new FrameDemo().echo(12L));
    }
}
```

In the directory containing the file, using JDK 17 or newer:

```bash
javac -g FrameDemo.java
java FrameDemo
javap -c -l -p FrameDemo
javap -v -p FrameDemo
```

The two stdout lines from `java FrameDemo` are:

```text
8
12
```

`javap -c` disassembles bytecode instructions; `-l` shows line number and local variable tables **if present**; `-p` also shows non-public members; `-v` shows verbose information, including the `Code` header with `stack`, `locals`, `args_size`, constant pool, and attributes. `javac -g` requests generating debug info (for example, `LocalVariableTable`). Parts such as constant-pool indices, source line numbers, and additional layout may vary by compiler/JDK, so treat the lines below as **an excerpt describing the main instructions of the `sumPlusOne` method**, not the entire `javap` output:

```text
public static int sumPlusOne(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: istore_2
     4: iload_2
     5: iconst_1
     6: iadd
     7: ireturn
```

This method requires `max_locals = 3` (two parameters `a`, `b` and variable `sum`) and `max_stack = 2` (at `iadd`, the stack holds two integers). With descriptor `(II)I`, the two `I`s in parentheses are two `int` parameters and the final `I` is the `int` return type.

Tracing when `a = 3`, `b = 4`:

| Offset | Instruction | Local slots after instruction (a, b, sum) | Operand stack after instruction |
| ---: | --- | --- | --- |
| 0 | `iload_0` | `(3, 4, —)` | `[3]` |
| 1 | `iload_1` | `(3, 4, —)` | `[3, 4]` |
| 2 | `iadd` | `(3, 4, —)` | `[7]` |
| 3 | `istore_2` | `(3, 4, 7)` | `[]` |
| 4 | `iload_2` | `(3, 4, 7)` | `[7]` |
| 5 | `iconst_1` | `(3, 4, 7)` | `[7, 1]` |
| 6 | `iadd` | `(3, 4, 7)` | `[8]` |
| 7 | `ireturn` | frame ends | returns `8` to caller |

The `—` symbol means variable `sum` has not been initialized yet. The table describes the logical state of the frame, not asserting that the JVM must implement each slot/stack as a separate physical memory region; the JIT may optimize execution.

For `echo(long value)`, the result typically has the sequence `lload_1` → `lreturn`. Note that `lload_1` reads a category 2 value and `lreturn` returns a `long`; they are not two reads/returns of an `int`.

## 4. Six `return` instructions by data type

In bytecode, a return instruction must be compatible with the **method descriptor**. `return` in Java source can generate one of the following six opcodes:

| Opcode | Value type on top of operand stack | Method return type | Effect |
| --- | --- | --- | --- |
| `ireturn` | `int` (category 1) | `int`, `boolean`, `byte`, `char`, `short` | Pops an int-typed value and returns it |
| `lreturn` | `long` (category 2) | `long` | Returns long |
| `freturn` | `float` (category 1) | `float` | Returns float |
| `dreturn` | `double` (category 2) | `double` | Returns double |
| `areturn` | reference (category 1) | object, interface, or array reference | Returns reference, including a valid `null` |
| `return` | no return value required | `void`, constructor/class initializer | Completes normally, transfers no result |

For value-returning instructions, the JVM pops the result from the **callee's operand stack**, terminates that frame, and places the result onto the caller's operand stack (when a caller exists). It does not directly read a Java variable by name: for example, `return sum;` usually requires `iload_2` followed by `ireturn`. After a normal `return`, subsequent instructions in the same frame are not executed.

`athrow` is **not** one of the six return instructions: it throws an exception reference, transferring control to a matching handler or unwinding across frames. `ret` in historical bytecode (paired with `jsr`/`jsr_w`) is also **not** a method return instruction; do not use it in place of `ireturn` or `return`.

### Program to observe all six types

Save to **`ReturnDemo.java`**:

```java
public class ReturnDemo {
    static int intValue(int x) { return x + 1; }
    static long longValue(long x) { return x * 2; }
    static float floatValue(float x) { return x / 2; }
    static double doubleValue(double x) { return x + 0.5; }
    static String referenceValue() { return "OK"; }
    static void voidValue() { System.out.println("done"); }

    public static void main(String[] args) {
        System.out.println(intValue(7));
        System.out.println(longValue(10L));
        System.out.println(floatValue(4.0f));
        System.out.println(doubleValue(2.0));
        System.out.println(referenceValue());
        voidValue();
    }
}
```

```bash
javac ReturnDemo.java
java ReturnDemo
javap -c -p ReturnDemo
```

Stdout of `java ReturnDemo`:

```text
8
20
2.0
2.5
OK
done
```

Observe that the end of `intValue` is `ireturn`, `longValue` is `lreturn`, `floatValue` is `freturn`, `doubleValue` is `dreturn`, `referenceValue` is `areturn`, and `voidValue` ends with `return`. The `main` method is `void`, so it also completes normally with `return`. Even though the source shares the `return` keyword, the JVM uses type-dependent opcodes.

## 5. Control flow, exception handlers, and type checking

At a branch point, loop, method call, or exception handler, you cannot guess the stack solely from the current source line:

1. Valid paths converging at the same bytecode offset must have local variable and operand stack states that are **compatible under type verification rules**. The JVM verifier checks bytecode, including descriptors, operand types, local accessibility, and frame consistency; `StackMapTable` data assists this check.
2. If a handler receives control due to an exception, the frame's operand stack at the start of the handler contains **one matching exception reference**, rather than preserving any in-progress values that were on the stack at the faulting instruction. Handler bytecode typically saves the exception with `astore` before handling it.
3. Offsets in branches (`if*`, `goto`, `tableswitch`, `lookupswitch`) and `exception_table` depend on bytecode layout. Adding new bytes shifts positions and may require updating offsets/ranges and related attributes.
4. `LineNumberTable` and `LocalVariableTable` serve debugging and may differ or be absent across compilations while the program still runs correctly. `StackMapTable` belongs to verification; it is not a variable name table for debuggers and is not synonymous with `max_stack`.

For example, `try/catch` may generate additional handler entries in `exception_table`; `finally` or try-with-resources may generate bytecode that duplicates exit paths and exception handling. You **should not** assume that one `return` in source always corresponds to exactly one `return` instruction in the class file.

## 6. Why does this knowledge matter for instrumentation?

Suppose you want to record the return value of an `int` method before it finishes. Right before `ireturn`, the result is already on the operand stack. If you call a logger directly, the logger may **consume** the result, leaving `ireturn` with no operand to pop. As a **bytecode illustration** (not a standalone Java program), the right pattern with a logger method `Trace.logInt(int) : void` could be:

```text
...                                 ; stack = [result:int]
dup                                 ; stack = [result:int, result:int]
invokestatic Trace.logInt:(I)V     ; stack = [result:int]
ireturn                             ; return result to caller
```

Points to check when inserting instructions:

- **Correct opcode:** `ireturn`/`freturn`/`areturn` use category 1, whereas `lreturn`/`dreturn` use category 2. For a category 2 value, the appropriate copy operation may be `dup2`. For `void` `return`, there is **no** value to `dup`; if recording abnormal exits, the `athrow`/handler path must be considered separately.
- **Correct descriptor and stack effect:** The `invokestatic` call in the example must consume one `int` and produce `void`; another descriptor alters the operand stack or causes a type verification error. Paths with multiple `return`s must be handled properly.
- **Correct frame metadata:** You may need to increase `max_stack`, recompute stack map frames, and update bytecode branch targets, exception handler ranges, debug attribute offsets, and code-dependent structures. `max_locals` needs to increase if additional temporary slots are introduced.
- **Correct program semantics:** A logger call can throw exceptions, cause side effects, trigger instrumentation recursion, or alter timing/synchronization locks. You need a clear intent for how to handle these cases, not just make the class pass the verifier.
- **Use an appropriate bytecode library:** With ASM, for example, there are mechanisms to help recompute maxs/frames in suitable situations, but you still must understand the class hierarchy, class loader, insertion points, and descriptors. Editing byte arrays with manual offset arithmetic easily produces an invalid class.

**Verification rule:** For every insertion point, write out the operand stack state *before* and *after* each instruction; ensure the final return instruction still receives the right value, branch/handler paths remain valid, and the verifier accepts the transformed class.

## 7. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| `max_stack` is the number of local variables | It bounds the operand stack depth; `max_locals` is the number of local slots. |
| `long`/`double` occupy one slot like `int` | They occupy two local slots and two operand stack depth units. |
| Slot 0 is always `this` | Only true on entry to an instance method; a static method starts with its first parameter at slot 0. |
| `javap` printing offset 7 means the 8th instruction | Offset is the number of bytes from the start of `code[]`; instruction lengths vary. |
| Variable names must be present in the class file | Local names are usually in the optional `LocalVariableTable`; bytecode works with indices. |
| `return` is always the `return` opcode | Returning values uses `ireturn`, `lreturn`, `freturn`, `dreturn`, or `areturn`. |
| You can call a logger then `ireturn` without leaving a value | `ireturn` must pop an `int` from the operand stack; often `dup` is needed before the call. |
| Exit bytecodes are only `return` or `ireturn` | There are other return types and abnormal exit paths via exceptions. |
| `StackMapTable` is a snapshot of the runtime stack | It is metadata about type states for bytecode verification. |
| Increasing `max_stack` is enough for any inserted code to run | You must also keep types, control flow, handlers, frames, and related attributes consistent. |

## 8. Self-check

1. For `static long add(long x, int y) { return x + y; }`, upon method entry, at least how many local slots do the parameters use? Which family does the return instruction belong to? **Answer:** `x` uses slots `0–1` and `y` uses slot `2`, so at least **3 slots**; the `long` result is returned with `lreturn` (the compiler must widen `y` from `int` to `long` when adding).
2. In `sumPlusOne`, why is `max_stack = 2` while the method has three variables `a`, `b`, `sum`? **Answer:** the three variables live in the local array; the operand stack only needs to hold at most two `int` values at a time.
3. What opcode does a method returning `String[]` use? **Answer:** `areturn`, because arrays are also references.
4. If you insert a `void` call right before `lreturn`, after the logger consumes the `long` value, can you continue with `lreturn`? **Answer:** no; you must preserve/restore the category 2 value onto the operand stack and verify the stack effect.
5. If the name `sum` does not appear in `javap -c` output, does the variable `sum` necessarily disappear from the bytecode? **Answer:** no; slot `2` is still used via `istore_2`/`iload_2`; displayed names depend on debug metadata such as `LocalVariableTable`.

## Reference specifications

- Java Virtual Machine Specification, **`2.6 Frames**: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6
- Java Virtual Machine Specification, **`4.7.3 Code Attribute; `4.7.4 StackMapTable; `4.7.13 LocalVariableTable**: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3
- Java Virtual Machine Specification, **`6.5 Instructions** (`*load`, `*store`, `iadd`, `ireturn`, `lreturn`, `return`, `athrow` families): https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html
