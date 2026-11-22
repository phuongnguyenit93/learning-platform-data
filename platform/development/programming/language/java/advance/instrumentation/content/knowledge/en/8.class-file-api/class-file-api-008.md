# Managing Local Variable Slots, Jump Labels, and Exception Paths with the Class-File API

## 1. Objectives and Java Version

In Java source code, we are used to writing local variables, `if`, `while`, `try/catch`, and `finally`. When generating or modifying a classfile, the JVM does not see those source constructs as Java syntactic objects. The JVM executes **bytecode instructions** with two main areas: the **local variable slots table** and the **operand stack**, moves control flow by **jumping to a bytecode index (BCI)**, and handles errors via the **exception table**.

The Java **Class-File API** (`java.lang.classfile`) was standardized in **JDK 24** (JEP 484). With `CodeBuilder`, we have an API to:

- Retrieve the exact slot of `this`/parameters and **allocate new local slots** with `parameterSlot(...)`, `receiverSlot()`, and `allocateLocal(TypeKind)`.
- Emit typed load/store instructions: `iload`, `istore`, `aload`, `astore`, `lload`, `lstore`, or `loadLocal`/`storeLocal`.
- Create **abstract labels** using `newLabel()`, bind labels to a position using `labelBinding(label)`, emit conditional/unconditional jumps (`ifeq`, `ifne`, `goto_`...), and define debug scopes.
- Declare an **exception table entry** with `exceptionCatch(tryStart, tryEnd, handler, catchType)` or `exceptionCatchAll(...)`; ensure the stack at the handler and on the normal execution path are both valid.
- Let the API generate the **StackMapTable** when needed, then verify with the JVM verifier, testing both the normal branch and the exception branch.

**Requirements to run the examples in this lesson:** JDK **24 or higher**, without needing `--enable-preview` when using the API that became official in JDK 24. You cannot use `javac --release 17` to compile code that directly calls `java.lang.classfile`; **Java 17 does not have this standard API**. The JVM concepts of slots/labels/exception table still apply to classfiles produced by Java 17, but Java source examples using the Class-File API must be compiled with JDK 24+ and the appropriate API target.

## 2. Overview: Local Slots, Operand Stack, and Control Flow

Each *frame* of a JVM method contains two structures that must be distinguished:

| Component | Access Mechanism | Role | Example |
|---|---|---|---|
| **Local variable array** | `slot` index | Holds `this`, parameters, and local values | `iload(0)`, `istore(2)` |
| **Operand stack** | Push/pop per instruction | Intermediate inputs/outputs of operations | `iload` pushes an `int` onto the stack; `idiv` pops 2 `int`s and pushes the quotient |
| **Program counter/BCI** | Instruction offset | Indicates the next instruction or jump target | `ifeq(label)`, `goto_(label)` |
| **Exception table** | BCI range and handler | When an error is thrown from the protected region, the JVM finds a matching handler | `[tryStart, tryEnd) → handler` |

Conceptual example of the calculation `result = a / b`:

~~~text
Local slots:                 Operand stack:
slot 0: a                   []
slot 1: b

iload(0)                    [a]
iload(1)                    [a, b]
idiv()                      [a / b]      or ArithmeticException
istore(resultSlot)          []           resultSlot holds the quotient
~~~

**Key takeaway:** `istore(slot)` is not an instruction that "creates a Java variable"; it pops an `int` from the operand stack and writes it into the frame's slot. `allocateLocal` is a *builder* operation to pick a new slot index for the code being built; it does not allocate a heap region or a separate runtime Java variable.

The number of slots and the operand stack depth are two different quantities. In a classfile, the `Code` attribute has `max_locals` and `max_stack`. These can be inspected via `CodeAttribute.maxLocals()` and `maxStack()` when reading a built classfile.

## 3. Managing Local Variable Slots Properly

### 3.1. Parameter Slots: `static` vs. `instance`

For an **instance** method, `slot 0` is reserved for the `this` reference. The parameters follow, but `long` and `double` require **two consecutive slots**. For a **static** method, there is no `this`.

Consider the illustrative signature:

~~~java
void process(int count, long timestamp, double ratio)
~~~

Locals layout of an instance method:

| Slot | Contents |
|---|---|
| 0 | `this` (reference) |
| 1 | `count` (`int`) |
| 2–3 | `timestamp` (`long`, category 2) |
| 4–5 | `ratio` (`double`, category 2) |
| 6 onward | Available for allocating new locals |

If the same signature is `static`:

| Slot | Contents |
|---|---|
| 0 | `count` |
| 1–2 | `timestamp` |
| 3–4 | `ratio` |
| 5 onward | Available for allocating new locals |

You should not compute the index manually with a formula like `paramNo + 1`. `CodeBuilder.parameterSlot(int paramNo)` takes the **0-based parameter index**, then automatically accounts for the receiver and type width; `receiverSlot()` is only for instance methods and throws `IllegalStateException` for static methods.

