# Constant Pool and References to Called Classes, Fields, and Methods

In Java, source code refers to a class, reads a field, or calls a method by name. After compilation, bytecode does not store fixed memory addresses of those members. Instead, the `.class` file stores **symbolic references** in the **constant pool**, and bytecode instructions point to them by index. The JVM uses this information to verify, link, and locate the corresponding member at runtime.

After this lesson, you will be able to read `Class`, `NameAndType`, `Fieldref`, `Methodref`, and `InterfaceMethodref` entries in `javap -v` output; distinguish names from descriptors; connect a bytecode instruction to its reference; and explain why binary API changes can cause `NoSuchMethodError` or `NoSuchFieldError`.

## 1. Where does the constant pool live and what is it used for?

The abbreviated structure of a class file is:

```text
ClassFile
├── magic = 0xCAFEBABE
├── minor_version, major_version
├── constant_pool_count
├── constant_pool[1 .. constant_pool_count - 1]
├── access_flags, this_class, super_class
├── interfaces[]
├── fields[]
├── methods[]                  (including the Code attribute containing bytecode)
└── attributes[]
```

- Each class/interface has its **own constant pool** in its `.class` file; this is not a shared name table for the entire application. An entry has the form `cp_info { u1 tag; u1 info[]; }`: `tag` identifies the kind, and the remainder holds data or reference indices.
- `constant_pool_count` is a `u2` value; valid indices start at **1**, not 0. `Long`/`Double` entries occupy **two index slots**, where the second slot is not an independent entry that can be referenced. Therefore, the number of usable entries is not necessarily equal to `constant_pool_count - 1`.
- Some entries are constants that can be pushed onto the operand stack (numbers, strings, class literals...); others only hold names, types, and links to classes/fields/methods. The name "constant pool" does **not** mean every entry is a `static final` value.
- Structures such as `this_class`, `super_class`, field/method declarations, and many attributes also point into the constant pool; not every entry appears in a `Code` instruction.
- The JVM creates a corresponding **run-time constant pool** when creating the class at runtime. The JVM may resolve references lazily when needed or eagerly as long as it preserves the specified behavior; do not assume that on every method call the JVM performs a linear scan over a text table.

A Java 17 file compiled with `javac --release 17` has `major version: 61`. This is the class file format version, not the number of constant pool entries.

## 2. Entry types to recognize

| Form in `javap -v` | Tag | Role |
| --- | ---: | --- |
| `Utf8` | 1 | Stores string data for names, descriptors, attribute names... (class files use *modified UTF-8*). |
| `Integer`, `Float`, `Long`, `Double` | 3, 4, 5, 6 | Constant numeric values in the class file. |
| `Class` | 7 | Points to a `Utf8` representing the internal name of a class/interface or an array type descriptor. |
| `String` | 8 | Points to a `Utf8` containing the string literal text; not the same entry type as `Utf8`. |
| `Fieldref` | 9 | Reference to a field via its owning class/interface and a `NameAndType`. |
| `Methodref` | 10 | Reference to a method belonging to a class, including constructor `<init>` calls. |
| `InterfaceMethodref` | 11 | Reference to a method declared in an interface. |
| `NameAndType` | 12 | Pair of **member name + descriptor**; by itself it does not indicate the owning class. |
| `MethodHandle`, `MethodType` | 15, 16 | Represents a field/method handle and a method type; important for lambdas and dynamic linking. |
| `Dynamic`, `InvokeDynamic` | 17, 18 | Dynamic constant / call site linked via a bootstrap method, rather than a regular `Methodref`. |
| `Module`, `Package` | 19, 20 | Module/package information used in appropriate class file structures, such as `module-info.class`. |

The core focus when reading ordinary calls is the trio **`Class` → `NameAndType` → `Fieldref/Methodref/InterfaceMethodref`**, with `Utf8` entries holding the actual text.

## 3. What is a reference composed of?

The three main reference structures share the same shape:

```text
CONSTANT_Fieldref_info / Methodref_info / InterfaceMethodref_info
    u1 tag
    u2 class_index             -> CONSTANT_Class_info
    u2 name_and_type_index     -> CONSTANT_NameAndType_info

CONSTANT_Class_info
    u1 tag = 7
    u2 name_index              -> CONSTANT_Utf8_info

CONSTANT_NameAndType_info
    u1 tag = 12
    u2 name_index              -> CONSTANT_Utf8_info
    u2 descriptor_index        -> CONSTANT_Utf8_info
```

Suppose there is a Java call `account.deposit(5)`, where class `Account` belongs to package `demo.constantpool` and the method has signature `void deposit(int amount)`. The constant pool of the **class containing the call** can be represented by the following illustrative diagram (`#...` indices are examples, not fixed `javac` output):

```text
#12 = Class       #40          // demo/constantpool/Account
#40 = Utf8        demo/constantpool/Account
#21 = NameAndType #41:#42      // deposit:(I)V
#41 = Utf8        deposit
#42 = Utf8        (I)V
#31 = Methodref   #12.#21      // demo/constantpool/Account.deposit:(I)V

Bytecode: invokevirtual #31     // Method demo/constantpool/Account.deposit:(I)V
```

Here:

1. `Methodref` specifies the **referenced class** and the **name + descriptor** of the method; it is not yet a function address in memory.
2. `Class` holds the internal name `demo/constantpool/Account`. In class file internal names, `/` separates packages, unlike `.` in Java names used by `javap`/`java`.
3. `NameAndType` distinguishes members that share the same name but have different types/signatures. For example, `deposit(I)V` and `deposit(J)V` are two methods with different descriptors.
4. A single `NameAndType` can be reused by multiple references; numeric index values depend on compilation order and the compiler. Following the chain `#31 → #12/#21 → #40/#41/#42` yields the full meaning.

For fields, the model is similar, except `NameAndType` carries a **field descriptor** instead of a **method descriptor**. For example, `Fieldref Account.balance:I` indicates a field named `balance` of type `int`. `Fieldref` can point to a field of a class **or** an interface; whereas `Methodref` points to a class and `InterfaceMethodref` points to an interface.

**Distinguishing declaration site from reference site:** `Account.class` has the `deposit` declaration in its `methods[]` table; `PoolDemo.class` has a `Methodref` when it calls `Account.deposit`. There does not have to be a corresponding `Methodref` for every declared method; the set of references depends on the actual bytecode of each class file.

## 4. Descriptors: the part most often misread

A descriptor is a string encoding **JVM types**, distinct from generic signatures and Java-syntax type names.

