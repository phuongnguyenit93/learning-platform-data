# Reading `javap -c -v -s -l` to Connect Class Structure with Java Code

## 1. Why Read `javap`?

Java source code tells you the **programming intent**: class declarations, fields, methods, data types, conditions, and calls. A `.class` file tells the JVM the **binary structure and instructions to execute**. The JDK's `javap` tool helps you look from the class file back to the structures and behaviors related to the source.

Think of it as a journey:

~~~text
BytecodeTour.java
      |
      | javac -g BytecodeTour.java
      v
BytecodeTour.class
      |
      +--- header, major version, access flags, this/super_class
      +--- constant pool, fields[], methods[], attributes[]
      +--- Code: bytecode + max_stack + max_locals + exception table
      +--- debug attributes: LineNumberTable, LocalVariableTable
      |
      | javap -c -v -s -l -p BytecodeTour
      v
Readable output of bytecode, descriptors, metadata, and debug tables
      |
      v
Cross-reference back: source line -> BCI -> opcode -> constant-pool entry
~~~

**`javap` is a disassembler, not a full decompiler.** It displays information that actually exists in the class file, but it does not guarantee restoring the verbatim original source, all variable names, comments, lambda syntax, or original expressions. Constant pool indices and bytecode offsets depend on the compiler, Java version, and compilation options.

Practical objectives of this lesson:

1. Run a Java 17+ example and determine its stdout.
2. Use `-c` to connect `if`, addition, and `return` with bytecode instructions.
3. Use `-s` to understand descriptors for fields, constructors, and methods.
4. Use `-v` to read the header, constant pool, access flags, `Code`, attributes, and references like `#12`.
5. Use `-l` and `javac -g` to connect source lines and local variables with **BCI** (bytecode index).
6. Know the limitations of inferring back from a class file to source.

## 2. Four Core Options and Supporting Flags

| Option | Main Information | Question Answered |
| --- | --- | --- |
| **`-c`** | Disassembles `Code` into bytecode opcodes, offsets, operands, branch targets, and calls | “What instructions does this Java snippet lower to?” |
| **`-v`** or `-verbose` | Detailed metadata: class version, flags, constant pool, descriptors, attributes, `Code` info, stack maps… | “What does the class file actually store?” |
| **`-s`** | **JVM type descriptors** for fields and methods | “How are data types, parameters, and return types encoded?” |
| **`-l`** | `LineNumberTable` and `LocalVariableTable` **if present** | “Which source line/local variable does a BCI correspond to?” |
| `-p` or `-private` | Shows **all** members, including private ones | “Why don't private methods/fields appear by default?” |
| `-classpath` / `-cp` | Specifies where to find user classes/JARs | “Where is the compiled class being disassembled located?” |
| `--module` / `-m` | Selects the module containing the class when browsing named modules | “Which module is the class in?” |
| `--multi-release N` | Helps select the appropriate version when analyzing a multi-release JAR | “Am I reading the right class variant for Java N?” |
| `-sysinfo` | Prints file info such as path, size, date, and hash depending on the tool version | “Am I inspecting the right file?” |

Combined command used in this lesson:

~~~bash
javap -c -v -s -l -p BytecodeTour
~~~

**The options have overlapping information.** For example, `-v` can already display descriptors and debug attributes; `-s` and `-l` are still useful when you want to study each perspective separately. When using all of them at once, the output can be long and repeat some information. This does not mean the four flags produce four output files or four JVM execution stages.

Quick commands as needed:

~~~bash
javap BytecodeTour
javap -p BytecodeTour
javap -c -p BytecodeTour
javap -s -p BytecodeTour
javap -l -p BytecodeTour
javap -v -p BytecodeTour
~~~

**Note the `-l` flag:** that is a lowercase **L** (*line/local*), not the number 1 or an uppercase I. `javap` takes a **class name** already on the classpath or a path to a `.class` file. Do not run `javap BytecodeTour.java` and expect the program to compile the source; compilation is the responsibility of `javac`.

## 3. Runnable Example: One Source, Multiple Class File Perspectives

Create the file **`BytecodeTour.java`** in a new directory:

~~~java
public class BytecodeTour {
    private final String label;

    public BytecodeTour(String label) {
        this.label = label;
    }

