# `new`, `newarray`, `anewarray`, and `multianewarray` for Creating Data in the JVM

## 1. Four opcodes solving four allocation scenarios

In Java source code, the `new` keyword appears both when creating an instance and when creating an array. However, in **JVM bytecode**, there are multiple data-creation instructions with different responsibilities. We need to distinguish between **Java keywords** and **JVM opcodes**.

| Java expression | Allocation opcode commonly seen from `javac` | What is created |
| --- | --- | --- |
| `new Person("Lan")` | `new`, followed by `invokespecial` to call `<init>` | An instance object of the class |
| `new int[3]` | `newarray` | An array object with `int` elements |
| `new String[3]` | `anewarray` | An array object with `String` reference elements |
| `new int[2][3]` | `multianewarray` | The outer array and subarrays of the two specified dimensions |
| `new int[2][]` | `anewarray` with component type `int[]` | Only the outer array; the rows are initially `null` |

All four instructions can **create an object on the heap and push a reference onto the operand stack**. The differences lie in the object type, how operands are encoded, the number of array dimensions provided, and whether an instance constructor needs to be called after allocation.

```text
                      Java syntax using new
                                |
             +------------------+------------------+
             |                                     |
      new Person(...)                         new Type[...]
             |                                     |
            new                   +-----------------+-----------------+
                                  |                 |                 |
                            primitive[]       reference[]     multidimensional
                                  |                 |                 |
                               newarray         anewarray       multianewarray
```

This is the common compilation pattern; a compiler may generate other valid bytecode sequences for the same semantics. Therefore, to know which instruction a `.class` file actually uses, inspect it with `javap -c`.

## 2. General model: heap, operand stack, and constant pool

The JVM is a stack-based virtual machine. During allocation:

1. Bytecode provides the **type to allocate** via operands encoded immediately after the opcode, such as `atype` or a constant-pool index.
2. Dynamic data such as the **array length `count`** is pushed onto the **operand stack** before the instruction.
3. The instruction checks the relevant conditions, allocates the array/object in the **heap** model, and pushes the resulting **reference** onto the operand stack.
4. A subsequent instruction such as `astore` can store that reference into a local slot.

For example:

```text
iconst_3       stack: []  → [3]
newarray int   stack: [3] → [ref(int[3])]
astore_1       stack: [ref(int[3])] → []
               locals[1] holds the reference to the array
```

**The array does not reside entirely inside the operand stack.** The stack only holds the reference value after allocation. The actual array has its elements, length, and runtime type in the memory area for objects.

Some terms to separate:

- **Opcode:** the operation code, such as `newarray` or `multianewarray`. Each opcode is encoded as one byte.
- **Operand bytes:** encoded data following the opcode, such as a constant-pool index, `atype`, `dimensions`.
- **Operand stack:** runtime values that the instruction reads/consumes, such as `count`. `count` does **not** necessarily reside in the instruction's operand bytes.
- **Local variables:** slots in a method frame, typically holding the reference after an `astore` instruction.
- **Constant pool:** class-file data containing the type symbols that `new`, `anewarray`, and `multianewarray` reference.

For example, `newarray int` has an operand byte specifying the `int` type, while the **length** is an `int` value on the operand stack. This is a place where beginners often get confused.

## 3. `new` — creating a class instance

### 3.1. JVM format

`new` has the form:

```text
new indexbyte1 indexbyte2
```

- The opcode is **`0xbb`**.
- The two following bytes form an **unsigned 16-bit constant-pool index**.
- The referenced entry is a `CONSTANT_Class_info` describing the class to be instantiated.
- The instruction does not consume `count` like array-creation instructions.
- On success, it allocates an instance and pushes a **reference in an uninitialized state** according to verifier rules.

Source code example:

```java
final class Person {
    final String name;

    Person(String name) {
        this.name = name;
    }
}

// Illustration inside a method:
Person p = new Person("Lan");
```

Illustrative bytecode:

```text
new           #k     // class Person
dup
ldc           #s     // String "Lan"
invokespecial #m     // Method Person."<init>":(Ljava/lang/String;)V
astore_1
```

The indices `#k`, `#s`, `#m`, and the local slot are **illustrative placeholders**, not fixed byte-for-byte output of every `javac`.

