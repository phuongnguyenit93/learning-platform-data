# `checkcast`, `instanceof`, `arraylength`, and Checks During Array Access

In the JVM execution model, **`checkcast`**, **`instanceof`**, and **`arraylength`** are three bytecode instructions with different purposes. The first two work with **reference values and object types at runtime**; the third retrieves the **length of an array object**. When a program accesses array elements, instructions such as `iaload` and `aastore` also perform specific checks for **null**, **valid index**, and **stored element type**.

Understanding these instructions helps explain why Java can compile successfully yet encounter `ClassCastException`, `NullPointerException`, `ArrayIndexOutOfBoundsException`, or `ArrayStoreException` at runtime. At the same time, it shows that JVM bytecode has dynamic checks that are **different** from the bytecode verifier: the verifier checks the structural/type validity of code before execution, whereas instructions perform checks on **actual program values**.

## 1. Overview

| Instruction/group | Target of operation | Input on operand stack | Main result | Typical runtime error |
| --- | --- | --- | --- | --- |
| `checkcast` | Target reference type | One reference | Keeps the same reference if cast is valid | `ClassCastException` |
| `instanceof` | Target reference type | One reference | `int` 1 or 0 | Does not throw `ClassCastException` on type mismatch |
| `arraylength` | Array | One array reference | `int` representing length | `NullPointerException` if reference is `null` |
| `*aload` | Array element | Array reference and `int` index | Element value | `NullPointerException`, `ArrayIndexOutOfBoundsException` |
| `*astore` | Array element | Array reference, index, value to write | Pushes no result | `NullPointerException`, `ArrayIndexOutOfBoundsException`; for `aastore` also possibly `ArrayStoreException` |

In the table, `*aload` and `*astore` are **group names**, not valid opcode names to write literally into a class file. The JVM has specific opcodes such as `iaload`, `aaload`, `iastore`, and `aastore`.

Three principles to remember:

1. **`checkcast` checks the ability to cast a reference to the target type**; it does not create a new object and does not modify the object's runtime class.
2. **`instanceof` asks whether a reference is compatible with the target type**; it returns `0` or `1` on the operand stack, and subsequent branching bytecode can use the result.
3. **A Java array is an object with a fixed length**, and element access instructions must handle null, bounds, and (for reference arrays) runtime type assignability.

## 2. Recap: reference, operand stack, and runtime type

In Java:

```java
Object value = "JVM";
String text = (String) value;
```

`value` is declared with static type `Object`, but at runtime it holds a reference to a `String`. The variable `text` receives the same reference after a valid cast. The Java compiler verifies whether the written cast is allowed by language rules; the JVM **checks the actual object** when executing the `checkcast` bytecode.

For the operand stack, references are all **category 1**. The notation below is written in **bottom → top** order; `value` is at the top:

```text
... , value
            ↑
           TOP
```

A reference value on the stack is not a copy of the entire object's contents pushed onto the stack. The JVM uses it to access the object or array. When `checkcast` succeeds, **the reference remains the same**. `instanceof`, on the other hand, consumes the reference and **pushes an `int` result**. These details determine what the next instruction can do.

## 3. `checkcast`: checking reference type at runtime

### 3.1. Bytecode syntax and stack effect

The `checkcast` opcode is **`0xC0`**. The instruction carries a two-byte index referencing the target type information in the constant pool (an appropriate `CONSTANT_Class`).

```text
Before: ..., objectref
checkcast <target-type>
After if successful: ..., objectref
```

- If `objectref` is **`null`**, `checkcast` **succeeds**, keeping `null` on the stack.
- If the reference is non-`null` and the runtime object is compatible with the target type, the instruction **succeeds**, keeping **that same reference**.
- If the object cannot be cast to the target type, the instruction throws **`ClassCastException`**.
- Resolving the target type from the constant pool can also encounter linking/class issues in specific situations; do not assume every class loading error is `ClassCastException`.

Valid example:

```java
Object value = "hello";
String text = (String) value;
System.out.println(text.length());
```

This is a **code snippet placed inside a method**, not a complete program. `value` holds a `String`; the compiler can emit `checkcast java/lang/String` after loading the reference to guarantee the object type before calling `String.length()`.

Invalid example at runtime:

```java
Object value = Integer.valueOf(42);
String text = (String) value; // ClassCastException at runtime
```

