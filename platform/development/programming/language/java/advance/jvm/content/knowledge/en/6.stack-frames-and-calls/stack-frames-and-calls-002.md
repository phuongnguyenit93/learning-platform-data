# JVM Frames and Method Calls: Passing Arguments, `this` Position, and Return Values

When a Java method calls another method, the JVM must transfer argument values from the **caller** context to the **callee** context, determine the target receiver object `this` if any, and then bring the return value back to the right place. The mechanism is described using the **operand stack**, **local-variable array**, **frame**, and the `invoke*` / `*return` bytecodes.

An important distinction:

- **On the caller side:** bytecode prepares `objectref` (if it is an instance call) and the argument values **on the operand stack of the current frame**.
- **When the call executes:** the JVM processes the call, creates a new frame for the target Java method according to the specification model, and assigns the receiver/arguments into the **local variables of the new frame**.
- **In the callee:** local slot `0` is `this` for an instance method, but it is the first argument for a static method.
- **On normal return:** the `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`, or `return` instruction terminates the callee frame; if there is a value, the value is transferred back to the **caller's operand stack**.

This is the **JVM model at the bytecode level**. HotSpot may inline methods, use CPU registers, eliminate allocations, and optimize the physical frame layout. The logical diagrams below should not be taken as a guarantee that every call always creates a tangible native stack frame.

## 1. Big Picture: Two Separate Frames

Suppose we have the Java source:

```java
static int add(int x, int y) {
    return x + y;
}

static int calculate() {
    int result = add(2, 3);
    return result * 10;
}
```

These are **illustrative methods**, not a standalone runnable class. At the bytecode level, the mental sequence is:

```text
Caller frame: calculate()                      Callee frame: add(int,int)
┌───────────────────────────────────┐         ┌──────────────────────────────┐
│ Local variables                   │         │ Local variables              │
│  slot 0: result (after store)     │         │  slot 0: x = 2               │
│                                   │         │  slot 1: y = 3               │
│ Operand stack (just before invoke)│         │ Operand stack: at the start  │
│  ... , int 2 , int 3              │──invoke►│  empty                       │
└───────────────────────────────────┘         └──────────────────────────────┘
                                                         │
                                                 iload_0, iload_1
                                                         │
                                                     iadd → 5
                                                         │
                                                     ireturn
                                                         ▼
Caller resumes:
  operand stack has int 5
  istore_0 → stores result = 5
  iload_0, bipush 10, imul, ireturn → returns 50
```

**Two different operand stacks:** when `add()` begins, the operand stack of the new frame is **empty**; the parameters have become **local variables** of the `add` frame, rather than remaining on the callee's operand stack. Conversely, before the `invokestatic add` instruction, the caller must push all arguments in the right order.

Each frame is associated with **one specific method invocation**. If `add` calls another method, another frame becomes the current frame; the `add` frame temporarily ceases to be the current frame until the inner call finishes.

## 2. Structure of a Frame in the JVM

In the Java Virtual Machine Specification (JVMS) model, each invocation of a Java method creates a frame containing:

| Frame component | Responsibility |
| --- | --- |
| **Local-variable array** | Holds the receiver `this` if any, parameters, and local/temporary variables; accessed via index 0,1,2,... |
| **Operand stack** | Provides operands to bytecode instructions, prepares arguments for method calls, and receives return results |
| **Dynamic-linking information** | Supports resolving symbolic references to fields/methods/types in the runtime constant pool |
| **Return information** | Serves to restore the execution flow and transfer the result back to the caller according to VM semantics |

A frame resides in the context of the **calling thread's Java Virtual Machine stack**. Each JVM thread has its own logical stack/frames, so local variables in a call on thread A are not automatically the same local-variable array as a call on thread B.

Parameters recorded in the `Code` attribute of the class file:

- `max_locals`: the maximum number of **local slots** needed for a frame of the method, including receiver, parameters, and temporaries.
- `max_stack`: the maximum depth measured in units of the **operand stack**.
- `code_length` and `code[]`: the bytes containing the method's bytecode instructions.

These two regions are independent; you cannot use `max_stack` to deduce the number of Java variables or use `max_locals` to deduce the number of live objects on the heap.

### 2.1. When a new frame is created, the operand stack is initially empty

At the moment a Java method begins, the JVM has already placed the receiver/argument values into the **callee's local variables**. Computation inside the callee continues via `iload`, `aload`, `dload`, `lload`,... instructions to push local values onto its own operand stack.

For example, `add(int,int)` has illustrative bytecode:

```text
0: iload_0
1: iload_1
2: iadd
3: ireturn
```

In that `static` method:

- `iload_0` loads local `0 = x` onto the operand stack.
- `iload_1` loads local `1 = y`.
- `iadd` pops two `int`s and pushes the result.
- `ireturn` pops one `int` from the callee's operand stack and returns it to the caller.

Do not confuse local slot `0` of `add` with local slot `0` of `calculate`: they are **two different frames** even though they have the same index.

