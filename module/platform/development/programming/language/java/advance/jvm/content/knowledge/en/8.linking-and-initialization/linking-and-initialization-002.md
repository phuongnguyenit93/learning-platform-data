# JVM Verification: Format Checking, Control Flow, and Type Safety

Before a Java method is executed, the JVM must have a basis to trust that the bytecode is **structurally valid** and **cannot use the operand stack, local variables, or object references with the wrong types under the static conditions specified by the specification**. This is the responsibility of **class-file verification** — a key part of the **linking** phase in the class loading, linking, and initialization lifecycle.

For example, valid Java source does not allow taking an `int` and arbitrarily using it as a `String`. However, the JVM can also receive class files provided by bytecode generators, instrumentation libraries, or class loaders; it **cannot assume by default that a `.class` file has passed through `javac`**. The verifier checks the relevant constraints to detect classes with faulty, improperly transformed, or invalidly structured code **before** they are permitted to be used according to JVM semantics.

This article thoroughly explains three layers of concepts:

1. **Format checking:** does the class file have the correct binary structure, constant pool, attributes, and format limits?
2. **Static/structural constraints and control-flow checking:** does the bytecode have valid instructions, branch targets, exception handlers, paths, and operand-stack shapes?
3. **Type safety:** on **every possible path** to an instruction, can the verifier prove that local variables, the operand stack, parameters, the receiver, and the return value are type-compatible?

We will also look at **`StackMapTable`**, the difference between `ClassFormatError` / `VerifyError`, a runnable Java 17 example, and how to inspect it in practice with `javap`.

## 1. Where does verification stand in the JVM lifecycle?

The conceptual model in the *Java Virtual Machine Specification* (JVMS):

```text
Bytecode / class representation
          │
          ▼
     Loading (create class/interface representation)
          │
          ▼
        Linking
          ├── Verification
          │      ├── check class file format
          │      ├── check JVM code constraints
          │      └── check types and control flow
          ├── Preparation
          │      └── prepare storage and default values for static fields
          └── Resolution
                 └── resolve symbolic references on runtime demand
          │
          ▼
     Initialization
          └── execute class initialization method <clinit>
              when present and when required by the JVM according to rules
          │
          ▼
   Code executed by interpreter/JIT
```

This is a **conceptual order**, not a requirement that every class be completely resolved before the program starts running. The JVMS allows **resolution to happen on demand**, and loading/linking of other related classes can interleave. An implementation may also organize/defer some checking work according to specification rules, but **must not skip mandatory verification results**.

### 1.1. Distinguishing verification, preparation, resolution, initialization

| Phase | Main question | Example |
| --- | --- | --- |
| **Loading** | Which class loader does the JVM use to identify and create the representation of the class/interface? | Loader finds bytes of `app.Example` |
| **Verification** | Are the class file and internal code valid in format and type state? | `iload` must not read a slot holding a reference |
| **Preparation** | How are static fields prepared according to VM rules? | `static int count` has default prepared value 0, before initialization |
| **Resolution** | Which actual class/field/method does a symbolic reference point to? | `invokevirtual` has a method reference to resolve |
| **Initialization** | Run the class's static initialization code when required? | `static { System.out.println("init"); }` |

**Do not confuse:** the verifier **does not execute `if` branches to test what output the program produces**. It analyzes metadata and **abstract type states**. Whether a call finds the actual method at runtime also involves resolution/linking; a `NoSuchMethodError` due to a missing method is not simply equivalent to a `VerifyError` caused by an operand stack type mismatch.

## 2. First layer: format checking of the `.class` file

A class file has a defined format, starting with `CAFEBABE` and containing the fields `minor_version`, `major_version`, `constant_pool`, `access_flags`, `this_class`, `super_class`, field/method lists, and attributes.

```text
ClassFile
├── magic                  // must be 0xCAFEBABE
├── minor_version
├── major_version
├── constant_pool_count
├── constant_pool[]
├── access_flags
├── this_class / super_class / interfaces[]
├── fields[]
├── methods[]
└── attributes[]
     └── Code attribute of a method with bytecode
          ├── max_stack
          ├── max_locals
          ├── code_length / code[]
          ├── exception_table[]
          └── attributes[]  (e.g., StackMapTable)
```

During **format checking**, the JVM must recognize a valid class-file structure: no missing bytes, no invalid trailing garbage data, correct magic number, fields with valid indices and lengths, and predefined attributes conforming to their constraints. The class-file format issue is also related to JVM version compatibility.

Examples of format errors to think about:

- A `.class` file truncated during copying, missing constant pool bytes.
- `attribute_length` does not match the actual size of a predefined attribute.
- A `constant_pool` entry contains an invalid tag for the recognized format/version.
- A constant pool index points to the wrong kind of entry at a required position.
- The `Code` attribute structure violates the format rules of the class-file version.

**Format checking and bytecode verification are related but not the same concept.** Although both contribute to integrity checking before a class is used, a file with a complete binary structure can still contain **type-unsafe** code.

### 2.1. `major.minor` is not type state

Class file `61.0` corresponds to standard Java 17. A Java 11 JVM may reject it because the class's major version is too new — a version error, not a problem of whether `iadd` has two `int`s on the stack.

The preview class format uses a special minor version rule `65535` in appropriate releases; the `--enable-preview` flag only has specific meaning for the corresponding release, does **not** bypass format checking/type verification, and does **not** allow arbitrarily running class files with higher versions.

### 2.2. Format error outcomes

`ClassFormatError` is the typical error when the class-file representation is malformed. `UnsupportedClassVersionError` reports that the class file has a version unsupported by the JVM or an invalid version/preview situation.

Do not just rely on a single word in a stack trace to "fix" it with `--enable-preview`, increasing heap, or adding dependencies. Look at the **error type**, the related version/constant-pool/attribute message, and the actual class artifact being loaded.

## 3. Second layer: instruction structure and control flow

Each method has bytecode carrying instructions, operands, branches, and exception handlers. The verifier together with structural constraints must ensure execution flow does not jump into **the middle of an instruction**, does not read non-existent operands, and does not create paths that violate bytecode rules.

### 3.1. Control-flow graph (CFG)

A method can be viewed as **basic blocks** — sequences of instructions with defined control entry points. Edges follow:

- Sequential path to the next opcode.
- Conditional jump instructions such as `ifeq`, `if_icmpge`.
- `goto` and the targets of `tableswitch` / `lookupswitch`.
- Paths that can transfer to an **exception handler** when an instruction in a protected region throws an exception.
- Return or throw to terminate a normal/abnormal path, with no normal sequential successor.

Java example:

```java
static int choose(boolean yes, int value) {
    int result;
    if (yes) {
        result = value + 1;
    } else {
        result = value - 1;
    }
    return result;
}
```

Conceptual CFG:

```text
                 [start]
                    │
                 test yes
                 /      \
              true      false
               │          │
         result = v+1  result = v-1
               │          │
               └────┬─────┘
                    ▼
            [join: result is int]
                    │
               return result
```

Both paths set `result` to **`int`** before the join point. Therefore, the instruction loading it onto the operand stack for `ireturn` has a valid type state.

This snippet is **an illustrative method**, not a standalone runnable file; the standalone program example is in section 8.

### 3.2. A branch target must be valid

For bytecode branches:

- The target must lie within `code[]` of the method itself.
- The target must be **the start of an instruction**, not an operand byte or padding.
- Switch instructions have their own encoding (including alignment, default, and jump offsets).
- Exception handler `handler_pc` must also point to a valid starting opcode; protected ranges in `exception_table` must satisfy the rules.
- Control flow and type state at joins must be compatible, not just "the address exists".

Hypothetical example:

```text
0: bipush 100   // opcode at 0, immediate operand at byte 1
2: istore_0

Wrong: goto byte 1
Correct regarding opcode boundary: goto byte 0 or 2 (still needs valid types/flow)
```

This is a diagram of **invalid bytecode** for explanation; it is not possible to generate "goto byte 1" using normal valid Java source syntax. When instrumenting class files, use a bytecode library that handles branch offsets properly instead of manually editing bytes with find/replace.

### 3.3. Operand stack depth must be consistent at join points

Suppose abstract bytecode has two paths to the same label `L`:

```text
path A: stack = [int]
path B: stack = []
L: ireturn
```

`ireturn` cannot receive **two states with different numbers of operands** depending on the incoming path; there is no guarantee an `int` is always present at point `L`.

Another error:

```text
path A: stack = [int]
path B: stack = [reference-to-String]
L: ireturn
```

The two paths have the same number of **elements** but **inconsistent types** for `ireturn`. The verifier must not accept a branch state where an instruction requires `int` but could receive an object reference.

**Not** every branch must have the same stack state at all instructions. Only where control flow converges / typing conditions require compatibility is an appropriate state needed; each basic block can use the operand stack in its own way.

## 4. Third layer: type safety on the operand stack and local variables

The verifier looks at the **abstract type** of each value. It does not need to know whether `x = 12` or `x = 99` at runtime; it needs to prove that `x` at that position is a value with a **verification type** corresponding to the opcode.