The code snippet using `CodeBuilder` below is an **illustrative snippet inside a builder callback**, not a standalone program:

~~~java
int slotOfFirstParam = code.parameterSlot(0);
int slotOfSecondParam = code.parameterSlot(1);
int temporaryInt = code.allocateLocal(TypeKind.INT);
int temporaryLong = code.allocateLocal(TypeKind.LONG);
int temporaryObject = code.allocateLocal(TypeKind.REFERENCE);
~~~

`allocateLocal(TypeKind.LONG)` or `allocateLocal(TypeKind.DOUBLE)` requires **two** consecutive slots. The builder has a policy for finding available slots; you should not hard-code the next index as `previous + 1`. When *transforming* an existing method, the API tries to avoid colliding with old locals, typically starting new locals after the original method's `max_locals`.

### 3.2. Choosing the Right Opcode for the Data Type

| Type in the JVM | Load from local | Store to local | Local width |
|---|---|---|---:|
| `int` and `boolean/byte/char/short` types at the computational level | `iload(slot)` | `istore(slot)` | 1 |
| Reference (`Object`, array, exception...) | `aload(slot)` | `astore(slot)` | 1 |
| `long` | `lload(slot)` | `lstore(slot)` | 2 |
| `double` | `dload(slot)` | `dstore(slot)` | 2 |
| `float` | `fload(slot)` | `fstore(slot)` | 1 |

Correct example when given `int resultSlot`:

~~~java
code.iload(code.parameterSlot(0))
    .iload(code.parameterSlot(1))
    .iadd()
    .istore(resultSlot);

code.iload(resultSlot)
    .ireturn();
~~~

After `iadd()`, the operand stack has an `int` for `istore` to pop into the slot. If `istore` is replaced with `astore`, the stack type and opcode type are incompatible, causing the class to fail verification.

### 3.3. Local Slot vs. `LocalVariableTable`

`CodeBuilder.allocateLocal(...)` manages **slots for JVM execution**, whereas `CodeBuilder.localVariable(...)` creates **debugging metadata** in the `LocalVariableTable`, for example:

~~~java
code.localVariable(
    resultSlot,
    "result",
    ConstantDescs.CD_int,
    scopeStart,
    scopeEnd
);
~~~

This is an illustrative snippet belonging to a `CodeBuilder` that already has the variables `resultSlot`, `scopeStart`, and `scopeEnd`. It **does not allocate** a new slot and **does not emit an `istore` instruction**. Therefore:

- You must allocate slots and load/store properly even when there are no debug attributes.
- You must place `scopeStart`/`scopeEnd` at appropriate positions; the debug scope is **half-open** `[start, end)`.
- `ClassFile.DebugElementsOption.DROP_DEBUG` can cause debug data to be dropped. Do not rely on debug variable names to guarantee runtime semantics.
- For generic types, `localVariableType(...)` can record the signature; when there is a type entry, a local variable entry with the type-erased descriptor is usually also needed.
- A slot can be reused for locals with non-overlapping lifetimes, but the verifier/type frame analysis must still be valid across all merged branches.

**Common mistake:** thinking every Java variable name is a permanent new slot. A slot is a cell that can be reused when lifetimes permit; the name is only optional information for the debugger.

## 4. Jump Labels: `Label` Is a Position, Not a Line Number

### 4.1. Why Not Compute BCI Manually?

Bytecode instructions have variable sizes: `iload_0` differs from `iload <index>`, opcodes can use the `wide` form, `goto` has the extended form `goto_w`, and `tableswitch/lookupswitch` require alignment/padding. If you calculate offsets manually while writing instructions, simply inserting one instruction earlier shifts the branches and exception table out of alignment.

`Label` solves this problem: it is an **abstract marker of a position**. When building the classfile, the builder resolves labels to the corresponding BCI positions.

- `code.newLabel()`: creates an **unbound label**; can be referenced from a jump before its position is set.
- `code.labelBinding(label)`: binds an unbound label to the **current position**.
- `code.newBoundLabel()`: creates a label and binds it immediately at the current position.
- `code.startLabel()` and `code.endLabel()`: pre-existing labels for the start/end of the current block.
- `CodeAttribute.labelToBci(label)`: when reading a complete `CodeAttribute`, converts a label belonging to that attribute to a BCI.

**Used labels must be bound** in the corresponding builder, and the same label must not be bound twice. Labels from a `CodeModel` during a transform do not automatically have a corresponding position in the new builder; they must be mapped or bound according to the contract.

### 4.2. Conditional Jumps and Merge Points

To represent the logic `if (a == 0) result = 0; else result = a/b;`, you can create labels `whenZero` and `afterIf`:

~~~text
iload(a)
ifeq whenZero
     |
     | a != 0
     v
iload(a), iload(b), idiv, istore(result)
goto afterIf
whenZero:
iconst_0, istore(result)
afterIf:
iload(result), ireturn
~~~

