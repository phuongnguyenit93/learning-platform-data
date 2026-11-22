# Primitive Types and Reference Types in the JVM Execution Model

In Java, a variable can hold a **primitive value** or a **reference value**. The JVM needs to know the value kind to select bytecode instructions, represent data in local variables and the operand stack, verify the correctness of operations, and manage objects. This distinction explains why assigning an `int` variable copies the number, whereas assigning a variable holding a reference to an object can cause both variables to observe changes on that object.

The content focuses on the **execution model**, so three commonly confused concepts must be separated:

1. **Java language types**: the compiler checks declarations such as `int`, `boolean`, `String`, `int[]`, classes, interfaces, generics...
2. **JVM types and instructions**: the class file uses type descriptors, instruction sets such as `iload`/`aload`, the operand stack, local-variable slots, and the bytecode verifier to execute.
3. **Objects in memory**: a reference is used to access an object/array; the GC and runtime manage the memory lifecycle according to the JVM implementation. Bit layout or physical location cannot be inferred from a Java declaration alone.

## 1. Two Type Families at the Java Language Level

| Group | Representative types/values | Behavior on assignment |
| --- | --- | --- |
| **Primitive** | `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double` | Assignment copies the primitive **value** |
| **Reference** | Variables of class (`String`, `Object`), interface, array (`int[]`), type variable, and other reference types | Assignment copies the **reference value**, which may point to the same object/array |
| **`null`** | Special value usable with compatible reference types | Indicates **referring to no object**; cannot be assigned directly to a primitive variable |

The eight primitives above are **Java types**, not eight independent instruction kinds in the JVM. `String` is a class and a `String` variable is a reference, even though the literal syntax `"hello"` looks simple. A primitive array `int[]` **is still an array object**, so an `int[]` variable is a reference variable; only its **elements** have type `int`.

**Easily confused cases:**

- `int number = 10;`: `number` holds an integer value; assigning `int copy = number;` produces an independent copy of the value.
- `Person p = new Person();`: `p` holds a reference value to an object, not the entire object placed “inside the variable”.
- `Person q = p;`: copies the **reference**; `p` and `q` can point to the same object. This is **still pass/copy by value**, not “Java variables are passed by reference”.
- `Person absent = null;`: a variable with a reference type that currently does not point to any object.
- `int[] data = {1, 2};`: `data` is a reference, while the two elements are `int` values stored in the array object.

## 2. Primitives: Meaning and Value Ranges

| Java type | Meaning and value size per specification | Notes |
| --- | --- | --- |
| `boolean` | Two values `false` and `true` | Java does not allow direct conversion back and forth with `int`; does not default to “true is the number 1” in source programs |
| `byte` | Signed integer, 8-bit (`-128` to `127`) | Arithmetic operations are usually **promoted to `int`** |
| `short` | Signed integer, 16-bit (`-32768` to `32767`) | The operation `short + short` returns `int` |
| `char` | **UTF-16** code unit, unsigned, 16-bit (`0` to `65535`) | A single `char` does not necessarily represent an entire Unicode character outside the BMP |
| `int` | Signed integer, 32-bit | Integer overflow is handled according to Java rules, without automatically becoming a wider type |
| `long` | Signed integer, 64-bit | Literals usually use the `L` suffix such as `12L` |
| `float` | IEEE 754 binary32 floating-point number | Has rounding error, special values NaN and infinity |
| `double` | IEEE 754 binary64 floating-point number | Has rounding error; default for floating-point literals such as `1.5` |

These sizes describe **width and value range according to the language**, which does not mean every variable always occupies that exact number of bytes everywhere in machine memory. How the JVM lays out objects, aligns fields, optimizes variables, or allocates CPU registers depends on the implementation.

Example of an operation on a narrow type:

```java
byte a = 3;
byte b = 4;
int sum = a + b; // The result of the expression a + b has type int
```