    public int compute(int left, int right) {
        int sum = left + right;
        if (sum > 10) {
            return sum * 2;
        }
        return sum + 1;
    }

    public String message(int value) {
        return label + ":" + value;
    }

    public static void main(String[] args) {
        BytecodeTour tour = new BytecodeTour("JVM");
        int result = tour.compute(4, 8);
        System.out.println(tour.message(result));
    }
}
~~~

Compile with **JDK 17 or higher** with **full debug metadata** and run:

~~~bash
javac -g BytecodeTour.java
java BytecodeTour
~~~

**Exact stdout:**

~~~text
JVM:24
~~~

Because `compute(4,8)` has `sum = 12`, the condition `12 > 10` is true, so it returns `24`. `message(24)` produces `"JVM:24"`. The `-g` flag in `javac` enables all standard debug information, including local variable names needed for `javap -l` to display.

In the same directory, run:

~~~bash
javap -c -v -s -l -p BytecodeTour
~~~

You will see many lines; an effective way to read it is to divide it into layers: **header → constant pool → member descriptors → Code → debug tables → attributes**.

### Relationship of Source to Class File Components

| Java line/concept | Where to observe in the class file |
| --- | --- |
| `public class BytecodeTour` | `this_class`, `flags: ACC_PUBLIC, ACC_SUPER` (in common builds) |
| No `extends` written | `super_class` references `java/lang/Object` |
| `private final String label` | A `field_info` with flags `ACC_PRIVATE, ACC_FINAL` and descriptor `Ljava/lang/String;` |
| `BytecodeTour(String label)` | `method_info` with special name `<init>`, descriptor `(Ljava/lang/String;)V` |
| `int compute(int,int)` | `method_info` named `compute`, descriptor `(II)I`, `Code` has `iadd`/comparison/`ireturn` |
| `String message(int)` | `method_info` named `message`, descriptor `(I)Ljava/lang/String;` |
| `static void main(String[])` | `method_info` named `main`, descriptor `([Ljava/lang/String;)V` |
| `new BytecodeTour("JVM")` | Allocation bytecode and constructor call (`new`, `dup`, `invokespecial`) |
| `System.out.println(...)` | `getstatic` and `invokevirtual` pointing to the constant pool |
| Lines and local variables in `compute` | `LineNumberTable` / `LocalVariableTable` when debug info is present |

**Do not infer that bytecode always mirrors Java source at a “one Java statement = one opcode” ratio.** A single Java expression often requires multiple bytecodes; some constants are folded/inlined by the compiler; some lambdas, string concatenations, switches, and generic operations generate bytecode or synthetic methods that the author does not see in the source.

## 4. Reading `-c`: From Java Conditions to Operand Stack and Branches

Run:

~~~bash
javap -c -p BytecodeTour
~~~

Focus on the `compute(int,int)` method. With a modern `javac`, you will typically observe an **equivalent** sequence like this (simplified to the key instructions; offsets and branch generation may vary by compiler):

~~~text
public int compute(int, int);
  Code:
       0: iload_1
       1: iload_2
       2: iadd
       3: istore_3
       4: iload_3
       5: bipush        10
       7: if_icmple     14
      10: iload_3
      11: iconst_2
      12: imul
      13: ireturn
      14: iload_3
      15: iconst_1
      16: iadd
      17: ireturn
~~~

This is an **illustrative disassembly example for the logic**, not a guarantee that every `javac` version outputs the exact BCIs above. The important part is the source lines and opcode meanings:

- `iload_1`, `iload_2`: loads `left` and `right` from **local variable slots 1 and 2** onto the operand stack.
- `iadd`: pops two `int`s from the operand stack, computes `left + right`, pushes the result.
- `istore_3`: stores `sum` into **local slot 3**.
- `bipush 10`: pushes the integer constant 10 onto the operand stack.
- `if_icmple 14`: compares two `int`s. If `sum <= 10`, jumps to BCI 14; otherwise continues to the `sum > 10` branch.
- `iconst_2; imul; ireturn`: multiplies `sum * 2` and returns an `int` from the method.
- `iconst_1; iadd; ireturn`: the remaining branch returns `sum + 1`.