Examples:

| Instruction | Primary type precondition | Action |
| --- | --- | --- |
| `iload n` | Local `n` holds an appropriate int-family value | Push `int` onto the operand stack |
| `aload n` | Local `n` holds an appropriate reference | Push reference onto the stack |
| `iadd` | Two `int` values at top of stack | Pop two `int`s, push `int` result |
| `ladd` | Two category 2 `long` values | Pop two `long`s, push one `long` |
| `getfield` | Objectref compatible with field resolution/access; field has valid descriptor | Pop receiver and push field value |
| `putfield` | Receiver and field value have compatible types | Write field with valid type |
| `invokestatic` | Sufficient arguments, types match method descriptor | Consume arguments, push return value onto stack if non-`void` |
| `invokevirtual` | Has objectref receiver and appropriate arguments | Perform instance call |
| `ireturn` | Return descriptor allows int-family and stack has `int` | Normal return, return int-family value |
| `areturn` | Return descriptor is reference type, reference on stack is compatible | Normal reference return |

The table above is only a **description of primary type conditions**; each opcode in the JVMS has more detailed rules regarding access, uninitialized values, constant pool, and frame state.

### 4.1. Why can't an `int` be used like a `String`?

Imagine hypothetical bytecode:

```text
iconst_1
invokevirtual java/lang/String.length:()I
```

The `invokevirtual` instruction needs a compatible **objectref receiver**, but the operand stack only has `int`. That bytecode is **invalid regarding type safety**; the verifier can reject it with `VerifyError`. There is no "implicit cast from int to String" just because the two values happen to have the same machine size.

### 4.2. The local-variable array has path-dependent type state

A local slot can be reused for another value after the old variable is no longer needed, but at **every using instruction**, the verifier must prove the slot has a valid type on all paths reaching it.

Error pattern:

```text
if condition:
    istore_2       // slot 2 is int
else:
    astore_2       // slot 2 is reference

join:
    iload_2        // cannot prove it is always int
```

This pseudocode is not permitted Java source. A normal Java compiler generates code that avoids such invalid states. However, a bytecode generator can produce an unsafe class if it does not compute type states when merging flows.

### 4.3. `long` and `double`: category 2

`long` and `double` are **category 2** values:

- In the local-variable array, each value occupies **two consecutive slots**; `lload n`/`dload n` accesses from the **lower** index.
- On the operand stack, a `long`/`double` occupies **two units of depth**, though it is a single logical value.
- You must not use `pop` (which operates on a category-1 value) to discard "half" of a `long`; an appropriate opcode such as `pop2` is required.
- Writing to the second slot of a local pair can invalidate the category 2 value starting at the first slot.

For example, the method `static long plusOne(long input)` receives `input` in local slots **0–1** and ends with `lreturn`; there are not two `int` parameters just because two slots are used.

## 5. `StackMapTable` and verification by type checking

From class-file **version 50.0 (Java 6)** onward, the JVMS specifies that the verifier uses **verification by type checking** with stack-map frame information. Class-file versions lower than 50.0 use **verification by type inference** according to the legacy specification; for exactly version **50.0**, there is a compatibility exception allowing an implementation fallback under conditions stated by the JVMS. For Java 17 (`61.0`) class files, you must think in terms of **type checking/`StackMapTable`**, not expecting the JVM to infer types the old way for bytecode with missing/invalid metadata.

A `StackMapTable` is an **attribute inside the `Code` attribute** of a method; it helps the verifier check type states at **key control points**, especially basic-block entries.

### 5.1. What does a stack-map frame record?

For a bytecode offset, a stack-map frame describes the abstract types of:

- The local-variable slots that need to be known at that point.
- The values on the operand stack at that point.
- Special information related to uninitialized objects, when needed.

Possible verification types include:

| Verification type | Meaning |
| --- | --- |
| `Integer` | Int-family form in the verifier's type system |
| `Float` | Float value |
| `Long` | Long value, category 2 width |
| `Double` | Double value, category 2 width |
| `Null` | Null reference value |
| `Object(className)` | Reference of an appropriate class/array type |
| `UninitializedThis` | Constructor receiver that has not completed initialization |
| `Uninitialized(offset)` | Uninitialized object, tied to the `new` instruction at that offset |
| `Top` | Top/unusable information according to verification type system rules, **not** a Java class named `Top` |

These are **verification types**, not synonymous with Java Reflection types or runtime values. For example, source `boolean`/`byte`/`char`/`short` are commonly represented via the `Integer` verification type at many bytecode locations.

