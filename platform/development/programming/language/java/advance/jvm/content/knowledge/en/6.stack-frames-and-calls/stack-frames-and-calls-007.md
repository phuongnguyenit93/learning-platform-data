# `return` and Variants When a Call Completes Normally

## 1. Goal: What Does "Returning" Mean at the Java Level and at the JVM Level?

In Java source, the `return` keyword terminates the execution of the current method along the normal branch, with a value or without a value. At the JVM level, **a method invocation completes normally (normal method invocation completion)** when the invoked method reaches one of the **six return bytecodes matching its return type** and no exception causes the completion process to fail.

According to **JVMS `2.6.4`**, when the callee completes normally, the JVM:

1. Completes any mandatory tasks before actually terminating the invocation, such as running the corresponding `finally` and handling the monitor of a `synchronized method` according to the relevant semantics.
2. If there is a return value, transfers that exact value from **the operand stack of the callee frame** to **the operand stack of the caller frame**.
3. Terminates the callee frame, restoring the caller frame as the **current frame**.
4. Continues executing the caller at the logical position **immediately after the method invocation instruction**.

For a method returning `void`, no value is pushed onto the caller's operand stack.

~~~text
frame(caller)                          frame(callee)
  locals: ...                            locals: parameters ...
  operand stack before invoke: [args]    initial operand stack: []
          |                                     |
          +------- invoke method ------------> |
                                                | execute code
                                                | ... -> [result]
          <----------- ireturn <----------------+
  operand stack after invoke: [result]   callee frame terminates
  caller continues after invoke
~~~

The diagram illustrates **frame semantics according to the JVM specification**. The JIT compiler may optimize or inline methods; it is not required for every call to have a separate native memory block if Java/JVMS behavior is preserved.

Distinguish three concepts right away:

- **`return` in Java source:** a flow-control statement that can return an expression or terminate a `void` method.
- **`return` opcodes in bytecode:** the virtual machine instructions that actually terminate a method along the normal path, chosen by the **return descriptor**.
- **`ret` in historical bytecode:** jumps back to the point after `jsr` **within the same method**; it is **not** an opcode that returns a value to the method caller and should not be grouped into the six opcodes of this lesson.

## 2. Table of Six Opcodes: Looking at the Name to Know Which Value Returns

JVMS `2.11.8` and `6.5` define the return instructions:

| JVM Opcode | Byte opcode (hex) | Valid method return type | Value that must be on top of the operand stack |
| --- | --- | --- | --- |
| **`return`** | `0xb1` | `void`; constructor `<init>`, class initializer `<clinit>` | No value needs to be returned |
| **`ireturn`** | `0xac` | `int`, **`boolean`, `byte`, `short`, `char`** | A value of **type `int`** |
| **`lreturn`** | `0xad` | `long` | A `long` value |
| **`freturn`** | `0xae` | `float` | A `float` value |
| **`dreturn`** | `0xaf` | `double` | A `double` value |
| **`areturn`** | `0xb0` | **Reference types**: class, interface, array | A descriptor-compatible `reference` value |

Why are there **six** rather than a separate opcode for each Java type?

- The JVM uses `int` as the common computational type for `boolean`, `byte`, `char`, and `short` in many bytecode contexts. Therefore, all five of those types share **`ireturn`**.
- `long`, `float`, and `double` need separate opcodes matching their operand types and execution structure.
- Object, array, and interface values are **references**; they share **`areturn`**.
- `void` has no value, so it uses **`return`**, not a dummy value like `null` or `0`.

**Verifier rules:** `ireturn` is invalid if the method descriptor requires `long`; `areturn` is invalid if the descriptor requires `int`; `return` cannot be used to normally terminate a method declared to return `String`. These constraint rules belong to **JVMS `4.9.2`**.

### How Do `boolean`, `byte`, `short`, and `char` Go Through `ireturn`?

In the callee frame, the value used by `ireturn` is represented as `int`. Before transferring the result to the caller, the JVM has the necessary conversions according to the declared return type:

- `byte`: conversion equivalent to `i2b` (signed narrowing).
- `short`: equivalent to `i2s`.
- `char`: equivalent to `i2c` (unsigned narrowing).
- `boolean`: takes only the low bit, i.e., an `AND 1` operation on the `int` value in `ireturn` semantics.
- `int`: keeps the `int` type.