**BCI** stands for **bytecode index**: the byte offset inside a method's `Code.code[]`, not the Java line number and not a CPU instruction address. An opcode can take multiple bytes, so BCI does not necessarily increment by 1. The branch operand printed by `javap` is the **target address within the method**, not a source line number.

### Simulating the Operand Stack

At the start of `compute` (an instance method):

~~~text
Local variables:
  slot 0 : this (BytecodeTour)
  slot 1 : left = 4
  slot 2 : right = 8
  slot 3 : sum (unassigned at the start of the method)

Operand stack (abstract area):
  []                       ; before iload_1
  [4]                      ; after iload_1
  [4, 8]                   ; after iload_2
  [12]                     ; after iadd
  []                       ; after istore_3
  [12, 10]                 ; before if_icmple
~~~

If the condition “`sum <= 10`” is **false**, the VM proceeds through the multiply-by-2 instructions, and then `ireturn` returns `24`. If the condition is true, the VM jumps to the branch returning `sum + 1`. Local slots are **not** permanently tied to source-level Java variables: the compiler is allowed to reuse slots when their live ranges do not overlap.

### Constructor and Entry Method in `-c`

In the `BytecodeTour(String)` constructor, you will see a meaningful sequence:

~~~text
aload_0                  ; this
invokespecial ...        ; call Object.<init>()
aload_0                  ; this
aload_1                  ; label argument
putfield ...             ; assign this.label
return
~~~

In `main`, object creation is typically represented by:

~~~text
new ... BytecodeTour
dup
ldc ... "JVM"
invokespecial ... BytecodeTour."<init>"
~~~

`new` creates the object, `dup` keeps a copy of the reference on the operand stack for use after the constructor call, `ldc` loads a constant (here, a string), and `invokespecial` calls the constructor. These instructions help connect the meaning of `new BytecodeTour("JVM")` to the class file. Do not confuse `return` of a `void` constructor with `ireturn` of `compute` returning an `int`.

## 5. Reading `-s`: Descriptors and Differences from Java Types

Run:

~~~bash
javap -s -p BytecodeTour
~~~

Key descriptors to look for:

~~~text
private final java.lang.String label;
  descriptor: Ljava/lang/String;

public BytecodeTour(java.lang.String);
  descriptor: (Ljava/lang/String;)V

public int compute(int, int);
  descriptor: (II)I

public java.lang.String message(int);
  descriptor: (I)Ljava/lang/String;

public static void main(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)V
~~~

Each symbol is interpreted according to **JVMS `4.3`**:

| Symbol | Meaning |
| --- | --- |
| `B` / `C` / `D` / `F` | `byte` / `char` / `double` / `float` |
| `I` / `J` / `S` / `Z` | `int` / `long` / `short` / `boolean` |
| `V` | `void` — used only as a method descriptor return type |
| `Lpkg/ClassName;` | A reference type; names in the JVM use `/` |
| `[I` | Array `int[]` |
| `[Ljava/lang/String;` | Array `String[]` |
| `(II)I` | Two `int` parameters, `int` return |
| `([Ljava/lang/String;)V` | One `String[]`, `void` return |

For example, `(Ljava/lang/String;I)J` is a method taking `String` and `int`, returning `long`. The number of descriptor characters does **not** equal the number of local-variable slots: a `long`/`double` occupies two local slots in the JVM model, whereas a `reference` or `int` typically takes one slot.

### Field Descriptors vs. Method Descriptors

- A field has **one** type symbol: `Ljava/lang/String;`, `I`, `[I`.
- A method has **parentheses surrounding parameters** followed by the return descriptor: `(II)I`.
- The constructor `<init>` has a method descriptor returning `V` even though constructors do not declare a return type in source.
- `-s` gives **descriptors** with generics erased. To see generic types like `List<String>`, also read the `Signature` attribute (if present) in `-v`.

Do not treat `-s` as an option that “prints complete Java source methods”: descriptors do not tell you parameter names, code, exception logic, or comments.

## 6. Reading `-v`: Header, Constant Pool, and Attributes

Run:

~~~bash
javap -v -p BytecodeTour
~~~

### 6.1. Header/Class Identity

The top section usually has:

~~~text
Classfile .../BytecodeTour.class
  Last modified ...; size ... bytes
  SHA-256 checksum ...
  Compiled from "BytecodeTour.java"
