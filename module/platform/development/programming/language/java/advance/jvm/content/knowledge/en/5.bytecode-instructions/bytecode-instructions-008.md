# getfield, putfield, getstatic, and putstatic When Accessing Fields in the JVM

## Lesson Objectives

When reading Java source code, expressions like `object.count`, `object.count = 5`, `Counter.total`, or `Counter.total = 10` look almost identical. At the JVM bytecode level, they belong to **two different access groups**: fields attached to an object (*instance fields*) and fields of a class (*static fields*). In addition, read and write operations also use different opcodes.

After this lesson, you will be able to:
- Accurately distinguish the four instructions **`getfield`, `putfield`, `getstatic`, `putstatic`** by object vs. class, read vs. write.
- Explain the operand stack before/after each instruction; understand why `getfield`/`putfield` require `objectref`, while static instructions do not.
- Trace the bytecode index operand to **`CONSTANT_Fieldref`** and the meaning of owner, field name, descriptor, and resolution.
- Recognize the impact of `getstatic`/`putstatic` on **class initialization**, rules for `final`, `volatile`, and runtime errors.
- Compile Java 17+ examples, use **`javap -c -v -p`** to identify and explain bytecode in constructors, class initializers, and regular methods.
- Avoid confusing field hiding with method overriding, field access with local variables, and constant inlining with runtime field reads.

## 1. Comparison Table of the Four Opcodes

| Opcode | JVM Opcode | Field Type | Action | Operand Stack Operation |
| --- | --- | --- | --- | --- |
| `getfield` | 180 (`0xb4`) | Instance | Read field value from object | `..., objectref → ..., value` |
| `putfield` | 181 (`0xb5`) | Instance | Write value to object's field | `..., objectref, value → ...` |
| `getstatic` | 178 (`0xb2`) | Static | Read field value of declaring class/interface | `... → ..., value` |
| `putstatic` | 179 (`0xb3`) | Static | Write value to field of declaring class/interface | `..., value → ...` |

This is the **operand stack model**, where `...` represents lower elements unchanged by the instruction. The stack is written from bottom (left) to top (right).

- **`getfield`** needs an object reference to know which instance is being read; it pops `objectref` and then pushes the field value.
- **`putfield`** needs both an object reference and a new value, with **`value` on top** and `objectref` immediately below it; the instruction pops both and does not leave a value on the stack.
- **`getstatic`** does not need an objectref; a static field is attached to the resolved class/interface.
- **`putstatic`** only needs the new value on the stack.

All four instructions have the same bytecode format consisting of one opcode and **two index operand bytes**:

~~~text
getfield    indexbyte1 indexbyte2
putfield    indexbyte1 indexbyte2
getstatic   indexbyte1 indexbyte2
putstatic   indexbyte1 indexbyte2

constant-pool index = (indexbyte1 << 8) | indexbyte2
~~~

That operand is an unsigned **16-bit** index into the *run-time constant pool* of the currently executing class. It is **not a direct offset of the field in memory**, nor is it the address of an object. When viewed with `javap`, it is printed as `#N` accompanied by a comment about the referenced field.

## 2. Two Field Types: Instance and Static

Consider the class definition:

~~~java
public class Counter {
    int count;           // Instance field
    static int total;    // Static field
}
~~~

This is an **illustrative declaration class**; it does not have a `main` method to run yet. Meaning:

- Each `new Counter()` object has its **own** `count` state. Reading `a.count` and `b.count` can return different values.
- The `total` field belongs to the **`Counter` class** according to Java semantics. Every instance of that same class definition accesses the same static field.
- Instance fields and static fields are two separate access symbol kinds; a `getfield` opcode **must not be used to read a static field**, and `getstatic` **must not be used to read an instance field**.
- The Java type of the field (`int`, `long`, `String`, ...) does not determine whether `getfield` or `getstatic` is used; **whether it is static** is the distinguishing factor.

Source code example:

~~~java
Counter a = new Counter();
Counter b = new Counter();
a.count = 3;
b.count = 8;
Counter.total = 11;
~~~

The assignments to `a.count` and `b.count` typically compile to **`putfield`** with different objectrefs; the assignment to `Counter.total` typically uses **`putstatic`**. This snippet illustrates expressions; to run it, it must be placed inside a valid class/method.