## 3. Passing Arguments: Caller Uses Operand Stack, Callee Uses Local Variables

### 3.1. Preparation step in the caller

For the call `add(2, 3)` in Java source, the compiler generates logic similar to:

```text
iconst_2              // push argument 2
iconst_3              // push argument 3
invokestatic #...     // call add:(II)I
                      // the int result is pushed onto the caller's operand stack
```

The operand stack is last-in-first-out, but that **does not reverse parameter order**: the compiler places values in the **order matching the method descriptor**, and the invoke instruction knows how to consume them. For the static call `add(int x, int y)`, `2` corresponds to `x`, `3` corresponds to `y`.

When argument expressions have side effects, the Java Language Specification also defines the evaluation order of expressions. Before the call is executed, argument expressions must be validly evaluated in Java language order, except in cases where the call fails early according to invocation expression rules (for example, an exception when evaluating the receiver). Do not assume right-to-left evaluation just because the operand stack is LIFO.

### 3.2. Callee's local variables

A **static** method receives parameters starting at local index **0**:

```java
static int sum(int left, int right) {
    return left + right;
}
```

```text
Callee local variables
index 0 = left
index 1 = right
```

An **instance** method reserves local index **0** for the receiver:

```java
int sum(int left, int right) {
    return left + right;
}
```

```text
Callee local variables
index 0 = this
index 1 = left
index 2 = right
```

**`this` is not explicitly written in the method descriptor**. For an instance method, `this` is the receiver passed by the JVM as an object reference. A method with three source parameters can still use four local slots just for the receiver and parameters if all three are category 1.

### 3.3. `long` and `double` occupy two local-variable slots

The JVM category 2 rule:

- `long` and `double`: each value uses **two consecutive local-variable slots**.
- `int`, `float`, object reference: each typically uses **one slot** in the JVM model.
- `boolean`, `byte`, `short`, `char` are typically handled via int-family bytecodes in the specified operations.
- A `long`/`double` value is only loaded from the **lower index** of the slot pair. The higher index is not a half-value that can be read separately with `iload`.

Consider:

```java
static long staticWork(long base, double rate, int extra) {
    return base + (long) (rate * extra);
}

long instanceWork(long base, double rate, int extra) {
    return base + (long) (rate * extra);
}
```

Table:

| Method | Slot 0 | Slot 1 | Slot 2 | Slot 3 | Slot 4 | Slot 5 |
| --- | --- | --- | --- | --- | --- | --- |
| `staticWork(JDI)J` | `base` (long) | 2nd part of `base` | `rate` (double) | 2nd part of `rate` | `extra` (int) | — |
| `instanceWork(JDI)J` | `this` | `base` (long) | 2nd part of `base` | `rate` (double) | 2nd part of `rate` | `extra` (int) |

Thus:

- `staticWork` needs **at least 5 local slots** for parameters; `lload_0` loads `base` and `dload_2` loads `rate`.
- `instanceWork` needs **at least 6 local slots** for the receiver and parameters; `lload_1` loads `base` and `dload_3` loads `rate`.
- Both have **three Java parameters**, even though the number of parameter slots differs. `long` and `double` are not counted as two source arguments.

The JVM descriptor of both is **`(JDI)J`**, because they take `long` (`J`), `double` (`D`), `int` (`I`) and return `long` (`J`). The receiver `this` is not in the descriptor.

## 4. The Receiver `this`: Where and When Does It Appear?

An instance method requires a target object. In Java source, the receiver can be explicit or implicit:

```java
item.process(5);    // receiver is item
process(5);         // inside an instance method: implicit receiver is this
this.process(5);    // explicit receiver
```

In the class file, when a method is called using the appropriate instance invocation mechanism, **the caller's operand stack has the object reference**, and the callee receives that reference in **local slot 0**.

Example call `item.process(5)`:

```text
Caller operand stack before the call (bottom → top):
    ..., objectref(item), int(5)
                           ▲ top

invokevirtual process:(I)V
    │
    ▼
Callee frame of item.process:
    local 0 = objectref(item) → this
    local 1 = 5               → parameter
    operand stack = empty at the start
```

Specifically:

- **A static method has no `this` receiver.** You cannot use `this` in a static method body the way you do in an instance method.
- **An instance method has the receiver in local 0** by the parameter passing rules, even if the source never uses the `this` keyword.
- **A static nested class** still has instance methods and `this` of **that** nested class itself; “static” in `static class Nested` does not make all of its methods static.
- **A constructor `<init>`** is an instance initialization case: the receiver is in local 0 in the constructor frame. Before object initialization completes, the verifier enforces additional constraints on the uninitialized reference.
- **An instance synchronized method** also has the receiver in local 0; the monitor mechanism is managed by the JVM for the invocation, without needing to explicitly write `monitorenter` as with a `synchronized` block.

### 4.1. `this` is not a whole copied object

