# Loading Constants and Transferring Data Between Local Variables and the Operand Stack in the JVM

In the Java Virtual Machine (JVM), many Java expressions are executed through a very specific sequence of operations: **pushing constants onto the operand stack**, **loading values from local variables onto the stack**, performing an operation or invoking a method, and then **storing the result from the stack back into local variables**. By understanding these instructions, you can read `javap -c` output, trace each value inside a JVM frame, and distinguish bytecode-level operations from Java statements.

This lesson focuses on the **constant loading** bytecode group (`iconst_*`, `bipush`, `sipush`, `ldc`, `ldc_w`, `ldc2_w`, etc.), **local load/store** (`iload`/`istore`, `lload`/`lstore`, etc.), slot indices, 1-slot or 2-slot values, and the `wide` and `iinc` instructions. The reference specification is **JVMS Java SE 17**. The code examples use Java 17+, and the opcodes chosen by `javac` will be distinguished from the mandatory rules of the specification.

## 1. Execution Frame: Locals and Operand Stack Belong to *Each Method Invocation*

A JVM method invocation creates a **frame** containing two important regions:

- **Local variable array**: slots indexed starting from `0`, containing parameters, the `this` receiver (for instance methods), and local/temporary values. This array is accessed by **index**.
- **Operand stack**: a LIFO stack containing operands and intermediate results. Most arithmetic instructions pop operands from the top of the stack and push the result back.
- **`max_locals` and `max_stack`** in the method's `Code` attribute specify the number of local slots and the maximum depth of the operand stack. These are **per-frame** limits, not the heap size or the entire Java thread stack.

A common data flow diagram:

```text
Local variables                     Operand stack (bottom → top)
slot 0: a = 4                          []
slot 1: b = 5                          []
      | iload_0                          [4]
      | iload_1                          [4, 5]
      | iadd                             [9]
      | istore_2                         []
slot 2: sum = 9   <---------------------+
```

`iload_0` does not take the value “out of” the local: it **copies the value** from slot 0 onto the stack. Conversely, `istore_2` **pops the value from the top of the stack** to assign it to slot 2, so the stack depth decreases. Local slot 0 remains 4, and slot 1 remains 5 after the addition.

A method with multiple concurrent invocations (multiple threads or recursion) will have **separate frames**. Local slot 0 must not be understood as a global variable shared across invocations.

### A Value Can Occupy One or Two Slots

| JVM computational type | Category width | Operand stack depth when pushing one value | Local slots required |
| --- | --- | ---: | ---: |
| `int`, `float`, `reference` | Category 1 | 1 | 1 |
| `long`, `double` | Category 2 | 2 | 2 |
| `byte`, `short`, `char`, `boolean` when operated on in bytecode | Usually as `int` (category 1) | 1 | 1 for the corresponding computational type local |

`long`/`double` is **one logical value** but requires two slots under the JVM model; it is not two independent numbers that code can arbitrarily read half by half. On the operand stack, stack manipulation instructions such as `dup`, `dup2`, `pop`, and `pop2` must respect this category classification.

## 2. Ways to Push Constants Directly onto the Operand Stack

The JVM has several short opcodes for common constants, helping keep bytecode smaller when accessing the constant pool is not needed.

| Bytecode instruction | Value pushed onto stack | Type | Notes |
| --- | --- | --- | --- |
| `aconst_null` | `null` reference | Reference, category 1 | Does not create an object |
| `iconst_m1` | `-1` | `int` | Dedicated opcode for minus one |
| `iconst_0` … `iconst_5` | `0` … `5` | `int` | Six opcodes for small ints |
| `lconst_0`, `lconst_1` | `0L`, `1L` | `long`, category 2 | Pushes a long value occupying two slots |
| `fconst_0` … `fconst_2` | `0.0f`, `1.0f`, `2.0f` | `float` | Three built-in float constants |
| `dconst_0`, `dconst_1` | `0.0d`, `1.0d` | `double`, category 2 | Two built-in double constants |
| `bipush n` | Integer from `-128` to `127` | `int` | **Signed 8-bit** immediate, sign-extended to int |
| `sipush n` | Integer from `-32768` to `32767` | `int` | **Signed 16-bit** immediate, sign-extended to int |