When translating to the builder, **place the label immediately before the instruction that is the target to execute**:

~~~java
Label whenZero = code.newLabel();
Label afterIf = code.newLabel();

code.iload(aSlot).ifeq(whenZero);
code.iload(aSlot).iload(bSlot).idiv().istore(resultSlot);
code.goto_(afterIf);

code.labelBinding(whenZero)
    .iconst_0()
    .istore(resultSlot);

code.labelBinding(afterIf)
    .iload(resultSlot)
    .ireturn();
~~~

This snippet assumes `aSlot`, `bSlot`, and `resultSlot` already exist and were properly allocated. `ifeq` **pops an `int` from the stack** to check if it equals 0; a conditional jump does not keep a copy of `a` on the stack. Therefore, when performing the division, you must `iload(aSlot)` again.

At the branch merge point `afterIf`, all paths reaching it must have **compatible stack height and verification types**. In the example, both paths store a value into `resultSlot` before merging, so at `afterIf` the stack is empty and `resultSlot` has type `int`.

### 4.3. Unconditional Jumps and Java Method Names

`goto` is a Java keyword (even though it is not used in the source language), so the `CodeBuilder` factory method is named `goto_(label)`. Similarly, `return_()` represents the `return` opcode of a `void` method. Specialized methods such as `ireturn()` are used for returning an `int`.

You can use:

~~~java
code.branch(Opcode.GOTO, afterIf);
~~~

or `code.goto_(afterIf)`. If the jump target is too far for the short form, `ClassFile.ShortJumpsOption` affects how the builder widens the jump. You should not manually insert BCI values or manually patch jump opcode bytes.

### 4.4. Valid Branches vs. Dead/Unreachable Code

A sequence such as:

~~~text
ireturn
iconst_1
ireturn
~~~

contains a section that cannot be reached by normal control flow. For modern classfiles with a `StackMapTable`, **dead code** and frame inference can cause stack map generation to fail depending on options. Build a CFG with valid paths and avoid letting handlers experience unintended fall-through. Options like `ClassFile.DeadCodeOption` or `ClassFile.StackMapsOption` are tools to assist when you already understand the code structure, not a way to hide control-flow graph errors.

## 5. Exception Table: Protected Regions, Handlers, and Half-Open Semantics

### 5.1. Bytecode Does Not Have a "try block" Like Java Syntax

At the classfile level, an `exception_table` entry has four main fields:

| Field | Meaning |
|---|---|
| `start_pc` | Starting BCI of the region covered by the handler, **inclusive** |
| `end_pc` | Ending BCI of the region covered by the handler, **exclusive** |
| `handler_pc` | Starting BCI of the exception-handling code |
| `catch_type` | Exception type to catch, or 0 to catch all |

With the Class-File API:

~~~java
code.exceptionCatch(
    tryStart,
    tryEnd,
    catchStart,
    ClassDesc.of("java.lang.ArithmeticException")
);
~~~

The three `Label`s represent BCI positions. The contract `[tryStart, tryEnd)` means the instruction at `tryEnd` is no longer within the protected region of that entry.

Another helper:

~~~java
code.exceptionCatchAll(tryStart, tryEnd, catchAllStart);
~~~

creates an entry that catches every `Throwable` (exceptions and errors). **Catch-all does not automatically create Java `finally` semantics**: if used to simulate `finally`, the bytecode builder must explicitly emit cleanup instructions, save/rethrow the exception, and handle the normal path, `return`, and related control edges.

### 5.2. A Handler Starts with an Exception Reference on the Operand Stack

When an instruction inside the try region throws an exception matching `catch_type`:

1. The JVM searches for a matching exception table entry in order.
2. The stack at handler entry contains **a single reference to the thrown exception**.
3. The handler typically starts with `astore(exceptionSlot)` to pop the reference into a local, or uses the object directly on the stack according to the contract.
4. The handler executes the handling code; if it needs to proceed to a join point, it must bring the stack and locals into a compatible state.

Illustration:

~~~text
tryStart:
    ... operation that may throw ArithmeticException ...
tryEnd:
    goto done           # normal path bypasses handler
catchStart:
    astore(errorSlot)    # top of stack initially holds exception object
    iconst_m1
    istore(resultSlot)
done:
    iload(resultSlot)
    ireturn
~~~

If you omit `astore(errorSlot)` and immediately execute `iload(resultSlot)`, the exception remains on top of the stack: the verifier may reject it or instructions may behave unexpectedly. If you omit `goto done` on the normal path, execution can **fall through into the handler even when no exception occurred**, breaking semantics and stack shape.

### 5.3. Ordering Multiple Handlers and Catch Types

If a code region has `catch (IllegalArgumentException)` and `catch (RuntimeException)`, the more specific handler must be declared in the proper priority order. The JVM scans the exception table in order; a broader handler can "swallow" the opportunity of a narrower handler if placed first.