Java passes **the value of the reference**. When the callee receives the receiver, it does not create a new object identical to the receiver. Both caller and callee hold references to **the same object**; operations on fields of that object can be observed externally when permitted.

Therefore:

```java
void setValue(int next) {
    this.value = next;
}
```

Modifying the field `this.value` affects the same object that the caller is holding. That is **not** “Java passes objects by reference” in the sense of being able to reassign the original reference variable on the caller side.

### 4.2. `NullPointerException` can occur before the callee starts

With `obj.method()` and `obj == null`, an instance invocation cannot have a valid receiver to start the corresponding method; the JVM may throw `NullPointerException` according to the opcode rules. **No callee frame runs the normal body of `method()`** and then checks for null afterward.

If the call also has arguments that are expressions with side effects, one must understand the **Java source** evaluation order and when the null check happens under the specific invocation semantics. Do not assume “nothing inside the call expression is evaluated” just because the receiver is null.

## 5. Five Bytecodes for Method Invocation

| Opcode | Primary call form | Is receiver `this` passed directly? |
| --- | --- | --- |
| `invokestatic` | Static method of a class/interface | **No** |
| `invokevirtual` | Instance method with target selection matching runtime class | **Yes** |
| `invokeinterface` | Calling an interface method on an object, with appropriate resolution/dispatch | **Yes** |
| `invokespecial` | Constructor `<init>`, private instance method, `super` calls/certain special calls | **Yes** |
| `invokedynamic` | Call site linked via a bootstrap method; commonly related to lambdas, string concatenation, dynamic language support | **No fixed implicit receiver**; all argument types are in the call-site descriptor |

This is a grouping to help read bytecode, not a complete definition of every special case such as signature-polymorphic methods or method selection changes across JVM versions.

### 5.1. `invokestatic`

```java
int answer = Math.abs(-7);
```

When calling a static method, the caller prepares the arguments on the operand stack, then `invokestatic` performs the call. The callee receives the first parameter in local 0. There is no `this` or objectref for the `Math` class.

It is **not** the case that because `Math.abs` does not use an object, it “needs no frame” in the JVM model: a static Java method call still has invocation semantics; the runtime/JIT may optimize it or use an intrinsic.

### 5.2. `invokevirtual`

```java
String text = "hello";
int size = text.length();
```

The caller places objectref `text` onto the operand stack and calls the method. The JVM relies on the object's class/method resolution to select the implementation according to virtual dispatch rules. In the callee, slot 0 is `this`.

A Java source call may bind to an overridden method; this does not change the positions of the receiver/arguments in the callee.

### 5.3. `invokeinterface`

```java
Runnable job = () -> System.out.println("run");
job.run();
```

Semantically, `job.run()` calls an interface method on a receiver object. The operand stack has objectref `job` before `invokeinterface`; the receiver becomes local 0 of the selected method.

Interface abstraction does not mean the JVM has no target receiver object for the call.

### 5.4. `invokespecial` and constructors

```java
Object item = new Object();
```

Typical bytecode in the caller:

```text
new java/lang/Object
dup
invokespecial java/lang/Object.<init>:()V
astore_1  // if the compiler chooses local 1 for item
```

**`new`** creates a reference to an uninitialized object according to JVM semantics; **`dup`** keeps a reference on the operand stack to use after the constructor finishes. **`invokespecial <init>`** calls the instance initialization method with a receiver, but the constructor has a descriptor **returning `void`**, so the constructor call **does not return objectref as a method result**. The reference used for `astore_1` is the reference kept by `dup`.

The bytecode snippet above is **illustrative**; the variable storage index will depend on where the code appears, and the JVM verifier checks that the uninitialized object reference is used according to the rules.

### 5.5. `invokedynamic` differs in how the call site is linked

`invokedynamic` is linked via a bootstrap method; the call-site descriptor declares the arguments and return type. Not every dynamic call has an implicit `this` at slot 0 like an instance invocation.

If an argument is an object reference, it is simply **an explicit argument according to the call site's descriptor**. When bootstrapping leads to executing other Java methods, those methods still follow the frame and receiver semantics matching their actual invocation type.

## 6. Return Type Determines the Opcode and Impact on the Caller Stack

Java source `return expression;` is compiled into a return instruction of the type matching the descriptor.

| Return type | JVM Opcode | Value transferred back to caller |
| --- | --- | --- |
| `int` and `boolean`, `byte`, `short`, `char` in appropriate form | `ireturn` | One int-family value, category 1 |
| `long` | `lreturn` | One `long` value, category 2 |
| `float` | `freturn` | One `float` value, category 1 |
| `double` | `dreturn` | One `double` value, category 2 |
| Reference type, array | `areturn` | One object/array reference, category 1 |
| `void`, constructor `<init>` | `return` | **No return value** |

Note that the `return` opcode **with no leading letter** is used only when the method returns `void`. `ireturn` and `areturn` are not two arbitrary ways to return the same kind of value; the verifier and method descriptor enforce type matching.

