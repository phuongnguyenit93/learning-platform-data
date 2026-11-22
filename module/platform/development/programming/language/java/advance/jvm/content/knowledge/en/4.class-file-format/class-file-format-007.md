# StackMapTable and Type Information for Bytecode Verification

## 1. The Problem: How Does the JVM Check a Bytecode Method?

Java source code is type-checked by the compiler, but a `.class` file can come from many sources: `javac`, Kotlin/Scala, code generators, bytecode transformers, or files loaded from an untrusted source. The JVM **cannot rely solely on a promise that the file was compiled correctly**. Before running, it must apply structural and type rules of the class file, helping detect invalid bytecode.

Consider a hypothetical scenario:

```text
Location A: operand stack has int
       |
       | jump to B
       v
Location B: invokevirtual instruction of an instance method
```

`invokevirtual` requires a suitable **object reference**, and cannot take an `int` as the receiver. Even if the bytecode is syntactically encoded correctly, such a type flow must be rejected during verification.

With branch instructions, the situation is even harder: **multiple execution paths can converge at the same bytecode offset**. The JVM needs to know whether those paths carry the same valid type state. `StackMapTable` provides **type-state checkpoints encoded in the class file** so that verification can check bytecode transitions efficiently and on a clear basis.

```text
Java Source Code
   |
   v
javac / compiler / bytecode generator
   |
   v
.class
  ├── constant pool
  ├── method_info
  └── Code
       ├── max_stack, max_locals
       ├── code[] (bytecode)
       ├── exception_table
       └── attributes[]
            └── StackMapTable (if present)
                  ├── frame at control point 1
                  ├── frame at control point 2
                  └── ...
   |
   v
JVM: load class → verify structure and types → execute when valid
```

**Key point:** `StackMapTable` does not contain source code, does not replace bytecode, and does not “run” in place of the JVM. It describes the **expected verification types** of **local variables** and the **operand stack** at key locations of a method.

## 2. Distinguishing Three Layers of Information

To read `StackMapTable` without confusion, it is necessary to separate three concepts:

| Concept | Content | What it is used for |
| --- | --- | --- |
| **Type in the Java language** | `boolean`, `byte`, `char`, `int`, `String`, generic type… | The compiler checks the validity of source code |
| **Type of JVM values and instructions** | `int`, `long`, `float`, `double`, `reference`, category 1/2; opcodes such as `iload`, `aload` | The JVM executes and follows the opcode contract |
| **Verification type** | Abstract types used to check the safety of bytecode flow: `Integer`, `Object`, `Null`, `Uninitialized`… | The bytecode verifier checks type states and transitions between them |

For example, at the bytecode level, `boolean`, `byte`, `char`, and `short` are manipulated through `int`-related types and instructions in many contexts; `StackMapTable` does not have a separate tag for each of those small primitives. A `String` reference in a frame is described by `Object_variable_info` pointing to the appropriate class in the constant pool; whereas a null reference has its own verification tag.

**A verification type is not a Java type object that can be declared in code.** `UninitializedThis` is a verifier state inside a constructor; it is not a declared type of the Java language. Similarly, `Top` is a special verification type, not the `java.lang.Object` class and not a principle that “every value fits.”

## 3. What Is a Stack Map Frame?

A **stack map frame** describes the type state at **a bytecode offset** inside **a method**. The state consists of:

- **Local variables:** the types of the local variable slots in the method's execution frame.
- **Operand stack:** the types of the values currently on the operand stack at that offset.

Abstract example:

```text
Method: static String pick(boolean flag)

At the start (initial frame):
  locals       = [Integer]       // flag: boolean is represented as verifier type Integer
  operandStack = []

After going through two branches and converging:
  locals       = [Integer, Object(java/lang/String)]
  operandStack = []              // before loading value to return

Instruction aload_1:
  locals       = [Integer, Object(java/lang/String)]
  operandStack = [Object(java/lang/String)]

Instruction areturn:
  takes a compatible reference from operand stack to return
```

This diagram only illustrates **expected types**, not the exact bytecode dump of every compiler. A compiler may choose different slot layouts, branches, and frames, but must produce a valid class file.

### 3.1. Why Look at Both Locals and Operand Stack?