A normal Java compiler already performs the necessary conversions according to language rules, but the bytecode verifier and the JVM return path must still adhere to the declared type. **There are no `breturn`, `creturn`, `sreturn`, or `zreturn`** in the JVM opcode set.

`long`/`double` values occupy **two slots** in the operand stack model; they are still **one logical value** transferred via `lreturn`/`dreturn`. `float` and `reference` belong to category 1.

## 3. Frame Structure Before and After Return

A Java method call has a frame with a **local variables array**, an **operand stack**, and dynamic linking information via the run-time constant pool. Before the callee executes, arguments are placed into the callee's locals; the new frame's operand stack starts empty.

Example:

~~~java
static int add(int x, int y) {
    int result = x + y;
    return result;
}
~~~

This is an illustrative method that must be placed **inside a class** to compile. A matching bytecode form generated by `javac`:

~~~text
static int add(int, int);
  descriptor: (II)I
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: istore_2
     4: iload_2
     5: ireturn
~~~

If the caller invokes `add(4, 5)`:

~~~text
Caller frame before invoke:
  operand stack: [4, 5]
  instruction: invokestatic add:(II)I

Callee frame upon entering add:
  locals: slot0=x=4; slot1=y=5; slot2=result(unassigned)
  operand stack: []

After iload_0:  [4]
After iload_1:  [4, 5]
After iadd:     [9]
After istore_2: []; local result=9
After iload_2:  [9]
After ireturn:  callee completes, result=9 returns to caller

Caller frame after invoke:
  operand stack: [9]
  next instruction: could be istore, iadd, ireturn,...
~~~

**The return value is transferred back to the caller's operand stack, not automatically assigned to a source variable.** If the caller writes `int answer = add(4,5);`, the caller bytecode usually uses an additional `istore` to write that value into a local slot. If the caller only writes `add(4,5);` and discards the result, the compiler still performs the call and may then use `pop` to discard the unused value.

For a `void` method, the caller's operand stack after invoke **has no added result**, because `return` brings no value back. The caller also cannot use a `void` result in an addition like an `int`.

### The "Path After Invoke" Rule

When a method returns normally, **the caller's PC** continues after the bytecode instruction used to invoke the method: `invokestatic`, `invokevirtual`, `invokeinterface`, `invokespecial`, or `invokedynamic`. The address in this description is the instruction position of the **caller**; one should not think the JVM jumps by Java line number or by constant-pool index.

Example:

~~~text
Caller:
  0: iconst_4
  1: iconst_5
  2: invokestatic #N   // add:(II)I
  5: istore_1
  6: ...
~~~

`#N` is the constant-pool index to identify the call; `5` is the **BCI** immediately after the invoke instruction in the illustrative code; `1` in `istore_1` is the **local slot index**. They are three different index spaces.

## 4. Runnable Java 17+ Code: Six Result Groups

Create the file **`ReturnOpcodes.java`** (a standalone Java 17+ program):

~~~java
public class ReturnOpcodes {
    static void noValue() {
        System.out.println("inside void");
    }

    static int anInt() {
        return 7;
    }

    static boolean aBoolean() {
        return true;
    }

    static byte aByte() {
        return 12;
    }

    static short aShort() {
        return 300;
    }

    static char aChar() {
        return 'A';
    }

    static long aLong() {
        return 4_000_000_000L;
    }

    static float aFloat() {
        return 1.5f;
    }

    static double aDouble() {
        return 2.25;
    }

    static String aReference() {
        return "JVM";
    }

    static int[] anArray() {
        return new int[] {2, 3};
    }

    static String aNullReference() {
        return null;
    }

    public static void main(String[] args) {
        noValue();
        System.out.println("int=" + anInt());
        System.out.println("boolean=" + aBoolean());
        System.out.println("byte=" + aByte());
        System.out.println("short=" + aShort());
        System.out.println("char=" + aChar());
        System.out.println("long=" + aLong());
        System.out.println("float=" + aFloat());
        System.out.println("double=" + aDouble());
        System.out.println("reference=" + aReference());
        System.out.println("array=" + java.util.Arrays.toString(anArray()));
        System.out.println("null reference=" + aNullReference());
    }
}
~~~

Compile and run:

~~~bash
javac -g ReturnOpcodes.java
java ReturnOpcodes
~~~

**Exact stdout:**