The line `byte sum = a + b;` is invalid without a cast because addition undergoes **binary numeric promotion** to `int`. Conversely, `byte x = 3 + 4;` can be accepted by `javac` due to the assignment rule for **compile-time constant integer expressions** within the `byte` range. The two situations are two different language rules.

## 3. How Does the JVM Represent Types When Executing Bytecode?

In the JVM Specification, JVM values are generally divided into numeric and reference groups. Numeric includes `byte`, `short`, `int`, `long`, `char`, `float`, `double`; `boolean` does not have an independent arithmetic instruction set like `int`. The JVM supports `boolean` to a limited extent, usually using `int`-related representations and instructions when Java `boolean` code is compiled.

Two **category** kinds are very important when inspecting bytecode:

| JVM value | Category on operand stack | Number of local-variable slots |
| --- | ---: | ---: |
| `int`, `float`, `reference`, and narrow integral values when operated on as `int` | 1 | 1 |
| `long`, `double` | 2 | 2 |
| `returnAddress` from the historical `jsr`/`ret` mechanism | 1 | 1 |

**Category 1/2 is a size convention in the JVM model**, which does not mean every physical reference has the same width as `int`. Implementations such as HotSpot can have different reference representations and memory optimizations; machine addresses and compressed references techniques are implementation details.

At the bytecode level, `byte`, `short`, and `char` are usually pushed onto the operand stack and processed as **`int`**. For example, adding two `byte` values can use `iadd` after loading the values onto the stack; when needing to store back into a narrow type, the compiler can use conversion instructions such as `i2b`, `i2s`, or `i2c`. Array load/store instructions still distinguish the appropriate element type, for example `baload`, `saload`, `caload`.

**Regarding `boolean`:** conditional Java code usually uses `iconst_0`/`iconst_1` together with `if*`-style branch instructions; the JVM defines how to support `boolean` and `boolean[]` arrays rather than guaranteeing a separate `boolean` arithmetic bytecode. One must not infer from this that Java allows `if (1)` or addition between `boolean` values: **the Java compiler rejects those expressions**.

**`returnAddress`** is a special value kind tied to the `jsr`/`ret` instructions of older class files, not a type that normal Java code can declare, and should not be used in modern Java code. `void` is a “no return value” result type, not a value placed on the operand stack.

## 4. How Do Local Variables, the Operand Stack, and Objects Differ?

A Java method running in the JVM has its own **stack frame** for each invocation. A frame contains:

- **Local variable array**: slots accessed by index for parameters and local variables; a category 2 value occupies two consecutive slots in the model.
- **Operand stack**: where bytecode pushes, pops, and combines intermediate values when performing computations, calling methods, and conditional branching.
- **Auxiliary information** for returning/controlling the call flow and related runtime references.

Conceptual example for a static method:

```java
static int add(int left, int right) {
    return left + right;
}
```

The bytecode produced by `javac` usually represents the addition with equivalent instructions:

```text
iload_0     // push int value from local slot 0
iload_1     // push int value from local slot 1
iadd        // pop two ints from operand stack, push int result
ireturn     // pop int value from stack to return
```

This is a **bytecode illustration**, not a standalone program to compile; the exact order and opcode selection should be checked using `javap -c` on an actual class file.

For an instance method, local slot `0` usually holds the `this` reference; parameters appear in subsequent slots. For a `static` method, there is no automatic `this`. A `long` or `double` parameter uses **two slots**, so the index of the next parameter may skip a position.

**Do not treat “primitives are always on the stack, objects are always on the heap” as an absolute rule.** A local variable can hold a primitive value or a reference; a field inside an object can have a primitive or reference type; an array can hold primitive elements or references. At the JVM model level, objects and arrays are heap entities; however, modern optimizing JVMs can eliminate allocations or represent data differently while preserving observable behavior.