### 6.1. Returning does not mean writing directly into the caller's variable

Suppose:

```java
int result = add(2, 3);
```

The callee uses `ireturn` to put `5` back onto the **caller's operand stack**. Only then does the caller decide what to do with the result:

```text
caller: iconst_2, iconst_3, invokestatic add:(II)I
                                    │
callee: iload_0, iload_1, iadd, ireturn
                                    │
                                    ▼
caller operand stack: [..., int 5]
caller: istore_0            // store into local variable result
```

If the caller writes `System.out.println(add(2, 3))`, the result can be used directly to form arguments for the next call **without needing `istore` into a local variable**.

For `long` or `double`, the return value is still **one category 2 value**, occupying **two depth units** on the caller's operand stack. There are not two return instructions for its two halves.

### 6.2. After return, which frame is current?

When a method completes normally:

1. The method returns a value (if any) using a typed return opcode.
2. The callee frame is discarded from the current frame context in the JVM model.
3. The caller frame becomes the current frame again.
4. The JVM resumes execution at the position **immediately following the caller's invocation instruction**.
5. The return value (if any) becomes a value on the caller's operand stack.

That is why the caller can continue computing with the callee's result without needing direct access to the callee's private local variables.

Runtime details such as machine registers, physical return addresses, or optimizations do not alter this semantic outcome.

### 6.3. `void` and exception cases

For the method:

```java
static void log(String message) {
    System.out.println(message);
}
```

When `log` ends with `return`, the caller **does not get any method return value pushed**. The method body may have produced side effects (printing to stdout), but there is no expression result to use.

Conversely, if the callee throws an exception and does not handle it inside itself, the method completes **abruptly**, with no normal return value. The JVM searches for a matching exception handler, potentially unwinding through frames until an appropriate handler is found or the thread terminates.

**Never say “an exception is returned as an object on the operand stack via `areturn`”.** Exception propagation is a separate control mechanism; when a handler is selected, the JVM sets up the operand stack state for the handler according to the specification.

## 7. Runnable Java 17 Example: Static Call, Instance Call, `this`, and Long Return

Create the file **`FrameCallDemo.java`**:

```java
public class FrameCallDemo {
    private final int factor;

    public FrameCallDemo(int factor) {
        this.factor = factor;
    }

    static long mix(long base, double ratio, int extra) {
        return base + (long) (ratio * extra);
    }

    long adjust(long base, double ratio, int extra) {
        return mix(base, ratio, extra) + factor;
    }

    static void display(long value) {
        System.out.println("display=" + value);
    }

    public static void main(String[] args) {
        FrameCallDemo demo = new FrameCallDemo(3);
        long result = demo.adjust(10L, 2.5, 4);

        System.out.println("result=" + result);
        display(result);
    }
}
```

Compile/run on JDK 17+:

```bash
javac --release 17 FrameCallDemo.java
java FrameCallDemo
```

**Exact stdout:**

```text
result=23
display=23
```

In `mix`: `(long) (2.5 * 4) = (long) 10.0 = 10L`, so `base + 10 = 20L`. `adjust` adds the field `factor = 3` and returns `23L`. `display` only prints the result and returns no value.

### 7.1. Call diagram in the program

```text
main(String[] args)
  local 0 = args
  local 1 = demo (reference, in typical bytecode)
  local 2–3 = result (long)

  new FrameCallDemo
    └─ invokespecial <init>(I)V
         local 0 = this (demo)
         local 1 = factor = 3
         return (void)

  call demo.adjust(10L, 2.5, 4)
    caller operand stack:
      [..., demo ref, long 10, double 2.5, int 4]
    invokevirtual adjust:(JDI)J
         │
         ▼
         frame adjust:
           local 0 = this
           local 1–2 = base (long)
           local 3–4 = ratio (double)
           local 5   = extra (int)
           │
           └─ invokestatic mix:(JDI)J
                 frame mix:
                   local 0–1 = base
                   local 2–3 = ratio
                   local 4   = extra
                   lreturn 20L
           │
           <long 20L> returns to adjust's operand stack
           read this.factor and add → lreturn 23L
         │
         ▼
    main receives long 23L on operand stack
    lstore ...  → result = 23L

  call static display(result)
    invokestatic display:(J)V
    callee local 0–1 = result (long)
    return (void), no value
```

The local layout of `main` is **one common allocation** from `javac` for this code; another compiler may reuse indices differently. In contrast, the local indices for **the receiver and parameters at the start of `adjust`, `mix`, `display`** are dictated by the order/types of the method descriptor, regardless of how many temporaries exist in the method body.

### 7.2. At the moment of `invokevirtual adjust`, what does the caller stack hold?

Method descriptor: **`(JDI)J`**.

| Order from bottom to top of values for the call | Type | Operand stack depth added |
| --- | --- | ---: |
| Object reference `demo` | Reference | 1 |
| `10L` | Long (category 2) | 2 |
| `2.5` | Double (category 2) | 2 |
| `4` | Int | 1 |
| **Total** | Receiver + three arguments | **6 units** |