### How Do Local Variables, Array Elements, and Object Properties Differ?

| Source Code / Task | Common Bytecode Group |
| --- | --- |
| Read a local variable `int n` | `iload`, `iload_0`... |
| Write a local variable `int n` | `istore`, `istore_0`... |
| Read/write instance field | `getfield` / `putfield` |
| Read/write static field | `getstatic` / `putstatic` |
| Get array length `array.length` | `arraylength` |
| Read/write array element `arr[i]` | `iaload/iastore`, `aaload/aastore`, and other variants depending on type |

Java arrays have a special `length` property, but it is **not read using `getfield`**. Array access operators are implemented via the array instruction set. A JavaBean getter like `obj.getCount()` is a **method call** (such as `invokevirtual`), not automatically a `getfield` for the caller. A field named `count` and a method named `getCount` are two different members.

## 3. Operand Stack in Instance Field Access Instructions

### `getfield`: Pop Reference, Push Value

Suppose `counter` has `count = 7`. Source code:

~~~java
int result = counter.count;
~~~

A conceptual bytecode form:

~~~text
aload_1              // stack: [..., objectref]
getfield #12         // stack: [..., 7]
istore_2             // stack: [...]
~~~

The `objectref` value comes from `aload_1` (assuming the `counter` variable is in local slot 1); the index `#12` is illustrative and **is not a fixed index**. Before `getfield`, the JVM must have a valid reference to an instance of the appropriate type on top of the stack. After `getfield`, that reference is consumed, leaving only the read field value.

If the instance field has type `long` or `double`, the value returned onto the stack belongs to **category 2** (occupying two units of depth); `int`, `float`, and reference types are category 1. For fields with descriptors `Z`, `B`, `C`, `S`, the stack value uses the **`int`** representation per JVM rules; this does not mean all fields inside the object have 32 bits of physical storage.

### `putfield`: Required Stack Order

For the statement:

~~~java
counter.count = 9;
~~~

Common bytecode form:

~~~text
aload_1              // stack: [..., objectref]
bipush 9             // stack: [..., objectref, 9]
putfield #12         // stack: [...]
~~~

**Objectref is below value**. The reverse order will not satisfy the stack contract of `putfield`. When compiling an assignment expression **whose result value is used**, the compiler may use instructions such as `dup`/`dup_x1`/`dup2_x1` to retain a copy of the value before `putfield` consumes the operands. `putfield` itself **does not push the assignment result**.

The statement `counter.count++` typically consists of read-then-write steps:

~~~text
aload_1
dup
getfield #12
iconst_1
iadd
putfield #12
~~~

This is a model illustrating the increment operation on an **int instance field**. The `iinc` opcode only operates directly on int local variables and **does not** replace the entire `getfield` + `iadd` + `putfield` sequence. For types smaller than int, the compiler may need narrowing conversions such as `i2b`, `i2s`, or `i2c`.

**Incrementing a field via a sequence of instructions does not mean it is atomic.** If multiple threads execute `counter.count++` concurrently without synchronization, they can read the same value, compute, and overwrite each other; `volatile` alone also does not turn a read-modify-write operation into an atomic one (see the concurrency section).

## 4. Static Field Access and Class Initialization

### `getstatic`

Reading a static field:

~~~java
int x = Counter.total;
~~~

Illustrative bytecode:

~~~text
getstatic #18         // stack: [..., total]
istore_1              // stack: [...]
~~~

