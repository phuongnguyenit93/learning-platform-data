# Conditional Branches, `goto`, Loops, and Target Addresses in JVM Bytecode

## 1. How Is Control-Flow Source Code Translated into Bytecode?

In Java, we use `if`, `else`, `for`, `while`, `do-while`, `switch`, `break`, and `continue` to express execution order. At the JVM level, most normal control flow is represented by **comparison/condition-checking instructions**, **unconditional jump instructions**, and **multi-way selection instructions**, along with instructions that perform work and return results.

~~~text
Java Source                      Common Bytecode Model

if (condition) { ... }       →   check; jump past block if false
while (condition) { ... }    →   check; run body; jump back to condition
for (init; test; update)     →   init; test; body; update; jump to repeat
break                        →   jump to point after loop/switch
continue                     →   jump to update/check point of loop
switch                       →   tableswitch / lookupswitch / comparison chain
return                       →   ireturn, areturn, return, ... by value type
~~~

This is a way to visualize it, **not a one-to-one rule** between source syntax and a specific bytecode instruction. The compiler can invert conditions, omit redundant branches, constant-fold, change the check position, or generate other structures while preserving the program's semantics.

A method has its bytecode located in the `Code` attribute of the class file. This `code[]` array is a sequence of instruction bytes whose addresses are calculated **from the start of that method's own code**. In `javap -c` output, the numbers at the beginning of lines such as `0:`, `4:`, `12:` are **bytecode offsets**, not source line numbers, constant pool indices, or RAM addresses.

## 2. Program Counter (PC), Fall-Through, and Branch Target

According to the JVM model, each JVM thread has a **program counter (PC) register** to indicate the position of the instruction currently being executed in the current method; details for native methods have separate rules. When executing bytecode instructions:

- **Fall-through**: if an instruction does not change control flow, the next position is usually the next instruction in `code[]` order.
- **Conditional branch**: the JVM checks the condition after popping the required operands from the operand stack. If true, it transfers to the **branch target**; if false, it continues at the next instruction.
- **Unconditional branch**: `goto` transfers directly to the target without checking a condition.
- **Return/throw**: `ireturn`, `areturn`, `return`, `athrow` transfer control out of the method's normal instruction flow, according to invocation and exception-handling rules.

Each instruction has a byte length depending on its opcode and operands. Therefore, bytecode offsets usually **do not increment uniformly by 1**: for example, an `iload_0` instruction may take 1 byte, whereas a standard `ifeq` takes 3 bytes (opcode and two offset bytes). Do not assume an instruction at offset 4 has "instruction sequence number = 4".

### Where Is the Target Address of `if` and `goto` Calculated From?

For 16-bit offset branch instructions such as `ifeq`, `if_icmpge`, `ifnull`, `goto`, the branch offset operand is a **signed 16-bit** number, encoded from two bytes in high-byte then low-byte order. The offset value is added to **the address of the jump opcode itself**, not the address of the instruction immediately following the jump instruction.

~~~text
target_pc = branch_opcode_pc + signed_branch_offset
~~~

Example:

~~~text
  1: ifge          7
  4: iload_0
  5: ineg
  6: ireturn
  7: iload_0
~~~

If the `ifge` opcode is at PC = 1 and the target printed by `javap` is 7, then the displacement (branch offset) is **7 - 1 = +6**, not 7 - 4. If the branch target is smaller than the current PC, the displacement is negative, which is very common in loops.

`javap -c` **prints the computed target PC as the target offset number** for readability; it does not necessarily print the two encoded operand bytes directly. When you need to inspect the actual bytes, use `javap -v` to view the structure and a hex class-file reader if needed, while remembering that `javap`'s presentation is a disassembly.

**Important:** the target must point to a valid instruction in `code[]`, not jump into the middle of another instruction's operand bytes; the class must satisfy JVM structural and verification rules. Nor is this "jumping to line 7 of the Java file".

## 3. Common Groups of Branch Instructions