The JVM is a **stack-based virtual machine**. The `iadd` instruction pops two `int`-compatible values from the operand stack; `aload_1` reads a reference value from local slot 1 and pushes it onto the operand stack. `invokestatic`, `invokevirtual`, `ireturn`, and `areturn` all impose requirements on the count and types of these values.

A state may be valid for `ireturn` but invalid for `areturn`. Checking each opcode requires tracking the kinds of values before and after abstract execution (*type transition*).

### 3.2. Not Every Instruction Has a Stored Stack Map Frame

`StackMapTable` typically provides frames at the **start of basic blocks**, especially **branch targets** and the **start of exception handlers**, according to specific verification constraints. Instructions between these points are checked by the verifier by applying the type-transition rules of each opcode.

Therefore:

- `max_stack` is the operand stack depth limit, **not** a list of type states.
- `max_locals` is the local variable slot limit, **not** the contents of `StackMapTable`.
- A frame can have an empty operand stack.
- A method may have no explicit `StackMapTable` entries, if the default type state and bytecode flow are sufficient for verification under the corresponding class file rules.

## 4. Location and Structure of `StackMapTable` in a `.class` File

According to **JVMS `4.7.4`**, `StackMapTable` is a **variable-length attribute** located **inside the attributes table of the `Code` attribute** of a method that has bytecode. Inside a `Code` attribute there is at most **one** `StackMapTable`.

Abstract binary format:

```text
StackMapTable_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 number_of_entries;
    stack_map_frame entries[number_of_entries];
}
```

Meaning:

| Field | Meaning |
| --- | --- |
| `attribute_name_index` | Index into `CONSTANT_Utf8_info` containing the string `StackMapTable` in the constant pool |
| `attribute_length` | Length of the attribute body, excluding the first 6 bytes of the attribute header |
| `number_of_entries` | Number of **explicit** frames in `entries` |
| `entries[]` | Frames ordered by bytecode position; can be delta-encoded and inherit information from the previous frame |

Some important misconceptions:

1. **Do not arbitrarily place `StackMapTable` at the class level.** It is an attribute of a specific `Code` attribute, meaning it is tied to verifying **one method**.
2. **The first frame of the method is not recorded in `entries[0]`.** The first state is an **implicit initial frame**, computed from the method descriptor and related rules; `entries[0]` represents the next explicit frame.
3. **A missing attribute does not necessarily mean a broken class.** For class file version **50.0 or higher**, if `Code` has no `StackMapTable`, then by specification there is an **implicit stack map attribute with `number_of_entries = 0`**. The class passes verification only if the method's code flow conforms to what is allowed in this case.
4. **A frame does not speak about concrete values.** For example, recording `Integer` means the slot must hold a value of verifier type Integer; it does not record whether 10 or 20 is stored at runtime.

### 4.1. Verification Types and Tags in `verification_type_info`

Each slot is described by a `verification_type_info` structure. The tags according to JVMS:

| Tag | Structure Name | Role |
| ---: | --- | --- |
| 0 | `Top_variable_info` | `Top` state used in slot checking and abstract types; not a Java object |
| 1 | `Integer_variable_info` | `int` value in the verification model (including small primitive values when represented accordingly) |
| 2 | `Float_variable_info` | `float` value |
| 3 | `Double_variable_info` | `double` value |
| 4 | `Long_variable_info` | `long` value |
| 5 | `Null_variable_info` | Null reference |
| 6 | `UninitializedThis_variable_info` | `this` not yet fully initialized in a constructor |
| 7 | `Object_variable_info` | Reference with a class, interface, or array type specified via the constant pool |
| 8 | `Uninitialized_variable_info` | Reference to an object just created with `new` whose corresponding constructor has not yet been called; tied to the `new` instruction offset |

**Tag 7:** the `Object_variable_info` structure contains `cpool_index` to a valid `CONSTANT_Class_info`. The object can be a class, interface, or array type depending on the corresponding information; do not interpret the word “Object” in the structure name as always meaning `java/lang/Object`.

**Tag 8:** the `Uninitialized_variable_info` structure contains `offset` referring to a relevant **`new` instruction**. This allows the verifier to distinguish uninitialized objects created at different `new` instructions.

**`long` and `double`:** each value occupies **two slot units** in the local variables/operand stack model; the frame table encodes them according to specific rules to match slots. Do not assume `number_of_locals` always equals the exact slot count of `max_locals` because entries representing `long` or `double` occupy two slots.

### 4.2. Seven Kinds of `stack_map_frame`