~~~text
inside void
int=7
boolean=true
byte=12
short=300
char=A
long=4000000000
float=1.5
double=2.25
reference=JVM
array=[2, 3]
null reference=null
~~~

Why does the output help distinguish bytecodes?

- `noValue()`: prints the message, then uses the `return` opcode at the end of the method (even though `return;` is not explicitly written in the source).
- `anInt()`, `aBoolean()`, `aByte()`, `aShort()`, `aChar()`: all five end with **`ireturn`** in a valid class file.
- `aLong()`, `aFloat()`, `aDouble()`: respectively **`lreturn`**, **`freturn`**, **`dreturn`**.
- `aReference()`, `anArray()`, and `aNullReference()`: all are **`areturn`** even though the result may be a String reference, an array reference, or `null`. `null` is a valid reference value; **there is no `nullreturn` opcode**.

In Java source, `boolean` is a separate type; in the JVM, `ireturn` uses an `int` representation according to the rules. The program above does **not** test abnormal bytecode behavior; it is standard evidence for how the compiler lowers return types in a class file.

### Using `javap` to Verify Actual Opcodes

~~~bash
javap -c -p ReturnOpcodes
javap -s -p ReturnOpcodes
javap -v -p ReturnOpcodes
~~~

How to read:

1. With `-s`, look at the descriptors `()V`, `()I`, `()Z`, `()B`, `()S`, `()C`, `()J`, `()F`, `()D`, `()Ljava/lang/String;`, `()[I`.
2. With `-c`, find the final opcode of the corresponding methods: `return`, `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`.
3. With `-v`, read `Code: stack=..., locals=...` along with line numbers/constant pool. `javac -g` helps show debug information to correlate with source.
4. Avoid treating the exact bytecode offsets and constant-pool indices described in the lesson as "canonical values": they can differ depending on the JDK/compiler or target release.

Example disassembly **illustrating structure, without guaranteeing fixed BCI/constant-pool indices**:

~~~text
static int anInt();
  descriptor: ()I
  Code:
     0: bipush        7
     2: ireturn

static long aLong();
  descriptor: ()J
  Code:
     0: ldc2_w        #...   // long 4000000000l
     3: lreturn

static java.lang.String aReference();
  descriptor: ()Ljava/lang/String;
  Code:
     0: ldc           #...   // String JVM
     2: areturn

static void noValue();
  descriptor: ()V
  Code:
     ... invokevirtual #... // PrintStream.println
     ... return
~~~

In the source example above, a compiler may choose a different instruction to load a constant, but the **return instruction matching the descriptor** must follow JVM rules.

## 5. The Descriptor Determines the Valid Return Opcode

The **method descriptor** in the class file specifies the form `(parameter types)return type`, for example:

| Java Method | JVM descriptor | Return opcode |
| --- | --- | --- |
| `void write()` | `()V` | `return` |
| `int sum(int,int)` | `(II)I` | `ireturn` |
| `boolean valid()` | `()Z` | `ireturn` |
| `byte code()` | `()B` | `ireturn` |
| `short id()` | `()S` | `ireturn` |
| `char initial()` | `()C` | `ireturn` |
| `long count()` | `()J` | `lreturn` |
| `float ratio()` | `()F` | `freturn` |
| `double average()` | `()D` | `dreturn` |
| `String label()` | `()Ljava/lang/String;` | `areturn` |
| `int[] numbers()` | `()[I` | `areturn` |
| `Object[][] matrix()` | `()[[Ljava/lang/Object;` | `areturn` |

Notations such as `I`, `J`, `V`, `L...;`, and `[` belong to **JVMS `4.3`**. When analyzing bytecode, **the return type recorded in the descriptor** is the source for determining which opcode is valid; the type of a local variable that happens to be on the stack beforehand does not by itself allow using a different return opcode.

For example, `return 42;` in a method declared `long` is processed by the compiler into a `long` value, possibly via `i2l` or loading a long constant directly, and then ends with **`lreturn`**; `ireturn` cannot simply be used to return `long` just because the source expression originally started as the integer 42.

### Why Is a Method Reference Different from a Method Return?

A call `foo()` in the caller bytecode has a **symbolic method reference** (owner/name/descriptor) or corresponding call site; the return instruction runs **in the callee** when the method finishes executing. `return` does not need to contain the caller's constant-pool index, nor does it re-select the target method. Method invocation and method completion are two different steps.

