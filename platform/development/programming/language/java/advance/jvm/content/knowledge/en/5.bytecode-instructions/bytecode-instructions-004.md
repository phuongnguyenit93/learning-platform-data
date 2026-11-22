# The `pop`, `dup`, `swap` Instruction Group and Value Size Constraints in the JVM

The Java Virtual Machine (JVM) uses an **operand stack** in each stack frame to hold operands and intermediate results when executing bytecode. The instructions `pop`, `pop2`, `dup`, `dup_x1`, `dup_x2`, `dup2`, `dup2_x1`, `dup2_x2`, and `swap` change the **order or number of copies of values** on the operand stack. They do not directly add numbers, invoke methods, or allocate objects.

Most importantly: these opcodes must respect the **computational type category**. A `long` or `double` value belongs to **category 2**, while `int`, `float`, and reference belong to **category 1**. Therefore, `pop` cannot directly remove a `long`; `swap` does not swap a `double` with an `int`; and `dup2` can duplicate **one category 2 value or two category 1 values**.

## 1. The operand stack belongs to a single method invocation

When the JVM executes a method, it has its own frame consisting of **local variables**, an **operand stack**, and auxiliary information. Bytecode reads local variables or creates constants and pushes values onto the operand stack; another instruction can pop the top values to compute, invoke a method, or write a field.

```text
Frame model (not physical RAM layout)

Local variables              Operand stack
slot 0: int a = 2             TOP ┌───────────────┐
slot 1: int b = 3                 │      3        │ ← top value
                                 ├───────────────┤
                                 │      2        │
                                 └───────────────┘
                                      bottom

iload_0   → push 2
iload_1   → push 3
iadd      → pop two ints, push 5
```

Diagrams in this article read the stack in order **from left to right = from bottom to top**:

```text
..., value3, value2, value1
                        ↑
                       TOP
```

The `...` represents the deeper part of the stack that is not modified by the instruction. `value1` is always the top value before the operation. The names `value1`, `value2` represent **logical values**, not Java variable names or physical bytes.

**`pop` of the operand stack is different from `Stack.pop()` in Java Collections.** Here we are studying JVM instructions from class files. There is no standard Java method `dup()` or `swap()` for programmers to manipulate the operand stack directly in Java source code. The compiler chooses bytecode based on the source structure.

## 2. Category 1 and category 2: the rule determining valid instructions

| Value type on operand stack | Category | Width in stack model | Example |
| --- | --- | --- | --- |
| `int` | 1 | 1 stack unit (slot/word in the model) | `42`, many operations with `byte`, `short`, `char`, `boolean` |
| `float` | 1 | 1 unit | `2.5f` |
| Reference | 1 | 1 unit | `String`, object, array references, including `null` |
| `long` | 2 | 2 units | `42L` |
| `double` | 2 | 2 units | `2.5d` |
| Historical `returnAddress` | 1 | 1 unit | Associated with `jsr`/`ret`, no corresponding Java declared type |

**Category is a concept of the JVM instruction set**, not an assertion that a reference in a 64-bit JVM necessarily occupies 4 or 8 bytes in RAM. The primitive types `byte`, `short`, `char` usually go through computations in `int` form; `boolean` has no independent arithmetic instruction set. Nor can one conclude that an object "lives on the stack": the operand stack holds a **reference value** to the object, not the entire object in the sense of copying all its fields.

Distinguish two ways of counting:

- **Number of logical values**: a `long` is **one value**, two `int`s are **two values**.
- **Number of width units**: one `long` occupies **two units**; two `int`s also total **two units**.

This is why `pop2` and `dup2` have two valid usage forms. The suffix `2` expresses the **total width by category**, not always "two objects" or "two values".

## 3. `pop` and `pop2`: discarding unused results

### `pop` — discard exactly one category 1 value

```text
Before: ..., value1
After:  ...

Condition: value1 is category 1.
Opcode: pop (0x57)
```

Valid example: discarding an `int`, `float`, or reference just placed on the stack. **Invalid** if `value1` is `long` or `double`, because they are category 2.

### `pop2` — discard a total of two width units

```text
Form 1: two category 1 values
Before: ..., value2(cat1), value1(cat1)
After:  ...

Form 2: one category 2 value
Before: ..., value(cat2)
After:  ...

Opcode: pop2 (0x58)
```

`pop2` is not used to take the "upper half" of a `long` or `double`. Category 2 is always **a single value that cannot be split in half** by this instruction group.

### Situations where the compiler uses `pop` and `pop2`