An important point: the word **byte** in `bipush` describes the width of the *immediate operand in the class file*, it does **not** mean this opcode pushes a Java `byte` value onto the stack. Both `bipush` and `sipush` push an **`int`**.

Examples of stack effects, where the left side denotes the stack before the instruction:

```text
[]             -- iconst_3   --> [3]
[]             -- bipush 7   --> [7]
[]             -- sipush 300 --> [300]
[12]           -- iconst_2   --> [12, 2]
[12, 2]        -- iadd       --> [14]
[]             -- lconst_1   --> [1L]  // one long value = two slots
[]             -- aconst_null --> [null]
```

In this example, `iadd` requires two `int` values on top of the stack; it pops them and pushes the `int` sum. The fact that `sipush 300` has an operand encoded in two bytes does not make the result a `short` type. Similarly, `lconst_1` is not two `int` elements that can be added using `iadd`.

### What About Values Beyond Small Immediates?

When a value does not fit an immediate opcode, the compiler can choose an instruction that accesses the **run-time constant pool**, such as `ldc` or `ldc2_w`. The choice of opcode among valid representations depends on the compiler; a constant appearing in source code is not guaranteed to be pushed onto the operand stack at runtime (the compiler may perform constant folding or code optimization).

## 3. `ldc`, `ldc_w`, and `ldc2_w`: Reading Data from the Run-Time Constant Pool

The run-time constant pool associated with a class holds constants and symbolic references defined through the constant pool structure in the `.class` file. Three opcodes use an **index** into the constant pool:

| Instruction | Index operand | Commonly loaded types | Instruction size in bytes including opcode |
| --- | --- | --- | ---: |
| `ldc index` | Unsigned `u1` index, up to 255 | `int`, `float`, `String` reference, `Class` reference, method type/handle, or category 1 dynamic constant | 2 |
| `ldc_w indexbyte1 indexbyte2` | Unsigned `u2` index, up to 65535 | Same as `ldc`; **only differs in index width** | 3 |
| `ldc2_w indexbyte1 indexbyte2` | Unsigned `u2` index | `long`, `double`, or corresponding category 2 dynamic constant | 3 |

- `ldc_w` does **not** mean “load a 64-bit value”; the `_w` suffix refers to a **wider constant-pool index**. It can load `int`, `float`, or a reference just like `ldc`.
- `ldc2_w` is used for `long`/`double` values beyond those with dedicated opcodes; there is no standard opcode named `ldc2` with an 8-bit index.
- A `String` literal is loaded as a **reference** pointing to the corresponding `String` object; `ldc` does not copy individual characters onto the operand stack.
- For `Class` constants, method handles/types, or **dynamic constants**, resolution can occur and throw linkage errors according to the specification. Do not treat every `ldc` as merely “reading a stored number” in a simple sense.
- `ldc` can load a dynamically computed category 1 constant (`CONSTANT_Dynamic`); `ldc2_w` can load a `long`/`double` dynamic constant. Not all ordinary Java source code can directly express these constants; they may come from bytecode-generating compilers/libraries.

Examples following common Java 17 `javac` choices:

```text
iconst_5               // int 5
bipush 100             // int 100
sipush 300             // int 300
ldc #N                 // int 40000 from constant pool
ldc2_w #M              // long 5000000000 from constant pool
ldc #K                 // String "JVM" from constant pool
```

`#N`, `#M`, and `#K` are **illustrative indices**, not mandatory numbers. The actual indices depend on the order of entries in the constant pool generated by the compiler.

### Why Doesn't One Source Line Correspond to One `ldc`?