| Group | Common Instructions | Operands Checked |
| --- | --- | --- |
| Compare with 0 | `ifeq`, `ifne`, `iflt`, `ifle`, `ifgt`, `ifge` | Pops **one int value** from the operand stack to compare with 0 |
| Compare two ints | `if_icmpeq`, `if_icmpne`, `if_icmplt`, `if_icmple`, `if_icmpgt`, `if_icmpge` | Pops **two int values**, compares relationally |
| Compare two references | `if_acmpeq`, `if_acmpne` | Checks whether two references refer to the same object or are both null |
| Compare with null | `ifnull`, `ifnonnull` | Pops one reference and checks for null |
| Unconditional jump | `goto`, `goto_w` | Uses no condition on the stack |
| Multi-way selection | `tableswitch`, `lookupswitch` | Pops one int key, selects matching target |

`if*` instructions **pop operands off the operand stack** to check them, so the stack state after the check has changed. The compiler usually must place value-loading instructions such as `iload`, `aload`, `iconst`, or corresponding computations before the branch instruction.

Note common misconceptions:

- `ifeq` means **jump when int equals 0**, not "the source if is true". If the source writes `if (flag)`, the compiler may use `ifeq` to **skip the if body when flag is false**.
- `if_icmp*` compares two `int`s, not all numeric types. For `long`, the JVM typically uses `lcmp` before a compare-with-0 branch; for `float`/`double`, there are `fcmpl`, `fcmpg`, `dcmpl`, `dcmpg` with specific rules for NaN.
- `if_acmp*` compares **reference identity**, not calling `equals()`. Two `String`s that are different objects with the same content can be `false` when compared with `==`.
- `ifnull`/`ifnonnull` operate on a reference value; `null` is not an object that can be dereferenced.
- Bytecode `goto` is a tool for implementing JVM control flow; **it does not prove the Java source has a goto statement**. Java has no `goto` statement; the `goto` keyword is reserved but unused.

## 4. Minimal Example: How Does an `if` Become a Branch?

Java source:

~~~java
static int absoluteLike(int number) {
    if (number < 0) {
        return -number;
    }
    return number;
}
~~~

A typical bytecode sequence generated by `javac` is:

~~~text
0: iload_0
1: ifge          7
4: iload_0
5: ineg
6: ireturn
7: iload_0
8: ireturn
~~~

This is **one illustrative compilation**; run `javap` on an actual class to see the offsets and instructions of the compiler you are using.

Step-by-step analysis:

1. `iload_0` pushes `number` onto the operand stack.
2. `ifge 7` pops `number` from the stack and jumps to offset 7 **if number ≥ 0**, i.e., **inverting the condition** to skip the negative-number branch.
3. If `number < 0`, the JVM continues at offset 4, loads `number` again, executes `ineg`, and then `ireturn`.
4. If `number ≥ 0`, the JVM reaches offset 7, loads `number`, and executes `ireturn`.

The source condition `number < 0` does not have to appear as an `iflt` instruction. The compiler uses `ifge` because that is the condition to **jump out of the true branch**.

A note on math: the value `Integer.MIN_VALUE` has no positive opposite representable as an `int`; `-number` on `int` produces that same value due to overflow under Java rules. The example focuses on bytecode branching, not implementing a safe absolute value function for every `int`.

## 5. Loops = Forward Branches, Backward Branches, and Check Points

A **backward branch** is a branch whose target offset is **less than** the jump opcode's offset: that is the link pattern commonly appearing in loops. However, the essence of a loop is a **cycle in the control-flow graph (CFG)**, not necessarily always having a single backward `goto` instruction.

### 5.1. While

Source:

~~~java
int i = 0;
while (i < 3) {
    i++;
}
~~~

CFG model:

~~~text
      [initialize i = 0]
              |
              v
       [check i < 3] ------- false -----> [after loop]
              |
             true
              v
         [increment i]
              |
              +----------- jump back to check
~~~

A simplified bytecode form, with offsets for illustration only:

~~~text
0: iconst_0
1: istore_1
2: iload_1
3: iconst_3
4: if_icmpge     13
7: iinc          1, 1
10: goto         2
13: ...          ; instruction after loop
~~~

The `if_icmpge` instruction jumps **forward** past the body when the condition `i < 3` is false. `goto 2` jumps **backward** to the check position, creating a cycle.

**Do not memorize these offsets as real output**: the compiler may change code generation depending on context, version, code after the loop, and optimizations. When analyzing a real class, offsets must be taken directly from `javap -c`.

### 5.2. Do-while

In `do { body } while (condition);`, the body must run **at least once**. The compiler usually places **the body before the check**, then uses a backward conditional branch if the condition is still true. This explains why sometimes there is only a single backward conditional branch, without needing a separate backward `goto`.