~~~text
tryStart..tryEnd:
  1) IllegalArgumentException -> handlerA
  2) RuntimeException         -> handlerB
  3) catch-all                -> handlerFinal
~~~

If there are nested try regions, you must consider entry priority, protected ranges, and branches exiting the block. An `exceptionCatch` only creates an entry; it does **not** automatically generate handler code, clean up the stack, run finally, close resources, or rethrow the exception.

Do not use `catch-all` indiscriminately to "ensure the agent doesn't crash": catching `Error` as well can mask serious issues. For code instrumentation, the choice of catch/finally must follow operational contracts and preserve the original method's behavior.

### 5.4. Using Higher-Level Builders When Appropriate

In addition to the primitives `newLabel`/`labelBinding`/`exceptionCatch`, `CodeBuilder` also provides `trying(...)` and `CatchBuilder.catching(...)`/`catchingAll(...)` to build structured blocks. Higher-level builders reduce manual management of break/handler labels, but the author must still ensure correct **semantics** for cleanup, exception flow, and return paths.

The examples in the next section intentionally use labels and the exception table directly to show the exact three mechanisms you need to master.

## 6. Complete JDK 24+ Example: Locals, Jumps, and ArithmeticException

We will **generate a classfile** ourselves, load the generated class into the JVM, and invoke the method via reflection. No Java agent or external bytecode library is needed, because the goal is to focus on `CodeBuilder` and bytecode control flow.

The generated method has the signature:

~~~java
public static int eval(int a, int b)
~~~

Designed behavior:

~~~text
if a == 0:        return 0 (fast path, no division performed)
otherwise:
    try a / b
    if ArithmeticException: return -1
~~~

The experiment covers **conditional jumps**, **jumping past catch**, **local slots**, **typed exception handler**, and a **merge point**.

### 6.1. Create the File `ClassFileFlowDemo.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.Label;
import java.lang.classfile.TypeKind;
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.MethodTypeDesc;
import java.lang.reflect.Method;

public final class ClassFileFlowDemo {

    private ClassFileFlowDemo() {}

    private static byte[] buildClass() {
        ClassDesc generated = ClassDesc.of("demo.GeneratedMath");

        return ClassFile.of().build(generated, classBuilder ->
                classBuilder
                    .withFlags(ClassFile.ACC_PUBLIC)
                    .withSuperclass(ConstantDescs.CD_Object)
                    .withMethodBody(
                        "eval",
                        MethodTypeDesc.of(
                            ConstantDescs.CD_int,
                            ConstantDescs.CD_int,
                            ConstantDescs.CD_int),
                        ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                        code -> {
                            // Static method eval(int a, int b):
                            // parameterSlot(0) = 0, parameterSlot(1) = 1.
                            int aSlot = code.parameterSlot(0);
                            int bSlot = code.parameterSlot(1);

                            // Allocate NEW locals outside the parameter slots.
                            int resultSlot = code.allocateLocal(TypeKind.INT);
                            int errorSlot =
                                    code.allocateLocal(TypeKind.REFERENCE);

                            Label tryStart = code.newLabel();
                            Label tryEnd = code.newLabel();
                            Label catchStart = code.newLabel();
                            Label fastZero = code.newLabel();
                            Label done = code.newLabel();

                            // [tryStart, tryEnd): region protected by catch.
                            code.labelBinding(tryStart);

                            // if (a == 0) goto fastZero;
                            code.iload(aSlot).ifeq(fastZero);

                            // Path a != 0: result = a / b.
                            code.iload(aSlot)
                                .iload(bSlot)
                                .idiv()
                                .istore(resultSlot)
                                .goto_(done);

                            // Path a == 0: result = 0.
                            code.labelBinding(fastZero)
                                .iconst_0()
                                .istore(resultSlot);

                            code.labelBinding(tryEnd)
                                .goto_(done); // Avoid falling into handler.

                            // JVM enters handler with exception
                            // reference on top of the operand stack.
                            code.labelBinding(catchStart)
                                .astore(errorSlot)
                                .iconst_m1()
                                .istore(resultSlot);

                            // Merge point: empty stack, int result.
                            code.labelBinding(done)
                                .iload(resultSlot)
                                .ireturn();

                            // Create exception table entry.
                            code.exceptionCatch(
                                tryStart,
                                tryEnd,
                                catchStart,
                                ClassDesc.of(
                                    "java.lang.ArithmeticException"));

                            // Metadata for debugger; does not create a slot.
                            code.localVariable(
                                resultSlot,
                                "result",
                                ConstantDescs.CD_int,
                                tryStart,
                                done);
                        }));
    }

    private static Class<?> loadGenerated(byte[] bytes) {
        // A small class loader to define the generated class;
        // no need to write a .class file to disk.
        return new ClassLoader(
                ClassFileFlowDemo.class.getClassLoader()) {
            Class<?> defineGenerated() {
                return defineClass(
                    "demo.GeneratedMath",
                    bytes,
                    0,
                    bytes.length);
            }
        }.defineGenerated();
    }