`static final int LIMIT = 100;` may be a **compile-time constant** and be inlined directly by the compiler at its usage sites. An expression consisting only of constants may be precomputed, leaving no corresponding addition/multiplication opcode in the bytecode. When inspecting bytecode, only draw conclusions about the **class file being viewed**; the language contract still resides in the JLS and opcode semantics reside in the JVMS.

## 4. Instructions for Loading Local Variables onto the Operand Stack

The `load` instructions take a value from the **current frame's local-variable array** and **push a copy of the value onto the operand stack**.

| JVM type | Explicit index form | Shorthand form for index 0–3 | Effect |
| --- | --- | --- | --- |
| `int` | `iload index` | `iload_0` … `iload_3` | Locals[index] → stack (1 slot) |
| `long` | `lload index` | `lload_0` … `lload_3` | Locals[index,index+1] → stack (2 slots) |
| `float` | `fload index` | `fload_0` … `fload_3` | Locals[index] → stack (1 slot) |
| `double` | `dload index` | `dload_0` … `dload_3` | Locals[index,index+1] → stack (2 slots) |
| Reference | `aload index` | `aload_0` … `aload_3` | Locals[index] → stack (1 slot) |

Several important rules:

1. `iload_0` is a separate opcode with an **implicit index 0**; `iload 0` uses an additional operand byte for the index. Both forms have the same semantics, with different encodings.
2. `lload_2` starts at **slot 2**, occupies slots **2 and 3**, and pushes a `long` value using two slots onto the stack.
3. Local slots must hold **valid types** according to verification state. `iload` cannot arbitrarily read a reference, `aload` cannot read an `int`, and an uninitialized/unassigned local value must not be used.
4. The Java types `byte`, `short`, `char`, and `boolean` in many local operations are represented by the JVM via **`int`** and the `iload` instruction. When it is necessary to ensure a value stays within a narrow range, the compiler may emit conversions such as `i2b`, `i2s`, or `i2c`.
5. `aload_0` in an instance method **usually** loads `this` because the receiver is at local slot 0; in a `static` method, slot 0 can hold the first parameter instead of `this`.

Do not infer that `iload_1` means “load the second parameter” in every method: the hidden receiver and category 2 parameters shift the **slot** ordering.

## 5. Instructions for Storing from the Operand Stack to Local Variables

`store` performs the reverse operation of `load`: it **pops the top value of the stack** and stores it at the indexed position in local variables.

| JVM type | Explicit index form | Shorthand form for index 0–3 | Effect |
| --- | --- | --- | --- |
| `int` | `istore index` | `istore_0` … `istore_3` | stack pop (int) → locals[index] |
| `long` | `lstore index` | `lstore_0` … `lstore_3` | stack pop (long) → locals[index,index+1] |
| `float` | `fstore index` | `fstore_0` … `fstore_3` | stack pop (float) → locals[index] |
| `double` | `dstore index` | `dstore_0` … `dstore_3` | stack pop (double) → locals[index,index+1] |
| Reference | `astore index` | `astore_0` … `astore_3` | stack pop (reference) → locals[index] |

For example, the expression `int result = a + b;` in a method can be compiled to:

```text
iload_0     // [] → [a]
iload_1     // [a] → [a, b]
iadd        // [a, b] → [a+b]
istore_2    // [a+b] → []; locals[2] receives a+b
```

Here, `istore_2` does **not** return the result from the method: it only writes to the local variable. To return an `int`, the bytecode may continue with `iload_2` and then `ireturn`. Another compiler may omit the intermediate store/load altogether and return the result directly while still preserving Java semantics.

Another constraint: assigning a category 2 local (`long`/`double`) changes the validity state of both slots it occupies. Store operations that overwrite part of a category 2 slot pair can render the previous category 2 value no longer validly readable. Therefore, any code that manually generates/modifies bytecode must synchronize **the types and liveness ranges of local slots**, rather than looking only at index numbers.

### `max_locals` Differs from the Number of Named Variables