Because type states between basic blocks are often similar, the class file format has compressed forms:

| Frame Kind | `frame_type` Code | Content |
| --- | --- | --- |
| `same_frame` | 0–63 | Locals same as previous frame; operand stack empty; offset delta encoded in the tag |
| `same_locals_1_stack_item_frame` | 64–127 | Locals unchanged; operand stack has one item; delta encoded in the tag |
| `same_locals_1_stack_item_frame_extended` | 247 | Same as the 1-stack-item form, but `offset_delta` is written as `u2` |
| `chop_frame` | 248–250 | Operand stack empty; drops 1–3 trailing locals compared to the previous frame |
| `same_frame_extended` | 251 | Locals unchanged, stack empty; delta written separately as `u2` |
| `append_frame` | 252–254 | Operand stack empty; appends 1–3 locals compared to the previous frame |
| `full_frame` | 255 | Explicitly encodes the full locals and operand stack for the new frame |

The tag range **128–246** is reserved in the format, not a frame kind readers can use arbitrarily.

**Compressing frames does not lose information needed by the verifier.** For example, if locals do not change and the stack is empty, `same_frame` only needs to record the tag; to understand it fully, reconstruct it from the previous frame's state.

### 4.3. `offset_delta` Is the Distance Between Frames, Not an Absolute Offset in Every Case

Explicit frames are encoded in **increasing order of bytecode offset**. Formula to determine position:

- **First explicit frame:** `offset = offset_delta` (relative to the implicit initial frame).
- **Subsequent explicit frames:** `offset = previous_offset + offset_delta + 1`.

Model example:

```text
Initial frame : offset = 0 (implicit)
Explicit #1   : offset_delta = 8   → offset 8
Explicit #2   : offset_delta = 4   → offset 8 + 4 + 1 = 13
Explicit #3   : offset_delta = 5   → offset 13 + 5 + 1 = 19
```

The offsets above are **hypothetical mathematical examples**, not compiler output. It must be ensured that a frame applies at a valid **instruction** offset and satisfies target/control-flow rules. Adding `+1` in subsequent frames helps distinguish offsets and prevents creating explicit frames at duplicate positions due to delta mistakes.

## 5. How Does the JVM Create the Initial State (Initial Frame)?

The verifier needs a starting point before examining explicit frames. The **initial frame** is derived from the **method descriptor**, whether the method is `static` or instance, the `<init>` name in a constructor, and related rules.

Example:

```java
static String describe(int id, Object value) {
    return id + ":" + value;
}
```

This is a **method illustration snippet** to be placed inside a class, not a standalone program. For a `static` method, the parameters are at the beginning of locals in order:

```text
locals[0] = Integer
locals[1] = Object(java/lang/Object)
stack     = []
```

In a **normal instance method**, local slot 0 holds the receiver `this`, and parameters start after it. For a `static` method, **there is no `this` at slot 0**.

In a class's **constructor `<init>`**, the receiver has the state `UninitializedThis` before valid initialization completes. That is why Java cannot arbitrarily use an uninitialized `this` as a complete object in all situations.

### 5.1. `long`/`double` and Double Slots

```java
static void consume(long id, double ratio, Object object) {
    System.out.println(object);
}
```

Conceptual example of local slot indices:

```text
slot 0–1 : long id
slot 2–3 : double ratio
slot 4   : Object object
```

Do not mistake the number of **declared values** for the number of **slots**. Even when a frame uses one entry for `Long` or `Double`, the position of the next local must still be calculated using the two-slot rule.

### 5.2. Types After Branching and Merging

Suppose two branches both write a `String` value into local 1:

```java
static String pick(boolean flag) {
    String value;
    if (flag) {
        value = "left";
    } else {
        value = "right";
    }
    return value;
}
```

If the compiler generates branches and a convergence point, the verifier needs to see that along paths reaching this point, the local holds a type compatible with `java/lang/String`. If one branch carries `int` while the other requires a `String` reference and then uses `aload` at the convergence point, the class file may **fail verification**.

When encountering different reference types in valid code, the allowed type state at the convergence point must satisfy the assignment relation accepted by verifier rules. An appropriate common type may appear, but one should not use the intuition “everything turns into `Object`” to ignore actual rules about interfaces, arrays, instantiation, and opcodes.

## 6. How Does the Verifier Use `StackMapTable`?