    private static int call(Method method, int a, int b)
            throws ReflectiveOperationException {
        return (int) method.invoke(null, a, b);
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = buildClass();
        Class<?> generatedClass = loadGenerated(bytes);
        Method eval = generatedClass.getMethod(
                "eval", int.class, int.class);

        System.out.println("eval(12,3)=" + call(eval, 12, 3));
        System.out.println("eval(0,0)=" + call(eval, 0, 0));
        System.out.println("eval(5,0)=" + call(eval, 5, 0));
    }
}
~~~

**Why is this a complete program?** It builds `demo.GeneratedMath` using `ClassFile.of().build(...)`, defines the class via `ClassLoader#defineClass`, and invokes the static method itself. It does not require `demo.GeneratedMath` to exist on the classpath beforehand, nor does it need a manifest file or agent; the input is just a single source file `ClassFileFlowDemo.java`.

### 6.2. Compile and Run

Open a terminal in the directory containing that file, with JDK 24:

~~~bash
javac --release 24 ClassFileFlowDemo.java
java -Xverify:all ClassFileFlowDemo
~~~

Similarly, when using a newer JDK that supports `--release 24`, you can keep target 24 to use the corresponding API. If you only have JDK 17 or JDK 21, the command will not succeed because the standard `java.lang.classfile` does not exist in those versions.

**Expected stdout:**

~~~text
eval(12,3)=4
eval(0,0)=0
eval(5,0)=-1
~~~

Why:

- `12 / 3` goes through the normal division branch, stores quotient 4 in `resultSlot`, and jumps to `done`.
- `a = 0` causes `ifeq(fastZero)` to jump to the branch that sets 0; `b = 0` does not matter then because **`idiv` is not executed**.
- `5 / 0` executes `idiv` and throws `ArithmeticException`. The JVM finds the `[tryStart, tryEnd)` entry and transfers to `catchStart` with the exception reference on the stack. `astore(errorSlot)` pops the exception, then writes `-1` into `resultSlot`.
- All paths reaching `done` have an **empty operand stack** and a valid `int` in `resultSlot`, so `iload(resultSlot).ireturn()` handles them uniformly.

The example was tested directly on a JDK 24 for the core `ClassFile.of().build`, `allocateLocal`, jump labels, `exceptionCatch`, `localVariable`, and dynamic class definition/invocation, producing `4,0,-1`. Learners should still run the file-based source program above using the two `javac`/`java` commands to test their own environment.

### 6.3. Table of Locals and Stack State at Key Points

For the newly built static method `eval(int a, int b)`:

| Point | Meaningful locals | Operand stack | Next |
|---|---|---|---|
| Method entry | `a` in slot 0; `b` in slot 1 | `[]` | `tryStart` |
| Before `ifeq` after `iload(a)` | `result` not yet set | `[a]` | Pop `a` to compare |
| Branch `a != 0`, before `idiv` | `a, b` in locals | `[a, b]` | Divide the two numbers |
| After successful `istore(result)` | `result = a/b` | `[]` | `goto done` |
| Branch `fastZero` after `istore` | `result = 0` | `[]` | `goto done` |
| Upon entering `catchStart` | `result` not necessarily written on error path | `[ArithmeticException]` | `astore(error)` |
| After `astore(error)` and `istore(result)` | `error` holds exception; `result = -1` | `[]` | `done` |
| At `done` | `result` has type `int` on every path | `[]` | `iload` then `ireturn` |

If you change one branch to reach `done` when `result` is undefined, or leave different data on the stack across predecessors, verifier/stack-map generation may report an error. This is why you cannot determine bytecode validity just by looking at the Java syntax of `CodeBuilder`.

## 7. Managing `StackMapTable` and the Verifier at Merge Points

In modern classfile versions, `StackMapTable` describes the state of verification types at key control-flow positions. The JVM verifier checks whether frames from different branches and handlers can merge.

For the JDK 24 API:

- `ClassFile.StackMapsOption.STACK_MAPS_WHEN_REQUIRED` is the **default**: the API generates stack maps or reuses them when compatible.
- `ClassFile.StackMapsOption.GENERATE_STACK_MAPS` forces regeneration; useful when you want to detect graph/frame representation errors early.
- `ClassFile.StackMapsOption.DROP_STACK_MAPS` skips generating stack maps; **not suitable by default** for modern methods with jumps/handlers unless you supply the corresponding attribute yourself.
- Stack map computation can report errors for unreachable code or legacy jump techniques. Do not use "drop stack maps" just to hide errors; the JVM can reject the class at link/verify time.

Architectural example when you need to force recomputation:

~~~java
ClassFile classFile = ClassFile.of(
    ClassFile.StackMapsOption.GENERATE_STACK_MAPS
);
~~~