public class BytecodeTour
  minor version: 0
  major version: ...
  flags: (...) ACC_PUBLIC, ACC_SUPER
  this_class: #...           // BytecodeTour
  super_class: #...          // java/lang/Object
  interfaces: 0, fields: 1, methods: ..., attributes: ...
~~~

Lines for path, timestamp, checksum, file size, constant-pool indices, method count, and version are **build-dependent output**. With default Java 17 `javac`, the major version is usually **61**; Java 21 defaults to **65**, Java 25 defaults to **69**. When using `javac --release 17` on a newer JDK, the class can still be major 61 because the target bytecode is lowered to Java 17.

`this_class` and `super_class` are **constant pool indices**, while flags indicate class characteristics. The field `label` also has its own flags (`ACC_PRIVATE, ACC_FINAL`); the method `compute` has `ACC_PUBLIC`. Do not confuse class-level flags with method/field-level flags.

### 6.2. Constant Pool: Connecting an Index to Its Meaning

The `Constant pool` can contain entry types such as:

| Entry Type | Content |
| --- | --- |
| `Utf8` | Class names, method names, descriptors, string literals, and name metadata |
| `Class` | Reference to a class/interface name |
| `NameAndType` | Member name paired with descriptor |
| `Fieldref` | Field reference used in bytecode |
| `Methodref` / `InterfaceMethodref` | Class/interface method reference |
| `String` / `Integer` / numeric constants | Constants that bytecode can use |
| `InvokeDynamic` | Dynamic call site; linked to a bootstrap method |
| `MethodHandle` / `MethodType` | Components describing links, bootstraps, or method handles |

A few schematic lines:

~~~text
#3  = Class              #4         // java/lang/Object
#4  = Utf8               java/lang/Object
#17 = Fieldref           #...#...   // BytecodeTour.label:Ljava/lang/String;
#21 = Methodref          #...#...   // BytecodeTour."<init>":(Ljava/lang/String;)V
#30 = Utf8               compute
#31 = Utf8               (II)I
~~~

The numbers `#3`, `#17`, `#21`… in the diagram are **not guaranteed** to match the file you generate: they only illustrate entry types. Take the **actual index** of an instruction in `javap -c` and cross-reference **that same number** in the `Constant pool` section of the `-v` output.

For example, seeing:

~~~text
... getfield  #17  // Field label:Ljava/lang/String;
~~~

Read through the chain:

1. `getfield` is an opcode that fetches an **instance field** from an object reference.
2. `#17` is the constant pool index **generated by the compiler in the file being viewed**.
3. The entry at `#17` is `Fieldref`; it links the owner class, the name `label`, and the descriptor `Ljava/lang/String;`.
4. To find which Java statement led to this opcode, turn to `LineNumberTable` and the source.

**`#17` is not a heap address, not line 17, and not local slot 17.** The same `#N` notation also appears in bootstrap methods, descriptors, and other attributes; always read the table's heading.

### 6.3. `Code` Information of a Method

In `-v`, a method with a bytecode body usually has:

~~~text
Code:
  stack=2, locals=4, args_size=3
  0: iload_1
  1: iload_2
  ...
LineNumberTable:
  ...
LocalVariableTable:
  ...
StackMapTable:
  ...
~~~

Meaning:

- `stack=2`: the method's `max_stack`, i.e., the **maximum number of operand-stack slots** that the method's bytecode needs (this illustrative `compute` example needs 2).
- `locals=4`: `max_locals` including slot 0 for `this`, slots 1–2 for `left`/`right`, and slot 3 for `sum`.
- `args_size=3`: the number of slots used for arguments in the JVM invocation frame: `this` + two `int` parameters. A static method has no `this` slot; `long` and `double` take two slots.
- `StackMapTable`: describes type frames used for **bytecode verification** at control flow points; it is **not** a Java stack trace when an application throws an exception.
- `Exception table` (if the method has exception-catching regions): defines protected ranges, target handlers, and catch types.

The numbers here depend on the chosen method, and `StackMapTable` can vary by class/compiler version. If there is no exception handling in `compute`, you do not need to look for an exception handler for no reason.

### 6.4. Distinguishing Attributes