This snippet can still **compile**, because the static type `Object` allows an explicit cast to `String`. However, the actual object is an `Integer`. There is no operation converting the numeric content `42` into the string `"42"` in the `checkcast` instruction.

### 3.2. Casting is not equivalent to value conversion

```java
Object number = Integer.valueOf(42);
String converted = String.valueOf(number); // "42"
```

`String.valueOf` performs an operation to create/obtain a string according to the API, whereas `(String) number` checks **the ability to use the reference as a String**. They have completely different semantics.

Primitive casts are also different: `(int) 3.7` uses the corresponding numeric conversion mechanism (such as `d2i`), **not** `checkcast`, because the operand is not a reference.

### 3.3. Where is type checking done?

`javac` checks the validity of a cast expression according to the **source type system**. When a reference cast still requires dynamic checking, the compiler emits `checkcast`. Casts that are guaranteed to be redundant may not emit a separate check instruction; therefore **not every cast parenthesis in source code corresponds to a `checkcast` opcode**.

In Java generics after type erasure, the compiler may also insert `checkcast` after retrieving a value from a type-erased generic API. For example, assigning the result of `List<String>.get(...)` to `String` may require `checkcast java/lang/String` in bytecode, even though the source code does not write an explicit cast.

**Generics note:** The JVM can check whether a runtime object is a `List`, but generally has no mechanism from a single reference to verify that all of its elements are `String`. Generic type arguments are erased in descriptors; this is why unchecked casts and heap pollution need to be understood separately.

## 4. `instanceof`: checking type and producing `int` 0/1

The `instanceof` opcode is **`0xC1`**; it also references the target type via a constant pool index.

```text
Before: ..., objectref
instanceof <target-type>
After:   ..., result (int)
```

- Reference is `null` → result is **`0`**.
- Reference is non-`null`, object is compatible with target type → **`1`**.
- Reference is non-`null`, object is not compatible → **`0`**.
- `instanceof` does not throw `ClassCastException` merely because the type does not match. However, errors in resolving the specified type can exist independently.

In Java source, `instanceof` has a **`boolean`** result. At the JVM operand stack level, the conditional value is represented as `int` 0/1 and can be used with instructions such as `ifeq` or `ifne`.

Example:

```java
Object value = "abc";
if (value instanceof String) {
    System.out.println("This is a String");
}
```

This is a code snippet placed inside a method; the compiler may emit `instanceof java/lang/String`, then `ifeq` to skip the branch if the result is 0.

### 4.1. `instanceof` and `checkcast` often appear together

The source snippet:

```java
static int textLength(Object value) {
    if (value instanceof String) {
        return ((String) value).length();
    }
    return -1;
}
```

is a **helper method**, which needs to be placed inside a Java class to compile. In typical compilers, the conditional branch uses `instanceof`, and when accessing `String.length()`, a `checkcast` brings the reference into the form that bytecode uses for that operation.

Although the two instructions often stand close together, **they do not replace each other**:

| Case | `instanceof String` | `(String) value` / `checkcast String` |
| --- | --- | --- |
| `value` is a reference to `String` | `true` (bytecode returns 1) | Succeeds, keeps reference |
| `value` is a reference to `Integer` | `false` (bytecode returns 0) | Throws `ClassCastException` |
| `value` is `null` | `false` (bytecode returns 0) | Succeeds, result remains `null` |

**Specifically:** `(String) null` **does not by itself cause `NullPointerException`**. However, if the `null` result is used to call `length()`, the instance method invocation statement can cause `NullPointerException`.

### 4.2. Pattern matching for `instanceof` (Java 17)

