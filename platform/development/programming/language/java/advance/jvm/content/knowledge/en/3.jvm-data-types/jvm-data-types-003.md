# `long`, `double`, and Two Slots in the JVM Local-Variable Array

In Java, both `long` and `double` have a logical size of **64 bits**. However, when viewing bytecode with `javap`, you will see something else that can be surprising: a `long` or `double` parameter uses **two consecutive slots** (two local-variable slots) in the method's frame. If the first parameter is `long`, the next parameter of a `static` method usually starts at **index 2**, not 1.

This is a rule of the **Java Virtual Machine Specification (JVMS)** for the local-variable structure in a frame, not a "two Java variables" rule or an exact claim that the physical JVM reserves two fixed RAM cells. Understanding this properly helps when reading `iload`, `lload`, `dload`, `max_locals`, bytecode parameters, and verifier messages.

## 1. Distinguishing Value Size and Number of JVM Slots

| Java Type | Semantic Value Width | JVM Computational Category | Number of local-variable slots in a frame |
| --- | --- | --- | --- |
| `boolean`, `byte`, `short`, `char` | According to the corresponding Java type; some are processed using `int` at the bytecode level | **Category 1**, mainly `int` | **1** |
| `int` | 32 bits | **Category 1** | **1** |
| `float` | 32 bits | **Category 1** | **1** |
| `reference` (e.g., `String`) | Do not infer physical pointer size from bytecode | **Category 1** | **1** |
| **`long`** | **64 bits**, signed integer | **Category 2** | **2** |
| **`double`** | **64 bits**, IEEE 754 double precision | **Category 2** | **2** |

**Category 1/2** is a classification used in the **JVM execution model**. For category 2, a `long`/`double` value has a depth unit of **2** on the operand stack and uses **2 slots** in the local-variables array. The value is still **one** `long`/`double`, not two independent `int`s.

Example:

```java
long distance = 9_000_000_000L;
double ratio = 0.75;
int attempts = 3;
```

In the source code, there are **three variables**. At a point when all three simultaneously need local slots, they require **2 + 2 + 1 = 5 slots** in the local-variable array, not counting the `this` receiver, other parameters, other temporary data, and slot reuse possibilities.

**Do not confuse with:**

- **Heap:** a `long` field in an object or a `long[]` element does not "occupy two array elements". The two-slot rule being discussed belongs to the **frame's local-variable array**.
- **Physical memory:** a slot is an indexing concept accessed by bytecode; the JVM is free to use CPU registers, the native stack, or internal optimizations. One must not conclude that "each slot occupies exactly 4 bytes of real RAM".
- **Primitive bit count:** `double` is still a 64-bit floating-point value, even though it has two local-variable slots.

## 2. What Are a Frame and a Local-Variable Array?

Each time the JVM invokes a Java method, the execution model creates a **frame** associated with that call. A frame consists of:

1. **Local-variable array:** holds parameters and local variables needed, addressed by indices 0, 1, 2, ...
2. **Operand stack:** where bytecode instructions push values, pop operands, and return results.
3. Information supporting dynamic linking, return results, and the method execution mechanism.

The length of a method's local-variable array is specified by **`max_locals`** in the `Code` attribute of the class file. `max_locals` is the **number of slots** required, not the number of variables declared in source code. `max_stack` is the maximum depth of the operand stack measured in **depth units**.

A frame exists only for the corresponding invocation in the JVM model. Active frames belong to a JVM thread; if a method is recursive, each invocation has its **own frame** with its own local variables. Unlike the heap, the local-variable array is not a global variable table shared across all threads.

### 2.1. Starting from Index 0

Local variables are indexed sequentially: `0`, `1`, `2`, ... `max_locals - 1`. For the load bytecode `lload 0`, the number `0` is the **starting index** of the slot pair containing the `long` value. That value occupies both slot `0` and slot `1`.

Example according to the specification model:

```text
Local-variable array
Index:   0         1         2         3         4
       ┌─────────┬─────────┬─────────┬─────────┬─────────┐
       │    long value     │   double value    │   int   │
       │ starts at index 0 │ starts at index 2 │ index 4 │
       └─────────┴─────────┴─────────┴─────────┴─────────┘
           ↑                   ↑                     ↑
        lload 0             dload 2              iload 4
```

The `long` value **can only be accessed by the lower index of the pair**, i.e. `0`; similarly `double` by `2`. Index `1` or `3` **is not a separate value** where you can use `iload` or `lload` to read the remaining part.

### 2.2. A `long` Index Does Not Have to Be Even