| Attribute | Location | Purpose |
| --- | --- | --- |
| `SourceFile` | Class level | Source file name; does not contain the full source |
| `Code` | Inside appropriate `method_info` | Bytecode, `max_stack`, `max_locals`, exception table, code attributes |
| `LineNumberTable` | Inside `Code` | Maps some **BCI → source line number** |
| `LocalVariableTable` | Inside `Code` | Name, type, slot, and valid BCI range of local variables |
| `LocalVariableTypeTable` | Inside `Code` | Generic signature of local variables when present |
| `Signature` | Appropriate class/field/method | Generics information erased from JVM descriptors |
| `Exceptions` | Method | Checked-exception types declared in `throws` |
| `BootstrapMethods` | Class level | Bootstrap metadata for dynamic constants / invokedynamic |
| `StackMapTable` | Inside `Code` | Declares type-verification frames |

Not every `.class` file has every attribute. Many items are optional, depending on source, debug options, Java release, compiler, and optimizations. Analysis tools need to distinguish **missing debug metadata** from a **corrupted class file**.

## 7. Reading `-l`: Connecting BCI to Line Numbers and Local Variables

This is the step that turns bytecode into an understandable explanation for learners.

### 7.1. What Does `LineNumberTable` Tell You?

In the `compute` method, a `LineNumberTable` might express something like:

~~~text
LineNumberTable:
  line <sum declaration line>: 0
  line <if line>: 4
  line <return sum * 2 line>: 10
  line <return sum + 1 line>: 14
~~~

The `<... line>` labels here are **illustrative of the relationship**, not actual lines of `javap` output. The tool prints **integer line numbers** in `BytecodeTour.java` and the corresponding starting BCI. One Java line can generate multiple opcodes, sometimes two source lines relate to the same BCI range, and the compiler may omit some lines that need no instructions.

According to the JVMS, `LineNumberTable` is **optional** metadata. It tells debuggers/tracing which source line a BCI relates to; it itself **does not contain source code** and does not guarantee every opcode has a distinct Java line.

### 7.2. What Does `LocalVariableTable` Tell You?

When compiling with `javac -g`, you may see a descriptive section like:

~~~text
LocalVariableTable:
  Start  Length  Slot  Name   Signature
  ...    ...      0   this   LBytecodeTour;
  ...    ...      1   left   I
  ...    ...      2   right  I
  ...    ...      3   sum    I
~~~

This is also a **value schematic**, not a specific dump of Start/Length. The table should be read as follows:

- `Start` is the starting BCI of the local variable's existence range.
- `Length` is the number of bytecode units of the live range: typically the variable is valid in the interval **[Start, Start + Length)**.
- `Slot` is the index in the frame's local variables area, **not the Java line number**.
- `Name` is the local name saved by the compiler to aid debugging.
- `Signature` in this table's output is usually a **field descriptor**; for generic local variables, there may be a `LocalVariableTypeTable` to hold generic information.

For example, `slot 3` holds `sum` in `compute`. If the compiler reuses slot 3 for another local variable in a non-overlapping code region, the table may have **two entries with the same Slot but different Start/Length/Name**. There is no contradiction: local slots are storage managed by bytecode scope, not permanent source variable identifiers.

### 7.3. Why Might `-l` Not Show Local Variable Names?

The key point: debug attributes are **not mandatory** in a class file. Default `javac` often writes only partial debug metadata (e.g., source file and line numbers), while **local variable names** may not be recorded unless the appropriate option is enabled.

Compare three compilation modes (each subsequent command **overwrites BytecodeTour.class** in the same directory; do them sequentially and inspect the output right after each one):

~~~bash
javac -g:none BytecodeTour.java
javap -l -p BytecodeTour

javac -g:lines,source BytecodeTour.java
javap -l -p BytecodeTour

javac -g BytecodeTour.java
javap -l -p BytecodeTour
~~~

Expected metadata:

| Compilation | `LineNumberTable` | `LocalVariableTable` |
| --- | --- | --- |
| `javac -g:none` | Usually **absent** | Usually **absent** |
| `javac -g:lines,source` | Present when the method has corresponding code | No local-name debug table due to this option |
| `javac -g` | Present when applicable | Present for locals/parameters for which the compiler retains metadata |