- Method `static int add(int a, int b)`: `a` is at slot 0, `b` is at slot 1; if storing the result in a new variable, slot 2 can be used.
- Method `int add(int b)` (instance): `this` is at slot 0, `b` is at slot 1.
- Method `static long add(long a, long b)`: `a` occupies slots 0–1, `b` occupies slots 2–3. Storing an additional `long` result may require slots 4–5.
- The compiler can **reuse** a slot after the old value's required scope ends or allocate slots for unnamed intermediate values in the source.

In `javap -v`, the line `stack=..., locals=..., args_size=...` summarizes frame information; `args_size` is how `javap` presents the number of slots reserved for the method's JVM arguments (including the receiver for instance methods and two slots for each `long`/`double`), and is **not** a separate field of the `Code_attribute` structure.

## 6. Runnable Java 17 Example: constant → stack → local → operation

Create the file **`LocalStackFlow.java`**:

```java
public class LocalStackFlow {
    public static int calculate(int input) {
        int increased = input + 7;
        int result = increased + 40_000;
        return result;
    }

    public static long addLong(long first, long second) {
        long sum = first + second;
        return sum;
    }

    public static String label() {
        return "JVM";
    }

    public static void main(String[] args) {
        System.out.println("calculate=" + calculate(2));
        System.out.println("long=" + addLong(20L, 22L));
        System.out.println("label=" + label());
    }
}
```

Compile and run on a JDK with `javac` supporting Java 17:

```bash
javac --release 17 -g LocalStackFlow.java
java LocalStackFlow
javap -c -v -p LocalStackFlow
```

**Stdout of `java LocalStackFlow`**:

```text
calculate=40009
long=42
label=JVM
```

### Reading the `calculate(int)` Method via `javap`

With standard Java 17 `javac`, the notable opcode section may appear as follows (excerpting only this method, omitting other metadata entries):

```text
public static int calculate(int);
  Code:
    stack=2, locals=3, args_size=1
       0: iload_0
       1: bipush        7
       3: iadd
       4: istore_1
       5: iload_1
       6: ldc           #...   // int 40000
       8: iadd
       9: istore_2
      10: iload_2
      11: ireturn
```

The `#...` notation above represents **a constant pool index**, not verbatim output that can be copied for execution. Bytecode indices `0, 1, 3, 4, ...` are **byte offsets**, not instruction counts. `bipush 7` occupies two bytes; `ldc` with a one-byte index also occupies two bytes.

| BCI / opcode | Local variables (slots 0, 1, 2) | Operand stack, bottom → top | Number of slots on stack |
| --- | --- | --- | ---: |
| Before `iload_0` | `[2, -, -]` | `[]` | 0 |
| After `iload_0` | `[2, -, -]` | `[2]` | 1 |
| After `bipush 7` | `[2, -, -]` | `[2, 7]` | 2 |
| After `iadd` | `[2, -, -]` | `[9]` | 1 |
| After `istore_1` | `[2, 9, -]` | `[]` | 0 |
| After `iload_1` | `[2, 9, -]` | `[9]` | 1 |
| After `ldc 40000` | `[2, 9, -]` | `[9, 40000]` | 2 |
| After `iadd` | `[2, 9, -]` | `[40009]` | 1 |
| After `istore_2` | `[2, 9, 40009]` | `[]` | 0 |
| After `iload_2` | `[2, 9, 40009]` | `[40009]` | 1 |
| `ireturn` | Frame about to return | Returns `40009` to caller | — |

The `-` in the table means the local does not yet have a usable value along the illustrated path, not the Java `null` value. The maximum depth is **2 slots**, so `max_stack=2` is appropriate for this method; **3 local slots** are needed (input/increased/result), so `max_locals=3`.

Note: this is **one way of compiling**. A compiler is permitted to transform or eliminate intermediate locals and change constant loading as long as the resulting code complies with the JLS/JVMS. When learning instruction rules, inspect the actual bytecode produced by the compiler you are using.