### 6.1. Checking Control Flow and Type State Transitions

Under the **verification by type checking** model (JVMS `4.10.1`):

1. The JVM has the method structure: code array, locals/stack limits, exception table, method descriptor.
2. The verifier determines the **expected type state** at locations described by stack map frames, including the initial frame.
3. At each instruction, it applies the opcode's rules to locals and operand stack: which types are read, which types are produced, how many elements are popped/pushed.
4. When an instruction transfers control to another offset (e.g., `if`, `goto`, exception handler), the state inferred along the transition path must be compatible with the state required by the target frame.
5. Operations that violate type rules, stack height, target validity, or uninitialized-object constraints lead to **verification failure**.

Do not take this as a claim that the JVM “dry-runs” the entire program with real data. The verifier operates on **abstract types**, does not execute business logic, does not know user-supplied values, and does not prove that the program will not throw valid exceptions at runtime.

### 6.2. Branching: A Convergence Point Needs a Type Contract

Hypothetical diagram:

```text
                  [method start]
                         |
                  iload_0, ifeq
                    /          \
                branch A      branch B
                  |              |
             astore_1       astore_1
                    \          /
                     \        /
                    [join @ offset J]
                    locals[1] = String
                    operandStack = []
                           |
                        aload_1
                           |
                        areturn
```

The frame at `J` states the **expected types when all valid paths arrive**. Bytecode that produces different stack heights on the two branches or incompatible local types may be rejected.

**No StackMapTable can “rescue” invalid bytecode.** If a jump leads into the middle of an instruction, stacks do not match, or a primitive value is used as an object reference, adding arbitrary frames will not make the program valid.

### 6.3. Exception Handlers Are Also Control-Flow Targets

Suppose bytecode has a `try/catch`. When an exception is transferred to the handler, the operand stack at the start of the handler must contain the corresponding **exception reference** per the contract; it does not preserve the entire operand stack of the failing instruction.

Java example:

```java
static int safeLength(String value) {
    try {
        return value.length();
    } catch (NullPointerException ex) {
        return -1;
    }
}
```

The exception handler needs a type state matching the exception branch. The specification requires verifying the handler's entry state properly; the compiler generates the corresponding `StackMapTable` when required by the target class format.

### 6.4. `new`, `Uninitialized`, and Constructor Calls

Bytecode that creates an object usually follows the conceptual sequence:

```text
new SomeClass
dup
invokespecial SomeClass.<init>:()V
... use the initialized reference ...
```

After `new` but before a valid constructor call, the reference is in the **uninitialized** state. Assigning it, calling methods on it, or letting it escape allowed places is strictly restricted; the verifier needs to know **which `new` instruction** produced that value.

Two states worth distinguishing:

- **`UninitializedThis`:** the special receiver of `<init>` before initialization per contract.
- **`Uninitialized(offset)`:** reference to a newly created object at a specific `new` offset.

Compiler-generated bytecode must ensure the transition from uninitialized to initialized follows constructor rules. This concerns **object structural safety**, which is different from checking whether a Java variable equals `null`.

## 7. Runnable Experiment with Java 17+: Inspecting `StackMapTable` with `javap -v`

Create **`FrameDemo.java`** in a separate directory:

```java
public class FrameDemo {
    static String pick(boolean flag) {
        String selected;
        if (flag) {
            selected = "left";
        } else {
            selected = "right";
        }
        return selected;
    }

    static int safeLength(String text) {
        try {
            return text.length();
        } catch (NullPointerException exception) {
            return -1;
        }
    }

    static String create() {
        return new String("created");
    }

    public static void main(String[] args) {
        System.out.println(pick(true));
        System.out.println(pick(false));
        System.out.println(safeLength("abc"));
        System.out.println(safeLength(null));
        System.out.println(create());
    }
}
```

Compile and run:

```bash
javac --release 17 FrameDemo.java
java FrameDemo
```

**Exact stdout**:

```text
left
right
3
-1
created
```

Output explanation:

- The two calls to `pick` take different branches but return the same **`String` type**.
- `safeLength("abc")` returns length 3; `safeLength(null)` triggers `NullPointerException`, which the handler turns into `-1`.
- `create()` creates a new `String` object; its bytecode shows the allocation and constructor call process.

To inspect the class file metadata:

```bash
javap -v -p FrameDemo
```