### 5.2. Not one stack-map frame per instruction

The compiler does not need to write a `StackMapTable` entry for **every opcode**. The intent of the format is that frames appear at the start of basic blocks that need a confirmed state; the verifier applies **type transitions** to deduce the state after each instruction from the block's starting state.

Space-saving forms:

- `same_frame`: local state stays the same, operand stack is empty at the point of application.
- `same_locals_1_stack_item_frame`: local state stays the same, stack has one item.
- `append_frame` / `chop_frame`: add/remove information about locals.
- `full_frame`: describes all necessary locals and stack state.

These are **encoding forms of stack-map entries**, not bytecode instructions executed at runtime like `iadd` or `goto`.

### 5.3. What if `StackMapTable` is not present?

According to the JVMS, a class file from version 50.0 onward **may omit an explicit `StackMapTable` attribute**; in that case it is interpreted equivalently to an **implicit StackMapTable with 0 entries**. That does **not** mean the verifier is disabled.

A linear method without complex joins may be valid with few or no entries. Conversely, a method with branch targets needing appropriate frames where the class file omits required information can be rejected with `VerifyError`, for example a message meaning "Expecting a stackmap frame at branch target".

### 5.4. Reading StackMapTable from `javap`

```bash
javac --release 17 VerificationDemo.java
javap -c -v -p VerificationDemo
```

In the output, look for blocks:

```text
Code:
  stack=..., locals=..., args_size=...
  ...
StackMapTable: number_of_entries = ...
  frame_type = ...
```

The actual `number_of_entries`, `frame_type`, and offsets depend on the compiled class and compiler; **do not guess them from Java source line numbers**.

## 6. The join problem: "safe on ALL paths"

The verifier must check that states entering a given block satisfy the **types and operand stack depth** required by the block. It does not just test one branch that "looks right".

Valid pattern:

```text
                 test
               /      \
path A: stack=[int]   path B: stack=[int]
               \      /
                 join
                 ireturn
```

Both states allow `ireturn` with `int`.

Invalid pattern:

```text
                 test
               /      \
path A: stack=[int]   path B: stack=[String ref]
               \      /
                 join
                 ireturn    // no guarantee of int
```

If actual Java source writes:

```java
static int f(boolean flag) {
    int x;
    if (flag) {
        x = 10;
    } else {
        x = 20;
    }
    return x;
}
```

`javac` will generate valid bytecode and appropriate stack-map metadata. It does not fix errors by "automatically casting String to int" if a bytecode generator tries to create inconsistent incoming paths.

### 6.1. Joining reference types does not necessarily preserve the exact concrete class

For example, one branch provides a `String` reference, the other a `StringBuilder`; the program can be valid if the code at the join point only requires **a common supertype** (such as `Object`), according to the assignability rules of the verification type system.

```java
static int describe(boolean asText) {
    Object value;
    if (asText) {
        value = "x";
    } else {
        value = new StringBuilder("y");
    }
    return value.toString().length();
}
```

This is an **illustrative method**. The source declares `Object` so the compiler generates bytecode where the join does not need to know whether the concrete object is `String` or `StringBuilder`, only needing a compatible reference type to call `Object.toString()`.

**Do not conclude** that all branch paths must have the exact same runtime class. What needs to be proven is **assignability and a valid frame type state according to the target instruction**.

## 7. Constructors and uninitialized references

One of the verifier's important roles is preventing code from using an object **before instance initialization completes**.

Source example:

```java
Object obj = new Object();
```

Illustrative bytecode:

```text
new java/lang/Object       // creates uninitialized reference
dup
invokespecial java/lang/Object.<init>:()V
astore_1                   // stores initialized reference
```

In the verifier type system, the reference right after `new` has the form **`Uninitialized(offset)`** tied to the bytecode offset of the instruction that created it. When `<init>` is validly called and completes, the state is updated so it can be used as an initialized reference.

For the class's own constructor, local slot 0 can start as **`UninitializedThis`** and must obey the rules regarding calling `this(...)` or `super(...)`.

**Invalid bytecode:** taking an uninitialized reference and arbitrarily calling an instance method like `toString()`, or returning that reference in a way that violates the rules, before a valid constructor completes. This kind of error cannot be "legalized" simply by casting or editing constant pool names.

### 7.1. Type safety does not mean `NullPointerException` cannot occur

The verifier proves **form and types**, not all runtime conditions. If the receiver type is a valid reference but **the value is null**, `invokevirtual` can still throw `NullPointerException` at runtime.