```text
main() stack frame (logical model)          Heap (logical model)
┌───────────────────────────────┐           ┌──────────────────────┐
│ int count = 7                 │           │ Item instance        │
│ Item first ───────────────────┼──────────►│ int value = 9        │
│ Item alias ───────────────────┼──────────►│ boolean active=false │
│                               │           │ String label=null    │
└───────────────────────────────┘           └──────────────────────┘

first and alias hold two COPIES of the reference value,
but both access the SAME Item object.
```

The diagram only explains the observable relationship, not a claim that the JVM always places each variable in a separate physical RAM cell or that a reference has a fixed machine pointer shape.

## 5. Runnable Java 17+ Example: Copying Values and Sharing Objects

Create the file **`JvmValueKinds.java`** in an empty directory:

```java
public class JvmValueKinds {
    static class Item {
        int value;
        boolean active;
        String label;
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        int original = 7;
        int copied = original;
        copied = 10;

        Item first = new Item();
        first.value = 7;
        Item alias = first;

        Item another = new Item();
        another.value = 7;
        alias.value = 10;

        Item fresh = new Item();

        byte left = 3;
        byte right = 4;
        int promotedSum = add(left, right);

        int[] numbers = {1, 2};
        int[] shared = numbers;
        shared[0] = 99;

        Integer boxed = 42;
        int unboxed = boxed;

        System.out.println("primitive: original=" + original
                + ", copied=" + copied);
        System.out.println("reference: first.value=" + first.value);
        System.out.println("same object: " + (first == alias));
        System.out.println("different objects: " + (first == another));
        System.out.println("defaults: " + fresh.value
                + ", " + fresh.active + ", " + fresh.label);
        System.out.println("byte + byte -> int: " + promotedSum);
        System.out.println("array alias: " + numbers[0]);
        System.out.println("boxed/unboxed: " + unboxed);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 JvmValueKinds.java
java JvmValueKinds
```

**Exact standard output:**

```text
primitive: original=7, copied=10
reference: first.value=10
same object: true
different objects: false
defaults: 0, false, null
byte + byte -> int: 7
array alias: 99
boxed/unboxed: 42
```

Explanation of each observation:

1. **Primitive:** `copied = original` creates a copy of the value `7`. Setting `copied = 10` does not change `original`.
2. **Reference:** `alias = first` copies the reference value to the same `Item`. `alias.value = 10` modifies the **object's field**, so `first.value` also reads `10`.
3. **Identity:** `first == alias` is `true` because both references point to the same object; `first == another` is `false` because two `new Item()` calls create two separate objects, even though the `value` field previously had the same value `7`.
4. **Default values:** explicitly unassigned instance fields `int`, `boolean`, `String` have `0`, `false`, `null` respectively. This rule **does not apply to local variables** that have not been assigned before being read: the compiler requires local variables to be definitely initialized.
5. **Numeric promotion:** `left` and `right` are `byte`; they are converted according to the `add(int, int)` call, producing the `int` result `7`. The addition inside `add` is `int` addition.
6. **Array reference:** `shared = numbers` copies the reference, so modifying `shared[0]` changes the element observed through `numbers[0]`.
7. **Boxing:** `Integer boxed = 42` performs autoboxing; `int unboxed = boxed` performs unboxing. `Integer` is an object reference type; `int` is a primitive. The compiler may use calls such as `Integer.valueOf` and `Integer.intValue`.

Note in the example, the assignment `alias = first` **does not create a new `Item`**; only `new Item()` requires creating an object according to program semantics.

### Inspecting the Bytecode Yourself

```bash
javap -c JvmValueKinds
javap -c -p JvmValueKinds
javap -verbose JvmValueKinds
```