Java 17 supports pattern matching such as:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "String length=" + text.length();
    }
    return "other";
}
```

`text` is a **pattern variable** whose scope the compiler restricts to the branch where the type is known to match. This makes source code shorter and avoids the programmer rewriting a manual cast; **it does not mean the JVM has a separate opcode named `instanceof_pattern`**. The bytecode may still consist of `instanceof`, branching, casting when needed, and storing into a local variable. Check `javap -c` to see what a specific compiler generates.

## 5. Array types also participate in `checkcast` and `instanceof`

Java arrays are objects; each array has a **runtime array class** with an element type and number of dimensions. Therefore, reference checks also apply to arrays:

```java
Object values = new String[2];
boolean b1 = values instanceof String[]; // true
boolean b2 = values instanceof Object[]; // true
boolean b3 = values instanceof int[];    // false
String[] names = (String[]) values;       // succeeds
```

This is a source snippet placed inside a method. It illustrates that `String[]` is a reference type, and the array elements do not need to currently hold any specific string for `instanceof String[]` to return `true`.

Reference array types follow the **covariance** rule: for example, `String[]` can be referenced through `Object[]`. However, the runtime component type of the object is still `String`; when writing an element, `aastore` must check assignability.

```java
Object[] base = new String[1];
base[0] = "ok";
base[0] = new Object(); // ArrayStoreException at runtime
```

This snippet is **not** a `ClassCastException` error. The variable assignment `Object[] base = new String[1]` is allowed by covariance. The error only arises when actually attempting to **store an incompatible object** into an array whose runtime component type is `String`.

Primitive arrays such as `int[]` are also objects, but **not `Object[]`**, because their elements are not references. An `int[]` can be assigned to a variable of type `Object`, but cannot be assigned directly to a variable of type `Object[]`.

## 6. `arraylength`: getting the number of array elements

The `arraylength` opcode is **`0xBE`**, with no constant-pool index operand.

```text
Before: ..., arrayref
arraylength
After:   ..., length (int)
```

- If `arrayref` is a reference to a valid array, the JVM reads the **length of the array** and pushes the `int` result.
- If `arrayref == null`, the instruction throws **`NullPointerException`**.
- Array length is the **number of elements**, not the byte size. For example, `new long[3]` has `length == 3`, not 24.
- Array length does not change after the array object is created. To have a different number of elements, create another array object or use a dynamic structure like `ArrayList`.

Example:

```java
int[] values = {10, 20, 30};
System.out.println(values.length); // 3
```

An important distinction: the Java syntax `values.length` is a **special property of array types**, and the compiler normally emits the **`arraylength`** opcode, not `getfield length` of an ordinary Java class. For `String`, `text.length()` is a **method call**, which is completely different.

### `arraylength` does not check bounds

`arraylength` only needs an array reference; it **does not take an element index**. Index checking happens in `*aload`/`*astore`. For example:

```java
int[] values = new int[2];
int n = values.length; // n = 2, does not access element
int x = values[2];     // ArrayIndexOutOfBoundsException
```

This is an illustrative snippet placed inside a method, not a standalone runnable program. For an array of length `n`, valid indices are **`0 <= index < n`**; negative indices are also invalid.

### Multidimensional arrays

Java represents multidimensional arrays as **arrays containing sub-arrays**:

```java
int[][] grid = { {1, 2, 3}, {4} };
System.out.println(grid.length);    // 2: number of rows
System.out.println(grid[0].length); // 3: number of elements in the first row
System.out.println(grid[1].length); // 1: length of the second row
```

`grid.length` and `grid[0].length` are two `arraylength` operations applied to **two different array references**. Java does not require all sub-arrays to have the same length. If a row is `null`, using `grid[i].length` can encounter `NullPointerException`.

## 7. The `*aload` instructions: reading array elements

Each element type has an appropriate instruction:

| Opcode | Corresponding array | Type of pushed value |
| --- | --- | --- |
| `iaload` | `int[]` | `int` |
| `laload` | `long[]` | `long` (category 2) |
| `faload` | `float[]` | `float` |
| `daload` | `double[]` | `double` (category 2) |
| `aaload` | Reference type array, e.g., `String[]` | Reference |
| `baload` | `byte[]` or `boolean[]` | Value pushed onto the operand stack as `int` |
| `caload` | `char[]` | `int` (zero-extended from `char`) |
| `saload` | `short[]` | `int` (sign-extended from `short`) |

When reading `byte[]`, `baload` sign-extends the signed byte to `int`; for `boolean[]`, true/false representation follows the corresponding JVM rules. `caload` preserves the unsigned value of `char` when pushing onto the stack.

General stack effect:

```text
Before: ..., arrayref, index(int)
*aload
After:   ..., value
```

Important checks:

1. Array reference must be non-`null`, otherwise → **`NullPointerException`**.
2. Index must be within `0..length-1`, otherwise → **`ArrayIndexOutOfBoundsException`**.
3. Operands and opcode must match the array type according to bytecode type constraints; the JVM verifier protects against arbitrarily using `iaload` as if a reference to `String[]` were an `int[]` array.

**When both the array reference is `null` and the index is out of range**, there is no valid array to determine bounds: a null error will occur rather than concluding anything about the bounds of a nonexistent object. On a valid array, negative indices or indices `>= length` are all invalid.

### Example of reading narrow types

```java
byte[] bytes = {(byte) 0xFF};
char[] chars = {(char) 255};
short[] shorts = {(short) -2};