In Java source, calling a method that returns a value and **not using the result** is valid:

```java
intResult();    // discard the returned int value
longResult();   // discard the returned long value
```

These are **illustrative lines placed inside a method that has appropriate definitions of `intResult()` and `longResult()`**, not a standalone runnable program. With bytecode generated by typical `javac`, a call returning `int` is followed by `pop`, while a call returning `long` is followed by `pop2`. In the case of a method returning `void`, there is no return value to discard with `pop`.

```text
invokestatic ... intResult:()I
pop
invokestatic ... longResult:()J
pop2
```

The `...` stands for indices/names in the constant pool; this is a **bytecode illustration**, not a listing that must match every compiler identically.

## 4. `dup` and `dup2`: duplicating values on the stack

### `dup` — duplicate exactly one category 1 value

```text
Before: ..., value1(cat1)
After:  ..., value1, value1

Opcode: dup (0x59)
```

`dup` cannot be used directly with `long` or `double`. If `value1` is a **reference**, the two stack positions after `dup` hold two **copies of the reference value pointing to the same object**, without creating a second object. If `value1` is an `int`, the two positions hold the same numeric value at the time of the operation.

A common compiler pattern when handling the expression `new Box()`:

```text
new Box
dup
invokespecial Box.<init>:()V
```

This is **illustrative** bytecode. `new` pushes a reference to an object currently in an uninitialized state; `dup` keeps an extra copy so that after `invokespecial` invokes the constructor, the expression still has the resulting reference to use. The verifier also tracks the uninitialized reference state and constructor constraints. The sequence above should not be viewed as a way to arbitrarily use an uninitialized object.

### `dup2` — duplicate two category 1 values or one category 2 value

```text
Form 1 (two cat1):
Before: ..., value2(cat1), value1(cat1)
After:  ..., value2, value1, value2, value1

Form 2 (one cat2):
Before: ..., value(cat2)
After:  ..., value, value

Opcode: dup2 (0x5C)
```

For two category 1 values, `dup2` **preserves the order** of the duplicated pair. For one `long`, it creates two copies of the **entire `long` value**, not four independent values.

`dup`/`dup2` often appear when the compiler needs to keep the value of an expression for **two purposes**: both assigning it to a field/array element and letting the assignment expression produce a result; or both using it as an operand of the next instruction and keeping a copy for the return result. One must not conclude that the source performs a deep copy of an object solely from a `dup` opcode.

## 5. `swap`: swapping the positions of two category 1 values

```text
Before: ..., value2(cat1), value1(cat1)
After:  ..., value1, value2

Opcode: swap (0x5F)
```

**Both values must be category 1.** The following cases are invalid for `swap`:

```text
..., long(cat2), int(cat1)    → cannot swap
..., int(cat1), double(cat2) → cannot swap
..., long(cat2), long(cat2)  → cannot swap
```

A reference is category 1, so it can participate in `swap` with an `int` if the reordering also satisfies the type requirements of subsequent instructions. However, **being valid by category alone is not enough for the entire method to be valid**: the verifier also checks actual types, control flow, and subsequent uses.

When it is necessary to rearrange a stack containing `long`/`double`, the compiler can use a combination of local variable load/store instructions or valid `dup*_x*` forms, depending on the context. There is no standard `swap2` opcode in the JVM instruction set to simply "swap any pair of 64-bit values".

## 6. Why do `dup_x1`, `dup_x2`, `dup2_x1`, `dup2_x2` exist?

`dup` or `dup2` only creates copies **right at the top**. For complex assignment expressions, the compiler may need to **place the copy underneath other operands** already on the operand stack. The group with `_x1`/`_x2` suffixes serves that purpose.

Diagram reading conventions:

- **cat1**: category 1 value (one unit).
- **cat2**: category 2 value (two units).
- `value1`: top of the operand stack before the instruction.
- `→`: stack change; the right-hand side is still written in **bottom → top** order.
- Values not shown in the diagram (the `...` part) remain unchanged.

### 6.1. `dup_x1`: one valid form

Requires **both top values to be category 1**.

```text
..., value2(cat1), value1(cat1)
→
..., value1, value2, value1

Opcode: dup_x1 (0x5A)
```

It duplicates `value1` and **inserts the copy beneath `value2`**. If `value2` is a `double`, `dup_x1` cannot be used.

### 6.2. `dup_x2`: two valid forms