### With `addLong(long,long)`: Two Values but Four Slots

In this `static` method:

```text
locals:
  slot 0-1 : first  = 20L
  slot 2-3 : second = 22L
  slot 4-5 : sum    = 42L (after lstore)

operand stack:
  []                         initially
  [20L]                      after lload_0         (2 slots)
  [20L, 22L]                 after lload_2         (4 slots)
  [42L]                      after ladd            (2 slots)
  []                         after lstore 4        (0 slots)
  [42L]                      after lload 4         (2 slots)
  []                         after lreturn
```

`max_stack` for the form above is **4**, and `max_locals` is **6**. Do not count `[20L, 22L]` as “two slots”: those are **two category 2 values**, totaling four slots.

`label()` illustrates loading a String literal with `ldc` onto the operand stack and then returning it with `areturn`; the JVM operates on the **reference** rather than pushing individual UTF-8 bytes of the string onto the stack.

## 7. Example of Parameters, `this`, and Non-Contiguous Local Positions

Standalone file **`ParameterSlots.java`**:

```java
public class ParameterSlots {
    private final int base;

    public ParameterSlots(int base) {
        this.base = base;
    }

    public long combine(int count, long amount, double ignored) {
        long result = amount + count + base;
        return result;
    }

    public static void main(String[] args) {
        ParameterSlots value = new ParameterSlots(5);
        System.out.println("combined=" + value.combine(2, 30L, 0.5));
    }
}
```

Commands:

```bash
javac --release 17 -g ParameterSlots.java
java ParameterSlots
javap -c -p ParameterSlots
```

**Stdout of `java`**:

```text
combined=37
```

In the **instance method** `combine(int,long,double)`, the initial local indices are determined by the descriptor, even though the variable `ignored` does not appear in the method body:

| Slot | Content at method entry |
| --- | --- |
| 0 | `this` reference |
| 1 | `count` (`int`) |
| 2 and 3 | `amount` (`long`) |
| 4 and 5 | `ignored` (`double`) |
| 6 and 7 | May be used by the compiler for `result` (`long`) |

The instruction `iload_1` loads `count`; `lload_2` loads `amount`; `aload_0` loads `this` to read the `base` field via `getfield`; a `long` result can be stored using `lstore 6`. Parameter positions are mandatory per invocation convention; temporary locals for `result` and the specific opcode sequence are decided by the compiler.

Examples with `long`/`double` show why `lload_2` is **not** “load the third parameter” and why `max_locals` cannot be calculated solely from the number of parameters written in Java source.

## 8. `iinc` Updates a Local Without Going Through the Operand Stack

`iinc index, const` is a special opcode that adds a **signed byte** immediate to an `int` local variable. It updates locals at `index` **directly**; the operand stack **is unchanged**.

Illustrative bytecode example for a local variable `int counter`:

```text
locals[1] = 8;  stack = []
iinc 1, 1
locals[1] = 9;  stack = []
```

Compare with an increment written as load/add/store:

```text
iload_1       // [] → [8]
iconst_1      // [8] → [8, 1]
iadd          // [8, 1] → [9]
istore_1      // [9] → []; locals[1] = 9
```

The two sequences can be equivalent in result in a simple context, but `iinc` only applies to an **`int` local** and has an immediate operand in its encoding. There is no equivalent `linc` opcode for `long`, and updating fields/arrays does not occur via `iinc`.

Java example:

```java
public static int next(int value) {
    value++;
    return value;
}
```

This is an **illustrative method snippet**, placed inside a class to compile. Java 17 `javac` typically generates `iinc 0, 1` followed by `iload_0` and `ireturn`. If `value == Integer.MAX_VALUE`, the integer increment wraps to `Integer.MIN_VALUE`; `iinc` does not throw an exception on overflow.

## 9. `wide`: Extending the Local Index and `iinc` Immediate