### 5.3. For

For `for (initialization; condition; update) { body }`, the logical flow is:

~~~text
initialization
      |
      v
  condition ----- false -----> exit
      |
     true
      v
     body
      |
      v
    update
      |
      +----------------------> condition
~~~

Initialization happens once, condition before each iteration (if present), and update after each iteration finishes normally or when `continue` transfers to update. The compiler may use `iinc` for `i++`, though this is just an optimization choice for certain local `int` variables.

A `for (;;)` without a condition can become a backedge cycle without a direct exit branch, unless the body contains `break`, `return`, `throw`, or another control event.

### 5.4. `break` and `continue` Correspond to Different Targets

In Java loops:

- `break` usually transfers control to **the point after the loop**.
- `continue` transfers control to **the update execution point** in `for`, or **the condition check point** of `while`/`do-while`.
- With **labeled break/continue**, the target must correspond to the labeled statement/loop according to Java semantics. It does not always jump to the innermost loop.
- If `break`/`continue` exits a `try/finally` region, the compiler must execute the appropriate `finally` semantics; it cannot be modeled by a single `goto` that skips cleanup.

Do not conflate `break` in a `switch` statement with `break` exiting a loop; they control different statements. `switch` expressions with arrow/`yield` also have their own source rules.

## 6. `tableswitch` and `lookupswitch`: Selecting Among Multiple Target Addresses

For multiple choices on a suitable `int` key, the compiler can use one of the two JVM switch instructions.

### 6.1. `tableswitch`

`tableswitch` represents targets corresponding to a **contiguous range of keys** from `low` to `high`, along with a default target. Each key in the range has an offset (if the source does not declare a corresponding case, the compiler can still have that entry jump to default).

Conceptual structure:

~~~text
tableswitch
    default_offset
    low
    high
    jump_offsets[high - low + 1]
~~~

It is suitable for relatively dense `case` values; a range that is too wide and sparse can make the table waste bytecode.

### 6.2. `lookupswitch`

`lookupswitch` stores a list of **match-offset pairs** for specific keys, along with default:

~~~text
lookupswitch
    default_offset
    npairs
    (match_1, offset_1)
    (match_2, offset_2)
    ...
~~~

The `match` list is sorted in ascending order per the class-file format rules. This can be a more compact choice when cases are sparse (for example 1, 1000, 1000000).

### 6.3. What the Two Instructions Have in Common

- They pop an `int` key from the operand stack and then select a branch.
- Switch target offsets are stored as **signed 32-bit**, calculated **relative to the offset of the `tableswitch`/`lookupswitch` opcode**, not from the entry position in the table.
- The switch data fields require **padding so that the data fields start on a 4-byte boundary** from the start of the `code[]` array. Therefore, a `tableswitch` or `lookupswitch` has a byte length that varies with the opcode's position.
- `javap -c` output prints the final targets as PCs and usually displays `default:` / `case:`, without requiring the reader to add offsets by hand.
- The compiler is **not required** to use `tableswitch` for every dense switch or `lookupswitch` for every sparse switch. The selection policy is a compiler detail; a switch with `String` or certain source constructs may use hash/equals or a chain of comparisons combined with other instructions.

Java example:

~~~java
static String classify(int value) {
    return switch (value) {
        case 0 -> "ZERO";
        case 1, 2 -> "SMALL";
        default -> "OTHER";
    };
}
~~~

When viewing `javap -c`, pay attention to the shared target for case 1 and 2, the default branch, and where the String is returned. This is a multi-choice example, but how the compiler lowers `switch` **is not guaranteed** to be a specific switch opcode.

## 7. Java 17+ Practice: Multiple Control Structures in One File

Create the file **`BranchFlowDemo.java`**:

~~~java
public final class BranchFlowDemo {
    static int absoluteLike(int number) {
        if (number < 0) {
            return -number;
        }
        return number;
    }

    static String grade(int score) {
        if (score < 0) {
            return "INVALID";
        }
        if (score >= 80) {
            return "HIGH";
        }
        return "NORMAL";
    }

    static int sumEvenUntilSeven(int limit) {
        int sum = 0;
        for (int i = 0; i < limit; i++) {
            if ((i & 1) != 0) {
                continue;
            }
            if (i > 6) {
                break;
            }
            sum += i;
        }
        return sum;
    }