### 3.2. Why does `new` not mean calling the constructor?

Three steps need to be separated:

1. **Instance allocation:** `new` creates the object and its fields have default values according to the JVM model.
2. **Class initialization:** if the class has not been initialized and the rules require it, the JVM performs class initialization, including applicable `static` blocks.
3. **Instance initialization:** `invokespecial` typically calls `<init>` to complete the constructor; the compiler ensures super-constructor calls and initialization actions according to Java rules.

If the constructor throws an exception, the expression `new Person(...)` does not complete normally. The verifier tracks the **uninitialized reference** and does not allow using it arbitrarily as an initialized instance.

### 3.3. Why does `dup` usually appear?

`invokespecial <init>` consumes the receiver along with the arguments on the operand stack. However, the expression `new Person("Lan")` still needs to return a reference to the object after the constructor. `dup` is commonly used to retain a reference for storing the result:

```text
new Person          → [uninitializedRef]
dup                 → [uninitializedRef, uninitializedRef]
ldc "Lan"           → [uninitializedRef, uninitializedRef, "Lan"]
invokespecial <init>→ [initializedRef]   (on success)
astore_1            → []                 (local 1 holds the reference)
```

This is a typical stack diagram, not a rule that every allocation must go through the exact same sequence of instructions.

### 3.4. `new` is not used to create interfaces, abstract instances, or arrays

Interfaces or abstract classes cannot be directly instantiated:

```java
// The following lines only illustrate compilation errors:
// Runnable r = new Runnable();
// java.lang.Number n = new java.lang.Number();
```

Arrays `int[]` and `String[]` are also not created by using the `new` opcode targeting an array class like a normal instance. They have their own array-creation opcodes.

If a class file is generated improperly and requests instantiating an inappropriate class, an `InstantiationError` or related linking/verification errors may occur. With normal Java source code, many cases are blocked early by the compiler.

## 4. `newarray` — creating a one-dimensional primitive array

### 4.1. Format and stack effect

```text
newarray atype
```

- Opcode byte: **`0xbc`**.
- `atype`: one byte representing the **primitive component type**.
- Operand stack **before the instruction**: must have an `int` value `count`.
- The instruction pops `count`, creates **a primitive array**, and pushes the array's reference.
- If `count < 0`, it throws `NegativeArraySizeException`.

```text
iconst_3       stack []  → [3]
newarray int   stack [3] → [ref(int[3])]
```

### 4.2. Complete table of `atype` values

| Value | Name in JVMS | Primitive component type | Example source code |
| ---: | --- | --- | --- |
| 4 | `T_BOOLEAN` | `boolean` | `new boolean[2]` |
| 5 | `T_CHAR` | `char` | `new char[2]` |
| 6 | `T_FLOAT` | `float` | `new float[2]` |
| 7 | `T_DOUBLE` | `double` | `new double[2]` |
| 8 | `T_BYTE` | `byte` | `new byte[2]` |
| 9 | `T_SHORT` | `short` | `new short[2]` |
| 10 | `T_INT` | `int` | `new int[2]` |
| 11 | `T_LONG` | `long` | `new long[2]` |

There is no `T_STRING` or `T_OBJECT` code in this table. If the component type is a reference, we need the reference-array creation mechanism.

### 4.3. What are the initial elements?

When an array object is allocated, its elements are set to the **default value of the component type**:

| Array | Default element value |
| --- | --- |
| `int[]`, `byte[]`, `short[]` | 0 |
| `long[]` | `0L` |
| `float[]` | `0.0f` |
| `double[]` | `0.0d` |
| `boolean[]` | `false` |
| `char[]` | character `'\u0000'` |

`new int[3]` has one array object with three `0` elements. It does **not** create three instances of the wrapper class `Integer`, and there is no constructor for each primitive element.

Even though the elements are primitives, **the array itself is an object**: `Object o = new int[3];` is valid; `int[]` has `length` and has a runtime type.

## 5. `anewarray` — creating an array with reference elements

### 5.1. Format

```text
anewarray indexbyte1 indexbyte2
```

- Opcode byte: **`0xbd`**.
- The two operand bytes form a constant-pool index to a `CONSTANT_Class_info` describing the **component type**.
- The operand stack provides `count` of type `int`.
- The result is a **reference array** of length `count`.
- All elements initially hold the **null value**, not yet referencing any instance.