The `iload index`/`istore index` instructions in their normal form have an unsigned **8-bit index**. When needing to reference a local slot index greater than 255, the JVM uses the **`wide`** prefix with a **16-bit** index. `wide` supports the local load/store groups, the legacy `ret`, and `iinc`; it is not a universal opcode that widens every instruction.

Illustrative forms:

```text
iload 12          // index 12 uses a 1-byte operand
wide iload 300    // index 300 uses a 2-byte operand
iinc 7, -3        // 1-byte index; 1-byte signed const
wide iinc 300, 1000 // 2-byte index; 2-byte signed const
```

**These are format-illustrating mnemonics**, not a `javap` snippet taken from a specific file. When encoded as bytes, `wide` is a prefix with its own opcode preceding an opcode allowed to be widened.

- With `wide iload`, `wide istore`, and other load/store instructions, the local index becomes `u2` (0–65535, though it must still fall within `max_locals`).
- With `wide iinc`, both the index is `u2` and the immediate is a **signed 16-bit** integer.
- `wide` does **not** turn an `int` into a `long`, does not make the operand stack wider, and does not widen a constant-pool index: that is the job of `ldc_w`.

One more practical note: a source program with very many local variables can cause the compiler to emit `wide`, but the compiler can also reuse local slots. The number of variables in source code does not by itself determine whether this prefix appears.

## 10. Loading/Storing Locals Differs from Reading/Writing Fields and Arrays

There are three places often collectively called “variables” when reading Java source, but their opcodes differ:

| In source | Representative opcode group | Data container |
| --- | --- | --- |
| Local variable or parameter | `iload`/`istore`, `aload`/`astore`, etc. | The frame's local-variable array |
| Instance field | `getfield`/`putfield` | An object pointed to by a reference |
| Static field | `getstatic`/`putstatic` | Static field of a class/interface |
| Array element | `iaload`/`iastore`, `aaload`/`aastore`, `baload`/`bastore`... | Array object and index |

For example, with `int[] a`, `a[0] = 9` is **not** performed using `istore_0` unless the compiler is assigning 9 to some *local variable*. An array store requires the array reference, index, and value on the operand stack, and then uses `iastore`.

Similarly, `aload_0` usually pushes `this`; to read `this.base`, the bytecode also needs `getfield`. `aload`/`astore` manipulate **references**, without automatically copying the entire object state.

### Illustrative Array Example, with Stack Flow

Suppose local slot 0 holds a reference to `int[]` and we want to write 9 to the first element:

```text
[]                     // initial operand stack
aload_0                // [arrayRef]
iconst_0               // [arrayRef, 0]
bipush 9               // [arrayRef, 0, 9]
iastore                // []; arrayRef[0] = 9
```

`iastore` pops three operands from the stack; `istore` only pops one `int` value and writes it to a local. This difference is very important when reading traces or calculating `max_stack`.

## 11. `dup`, `pop`, and Consequences for Operand Stack Depth

Not every stack-manipulating instruction performs arithmetic or accesses locals. Some instructions change **how values sit on the stack**:

- `pop` discards one **category 1** value on top.
- `pop2` discards one category 2 value **or** two category 1 values on top, depending on valid configurations.
- `dup` duplicates the category 1 value on top.
- `dup2` has valid forms to duplicate one category 2 value or a pair of category 1 values.
- `swap` exchanges the top two category 1 values; it cannot be used to arbitrarily swap a `long` and an `int`.

For example, an expression that both assigns and uses the result may need `dup` to **both store into a local/field and keep a copy of the value on the stack**. Reading opcodes without tracking the stack makes it very easy to mistake two copies for two different objects; with references, `dup` copies the **reference**, without creating a new object.

## 12. Data Types, Verification, and Related Errors

The JVM verifier checks that the code in a method has valid control-flow paths and stack/local types according to the corresponding class-file version. Examples of type-**invalid** bytecode:

```text
aconst_null
iadd                  // invalid: iadd requires two ints

iconst_1
lstore_0              // invalid: lstore requires a category 2 long

iload_1               // invalid if slot 1 does not yet hold a valid int value
```

These are **intentionally invalid fragments to illustrate verification**, definitely not runnable programs. Type/stack errors can lead to `VerifyError`; structurally corrupted class files can lead to `ClassFormatError`. These errors differ from `NullPointerException` or `ArithmeticException` thrown when **valid code** is executing.

Rules to follow when reading/generating bytecode:

1. There must be enough operands in the exact **order and type** for the next opcode.
2. Merging branches must agree on **stack/local types**; `StackMapTable` can assist the verifier in confirming this.
3. A local must not be loaded before it is validly assigned on the execution path reaching that instruction.
4. `max_stack` must be sufficient for every execution path; `max_locals` must cover all indices and `index+1` pairs of category 2 values.
5. When converting small types, remember `byte`/`short`/`char` are computed as `int` and may have `i2b`/`i2s`/`i2c` when narrowing is needed.
6. For `long`/`double`, one logical value has two slots; you cannot access the “upper half” with `iload` to pretend it is an `int`.

A `null` value pushed onto the operand stack by `aconst_null` is a **valid reference**. Only when using it in operations that require an actual object (such as dereferencing via `getfield`/`invokevirtual`) can `NullPointerException` occur; `aconst_null` itself does not throw an error.

## 13. Reading `javap` Output with a Consistent Process

Use `javap -c -v -p FileName` to inspect method bytecode and related metadata. When encountering an unfamiliar snippet:

1. **Identify the method descriptor accurately**: static or instance, which parameters occupy one/two slots, whether there is a `this` receiver.
2. **Read `stack=..., locals=..., args_size=...`**: `max_stack` is the maximum slot depth; `max_locals` is the number of slots allocated for locals; `args_size` is the number of argument slots as interpreted by `javap`.
3. **Initialize the locals table**: place slots for the receiver and parameters according to the descriptor. Mark uninitialized/invalid slots.
4. **Follow the BCI**: for `iconst_*`/`bipush`/`ldc`, push the value; for `iload`, copy from local; for `istore`, pop to local.
5. **Maintain category 1/2 accounting** when counting stack depth, especially with `lload`, `dload`, `lstore`, `dstore`.
6. **Track arithmetic, call, array, field, and return operations**: they consume/push different numbers of operands.
7. **Cross-reference branches and handlers**: an execution path may not follow the “straight-line” order of the output; exception handlers start with the exception reference on the operand stack.
8. **Distinguish observation from specification**: a compiler may choose different opcodes for the same source, but the semantics of each executed opcode are defined by the JVMS.

### Quick Reference Table

| If seen in `javap` | Read it as | What NOT to infer |
| --- | --- | --- |
| `iconst_2` | Pushes int 2 onto stack | There is a Java variable named “2” |
| `bipush 100` | Pushes int 100 from an 8-bit immediate | It pushes a Java `byte` onto the stack |
| `ldc #17` | Loads a category 1 constant via pool index 17 | Index 17 means the constant value 17 |
| `ldc_w #300` | Loads via a 16-bit index | The loaded value is 64 bits wide |
| `ldc2_w #42` | Loads `long`/`double` or corresponding dynamic constant | The number 42 itself is the `long` value |
| `iload_0` | Copies int from local slot 0 onto stack | It clears slot 0 |
| `istore_1` | Pops int from stack into local slot 1 | It returns the result to the caller |
| `lload_2` | Loads long starting at slots 2–3 | A long is two independent integers |
| `iinc 1, 1` | Increments local int slot 1 without changing operand stack | It is equivalent to incrementing a field |
| `wide iload 300` | Widens the encoding of the local index | Widens an int value into a long |
| `aload_0; getfield` | Loads reference, then reads field of the object | `aload_0` by itself reads the entire object |
| `iaload` | Reads an `int` array element | Reads a local variable like `iload` |

## 14. Common Mistakes