This is an **illustrative configuration snippet**, not a complete program. From `classFile`, you can call `build(...)` as in the main example. You do not need to enable this option for the practice exercise; the default already generates stack maps when required.

### 7.1. Frame Merge Rules

At every label that receives multiple incoming jump paths:

1. **Stack height** of all predecessors must be compatible.
2. **Types of stack entries** must be mergeable according to the verifier.
3. **Local variable verification types** must be mergeable; a slot uninitialized on one branch cannot be read as `int` on another branch.
4. Both normal branches and exception branches must be considered, not just `if/else` paths.
5. For constructors, the `uninitializedThis` state and `<init>` calls have special rules; you should not naively apply static-method logic to all constructors.

For that reason, the following is a **counterexample**:

~~~text
if (condition) goto done
iconst_1
done:
ireturn
~~~

One path reaching `done` has an `int` on the stack, while the other does not: the operand stack is inconsistent. The fix is to make every path produce a value (or store it into a slot) before the merge point.

### 7.2. When the Original Class Belongs to a Custom Loader/Module

If you transform classes via `CodeTransform` in a Java agent, generating stack maps may need to resolve type relationships for classes defined by custom class loaders or module layers. `ClassFile.ClassHierarchyResolverOption` lets you provide a context-appropriate resolver. Do not assume the system class loader can resolve all types of plugins/OSGi/application servers; if the resolver sees the wrong hierarchy, verification results may not match the target runtime.

The static example uses `int` and standard Java `ArithmeticException`, avoiding most of these difficulties and making it suitable as a first learning step.

## 8. Moving from Building from Scratch to Transforming an Existing Method

For an existing classfile, you can parse a `ClassModel`, find a `MethodModel` and `CodeModel`, and use `CodeTransform` to emit new instructions. The hard part is not merely copying a byte array, but keeping **all references to code positions** consistent.

Things to check:

- **Existing locals:** the original method already uses `max_locals`; new locals must not overwrite parameters or live variables. `allocateLocal` helps obtain a slot more safely than picking a fixed number.
- **Branch targets:** labels from the old `CodeModel` do not bind automatically in the new builder; when copying/transforming, labels must be translated and bound in the right places. Do not jump using old offsets after inserting instructions.
- **Exception ranges:** inserting instructions **before or after** a try start/end label can place them inside or outside the handler, affecting semantics if the instrumentation code itself throws an error.
- **Handlers:** if you insert event logging at the start of a handler, remember the entry stack holds the exception reference. A logging helper might throw an error and lose track of the original exception if not properly guarded.
- **LineNumberTable/LocalVariableTable:** debug attributes use labels/positions; `DebugElementsOption`, `LineNumbersOption`, and binding order affect whether they are preserved.
- **Stack maps:** adding branches or local references can change frames. Use a compatible stack-map generation mode and the verifier; do not assume the original table remains valid after transformation.
- **Synchronized methods/monitors:** `monitorenter` and `monitorexit`, exception paths, and early returns must stay balanced; a new early return can skip cleanup.

**Do not equate `LocalVariableTable` with the runtime local array.** A method without debug info still has `max_locals` and `iload/istore`; an agent that relies solely on variable names in `LocalVariableTable` will fail when classes have had debug symbols stripped.

### 8.1. Considerations When Inserting Code at Try Boundaries

Suppose the original method has:

~~~text
tryStart:
    callBusiness()
tryEnd:
    goto done
handler:
    ...
~~~

If you instrument with `logEnter()`:

- Insert **before `tryStart`**: exceptions from `logEnter` normally fall outside the protected range of this handler.
- Insert **after `tryStart`**: `logEnter` may be caught by the handler, changing behavior, including causing an agent exception to be handled as a business exception.
- Insert at the start of `handler`: the operand stack holds the exception, so if the helper wants to call another API it must preserve or store that object first.
- Insert before `return` inside the try region: every return path must be instrumented; logging code can also throw errors or add locals/stack.

This is why a professional transformer must decide the **exact protection boundaries** of instrumentation code and how to restore the original exception. Do not place labels arbitrarily just so the code "compiles."

### 8.2. Try-with-resources Is Not Just a Catch-All

Java source `try-with-resources` also has semantics for closing resources in order, handling the primary exception, and `suppressed exceptions`. Creating a single `exceptionCatchAll` and calling `close()` is not enough to reproduce every case. When you need to preserve the original program's semantics, prefer structured transforms, test both normal and exception paths thoroughly, and inspect the bytecode generated by `javac` for the equivalent case.

## 9. Reading and Inspecting a Built Classfile

The Class-File API provides models suited for inspection:

| Model/API | Information |
|---|---|
| `ClassFile.of().parse(byte[])` | Returns a `ClassModel` from classfile bytes |
| `ClassModel.methods()` | The `MethodModel`s of the class |
| `MethodModel.code()` | `Optional<CodeModel>` for a method with code |
| `CodeModel.exceptionHandlers()` | List of `ExceptionCatch` |
| `CodeAttribute.maxLocals()` | Maximum number of local slots in a complete `Code` attribute |
| `CodeAttribute.maxStack()` | Maximum operand stack depth |
| `CodeAttribute.labelToBci(label)` | BCI for a label belonging to that `CodeAttribute` |

The conceptual inspection snippet below assumes `bytes` is a generated classfile; it is an **illustrative code fragment**, not a standalone program:

~~~java
var model = ClassFile.of().parse(bytes);
var method = model.methods().stream()
    .filter(m -> m.methodName().stringValue().equals("eval"))
    .findFirst().orElseThrow();

var code = method.code().orElseThrow();
System.out.println(code.exceptionHandlers().size());
~~~

For the `eval` method in the main example, the exception handlers list is designed to have **one** typed `ArithmeticException` entry. When you want to view detailed JVM bytecode, you can write the bytes to `demo/GeneratedMath.class` and run `javap -c -v` on the saved class; do not confuse the dynamic class file with `ClassFileFlowDemo.class` produced by `javac`.

Note that `LineNumberTable` and `LocalVariableTable` are optional debug data; an analysis tool should not treat their absence as a classfile error.

## 10. Common Mistakes and How to Debug Them

### Mistake 1: Hard-coding a slot that collides with a parameter or live value

~~~java
// Wrong if slot 1 currently holds parameter b of eval(int a, int b):
code.iconst_0().istore(1);
~~~

Consequence: alters the parameter value or corrupts type state. Use `parameterSlot` to get parameters and `allocateLocal(TypeKind)` to allocate new slots.

### Mistake 2: Forgetting that `long`/`double` take two slots

For the static method `m(int, long, double)`, the parameter slots are 0, 1, and 3, respectively—not 0, 1, 2. Use `parameterSlot(paramNo)` instead of calculating manually.

### Mistake 3: Confusing the local array with the operand stack

`istore(resultSlot)` requires an `int` on top of the stack. `iload` is what pushes a local onto the stack. You cannot call `ireturn()` when the stack is empty or holds an exception reference.

### Mistake 4: Creating a label without binding it

~~~java
Label target = code.newLabel();
code.goto_(target);
// Missing labelBinding(target): wrong.
~~~

For any label that is used, the builder needs to know its target position. Call `labelBinding(target)` at the appropriate place and bind it only once.

### Mistake 5: Binding the handler right after `try` without jumping over it

If the normal path falls through into the first instruction of the handler while the top of stack has no exception reference, `astore(exceptionSlot)` will lack an operand of the right type. Add `goto_(afterHandler)` or structure blocks otherwise so normal execution bypasses the handler.

### Mistake 6: Using the wrong scope for the try-end label

`[tryStart, tryEnd)` excludes the instruction at `tryEnd`. If you bind `tryEnd` too late, you may accidentally catch exceptions thrown by instrumentation code itself; if you bind it too early, an important business instruction falls outside the protected range.

### Mistake 7: Forgetting that the handler entry stack holds an exception

When jumping into a catch block due to an exception, the stack contains the thrown object. You must consume/store it properly, especially before new instructions that expect an empty stack.

### Mistake 8: Merging branches with uninitialized locals

`resultSlot` must have a valid value on **every** path reaching `done`. If the `fastZero` branch does not `istore(resultSlot)`, one path to `iload(resultSlot)` uses an uninitialized local.

### Mistake 9: Treating catch-all as a complete `finally` implementation

Catch-all only creates an **exception table entry**. To implement `finally`, you must also handle the normal path, return paths, throws, and other control edges, and preserve the exception according to the required semantics.

### Mistake 10: Dropping `StackMapTable` to silence build errors

Stack-map generation errors usually indicate a real issue in the control-flow graph or type merge. A modern class with branches/handlers missing valid frames can fail with `VerifyError`. Fix the CFG and verify under `-Xverify:all`.

### Mistake 11: Expecting Java 17 to compile the standard Class-File API

`java.lang.classfile` became official in JDK 24. With Java 17, you can use compatible bytecode libraries such as ASM/Byte Buddy for another instrumentation target, but you **cannot** copy the JDK 24 example verbatim and run it with `javac 17`.

### Mistake 12: Testing only the "happy path"

A method with `idiv` must be tested with a zero divisor as well as the fast path. The exception handler path may never actually be verified in tests that do not trigger errors.

## 11. Pre-Release Bytecode Verification Checklist