The caller must have sufficient operand stack capacity at this point. The call instruction consumes the values above. The `adjust` frame has the receiver at slot 0, and parameter values at slots 1–5. When `adjust` finishes with `lreturn`, the caller receives **one long value** with depth 2 on the operand stack.

**Note:** the number 6 is the depth **of the values used for the call itself**. The actual `max_stack` of the entire `main` method may be higher depending on other operations and instructions.

### 7.3. Inspecting bytecode with `javap`

```bash
javap -c -p FrameCallDemo
javap -v -p FrameCallDemo
```

Areas to look for:

- `FrameCallDemo(int)`: `aload_0` loads `this`, `iload_1` loads the `factor` parameter, `putfield` writes the field, and finally `return`.
- `static long mix(long, double, int)`: `lload_0` loads `base`, `dload_2` loads `ratio`, `iload 4` loads `extra`; multiplication/conversion/addition instructions lead to `lreturn`.
- `long adjust(long, double, int)`: `lload_1`, `dload_3`, `iload 5` prepare arguments for `invokestatic mix`. Then it loads `this.factor` and uses `lreturn`.
- `static void display(long)`: receives `long` in local slots 0–1; at the end of the method there is `return`.
- `main`: `new`, `dup`, `invokespecial <init>` when creating the instance; `invokevirtual adjust` with descriptor `(JDI)J`; `lstore` stores the result and `invokestatic display` prints it.

Exact instruction offsets may differ across compilers, compiler settings, and JDK versions. The list only highlights **core bytecode relationships** to cross-check, without assuming every compiler places instructions at the exact same indices.

### 7.4. `max_locals` is not the number of source parameters

For `adjust(long, double, int)`, right upon entering the method:

```text
Slot 0     : this
Slot 1,2   : long base
Slot 3,4   : double ratio
Slot 5     : int extra
Needs at least 6 local slots
```

For `mix(long, double, int)`:

```text
Slot 0,1   : long base
Slot 2,3   : double ratio
Slot 4     : int extra
Needs at least 5 local slots
```

No `long` or `double` pair is required to start at an even index. `adjust` having `long` at `1–2` and `double` at `3–4` is completely valid.

## 8. Java Passes Parameters by Value, Including References

A misconception arises upon hearing “passing object arguments”: Java **always passes the values** of primitives or references. The caller puts a **copy of the value** into the call; the callee receives that value in a local variable of its own frame.

For primitives:

```java
static void change(int value) {
    value = 99;
}
```

Reassigning the callee's `value` does not change the caller's `int` variable.

For references:

```java
static void mutateBox(Box box) {
    box.value = 99; // Modifies the state of the object shared via reference.
}

static void replaceBox(Box box) {
    box = new Box(); // Only reassigns the callee's local reference.
}
```

The snippet above is **illustrative** and requires declaring `Box` when placed into a program. A standalone example is right below.

### 8.1. Runnable example: mutating an object vs. reassigning a reference

Create the file **`ReferenceValueDemo.java`**:

```java
public class ReferenceValueDemo {
    static class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box box) {
        box.value = 99;
    }

    static void replace(Box box) {
        box = new Box(123);
        System.out.println("inside replace=" + box.value);
    }

    public static void main(String[] args) {
        Box shared = new Box(10);

        mutate(shared);
        System.out.println("after mutate=" + shared.value);

        replace(shared);
        System.out.println("after replace=" + shared.value);
    }
}
```

Run:

```bash
javac ReferenceValueDemo.java
java ReferenceValueDemo
```

Stdout:

```text
after mutate=99
inside replace=123
after replace=99
```

Reason:

- `shared` in `main` holds a **reference value** to the `Box` object.
- When calling `mutate(shared)`, the reference value is copied into parameter `box` at **local slot 0** of the static callee. Both references point to the same object, so changing the field is visible from the caller.
- When calling `replace(shared)`, `box = new Box(123)` only changes **the callee's local slot** to the new object; `shared` in the caller frame still points to the old object with `value = 99`.
- There is no “passing the variable `shared` by reference” that allows the callee to directly overwrite the caller's local slot.

This also applies when passing the receiver `this`: the reference to the object is used to select/invoke the instance method, whereas the object itself is not copied into the new frame.

## 9. Argument Evaluation, Boxing, and Varargs Before Method Invocation

Java code may look like it is just “handing a variable” to a call, but the compiler can emit operations to prepare the values.

### 9.1. Order of argument evaluation

```java
static int first() {
    System.out.print("A");
    return 1;
}

static int second() {
    System.out.print("B");
    return 2;
}

static int add(int a, int b) {
    return a + b;
}
```

When the caller calls `add(first(), second())`, Java evaluates the argument expressions in language order (in the simple case above: `first()` then `second()`), preparing them for `invokestatic add`. Side effects print `A` before `B`. A LIFO stack does **not** mean `second()` executes before `first()`.