The rule is **two consecutive slots**, not "must start at an even number". A valid `long` can be at `1` and `2` (for example, the first parameter of an instance method after `this`), or `3` and `4`. The JVM Specification **does not require 64-bit alignment on even indices** in the local-variable array.

## 3. Why Must the Next Slot Be Skipped?

Consider the declaration:

```java
static void report(long count, double price, int batch) {
    // ...
}
```

Because it is a `static` method, parameters start from index 0:

| Parameter Variable | Type | Position in Frame |
| --- | --- | --- |
| `count` | `long` | **0 and 1**; read with `lload 0` |
| `price` | `double` | **2 and 3**; read with `dload 2` |
| `batch` | `int` | **4**; read with `iload 4` |

How to calculate the next index:

```text
start = 0                // static method: first parameter
count: [0, 1]            // long  → shift +2
price: [2, 3]            // double → shift +2
batch: [4]               // int → shift +1
next free index >= 5
```

The local-variables array must be large enough to hold parameters up to slot 4, so the parameters alone require **at least 5 slots**. If the body also has another `double` variable needing slots at 5 and 6, `max_locals` is at least 7.

**Important:** `count` is **one parameter**, even though it needs two slots. When the Java reflection API returns `Method.getParameterCount()` for the method above, the result is **3**, not 5. Counting source/reflection parameters and indexing local slots are two different frames of reference.

### 3.1. Instance Methods: Slot 0 Is Reserved for `this`

For an instance method:

```java
double calculate(long count, double price, int batch) {
    return count * price + batch;
}
```

The receiver `this` resides at **index 0**; actual parameters start from 1:

| Slot | Content |
| --- | --- |
| 0 | `this` — reference to the object receiving the call |
| 1, 2 | `count` — a `long` |
| 3, 4 | `price` — a `double` |
| 5 | `batch` — an `int` |

Thus, with the same three parameter types `long, double, int`, an instance method needs **at least 6 slots** to pass the receiver and parameters, whereas a `static` method only needs 5 slots for the parameters. In the bytecode of the instance method, `lload_1` (not `lload_0`) will load `count`.

`this` is not a local variable declared by the programmer using `long`/`double` syntax, but it is the receiver required in an instance method's frame according to JVM method invocation rules.

## 4. Rule for Overwriting the Second Half of a Slot Pair

The JVMS also has an important detail when understanding bytecode or writing bytecode manually:

- A `long`/`double` placed at index `n` occupies **n and n+1**.
- You can only **load** the entire category 2 value via index `n`.
- You can **store** another value into index `n+1`, but doing so **makes the `long`/`double` value starting at `n` no longer valid for use**.

Conceptual illustration:

```text
Initially:
slot 0 ─┐
        ├── long value L (read with lload 0)
slot 1 ─┘

After istore 1:
slot 0 ─── old data no longer forms a valid long
slot 1 ─── int value M

Afterward, lload 0 is no longer valid according to the local-variables type state.
```

This is **not a technique for splitting a `long` into two halves to read data**, nor a way to access 32 bits at a time. With inconsistent bytecode, the type checker/verifier can reject the class (for example, `VerifyError`). Valid bytecode only loads a category-2 value after the slot pair has been established with the correct type state.

The compiler can **reuse slots** when two variables do not need to be alive at the same time. Therefore, you cannot multiply the total number of variables appearing in the source by their sizes to deduce the exact `max_locals`.

## 5. Bytecode Instructions for Local Variables

| Operation | For `int` (1 slot) | For `long` (2 slots) | For `double` (2 slots) |
| --- | --- | --- | --- |
| Load local onto operand stack | `iload index` | `lload index` | `dload index` |
| Store from operand stack to local | `istore index` | `lstore index` | `dstore index` |
| Shorthand form for index 0…3 | `iload_0`…`iload_3` | `lload_0`…`lload_3` | `dload_0`…`dload_3` |
| Return value from method | `ireturn` | `lreturn` | `dreturn` |
| Addition | `iadd` | `ladd` | `dadd` |

For example, `lload_0` reads **one `long` value spanning slots 0–1**. It does **not** read `slot 0` and then need a separate `lload_1`. Likewise, `dstore 5` writes a `double` starting at index 5, using slots 5–6.

Some opcodes support operating on large indices via the `wide` prefix, but `wide` is a mechanism to **extend the size of the instruction's index operand**, not a keyword indicating `long`/`double` and it does not change the two-slot rule.

### 5.1. `lconst`, `dconst`, and `ldc2_w`