Example:

```java
String[] names = new String[3];
Runnable[] jobs = new Runnable[3];
Number[] values = new Number[3];
```

`Runnable` is an interface and `Number` is an abstract class, yet arrays of them are still valid: the slots only hold **references**, without requiring an instance of the component type to be created.

### 5.2. Array allocation does not call the element's constructor

```java
Person[] people = new Person[2];
System.out.println(people[0] == null); // true
```

**The code snippet is illustrative**, assuming a `Person` class has been declared. The first statement creates **an array consisting of two reference slots**, not two `Person` objects.

To have actual instances, they must be allocated separately:

```java
people[0] = new Person("Lan");
people[1] = new Person("Minh");
```

Creating `Person[]` does not automatically trigger class initialization of `Person` merely because that class is the component type. The class may be loaded/resolved by the runtime, but **class loading is different from class initialization**, and instantiating an actual `Person` is a scenario that triggers initialization when needed.

### 5.3. The component type of `anewarray` can be an array type

Important example:

```java
int[][] rows = new int[2][];
```

Here, the **direct component type** of the outer array is **`int[]`**, which is a **reference type**. Therefore, the compiler typically uses `anewarray` referencing the constant-pool array class descriptor `[I`:

```text
iconst_2
anewarray #k   // class "[I" i.e. int[]
```

Result:

```text
rows --> [null, null]         // outer array length = 2
           |     |
           X     X            // no row arrays yet
```

Having the source type `int[][]` **does not mean `multianewarray` is automatically used**; the expression only allocates one array level.

If later:

```java
rows[0] = new int[] {1, 2};
rows[1] = new int[] {3};
```

then two new `int[]` arrays are created separately, typically with `newarray int`. This approach also creates **jagged arrays** with different row lengths.

## 6. `multianewarray` — multidimensional allocation

### 6.1. Instruction format

```text
multianewarray indexbyte1 indexbyte2 dimensions
```

- Opcode byte: **`0xc5`**.
- The next two bytes point to a constant-pool entry describing the **array type**, e.g., `[[I`.
- The `dimensions` byte specifies the **number of dimensions to be allocated** in the instruction.
- The operand stack must contain the exact **number of `int` values corresponding to `dimensions`**.
- On success, the JVM allocates the outer array and the subarrays of the requested dimensions, then pushes a **reference to the outer array** onto the stack.

Validity condition: `dimensions` is at least **1** and must not exceed the **number of dimensions/rank of the array type**. `multianewarray` also supports allocating a subset of dimensions, without requiring the allocated dimensions to equal the total rank.

### 6.2. Two-dimensional primitive: `new int[2][3]`

```java
int[][] matrix = new int[2][3];
```

Typical bytecode:

```text
iconst_2
iconst_3
multianewarray #k, 2  // class "[[I"
```

Operand stack simulation, top on the right:

```text
[]        → [2]       → [2, 3]
                            |
                            | multianewarray [[I, dimensions=2
                            v
                       [ref(matrix)]
```

Object graph:

```text
matrix --> [ref row 0, ref row 1]        outer int[][] length 2
                |           |
                v           v
             [0,0,0]     [0,0,0]         each int[] length 3
```

There are **three array objects**: one outer array and two subarrays. This is an **array of arrays**, not a guarantee of a single contiguous block of primitive memory like a native matrix.

### 6.3. Two-dimensional reference: `new String[2][3]`

```java
String[][] labels = new String[2][3];
```

The expression typically uses `multianewarray` with array type descriptor `[[Ljava/lang/String;` and `dimensions = 2`. After allocation:

- The outer array has length 2, with elements pointing to two allocated `String[]` arrays.
- Each `String[]` row has length 3.
- All six `String` reference slots are initially **null**.
- **Six `String` instances are not automatically created**.

### 6.4. Allocating only part of the total rank

```java
int[][][] cube = new int[2][3][];
```

The **rank is 3**, but the **number of allocated dimensions is 2**. `javac` may use:

```text
iconst_2
iconst_3
multianewarray #k, 2  // class "[[[I"
```

Initial object graph:

```text
cube  (length 2)
  ├── cube[0] (length 3) : [null, null, null]
  └── cube[1] (length 3) : [null, null, null]
```

**Three array objects** have been created, but **no `int[]` objects** at the final level yet. The slots referencing the deeper rows remain null. Later, one can do:

```java
cube[0][0] = new int[] {7, 8};
```

Key point: the `dimensions` = 2 operand **does not say that the outer array has length 2**. It says **two dimensions are allocated**. The lengths 2 and 3 in the example are already on the **operand stack**.

### 6.5. Not limited to primitives

`multianewarray` works with multidimensional array types having either primitive or reference components:

```java
int[][] a = new int[2][3];
Object[][] b = new Object[2][3];
String[][][] c = new String[2][3][4];
```

In the reference-component case, the innermost elements are initially null; in the primitive-component case, they hold the primitive default value.

## 7. Exact comparison table

| Property | `new` | `newarray` | `anewarray` | `multianewarray` |
| --- | --- | --- | --- | --- |
| Opcode byte | `0xbb` | `0xbc` | `0xbd` | `0xc5` |
| Operand bytes | 2-byte constant-pool index | 1-byte `atype` | 2-byte constant-pool index | 2-byte index + 1-byte dimensions |
| Input on operand stack | No array length | One `int` count | One `int` count | `dimensions` `int` count values |
| Allocated object | Class instance | Primitive array | Reference array | Outer array and specified array levels |
| Value pushed onto stack | Uninitialized reference per verifier | Array reference | Array reference | Outer-array reference |
| Initial element values | Default fields, then constructor completes | Primitive defaults | Null references | Defaults and references to subarrays |
| Needs `<init>` for result? | Under the normal instance creation model: yes | No | No | No |

**Note on the word “uninitialized”:** after `new`, the object is already allocated. The `uninitialized reference` state is a **bytecode verification** state to ensure the constructor is called validly; it does not mean the object has no memory at all.

**Note on dimensions:** `newarray` creates a single-level primitive array; `anewarray` creates a single level whose component is a reference, so that level can still have type `int[][]`. `multianewarray` can allocate multiple levels in a single instruction.

## 8. Complete Java 17+ example with deterministic stdout

Create a file **`AllocationDemo.java`** with the content:

```java
import java.util.Arrays;

public final class AllocationDemo {
    static final class Item {
        static {
            System.out.println("Item class initialized");
        }

        final String name;

        Item(String name) {
            this.name = name;
            System.out.println("Item constructor: " + name);
        }
    }

    public static void main(String[] args) {
        Item[] slots = new Item[2];
        System.out.println("item-array first is null: " + (slots[0] == null));

        Item item = new Item("Lan");
        slots[0] = item;
        System.out.println("instance: " + slots[0].name);

        int[] counts = new int[3];
        counts[1] = 7;
        System.out.println("primitive array: " + Arrays.toString(counts));

        String[] labels = new String[2];
        labels[0] = "JVM";
        System.out.println("reference array: " + Arrays.toString(labels));

        int[][] matrix = new int[2][3];
        matrix[1][2] = 9;
        System.out.println("matrix: " + Arrays.deepToString(matrix));

        int[][] jagged = new int[2][];
        jagged[0] = new int[] {4};
        System.out.println("partial second row null: " + (jagged[1] == null));
        System.out.println("jagged first row: " + Arrays.toString(jagged[0]));

        System.out.println("int component: "
                + counts.getClass().getComponentType().getName());

        try {
            int[] impossible = new int[-1];
            System.out.println(impossible.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negative length rejected");
        }
    }
}
```

Compile and run with **JDK 17 or higher**:

```bash
javac --release 17 AllocationDemo.java
java AllocationDemo
```

**Exact stdout in a normal run:**

```text
item-array first is null: true
Item class initialized
Item constructor: Lan
instance: Lan
primitive array: [0, 7, 0]
reference array: [JVM, null]
matrix: [[0, 0, 0], [0, 0, 9]]
partial second row null: true
jagged first row: [4]
int component: int
negative length rejected
```

### Output analysis

**`item-array first is null: true`:** `new Item[2]` creates an array object, does not create an `Item` instance, and does not automatically trigger class initialization of `Item` because it is only the array's component type.