There is no need to `aload` a `Counter` object before `getstatic`. The JVM resolves the reference to the field, and if **the class or interface that actually declares that field** has not yet been initialized, `getstatic` triggers initialization according to JVMS rules (`5.5), except in cases where the code has been compiled in another form such as an inlined compile-time constant.

### `putstatic`

Writing a static field:

~~~java
Counter.total = 20;
~~~

Common bytecode:

~~~text
bipush 20             // stack: [..., 20]
putstatic #18         // stack: [...]
~~~

During actual execution, `putstatic` also requires the class/interface **declaring the resolved field** to complete initialization if it has not already done so, before writing the new value according to JVM rules.

### Why Is Class Initialization Important?

During the **preparation** phase, static fields (excluding certain constant assignments via `ConstantValue`) are prepared with **default values** according to their types: 0 for `int`, `false` for `boolean`, `null` for references. The **initialization** phase runs the class initializer `<clinit>` if present, executing static initializers/initialization expressions in the order specified by Java.

Once the class has been successfully initialized, reading with `getstatic` returns the current value of the field. If initialization fails, access can lead to `ExceptionInInitializerError` or, on subsequent uses, `NoClassDefFoundError`, depending on the case.

Avoid generalizing that "the first mention of a class name initializes the class": class literals `SomeClass.class`, inlined compile-time constants, and many reflection/class-loading operations have their own rules. Precisely stated, **reading/writing a resolved static field via the getstatic/putstatic opcodes** is one of the operations that triggers class initialization.

## 5. Java 17+ Example Using All Four Opcodes

Create the exact file **`FieldOpsDemo.java`**:

~~~java
public class FieldOpsDemo {
    static int total = 10;
    int value;

    FieldOpsDemo(int initial) {
        value = initial;
    }

    static int change(FieldOpsDemo target) {
        int current = target.value;
        target.value = current + 2;

        int previousTotal = total;
        total = previousTotal + 1;

        return target.value + total;
    }

    public static void main(String[] args) {
        FieldOpsDemo box = new FieldOpsDemo(5);
        System.out.println("sum=" + change(box));
        System.out.println("value=" + box.value);
        System.out.println("total=" + total);
    }
}
~~~

Compile and run on **JDK 17 or newer**:

~~~bash
javac --release 17 FieldOpsDemo.java
java FieldOpsDemo
~~~

**Exact stdout:**

~~~text
sum=18
value=7
total=11
~~~

Analysis:

1. Before executing `main`, the `FieldOpsDemo` class is initialized. The declaration `static int total = 10;` normally causes the compiler to generate a section in `<clinit>` containing **`putstatic FieldOpsDemo.total:I`**.
2. The constructor receives `initial = 5` and writes `this.value = 5` using **`putfield FieldOpsDemo.value:I`**.
3. In `change`, `target.value` is read via **`getfield`**, added with 2, and then written back using **`putfield`**.
4. `total` is a static field, so reading it into `previousTotal` uses **`getstatic`**, and the assignment `total = previousTotal + 1` uses **`putstatic`**.
5. The return expression reads both `target.value` via **`getfield`** and `total` via **`getstatic`**, computing `7 + 11 = 18`.

Inspecting the bytecode and constant pool:

~~~bash
javap -c -p FieldOpsDemo
javap -v -p FieldOpsDemo
~~~

Look in the `change` method for lines with comments of the form:

~~~text
getfield     #N  // Field value:I
putfield     #N  // Field value:I
getstatic    #M  // Field total:I
putstatic    #M  // Field total:I
~~~

The above is a **pattern to recognize**, not the complete output of a specific build. The `#N` and `#M` indices, offsets, and choice of certain instructions depend on the compiler/version. In `main`, there is also `getstatic java/lang/System.out:Ljava/io/PrintStream;` to obtain the console output stream; this is an example of a static field **belonging to a different class** from `FieldOpsDemo`.

### Tracing the Operand Stack in the `change` Method

Suppose local slot 0 holds `target`:

~~~text
Instance read step:
  aload_0               Stack [target]
  getfield value:I      Stack [5]
  istore_1              Stack []

Instance write step:
  aload_0               Stack [target]
  iload_1               Stack [target, 5]
  iconst_2              Stack [target, 5, 2]
  iadd                  Stack [target, 7]
  putfield value:I      Stack []

Static read step:
  getstatic total:I     Stack [10]
  istore_2              Stack []

Static write step:
  iload_2               Stack [10]
  iconst_1              Stack [10, 1]
  iadd                  Stack [11]
  putstatic total:I     Stack []
~~~

This is a **logical analysis diagram**; the opcode order in actual disassembly may appear in equivalent forms. The core invariant is that the values on the stack match the instruction contract and field descriptor.

## 6. Fieldref in the Constant Pool: Owner + Name + Descriptor

The four opcodes do not contain the field name as text directly inside the instruction operand. They use a **`CONSTANT_Fieldref`** index in the run-time constant pool of the currently executing class.

A typical symbolic reference has the chain:

~~~text
getfield #12
    |
    +--> #12 CONSTANT_Fieldref
           |
           +--> class_index --------> CONSTANT_Class
           |                              |
           |                              +--> CONSTANT_Utf8 "org/example/Account"
           |
           +--> name_and_type_index -> CONSTANT_NameAndType
                                         |
                                         +--> CONSTANT_Utf8 "balance"
                                         +--> CONSTANT_Utf8 "J"
~~~

Accordingly, a symbolic reference can mean:
**`org/example/Account.balance:J`**, meaning a field named `balance` with descriptor `J` (`long`) belonging to the class/interface determined via resolution rules.

The `CONSTANT_Fieldref_info` format has tag 9 and two indices: `class_index` and `name_and_type_index`. `CONSTANT_NameAndType` in turn points to two `CONSTANT_Utf8` entries: the **field name** and the **field descriptor**. An index cannot be understood properly by just looking at a number `#12` without tracing the entire entry chain.

Some common field descriptors:

| Descriptor | Java Type |
| --- | --- |
| `I` | `int` |
| `J` | `long` |
| `D` | `double` |
| `F` | `float` |
| `Z` | `boolean` |
| `B` | `byte` |
| `S` | `short` |
| `C` | `char` |
| `Ljava/lang/String;` | `java.lang.String` |
| `[I` | `int[]` |
| `Ljava/util/List;` | `java.util.List` (erasure of generic types like `List<String>`) |

**A descriptor is not the Java display type name.** For example, the field `long balance` has descriptor `J`, not the string `long`. In `javap -v`, you can see lines like `Fieldref ... // Field org/example/Account.balance:J`.

## 7. Resolution, Field Kind Checks, and Access Checks

A JVM must determine the actual field from the symbolic reference through **field resolution** (JVMS `5.4.3.2), following the rules for searching the field in the class/interface hierarchy, checking class loading, and verifying accessibility. Resolution may be performed eagerly or lazily on demand, within the bounds permitted by the JVMS.

Distinguish three steps:

1. **Symbolic reference:** owner name, field name, and descriptor already present in the constant pool.
2. **Resolution:** the JVM locates the actual field and performs linking/permission checks according to the rules.
3. **Instruction execution:** checks static/instance kind, `final` conditions, and objectref when needed, then reads/writes the value.

**Do not equate `Fieldref` with a physical address/offset.** A JVM implementation may cache resolution results or optimize access paths at runtime, but the standardized binary representation remains a symbolic reference.

### Fields with the Same Name but Different Kind/Descriptor

A class may expose different members across binary versions. A caller compiled against the field `score:I` will look for a field matching both **name and descriptor**, not merely a member with the same name. When runtime provides a class version where the field was removed or its descriptor changed from `I` to `J`, linking can fail with `NoSuchFieldError`. Changing a field from instance to static (or vice versa) can also make existing instructions incompatible with the field kind, causing `IncompatibleClassChangeError`.

### Field Hiding Is Not Dynamic Dispatch

In Java, **field access is bound by the reference type at compile time**, unlike virtual method dispatch. Consider:

~~~java
class Parent {
    int number = 1;
}

class Child extends Parent {
    int number = 2;
}
~~~

If we have:

~~~java
Parent p = new Child();
System.out.println(p.number);          // 1
System.out.println(((Child) p).number); // 2
~~~

This is an illustrative snippet that needs to be placed inside a method to run. `p.number` was compiled to access `Parent`'s field; casting to `Child` allows the source code to point to `Child`'s distinct field. The JVM **does not automatically look up a "field override" based on the object's runtime class** when executing `getfield`, because fields can be *hidden*, not *overridden*. Instance methods are where virtual dispatch normally occurs via the appropriate invocation opcodes.

### Access Permissions Are Checked at Runtime

Being able to compile in one configuration does not mean binaries will always link after replacing a JAR, module, or class loader. Common cases:
- Field no longer exists: `NoSuchFieldError`.
- Field exists but access is not permitted: `IllegalAccessError`.
- Static/instance mismatch: `IncompatibleClassChangeError`.
- Owner class cannot be loaded/defined as required: may encounter `NoClassDefFoundError` or related linking errors.

These errors belong to the **`LinkageError`** family, unlike the null check exception during the execution step of `getfield`/`putfield`.

## 8. Null Access: Why Only Instance Fields Require an Object?

If `objectref` is `null` when executing **`getfield` or `putfield`** after the relevant linking checks, the JVM throws `NullPointerException`.

Complete Java 17+ example:

Create **`NullFieldDemo.java`**:

~~~java
public class NullFieldDemo {
    int value = 5;
    static int shared = 9;

    public static void main(String[] args) {
        NullFieldDemo item = null;

        try {
            System.out.println(item.value);
        } catch (NullPointerException expected) {
            System.out.println("instance=NPE");
        }

        System.out.println("static=" + NullFieldDemo.shared);
    }
}
~~~

Run:

~~~bash
javac --release 17 NullFieldDemo.java
java NullFieldDemo
~~~

**Exact stdout:**

~~~text
instance=NPE
static=9
~~~

`item.value` requires an objectref and fails because of the null reference. `NullFieldDemo.shared` uses `getstatic`, needing no instance.

Java allows writing static field syntax through a reference expression such as `item.shared` (the compiler may warn about style), even when `item` is null. However, **the expression before the dot may still be evaluated and cause its own side effects or exceptions**; therefore, you should not write static access through an object variable. Use `ClassName.field` to make the meaning clear and avoid confusion with `getfield`.

### Order of Errors and Exceptions

In cases where bytecode has both a linking error and a null objectref simultaneously, do not build logic based on the assumption that "NPE is definitely thrown first." The JVM must follow the specified resolution/checking order; linking errors may occur before the objectref check step. This is especially important when analyzing generated class files or binary compatibility errors.

## 9. `final`, Compile-Time Constants, and Field Write Exceptions

### `final` Rules at the Bytecode Level

With modern Java class file formats, the verifier/linker restricts writes to `final` fields:

- **`putfield` to an instance `final` field**: the field must be declared in the **current class**, and the instruction must be inside an **instance initialization method `<init>`** of that same class; otherwise, `IllegalAccessError` may occur when the relevant checks are executed.
- **`putstatic` to a static `final` field**: the field must be declared in the **current class/interface**, and the instruction must be inside the **class/interface initialization method `<clinit>`**.
- `getfield`/`getstatic` can read final fields from permitted locations if resolution/access succeeds.

These bytecode rules explain why the Java compiler only allows assigning `final` in valid initialization contexts, but **they do not replace all JLS rules** regarding definite assignment, blank finals, and the validity of constructors/source code.

### Reading `static final` Is Not Always `getstatic`

A **constant variable** in Java is a `final` field of primitive or `String` type initialized with an appropriate *constant expression*. Its value can be **inlined directly at the use site** by the compiler, so code using that field may **not contain `getstatic`** for the field.

Complete example:

Create **`ConstantFieldDemo.java`**:

~~~java
class ConfigData {
    static final int LIMIT = 7; // Compile-time constant variable

    static int dynamic = start();

    private static int start() {
        System.out.println("ConfigData initialized");
        return 21;
    }
}

public class ConstantFieldDemo {
    public static void main(String[] args) {
        System.out.println("limit=" + ConfigData.LIMIT);
        System.out.println("before dynamic");
        System.out.println("dynamic=" + ConfigData.dynamic);
    }
}
~~~

Run:

~~~bash
javac --release 17 ConstantFieldDemo.java
java ConstantFieldDemo
~~~

**Exact stdout:**

~~~text
limit=7
before dynamic
ConfigData initialized
dynamic=21
~~~

Explanation:

1. `ConfigData.LIMIT` is a compile-time constant; the compiler can place the number 7 directly into the caller class. Therefore, this read does not need `getstatic` and does not trigger initialization of `ConfigData` in the way an actual `getstatic` does.
2. `ConfigData.dynamic` is not a compile-time constant because its value comes from calling `start()`. When bytecode executes `getstatic` to read it, the JVM must initialize `ConfigData` first.
3. The body of `<clinit>` runs `start()` and prints `ConfigData initialized`, then stores the value 21 using `putstatic`.
4. After initialization, `getstatic` returns 21.

**Important point about binary compatibility:** If a library changes the value of a compile-time constant `static final int LIMIT` and users **do not recompile the caller**, the caller may continue using the inlined value from the old version. That is one reason not to use primitive/string compile-time constants to publish configurations that need to change at runtime across releases.

### A Final Field Does Not Mean an Immutable Object

`final Account account` prevents reassigning the field reference after valid initialization, but **does not make all fields inside the Account object immutable**. Nor is there any automatic thread-safety guarantee for operations on the referenced object.

## 10. `volatile`, the Java Memory Model, and Atomicity

Fields marked `volatile` are still accessed via the **same opcodes**: `getfield`/`putfield` if instance, `getstatic`/`putstatic` if static. There is no separate "`getvolatile`" or "`putvolatile`" opcode set in the standard JVM.

Example:

~~~java
class Flag {
    volatile boolean ready;
    static volatile int version;
}
~~~

This is an illustrative class. The bytecode uses `getfield`/`putfield` for `ready` and `getstatic`/`putstatic` for `version`; **field metadata** contains the `ACC_VOLATILE` flag so the JVM enforces the Java Memory Model (JMM) rules.

- **Volatile read** has visibility and ordering semantics; **volatile write** also has corresponding semantics, including a *happens-before* relationship of a write with subsequent reads of the same field under the JMM.
- Individual volatile read/write operations have atomicity guarantees for the field type under the JMM; for example, reads/writes of `volatile long` and `volatile double` are atomic under Java rules.
- **`volatile int counter; counter++;` is not atomic** as a read-modify-write operation. It consists of a read, a computation, and a write; two threads can still lose updates.
- If atomic incrementing is needed, use synchronization, `AtomicInteger.incrementAndGet()`, or an appropriate concurrency utility. Calling these APIs does not create new field access opcodes, although the JIT may use efficient intrinsics/CPU instructions.

**JMM semantics differ from physical storage.** From the `getfield` bytecode alone, one cannot conclude whether a field is volatile; one must inspect the field declaration/flags in the class file. With `javap -v -p`, the field declaration section can display `ACC_VOLATILE`.

## 11. Compound Assignment and Expression Results

Assignments such as `obj.x += 3`, `obj.x++`, or `staticCount *= 2` **do not have a separate "fieldAdd" opcode**. The compiler coordinates:
1. Computing the receiver/objectref if it is an instance field.
2. Reading the old value with `getfield` or `getstatic`.
3. Computing with opcodes such as `iadd`, `imul`; converting if necessary.
4. Writing back with `putfield` or `putstatic`.
5. If the assignment expression has a used value, stack-duplicating opcodes such as `dup`, `dup_x1`, `dup2_x1`, `dup2_x2` may be needed to retain the appropriate value.

Example:

~~~java
int result = (obj.count += 3);
~~~

This is a snippet inside a method where `obj` is an appropriate instance. `result` needs to receive **the new value of the assignment expression**; whereas `putfield` itself pushes nothing. The compiler must preserve Java expression semantics by arranging the stack before and after the write instruction.

Similarly, `obj.count++` (post-increment) returns **the old value** as the expression result, while `++obj.count` returns **the new value**. They can use the same `getfield`/`putfield` instructions but arrange the stack differently to preserve the right result.

## 12. Relationship Between Class Initialization and Constructors

Two kinds of initializers commonly seen when reading disassembly:

| Component | JVM Symbol | When It Runs | Common Field Access Instructions |
| --- | --- | --- | --- |
| Constructor | `<init>` | When creating and initializing an instance per Java rules | `putfield` for instance field initializers / constructor assignments |
| Class/interface initializer | `<clinit>` | When a class/interface needs initialization for the first time per rules | `putstatic` for static field initializers / static blocks |

Distinguish carefully:
- `new Counter()` requires the class to be appropriately initialized, creates a new object, and then runs the constructor; `<init>` itself is the instance initializer in JVM terminology.
- `<clinit>` is the special method of a class/interface invoked by the JVM for initialization; users do not call it directly from Java source like a normal method.
- `getstatic`/`putstatic` on a resolved field is an initialization trigger if the declaring class/interface has not yet been initialized, whereas `getfield`/`putfield` does not have a similar initialization trigger mechanism **merely for reading/writing an instance field**. Normally, a valid object has already gone through the appropriate initialization sequence when created.

Do not explain that "`putfield` initializes the class on the first write": this is a common confusion between **instance constructors** and **class initialization**.

## 13. JVM Errors Related to the Four Opcodes

| Situation | Common Error/Exception | Correct Understanding |
| --- | --- | --- |
| `getfield`/`putfield` with `objectref = null` | `NullPointerException` | No instance to read/write; belongs to the execution step, after relevant linking checks. |
| Referencing a field that no longer exists by name and descriptor | `NoSuchFieldError` | Runtime class does not match the binary the caller expected. |
| Trying to use `getfield`/`putfield` for a static field or `getstatic`/`putstatic` for an instance field | `IncompatibleClassChangeError` | Opcode is incompatible with the resolved field kind. |
| Bytecode accesses a field that is no longer permitted | `IllegalAccessError` | Runtime access rules or `final` rules were violated. |
| Owner class cannot be loaded | `NoClassDefFoundError` or appropriate loading/linking error | Check the cause and class loader, classpath/module path. |
| Static initialization throws an exception | `ExceptionInInitializerError` or related error | Check the stack trace and root cause of `<clinit>`. |
| Generated class file has invalid stack/types | `VerifyError`/`ClassFormatError` | Invalid bytecode; need to inspect the verifier and class format. |

When debugging, read the **full exception chain**, the class, and the descriptor that the runtime expects. For example, a library version changes `static int total` to `int total` while the caller is not recompiled: the old bytecode still uses `getstatic`, so it cannot "reinterpret itself" as `getfield` just because the field name matches.

### Do Not Use Reflection to Guess Opcodes Directly

When writing `Field.get(target)` or `Field.set(target, value)`, the bytecode at the call site is a **reflection API call**. The JVM/reflection implementation may use different internal mechanisms, but the caller's code does not naturally emit a `getfield` opcode pointing directly to the target field. Similarly, APIs such as `VarHandle.get` and `VarHandle.set` express flexible access modes; they are not names of new instructions replacing the four opcodes above.

## 14. `javap` Reading Checklist

When disassembling a class yourself with `javap -c -v -p`, check in order:

1. **Current class and method:** does it belong to an instance method, constructor `<init>`, static method, or `<clinit>`?
2. **Index operand:** which `#N` does the `getfield/putfield/getstatic/putstatic` instruction contain?
3. **Constant pool:** which `CONSTANT_Fieldref` does `#N` point to? What are the owner class, field name, and descriptor?
4. **Field kind:** does the field have the `ACC_STATIC` flag? If `ACC_FINAL`, is the write instruction in a valid location?
5. **Stack:** instance read requires `objectref`; instance write requires `objectref` below `value`; static read/write does not require objectref.
6. **Surrounding instructions:** loads, constants, arithmetic, `dup`, `invoke*`, stores show whether this is an assignment, compound assignment, or access within an expression.
7. **Class initialization:** for `getstatic/putstatic`, does the class/interface declaring the field need initialization at that point?
8. **Concurrency:** does the field have `ACC_VOLATILE`? Is there a read-modify-write needing greater atomicity than individual accesses?
9. **Unstable index numbers:** do not assign fixed meanings to `#N` across compilations; read the actual file being inspected.

### Some Common Source Expressions

| Java Expression | Common Related Bytecode | Notes |
| --- | --- | --- |
| `obj.x` | `aload` + `getfield` | Receiver obtained from expression. |
| `obj.x = 42` | `aload` + push 42 + `putfield` | Stack order: receiver, then value. |
| `Holder.x` if `x` is a regular static | `getstatic` | May trigger class initialization. |
| `Holder.x = 42` if `x` is a regular static | push 42 + `putstatic` | May trigger class initialization. |
| `obj.x++` | `getfield`, arithmetic, `putfield`, stack duplication if needed | Not guaranteed atomic. |
| `staticCounter += 2` | `getstatic`, arithmetic, `putstatic` | Not guaranteed atomic. |
| `Holder.CONSTANT` if compile-time constant | Constant-loading instruction (not necessarily `getstatic`) | Can be inlined. |
| `array.length` | `arraylength` | Not an instance field opcode. |
| `obj.getX()` | `invokevirtual` / appropriate invoke instruction | Method call, not a direct getfield at the caller. |

## 15. Self-Check and Answers

**Question 1.** What is the fundamental difference between `getfield` and `getstatic`?

**Answer:** `getfield` reads a value from **an instance** and requires objectref on the stack; `getstatic` reads a field **of the resolved class/interface** and does not require objectref. `getstatic` can trigger initialization of the class/interface declaring the field.

**Question 2.** Before `putfield`, what must the operand stack contain and in what order?

**Answer:** `..., objectref, value` from bottom to top. The new value is on top, objectref is below. The instruction pops both.

**Question 3.** Is there an `iincfield` opcode to increment `obj.count++`?

**Answer:** No. The compiler typically combines `getfield`, arithmetic instructions, and `putfield`; `iinc` is for int local variables, not fields.

**Question 4.** Must `getstatic` always appear when reading `static final int LIMIT = 7`?

**Answer:** No. If it is a compile-time constant variable and the caller is compiled with that value, the compiler can inline 7 and not emit `getstatic` for the field at the call site.

**Question 5.** Are instance fields `int number` with the same name in Parent and Child overriding or hiding?

**Answer:** **Hiding**. Fields are selected according to compile-time binding rules and symbolic references, not virtual dispatch like instance methods.

**Question 6.** What does `getfield` with a null objectref cause? Does `getstatic` need an objectref?

**Answer:** After appropriate linking checks, `getfield` on null throws `NullPointerException`. `getstatic` has no objectref operand.

**Question 7.** If a caller was compiled to access `static int total` but at runtime it is changed to `int total`, what will happen?

**Answer:** The old bytecode uses `getstatic/putstatic` on a field that is now an instance field; during resolution and execution per JVM checks, `IncompatibleClassChangeError` may be encountered. The binary incompatibility must be resolved and compiled/deployed consistently.

**Question 8.** Is incrementing a `volatile int counter` field with `counter++` atomic?

**Answer:** No. Volatile reads and volatile writes have visibility/ordering rules, but the read-modify-write sequence does not automatically become atomic. `AtomicInteger` or synchronization can be used.

**Question 9.** Is it valid for `putstatic` to write a `static final` field at an arbitrary time after initialization?

**Answer:** No. Valid bytecode must obey JVMS rules: the `final` field belongs to the current class/interface, and the `putstatic` instruction must be inside the `<clinit>` initializer of that class/interface.

**Question 10.** Why is the index `#18` after `getfield` not an "18-byte offset" in the object?

**Answer:** Because that operand is an index of a `CONSTANT_Fieldref` in the run-time constant pool. The JVM resolves the symbol to the appropriate field; physical layout is a runtime implementation detail.

## 16. Memory Map

~~~text
                          FIELD ACCESS
                               |
                    +----------+----------+
                    |                     |
                 INSTANCE                STATIC
            requires objectref      no objectref needed
                    |                     |
            +-------+-------+     +-------+-------+
            |               |     |               |
          READ            WRITE  READ            WRITE
        getfield         putfield getstatic       putstatic

Stack:
  getfield : ..., ref        -> ..., value
  putfield : ..., ref, value -> ...
  getstatic: ...             -> ..., value
  putstatic: ..., value      -> ...

Each instruction -> #N CONSTANT_Fieldref -> Class + NameAndType
                 -> owner class, field name, field descriptor
                 -> resolution + access/field-kind checks

Static access (getstatic/putstatic)
                 -> may trigger class/interface initialization
Instance access (getfield/putfield)
                 -> requires non-null objectref

final       -> writes restricted to <init>/<clinit> by field kind
volatile    -> adds memory-order/visibility; does not make ++ atomic
~~~

**Key takeaway:** All four opcodes access fields via a **symbolic reference** from the constant pool, but they differ in **instance/static**, **read/write**, **operand stack shape**, and **runtime conditions**. Reading disassembly correctly requires matching the opcode with the descriptor, flags, class initialization, and Java Memory Model rules.

## References

- [JVMS Java SE 21 — 6.5 Instructions: getfield, putfield, getstatic, putstatic](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5).
- [JVMS Java SE 21 — 4.4.2 Fieldref, Methodref, and InterfaceMethodref](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.2).
- [JVMS Java SE 21 — 5.4.3.2 Field Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.2).
- [JVMS Java SE 21 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5).
- [JLS Java SE 21 — 12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4).
- [JLS Java SE 21 — 17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4).
- [JDK 21 — javap tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).