The JVM has suitable constant-loading instructions: `lconst_0`, `lconst_1` for two small `long` values; `dconst_0`, `dconst_1` for `double` 0.0 and 1.0; for many other `long`/`double` constants, the compiler typically uses `ldc2_w` to load from the constant pool. Only after that does it use `lstore`/`dstore` if that value needs to be stored into local variables.

For example, `long x = 10L;` may produce `ldc2_w` followed by `lstore` depending on the index; do not expect that it always uses an `lconst_10` instruction (that opcode **does not exist**).

## 6. How Do Two Local Slots Differ from the Operand Stack?

In the **local-variable array**, a `long`/`double` occupies **two consecutive local-variable slots**. However, on the **operand stack**, it is **one category 2 value** that increases the stack depth by **two units**. You are not allowed to arbitrarily split it into two category 1 values.

Example of a `long` addition:

```java
static long add(long a, long b) {
    return a + b;
}
```

Assuming a typical bytecode sequence:

```text
Local variables:
  slot 0–1: long a
  slot 2–3: long b

Operand stack:                         depth (units)
  [empty]                              0
  lload_0  → [a]                       2
  lload_2  → [a, b]                    4
  ladd     → [a+b]                     2
  lreturn  → [empty], returns one long 0
```

Because both `long` operands are simultaneously on the operand stack, this example needs **`max_stack >= 4`**. It also needs at least **`max_locals = 4`** for the two parameters; these are **two independent size metrics**.

For `double`, `dload` and `dadd` follow the same category 2 principle. Do not imagine the JVM adding the "high half" and the "low half" using two `iadd` instructions: the JVM uses the proper `dadd`/`ladd` operation on **one typed 64-bit value**.

Some stack manipulation instructions have their own category rules:

- `pop` only removes one **category 1** value; to remove one **category 2** value, use `pop2`.
- `pop2` can pop **one** category 2 value **or two** category 1 values.
- `dup2` can duplicate **one** category 2 value or **two** category 1 values on top in a valid form.
- `swap` only swaps two category 1 values; it cannot be used to split or directly swap a `long`/`double` into two halves.

**Remember:** the operand stack has **2 depth units**, which does not mean a category-2 value consists of **two independent elements** to `pop`, `swap`, or access individually.

## 7. Complete Java 17+ Program and How to Read Bytecode

Create the file **`SlotDemo.java`**:

```java
public class SlotDemo {

    // static: first parameter starts at local slot 0.
    static double weighted(long items, double unitPrice, int fee) {
        double total = items * unitPrice + fee;
        return total;
    }

    // instance: local slot 0 is "this".
    double adjust(long items, double unitPrice) {
        double total = items * unitPrice;
        return total;
    }

    public static void main(String[] args) {
        long count = 3L;
        double price = 2.5;
        double result = weighted(count, price, 1);

        System.out.println("result = " + result);
        System.out.println("adjusted = " + new SlotDemo().adjust(4L, 1.25));
    }
}
```

Compile/run:

```bash
javac SlotDemo.java
java SlotDemo
```

**Exact stdout:**

```text
result = 8.5
adjusted = 5.0
```

At `weighted(3L, 2.5, 1)`, the result is `3 × 2.5 + 1 = 8.5`. At `adjust(4L, 1.25)`, the result is `4 × 1.25 = 5.0`. The values have exact binary representations in this example, so the short display has no noticeable rounding error.

### 7.1. Opening Bytecode with JDK Tools

```bash
# Show bytecode instructions, descriptors, and Code attribute details.
javap -c -v -p SlotDemo

# If you want a more readable local-variable name debug table:
javac -g SlotDemo.java
javap -c -v -p SlotDemo
```

In the output, find the **`static double weighted(long, double, int)`** and **`Code:`** sections. With typical bytecode generated by `javac` from the snippet above, the slot layout is:

```text
weighted(long items, double unitPrice, int fee)
(static, no this)

  index     content
  0, 1      items        (J = long)
  2, 3      unitPrice    (D = double)
  4         fee          (I = int)
  5, 6      total        (D = double)

  max_locals needs at least 7.
  method descriptor: (JDI)D
```

Illustrative bytecode sequence for this body:

```text
lload_0       // read long at local 0–1
l2d           // convert long to double
dload_2       // read double at local 2–3
dmul          // multiply two doubles
iload 4       // read int at local 4
i2d           // convert int to double
dadd          // add
dstore 5      // store total at local 5–6
dload 5       // load total
dreturn       // return double
```

This is a **logical illustrative excerpt** of the opcodes; actual `javap` also displays offsets, declarations, and other metadata. The exact choice of individual opcodes/slots for variables does not have to be identical across every compiler/version; **the slot-pair rules and opcode semantics are mandatory**.