```text
Form 1: three cat1
..., value3(cat1), value2(cat1), value1(cat1)
→
..., value1, value3, value2, value1

Form 2: one cat2 beneath one cat1
..., value2(cat2), value1(cat1)
→
..., value1, value2, value1

Opcode: dup_x2 (0x5B)
```

The duplicated value is always the **top `value1` of category 1**. The two units beneath it can be **two cat1** or **one cat2**. You cannot replace `value1` with a `long` and assume the `x2` suffix will automatically make it valid.

### 6.3. `dup2_x1`: two valid forms

```text
Form 1: three cat1
..., value3(cat1), value2(cat1), value1(cat1)
→
..., value2, value1, value3, value2, value1

Form 2: one cat1 beneath one cat2
..., value2(cat1), value1(cat2)
→
..., value1, value2, value1

Opcode: dup2_x1 (0x5D)
```

In form 1, it duplicates the **pair** `value2, value1` (both cat1). In form 2, it duplicates **one cat2 value** `value1`. They are inserted beneath `value3` or `value2` respectively; the order within the duplicated pair is not swapped.

### 6.4. `dup2_x2`: four valid forms

This is the easiest case to get wrong; you need to **read the category of each value** before drawing the stack.

```text
Form 1: four cat1
..., value4(cat1), value3(cat1), value2(cat1), value1(cat1)
→
..., value2, value1, value4, value3, value2, value1

Form 2: two cat1 beneath one cat2
..., value3(cat1), value2(cat1), value1(cat2)
→
..., value1, value3, value2, value1

Form 3: one cat2 beneath two cat1
..., value3(cat2), value2(cat1), value1(cat1)
→
..., value2, value1, value3, value2, value1

Form 4: two cat2
..., value2(cat2), value1(cat2)
→
..., value1, value2, value1

Opcode: dup2_x2 (0x5E)
```

Similar to `dup2`, the duplicated part at the top has a total width of **two units**: **two cat1** or **one cat2**. The part beneath also has a total width of **two units**: two cat1 or one cat2. The four valid combinations produce the **four forms** above.

### Summary table of opcodes and conditions

| Instruction | Opcode (hex) | Required top part | Meaning |
| --- | --- | --- | --- |
| `pop` | `57` | 1 cat1 | Discard one value |
| `pop2` | `58` | 2 cat1 **or** 1 cat2 | Discard two units |
| `dup` | `59` | 1 cat1 | Duplicate top |
| `dup_x1` | `5A` | 2 cat1 | Duplicate top beneath one cat1 |
| `dup_x2` | `5B` | 3 cat1 **or** cat2 + cat1 | Duplicate top beneath two units |
| `dup2` | `5C` | 2 cat1 **or** 1 cat2 | Duplicate top two units |
| `dup2_x1` | `5D` | 3 cat1 **or** cat1 + cat2 | Duplicate top two units, insert beneath one cat1 |
| `dup2_x2` | `5E` | Four forms in section 6.4 | Duplicate top two units, insert beneath two units |
| `swap` | `5F` | 2 cat1 | Swap the order of two values |

**Note:** the expression "two units" is the width in the JVM model, not the number of elements in a collection, number of bytes, or an operation on two Java variables. The orders in the condition table are read **from bottom to top**, while the full diagrams determine exactly where `value1` is located.

## 7. Valid and invalid cases: deducing by category

Suppose the stack has the following values; the numbers are only to distinguish values, not bytecode opcodes:

| Stack before instruction (bottom → top) | Instruction | Result / reason |
| --- | --- | --- |
| `..., int(7)` | `dup` | `..., 7, 7`, valid |
| `..., long(7L)` | `dup` | **Invalid**: top is cat2 |
| `..., long(7L)` | `dup2` | `..., 7L, 7L`, valid |
| `..., int(1), int(2)` | `dup2` | `..., 1, 2, 1, 2`, valid |
| `..., double(2.0)` | `pop` | **Invalid**: top is cat2 |
| `..., double(2.0)` | `pop2` | `...`, valid |
| `..., int(1), long(2L)` | `pop2` | `..., 1`, valid because only the top long is popped |
| `..., long(1L), int(2)` | `pop2` | **Invalid**: cannot pop top int and half of a long |
| `..., int(1), float(2f)` | `swap` | `..., 2f, 1`, valid by category |
| `..., int(1), long(2L)` | `swap` | **Invalid**: one operand is cat2 |
| `..., long(1L), int(2)` | `dup_x2` | `..., 2, 1L, 2`, form 2 |
| `..., int(1), long(2L)` | `dup2_x1` | `..., 2L, 1, 2L`, form 2 |