## 6. `void` Methods, Constructors, and `<clinit>`

### Java Source Without Writing `return;` Still Has a Return Opcode

~~~java
static void show() {
    System.out.println("done");
}
~~~

Method `show` ends when it reaches the end of the block. The compiler emits the corresponding `return` opcode so the VM knows the `void` method has completed.

You can also write:

~~~java
static void choose(boolean stop) {
    if (stop) {
        return;
    }
    System.out.println("continue");
}
~~~

In a `void` method, `return;` **has no expression**. Bytecode may have multiple paths leading to a `return` opcode, or branches/gotos leading to a common return point. There is **no** valid `return void;` or `return null;` in a `void` method.

### Constructor: `<init>` Bytecode Ends with `return`

Java constructors do not declare a return type:

~~~java
class Ticket {
    final int number;

    Ticket(int number) {
        this.number = number;
    }
}
~~~

This is an illustrative class without a `main` to run standalone. In the class file, the constructor is an **instance initialization method** named `<init>` with descriptor `(I)V`. The `return` instruction terminates execution of the **constructor**, whereas the expression `new Ticket(5)` has a reference value provided by the allocation/invocation mechanism on the caller side.

A common point of confusion: **a constructor having a descriptor returning `V` does not mean the `<init>` opcode returns the object itself**. When source writes `new Ticket(5)`, the expression's result is an object reference, but the constructor is invoked via `invokespecial` and completes with `return`, not `areturn`.

### Class Initializer: `<clinit>` Also Uses `return`

The compiler may generate a special method `<clinit>` for `static` initialization expressions and `static` blocks. It has descriptor `()V` and completes normally with the `return` opcode. `<clinit>` cannot be declared or called directly using normal Java syntax.

If a static initializer throws an exception and causes class initialization to fail, that is **not** a normal completion via `return`. The runtime applies the specific class initialization error rules of JVMS/JLS.

## 7. `return` Terminates a Call, While Legacy `ret` Does Not

In historical bytecode, `jsr`/`ret` were once used for **subroutines within the same method**, often related to old `finally` compilation strategies.

~~~text
A method:
  jsr Lcleanup     ; pushes returnAddress to the next instruction
  ireturn          ; ONLY AFTER cleanup finishes, returns int to the method caller

Lcleanup:
  astore_2         ; stores returnAddress in local slot 2
  ... cleanup ...
  ret 2            ; jumps back to the instruction after jsr, within the same method
~~~

This is a **historical bytecode diagram, not a complete program to load into the JVM**. `ret` uses a `returnAddress` value in a local slot to transfer the PC within the method. `ireturn` uses an `int` on the operand stack to complete the method and transfer the value back to the caller. **The two instructions do not have the same function**, even though both names contain "ret/return".

According to **JVMS `4.9.1`**, class files with **major version ≥ 51 (Java 7+)** must not contain `jsr`, `jsr_w`, and `ret` in `Code`. Therefore, in bytecode generated by modern `javac`, look for the **six return opcodes** listed in section 2, and do not create new examples using `ret`.

## 8. `finally`: A Source `return` May Not Be a Return Opcode Immediately

A common mistake is assuming that whenever `return expression;` appears in source, the JVM immediately executes `ireturn`/`areturn` at that exact spot. With `try/finally`, Java must complete the work of `finally` before the method actually returns normally.

Create the file **`FinallyReturns.java`**:

~~~java
public class FinallyReturns {
    static int normal(int input) {
        try {
            System.out.println("try=" + input);
            return input * 2;
        } finally {
            System.out.println("finally=" + input);
        }
    }

    static int overrideReturn() {
        try {
            return 10;
        } finally {
            return 20; // warning example: avoid writing return in finally
        }
    }