**Explaining `max_stack`:** before `dmul`, the operand stack contains two `double`s → depth 4. Before `dadd`, there are two `double`s → depth 4. With the illustrative bytecode sequence, `max_stack` is **4**, while `max_locals` is **7**. The two values happen to differ in the example; there is no formula saying "every `long` makes `max_stack` always equal `max_locals`".

### 7.2. Instance Methods Have an Additional `this`

`adjust(long, double)` has the layout:

```text
  local 0        this              (reference, 1 slot)
  local 1–2      items             (long, 2 slots)
  local 3–4      unitPrice         (double, 2 slots)
  local 5–6      total             (double, 2 slots)

  max_locals needs at least 7.
  descriptor: (JD)D
```

In bytecode, `lload_1` must use index 1 for `items`; `dload_3` uses index 3 for `unitPrice`. The instance method needs an extra slot 0 for `this`, even though the descriptor `(JD)D` **does not list `this` as an explicit parameter**.

### 7.3. `main` Also Uses Slots for Parameters and Local Variables

In `main(String[] args)`:

```text
  slot 0        args         (String[] reference)
  slot 1–2      count        (long)
  slot 3–4      price        (double)
  slot 5–6      result       (double)
```

At `invokestatic weighted`, preparing the `long`, `double`, `int` arguments on the **operand stack** is a **different** operation from where they are stored in the **local-variable array** of `main`'s frame. When the `weighted` method is called, the **new** frame has its own parameters at indices 0–4. Indices in the caller's frame are not used as indices in the callee's frame.

## 8. Reading `Code`, `max_locals`, and `LocalVariableTable` Properly

Suppose `javap -v` displays information like:

```text
Code:
  stack=4, locals=7, args_size=3
```

It should be read as follows:

- **`stack=4`**: maximum depth of the operand stack, in JVM calculation units.
- **`locals=7`**: the local-variable array has 7 slots, indices 0–6.
- **`args_size=3`** is summary information presented by `javap` about the number of arguments according to how it reports it; **it does not replace the slot calculation rules**. To know the actual positions, check the descriptor, `static`/instance, and `lload`/`dload` instructions.
- **`LocalVariableTable`**, if present, is used for debug information about local variables. An entry for `long`/`double` indicates the **starting index** along with descriptor `J`/`D`; the entry does not mean the source variable was split into two variables.
- **`StackMapTable`**, if present, is type-state information used for bytecode verification. It is not a copy of all live runtime objects.

Not every `.class` file contains source variable names and `LocalVariableTable`; debug information can be omitted during compilation. Relying only on variable names in `javap` to infer slots will fail when debug metadata is missing. **Opcodes and descriptors** are more reliable for understanding indices.

## 9. Reusing Slots by Live Scope

Two slots reserved for a `long`/`double` do not necessarily remain held until the method ends if the compiler can prove a variable has gone out of scope or is no longer used.

Example:

```java
static void reuse() {
    {
        long left = 10L;
        System.out.println(left);
    }
    {
        int right = 3;
        System.out.println(right);
    }
}
```

Semantically, `left` is no longer in scope when `right` is used. A compiler can reuse a local slot in the second block and still produce valid bytecode. However, **there is no exact guarantee that every version of `javac` will choose a fixed index**, and the JIT may further move values to registers/eliminate unnecessary stores.

Therefore:

- Do not deduce `max_locals` as "the sum of all declared variables".
- Do not deduce actual OS stack size as `max_locals × 4` bytes.
- Do not deduce heap usage or object count because `long`/`double` uses two local slots.
- Do not treat slots as **direct addresses** to read/write arbitrarily like C-style memory.

## 10. Why Are the Verifier and Category 2 Rules Needed?

Bytecode carries explicit operation types: `lload` requires a valid `long` local value at the **starting index**; `dload` requires `double`; `iload` requires `int`. The JVM verifier checks the necessary type/stack conditions before code is accepted for execution as specified. As a result, it is impossible to validate an arbitrary sequence like "store `long` at 0–1, overwrite slot 1 with `int`, and still `lload_0`".

Some errors that can appear when manually creating/editing class files:

| Symptom | Cause to Check |
| --- | --- |
| `VerifyError` at `lload`/`dload` instruction | Local index or type state at that point does not contain a valid category 2 value |
| `VerifyError` or rejected code after writing to the second slot | The remaining part of the slot pair invalidated the `long`/`double` starting at the old index |
| `VerifyError` related to the operand stack | Wrong category `pop`/`swap` usage or inconsistent stack depth/type |
| `ClassFormatError` or verification error due to `Code` attribute | `max_locals`, `max_stack`, index, or class file structure does not satisfy validity conditions |
| Reading `javap` shows parameters "skipping indices" | Usually **follows the rule** that `long`/`double` occupies two slots, not the compiler forgetting a variable |