Do not infer “no LocalVariableTable = method has no local variables”. The JVM still has `max_locals` and still executes `iload`/`istore`; **only the names and source-mapping ranges are stripped**. Parameter names can also be preserved via `MethodParameters` if using `javac -parameters`, somewhat independently of `LocalVariableTable`; the two attributes do not have completely identical functions.

To reset for the main lesson after the comparisons:

~~~bash
javac -g BytecodeTour.java
javap -c -v -s -l -p BytecodeTour
~~~

## 8. Combining All Four Options into a Reading Workflow

When you want to explain why the call `compute(4,8)` returns `24`, follow this exact order:

**Step 1 — identify the method from source.** `public int compute(int left, int right)` takes two `int`s and returns an `int`.

**Step 2 — use `-s` to identify the descriptor.** Find `compute` with `(II)I`. If the class has multiple overloads, the descriptor helps pick the right method, avoiding confusion with `compute(long,long)`.

**Step 3 — use `-c` to trace the operand stack.** Find `iload_1` and `iload_2`, `iadd`, `istore_3`, the comparison instructions, and the two `ireturn` branches. Test with values 4 and 8 to deduce the result 24.

**Step 4 — use `-v` to understand operands.** If there is `getfield #N`, `invokevirtual #M`, or `invokedynamic #K`, look up entries `#N`/`#M`/`#K` in the constant pool and related bootstrap attributes. Know the exact owner/name/descriptor instead of guessing from the mnemonic.

**Step 5 — use `-l` to check source mapping.** Find the BCI corresponding to the `sum`/`if`/`return` lines and the slots for `left`, `right`, `sum`. If metadata is missing, enable `-g` and recompile when you have the source and permission; do not pretend that `javap` magically resurrects variable names.

**Step 6 — separate evidence from inference.** Bytecode is evidence of the class file structure **generated by the compiler**; it does not guarantee the JVM executes each opcode with a single CPU instruction. The JVM may interpret or JIT-compile depending on the VM, but observable behaviors must conform to Java/JVMS requirements.

### Cross-Reference Diagram for an Expression

~~~text
Java Source:
    int sum = left + right;
          |
          v
Method descriptor (-s):
    compute(II)I
          |
          v
Bytecode (-c):
    iload_1 -> iload_2 -> iadd -> istore_3
          |
          v
Debug info (-l, if present):
    BCI 0 -> source line with the addition
    slots: 1=left, 2=right, 3=sum
          |
          v
Verbose (-v):
    Code { max_stack, max_locals, LineNumberTable,
           LocalVariableTable, StackMapTable, ... }
~~~

Subtle point: the expression `left + right` only operates on local ints, so the `iload` and `iadd` instructions **do not need** a constant-pool entry for each variable. Conversely, `getfield`/`invokevirtual`/`new` usually reference the constant pool because they need to know the class/field/method being accessed.

## 9. Common Opcode Patterns and Java Meaning

| Illustrative Java source | Common bytecode | Interpretation |
| --- | --- | --- |
| `int x = a + b;` | `iload`, `iadd`, `istore` | Load, add, store integers |
| `if (x > 10)` | `iload`, `bipush`, `if_icmple` | Branch on the **inverted condition** to skip the true branch |
| `return x;` in an `int` method | `iload`, `ireturn` | Return `int` to the caller |
| `new Foo()` | `new`, `dup`, `invokespecial <init>` | Allocate and initialize object |
| `obj.name` | `aload`, `getfield` | Read instance field |
| `Foo.count` | `getstatic` | Read static field |
| `obj.work()` | `invokevirtual` or appropriate invoke mechanism | Call method; dispatch depends on type and opcode |
| `Interface m = ...; m.work()` | Possibly `invokeinterface` | Call via interface reference |
| `System.out.println(x)` | `getstatic`, `invokevirtual` | Fetch `PrintStream` then call method |
| `label + ":" + value` | Possibly `invokedynamic` with `StringConcatFactory` on modern compilers | String concatenation does not necessarily build `StringBuilder` like older compilers |
| `try/catch` | `Exception table` + handlers | Describes exception ranges; don't look only at branch opcodes |
| `switch` on integers | `tableswitch` or `lookupswitch` | Branch selection by value, depending on case density |