**`Item class initialized`:** appears when the program first actively uses `Item` via the expression `new Item("Lan")`, causing the class to be initialized as needed.

**`Item constructor: Lan`:** appears when the instance constructor runs. This shows the difference between **class initialization** and **instance initialization**.

**`primitive array: [0, 7, 0]`:** `newarray int` creates three zero elements before the code assigns `counts[1] = 7`.

**`reference array: [JVM, null]`:** `anewarray` creates reference slots that are initially null. Then `labels[0]` points to a `String`.

**`matrix: [[0, 0, 0], [0, 0, 9]]`:** the outer array and two row arrays were allocated; the code modifies a single primitive element.

**`partial second row null: true`:** `new int[2][]` has not allocated the second row array.

**`int component: int`:** `getComponentType()` reflects the actual primitive component type of `counts`; `counts` itself is still a reference to an array object.

**`negative length rejected`:** a negative length is valid in a numeric expression but invalid for array allocation, so `NegativeArraySizeException` is thrown and caught in the program.

## 9. Using `javap` to view actual opcodes

After compiling:

```bash
javap -c -p AllocationDemo
```

The `-c` flag prints method bytecode, and `-p` additionally shows non-public members. To view the constant pool, descriptors, and `Code` attribute:

```bash
javap -v -p AllocationDemo
```

Look in `main` for the corresponding instruction groups:

| Source code | Opcode to look for |
| --- | --- |
| `new Item[2]` | `anewarray`, component type `AllocationDemo$Item` |
| `new Item("Lan")` | `new`, `dup`, `invokespecial <init>` |
| `new int[3]` | `newarray int` |
| `new String[2]` | `anewarray java/lang/String` |
| `new int[2][3]` | `multianewarray [[I, 2` |
| `new int[2][]` | `anewarray [I` |
| `new int[] {4}` | `newarray int` then store element |
| `new int[-1]` | push `-1` then `newarray int` |

The forms in the table are **expected instruction/data names**, not verbatim excerpts with fixed constant-pool indices or bytecode offsets. The specific compiler/JDK determines those indices and instruction layouts.

### Reading `new` and `anewarray` output

Illustrative example:

```text
new        #k    // class AllocationDemo$Item
anewarray  #m    // class java/lang/String
```

`#k` and `#m` are **constant-pool indexes**. The two operand bytes after the opcode are used to access class information, not a heap address or element count.

In both cases, the operand bytes do not directly store the array length; `new` does not need a count, whereas `anewarray` takes the count from the operand stack.

### Reading `multianewarray` output

```text
multianewarray #k, 2  // class "[[I"
```

- `#k` identifies the array type `int[][]`, descriptor `[[I`.
- The number **2** after the comma indicates the **number of dimensions to allocate**, not the array length.
- The two actual sizes **2** and **3** of `new int[2][3]` were already pushed onto the operand stack before the instruction.
- The instruction returns **a reference to the outer array**.

If the source code is `new int[4][7]`, the `dimensions` operand is still **2**, even though the actual lengths are 4 and 7.

## 10. Reading descriptors to understand component type and rank

A JVM descriptor is a way of encoding a **type**, not including array lengths:

| Java type | JVM descriptor |
| --- | --- |
| `int` | `I` |
| `boolean` | `Z` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `int[][]` | `[[I` |
| `int[][][]` | `[[[I` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |

Each `[` character adds one dimension. However, the **direct component type** of `int[][]` is `int[]`, not `int`. Therefore:

```java
int[][] rows = new int[2][];
```

can use `anewarray` because the outer array's elements have the reference type `int[]`. Conversely:

```java
int[] row = new int[2];
```

uses `newarray` because the direct elements are primitive `int`.

Distinguish:

- **Rank:** total number of dimensions of an array type.
- **Allocated dimensions:** number of dimensions actually allocated in a given execution.
- **Component type:** the **direct** element type of an array object.
- **Length:** the actual number of elements of an array object at runtime.

For example, `new int[2][3][]` has rank 3, two allocated dimensions, outer array length 2, and the direct component type of the outer array is `int[][]`.

## 11. Arrays of length 0, negative length, and excessive size

### Length 0 still creates a valid array object

```java
int[] a = new int[0];
String[] b = new String[0];
int[][] c = new int[0][5];
```