Similarly, the verifier does not guarantee:

- Arrays are always indexed within bounds (`ArrayIndexOutOfBoundsException`).
- Integer division never uses 0 (`ArithmeticException`).
- The program does not run out of heap (`OutOfMemoryError`).
- Two threads do not experience a race condition or deadlock.
- A cast from `Object` to `String` always succeeds at runtime (`ClassCastException`).
- SQL queries or business logic produce correct results.

**"Type-safe bytecode" is not synonymous with "error-free application".**

## 8. Runnable Java 17+ example: tracing branches, handlers, and category 2

Create the file **`VerificationDemo.java`**:

```java
public class VerificationDemo {

    static int choose(boolean positive, int value) {
        int result;
        if (positive) {
            result = value + 1;
        } else {
            result = value - 1;
        }
        return result;
    }

    static int safeDivide(int numerator, int denominator) {
        try {
            return numerator / denominator;
        } catch (ArithmeticException ex) {
            return -1;
        }
    }

    static long plusOne(long value) {
        return value + 1L;
    }

    public static void main(String[] args) {
        System.out.println("choose true = " + choose(true, 4));
        System.out.println("choose false = " + choose(false, 4));
        System.out.println("divide = " + safeDivide(10, 0));
        System.out.println("long = " + plusOne(41L));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 VerificationDemo.java
java VerificationDemo
```

**Deterministic stdout:**

```text
choose true = 5
choose false = 3
divide = -1
long = 42
```

At `choose(true,4)`, `result=4+1=5`; at `choose(false,4)`, `result=4-1=3`. `safeDivide(10,0)` throws `ArithmeticException` at `idiv` and the catch returns `-1`; `plusOne(41L)` uses category-2 arithmetic and returns `42L`.

### 8.1. What the bytecode shows

```bash
javap -c -p VerificationDemo
javap -v -p VerificationDemo
```

When reading **`choose(boolean,int)`**, expect to see logic like:

```text
iload_0                 // boolean is handled as int-family
ifeq ELSE
  iload_1
  iconst_1
  iadd
  istore_2
  goto JOIN
ELSE:
  iload_1
  iconst_1
  isub
  istore_2
JOIN:
  iload_2
  ireturn
```

This is an **opcode diagram without offsets** for explanation, not verbatim `javap` output; in actual output the `ELSE`/`JOIN` labels are numeric bytecode offsets. Both branches place an `int` into local 2 before `iload_2`.

In **`safeDivide(int,int)`**, look for `idiv`, an **Exception table** with `Class java/lang/ArithmeticException`, and the handler section receiving the exception reference via `astore` then `ireturn`ing `-1`. Upon entering the handler, the operand stack has been reset to **one reference to the exception** — different from the normal flow returning an `int`.

In **`plusOne(long)`**, you typically see:

```text
lload_0
lconst_1
ladd
lreturn
```

`long value` is a category 2 value at local slots 0–1. `ladd` and `lreturn` require a state of the appropriate `long` type; you cannot replace `lreturn` with `ireturn` and expect the verifier to convert the type automatically.

### 8.2. Observing the `StackMapTable` of the branches

Use:

```bash
javap -v -p VerificationDemo
```

Look for `StackMapTable` in the sections for `choose` and `safeDivide`. At branch targets and handlers, stack-map entries help describe the type states:

- At the `else` branch entry: parameters `positive` and `value` have appropriate types, stack is empty under typical bytecode layout.
- At `JOIN`: local `result` is `int` on all valid paths, so it can be `iload`ed and `ireturn`ed.
- At the `ArithmeticException` handler: the operand stack at the handler has one exception reference, not the two `int` operands left over from `idiv`.

The exact entry count, frame forms, and offsets are decided by the compiler. `javap -v` displays **class metadata**, not the JVM recording a live stack of an executed call.

## 9. An exception handler is a special control-flow edge

`exception_table` is inside the `Code` attribute, with fields:

```text
start_pc, end_pc, handler_pc, catch_type
```

- The handler protects the region **`[start_pc, end_pc)`** (start-inclusive, end-exclusive).
- `handler_pc` points to the first instruction of the handler.
- `catch_type` points to an appropriate exception class or is **0** to match any Throwable.
- Entries are checked in **order**; the first entry matching pc/type is used.

At handler entry, the JVM sets the operand stack to **one exception object reference**, clearing the old operands in that frame. This is an important principle for type state checking at handlers.

Example of a bytecode design error:

```text
TRY:                  // push two ints before operation
  iload_0
  iload_1
  idiv                // may throw ArithmeticException

HANDLER:
  iadd                // WRONG: two ints are not available at handler entry
```