`-v` prints verbose information, including the `Code` attribute and `StackMapTable` of relevant methods; `-p` allows showing non-public members as well. Look for lines such as:

```text
Code:
  stack=..., locals=..., args_size=...
  ...
  StackMapTable: number_of_entries = ...
    frame_type = ... /* ... */
```

**This is a display-format illustration, not verbatim `javap` stdout.** The `...` markers represent data that depends on the compiler and method. Rely on the actual output on your machine to see the exact `frame_type` and offsets for the build in use.

### 7.1. Analyzing `pick`

You can see instructions belonging to the group:

- `iload_0` to read the flag value (boolean is handled as an integer in bytecode).
- `ifeq` or an appropriate branch form.
- `ldc` to load a string constant.
- `astore_1` to store the reference in a local.
- `goto` to skip over the unchosen branch.
- `aload_1` and `areturn` to return the reference.

The compiler may arrange branches or perform other optimizations. What to look for are the **branch targets** and the **frame describing the state at that point**. If the branches update `selected`, the frame at the convergence point must be compatible with the incoming paths.

Example type state as a **diagram, not fixed by offset**:

```text
locals = [Integer(flag), Object(java/lang/String)]
stack  = []
```

In this state, `aload_1` is allowed to load the reference at local 1 to return. The actual encoding may use `append_frame`, `same_frame`, `full_frame`, or another suitable form.

### 7.2. Analyzing `safeLength`

In the `javap -v` output, look at both:

- **Exception table:** the protected bytecode range and handler target.
- **StackMapTable:** the state at the handler, typically including one stack item of the appropriate exception type.
- **Bytecode:** the `invokevirtual` instruction to call `String.length()`, then instructions leading to the `-1` return branch.

At the start of the handler, the operand stack is reset by the exception dispatch mechanism, containing the exception reference for the handler code to process. Therefore, the handler frame does not need to carry the entire stack contents from the earlier `length()` call.

### 7.3. Analyzing `create`

For `new String("created")`, a typical compiler generates an opcode sequence showing `new`, `dup`, loading constructor arguments, and `invokespecial`. Inspecting `new` and `invokespecial` helps connect the `Uninitialized` tag with constructor verification rules.

**`create` does not necessarily need an explicit StackMapTable with many entries.** Because the method has straight-line control flow, the implicit initial frame may suffice; not seeing a `StackMapTable` line in this method is **not** evidence that the JVM skips verification.

### 7.4. Changing Debug Flags Without Changing Verification Semantics

`javac -g FrameDemo.java` adds debug information such as line/local variable tables when appropriate. `javac -g:none FrameDemo.java` reduces optional debug tables. `StackMapTable` is **metadata for the verifier**, not merely a source-line mapping table like `LineNumberTable`.

The command `javap -c -p FrameDemo` is enough to read instructions; use `-v` when you want to inspect attributes and frames. Do not confuse **`LocalVariableTable`** (variable names and scopes for debugging) with **`StackMapTable`** (verification types by bytecode offsets). The two tables serve different purposes.

## 8. Why Must Frames Exist at Key Control Points?

Any tool reading bytecode can build a **control-flow graph**: nodes are basic blocks, and edges are control branches or exceptions. Without constrained type states at each required point, the verifier might have to iteratively infer states across edges until reaching a fixed point.

Stack map frames allow the class file to provide **declared states** upfront. The verifier still needs to check that they are **correct** and **compatible with opcodes/flow**; it does not trust them blindly. That is the difference between:

- **Information declared in the class file:** expected type state at an offset.
- **JVM verification result:** confirmation that the instructions and all control-flow edges satisfy the required rules.

Operationally, this mechanism supports verification by type checking, which is especially useful for tools that generate/transform compliant class files. However, **safety** is the primary purpose; `StackMapTable` is not considered “an application speed optimizer” for the JIT and does not directly guarantee faster code execution.

### 8.1. Basic Blocks Are Not Synonymous with Java Lines

One Java line can produce multiple bytecode instructions; conversely, the compiler can optimize and restructure source lines. `StackMapTable` uses **bytecode offsets**, not source line numbers. Therefore, when `javap` prints:

```text
17: goto          26
20: ...
26: aload_1
```

The numbers 17, 20, and 26 in this example are only **illustrative offsets**. Frames apply to offsets in the actual code array, which do not necessarily match line numbers in `FrameDemo.java`.