Specific error names and messages depend on the JVM version and bytecode. You cannot produce a `VerifyError` example with normal valid Java source: `javac` actively generates compliant bytecode. This kind of type verification error typically occurs when a class file is edited incorrectly, a bytecode generator/instrumentation is buggy, or a class is otherwise incompatible.

## 11. Common Misconceptions

1. **"`long` has two slots, so it is two 32-bit variables."** False. It is **one category 2 `long` value**, occupying two local-variable slots in the JVM model.
2. **"`lload_1` reads the second half of `lload_0`."** False. It starts reading a `long` at index 1 and is only valid if a `long` value is established at pair **1–2**.
3. **"A `double` variable always requires 8 real bytes in the native stack frame."** Cannot be concluded from the JVMS alone. Implementation and optimization are the JVM's responsibility.
4. **"Two slots must start at an even index."** False. `this` at index 0 causes the first `long` parameter of an instance method to usually start at **1**.
5. **"`static` and instance methods have the same parameter indices."** False. Instance methods reserve slot 0 for `this`.
6. **"`max_locals` counts Java variables."** False. It counts **slots**, including receiver, parameters, and bytecode local storage; the compiler can reuse them.
7. **"`max_stack` and `max_locals` are both cell counts in the same array."** False. They are two different data regions of a frame.
8. **"`long[]` has two elements for each number."** False. Two slots apply to the local-variable array, not Java array indices.
9. **"A `long` on the operand stack is two `int` values to `pop` twice."** False. It is one category 2 value, only manipulated via appropriate opcodes.
10. **"Using `int` instead of `long` to save one slot definitely improves performance."** No such conclusion exists. Choose types based on value range/precision; actual performance must be measured in the specific workload.

## 12. Self-Check Questions with Answers

**Question 1.** How many slots does the method `static void foo(double x, int y, long z)` use for parameters, and what are the individual indices?

**Answer:** `x` uses **0–1**; `y` uses **2**; `z` uses **3–4**. In total, at least **5 slots** are needed to hold the parameters.

**Question 2.** If `foo` is changed to an instance method with the same parameter list, what is the index of `z`?

**Answer:** `this` is at **0**; `x` is at **1–2**; `y` is at **3**; `z` is at **4–5**. The starting index of `z` is **4**.

**Question 3.** `static long sum(long a, long b)` only needs to return `a + b`. If the operand stack holds `a` and `b` at the same time, what is the depth in units?

**Answer:** **4**: two `long` values, each category 2 value contributing two units.

**Question 4.** Why cannot `lload 2` and `lload 3` be arbitrarily used to fetch the "two halves" of a `long` stored starting at index 2?

**Answer:** `lload 2` fetches the **entire** `long` value occupying pair **2–3**. `lload 3` instead requires a valid `long` value starting at **3** (i.e., pair **3–4**), which is completely different, and the second half cannot be used as a separate value.

**Question 5.** An instance method containing `long` and `double` results in `max_locals = 7`. Does that prove there are exactly 7 source variables or 28 bytes of physical memory?

**Answer:** **No.** `max_locals` is the number of abstract slots; the receiver and category 2 values change the slot count, the compiler can reuse slots, and the runtime has the right to choose an optimal representation.

## Conclusion

In a JVM frame, `long` and `double` are **category 2 values**: each value occupies **two consecutive local-variable slots**, addressed by the **lower index**; the second index is not a variable that can be read independently. On the operand stack, each such value also counts as **two depth units**, even though it remains one logical operand. Distinguishing the two data regions, remembering slot 0 for `this` in instance methods, and using `javap -c -v` to inspect `max_locals` and opcodes help you read bytecode accurately without making assumptions about physical memory.

### References

- [JVMS Java SE 17, §2.6.1 — Local Variables](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.1): slot-pair rules, lower index, second slot, and instance/`static` parameters.
- [JVMS Java SE 17, §2.6.2 — Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.2): value categories, depth measured in units.
- [JVMS Java SE 17, §2.11.1–2.11.2 — Type Categories and Load/Store](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.1): category 1/2 and local access opcodes.
- [JVMS Java SE 17, §4.7.3 — Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals` in a class file.
- [Oracle JDK 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): how to view bytecode and metadata.