    static int fail() {
        try {
            System.out.println("start");
            throw new IllegalStateException("boom");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        System.out.println("normal=" + normal(4));
        System.out.println("overridden=" + overrideReturn());

        try {
            fail();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Commands:

~~~bash
javac -g FinallyReturns.java
java FinallyReturns
~~~

**Exact stdout:**

~~~text
try=4
finally=4
normal=8
overridden=20
start
cleanup
caught=boom
~~~

### Interpreting the Three Branches

**`normal(4)`**: the expression `input * 2` evaluates to 8; `finally` prints the message; finally the call returns the value 8. In bytecode, the compiler may temporarily store 8 in a local slot, execute the `finally` code, and only then use `ireturn`. A single source statement `return input * 2;` can therefore be implemented across **multiple opcodes and multiple BCIs**.

**`overrideReturn()`**: `finally` has `return 20;`, so the result `10` intended to be returned from `try` **is replaced** by 20. In Java, if `finally` completes abruptly via another `return` or throws an exception, the previous completion reason of `try` can be replaced. This is why **you should not use `return` in `finally` in real code**: it obscures the previous result or exception. The example is given to understand semantics, not to recommend this coding style.

**`fail()`**: throws `IllegalStateException`, runs `finally` to print `cleanup`, and then the exception propagates to the caller. Method `fail` **does not complete normally**, and returns no `int` result to `main`. `main` catches the exception and then continues running normally.

### Why Can `javap` Display Multiple Return Opcodes?

~~~bash
javap -c -p FinallyReturns
javap -v -p FinallyReturns
~~~

In `normal`, you can see multiple branches and code segments printing `finally` on different exit paths. The compiler may duplicate the `finally` code or organize appropriate handlers; **it is not required to have only one `ireturn` opcode per method**. In method `overrideReturn`, the compiler might not emit an `ireturn` path that actually returns 10 because `finally` always replaces the result.

What determines whether a method **has completed normally** is **the final return opcode executed along the specific path and other constraints**, not the number of `return` keywords you count in Java source.

## 9. `return` Differs from `throw` and Abrupt Completion

The normal path (normal completion) differs from **abrupt completion**:

| Situation | Callee frame | What does the caller receive? |
| --- | --- | --- |
| `return;` in a `void` method | Terminates normally | No return value |
| `return 5;` from an `int` method | Terminates normally | An `int` value 5 |
| `return obj;` from an `Object` method | Terminates normally | A reference (possibly `null`) |
| Exception caught and handled **inside** the callee, then `return` | Eventually completes normally | Appropriate result if any |
| Exception **not handled** in the callee | Terminates abruptly | **No result**; exception continues searching for an outer handler |
| `finally` itself throws an exception | May cause abrupt termination even if try already computed a result | No normal result if the exception exits to the caller |

According to **JVMS `2.6.5`**, an invocation that completes abruptly **never returns a normal value to the caller**. This is a very important point when reading the `athrow` opcode: it handles exceptions, and is **not** another kind of `return`.

A Java method declared `int` can throw an exception without executing `ireturn` on that path. Compiler rules checking return-path completeness in source need to account for paths that always `throw`; the JVM verifier checks bytecode paths separately.

### Short Java 17+ Example of an Exception Caught Before Return

~~~java
static int parseOrDefault(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return -1;
    }
}
~~~

This is an illustrative method inside a class. If parsing succeeds, it returns the parsed `int`; if parsing throws `NumberFormatException` and it is caught right inside the method, the method still completes normally via `ireturn` with the value -1. One must not say that "whenever an exception occurs, the invocation is definitely abnormal": **only an exception that escapes unhandled from the callee** causes that invocation to complete abruptly.

## 10. `synchronized method`: The Monitor Is Handled on Return

When a method has the `synchronized` modifier, the JVM must provide monitor entry/exit semantics for the corresponding object:

- **Instance synchronized method** locks the monitor of the receiver, i.e., `this`.
- **Static synchronized method** locks the monitor associated with the `Class` object representing that class.
- When the method completes normally, the JVM handles exiting the monitor (or updating the reentrancy count) as if the appropriate `monitorexit` had been executed.
- On an unhandled exception path, the JVM must also handle monitor release according to the appropriate rules.

Technical point: **`javac` usually does not generate explicit `monitorenter`/`monitorexit` wrapping the body of a `synchronized method`**. The method is marked **`ACC_SYNCHRONIZED`**, and the VM's invocation/return mechanism handles the monitor. Conversely, a **`synchronized (lock) { ... }` block** in source is usually compiled into `monitorenter`/`monitorexit` and the necessary exception handler in `Code`.

Create the file **`SynchronizedReturn.java`**:

~~~java
public class SynchronizedReturn {
    private int counter;

    public synchronized int increment() {
        counter++;
        return counter;
    }

    public static void main(String[] args) {
        SynchronizedReturn sample = new SynchronizedReturn();
        System.out.println("first=" + sample.increment());
        System.out.println("second=" + sample.increment());
    }
}
~~~

~~~bash
javac -g SynchronizedReturn.java
java SynchronizedReturn
javap -v -p SynchronizedReturn
~~~

**Program stdout:**

~~~text
first=1
second=2
~~~

In `javap -v -p`, look for the `increment` method with **`ACC_PUBLIC, ACC_SYNCHRONIZED`**, descriptor `()I`, and opcode `ireturn`. The JVM ensures the corresponding monitor is handled when the method completes; returning 1/2 does not cause the lock to remain held forever. The `javap` command run after the program will print **additional metadata/disassembly**, which is not part of the stdout of the two print statements from the program.

**Note:** Java `synchronized` is a thread synchronization mechanism; a single-threaded example demonstrates predictable output, **not** correctness under all contention scenarios. To analyze concurrency, one must look at the Java Memory Model, lock rules, and multi-threaded scenarios.

## 11. Opcodes, Slots, and Descriptors: Avoid Confusing the Three Layers

### `max_stack`/`max_locals` Is Not the Number of Results

A `Code` attribute in a class file contains `max_stack` and `max_locals`:

- `max_stack` indicates the maximum depth in **slots** the operand stack can reach while the method runs.
- `max_locals` indicates the capacity of local slots for the method.
- A method return can push **one logical result** to the caller, though that result may occupy 1 or 2 operand-stack slots.

Example:

~~~text
callee: long produce()
  descriptor: ()J
  operand stack right before lreturn: [long 4000000000]
  logical values: 1
  stack slots occupied by long: 2

caller: long n = produce()
  after invoke, caller operand stack: [long 4000000000]
  then lstore_<n> writes to 2 consecutive local slots
~~~

The diagram above describes the JVMS model; in `javap`, `lstore` has a local slot index, whereas `#N` in `invokestatic #N` is a constant-pool index. There is no requirement that the `lreturn` instruction must point to the constant pool to know which slot holds the value.

### Booleans and Arrays Do Not Need Separate Return Opcodes

`boolean ok()` in source produces descriptor `()Z` but ends with `ireturn`; `int[] data()` produces descriptor `()[I` but ends with `areturn`. This is a **virtual machine-level rule**; descriptor symbols and opcode categories do not have names identical to Java keywords.

### Return Statement in a Loop

~~~java
static int firstPositive(int[] values) {
    for (int value : values) {
        if (value > 0) {
            return value;
        }
    }
    return -1;
}
~~~

This is an illustrative method that must be placed in a class. A loop **does not create a new frame** on each iteration; there is only one method call and one frame. There can be multiple `ireturn` opcodes, each path leading to one of them. Branches that do not terminate continue the method; whichever return opcode actually executes determines where the call ends.

## 12. Common Mistakes When Learning and Reading Return Bytecode

| Misconception | Correct Understanding |
| --- | --- |
| "Java has 8 primitive types, so there must be 8 return opcodes." | `boolean`, `byte`, `char`, and `short` share `ireturn` with `int`; `void`, references, and wide numbers have separate opcodes. |
| "`ireturn` always requires a method declared `int`." | It is also valid for `boolean`, `byte`, `short`, and `char` methods. |
| "`return` is the bytecode that returns `null`." | `return` is for `void`; a `null` reference is pushed and then returned via `areturn`. |
| "`areturn` only returns Java Objects, not arrays." | Arrays are also a JVM reference type, so they use `areturn`. |
| "`lreturn`/`dreturn` return two values." | They return one category 2 value, which occupies two operand-stack slots. |
| "Java's `return 5;` is always `ireturn`." | It depends on the **method descriptor**: a `long` method must return via `lreturn`. |
| "The caller always receives the value in local variables right when invoke finishes." | The return result is placed onto **the caller's operand stack**; the caller may then store it into a local. |
| "Each source `return` corresponds to exactly one return opcode at the same BCI." | The compiler may arrange control flow and `finally` before actually returning. |
| "`ret` is shorthand for `return`." | `ret` is a legacy subroutine branch, not a method return. |
| "If the callee throws an exception, it also returns an exception object via `areturn`." | An uncaught exception causes **abrupt completion**, returning no normal value. |
| "`finally` runs after the callee has already returned the value to the caller." | `finally` must complete before the caller receives a normal result; `finally` itself can change the result/exception. |
| "`synchronized method` must always have a `monitorexit` opcode printed in Code." | Monitor entry/exit for a method is managed via `ACC_SYNCHRONIZED` and invocation/return semantics. |
| "Constructor `new C()` uses `areturn` to return the object." | `<init>` has descriptor `()V` and uses `return`; the value of the `new` expression is produced by caller-side object construction logic. |
| "A `void` method reaching the end of its source block has no return instruction." | The compiler must generate a valid bytecode termination path using `return` per JVM semantics. |
| "JIT method inlining means the JVM ignores return rules." | Implementation optimizations may change the shape of native code, but must preserve observable return semantics. |

## 13. Self-Check Exercises

**Q1.** Do `boolean valid()` and `int answer()` have the same normal completion opcode?  
**Answer:** Yes, both use **`ireturn`** according to their respective descriptors.

**Q2.** Method `long count()` has `return 2;` in source. What is the terminating opcode?  
**Answer:** **`lreturn`**, because the method is declared `long`. The compiler must produce an appropriate long value before returning.

**Q3.** What opcodes do `String[] names()` and `int[] numbers()` use?  
**Answer:** Both use **`areturn`**, because arrays are reference types.

**Q4.** When `callee()` returns `int 9` normally, where is the result when the caller frame resumes?  
**Answer:** On **the caller's operand stack**; the caller can use it immediately in an operation or write it to a local.

**Q5.** Does `return;` in a `void` method push `null` onto the caller?  
**Answer:** No. The `return` opcode transfers no value.

**Q6.** What JVM descriptor does constructor `Ticket(int)` have, and what is its normal final opcode?  
**Answer:** `(I)V`, using **`return`**. A constructor does not return an object reference via `areturn`.

**Q7.** What value does the caller receive from `try { return 10; } finally { return 20; }`?  
**Answer:** **20**, because `finally` replaces the previous completion reason. This style of code should not be used in practice.

**Q8.** An `int` method throws an exception that is not caught inside the method itself. Does any `ireturn` deliver a value back to the caller?  
**Answer:** No, the invocation completes **abruptly** and has no normal return value.

**Q9.** Is `ret 2` in an old Java 6 file equivalent to `ireturn`?  
**Answer:** No. `ret` uses a `returnAddress` to jump within the same method after `jsr`. `ireturn` terminates the method and returns an `int` to the caller.

**Q10.** Does a `synchronized int increment()` method require the compiler to insert an explicit `monitorenter`/`monitorexit` pair in the Code body?  
**Answer:** No, not for method-level synchronization locking; the JVM handles the monitor implicitly via `ACC_SYNCHRONIZED`, and `ireturn` participates in the normal termination path.

## 14. Official References

- [JVMS Java SE 25 — `2.6` Frames](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6): frames, local variables, operand stack, and caller/callee transfer of control.
- [JVMS Java SE 25 — `2.6.4` Normal Method Invocation Completion](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.4): normal termination, restoring the caller, returning a value.
- [JVMS Java SE 25 — `2.6.5` Abrupt Method Invocation Completion](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6.5): abrupt termination with no normal result.
- [JVMS Java SE 25 — `2.11.8` Method Invocation and Return Instructions](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.11.8): mapping data types to return opcodes.
- [JVMS Java SE 25 — `6.5` JVM Instructions](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): entries for `return`, `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`, and synchronized monitor constraints.
- [JVMS Java SE 25 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3): notations `V`, `I`, `J`, `F`, `D`, `L...;`, `[`, and method descriptor format.
- [JVMS Java SE 25 — `4.9.2` Structural Constraints](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.9.2): return opcode must match the declared return type.
- [JLS Java SE 25 — `14.17` The return Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.17): `return` in Java source, including with `try/finally`.
- [JLS Java SE 25 — `14.20.2` Execution of try-finally](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.2): how `finally` affects normal/abrupt completion.
- [Oracle JDK 25 — `javap`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): using `javap -c -s -v -p` to inspect return opcodes, descriptors, and metadata.

**Keep in mind when reading bytecode:** look at the method's **return descriptor** first, then check the **return opcode** on each branch. A call only completes normally when the right return instruction executes and required processing finishes; **the value goes back to the caller's operand stack**, whereas an unhandled exception causes the invocation to complete abruptly and **produces no normal result**.