| Step | Question | How to verify |
|---|---|---|
| API version | Are runtime/compiler JDK 24+? | `java -version`, `javac -version` |
| Parameters | Which slots do `this` and parameters occupy? | `receiverSlot()`, `parameterSlot(...)` |
| New locals | Do they overwrite live variables or category-2 slots? | `allocateLocal(TypeKind)` |
| Opcodes | Do load/store/return types match the stack? | `iload/istore`, `aload/astore`, `ireturn/areturn` |
| Labels | Is every used label bound exactly once? | Review `newLabel/labelBinding` and check build |
| Branch merge | Are stack height/types valid on every predecessor? | Stack-map generation and JVM verifier |
| Try range | Which instructions does `tryStart` include? Which does `tryEnd` exclude? | Check label positions; `[start, end)` |
| Exception handler | Is there a reference on the stack upon entering the handler? | `astore(exceptionSlot)` or equivalent handling |
| Normal path | Does it bypass the handler? | `goto_(done)` or equivalent graph |
| Catch priority | Are narrow and broad handlers ordered properly? | Review exception table order |
| Debug | Does the local variable scope have proper labels? | `localVariable(...)` and debug attribute policy |
| StackMapTable | Are frames valid at every branch/handler? | Default stack maps, `-Xverify:all` |
| Behavior | Do normal and exception paths produce the right results? | Test `eval(12,3)`, `eval(0,0)`, `eval(5,0)` |
| Agent/loader | Do helper and target classes have the right loader/module? | Test real runtime if embedded in an agent |
| Modifying existing methods | Are `finally`/monitor/return semantics preserved? | Differential testing on before/after bytes |

**Limitation:** a successful build and successful class load are **not enough** to prove all execution paths have correct logic. Combine model inspection APIs, the verifier, and output comparison tests. For instrumented classfiles from real applications, also add tests for concurrency, reflection, exception suppression, and custom class loaders depending on scope.

## 12. Review Questions with Answers

**1.** Why can `long` and `double` cause subsequent parameter slots to differ from `paramNo`?

> They occupy two slots in the local array; `paramNo` is the parameter index, not the slot index. `parameterSlot` properly accounts for both the receiver and type widths.

**2.** Does `allocateLocal(TypeKind.INT)` add an entry to `LocalVariableTable`?

> No. It selects a new slot for the generated code. `localVariable(...)` is what declares debug metadata with a name, descriptor, and scope.

**3.** How does `newLabel()` differ from `newBoundLabel()`?

> `newLabel` creates an unbound marker that can serve as a forward jump target; `newBoundLabel` creates and binds immediately at the current position. Labels used in code must be bound according to the contract.

**4.** In a `catch (ArithmeticException e)` handler, what is on top of the operand stack?

> A reference to the thrown exception. You can use `astore(errorSlot)` to move it into a local before building other instructions.

**5.** Why must normal code jump over the handler?

> The handler is emitted as instructions in the code array; without an appropriate branch/return, normal execution can fall through into the handler when the stack has no exception reference.

**6.** Does `exceptionCatch(tryStart, tryEnd, handler, type)` automatically generate `finally` logic?

> No. It only adds an entry to the exception table for the range `[tryStart, tryEnd)`. Cleanup logic on all paths, handling the original exception, and returns must be generated explicitly.

**7.** Is `goto_(done)` from two different branches always valid?

> Only when the operand stack state and local verification types can merge. Labels do not automatically fix type mismatches or missing values.

**8.** If a generated method uses `resultSlot` without a variable name for the debugger, can the JVM run it?

> Yes. Local slots and bytecode are what execute; variable names in `LocalVariableTable` are optional metadata, not a requirement for load/store.

**9.** Why is default stack-map generation usually better than `DROP_STACK_MAPS`?

> For modern classfiles with branches/handlers, the JVM verifier requires valid frame information. The API default generates or reuses stack maps when needed; dropping them entirely without supplying a valid table can lead to `VerifyError`.

**10.** Why is testing `eval(5,0)` important even when `eval(12,3)` already works?

> `5/0` forces the JVM to enter the handler, verifying the try range, storing the exception reference, and the result value on the exception path; the happy path does not test those aspects.

## 13. Official Reference Documentation

- JEP 484 — Class-File API standardized in JDK 24: https://openjdk.org/jeps/484
- Java SE 24, `ClassFile` — build, parse, options for classfiles and stack maps: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html
- Java SE 24, `ClassBuilder` — `withMethodBody`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassBuilder.html
- Java SE 24, `CodeBuilder` — `allocateLocal`, `parameterSlot`, `newLabel`, `labelBinding`, `exceptionCatch`, `localVariable`, instruction factories: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html
- Java SE 24, `TypeKind` — computational types `int`, reference, category-2 `long`/`double`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/TypeKind.html
- Java SE 24, `CodeAttribute` — `maxLocals`, `maxStack`, `labelToBci`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/attribute/CodeAttribute.html
- Java SE 24, `CodeModel` and `ExceptionCatch` — exception handlers in the model: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeModel.html
- Java SE 24, `ClassFile.StackMapsOption` — default and stack map generation options: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html
- JVM Specification Java SE 24 — local variable array, operand stack, `Code` attribute, exception table, verifier: https://docs.oracle.com/javase/specs/jvms/se24/html/index.html