This table describes **compilation tendencies**, not a contract that “one source construct always maps to one exact opcode sequence”. Compilers can change strategies while still producing valid classes. In particular, do not treat the absence of `StringBuilder` as a bug: since Java 9, compilers often use `invokedynamic` for string concatenation.

## 10. Extension: Generics and Bridge Methods Make Classes Differ from Source

Java source uses generics, but the JVM executes based on descriptors and, when needed, compiler-generated bridge methods. This example runs standalone on Java 17+; create the file **`BridgeDemo.java`**:

~~~java
interface Handler<T> {
    T process(T input);
}

final class TextHandler implements Handler<String> {
    @Override
    public String process(String input) {
        return input + "!";
    }
}

public class BridgeDemo {
    public static void main(String[] args) {
        Handler<String> handler = new TextHandler();
        System.out.println(handler.process("ok"));
    }
}
~~~

~~~bash
javac -g BridgeDemo.java
java BridgeDemo
javap -c -v -s -l -p TextHandler
~~~

**Program stdout:**

~~~text
ok!
~~~

Look in `TextHandler.class` for:

- The actual method declared in source, with descriptor `(Ljava/lang/String;)Ljava/lang/String;`.
- A compiler-generated **bridge method** to satisfy the type contract after generic erasure, carrying flags such as `ACC_BRIDGE` and `ACC_SYNTHETIC`; its descriptor is usually `(Ljava/lang/Object;)Ljava/lang/Object;`.
- The bridge's bytecode may `checkcast` from `Object` to `String` and then call the actual `process(String)` method.
- The `Signature` attribute stores the generic type information of `Handler<String>`, whereas JVM method descriptors use erased types.

This example illustrates why **`methods_count` and `javap -p` can show methods that do not appear directly in the source**. To understand a class file, you need to look simultaneously at `flags`, `descriptor`, `Signature`, `Code`, and inheritance/implementation relationships.

## 11. Reading Classes in Packages, JARs, and Modules

### Class Inside a Package

If the source declares `package demo;` and the class name is `demo.BytecodeTour`, compile into the `out` directory (the `out` directory must exist or be created beforehand) and use the **fully qualified class name**:

~~~bash
javac -g -d out src/demo/BytecodeTour.java
java -cp out demo.BytecodeTour
javap -c -v -s -l -p -classpath out demo.BytecodeTour
~~~

This illustrative command **assumes you have moved the example into `src/demo/BytecodeTour.java` and added `package demo;` at the top**; do not run it verbatim with the packageless `BytecodeTour.java` from section 3.

### Class Inside a JAR

~~~bash
javap -c -v -s -l -p -classpath app.jar demo.BytecodeTour
~~~

You do not need to launch the JAR to inspect a class. If the application has multiple dependent JARs, ensure the classpath you use points to the right binary to analyze. If it is a **multi-release JAR**, note that different class variants may exist for different Java versions; identify the correct entry/version and use the `--multi-release` option (when supported by the JDK) or specify the exact class file to view. Do not take the base version and conclude it is the code used at runtime if the JAR has versioned entries.

### Class Belonging to a JDK Module

~~~bash
javap -v -p --module java.base java.lang.String
~~~

Here `--module java.base` selects the module; `java.lang.String` is the class name. The output is very long and depends on the JDK version. This is an exercise in reading **a real JDK class**, and it is not mandatory to understand every detail of the source implementation.

## 12. Common Misconceptions