A common point of confusion with `pop2`: if the top is cat2, the instruction **only discards that one value**, regardless of how many cat1 values are beneath it. If the top is cat1 but directly beneath it is cat2, there is no valid form for `pop2` because a second cat1 at the top is missing.

A cat2 value cannot be treated as two cat1 values by calling `pop` twice. Category 2 is an indivisible unit for these instructions. The JVM specification defines the valid stack forms, and the **bytecode verifier** relies on type forms during verification.

## 8. Why does `javac` need these instructions?

In Java source, an assignment can simultaneously **affect the storage location** and **return the expression value**. For example, `int y = (x = 5);`: the assignment `x = 5` must leave a value behind to assign to `y`. The compiler can keep a copy of the value on the operand stack instead of reloading it from local variables.

For assignments to a field or array, the stack order also includes the **object/array reference**, index, and new value. The variants `dup_x1`, `dup_x2`, `dup2_x1`, `dup2_x2` allow the compiler to keep a copy of the expression result **beneath** the operands that `putfield` or `xastore` need to consume.

### Conceptual example: updating a field while keeping the value

Suppose inside a valid method there is:

```java
Box box = new Box();
int result = (box.value = 9);
```

In a typical compilation strategy, before `putfield` there are `objectref` and `int value` on the stack. However, the assignment expression also needs the result `9`, so the compiler can use `dup_x1`:

```text
Before: ..., objectref(cat1), value=9(cat1)
dup_x1:
        ..., 9, objectref, 9
putfield Box.value:I:
        ..., 9            // copy used as the expression result
```

`Box` and `value` here are hypothetical types/fields for the illustration; a complete runnable example is in section 9. The diagram only presents a **reasonable compilation pattern**, not requiring every compiler or JIT to keep these exact intermediate instructions.

### Conceptual example: assigning an array element

To execute `result = (numbers[index] = 9)`, `iastore` needs three operands:

```text
..., arrayref(cat1), index(cat1), value=9(cat1)
```

The compiler can use `dup_x2` (form 1) to keep a copy of `9`:

```text
Before:    ..., arrayref, index, 9
dup_x2:    ..., 9, arrayref, index, 9
iastore:   ..., 9
```

If the element value is `long` (cat2), such as `long[]`, keeping a copy of the wide value and inserting it beneath `arrayref`, `index` (two cat1) can use **`dup2_x2` form 2**:

```text
Before:     ..., arrayref(cat1), index(cat1), value(cat2)
dup2_x2:    ..., value(cat2), arrayref, index, value(cat2)
lastore:    ..., value(cat2)
```

Thus the difference between `dup_x2` and `dup2_x2` stems from the **category of the element value**, not the array size or the number of parentheses in the source.

## 9. Java 17+ Practice: generating bytecode and reading with `javap`

Create **one file** `StackInstructionDemo.java` with the following content:

```java
public class StackInstructionDemo {
    static class Box {
        int value;
    }

    static int intResult() {
        return 7;
    }

    static long longResult() {
        return 9L;
    }

    static int assignedField(Box box) {
        int result = (box.value = 12);
        return result;
    }

    static int assignedElement(int[] numbers, int index) {
        int result = (numbers[index] = 21);
        return result;
    }

    static long assignedLongElement(long[] numbers, int index) {
        long result = (numbers[index] = 34L);
        return result;
    }

    public static void main(String[] args) {
        intResult();
        longResult();

        Box box = new Box();
        int[] numbers = new int[1];
        long[] longNumbers = new long[1];

        System.out.println("field: " + assignedField(box));
        System.out.println("element: " + assignedElement(numbers, 0));
        System.out.println("long element: "
                + assignedLongElement(longNumbers, 0));
        System.out.println("stored: " + box.value
                + ", " + numbers[0] + ", " + longNumbers[0]);
    }
}
```

From the directory containing the file, using JDK 17 or newer:

```bash
javac -encoding UTF-8 StackInstructionDemo.java
java StackInstructionDemo
```

**Exact standard output:**

```text
field: 12
element: 21
long element: 34
stored: 12, 21, 34
```

The methods only return the assigned value, without using complex execution flows or wall-clock time, so the four stdout lines do not depend on JIT. `intResult()` and `longResult()` have no observable side effects in the source; however, the compiler generates bytecode from normal method invocations and may have to discard unused return values.

### 9.1. Viewing instructions in the class file

```bash
javap -c -p StackInstructionDemo
javap -c -p 'StackInstructionDemo$Box'
```