When transferring into the handler, the stack is `[exceptionRef]`, so `iadd` at the start of the handler does not have two compatible `int`s. A valid handler usually starts with `astore` to take the reference, then computes the value to return.

## 10. Common verification errors with bytecode generators

| Bytecode error | Why is it unsafe/invalid? |
| --- | --- |
| `iadd` with only one `int` on the stack | Stack underflow / missing operand |
| `iadd` encountering a `String` reference | Wrong operand types |
| `iload_2` when local slot 2 is not guaranteed to hold `int` on all paths | Using a local without an appropriate type state |
| Branching into an operand byte of another instruction | Target is not an opcode boundary |
| Two join paths having incompatible stack heights | No valid block entry state |
| `ireturn` from a method returning `long` | Return opcode/type violates method descriptor |
| `invokevirtual` with an `int` receiver | Receiver must be a compatible reference |
| Calling a method with argument count/types differing from descriptor | Operand stack does not provide the right types |
| `lload` from a pair of slots that was overwritten | No longer a valid `long` value at index |
| Using an uninitialized object reference as an initialized object | Violates `new`/`<init>` initialization rules |
| Handler starting with an opcode requiring two `int`s | Handler entry stack has one exception reference |
| Modifying branch offsets without updating stack maps | StackMapTable is no longer consistent with the new CFG |

**Do not try to create these errors with normal Java source:** `javac` proactively generates valid code or rejects ill-typed source. These errors usually make sense when inspecting modified bytecode, code generated by another compiler/transformer, or a corrupted class file.

## 11. `VerifyError`, `ClassFormatError`, and other linkage errors

| Error type | Common context | What to investigate |
| --- | --- | --- |
| **`ClassFormatError`** | Class file data does not meet binary/attribute format | Is the artifact corrupted, constant pool or lengths wrong? |
| **`UnsupportedClassVersionError`** | Class-file version/preview not supported by runtime | `java -version`, major/minor, preview flags |
| **`VerifyError`** | Bytecode or type state does not satisfy verification rules | Opcodes, branch targets, StackMapTable, exception table |
| **`NoClassDefFoundError`** | Required class is not defined/found in the corresponding context | Classpath/module path, dependencies, prior init error |
| **`NoSuchMethodError` / `NoSuchFieldError`** | Symbolic reference cannot find expected member during resolution | JAR versions and binary compatibility |
| **`IllegalAccessError`** | Access check/linkage violates runtime access permissions | Visibility, modules, nestmates, artifact versions |
| **`ExceptionInInitializerError`** | Static initialization `<clinit>` failed under corresponding conditions | Static initialization code and underlying cause |
| **`ClassCastException` / `NullPointerException`** | Wrong type cast or reference value during execution | Data/runtime logic; do not assume verifier failed |

The table above is a **diagnostic guide**; the exact error also depends on the class loader, time of detection, and implementation. `VerifyError`/`ClassFormatError` belong to errors related to class file validity, but not every program error is caused by the verifier.

### 11.1. A `VerifyError` message does not mean the JDK "does not support Java source"

If Java 17 code compiles with `javac --release 17` but at runtime shows `VerifyError` in a library class, check:

1. Which **`.class` file** is the runtime actually loading (are there copies in multiple JARs?).
2. Was that class modified by a Java agent/instrumentation transformer?
3. Did the transformer update **branch offsets, `StackMapTable`, and exception handler ranges**?
4. Are `java -version` and the build target correct?
5. Did the error only occur after upgrading the JDK or changing a framework/bytecode library version?

Do not assume the error is due to small heap size or use `--enable-preview` to "dodge" verification. Enabling preview does not legalize invalid bytecode.

## 12. Limits of the verifier: what it does NOT prove

The verifier is designed to guarantee **JVM type and structural constraints**, not to be a tool that proves a program is correct in all aspects.

| What the verifier can protect statically | What must still be handled at runtime or in the application |
| --- | --- |
| Instruction receives operands of valid types | `NullPointerException` when reference is valid but value is null |
| A local is read with an appropriate type | Business logic computes wrong results even when types are right |
| Valid branch targets and safe frame joins | Deadlock or race condition between threads |
| Return opcode matches method descriptor | Input data exceeds business limits |
| Valid object initialization rules | `ClassCastException` when an actual downcast fails |
| Operand stack is not imbalanced in violation of rules | `OutOfMemoryError` when memory is insufficient |
| Basic class-file structure is valid enough to use | SQL injection, application authorization, or logic vulnerabilities |