### 9.2. Boxing and unboxing

With a call like `accept(Integer.valueOf(7))` or `accept(7)` when the signature takes `Integer`, the compiler may emit a boxing method call before the main method invocation.

With a primitive `int` parameter where the caller has an `Integer`, the compiler may call `intValue()` to unbox, and may throw `NullPointerException` if the reference is null. These calls/conversions are argument-preparation work; the callee ultimately still receives **the type declared in the descriptor**.

### 9.3. Varargs is actually an array parameter

```java
static int count(String... items) {
    return items.length;
}
```

The runtime signature has a parameter of `String[]` (descriptor `([Ljava/lang/String;)I`). For `count("a", "b")`, the compiler typically creates a `String[]` of two elements and passes **one array reference** to the callee. There is no special opcode named `invokevarargs` and there are no two separate local parameters for `"a"`, `"b"`.

However, Java source can pass a matching array directly in a varargs invocation. When inspecting bytecode, do not deduce the slot count merely from the number of varargs elements at the call site.

## 10. Method Descriptor: Map of Argument Types and Return Type

A JVM method descriptor records the **types and order** of parameters, then the return type. Examples:

```text
(I)I                         int → int
(II)I                        (int,int) → int
(JDI)J                       (long,double,int) → long
(Ljava/lang/String;)V        (String) → void
([Ljava/lang/String;)V       (String[]) → void
()D                          () → double
()Ljava/lang/Object;         () → Object
```

Recognition rules:

| Descriptor character | Type |
| --- | --- |
| `B` | `byte` |
| `C` | `char` |
| `D` | `double` |
| `F` | `float` |
| `I` | `int` |
| `J` | `long` |
| `S` | `short` |
| `Z` | `boolean` |
| `V` | `void` (only for return type) |
| `Lpkg/Type;` | Class/interface reference |
| `[` followed by a type | One-dimensional array; multiple `[` for multi-dimensional |

The descriptor **does not record `this`** for instance methods. This often causes confusion when comparing against local slots:

```text
instance method: adjust:(JDI)J

descriptor parameter types: 3
receiver objectref:        1 (implicit on instance call)
parameter local slots:     2 + 2 + 1 = 5
total entry local slots:   1 + 5 = 6

static method: mix:(JDI)J

descriptor parameter types: 3
receiver objectref:        0
parameter local slots:     2 + 2 + 1 = 5
total entry local slots:   5
```

**Do not use the number of commas or the length of the descriptor string** to deduce `max_locals`. For the reference `Ljava/lang/String;`, even though the descriptor string is long, it is still **one category 1 reference** in the JVM.

## 11. Difference Between Normal Completion and Exception Propagation

Suppose:

```java
static int parse(String text) {
    return Integer.parseInt(text);
}
```

If `text` is valid, the callee returns an `int`, and the caller resumes and can use the result.

If `Integer.parseInt` throws `NumberFormatException`:

1. The deeper call does not complete normally.
2. The JVM searches for a matching `catch` handler across frames according to exception dispatch rules.
3. If there is no handler in a frame, that frame is unwound, and its call context is exited.
4. At the selected handler, the exception object is placed into the appropriate operand stack state for the handler to use (typically the sole element on the stack at the handler entry point).
5. There is no normal typed return value for the `parse` call if the exception has not been caught and handled to return to the normal execution path.

A method may use `try/finally` or `try-with-resources`; the Java compiler must ensure appropriate side effects during return/exception. That may add handler/branch bytecode, but it does not turn an exception into `ireturn` or `areturn`.

### 11.1. What happens when the callee is a native method?

For a `native` method, the JVM may transition to native code through a platform-dependent implementation mechanism (e.g., JNI), so argument passing at the ABI/native stack level may differ. However, from the perspective of the Java bytecode caller, the call still obeys the descriptor, objectref/argument values, and result type specified by the JVM.

Therefore, do not assume “if a Java method takes `long` in two slots, then the JNI C function receives exactly two 32-bit registers” without understanding the specific ABI.

## 12. Frame Recursion, Stack Overflow, and Data Lifetime

If a method calls itself, **each invocation has its own frame**:

```java
static int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
```

For `factorial(3)`, the logical frames existing during the deep call:

```text
factorial(3) ─ waiting for factorial(2)
    factorial(2) ─ waiting for factorial(1)
        factorial(1) ─ ireturn 1
    factorial(2) ─ multiply 2 * 1, ireturn 2
factorial(3) ─ multiply 3 * 2, ireturn 6
```

Each callee has local slot `0` holding `n` **specific to that invocation**. The waiting caller does not have its local `n` overwritten when a new frame also uses slot 0.

Deep recursion can lead to `StackOverflowError` when the JVM stack does not have enough room for the needed frames. This is different from `OutOfMemoryError: Java heap space`. Increasing heap `-Xmx` is not the default solution for stack overflow; one should examine the algorithm, recursion depth, and appropriate stack limits.