### 8.2. Why Must Exception Handlers Be Verified?

An exception can occur at many instructions inside a `try` region. When the JVM transfers to a handler, the entry stack has a special shape containing the exception reference. If the handler expects the wrong type or stack structure, that bytecode is invalid. The frame at the handler is an explicit type-checking checkpoint.

### 8.3. Why Can Safety Not Be Inferred from a Single Test Run?

A program may run fine with input `true` yet enter another branch with `false`. The bytecode verifier does not just observe one sample input; it checks structural/type constraints that must hold across all allowed control paths. However, it does not prove that logic bugs, race conditions, or valid exceptions do not exist.

## 9. Class File Versions and Verification Rules

Important scope according to **JVMS `4.10.1`**:

- Class file version **50.0 or higher** (starting from Java 6) is verified under the **type checking** mechanism as described by the specification.
- There is a special compatibility rule: **for version 50.0 only**, when type checking fails, a JVM implementation may choose to fall back to **verification by type inference** according to specification rules. This is not a behavior applications are entitled to require across all versions.
- For older class file formats, verification has rules for the **type inference** mechanism, in JVMs within the corresponding applicable scope.
- For **newer class file versions** (for example Java 17 default compilation, major 61), one should not rely on the version 50.0-specific fallback to run classes missing required frames at branch targets.

Example in `javap -v` after running:

```bash
javac --release 17 FrameDemo.java
javap -v FrameDemo
```

The header describes the class file with **major version: 61** for target Java 17. This is the **class file format version**, not the number of frames in a method. The `StackMapTable` section sits inside each relevant `Code` attribute.

**Do not deduce that “no `StackMapTable` is always wrong.”** If a method is simple enough and the implicit initial frame satisfies all requirements, the number of explicit entries can be 0. Conversely, for control branches/handlers that require frames, missing or wrong frames can cause the verifier to reject the class.

## 10. When Does `VerifyError` Occur?

`java.lang.VerifyError` is a kind of `LinkageError`. It may be thrown when the JVM attempts verification and detects bytecode in a class file violating required constraints. The timing of when the error is observed can be during class loading/linking/use depending on runtime behavior and how checking is organized.

Some common message forms from JVM implementations:

```text
java.lang.VerifyError: Expecting a stackmap frame at branch target ...
java.lang.VerifyError: Bad type on operand stack
java.lang.VerifyError: Inconsistent stackmap frames at branch target ...
```

**These lines are illustrative message samples**, not guaranteed stdout of `FrameDemo`, nor mandatory stable text across all JVMs.

### 10.1. Practical Causes

1. **Editing opcodes while keeping old frames.** Inserting an instruction shifts bytecode offsets; previous frames still point to wrong positions.
2. **Changing branch structure without updating states.** Adding a new branch leading into a convergence point where stack or locals are incompatible.
3. **Changing the type of a value on the stack.** An instruction uses a reference opcode while a path supplies a primitive.
4. **Generating invalid constructor code.** Using an `Uninitialized` reference before a valid initialization step.
5. **Updating the exception table while forgetting the handler frame.** The new handler needs a suitable type state.
6. **Generating a class file incompatible with its major version.** A bytecode generator uses outdated frame rules or sets invalid metadata.
7. **Incorrectly instrumented classes.** An agent/transformer modifies code or control flow, but fails to recompute stack map frames and locals/stack limits when needed.

**Not every class file error is `VerifyError`.** Severe class file structural errors can cause `ClassFormatError`; a class compiled for a newer runtime on an older one can cause `UnsupportedClassVersionError`; class lookup failures can be `ClassNotFoundException` or `NoClassDefFoundError` depending on context. Read the **actual error type and message** before fixing.

### 10.2. Safe Debugging Workflow

1. Identify the **exact class** being rejected (do not rush to edit other sources just because the stack trace has many classes).
2. Check the runtime and bytecode target: `java -version`, compiler target, `javap -v` to see the major version.
3. If the class was modified by a transformer/agent, compare the **original class** and the **transformed class** in a development environment; identify new instructions/branches/handlers.
4. Use `javap -v -p <ClassName>` or a compatible class file inspection tool to cross-check bytecode offsets, `StackMapTable`, and the exception table.
5. At the failing offset, simulate the **types** produced by preceding instructions; compare against the state declared by the target frame.
6. Fix the transformation logic to update **control-flow targets, frame states, max stack, max locals** using the API of the bytecode generation library in use.
7. Build and run again on the **target JDK** so the JVM verifies the final output.