System.out.println(bytes[0]);       // -1
System.out.println((int) chars[0]); // 255
System.out.println(shorts[0]);      // -2
```

This example snippet is placed inside `main` or an equivalent method. The difference between `-1` and `255` helps show that `byte` is a signed type, while `char` is an unsigned UTF-16 code unit; the compiler/JVM performs the corresponding conversion when pushing the value onto the operand stack.

## 8. The `*astore` instructions: writing array elements

| Opcode | Target array written | Value written |
| --- | --- | --- |
| `iastore` | `int[]` | `int` |
| `lastore` | `long[]` | `long` |
| `fastore` | `float[]` | `float` |
| `dastore` | `double[]` | `double` |
| `aastore` | Reference array such as `Object[]`, `String[]` | Reference, with runtime component type check |
| `bastore` | `byte[]`, `boolean[]` | Appropriate value processed from `int` form |
| `castore` | `char[]` | Appropriate value converted to `char` |
| `sastore` | `short[]` | Appropriate value converted to `short` |

General stack effect:

```text
Before: ..., arrayref, index(int), value
*astore
After:   ...
```

`lastore` and `dastore` consume a **category 2** value; the remaining opcodes take their operand type according to the corresponding rules. After a successful store, the instruction **does not leave the written value** on the stack. If the assignment expression must have a result, the compiler can use an appropriate `dup_x2` or `dup2_x2` to keep a copy of the value before storing.

### 8.1. Three types of checks when writing

For an array reference:

- **Null check**: array reference is `null` → `NullPointerException`.
- **Bounds check**: index less than 0 or greater than/equal to length → `ArrayIndexOutOfBoundsException`.
- **Store type check for `aastore`**: for a non-`null` written element, the runtime object of the element must be compatible with the **runtime component type of the array object itself**; otherwise → `ArrayStoreException`.

It is necessary to separate the **static type of the array variable** from the **runtime type of the array object**:

```java
Object[] slots = new String[2];
slots[0] = "ok";       // valid
slots[1] = new Object(); // ArrayStoreException at runtime
```

The compiler accepts assigning `new Object()` to an element of a variable with static type `Object[]`. However, the actual array object is `String[]`, so `aastore` must reject a non-`String` object. This type check is **not `checkcast`** and the error is **`ArrayStoreException`**, not `ClassCastException`.

### 8.2. `null` values and reference arrays

`null` can be written into any compatible reference array:

```java
String[] words = new String[1];
words[0] = null; // valid
```

Even though the written value is `null` and there is no object whose runtime class needs checking, **the null/bounds checks on the array itself must still be satisfied**. For example, `words[9] = null` is still out of bounds.

Primitive arrays do not have `null` for individual elements: `int[]` holds `int` values, not `Integer` references. If nullable elements are needed, `Integer[]` can be used, but it is a different array type and boxing/unboxing has additional rules.

## 9. Difference between the bytecode verifier and dynamic checks

A common mistake is saying “the JVM already verified the bytecode so array access cannot go wrong.” In reality, there are two different layers of checks:

| Layer | Example checks | Timing/purpose |
| --- | --- | --- |
| `javac` compiler | Type of expression `a[i]`, feasibility of cast, variable types, syntax | Before creating the class file |
| Bytecode verification / linking | Operand types on operand stack, stack frames, control flow, appropriateness of `iaload`/`arraylength` | When the JVM verifies/prepares to use the class file according to JVM rules |
| Dynamic checks at instruction | Whether object can be cast, whether reference is null, whether index is in bounds, whether element matches runtime array component type | **During execution**, depending on runtime data |

The bytecode verifier cannot know in advance the actual value of an index received from a user or an object returned from a library. Therefore, a completely valid class file can still throw exceptions at runtime.

The JIT may optimize away **checks that are observably unnecessary** when it proves them redundant, such as hoisting/eliminating certain bounds checks. This does not change the semantics that must be preserved: cases that ought to throw an exception must still behave in accordance with the Java model. Do not use the existence of the JIT to conclude that instructions have no runtime checks.

## 10. Runnable Java 17+ example: cast, `instanceof`, length, and array access

Create a file **`CastArrayDemo.java`** in your working directory:

```java
public class CastArrayDemo {
    static String castText(Object value) {
        return (String) value;
    }