**Data lifetime:** local primitives or references in a frame do not persist forever after the method ends. If a local holds a reference to an object that is retained by the caller/a static field/another container, the object can remain reachable on the heap after return. A frame becoming inactive does not prove GC will immediately reclaim the object.

## 13. Does the JVM Actually Create a Physical Frame for Every Call?

The JVMS describes **semantics** in terms of frames and operand stacks. An optimizing JVM like HotSpot can perform:

- **Inlining:** replacing the call with the callee's code inside the compiled caller, while preserving Java behavior.
- **Scalar replacement:** eliminating unnecessary allocations or representing data in registers/internal values.
- **Register allocation:** placing arguments/temporaries in CPU registers instead of a layout identical to the local-slot diagram.
- **Deoptimization:** restoring appropriate Java-level state when optimization assumptions no longer hold.
- **Native/intrinsic calls:** executing certain operations via specialized mechanisms, not appearing as a full interpreted bytecode sequence at runtime.

Do not infer that “a small method with `invokestatic` will definitely be slow because it has to create a new OS thread or native frame”. Calling a normal method **does not create a new thread**, and the JIT can optimize away invocation overhead.

When analyzing profiler/thread dump output, some logical frames may be reconstructed or represented according to tool conventions; do not equate every logical Java frame with a fixed region on the machine stack.

## 14. Practice: Viewing `max_locals`, `max_stack`, and the Call Stack

### 14.1. Inspecting `FrameCallDemo` with `javap`

```bash
javac --release 17 FrameCallDemo.java
javap -c -p FrameCallDemo
javap -v -p FrameCallDemo
```

Find the `adjust` method section. In particular, check:

1. **Method descriptor `(JDI)J`.** It describes three parameters and a `long` result.
2. **No `this` in the descriptor**, yet the `aload_0` instruction in the instance method references the receiver.
3. **`lload_1` and `dload_3`:** showing that `long`/`double` start at slots 1/3.
4. **`invokestatic`:** calling `mix` without an objectref.
5. **`lreturn`:** returning `long` using a typed return instruction.
6. **`Code: stack=..., locals=..., args_size=...`:** numbers printed by `javap` to help understanding, but remember `max_locals` and stack depth are different concepts.

Use `javac -g` if you need debug information such as `LocalVariableTable`. Even without debug local-variable names, you can still read the indices through bytecode instructions and the method descriptor.

### 14.2. Understanding an example stack trace

When a Java exception is printed, you commonly see:

```text
Exception in thread "main" java.lang.IllegalArgumentException: invalid
    at Example.callee(Example.java:20)
    at Example.caller(Example.java:12)
    at Example.main(Example.java:5)
```

This is an **illustrative sample**, not the output of the programs above. A stack trace shows the chain of Java calls near the time of the exception: callee at the top, caller below. It does not print the raw local-variable array or operand stack by index.

To inspect method signatures and instructions in detail, use `javap`; to observe calls/runtime frames, use a debugger/profiler/thread dump within the appropriate scope. Avoid predicting the exact physical frame layout from a stack trace.

### 14.3. Distinguishing methods and threads

A call `demo.adjust(...)` **adds a logical frame** on the current thread's JVM stack; it does not create a new thread on its own. Only when the program uses a Thread/Executor/virtual thread mechanism appropriately is there a new thread context for a task. Within each thread, many method frames can appear in the call chain; threads do not share each other's local slots.

## 15. Common Misconceptions

1. **“Method arguments are passed directly into the caller's local slots.”** False. The caller prepares arguments on the **caller's operand stack**; the callee receives them in **its own local-variable array**.
2. **“An instance method has its first parameter at slot 0.”** False. Slot 0 is `this`; the first parameter starts at 1.
3. **“A static method still has `this` at slot 0 but doesn't use it.”** False. A static method receives no receiver; its first parameter starts at 0.
4. **“Having three parameters means needing exactly three slots.”** False when `long` or `double` takes two slots, and an instance receiver adds one slot.
5. **“A constructor returns the object using `areturn`.”** False. `<init>` has return descriptor `V`; the object reference to assign is retained from `new`/`dup` in the caller.
6. **“`ireturn` stores the result straight into the Java variable `result`.”** False. It returns to the caller's operand stack; the caller may `istore` afterward, or use it directly.
7. **“`return` returns a null value.”** False. `return` is for `void` methods and pushes no result.
8. **“Java passes objects by reference so the callee can change the caller's variable.”** False. Java passes **reference values**; reassigning a local parameter does not change the caller's local variable.
9. **“The object is copied every time `this` is used.”** False. The reference is passed; multiple frames can reference the same heap object.
10. **“`invokedynamic` always has `this` like `invokevirtual`.”** False. The argument list comes from the call-site descriptor, with no invariant implicit receiver.
11. **“A method that `throw`s an exception still uses `areturn`.”** False. Exception propagation is abrupt completion, with no typed normal return.
12. **“Every bytecode call always creates an additional physical native stack frame in HotSpot.”** Not a guarantee. The JIT may inline and optimize the layout while preserving Java semantics.
13. **“`max_stack` is the number of open method invocations.”** False. It is the maximum operand stack depth of **one** frame, not the call stack depth.
14. **“Frames of two threads share local slot 0.”** False. Indices only have meaning within each specific frame, not as JVM-wide shared variable names.
15. **“`lreturn` returns two `int` values.”** False. It returns **one category 2 `long` value**.