- `javap -c` prints the bytecode of ordinary public methods; `-p` allows viewing non-public members as well.
- In `add(int, int)`, observe `iload`, `iadd`, `ireturn`. Those are **`int`** instructions, even though the inputs `left` and `right` in `main` have type `byte`.
- For `new Item()`, the compiler usually generates the group `new`, `dup`, `invokespecial` to allocate the object and invoke the constructor. Accessing `value` uses `getfield`/`putfield`.
- For `new int[]` or an array initializer, observe array-related instructions such as `newarray`, `iastore`, `iaload`.
- Instructions for printing strings may use `invokedynamic` for string concatenation on modern JDKs; constant pool index details and offsets depend on the compiler version.

**Do not confuse `javap` bytecode with CPU machine code.** When the JVM executes, the interpreter or JIT processes the bytecode appropriately for the current platform.

## 6. What Do Descriptors in a Class File Say About Types?

A JVM class file uses **type descriptors** to record field types and method signatures at the bytecode level. Primitive notations:

| Java type | Notation in field descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `short` | `S` |
| `char` | `C` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |

A reference to a class usually has the form **`Lname/package/Class;`**. Array types have the prefix **`[`**; multiple `[` characters indicate multiple dimensions. `V` means `void` **in the return type part of a method descriptor**, not a field type.

| Java declaration | JVM descriptor |
| --- | --- |
| `int number` | `I` |
| `String text` | `Ljava/lang/String;` |
| `int[] values` | `[I` |
| `String[][] names` | `[[Ljava/lang/String;` |
| `static int add(int a, int b)` | `(II)I` |
| `void use(String[] args)` | `([Ljava/lang/String;)V` |

A method descriptor has the structure **`(parameter-descriptors)return-descriptor`**. The slashes in `java/lang/String` are the internal name of the class file, different from the Java name notation `java.lang.String`.

Generics such as `List<String>` have corresponding declaration/metadata information when saved by the compiler, but the basic descriptor part operates on types after **erasure**; do not expect bytecode to always preserve every generic parameter from the source language. Inspect `javap -verbose` to observe the descriptor and, when present, the `Signature` attribute.

## 7. Bytecode Selects Instructions by Value Kind

JVM opcodes usually have a prefix indicating the type group:

| Operation group | For `int` | For `long` | For `float`/`double` | For reference |
| --- | --- | --- | --- | --- |
| Load local variable | `iload` | `lload` | `fload`/`dload` | `aload` |
| Store local variable | `istore` | `lstore` | `fstore`/`dstore` | `astore` |
| Return value | `ireturn` | `lreturn` | `freturn`/`dreturn` | `areturn` |
| Numeric addition | `iadd` | `ladd` | `fadd`/`dadd` | No instruction to add two references |

Additions with `byte`, `short`, `char` are usually handled in the `int` domain according to numeric promotion. `boolean` is also not treated as a Java language integer to use `iadd` in valid Java code.

Some reference-specific instructions:

- `new`: creates an instance of a class.
- `getfield`/`putfield`: reads/writes an instance field; `getstatic`/`putstatic` serve static fields.
- `invokevirtual`, `invokeinterface`, `invokespecial`, `invokestatic`: method invocation mechanisms; not simply “jumping to a pointer”.
- `checkcast` and `instanceof`: check appropriate reference type relationships at runtime.
- `ifnull`/`ifnonnull`, `if_acmpeq`/`if_acmpne`: branches related to null or comparing reference identity.
- `aaload`/`aastore`: reads/writes an element of a reference array, as opposed to `iaload`/`iastore` for `int[]`.

The **bytecode verifier** uses value kinds and the state of local variables/operand stack to reject bytecode that does not satisfy type and structural rules. For example, it cannot be valid to push a reference and then use `iadd` as with `int`. The verifier also tracks uninitialized object states and control-flow constraints; the fact that Java source compiles does not allow a bytecode tool to freely generate ill-typed code.

## 8. A Reference Is Not the Object Itself

Distinguish the three operations below:

```java
Item a = new Item(); // create new object, a holds reference
Item b = a;          // copy reference: same object
b = new Item();      // b receives new reference, a still points to old object
```