1. **“`javap -c` runs bytecode.”** No. It **disassembles** the class file; to run the program, use `java`.
2. **“`javap` always recovers the original Java source.”** No. Source comments, many local names, original expressions, or optimized code may no longer have enough information.
3. **“BCI 17 is source line 17.”** No. BCI is a bytecode position; you must use `LineNumberTable` to map it to a source line when metadata is present.
4. **“`#17` in `getfield #17` is local slot 17.”** No. The `#` sign denotes a **constant-pool index** in this context.
5. **“`javap -s` displays full generic signatures.”** It mainly shows erased **JVM descriptors**; additional generics information resides in `Signature`/`LocalVariableTypeTable` when recorded.
6. **“Without `LocalVariableTable`, a method has no local variables.”** False. `max_locals` and bytecode still work normally; missing debug metadata does not prevent the JVM from running.
7. **“`-v` and `-l` require a runtime with a debug agent.”** No. They read metadata from the class file; whether local/line tables exist depends on the compilation process.
8. **“`stack=2` means the VM has exactly two Java stack frames.”** False. `max_stack` is the maximum number of **operand stack slots** for **one method**.
9. **“The `invokevirtual` instruction always sees the method owner as the runtime object's class.”** Not necessarily. The constant pool stores a symbolic method reference; runtime dispatch can select a subclass implementation.
10. **“`javap` sees the exact HotSpot JIT machine code currently running.”** False. `javap` inspects **class-file bytecode**; JIT-compiled native code is a different runtime layer.
11. **“Because there is a `main` in the class, `javap` automatically calls main.”** False. `javap` reads `method_info`; it does not execute method bodies.
12. **“`javap` output is identical across all JDKs down to every index and opcode.”** False. Compiler/target version variations can change the constant pool, bytecode, and metadata while preserving application semantics.

## 13. Self-Check

**Question 1.** Which command is used to view bytecode, constant pool, descriptors, and line/local tables all at once?  
**Answer:** `javap -c -v -s -l -p ClassName`, noting that debug metadata may be missing.

**Question 2.** What do `(II)I` and `([Ljava/lang/String;)V` mean respectively?  
**Answer:** A method taking 2 `int`s and returning `int`; a method taking one `String[]` and returning `void`.

**Question 3.** In the instance method `compute(int,int)`, what does slot 0 usually hold?  
**Answer:** The `this` reference. The two `int` parameters are in slots 1/2; the local `sum` may be in slot 3.

**Question 4.** The output has `5: bipush 10` and `7: if_icmple 14`. Are 5 and 7 Java line numbers?  
**Answer:** No, those are **BCIs**. The address 14 is the branch target BCI presented by `javap`.

**Question 5.** Why doesn't `-l` show `left` and `right` even though the bytecode has `iload_1` and `iload_2`?  
**Answer:** The class may not contain `LocalVariableTable` because the compiler was not given `-g:vars` or `-g`. The slots still exist; local names may be missing.

**Question 6.** What descriptor does `-s` show for `List<String>`, and where can you see the generic type?  
**Answer:** The descriptor is usually `Ljava/util/List;` due to erasure. Look up the `Signature` attribute in `-v` if recorded by the compiler.

**Question 7.** Why might `TextHandler` have two `process` methods even though the source only writes one?  
**Answer:** The compiler generates a **synthetic bridge** to serve the generic interface method after erasure.

**Question 8.** With only `javap -c`, can you know the exact native assembly generated by the HotSpot JIT?  
**Answer:** No. `-c` shows JVM bytecode from the class file, not native machine instructions after JIT.

## 14. Authoritative References

- [Oracle JDK 25 — `javap` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): options `-c`, `-v`, `-s`, `-l`, `-p`, classpath/module, and multi-release.
- [dev.java — `javap`, the Disassembler](https://dev.java/learn/jvm/tools/core/javap/): examples and how to read disassembly in the JDK toolset.
- [JVMS Java SE 25 — Chapter 4: The class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): `ClassFile`, constant pool, descriptors, access flags, `Code`, `Signature`, `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`, and `StackMapTable`.
- [JVMS Java SE 25 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3): codes such as `I`, `J`, `L...;`, `[`, and method descriptor parentheses.
- [JVMS Java SE 25 — `4.7.3` Code](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, bytecode, exception table, and code attributes.
- [JVMS Java SE 25 — `4.7.12` LineNumberTable](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.12): mapping BCI to line numbers.
- [JVMS Java SE 25 — `4.7.13` LocalVariableTable](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.13): local slots, variable names, descriptors, and ranges.
- [Oracle JDK 25 — `javac` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): how to use `-g`, `-g:lines,vars,source`, `-g:none`, and `--release`.

**Effective study method:** Read **one method** at a time following the chain **source → descriptor (`-s`) → bytecode (`-c`) → constant pool and attributes (`-v`) → BCI, lines, and local slots (`-l`)**. Record what is actually stored in the class file, and only then infer about the Java source or how the JVM executes it.