**Mistake 1 — Confusing locals with the stack.** Saying “`istore` puts a value onto the stack” is backwards: `store` pops a value off the operand stack and writes it into a local.

**Mistake 2 — Counting values and ignoring slot count.** `[10L,20L]` is two category 2 values, which is **4 slots** deep, not 2. Counting accurately is necessary to understand `max_stack`.

**Mistake 3 — Confusing `ldc_w` with `ldc2_w`.** One instruction widens the **constant pool index**; the other loads a `long`/`double` constant (or dynamic constant of the same kind).

**Mistake 4 — Assuming `byte` is loaded with `bload`.** The JVM has no `bload` local load group; `byte` is typically represented as `int` when passing through stack/locals.

**Mistake 5 — Assuming local slot index equals parameter ordinal.** `this` is at slot 0 in instance methods; `long`/`double` occupy two slots, so indices do not necessarily increase by one per parameter.

**Mistake 6 — Equating `iload` with `iaload`.** `iload` reads **locals**; `iaload` reads an **array element** and consumes the array reference and index from the stack.

**Mistake 7 — Assuming every constant must appear via `ldc`.** Small values have `iconst_*`/`bipush`/`sipush`; the compiler can fold constant expressions.

**Mistake 8 — Using `wide` with any opcode.** It is only valid when preceding opcodes defined by the JVMS as supported, not as a general “width-increasing prefix”.

**Mistake 9 — Treating a `javap` fragment as a compiler guarantee.** Another compiler may reuse locals, eliminate temporary variables, or use a different encoding. Learn **instruction semantics** and verify on the class being analyzed.

## 15. Self-Check Exercises

**Question A.** A static method has `int x` at local 0 and `int y` at local 1. Which sequence computes and stores `x+y` into local 2?

```text
iload_0
iload_1
iadd
istore_2
```

After `istore_2`, the stack returns to empty and local 2 holds the sum.

**Question B.** Do `ldc_w #300` and `ldc2_w #300` have the same meaning because both indices are 300?

No. `ldc_w` has a wide index but loads a category 1 constant; `ldc2_w` loads a category 2 `long`/`double`. Having the same index does not allow arbitrarily swapping opcodes.

**Question C.** After `lload_0` and `lload_2`, the stack contains two `long`s. What is the depth in slots?

**4 slots**.

**Question D.** Does `iinc 1, 5` pop or push the operand stack?

**No**; it modifies local `int` slot 1 directly.

**Question E.** In the instance method `m(int a, long b, double c)`, at which local slot does parameter `c` start?

`this` is at 0, `a` is at 1, `b` is at 2–3, so `c` starts at **slot 4** (occupying 4–5).

**Question F.** Does `bipush 127` push a `byte` or an `int`?

**`int`**, because the immediate signed byte is sign-extended before being pushed onto the operand stack.

## Original References for Java SE 17

- [JVMS 2.6 — Frames, local variables, operand stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): the per-method-invocation frame model.
- [JVMS `2.11.1–`2.11.2 — Types and load/store instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.2): category 1/2 types, local load/store groups, and constant loading.
- [JVMS 4.7.3 — Code attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): definitions of `max_stack`, `max_locals`, `code_length`, and the exception table.
- [JVMS 6.5 — Descriptions of individual instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): definitions of `bipush`, `sipush`, `ldc`, `ldc_w`, `ldc2_w`, `iload`, `istore`, `lload`, `iinc`, `wide`, `dup`, and `pop`.
- [JVMS 4.4 — Constant pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4): constant pool entry formats.
- [Java SE 17 `javap` Guide](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): using `-c`, `-v`, `-p` to analyze actual class files.

**Key takeaway:** constants are **pushed onto the stack**; `load` copies from locals **onto the stack**; `store` pops from the stack **to locals**. To read an instruction accurately, you must know the **type**, **slot count**, **local index**, **values currently on the operand stack**, and how many values the next instruction will pop or push.