Avoid treating symptoms by trying to **disable bytecode verification** in production environments. That hides class file bugs and may not be available on newer runtimes. The right goal is to produce valid bytecode along with valid metadata.

## 11. StackMapTable When Editing Bytecode with ASM, Byte Buddy, or Agents

This article does not teach implementing a specific transformer, but it is important to understand the consequences of modifying code:

```text
Original method:
  Code instructions
  Branch targets
  Exception handlers
  StackMapTable states

Transformer:
  insert logging / guards / branches / try-catch
           |
           v
New control-flow graph
           |
           v
Recompute or carefully update:
  instruction offsets
  branch and handler targets
  frame states
  max_stack / max_locals
           |
           v
Valid transformed .class
```

A change that **does not alter control flow** can still change stack/local states at specific points. When a transformer modifies bytecode, do not assume that “just adding a println” always keeps `StackMapTable` valid.

Libraries like **ASM** provide mechanisms to compute frames/maxs under appropriate configurations (for example, the approach with `ClassWriter.COMPUTE_FRAMES` in ASM). Even so, this computation needs to know **common class types**, hierarchies, and a suitable classpath. If the resolver cannot find a needed class or uses a different class loader from the target runtime, frame computation can fail or fail to express the required type relation.

More important than API names: **the final output must be accepted by the JVM verifier**. When upgrading the JDK, changing the target class version, creating new branches, or changing constructor structure, re-verify the generated class.

### Distinguishing Verifier Metadata from Debug, GC, and JIT Metadata

| Data | Purpose |
| --- | --- |
| `StackMapTable` in class file | Declares **verification type** states at bytecode offsets of a method |
| `LineNumberTable` | Maps bytecode offsets to source line numbers for debugging/stack traces |
| `LocalVariableTable` | Names, scopes, and descriptors of local variables for debugging |
| `max_stack` and `max_locals` | Resource limits for operand stack/local variable slots of a method frame |
| **GC stack maps / oop maps** of a JVM | Internal data about reference locations at appropriate runtime points to support GC |
| **JIT compiler metadata** | Information for optimizing and executing compiled machine code |

Two terms sharing the words **stack map** do not necessarily refer to the same structure. In particular, **`StackMapTable` in `.class` is not directly a map of GC roots at safepoints** and does not describe the actual runtime state of each thread.

## 12. Thought Experiment: Distinguishing Verification Errors from Valid Exceptions

Consider two scenarios:

**Scenario A — valid Java code that can throw an exception:**

```java
static int divide(int a, int b) {
    return a / b;
}
```

If `b == 0`, the program can throw `ArithmeticException` at runtime. This is **not** evidence that the bytecode has invalid types. Verification ensures `idiv` is used on appropriate types, not that the divisor is always non-zero.

**Scenario B — type-invalid bytecode:**

```text
Hypothetical bytecode:
  iconst_1       // pushes int onto operand stack
  invokevirtual  // assumes a call requiring a receiver reference at this position
```

Without an appropriate receiver reference and valid signature/stack operands, the bytecode violates type/stack rules. This is a **structural or verification error**, different from the valid `ArithmeticException` in A.

Similarly, `String s = null; s.length();` is compilable Java code that can throw `NullPointerException` at runtime. `StackMapTable` can confirm slot `s` belongs to a **reference type**, but **does not prove that the runtime reference is non-null**. The verifier handles type safety, not proving all business conditions.

## 13. Common Misconceptions