## 16. Self-Check (with Answers)

**Question 1.** What parameter slots does the method `static double avg(long sum, int count)` have?

**Answer:** `sum` is in slots **0–1**, `count` is in slot **2**. The method needs at least **3 slots** for parameters, descriptor `(JI)D`.

**Question 2.** If `avg(long,int)` becomes an instance method, how do the indices change?

**Answer:** Slot **0** is `this`, `sum` is in **1–2**, `count` is in **3**. The descriptor **is still `(JI)D`**, because the receiver is not written in the descriptor.

**Question 3.** An instance method takes `long, double, int`; what must the caller prepare on the operand stack right before `invokevirtual`?

**Answer:** From bottom to top: **objectref**, **long**, **double**, **int**, matching the descriptor. The total depth allocated for them is **1+2+2+1 = 6** units.

**Question 4.** A method `static long parse(...)` ends with `lreturn`. Where does the value go?

**Answer:** One category 2 `long` is placed onto the **caller's operand stack**; the caller can use it directly or `lstore` it into its own local variable.

**Question 5.** Why does `new SomeType()` not mean the constructor `<init>` returns the reference via `areturn`?

**Answer:** The constructor descriptor returns **`void`**. The `new` bytecode creates an uninitialized object reference; the caller can keep a copy with `dup` while `invokespecial <init>` performs initialization, and then use the retained reference.

**Question 6.** Why does `replace(Box box)` assigning `box = new Box()` not change the value of the caller's `shared` variable?

**Answer:** `box` is a local parameter in the callee frame, holding a copy of the **reference value**. Reassigning it does not write to the local slot holding `shared` in the caller frame.

**Question 7.** If `callee` throws an uncaught exception, does the caller receive a normal return on its operand stack?

**Answer:** No. The JVM performs **abrupt completion** and stack unwinding; there is no normal return value unless the exception path is handled to proceed as a successful call.

**Question 8.** Why does a very small Java method with many calls not necessarily incur corresponding physical frame overhead?

**Answer:** The JIT can inline/optimize the call, using registers and other internal representations; the JVM only has to preserve the invocation and return **semantics** according to Java/JVMS.

## 17. Summary in One Diagram

```text
                 Caller's frame (current)
                 ┌───────────────────────────────┐
                 │ Local variables: private data │
                 │ Operand stack:                │
                 │ [..., receiver?, arg1, arg2]  │
                 └───────────────┬───────────────┘
                                 │ invoke*
                                 │ pops receiver/args per descriptor
                                 ▼
                 Callee's frame (new current)
                 ┌───────────────────────────────┐
                 │ Instance: slot 0 = this       │
                 │ Static:   slot 0 = 1st param  │
                 │ long/double = two local slots │
                 │ Operand stack: initially empty│
                 │ Execute callee instructions   │
                 └───────────────┬───────────────┘
                                 │
                     ┌───────────┴───────────┐
                     │                       │
                  *return                 athrow /
               normal completion          exception
                     │                       │
                     ▼                       ▼
        Result → caller operand        Find handler /
        stack (if non-void)            unwind frames
                     │
                     ▼
            Caller resumes after invoke
```

**Core takeaway:** The caller prepares arguments **on its own operand stack**; the callee receives those values in **the new frame's local-variable array**. **`this` occupies local slot 0 in instance methods**, while static methods start parameters at slot 0. Typed return opcodes transfer **a typed value** back to the caller's operand stack; `void` and exceptions have no normal return value. This model helps read bytecode, descriptors, frames, recursion, and stack traces accurately without equating these concepts with the native stack or physical memory locations.

### Standard References

- [JVMS Java SE 17 — Frames (`2.6`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6).
- [JVMS Java SE 17 — Local Variables (`2.6.1`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.1): rules for `this`, static parameters, and category-2 slots.
- [JVMS Java SE 17 — Operand Stacks (`2.6.2`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.2): argument preparation and method results.
- [JVMS Java SE 17 — Normal/Abrupt Method Invocation Completion (`2.6.4–2.6.5`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.4).
- [JVMS Java SE 17 — Method Descriptors (`4.3.3`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3).
- [JVMS Java SE 17 — Method invocation opcodes (`6.5`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html).
- [JVMS Java SE 17 — Compiling examples: Passing/Receiving Arguments (`3.5–3.6`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-3.html#jvms-3.6).
- [JDK 17 `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