    static int countDown(int start) {
        int remaining = start;
        while (remaining > 0) {
            remaining--;
        }
        return remaining;
    }

    static String classify(int code) {
        return switch (code) {
            case 0 -> "ZERO";
            case 1, 2 -> "SMALL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("abs=" + absoluteLike(-3));
        System.out.println("grade=" + grade(85));
        System.out.println("sum=" + sumEvenUntilSeven(10));
        System.out.println("remaining=" + countDown(3));
        System.out.println("kind0=" + classify(0));
        System.out.println("kind2=" + classify(2));
        System.out.println("kind9=" + classify(9));
    }
}
~~~

Compile and run with JDK 17+ from the directory containing the file:

~~~bash
javac --release 17 BranchFlowDemo.java
java BranchFlowDemo
~~~

**Expected stdout determined by the program:**

~~~text
abs=3
grade=HIGH
sum=12
remaining=0
kind0=ZERO
kind2=SMALL
kind9=OTHER
~~~

Quick check:

- `absoluteLike(-3)` returns 3 via the negative-number branch.
- `grade(85)` falls into the `score >= 80` branch, returning `HIGH`.
- In `sumEvenUntilSeven(10)`, odd numbers are skipped by `continue`; summing 0 + 2 + 4 + 6 = **12**; at i = 8, `break` exits the loop.
- `countDown(3)` decrements to 0 and then exits because `remaining > 0` is false.
- `classify` returns the right string for case 0, case 1/2, and default.

### Using `javap` to Observe Actual Branches

~~~bash
javap -classpath . -c -p BranchFlowDemo
javap -classpath . -v -p BranchFlowDemo
~~~

Read each method as follows:

1. Locate the `Code:` block of `absoluteLike`; find `ifge` or an equivalent conditional branch and then the `ireturn` instructions.
2. In `grade`, notice multiple conditions and reference-type return instructions such as `areturn`.
3. In `sumEvenUntilSeven`, find the `for` condition, the branch skipping odd numbers, the exit branch when `i > 6`, and the backedge. Connect `continue` with the path to the next update/check.
4. In `countDown`, find the stopping check and backedge, and also see whether the compiler puts the condition at the start or uses another layout.
5. In `classify`, observe whether the compiler chooses `tableswitch` or `lookupswitch` or a branch chain; do not infer the choice from the source without checking.
6. With `-v`, also inspect `StackMapTable` (if present), `LineNumberTable`, and class-file version data. A class compiled with `--release 17` has **major version 61**.

An additional exercise is to compile separately with `-g:none` and compare `javap -c` output with `javap -l`: removing debug line/local metadata **does not remove the control branches needed for the program to run**.

## 8. Reading a Control-Flow Graph (CFG) from Bytecode

A **basic block** is a sequence of instructions with a single entry point and no internal branching, ending with a control-transfer instruction or at the position before a branch target. You can construct a CFG from `javap`:

1. Take **entry PC = 0** for a method with code.
2. Find the targets of `if*`, `goto`, `tableswitch`, `lookupswitch`, and the continuation points after conditional branches.
3. Split basic blocks at the start of the method, at targets, and at the instruction following places where control flow can branch.
4. Connect **conditional true**, **fall-through**, **unconditional goto**, and switch/default selection edges. `return` ends a normal execution path.
5. Find paths returning to existing blocks to identify loops; find blocks where multiple branches converge to understand shared continuation.
6. When analyzing real programs, add **exceptional control flow** from `exception_table`; code throwing an exception can transfer to a handler without going through a normal `goto` instruction.

Minimal CFG example:

~~~text
PC 0: [load x; test x]
          |
          +-- true ---> PC 8: [return A]
          |
          +-- false --> PC 4: [return B]
~~~

The PC numbers are only example offset labels. If you see a path `PC 20 -> PC 4`, you recognize a **backedge**, but you cannot yet assert whether the source used `for`, `while`, or `do-while`; different constructs can produce similar CFGs.

### Branch Conditions Are Not "a Boolean Result on the Stack" in All Cases

A source expression like `a < b` can be implemented by the compiler with `iload` of two variables and an inverted `if_icmpge` to skip the body, **without necessarily pushing a Boolean object** or a temporary boolean value first before checking. That helps you read code more effectively: observe **the instruction sequence that pops operands and jumps**, rather than trying to find a `Boolean` object for every conditional expression.

## 9. `&&`, `||`, and Short-Circuiting

The Java language has short-circuiting:

- `a && b`: if `a` is false, **do not evaluate `b`**.
- `a || b`: if `a` is true, **do not evaluate `b`**.

The compiler can use multiple consecutive branches to enforce the correct order and avoid unnecessary side effects. Example:

~~~java
static boolean allowed(String value) {
    return value != null && !value.isEmpty();
}
~~~

The condition `value != null` must be handled first, and when `value == null`, the call `value.isEmpty()` **is not executed**. In bytecode, you may see `ifnull` or an equivalent branch transferring to the false-returning path before the `invokevirtual` instruction of `isEmpty`.

Therefore, if you want to analyze the behavior of a complex expression, identify the actual branch paths and call order, not just count `if` instructions.

## 10. Branch Offset Limits and `goto_w`

Most ordinary conditional branches and `goto` use a **signed 16-bit relative offset**, with a range from -32768 to +32767 relative to the opcode's bytecode PC. When the target is outside this range:

- `goto_w` uses a **signed 32-bit branch offset** to jump unconditionally to a farther target.
- There is no general `if_w` opcode pair for every condition. The compiler can **invert the condition** to jump over a `goto_w`, thereby still representing a long conditional branch.
- How the compiler implements this depends on method size and tooling; do not infer that a `goto_w` instruction appears because the Java source has a special construct.
- A method has a `code[]` length limit per the class-file format (at most **65535 bytes** in the relevant class file versions), so a method cannot have infinitely long bytecode. The compiler may report an error when a method is too large; using `goto_w` does not remove the method size limit.

Illustrative example of transforming for a long jump:

~~~text
Intended condition: if x == 0 then jump to TARGET_FAR

Form the compiler may transform into:
    ifne AFTER
    goto_w TARGET_FAR
AFTER:
    ...           ; continue when x != 0
~~~

This is **control pseudocode**, not fixed `javap` output; the labels `AFTER`, `TARGET_FAR` only help learners understand how condition inversion works.

### Historical Instructions

The JVM also has `jsr`, `jsr_w`, and `ret`, which were once used with bytecode subroutines for `finally` in older compilers. They **are not** how normal Java loops are represented; for modern class-file versions, verifier constraints have caused modern Java compilers not to use this historical subroutine model. When you see old documentation with `jsr`/`ret`, distinguish them from `goto` and modern Java compilers.

## 11. Verification, `StackMapTable`, and Safe Branch Targets

The JVM verifier does not only check whether opcodes are supported. It must verify conditions so that instructions using the operand stack/local variables are consistent at reachable control points.

For example: a block receiving control from two branches must have **valid and compatible** operand stack/local variable type states according to verification rules. If one branch leaves an int on the stack while another path brings a reference to the same point where the code expects to read an int, the class file may fail verification.

**`StackMapTable`** (in modern class-file versions where applicable) contains frames that support type checking at relevant locations. This is metadata for **verification**, distinct from `LineNumberTable` which supports source line mapping:

- You cannot just edit two branch offset bytes and trust that the class will run; targets, stack frames, instruction lengths, and control-flow metadata must be consistent.
- Jumping into the middle of an instruction/operand is invalid.
- Targets belong within the `Code` scope of the **same method**; to call another method you must use an invoke instruction, not `goto` to "jump" directly into another method.
- `StackMapTable` does not describe the verbatim order of source `if`/loop statements. It supports type consistency checking of the generated bytecode.

Besides branch instructions, there is also the **exception table** in `Code`, with `start_pc`, `end_pc`, `handler_pc`, and catch type values. These fields are **PC indices in the code array**, not all signed relative offsets like `goto` operands. An exception can transfer control to a handler even though there is no explicit `goto` to it in the bytecode.

## 12. Target Addresses in `javap` Are Neither Machine Addresses Nor Source Lines

There are at least four kinds of numbers that commonly appear when analyzing a class file:

| Value | What Does It Number? | Purpose |
| --- | --- | --- |
| Bytecode offset/PC | Instruction position in the **method**'s `code[]` | `javap -c` displays instructions and targets |
| Branch offset | Relative byte displacement of target from jump opcode PC | Operand of `if*`, `goto`, `switch` |
| Source line number | `.java` text line recorded by the compiler in `LineNumberTable` | Breakpoints, stack traces, debugging |
| Native/virtual memory address | Location in process address space or JIT-generated code | Implementation/runtime detail, not `javap -c` labels |

For example, a disassembly line `10: goto 2` says that **the instruction at bytecode PC 10 transfers to bytecode PC 2** in the same method. It does **not** mean "jump to source line 2", "access RAM address 0x2", or "go to the 2nd instruction". If the bytecode is being JIT-optimized into native machine code, native instruction positions are completely different from this bytecode PC coordinate system.

A program can run with a class file whose debug metadata has been stripped so it has no `LineNumberTable`, yet `goto` branches and bytecode offsets are still present because the JVM needs them to execute. This is direct evidence that **bytecode control flow** and **source-line mapping** are two separate layers of information.

## 13. Common Misconceptions

1. **"`ifeq` means the source if is true."** False. It jumps when the int operand equals 0; the compiler often uses it to skip the body when the source condition is false.
2. **"`goto 12` jumps to line 12 in Java."** False. It is bytecode PC 12 of the same method.
3. **"Branch offset is calculated from after the `goto` instruction."** False. JVM branch offsets are calculated from **the PC of the opcode itself**.
4. **"A loop must always have a backward `goto`."** False. A CFG can have a conditional backedge, or the compiler can arrange conditions and jumps differently.
5. **"`break` only needs to skip the next instruction."** False. It transfers control to the right target and must still respect `finally` semantics when present.
6. **"`continue` in a for loop always goes back to the start of the body."** False. It goes to the update/check as defined by the `for` structure.
7. **"`if_acmpeq` calls `equals()`."** False. It compares reference identity.
8. **"`tableswitch` has offsets calculated from the start of the case table."** False. Relative offsets are calculated from **the switch opcode PC**.
9. **"Every Java switch is a `tableswitch`."** False. The compiler can choose `lookupswitch` or another mechanism.
10. **"Jumping to any byte in `code[]` is fine."** False. Targets and stack state must be valid under verification.
11. **"Line 20 in `LineNumberTable` is PC 20."** False. Line numbers and bytecode offsets are two different quantities.
12. **"Java source has the `goto` keyword to invoke JVM goto."** False. Java reserves the word `goto` but has no valid `goto` statement.

## 14. Self-Check Questions and Exercises

1. `ifge` at PC 4 jumps to PC 16. What is the relative offset operand? **+12**, because it is calculated from opcode PC = 4.
2. `goto` at PC 20 jumps back to PC 5. What is the offset? **-15**; this is a backward branch.
3. What will `ifeq` do when it sees int 0? **Jump to target**; if nonzero, fall through.
4. Can an `if (x > 0)` compile into `ifle`? **Yes**, if `ifle` is used to skip the body when the source condition is false.
5. Does `if_acmpeq` compare `String.equals()` or reference identity? **Compares identity**.
6. Why does `continue` in `for (init; test; update)` usually lead to `update`? Because that is the next step under `for` semantics, before the next test.
7. Why is `tableswitch` usually efficient for dense key ranges and `lookupswitch` more suitable for sparse keys? Because **a contiguous target table** differs from **a list of match/offset pairs**.
8. Is `StackMapTable` another name for `LineNumberTable`? **No**; one table serves type verification, and the other serves source line mapping.
9. If `javap -c` displays `0: iload_0`, `1: ifge 7`, `4: iload_0`, why is the next PC 4? Because `ifge` is 3 bytes long, not 1 byte.
10. Why can a decompiler not be certain whether the source used `for` or `while` from a backedge alone? Because multiple source constructs can produce **equivalent CFG/bytecode**.

## 15. Specification References

- JVM Specification Java SE 17, chapter **Instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- JVMS, chapter **The Class File Format**, `Code` and `StackMapTable` structures: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS, chapter **Verification**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10
- JDK 17 `javap` documentation: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Java Language Specification Java SE 17, section **Statements**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html

**Technical conclusion:** `if*`, `goto`, `goto_w`, `tableswitch`, and `lookupswitch` describe **control-flow edges between bytecode positions within the same method**. Conditional branches inspect the operand stack, `goto` jumps unconditionally, and loops create cycles in the CFG. Target addresses are computed from **bytecode PCs and signed relative offsets**, not Java line numbers or physical memory addresses. When reading disassembly, always trace operands, targets, and stack state to understand exactly which path the JVM executes.