1. **“StackMapTable is the JVM's call stack.”** False: it is an attribute in the class file describing type states by bytecode offsets, not runtime call history.
2. **“Every Java line corresponds to a frame.”** False: frames are tied to bytecode positions for the verifier; there is not an entry per source line.
3. **“Frames record actual variable values.”** False: frames record verification types, not values like 42, `"hello"`, or a PID.
4. **“StackMapTable checks runtime null-safety.”** False: a reference can hold `null`; the verifier does not prevent every `NullPointerException`.
5. **“A method missing StackMapTable is definitely invalid.”** False: there is an implicit initial frame and rules for an implicit 0-entry attribute in applicable class versions.
6. **“A frame can be inserted at any byte offset.”** False: frames must satisfy the verifier's offset/instruction/control-flow rules.
7. **“`Top` is synonymous with `Object`.”** False: `Top` is a special verification type; `Object(java/lang/Object)` is a specific reference verification type.
8. **“`Uninitialized` is the same as null.”** False: an uninitialized reference relates to an object being constructed; `Null` is a distinct null reference.
9. **“A large `max_stack` is enough to fix any `VerifyError`.”** False: sufficient size does not fix stack types, locals, branch targets, or initialization states.
10. **“Adding bytecode without changing line numbers means frames do not need updating.”** False: frames are based on **bytecode offsets and flow**, not line numbers.
11. **“StackMapTable is GC/JIT runtime data.”** False: it belongs to the class file verification phase; GC/JIT have separate internal metadata.
12. **“`javap -c` and `javap -v` give the same level of detail.”** `-c` focuses on instructions; `-v` provides attribute details, including `StackMapTable` when present.

## 14. Self-Check Exercises (with Answers)

**Question 1.** Where is `StackMapTable` attached?

**Answer:** In the attributes table of the **`Code` attribute** belonging to a method with bytecode, at most one `StackMapTable` per `Code`.

**Question 2.** Why is `entries[0]` not the frame at the first offset of the method?

**Answer:** Because the **initial frame** is implicitly computed by the verifier from the method descriptor and method rules; the first entry is the next explicit frame.

**Question 3.** How many minimum local slots for parameters does `static void f(long x, Object y)` need?

**Answer:** At least **3 slots**: `long` occupies slots 0–1, `Object` is at slot 2. A `static` method has no `this` receiver.

**Question 4.** Which tag is used for a null reference? Which tag for uninitialized `this` in a constructor?

**Answer:** `Null_variable_info` tag **5**; `UninitializedThis_variable_info` tag **6**.

**Question 5.** Can `same_frame` represent an operand stack containing two `int`s?

**Answer:** No. `same_frame` inherits locals but requires an **empty** operand stack. If the state needs a stack containing two values, it must be encoded with an appropriate form.

**Question 6.** Why can a class throw `VerifyError` after adding an `if` to a method with a transformer?

**Answer:** Because there are new control-flow targets and the locals/operand stack states at the target must match; old frames or offsets may no longer be valid.

**Question 7.** Does `StackMapTable` prevent `NullPointerException` in `text.length()` when `text == null`?

**Answer:** No. A null reference can still be stored in a reference slot; dereferencing at runtime throws `NullPointerException`.

**Question 8.** Are all three offsets of explicit frames equal to the sum of their corresponding `offset_delta` values?

**Answer:** No. The first explicit frame is at `offset_delta`; each subsequent frame is at `previous_offset + offset_delta + 1`.

**Question 9.** Which JDK tool is used to inspect `StackMapTable`?

**Answer:** `javap -v -p ClassName` after compiling; it can read bytecode, the exception table, and method attributes.

**Question 10.** Why does `javap -v` output only show a few frames even though a method has dozens of bytecode instructions?

**Answer:** Frames are stored at necessary offsets, typically the start of basic blocks; other instructions are checked by the verifier using type transition rules.

## 15. Summary and Reference Documentation

**`StackMapTable` is the bytecode-level type-state contract of a method.** It appears inside the `Code` attribute, storing compressed explicit frames, each describing the types of locals and the operand stack at an offset. The verifier combines the implicit initial frame, frames at branch/exception points, and the rules of each opcode to ensure the class file does not violate structural/type constraints required by the JVM.

If you remember only one workflow when editing bytecode:

```text
Change instructions / branches / handlers
             ↓
Re-check the control-flow graph
             ↓
Recompute locals + operand stack states at required points
             ↓
Generate/update valid frames and stack/locals limits
             ↓
Read output with javap -v
             ↓
Verify the class on the target JVM
```

Official specification documentation:

- [JVMS `4.7.3` — The Code Attribute (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): where bytecode, the exception table, and method attributes live.
- [JVMS `4.7.4` — The StackMapTable Attribute (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.4): frame structure, verification_type_info, frame types, and offset calculation.
- [JVMS `4.10.1` — Verification by Type Checking (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.10.1): verification by type checking rules and initial frame.
- [JVMS `2.6` — Frames (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6): JVM local variables and operand stacks.
- [`javap` tool documentation (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): `-c`, `-v`, `-p` flags to inspect class files.