The two variables `a` and `b` are two separate **locations storing reference values** according to the variable model. When only assigning `b = a`, the object is not copied; when reassigning `b = new Item()`, the aliasing relationship is changed without modifying `a`.

When calling a method:

```java
static void replace(Item parameter) {
    parameter = new Item();
}

static void mutate(Item parameter) {
    parameter.value = 99;
}
```

Both snippets above are **illustrative helper methods** and need to be inside a class with a compatible `Item` declaration to compile; they do not form a standalone runnable program.

- `replace(a)` only changes **the copy of the reference value in `parameter`**, without switching `a` to the new object.
- `mutate(a)` modifies **the field of the object that `parameter` and `a` both reference**, so the caller can observe `a.value == 99`.

Therefore, Java **always passes arguments by value**: for primitives it is a copy of the primitive value, for references it is a copy of the reference value. The phrase “Java passes objects by reference” easily leads learners to wrongly conclude that a caller's reference variable can be reassigned from a parameter.

### `==`, `equals`, and Wrappers

For numeric primitives, `==` compares values according to Java's numeric conversion rules; for two references, `==` checks **same identity or both null**. Comparing the **business-meaningful content** of two objects requires an appropriate method such as `equals` if the class provides that comparison contract.

Example:

```java
String left = new String("abc");
String right = new String("abc");
System.out.println(left == right);      // false (two new objects)
System.out.println(left.equals(right)); // true  (equal content)
```

This is an **illustrative snippet placed inside `main`**, not a complete class. Do not use `==` to compare `String` content: string literals can be interned and thus give matching identity results in some situations, masking bugs.

Autoboxing turns a primitive into a wrapper reference value such as `Integer`; unboxing extracts the primitive value from the wrapper. If the wrapper variable is `null`, **unboxing throws `NullPointerException`**. Do not rely on `==` between two wrappers to compare values because **identity/caching** can produce counterintuitive results; use `equals` or unbox safely when wanting to compare content.

## 9. Fields, Local Variables, Arrays: Same Types, Different Initialization Rules

| Location | Value before explicit assignment | Notes |
| --- | --- | --- |
| Instance field / static field | Has a default value such as `0`, `false`, `null` | Initialized according to JVM rules; constructor/static initialization can assign further |
| New array element | Has the default value of the element type | For example, `new int[2]` contains `0, 0`; `new String[2]` contains `null, null` |
| Local variable in a Java method | **Cannot be read before being definitely assigned** | `javac`'s **definite assignment** rule; not considered to have default `0`/`null` |

Example:

```java
int[] numbers = new int[2];       // numbers references array; elements are int
String[] names = new String[2];  // names references array; elements are references
System.out.println(numbers[0]); // 0
System.out.println(names[0]);   // null
```

The snippet above is valid when placed inside a `main` or appropriate method. Both `numbers` and `names` in the example are assigned by `new` before use.

For reference arrays, the JVM also checks element type compatibility at runtime (because Java arrays are **covariant**):

```java
Object[] values = new String[1];
values[0] = "ok";            // valid
// values[0] = new Object(); // if uncommented: ArrayStoreException at runtime
```

An array's type check is different from copying a reference and different from a compilation error. `int[]` cannot be directly converted to `Object[]`; even though both are array objects in the Java object sense, `int[]` has primitive elements.

## 10. `null`, Object Access, and Garbage Collection

`null` is a **special reference value** with no corresponding object. Accessing an instance field or invoking an instance method through a `null` reference usually leads to `NullPointerException` at runtime:

```java
String text = null;
// System.out.println(text.length()); // if uncommented: NullPointerException
System.out.println(text == null); // true
```

`null` is not `0` and cannot be assigned to `int`. The `instanceof` operator when the operand is `null` evaluates to `false`, but that does not mean all other operations with `null` are safe.