The references `a`, `b`, and `c` are all **non-null** when allocation succeeds. `c` is an outer array of length 0; there are no rows to access `c[0]`. A zero-length array is different from a null reference.

### Negative length: `NegativeArraySizeException`

```java
// Syntactically valid expression, will throw at runtime:
int[] bad = new int[-1];
```

`newarray`, `anewarray`, and `multianewarray` check the array counts according to each opcode's semantics. If a size to be allocated is negative, the program cannot succeed in allocating and return a “half-finished” array as a result.

### Memory is not infinite

`OutOfMemoryError` can occur even when all counts are non-negative, due to heap limits, the number of objects to create, array size limits, or system resources.

`new int[10000][10000]` may require one outer array and **10,000 inner arrays**, not just a single array. Sparse structures can use `new int[10000][]` to allocate rows when truly needed, but must handle rows that do not yet have objects and are null.

Do not assume a single universal array-length limit across all JVMs based solely on the representable range of `int`; the implementation and runtime configuration also affect it.

## 12. Array read/write opcodes after allocation

Allocation opcodes only create objects. Reading/writing elements uses other instructions:

| Array/operation | Opcode |
| --- | --- |
| `int[]` element read/write | `iaload` / `iastore` |
| `long[]` element read/write | `laload` / `lastore` |
| `double[]` element read/write | `daload` / `dastore` |
| Reference array element read/write | `aaload` / `aastore` |
| Get array length | `arraylength` |

Consider:

```java
int[][] rows = new int[2][];
rows[0] = new int[] {5};
rows[0][0] = 7;
```

- `rows[0] = ...` writes an **`int[]` reference** into the outer array, so it uses the **`aastore`** group.
- `rows[0][0] = 7` writes a **primitive int** into the inner array, so it uses the **`iastore`** group.

Even an array of primitive arrays is a reference array at the outer level. Do not decide the store opcode based solely on the deepest primitive.

For reference arrays with covariance:

```java
Object[] values = new String[1];
// values[0] = Integer.valueOf(7); // compiles, but ArrayStoreException
```

At runtime, elements of `String[]` can only hold references compatible with `String` (or null), so writing through an `Object[]` variable does not bypass the runtime type check.

## 13. Why do object arrays not automatically initialize the component class?

We need to distinguish:

1. **Class loading/resolution:** the runtime knows the information/definition of the type to be used.
2. **Class initialization:** running the class's static initializers when active use requires it.
3. **Instance initialization:** the constructor creates the object's state after `new`.
4. **Array initialization:** setting default values for the array object's slots.

`new Widget[2]` only requests **an array with component type `Widget`**, not initializing two `Widget`s. It does not automatically call constructors and does not automatically trigger class initialization of `Widget` merely because of the component type.

`new Widget()` is different: it is an active use causing the class to be initialized if not already, then running the appropriate constructor.

Note: class/array resolution may cause class-loading activities or linking errors, but **knowing a type** should not be equated with **running that type's static initializer**.

## 14. Common misconceptions

1. **“If the source has `new`, bytecode only has the `new` opcode.”** False. Arrays use other opcodes.
2. **“`newarray` can create `String[]` with some `atype`.”** False. `atype` is only for the eight primitive types.
3. **“`anewarray` pre-creates all element objects.”** False. Reference elements are initially null.
4. **“`new int[2][]` creates two empty rows.”** False. It creates the outer array; the rows are null.
5. **“`multianewarray #k, 2` means the outer array has length 2.”** False. The trailing 2 is the allocated dimensions.
6. **“`int[][]` is always created with `multianewarray`.”** False. `new int[2][]` typically uses `anewarray`.
7. **“`new` already calls the constructor, `invokespecial` is redundant.”** False. The two instructions serve two separate phases.
8. **“A primitive array is not an object.”** False. `int[]` is a reference type and an array object.
9. **“`new int[0]` is equivalent to null.”** False. It is an array object with `length` 0.
10. **“Array counts reside inside the operand bytes of `anewarray`.”** False. The count is on the operand stack; the operand bytes of `anewarray` contain a constant-pool index.
11. **“`multianewarray` allocates all dimensions in the descriptor.”** False. It only allocates the specified `dimensions`.
12. **“A 2D array is always a single contiguous block of primitives.”** False in the Java model: it is an array of arrays.
13. **“An array of an interface is invalid.”** False. `Runnable[]` is valid even though `Runnable` cannot be directly instantiated.
14. **“An allocated object means the entire instance initialization succeeded.”** False. The constructor can throw an exception.
15. **“An error during array allocation must be `VerifyError`.”** False. Negative size or out-of-memory are separate runtime errors; the verifier handles class-file and type constraints.