For example, `checkcast java/lang/String` is an opcode with **valid type safety** when the input is an object reference, but if the actual object is an `Integer`, **runtime** can throw `ClassCastException`. The verifier is not required to guess what dynamic type every actual object will have.

Similarly, array stores still have runtime checks per specification for corresponding cases; bytecode verification does not replace all dynamic checks.

## 13. Working with ASM, Byte Buddy, and Java agents

When writing a bytecode generator or transformer, the biggest practical problem is **keeping the control-flow graph and stack-map frames compatible**. A seemingly simple edit — inserting logging at the start of a method, adding a `try/catch`, replacing an opcode, expanding a `switch` — can:

- Shift bytecode offsets and branch targets.
- Change basic-block entry positions.
- Change the operand stack state or local-variable types at join points.
- Make `max_stack` or `max_locals` insufficient.
- Make the exception table or frame offsets mismatch the new code.
- Violate uninitialized reference rules around `new`/`<init>`.

Checklist for safe modification:

1. Identify the class-file version and method descriptor before transforming.
2. Maintain accurate type states of the operand stack/locals when inserting instructions.
3. Rebuild/update jump labels, try/catch ranges, and stack-map entries using supported tool features.
4. Ensure `max_stack` and `max_locals` are sufficient for all executable paths.
5. Do not violate rules for uninitialized objects or monitors.
6. Run tests on the right target JDK, including branches and exception paths.
7. Use `javap -c -v` to inspect the **post-transformation** class file, not just the original `javac` output.

Some libraries like ASM have features to automatically compute stack-map frames/max stack when configured appropriately, but you must follow version-specific guidelines; there is no "auto-fix all invalid bytecode" option for every transformation.

**Do not** disable the verifier as a way to resolve production incidents. It is an important part of the safety guarantees of the JVM model; instead, fix the invalid class file/transformer/toolchain.

## 14. Three steps to read a real error

### Scenario A: `VerifyError: Bad type on operand stack`

Diagnostic direction:

- Find the class and method mentioned by the error, and identify the instruction/offset.
- Read `javap -c -v -p ClassName` of the artifact being loaded.
- Check the opcode at the offset, the `StackMapTable` type state, and the branches leading there.
- Cross-check the method descriptor and the types of the receiver/arguments.

Do not conclude "JVM runtime data holds the wrong type due to a race"; usually you need to investigate **bytecode/type state**.

### Scenario B: `VerifyError: Expecting a stackmap frame at branch target`

Especially common when a tool inserts `goto` or adds a basic block without updating `StackMapTable`. You need to check the offsets/frames of the class-file version in use. Adding a frame at a guessed location without analyzing the state can continue to fail; use a generator capable of computing valid frames.

### Scenario C: `ClassFormatError` due to malformed attribute

The error may originate from a packaging tool/transformer writing an incorrect attribute length or constant pool. Inspect the input artifact bytes and the class-generating program, not just `java -version`. If the class has been truncated, it cannot be handled by a `catch` in `main` because the error may appear before the method to run is even loaded.

## 15. Common misconceptions

1. **"`javac` compiled it, so the JVM doesn't need verification."** False. The JVM can receive bytecode from many sources and must perform checks according to the class-file/linking contract.
2. **"Verification and initialization are the same."** False. Verification checks validity; initialization runs `<clinit>` code under its own conditions.
3. **"The JVM verifier runs every branch with sample data."** False. It analyzes structure and **abstract type states**, not test cases.
4. **"Seeing `StackMapTable` means it is a live Java stack trace."** False. It is metadata for type checking at bytecode offsets.
5. **"Every instruction must have its own stack-map frame."** False. Frames represent necessary state points; many instructions are checked via type transitions.
6. **"No explicit `StackMapTable` definitely means the class is not verified."** False. For version 50+, there is an implicit zero-entry stack map rule.
7. **"A join only needs the same operand stack length, regardless of types."** False. Types must also be compatible.
8. **"All references on two branches must have the same runtime class."** False. Assignability may allow an appropriate common supertype.
9. **"`iadd` can add two `Object`s because they have machine addresses."** False. The `iadd` opcode requires `int`.
10. **"`long` uses one local slot like `int`."** False. `long`/`double` use two local slots; they are category 2.
11. **"A `new`-created object can call any instance method right before `<init>`."** False. Uninitialized references are constrained.
12. **"`VerifyError` means Java source syntax is wrong."** False. The compiler may have succeeded, while the bytecode was transformed/malformed.
13. **"`--enable-preview` makes the JVM skip type safety checks."** False. The flag only enables supported preview features for the exact release.
14. **"The verifier guarantees there will never be a `NullPointerException`."** False. Null is a runtime condition.
15. **"The verifier fixes broken bytecode during loading."** False. If bytecode does not satisfy constraints, the class is rejected; there is no guarantee the JVM fixes source/offsets.
16. **"A JIT compilation error is a `VerifyError`."** Not necessarily. Verification is a separate semantic step from JIT optimization/runtime execution.
17. **"A `StackMapTable` metadata error can be solved by increasing `-Xmx`."** False. This is a class-file/type-state issue, not insufficient heap.