| Java Type | Field descriptor |
| --- | --- |
| `boolean`, `byte`, `char`, `short` | `Z`, `B`, `C`, `S` |
| `int`, `long`, `float`, `double` | `I`, `J`, `F`, `D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

A **method descriptor** has the form `(parameter_types...)return_type`. `V` is used only for the `void` return type:

| Java Declaration | Descriptor |
| --- | --- |
| `void deposit(int amount)` | `(I)V` |
| `String name()` | `()Ljava/lang/String;` |
| `long sum(int x, long y)` | `(IJ)J` |
| `static void main(String[] args)` | `([Ljava/lang/String;)V` |

Remember three things: (1) parameters are written consecutively with no commas; (2) `L...;` wraps the internal name of an object type; (3) `[` adds one array dimension. For example, `(Ljava/lang/String;[I)Z` takes a `String` and an `int[]`, and returns `boolean`.

**Overloads** require name + descriptor to distinguish calls. At the JVM level, a method's descriptor also includes the return type, though Java does not allow overloading two methods that differ only by return type. **Generics** undergo *type erasure*: `List<String>` and `List<Integer>` normally share the descriptor `Ljava/util/List;`; generic type information may be stored additionally in the `Signature` attribute without changing the field/method descriptor used in regular linking.

The special name `<init>` is an instance initialization method (constructor), with return type `V` in its descriptor; `<clinit>` is the class initialization method invoked implicitly by the JVM and is not the target of normal direct calls.

## 5. Runnable experiment with Java 17+

Create a single file `PoolDemo.java` in any working directory with the following contents. Non-`public` types are declared in the same file to keep the exercise compact:

```java
package demo.constantpool;

interface Named {
    String name();
}

final class Account implements Named {
    static int opened;
    final String owner;
    int balance;

    Account(String owner, int opening) {
        this.owner = owner;
        this.balance = opening;
        opened++;
    }

    @Override
    public String name() {
        return owner;
    }

    void deposit(int amount) {
        balance += amount;
    }

    static String label() {
        return "Account";
    }
}

public class PoolDemo {
    public static void main(String[] args) {
        Account account = new Account("Lan", 10);
        account.deposit(5);

        Named named = account;
        String line = Account.label() + " " + named.name()
                + ": " + account.balance + ", opened=" + Account.opened;
        System.out.println(line);
    }
}
```

Compile and run from the directory containing the file; the `out` directory will be created if needed:

```bash
javac --release 17 -d out PoolDemo.java
java -cp out demo.constantpool.PoolDemo
```

Exact output:

```text
Account Lan: 15, opened=1
```

Explanation: the constructor assigns `balance = 10` and increments `opened` from 0 to 1; `deposit(5)` increases `balance` to 15; the call through the `Named` variable returns `"Lan"`. Static fields are default-initialized to 0 before the first constructor runs.

Inspect the constant pool entries and bytecode using the tools included with the JDK:

```bash
javap -v -p -classpath out demo.constantpool.PoolDemo
javap -c -p -classpath out demo.constantpool.PoolDemo
javap -v -p -classpath out demo.constantpool.Account
javap -v -p -classpath out demo.constantpool.Named
```

In `PoolDemo.class`, look for the following items (actual `#n` indices depend on the compiler version):

| Trace in `javap` | Why does it appear? |
| --- | --- |
| `Class demo/constantpool/Account` and `Methodref Account."<init>":(Ljava/lang/String;I)V` | `new Account("Lan", 10)` creates the object, then invokes the constructor via `invokespecial`. |
| `Methodref Account.deposit:(I)V` | `account.deposit(5)` uses an instance method call. |
| `Methodref Account.label:()Ljava/lang/String;` | `Account.label()` is a static call. |
| `InterfaceMethodref Named.name:()Ljava/lang/String;` | `named.name()` is called through an interface type. |
| `Fieldref Account.balance:I` and `Fieldref Account.opened:I` | Reads the instance and static fields for the output string. |
| `Fieldref java/lang/System.out:Ljava/io/PrintStream;` and `Methodref java/io/PrintStream.println:(Ljava/lang/String;)V` | Prints the line to the console. |
| `InvokeDynamic ... makeConcatWithConstants ...` and `BootstrapMethods` | With standard Java 17 compilers, dynamic string concatenation is implemented via `invokedynamic` and bootstrapped from `StringConcatFactory`. |

Note that `Account.class` contains the code for the constructor, `name`, and `deposit`; you must open `PoolDemo.class` **as well** to see the references from the caller side. In `Account.class`, `opened++` typically produces a `getstatic`/`putstatic` pair and `balance += amount` produces `getfield`/`putfield`. Details such as index ordering, bytecode offsets, and string concatenation strategy can vary by compiler and options; rely on entry types, descriptors, and opcodes rather than memorizing `#n` numbers.

## 6. How does bytecode use references?

| Common Opcode | Constant-pool entry kind / meaning |
| --- | --- |
| `new`, `anewarray`, `checkcast`, `instanceof` | Points to `Class`; for example `new Account` or `checkcast Account`. |
| `getfield`, `putfield` | Points to `Fieldref`; reads/writes an instance field of an object. |
| `getstatic`, `putstatic` | Points to `Fieldref`; reads/writes a static field of a class/interface, subject to access and field-type constraints. |
| `invokevirtual` | Usually points to `Methodref` for an instance method with dynamic dispatch based on the receiver's runtime class. |
| `invokespecial` | Invokes a constructor, superclass method, or certain special calls; the appropriate reference is `Methodref` or `InterfaceMethodref` depending on the target. |
| `invokestatic` | Invokes a static method; may use `Methodref` or `InterfaceMethodref` if the target is a static method of an interface. |
| `invokeinterface` | Points to `InterfaceMethodref`, invoking a method through an interface contract with dispatch on the runtime receiver. |
| `invokedynamic` | Points to `InvokeDynamic`; links a call site via a bootstrap method, rather than carrying an owner/method pair like `Methodref`. |
| `ldc`/`ldc_w`, `ldc2_w` | Pushes a constant supported by the opcode, such as a string, class literal, or number; `ldc2_w` is used for `long`/`double`. |

Example of a conceptual bytecode sequence, **not a byte-for-byte dump**:

```text
new           #...    // Class Account
dup
ldc           #...    // String "Lan"
bipush        10
invokespecial #...    // Methodref Account.<init>:(Ljava/lang/String;I)V
astore_1
aload_1
iconst_5
invokevirtual #...    // Methodref Account.deposit:(I)V
...
invokeinterface #...  // InterfaceMethodref Named.name:()Ljava/lang/String;
...
getfield      #...    // Fieldref Account.balance:I
getstatic     #...    // Fieldref Account.opened:I
```

`new` allocates the object without running the constructor body; `dup` keeps a reference on the operand stack so that `invokespecial <init>` initializes the object and still leaves a reference for `astore_1`. The index after an opcode is a constant pool index **of the class containing that bytecode**.

A common point of confusion: `invokevirtual` and `invokeinterface` first use symbolic information for **member resolution**, and then the JVM selects the implementation matching the actual runtime class of the receiver. In contrast, `invokestatic` invokes the resolved static target; `invokespecial` has its own target-selection rules. Therefore, "having a `Methodref` to class X" does not guarantee that X's own code will execute on every virtual call.

## 7. From names in the class file to the actual target at runtime

A useful mental model is:

```text
Java source code
  -> javac emits bytecode + constant pool per class
  -> JVM loads class, checks format, and verifies bytecode
  -> linking: prepares and resolves symbolic references when appropriate
  -> instruction uses field/method; dispatches if the call kind requires it
  -> result or linkage error
```

**Loading** finds the class definition and creates its runtime representation. **Verification** checks class file and bytecode constraints. **Preparation** sets up initial state for static fields. **Resolution** turns a symbolic reference into a concrete runtime entity according to lookup rules, member kind, access control, and class loaders. **Initialization** executes `<clinit>` when triggered; it is a distinct step from merely resolving a name. The timing of resolution can be flexible depending on the JVM, but errors must be thrown according to specification rules.

- **Class reference:** an internal name such as `java/lang/String` is resolved in the context of the referencing class's class loader. Two classes with the same binary name created by two different defining class loaders can be two distinct runtime types.
- **Field reference:** the JVM locates the field by owner, name, **and descriptor**, walking the appropriate member hierarchy, and then checks access permissions. Even though bytecode says `Account.balance:I`, storage layout and the actual object are runtime concerns.
- **Method reference:** the JVM resolves by owner, name, descriptor, and lookup rules; the invocation kind determines whether virtual/interface dispatch occurs. You cannot deduce from a `Methodref` line alone which method will ultimately run if overriding is possible.
- **Initialization:** instructions like `new`, `invokestatic`, and `getstatic`/`putstatic` are typical triggers for class initialization under JVM conditions. However, reading a `static final` variable that is a **compile-time constant** may have been inlined directly by the compiler at the call site, leaving no `getstatic` for that variable in the caller's bytecode.

**Dynamic linking is not the same as JIT compilation.** Resolution determines the meaning of a reference; the JIT may optimize machine code afterward (inlining, devirtualization...), which is a separate mechanism. Also, do not equate the class-file constant pool with the **String pool** of interned `String` objects or with the `Integer` cache.

## 8. `invokedynamic` and the modern constant pool

Not every call has a direct `Methodref` to the target method. A `CONSTANT_InvokeDynamic_info` entry consists of **bootstrap_method_attr_index** (an index into the class file's `BootstrapMethods` table) and **name_and_type_index**. When linking the call site, the JVM uses the bootstrap method to obtain an appropriate `CallSite`. In the Java 17 string concatenation example, the constant pool may contain `InvokeDynamic` along with `MethodHandle` entries and bootstrap arguments referencing `java/lang/invoke/StringConcatFactory`.

Similarly, `CONSTANT_Dynamic_info` describes a **dynamic constant** computed/linked via a bootstrap method, distinct from `InvokeDynamic` which is for call sites. Lambdas may use `LambdaMetafactory`, though you should not assume every lambda or every string concatenation produces identical output across all compilers. `Module`/`Package` entries help describe modules; they do not replace `Class`/`Fieldref`/`Methodref` for ordinary Java instructions.

When you see `InvokeDynamic`, inspect together: the `InvokeDynamic` entry, its `NameAndType` (name + method descriptor), the `BootstrapMethods` attribute, the `MethodHandle`/bootstrap arguments, and the `invokedynamic` bytecode. Do not look for an "owner class" with the same structure as `Methodref` directly inside that entry.

## 9. Common pitfalls when reading or modifying bytecode

| Symptom | How to interpret / check |
| --- | --- |
| `#n` indices change on recompilation | Indices are local to each class file; compare **entry kind, name, descriptor, and opcode**, not the numbers. |
| A `Utf8` entry contains a name, but there is no `Methodref` | The name string may serve declarations or attributes; the mere presence of a name does not prove a call exists. |
| Looking for a `Fieldref` for a `static final int` constant and not finding one | Compile-time constants may be inlined via `iconst`, `bipush`, `sipush`, or `ldc`; inspect the actual bytecode. |
| Compilation succeeds, but runtime throws `NoSuchMethodError`/`NoSuchFieldError` | Usually a binary mismatch: the class loaded at runtime lacks the **name + descriptor** recorded by the caller. Check JARs/classpath, versions, and `javap` on both sides. |
| `IllegalAccessError` or `IncompatibleClassChangeError` | An API may have changed visibility or static/instance or class/interface form, making linkage invalid. |
| Class not found at runtime | Check classpath/module path, binary name, and class loader. `NoClassDefFoundError` during loading/linking differs from `ClassNotFoundException`, which is typically thrown by explicit class-loading APIs. |
| Confusing `NameAndType` with an actual method | `NameAndType` lacks an owner; trace back to the `Methodref`/`InterfaceMethodref` that references it. |
| Confusing source signatures with JVM descriptors | Generics are erased; packages use `/`; primitive types and arrays use single-character codes/`[`. |
| Assuming a reference to an interface forces the interface's default method to run | `invokeinterface` selects behavior by the runtime receiver and JVM rules; a class implementation may be invoked. |

When investigating binary errors, follow this order: identify the exact class/JAR file loaded by the runtime; run `javap -v -p` on the **calling class** to extract owner/name/descriptor; inspect the **actual loaded target class**; compare signatures and static/access/interface flags; and only then look into class loaders or the build process. Do not edit constant pool index numbers by hand to fix errors.

## 10. Self-check exercises

1. If you see `#18 = Fieldref #7.#11 // demo/constantpool/Account.balance:I`, identify the owner, field name, and type. Answer: the owner is `demo/constantpool/Account`, the name is `balance`, and the type is `int`. To verify the full reference path, inspect `#7` (`Class`) and `#11` (`NameAndType`).
2. If you change `void deposit(int)` to `void deposit(long)` and recompile only `Account.java`, will the old calling class adapt automatically? No. The old calling class still references `deposit:(I)V` and may encounter `NoSuchMethodError` when calling it. Recompile the calling class or keep a compatible method.
3. Why can `Named named = account; named.name();` produce `InterfaceMethodref Named.name:()Ljava/lang/String;`, yet at runtime execute `Account.name()`? The constant pool records the interface contract at the **call site**; the dispatch mechanism selects the concrete method of the runtime object.

## 11. Key takeaways and reference documentation

**Four sentences to remember:** (1) each `.class` file has its own constant pool; (2) a member reference is **owner + name + descriptor** linked through indices; (3) bytecode uses these indices, while the JVM resolves references at runtime and dispatches according to the instruction kind; (4) `javap -v -c -p` is the most direct tool for cross-referencing Java code, the constant pool, and bytecode.

Further reading in the **Java Virtual Machine Specification, Java SE 17**:
- §4.1 — `ClassFile` and `constant_pool_count`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1
- §4.3 — Field and method descriptors: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3
- §4.4 — Constant pool entries: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4
- §5.4.3 — Resolution: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3