## 15. Self-check exercises with answers

**Question 1.** Which opcode does `new long[4]` use, and how many objects does it create?

**Answer:** `newarray` with `atype = T_LONG (11)`; creates **one `long[]` array** consisting of four `0L` elements.

**Question 2.** Is `new Runnable[3]` valid when `Runnable` is an interface?

**Answer:** Yes. `anewarray` creates an array object with three null reference slots; it does not create `Runnable` instances.

**Question 3.** How many array objects does `new int[2][3]` typically create?

**Answer:** One outer array and two `int[]` rows, totaling **three objects**, typically via `multianewarray` with `dimensions=2`.

**Question 4.** How many objects does `new int[2][]` create initially?

**Answer:** **One outer array**, with two reference elements equal to null; the compiler typically uses `anewarray` with component type `int[]`.

**Question 5.** `multianewarray [[I, 2`: what is the trailing 2?

**Answer:** The number of dimensions to allocate. The actual sizes are on the operand stack.

**Question 6.** Does `new Person[5]` run the `Person()` constructor five times?

**Answer:** No. The array initially contains five null references.

**Question 7.** Why is `new Person("Lan")` usually accompanied by `dup` and `invokespecial <init>`?

**Answer:** `new` allocates; `dup` keeps the reference as the expression result; `invokespecial` calls the constructor, consuming the receiver/arguments according to the rules.

**Question 8.** Is `new String[0]` equal to null?

**Answer:** No. It is a valid array object with `length == 0`.

**Question 9.** Does assigning `rows[0] = new int[3]` on `int[][] rows` use a primitive store or a reference store on the outer array?

**Answer:** **Reference store `aastore`**, because the direct element of `int[][]` is `int[]`.

**Question 10.** For `new int[2][3][]`, which dimensions already have arrays?

**Answer:** The first two dimensions. The references meant to point to `int[]` at the final level are initially null.

**Question 11.** Is `new int[-1]` a compile-time or runtime error?

**Answer:** The expression is well-typed; runtime throws `NegativeArraySizeException` during allocation.

**Question 12.** Why does `new int[10000][10000]` risk exhausting the heap quickly?

**Answer:** Because there are very many elements and many subarray objects, not just one object; total memory can exceed JVM limits.

## 16. Summary in one diagram

```text
new
  operand bytes: constant-pool index for class
  stack input  : no array length
  stack output : reference to instance that has not completed <init>
  example      : new Person("Lan")

newarray
  operand bytes: atype = one of the eight primitive types
  stack input  : one int count
  stack output : reference to primitive array
  example      : new int[3]

anewarray
  operand bytes: constant-pool index for component reference type
  stack input  : one int count
  stack output : reference to reference array
  example      : new String[3], new int[2][]

multianewarray
  operand bytes: constant-pool array type index + dimensions
  stack input  : dimensions int count values
  stack output : reference to outer array
  example      : new int[2][3], new String[2][3], new int[2][3][]
```

**Remember:** The `new` keyword in source code is one idea; the opcodes `new`, `newarray`, `anewarray`, and `multianewarray` express **different forms of allocation** at the JVM level. When reading `javap`, ask: **where is the type specified, where are the sizes taken from, how many array objects are created, and what are the initial elements?**

### Official specifications

- [JVMS 6.5 — new](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.new): class instance allocation.
- [JVMS 6.5 — newarray](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.newarray): `atype` and primitive arrays.
- [JVMS 6.5 — anewarray](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.anewarray): reference arrays.
- [JVMS 6.5 — multianewarray](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.multianewarray): dimensions and multidimensional array allocation.
- [JVMS 4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3): notation for class, primitive, and array types.
- [JLS 10 — Arrays](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html): concepts, component types, and array elements.
- [`javap` JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): reading bytecode/constant pool.