    static String describe(Object value) {
        if (value instanceof String text) {
            return "String(" + text.length() + ")";
        }
        return "other";
    }

    static int arraySize(int[] data) {
        return data.length;
    }

    static int read(int[] data, int index) {
        return data[index];
    }

    static void write(int[] data, int index, int value) {
        data[index] = value;
    }

    public static void main(String[] args) {
        Object text = "JVM";
        Object number = Integer.valueOf(42);
        Object absent = null;

        System.out.println("instanceof text: " + (text instanceof String));
        System.out.println("instanceof number: " + (number instanceof String));
        System.out.println("instanceof null: " + (absent instanceof String));
        System.out.println("pattern: " + describe(text));
        System.out.println("cast: " + castText(text));
        System.out.println("cast null: " + (castText(absent) == null));

        try {
            castText(number);
        } catch (ClassCastException e) {
            System.out.println("bad cast: ClassCastException");
        }

        int[] scores = {5, 8};
        System.out.println("length: " + arraySize(scores));
        System.out.println("read: " + read(scores, 1));
        write(scores, 0, 11);
        System.out.println("after write: " + scores[0]);

        byte[] bytes = {(byte) 0xFF};
        char[] chars = {(char) 255};
        System.out.println("byte load: " + bytes[0]);
        System.out.println("char load: " + (int) chars[0]);

        try {
            read(scores, 2);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("bad index: ArrayIndexOutOfBoundsException");
        }

        try {
            arraySize(null);
        } catch (NullPointerException e) {
            System.out.println("null array: NullPointerException");
        }

        Object[] slots = new String[1];
        slots[0] = "ok";
        System.out.println("stored: " + slots[0]);
        try {
            slots[0] = new Object();
        } catch (ArrayStoreException e) {
            System.out.println("bad store: ArrayStoreException");
        }

        Object rawArray = new String[2];
        System.out.println("instanceof String[]: "
                + (rawArray instanceof String[]));
        System.out.println("cast array length: "
                + ((String[]) rawArray).length);
    }
}
```

With JDK 17 or later:

```bash
javac -encoding UTF-8 CastArrayDemo.java
java CastArrayDemo
```

**Exact standard output:**

```text
instanceof text: true
instanceof number: false
instanceof null: false
pattern: String(3)
cast: JVM
cast null: true
bad cast: ClassCastException
length: 2
read: 8
after write: 11
byte load: -1
char load: 255
bad index: ArrayIndexOutOfBoundsException
null array: NullPointerException
stored: ok
bad store: ArrayStoreException
instanceof String[]: true
cast array length: 2
```

Explanation:

1. `text` points to a `String`, so `instanceof` is `true`; `number` points to an `Integer`, so it does not match; `absent == null` makes `instanceof` return `false`.
2. `describe(text)` uses **pattern matching for `instanceof`** and returns the string length 3.
3. `castText(text)` succeeds; `castText(absent)` still returns `null`; only `castText(number)` throws `ClassCastException`.
4. `scores.length` is 2; index 1 is valid and reads 8. After writing `scores[0] = 11`, the array holds the value 11.
5. The byte value `0xFF` corresponds to `-1` when interpreted as a signed `byte`; `char` 255 is unsigned.
6. Reading `scores[2]` exceeds the range `0..1`, so it is caught as `ArrayIndexOutOfBoundsException`.
7. `arraySize(null)` executes `arraylength` on a `null` reference, causing `NullPointerException`.
8. `slots` has variable type `Object[]` but the object is `String[]`. Writing `"ok"` is valid, while writing `new Object()` is rejected with `ArrayStoreException`.
9. The reference `rawArray` points to `String[]`; both the `instanceof String[]` check and `checkcast` to `String[]` are valid. Casting does not create a second array.

The example intentionally **catches exceptions by type** and prints fixed strings, because the detailed message in `e.getMessage()` may vary across JVMs and versions. Thus, the stdout above is a stable output of the program.

## 11. Using `javap` to read real bytecode

From the directory containing `CastArrayDemo.class`:

```bash
javap -c -p CastArrayDemo
javap -v -p CastArrayDemo
```

`-c` prints bytecode, `-p` allows viewing non-public methods as well; `-v` additionally displays the constant pool, descriptors, exception table, and ClassFile attributes.

Look for methods/segments such as:

| Source/method | Typical bytecode | Meaning |
| --- | --- | --- |
| `castText(Object)` | `aload_0`, `checkcast java/lang/String`, `areturn` | Checks reference then returns reference |
| `describe(Object)` | `instanceof java/lang/String`, branch, possibly `checkcast` | Decides branch and assigns pattern variable |
| `arraySize(int[])` | `aload_0`, `arraylength`, `ireturn` | Gets array length as `int` |
| `read(int[], int)` | `aload_0`, `iload_1`, `iaload`, `ireturn` | Gets `int` element with null/bounds checks |
| `write(int[], int, int)` | `aload_0`, `iload_1`, `iload_2`, `iastore`, `return` | Writes `int` element |
| `slots[0] = new Object()` | `aastore` | Checks runtime component type when storing reference |

The rows above describe **important instructions**; offsets, constant pool indices, and how the compiler generates pattern matching/string concatenation may differ between JDKs. Do not replace inspecting actual `javap` output with an assumed listing.

### 11.1. Operand stack through `checkcast`

```text
aload_0
  ..., objectref