## 16. Self-check exercises (with answers)

**Question 1.** For `static int f(boolean b, int n)`, both branches assign `int result` and then return. Why is the join valid?

**Answer:** At the join, the local slot for `result` has a valid `int` type on both paths. `iload` and `ireturn` therefore have the right operand types.

**Question 2.** If branch A leaves stack `[int]` and branch B leaves stack `[String ref]` and both run `iadd`, what is the problem?

**Answer:** `iadd` requires **two `int`s**, while neither path guarantees the right types/number of operands. The state at the join and the instruction precondition are invalid; the bytecode can be rejected with `VerifyError`.

**Question 3.** Is `StackMapTable` used for debugging local variable names or for the verifier?

**Answer:** It serves **verification by type checking**, containing type state information at bytecode offsets; it does not replace `LocalVariableTable` for debugging variable names.

**Question 4.** A 61.0 class has no `StackMapTable` shown in `javap`. Is it certain the JVM skips verification?

**Answer:** No. The JVM interprets an implicit zero-entry stack map when the attribute is absent; the method is only valid if it meets the corresponding verification conditions.

**Question 5.** Why is a reference from `new` not yet treated as an initialized object?

**Answer:** The verifier tracks `Uninitialized(offset)` / `UninitializedThis` and requires valid constructor initialization via `<init>` before constrained uses.

**Question 6.** When an exception handler starts, what does the operand stack contain?

**Answer:** **One exception reference**, not the old operands of the instruction that threw the exception.

**Question 7.** The verifier accepted a method containing `idiv`. Does that guarantee the divisor is non-zero at runtime?

**Answer:** No. The verifier verifies the `int` type of the operands; division by 0 can still throw `ArithmeticException` during execution.

**Question 8.** Are `ClassFormatError` due to a truncated class file and `VerifyError` due to a missing stack-map frame the exact same kind of error?

**Answer:** No. One belongs to **format/data structure**, the other belongs to **bytecode verification/type-state**; the specific messages and investigation steps differ.

**Question 9.** A Java agent just added a `goto`, and the method no longer verifies. What should be checked first?

**Answer:** Instruction offsets, branch targets, basic-block entries, `StackMapTable` and type states, `max_stack`/`max_locals`; fix the transformer, do not disable the verifier.

## 17. Summary of the analysis flow

```text
Class bytes
    │
    ▼
Format check
  ├─ magic, version, constant pool, length, attributes
  └─ invalid → class rejected
    │ valid
    ▼
Bytecode / control-flow structure
  ├─ opcode, operands, branch/handler targets
  └─ invalid → class rejected
    │ valid
    ▼
Type checking
  ├─ method descriptor → initial type state
  ├─ StackMapTable → state at basic block entries
  ├─ instructions → state transitions
  ├─ joins → stack height and type assignability
  ├─ constructors → uninitialized reference constraints
  └─ invalid → VerifyError
    │
    ▼
Code can be used by the JVM according to loading/linking rules
    │
    ▼
Runtime checks still exist (null, bounds, casts, memory, ...)
```

**Remember:** Verification does not only ask "is the class file readable?", but also must determine **safe control flow and type state on all paths to an instruction**. `StackMapTable` provides type-state metadata so the JVM can check efficiently; `VerifyError` warns of code/type constraint errors, while `ClassFormatError` leans toward class file structure. After verification succeeds, the application **can still** encounter runtime exceptions or business bugs. That is the boundary between **VM guarantees** and **application code responsibility**.

### References

- [JVMS Java SE 17 — ClassFile structure (4.1)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 17 — `StackMapTable` attribute (4.7.4)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.4).
- [JVMS Java SE 17 — Format Checking (4.8)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.8).
- [JVMS Java SE 17 — Constraints on JVM Code (4.9)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.9).
- [JVMS Java SE 17 — Verification of class Files (4.10)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10).
- [JVMS Java SE 17 — Linking/Verification (5.4.1)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.1).
- [Oracle Java SE 17 — `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