**Reachability** helps the GC determine whether an object can still be used by the program from the reference roots considered by the collector. When there are no longer any relevant reference paths to an object, the object may become **eligible for collection**, but **there is no guarantee it will be collected immediately**. Assigning `reference = null` is not equivalent to “deleting the object from the heap” at that instant, and one cannot rely on `System.gc()` to guarantee reclamation timing.

There is no pointer arithmetic on references in Java source like in C/C++; the specification also does not allow assuming a reference representation has a fixed number of bytes to add/subtract addresses.

## 11. Common Misconceptions When Learning JVM Types

| Easily mistaken claim | Correct understanding |
| --- | --- |
| “Primitives are always on the stack; references are always on the heap.” | Variables/fields/arrays can store primitives or references; **objects** are heap entities in the model, while physical placement can be optimized by the JVM |
| “Object assignment `b = a` is a deep copy of the object.” | Assignment copies the **reference value**; two variables can share the same object |
| “Class parameters are passed by reference.” | Java is **pass by value**, even for references to objects |
| “`long` occupying two slots means references are always 4 bytes.” | Categories and slots are the **JVM model**, not a way to deduce physical pointer size |
| “There are 8 Java primitives so the JVM must have 8 different addition opcodes.” | The JVM uses `int` for many operations on narrow types; `boolean` has no Java addition |
| “An array is always a reference to an array of objects.” | An array is an object; its **element type** can be primitive (`int[]`) or reference (`String[]`) |
| “Unassigned fields and local variables are both `0`.” | Fields/array elements have defaults; Java local variables must be definitely assigned before reading |
| “`Integer` is identical to `int`.” | `Integer` is a reference wrapper, can be `null`, and has identity; unboxing can fail |
| “`==` always compares object content.” | For references, `==` compares identity; `equals` can compare content depending on the class contract |

## 12. Self-Check on the Execution Model

**Question 1.** In `int[] a = new int[3];`, is `a` a primitive or a reference?  
**Answer:** `a` has a **reference** type, pointing to an array object. Each element `a[i]` holds a primitive `int` value.

**Question 2.** Why does `byte a = 1, b = 2; byte c = a + b;` fail to compile?  
**Answer:** Addition applies numeric promotion, producing an expression of type `int`, so it requires an `int` target or an appropriate explicit cast; a non-constant `int` expression is not automatically assigned to `byte`.

**Question 3.** How many local slots do `long` and `double` occupy in a frame?  
**Answer:** Each value occupies **two slots** according to the JVM model; this does not determine the exact final RAM layout.

**Question 4.** Two references point to the same object; changing a field through reference A, what does reference B see?  
**Answer:** B can observe the new field value of the **same object**, subject to synchronization and memory visibility rules if multiple threads are involved. In a normal single-threaded execution, the field change is immediately observable through that alias.

**Question 5.** Why can `getfield` be used on a reference, but `iadd` cannot be used on two references?  
**Answer:** The bytecode verifier and type model distinguish references from numeric operands. `iadd` requires two `int` values, whereas `getfield` operates on an object reference matching the specified field.

**Question 6.** Can we determine that a reference variable always occupies exactly 8 bytes because the application runs on a 64-bit JVM?  
**Answer:** **No.** How references are represented and optimized depends on the JVM/configuration; descriptors and operand-stack categories do not encode a fixed native address width.

**Question 7.** Why does `Integer number = null; int x = number;` fail even though the compiler accepts it?  
**Answer:** `Integer` is a reference type that can be `null`; **unboxing at runtime** attempts to extract an `int` value from `null` and thus throws `NullPointerException`.

In summary, **primitive values** are copied by content, whereas **reference values** are copied as a handle to access an object. The JVM reflects that distinction through **type descriptors, instruction families, local-variable slots, the operand stack, and bytecode verification**; actual memory layout is the responsibility of the runtime/JIT/GC. Understanding these layers helps read `javap`, diagnose `NullPointerException`, avoid pass-by-value confusion, and accurately explain the behavior of assignments, arrays, fields, and method calls.