In **Bash** and **PowerShell**, single quotes protect the `$` character in the nested class name; with **Windows cmd.exe**, use double quotes instead. The second command is optional to inspect the `Box` class.

Look for the bytecode snippets, **without needing exact matches for offsets or constant pool indices**:

| Method | Instructions to observe | Why they may appear |
| --- | --- | --- |
| `main` | `invokestatic ... intResult`, `pop` | Discard unused `int` value |
| `main` | `invokestatic ... longResult`, `pop2` | Discard unused `long` value |
| `main` | `new`, `dup`, `invokespecial ... Box.<init>` | Keep object reference when invoking constructor |
| `assignedField` | `dup_x1`, `putfield` | Keep assigned `int` value while writing field |
| `assignedElement` | `dup_x2`, `iastore` | Keep assigned `int` value while writing array element |
| `assignedLongElement` | `dup2_x2`, `lastore` | Keep assigned `long` (cat2) value while writing array element |

**You should read the `javap` output on the actual tool.** The instructions in the table are typical `javac` patterns for this code, but Java compilers or versions/optimization strategies may use a different arrangement that is still valid. `javap -c` shows the **bytecode in the class file**, not the machine code that the JIT later executes.

### 9.2. Interpreting the group of operations on a field

For `assignedField(Box box)`, the goal is to both execute `box.value = 12` and keep the result for the `result` variable. One may see the conceptual sequence:

```text
aload_0            // box reference
bipush 12          // int 12
dup_x1             // ..., ref, 12 → ..., 12, ref, 12
putfield ... value  // consumes ref, 12; leaves 12
istore_1           // store into result
iload_1
ireturn
```

It is valid because **reference** and **int** are both category 1. If the field is changed to `long`, the compiler cannot blindly use the same `dup_x1` because the top `long` is category 2; it must choose a valid instruction for the new stack shape.

### 9.3. Interpreting `dup2_x2` with a `long` array

Before `lastore`, the stack has the `long[]` reference, index, and `long` value:

```text
..., arrayref(cat1), index(cat1), 34L(cat2)
```

`dup2_x2` form 2 turns it into:

```text
..., 34L(cat2), arrayref(cat1), index(cat1), 34L(cat2)
```

The `lastore` instruction pops **arrayref, index, long value at the top according to operand rules**; the `34L` copy underneath remains as the assignment expression value. The understanding that "dup2 duplicates the two numbers on top" would fail immediately in this case because the top contains only **one** logical `long` value.

## 10. The bytecode verifier prevents invalid stack forms

Instructions in `.class` files must satisfy rules on **count, order, category, and value type**. The JVM verifier checks the type data of the stack and local variables along control flow before allowing bytecode to be executed under specification conditions.

Example of **hypothetical invalid bytecode**:

```text
lconst_0   // push a long: category 2
pop        // INVALID: pop requires a category 1 top
return
```

This is **not valid Java source** and cannot be run as a `.java` file; it illustrates a class file generated **incorrectly** by a bytecode assembler/tool. A specification-compliant JVM will not consider that operation valid; during verification a `VerifyError` (part of the `LinkageError` family) may occur. You should not try to trigger the error by editing a few hex bytes in a real class file, because doing so may produce `ClassFormatError` due to structural corruption before reaching the verification step.

Similarly:

```text
dconst_0
dup         // INVALID: double is category 2
```

and:

```text
iconst_1
lconst_0
swap        // INVALID: top is long (category 2)
```

There is no concept of "only warning while the JVM automatically fixes the stack" for these category-invalid sequences. Nor does the verifier only inspect each opcode in isolation: data across merged control-flow branches must have compatible stack states and types; an `ireturn` must return a value matching the method descriptor; method invocations and field accesses need operands of the right types.

## 11. Stack depth, `max_stack`, and memory misconceptions

In each `Code` attribute, the class file stores information such as **`max_stack`** and **`max_locals`**. `max_stack` represents the **maximum depth of the operand stack measured in width units**, not always the number of logical values on the stack.

For example, after a `dup2` with a `long` on top, the two `long` copies occupy **four stack units** in total, even though there are only **two logical values**. If the code also keeps a reference or index underneath, the corresponding units also add to the depth.

You can view the information generated by the compiler:

```bash
javap -v -p StackInstructionDemo
```

Look for the `Code:` section, the `stack=...` and `locals=...` lines. Specific results depend on the actual bytecode of the compiler and method being inspected. `max_stack` does **not** indicate heap memory usage, does not equal the JVM thread stack size in bytes, and does not mean each cat2 value always occupies exactly 8 physical bytes in the JIT compiler's registers/memory.