checkcast java/lang/String
  ..., objectref         // keeps the same value if successful
areturn
  ...                    // reference is returned to caller
```

### 11.2. Operand stack through `instanceof`

```text
aload_0
  ..., objectref
instanceof java/lang/String
  ..., result(int: 0 or 1)
ifeq target
  ...                    // condition is popped from stack for branching
```

### 11.3. Operand stack through `arraylength` and `iaload`

```text
aload_0                    // int[] reference
arraylength                // int length
ireturn

aload_0                    // int[] reference
iload_1                    // int index
iaload                     // int element
ireturn
```

These fragments are **illustrative diagrams**, not a standalone `.jasm` file to run. If the array or index is invalid, the instruction throws an exception instead of placing a normal result onto the stack.

### 11.4. `aastore` can fail without `checkcast`

When compiling `Object[] slots = new String[1]`, the variable `slots` has static type `Object[]`. An instruction writing an object through that variable can directly use **`aastore`**, without needing to add `checkcast String` to the source/bytecode. **`aastore` itself** is responsible for ensuring the stored object is compatible with the element type of the actual array. This is what helps distinguish `ArrayStoreException` from `ClassCastException`.

## 12. Error matrix and how to reason in the right order

| Situation | Instruction/operation | Result |
| --- | --- | --- |
| `(String) Integer.valueOf(42)` after static type allows cast | `checkcast` | `ClassCastException` |
| `null instanceof String` | `instanceof` | `false` / bytecode `0` |
| `(String) null` | `checkcast` | Succeeds, keeps `null` |
| `((String) null).length()` | Cast then method call | Cast is valid, dereference causes `NullPointerException` |
| `((int[]) null).length` | `arraylength` | `NullPointerException` |
| `new int[2]` then read index `-1` or `2` | `iaload` | `ArrayIndexOutOfBoundsException` |
| `new int[2]` then write index `2` | `iastore` | `ArrayIndexOutOfBoundsException` |
| `Object[] a = new String[1]; a[0] = new Object();` | `aastore` | `ArrayStoreException` |
| `Object[] a = new String[1]; a[0] = null;` | `aastore` | Valid |
| `new long[3]` and `.length` | `arraylength` | `3` as `int` |

**Do not equate the evaluation order of Java source code with the check order inside an instruction.** In a complex expression, Java has its own rules for evaluating operands and side effects. Once `*aload`/`*astore` is reached, the instruction operates on the values already prepared on the operand stack and checks null/bounds/type according to the specification. If you need to determine which exception occurs in an expression with multiple failing subexpressions, examine both the source evaluation order and the `javap` bytecode.

### Distinguishing errors from array creation errors

`NegativeArraySizeException` arises when creating an array with a negative size in instructions such as `newarray` or `anewarray`, **not** from `arraylength`. `OutOfMemoryError` can also occur when allocating an array if the runtime lacks sufficient resources. They relate to the array object lifecycle, but do not replace the array access checks in this lesson.

## 13. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “`checkcast` converts `Integer` to `String`.” | It checks the ability to use the **same reference** under the target type; it does not convert object contents |
| “Casting `null` to `String` throws NPE.” | Casting `null` succeeds; NPE only occurs when performing an invalid dereference operation |
| “`instanceof` returns a new reference if the type matches.” | It pops the reference from the stack and pushes `int` 1/0 |
| “If source has `instanceof`, bytecode always has just one opcode.” | The compiler may add branching, `checkcast`, and pattern variable stores depending on the logic |
| “`array.length` is `getfield` like a normal field.” | Arrays use the dedicated `arraylength` instruction |
| “`arraylength` checks the array index.” | It has no index operand; `*aload`/`*astore` check bounds |
| “An `Object[]` array can hold any object.” | If the actual array object is `String[]`, `aastore` only allows values compatible with `String` or `null` |
| “`ArrayStoreException` is `ClassCastException`.” | These are two different exceptions, caused by different runtime checks |
| “The verifier already checked the bytecode so runtime indices cannot be wrong.” | The verifier does not know in advance the actual index/object received at runtime |
| “`int[][]` is always a rectangular block.” | A two-dimensional array is an array of arrays; rows can have different lengths or be `null` |
| “`baload` is only used for `byte[]`.” | It is used for both `byte[]` and `boolean[]` according to the JVM Specification |
| “If the JIT removes bounds checks, the program doesn't need to follow Java semantics.” | Optimizations must preserve observable behavior according to Java semantics |

## 14. Self-check exercises

**1.** Does `Object x = null; String s = (String) x;` throw `ClassCastException`?  
**Answer:** No. `checkcast` accepts `null`; `s == null`.

**2.** Does `Object x = Integer.valueOf(10); boolean ok = x instanceof String;` throw `ClassCastException`?  
**Answer:** No. `ok == false`. Only if you attempt `(String) x` will an invalid cast occur.

**3.** For `int[] a = new int[4]`, what are the valid indices?  
**Answer:** 0, 1, 2, 3. `-1` and `4` both cause `ArrayIndexOutOfBoundsException` when accessed.

**4.** Why does `int[] a = null; int n = a.length;` cause an error?  
**Answer:** `arraylength` requires a reference to an array object, but the operand is `null`, resulting in `NullPointerException`.

**5.** What error does `Object[] a = new String[1]; a[0] = Integer.valueOf(1);` cause?  
**Answer:** `ArrayStoreException`: the actual array object is `String[]`, which cannot hold an `Integer` as an element.

**6.** How do `instanceof` and `checkcast` differ regarding the operand stack?  
**Answer:** `instanceof` pops the reference and pushes `int` 0/1; `checkcast`, if successful, keeps that reference on the stack, and if it fails, throws an exception.

**7.** Does `long[] a = new long[3]; a.length` return `long` because the elements have type `long`?  
**Answer:** No. `arraylength` always pushes an **`int`** representing the number of elements; the result is 3.

**8.** Why does `aastore` need dynamic type checking even though `javac` already checked the assignment?  
**Answer:** Reference arrays are **covariant**, so a variable of type `Object[]` can point to a `String[]` object. The compiler only sees the static type of the variable; the runtime knows the actual element type and prevents writes that break type safety.

**9.** Do `byte[]` and `boolean[]` have two completely different load opcodes?  
**Answer:** No. The JVM uses `baload` for both cases, with appropriate element representation/reading rules.

**10.** If `ArrayIndexOutOfBoundsException` occurs, should you fix it by disabling the bytecode verifier?  
**Answer:** No. The error is caused by a **runtime index** being outside the array's range. You need to check the condition `0 <= index && index < array.length` and the array creation/traversal logic; the verifier is not the cause.

**Reference:** *Java Virtual Machine Specification*, Section 6.5 (entries for `checkcast`, `instanceof`, `arraylength`, `iaload`, `aaload`, `aastore`, and related array instructions): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html. For Java source expressions and operand evaluation order, also see the *Java Language Specification* Java 17.

**Conclusion:** `checkcast` **checks and keeps the reference**, `instanceof` **checks and pushes `int` 0/1**, `arraylength` **pushes the `int` length of the array**, and `*aload`/`*astore` **read/write elements with null and bounds checks**; in particular, `aastore` also checks the **runtime component type**. When encountering an exception, distinguish between **object type check**, **dereference**, **index**, **array element compatibility**, and **bytecode verification** before fixing the program.