### Category 2 values in local variables

For the local-variable array, `long` and `double` occupy **two consecutive slot indices** in the JVM model; reference and `int` occupy one slot. This rule relates to the same category classification, but the `dup2` instruction operates on the **operand stack**, not duplicating local variable slots. To read/write local variables, there are separate instructions such as `lload`, `lstore`, `iload`, `istore`.

## 12. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`pop2` always removes two values." | Removes **two cat1** or **one cat2**. |
| "`dup2` duplicates everything on top as two objects." | Duplicates a total width of two units, which may be **one long/double**. |
| "`dup` of a reference creates a new object." | Only duplicates the **reference value**, does not call `new`. |
| "`swap` works with `long` on a 64-bit JVM." | No; both top values must be category 1 according to the JVM Specification. |
| "The `_x2` suffix means duplicate twice." | `_x2` expresses inserting the copy **two units** deep beneath; the scope of duplication is determined by `dup` or `dup2`. |
| "Two cat1 values are equivalent to one cat2 in every instruction." | They have the same **total width** but differ in value count and type; only certain instructions have multiple valid forms. |
| "Bytecode having `dup` means the Java program intentionally creates a copy for reuse." | Usually it is a compiler strategy to retain an intermediate result, such as in field, constructor, or array assignments. |
| "`javap` shows the final CPU code." | It disassembles class-file bytecode; JIT and interpreter are separate runtime steps. |
| "If an instruction is valid by category, the whole method is definitely valid." | The verifier also checks value types, descriptors, initialization state, stack depth, and control-flow branches. |

## 13. Operand stack reading exercises

**Exercise 1:** Stack `..., int A, int B`; execute `dup_x1`.  
**Answer:** `..., B, A, B`. Both values are cat1.

**Exercise 2:** Stack `..., long L`; want to duplicate value `L` for a subsequent computation step. Choose `dup` or `dup2`?  
**Answer:** `dup2`; `long` is a category 2 value.

**Exercise 3:** Stack `..., double D, int I`; execute `dup_x2`.  
**Answer:** `..., I, D, I` according to form 2 because the top is cat1 and the value beneath is cat2.

**Exercise 4:** Stack `..., long L, int I`; execute `pop2`.  
**Answer:** **Invalid**; the top is cat1 but directly beneath is cat2. `pop2` does not split `long` into one unit to discard.

**Exercise 5:** Stack `..., int X, int Y, long L`; execute `dup2_x2`.  
**Answer:** `..., L, X, Y, L` according to form 2. The cat2 value `L` is duplicated and inserted beneath two cat1 values.

**Exercise 6:** Stack `..., long X, long Y`; execute `dup2_x2`.  
**Answer:** `..., Y, X, Y` according to form 4. Both are cat2; cannot be replaced by `swap`.

**Exercise 7:** After `new` and before the constructor, the compiler uses `dup` on the reference. Are two objects created?  
**Answer:** No. `dup` creates two copies of the same reference (currently in an uninitialized state tracked by the verifier), without performing a new object allocation.

**Exercise 8:** Why can the assignment `long result = (array[index] = 34L)` be associated with `dup2_x2`?  
**Answer:** A copy of the `long` value needs to be kept as the **expression result**, while `lastore` still needs the triple `arrayref(cat1), index(cat1), value(cat2)`.

### Self-check after studying

1. Can you distinguish **category** from the **number of logical values**?
2. Can you correctly identify **TOP** as the right-hand side in the notation `..., value2, value1`?
3. For `dup_x2`, do you remember that **the top value must be cat1** in both forms?
4. For `dup2_x2`, can you analyze all **four valid forms**?
5. Do you know how to use `javap -c -p` to verify the instructions that `javac` actually generates?

**Reference:** *The Java Virtual Machine Specification*, chapter **6.5 Instructions** (sections `pop`, `pop2`, `dup`, `dup_x1`, `dup_x2`, `dup2`, `dup2_x1`, `dup2_x2`, `swap`): https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html. When learning the syntax of the forms, prioritize the specification's operand stack tables rather than guessing from opcode names.

Practical takeaway: read `pop`, `dup`, `swap` by **determining the category of each value in order from bottom to top**, choosing the right instruction form, and rewriting the stack after the operation. Only when all these transformations are valid by category and subsequent instructions use the right types can the JVM verify and execute the bytecode as expected.