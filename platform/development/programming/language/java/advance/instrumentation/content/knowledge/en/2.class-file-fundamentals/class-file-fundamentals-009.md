# Line number, local variable metadata, and limits of mapping bytecode to source code

When inspecting a `.class` file with `javap`, we often see lines such as `LineNumberTable`, `LocalVariableTable`, or `MethodParameters` alongside instructions like `iload`, `invokevirtual`, and `return`. These tables help debuggers, stack traces, and instrumentation tools **correlate executable code with source code**, but they are **not a copy of the source code** and do not establish an exact one-to-one mapping between Java and bytecode.

This lesson focuses on three practical questions:

1. Which Java line does a **bytecode index (BCI)** correspond to, and when can it not be determined?
2. What name/type does a **local-variable slot** have over a bytecode range, and does that metadata tell us the value currently stored?
3. Why do instrumentation, compilers, optimizations, or stripping debug information prevent a tool from reconstructing the original Java code intact?

## 1. The big picture: from source to class file structure

```text
DebugMetadataDemo.java
       |
       | javac
       v
DebugMetadataDemo.class
  ClassFile
  ├─ constant_pool
  ├─ fields[]
  ├─ methods[]
  │    ├─ method_info (name, descriptor, flags, ...)
  │    │    ├─ Code
  │    │    │    ├─ bytecode[] (each instruction starts at a BCI)
  │    │    │    ├─ exception_table
  │    │    │    ├─ LineNumberTable       [optional]
  │    │    │    ├─ LocalVariableTable    [optional]
  │    │    │    ├─ LocalVariableTypeTable[optional]
  │    │    │    └─ StackMapTable         [when format requires]
  │    │    └─ MethodParameters          [optional, belongs to method_info]
  │    └─ ...
  └─ attributes[]
       ├─ SourceFile                    [optional]
       └─ SourceDebugExtension          [optional]
```

The attributes above **differ in location and purpose**. `LineNumberTable` and the two local-variable tables are metadata of the `Code` attribute belonging to a specific method. `SourceFile` and `SourceDebugExtension` live at the class level. `MethodParameters` lives at the `method_info` level, independent of `Code` and the local-variable tables.

A `native` or `abstract` method has no `Code` attribute and therefore none of `Code`'s sub-tables. A class file can **contain no debug metadata** and its bytecode will still execute properly, provided the class structure/logic is valid.

| Attribute | What information does it contain? | What is it used for? | What does it **not** guarantee? |
|---|---|---|---|
| `SourceFile` | Source file name, e.g., `DebugMetadataDemo.java` | Hints the source file for debuggers/stack traces | Does not store the absolute path or file contents |
| `SourceDebugExtension` | Extended data attached by a compiler/tool, which may contain a source map | Mapping for generated code or code from another language if the tool understands the format | Not every Java class has it; SMAP is not present by default |
| `LineNumberTable` | Pairs of `start_pc → line_number` | Locates source lines at bytecode positions | Does not give columns, expressions, original source order, or a one-to-one mapping |
| `LocalVariableTable` | BCI range, name, descriptor, and slot of local variables | Displays variable names/types within debug scope | Does not contain runtime variable values; does not necessarily contain every variable |
| `LocalVariableTypeTable` | Generic signature of some local variables | Displays `List<String>` instead of just `List` | Does not restore generics at runtime or alter type erasure |
| `MethodParameters` | Formal parameter metadata of a method/constructor | Serves reflection, e.g., `Parameter.getName()` | Does not describe local variables inside the body |

## 2. `LineNumberTable`: BCI ↔ source line

### 2.1. What is BCI?

A **Bytecode index** is a **byte offset** from the start of the `code[]` array of **a single method**—not the sequential instruction number in source, not a CPU machine address, and not a Java line number. Opcodes can have different lengths, so incrementing the BCI by one does not necessarily move to a new instruction.

For example, `javap -c` displays:

```text
  0: iload_0
  1: iload_1
  2: iadd
  3: istore_2
  4: iload_2
  5: ireturn
```

The numbers `0`–`5` are bytecode positions of the specific method. If a tool later inserts instructions, the offsets of subsequent instructions may change; an offset is not a durable identity of a source expression.

### 2.2. Structure and meaning of each entry

According to the JVM Specification, an entry in `LineNumberTable` has:

```text
start_pc     = starting offset of the code section associated with a source line
line_number  = corresponding line number in the source file
```

Suppose the source has:

```java
public static int add(int left, int right) {
    int total = left + right; // line 3, if the class declaration is on line 1
    return total;             // line 4
}
```

A typical `javac` build might produce:

```text
LineNumberTable:
  line 3: 0
  line 4: 4
```

This means bytecode starting from position `0` begins the section corresponding to line 3, and starting from `4` begins the section corresponding to line 4. It is **not** that `line 3` occupies only a single opcode, nor does every instruction have its own entry. When a debugger selects a line for a BCI, it must interpret these markers and the tool's rules; do not assume a perfect mapping according to Java syntax.

### 2.3. Easily confused limitations

- **One line can generate multiple instructions:** `int total = left + right;` leads to loading two variables, adding them, and storing the result. Those BCIs can still belong to the same line.
- **One line can appear at multiple bytecode positions:** loops, conditionals, compound statements, and how the compiler lays out code can produce multiple code segments associated with the same line.
- **One expression can span multiple lines:** choosing where to place markers is a compiler decision and does not reflect every token or column in the file.
- **The compiler can add code without dedicated source:** bridge/synthetic methods, lambdas, enum/record scaffolding, desugaring, and compiler-generated helpers do not necessarily have a separate Java line for each instruction.
- **No guarantee the table exists:** `LineNumberTable` is optional metadata; `javac -g:none` can strip this table without changing method behavior.
- **No file path from the table:** it must be combined with `SourceFile` or information outside the class file to locate the file; the file name alone is not enough to confirm the right source version.
- **Does not determine original Java order or structure:** multiple equivalent source expressions can be reconstructed from the same bytecode.

Some debugger APIs return a “no line information” message when the class file lacks sufficient data. Even when line info is present, stepping through source in a debugger can look like “jumping” across lines because the compiler merges or splits code.

## 3. `LocalVariableTable`: names and scopes of local variables

Bytecode instructions read/write **slots** in the stack frame's local-variable array, such as `iload_0` or `istore_2`. Bytecode **does not need Java names** like `left`, `right`, or `total`: those names usually exist only in debug metadata.

### 3.1. Each entry has five fields

```text
start_pc          // starting bytecode offset of the scope
length            // length of the scope in bytecode bytes
name_index        // variable name in the constant pool
descriptor_index  // JVM type descriptor, e.g., I or Ljava/lang/String;
index             // slot in the frame's local-variable array
```

The valid range is **[start_pc, start_pc + length)**: inclusive of the start, exclusive of the end. For example:

```text
LocalVariableTable:
  Start  Length  Slot  Name   Signature
      0       6     0  left   I
      0       6     1  right  I
      4       2     2  total  I
```

This is a **typical illustrative** output from the simple `add` method, which may vary by compiler/version/optimization:

- At BCI `0`, slot `0` is labeled `left`, and slot `1` is labeled `right`.
- The variable `total` only has an entry starting at BCI `4`. At BCI `2`, **you must not infer** that `total` can already be treated as an existing source variable.
- `I` is the JVM field descriptor for `int`; `Ljava/lang/String;` is an example descriptor for a `String` reference.
- The table **does not store the number `5` or any actual variable value**. Values exist only in the frame at runtime or are inferred via bytecode simulation, not in `LocalVariableTable`.

### 3.2. A slot does not mean a fixed source variable

- For **instance methods**, slot `0` normally holds `this`; subsequent parameters start after it. For **static methods**, there is no implicit `this`, so the first parameter can be at slot `0`.
- `long` and `double` consume **two consecutive slots**; all other types normally use one slot. Therefore, slot indices do not match source parameter order when two-slot types are present.
- The compiler can **reuse slots** for two different source variables with non-overlapping live ranges. Two entries can share the same `index` while having different `start_pc/length` and names.
- One name can appear in multiple entries across different scopes. Conversely, a variable may be elided or its scope shortened/split due to code generation.
- `max_locals` in `Code` is the required size of the slot array at execution time, **not** the number of rows in `LocalVariableTable`.
- When metadata is missing, `iload_2` still executes normally; the debugger is simply less able to tell which source variable slot `2` corresponds to.

**Proper reading rule:** you must consider **method + current BCI + slot + valid range** together before attributing a local name to a value. Do not read `Slot 2 = total` in isolation and apply it to every BCI and every execution.

### 3.3. `LocalVariableTypeTable` and generic types

`LocalVariableTable` uses JVM descriptors, which are subject to **type erasure**. If the source has:

```java
java.util.List<String> names = java.util.List.of("An", "Binh");
```

Type data can be represented at two levels:

```text
LocalVariableTable:
  Name = names
  Descriptor = Ljava/util/List;

LocalVariableTypeTable:
  Name = names
  Signature = Ljava/util/List<Ljava/lang/String;>;
```

`LocalVariableTypeTable` has scope/slot information similar to the regular local-variable table, but uses a **generic signature** instead of the descriptor with erased type parameters. This table is only useful when the compiler emits the relevant generic information and has no effect in forcing the JVM to preserve “`List<String>`” separately from “`List<Integer>`” at runtime.

Do not confuse `LocalVariableTypeTable` with the `Signature` attribute of the class, field, or method itself; they apply at different levels.

## 4. `SourceFile`, `SourceDebugExtension`, and `MethodParameters`

### 4.1. `SourceFile` is a name, not source code

A class file compiled from `DebugMetadataDemo.java` may contain:

```text
SourceFile: "DebugMetadataDemo.java"
```

This helps stack traces display in the form `DebugMetadataDemo.java:12` when line data is present. However, that attribute **does not store file contents**, Git location, absolute path, or commit. Multiple class files can declare the same `SourceFile`. If artifact A is running while opening the source of artifact B, line numbers may be “well-formatted” yet point to the wrong lines.

### 4.2. `SourceDebugExtension` serves extended source mapping

Tools that generate Java/bytecode from templates or other languages **may** attach additional information such as multi-level source maps, for example according to SMAP/JSR 45. A reading tool must understand the internal format; the JVM does not automatically turn extended metadata into a copy of the source code. When this attribute is absent, a second source file must not be inferred.

### 4.3. `MethodParameters` is completely different from `LocalVariableTable`

`MethodParameters` is metadata on `method_info` about the **formal parameters** of a method/constructor, including names (if any) and related flags. With `javac`:

- `-parameters` requests emitting metadata so Java Reflection can read parameter names from `Executable.getParameters()`.
- `-g` requests full debug info, including local-variable information, but **does not replace** the role of `-parameters` for reflection.
- `-g:none -parameters` can still retain `MethodParameters`, even without line/source/local-variable debug tables.
- `-g:lines,vars,source` specifies the types of debug info; by default `javac` usually generates **line number** and **source file**, not full local-variable information.

Therefore, a framework that wants to obtain formal parameter names via reflection needs to check `Parameter.isNamePresent()`; names in `LocalVariableTable` cannot be treated as a guaranteed source for Java Reflection.

## 5. Java 17+ experiment: compile, inspect bytecode, and observe missing metadata

Create a file named **`DebugMetadataDemo.java`** (with no `package` declaration) with the full contents:

```java
public final class DebugMetadataDemo {
    public static int add(int left, int right) {
        int total = left + right;
        return total;
    }

    public static void main(String[] args) throws Exception {
        System.out.println(add(2, 3));
        var method = DebugMetadataDemo.class.getMethod(
                "add", int.class, int.class);
        var first = method.getParameters()[0];
        System.out.println(first.getName() + ":" + first.isNamePresent());
    }
}
```

The program uses standard Java Reflection and requires no external libraries. `throws Exception` is only an example to handle that `getMethod` could throw a checked exception if the name/method were changed; with the file above, the `add` method exists and is `public static`.

### Run A — full debug metadata **and** Reflection parameter names

Run in the directory containing the file (JDK 17+ with `javac`, `java`, `javap` available):

```shell
javac -g -parameters DebugMetadataDemo.java
java DebugMetadataDemo
javap -c -l -v -p DebugMetadataDemo
```

**Exact stdout of the `java DebugMetadataDemo` command:**

```text
5
left:true
```

In the very long output of `javap`, find `public static int add(int, int)`. The following sections are an **illustrative excerpt** from typical `javac`, not the entire output:

```text
Code:
   0: iload_0
   1: iload_1
   2: iadd
   3: istore_2
   4: iload_2
   5: ireturn
LineNumberTable:
  line 3: 0
  line 4: 4
LocalVariableTable:
  Start  Length  Slot  Name   Signature
      0       6     0  left   I
      0       6     1  right  I
      4       2     2  total  I
MethodParameters:
  Name   Flags
  left
  right
```

The BCI numbers and ranges in the table above illustrate how to read them and may differ if the source/compiler changes. `MethodParameters` is a method attribute so it is not necessarily printed immediately below `LocalVariableTable` in actual output. `javap -c` displays instructions, `-l` displays line/variable tables, `-v` adds class file/attribute details, and `-p` displays non-public members as well.

### Run B — strip debug metadata, **keep** Reflection parameter names

Recompile the **same file**, overwriting the old `.class` in the experiment directory:

```shell
javac -g:none -parameters DebugMetadataDemo.java
java DebugMetadataDemo
javap -c -l -v -p DebugMetadataDemo
```

The program's stdout is still:

```text
5
left:true
```

Although `LineNumberTable`, `LocalVariableTable`, and `SourceFile` from `javac` are gone, `MethodParameters` is still present thanks to `-parameters`; therefore Reflection continues to see the name `left`. The `add` call still returns `5`: debug metadata is not a condition for executing addition.

### Run C — strip both debug metadata and parameter name metadata

```shell
javac -g:none DebugMetadataDemo.java
java DebugMetadataDemo
javap -c -l -v -p DebugMetadataDemo
```

**Exact stdout of the program:**

```text
5
arg0:false
```

At this point `Parameter.getName()` uses the synthesized name `arg0` when no real name is present, and `isNamePresent()` returns `false`. This is a clear example that **no source names ≠ no runnable bytecode**.

**Note on running:** the three `javac` invocations successively replace `DebugMetadataDemo.class` in the experiment directory itself. If using a build tool or another classpath, make sure `java`/`javap` are reading **the exact `.class` just generated**, to avoid wrong conclusions from reading the wrong artifact.

### Side experiment — seeing the limits of line numbers when an exception occurs

Replace `add` in the same file with:

```java
public static int add(int left, int right) {
    return left / right;
}
```

To trigger an intentional error, change the call in `main` to `add(2, 0)` (this code is a **side-experiment edit**, not applied simultaneously with the `5` stdout above). When running the `-g` build, the stack trace typically looks like:

```text
Exception in thread "main" java.lang.ArithmeticException: / by zero
    at DebugMetadataDemo.add(DebugMetadataDemo.java:<line>)
    at DebugMetadataDemo.main(DebugMetadataDemo.java:<line>)
```

The `<line>` notation here is an illustrative placeholder; the actual number depends on the line numbers after you edit the source. When recompiled with `-g:none`, the trace may display `Unknown Source`. The invalid division still throws the same exception type; what changes is **the ability to locate source**, not the semantics of `idiv`.

## 6. Mapping can be right at the line level while still wrong about “Java statements”

Suppose a method contains:

```java
int x = read();
int y = normalize(x) + validate(x);
return y;
```

A compiler can place one or more line markers for the bytecode of each line, but **cannot fully infer backward** that there are two calls `normalize` and `validate` in the second expression from `LineNumberTable` alone. To understand expressions, a tool must also analyze opcodes, the operand stack, control flow, and the constant pool; even then, source variable names or the original syntactic form may no longer exist.

Common reasons for information loss:

1. **Asymmetric transformations:** multiple source constructs produce equivalent bytecode. `for` can be represented like `while`; parentheses, comments, whitespace, and variable names can be lost.
2. **Compiler-generated additional code:** lambdas via `invokedynamic`, bridge methods for generics/overrides, synthetic accessors in some targets/compilers, resource/exception handling, and other constructs produce code that does not correspond one-to-one with a standalone source statement.
3. **Optimizations and transformations:** javac/bytecode transformers/JIT can merge, split, move, or eliminate code. **JIT machine code** is also a different layer from BCI; source mapping in a class file is not directly a native address.
4. **Line info only has line resolution:** setting breakpoints at two expressions on the same line may not be distinguishable using `LineNumberTable` alone.
5. **Slots are reused:** looking only at the `iload_1` opcode does not prove slot `1` always carries a specific Java name/type at every BCI.
6. **Artifact and source version mismatch:** a source checkout at a different commit or a class loader loading a different JAR causes line numbers to point to the wrong source snippet.
7. **Generic info is only a signature:** `LocalVariableTypeTable` does not restore actual runtime values/types or the identity of every object in a collection.

**Technical conclusion of this section:** a class file is usually sufficient for the JVM to execute and for the verifier to check type safety; source-debug metadata helps label some positions, but **does not guarantee reconstructing the exact AST, variable names, comments, expressions, and original file**.

## 7. Implications for instrumentation: preserving mappings when inserting bytecode

An agent might insert a probe before a service call:

```text
Before:
  BCI 0  ... read parameters
  BCI 4  ... call service
  BCI 7  ... return

After inserting probe:
  BCI 0  ... probe before service
  BCI 5  ... read parameters
  BCI 9  ... call service
  BCI 12 ... return
```

This is an **illustrative diagram**, not specific `javap` output. If the old bytecode's `start_pc` table is kept unchanged while code offsets have shifted, debuggers/stack traces may display mismatched lines or the class file may have invalid metadata. Transformation tools need to manage the old–new BCI correlation and variable live ranges.

When designing instrumentation:

- **Attach probes to stable semantics** (class/method name + descriptor + available source info) rather than treating the initial BCI as an immutable identifier.
- **Only pick lines from real metadata.** If `LineNumberTable` is missing, report “unknown line” instead of fabricating a line number based on opcodes.
- **Shift/update ranges** `start_pc` and `length` of `LocalVariableTable`/`LocalVariableTypeTable` when inserting/removing instructions affects positions/scopes.
- **Preserve or intentionally design attribution for probes:** new bytecode may not represent a new source line; a probe before/in the middle of a method should not mislead users into thinking that statement existed in source.
- **Do not manually edit each table independently:** branch targets, exception handler ranges, and `StackMapTable` have other constraints; use a class-file transformation library that supports updating offsets/frames and verify the result.
- **Distinguish `StackMapTable` from debug tables:** `StackMapTable` serves type verification, whereas `LineNumberTable`/`LocalVariableTable` serve debugging tools; missing debug info usually still runs, but corrupting verification frames can cause `VerifyError`.
- **Identify the exact class loader and class version:** if multiple class loaders have different versions of `com.example.Service`, metadata from one version does not accurately apply to another.
- **Record provenance:** store build hash/commit, class loader name, class-file hash or artifact version, and source lookup strategy so production investigations do not use the wrong source.

If the goal is measuring per-method latency, line numbers are not necessarily needed. But if a product displays “processing time of line 42” or “value of variable `total` at line 42”, the tool must recognize **missing data**, **variable scope**, **transformed bytecode**, and the limited resolution of line mapping.

## 8. Diagnostic checklist when a debugger or stack trace points to the wrong line

| Symptom | What to check | Correct interpretation |
|---|---|---|
| Stack trace says `Unknown Source` | Are `SourceFile`/`LineNumberTable` present in the exact running class? | Insufficient metadata to show file/line; does not prove the code didn't run |
| `javap` shows `iload_2` but variable `total` is not visible | Is there a `LocalVariableTable`, and is the current BCI within the entry's scope? | Variable name is absent or out of scope; the slot still exists |
| Reflection returns `arg0` | Was it compiled with `-parameters`; what is `isNamePresent()`? | `MethodParameters` lacks formal names; `-g` is not guaranteed to fix it |
| Generic variable shows `java.util.List` | Is there a `LocalVariableTypeTable` with a generic signature? | Descriptor erased type args; generic metadata may be missing |
| Debugger “jumps” lines | Inspect `LineNumberTable` and the method's bytecode, compiler-generated instructions | Each line does not correspond to exactly one instruction |
| Instrumentation shifts stack trace lines | Were the new bytecode and line/scope tables updated? | Metadata may still be describing old offsets |
| Syntactically valid line but different source content | Compare JAR/class bytes against source version/build | Reading the wrong source version or class loader |
| Line numbers exist but variables cannot be debugged | Check `LocalVariableTable` independently of `LineNumberTable` | The two types of metadata are configured independently |

**Workflow for reading a real instrumentation issue:**

1. Pin down the identity **class + method descriptor + defining class loader + artifact/build**.
2. Obtain the exact class bytes used at the stage being investigated; distinguish bytecode on disk from bytecode emitted by a transformer.
3. Run `javap -c -l -v -p` on a controlled artifact to inspect BCIs, `LineNumberTable`, local scopes, and related attributes. If bytecode is processed at runtime, dump an authorized copy of the bytecode to cross-check instead of assuming the build file is what the JVM is running.
4. If local names are needed, look up `LocalVariableTable` by **exact BCI and slot**, rather than inferring from Reflection parameters or current source.
5. Check whether mappings were lost during compilation/obfuscation/instrumentation; if absent, report only the level of conclusion that the metadata actually supports.

## 9. Misconceptions to avoid

- **“Each Java line corresponds to one bytecode index.”** False: the line table stores markers; a line can have multiple opcodes and can appear at multiple BCIs.
- **“`LineNumberTable` contains source code and file name.”** False: it only contains BCI/line pairs; the file name is separate metadata and the source file must be fetched externally.
- **“`LocalVariableTable` contains variable values.”** False: it contains name, type descriptor, slot, and applicable range; values live in the frame at runtime.
- **“Slot 0 is always `this`.”** False for static methods; slot 0 is used for the first parameter, and numbering also depends on data type sizes.
- **“With `-g`, Java Reflection knows parameter names.”** Not guaranteed: use `-parameters`/`MethodParameters` and check `isNamePresent()`.
- **“`LocalVariableTypeTable` disables type erasure.”** False: it is generic metadata for tools and does not change runtime semantics.
- **“Missing `-g` makes bytecode lose logic.”** False: typically only debug info is missing, while the code still executes.
- **“Instrumenting code can keep all BCIs unchanged.”** Must not be assumed: inserting/removing instructions can shift offsets and variable scopes, and related metadata must be reprocessed.
- **“A stack trace pointing to `File.java:42` definitely matches the source I have open.”** False: you need to cross-check artifact/version/class loader.
- **“From `javap` you can reconstruct the exact Java source.”** False: debug tables are partial information; decompilers infer structure and cannot recover every expression, name/comment/whitespace.

## 10. Self-check questions

1. **Why can the same Java line appear multiple times in `LineNumberTable`?** Because multiple bytecode locations/branches/loops or compiler decisions can map to the same source line; the mapping is not required to be one-to-one.
2. **In `LocalVariableTable`, does `start_pc=4`, `length=2` apply at BCI `6`?** No. The range is `[4, 6)`; BCI `6` is outside it.
3. **Is `iload_1` enough to conclude slot `1` is named `count`?** No. You must know the method, BCI, and a valid metadata entry; the name may be absent or the slot may have been reused.
4. **Why can `-g:none -parameters` still cause reflection to print `left:true`?** Because `MethodParameters` from `-parameters` is independent of the debug attributes from `-g`.
5. **What happens if an agent inserts 5 bytes without updating line/scope metadata?** Debug offsets may no longer match the new bytecode; debugging results may be wrong and the class file may become invalid under related constraints.
6. **Can you rely on `SourceFile` to identify a Git commit?** No. It is only the source name recorded in the class; you must also use build/artifact/provenance information.
7. **Which metadata helps a debugger display `List<String>` for a local variable?** `LocalVariableTypeTable` when the compiler has recorded the corresponding signature; `LocalVariableTable` only gives the erased descriptor.

## Official references for cross-checking

- [Java SE 21 JVM Specification — Chapter 4, Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): ``4.7.10–4.7.14` for `SourceFile`, `SourceDebugExtension`, `LineNumberTable`, `LocalVariableTable`, and `LocalVariableTypeTable`; `4.7.24` for `MethodParameters`.
- [JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-g`, `-g:lines,vars,source`, `-g:none`, `-parameters`.
- [JDK 21 — javap command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): `-c`, `-l`, `-v`, `-p`.
- [Java SE 21 — java.lang.reflect.Parameter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): `getName()` and `isNamePresent()`.

**Key takeaway:** `LineNumberTable` only links **bytecode positions to lines**; `LocalVariableTable` links **slots and BCI ranges to names/descriptors**; `LocalVariableTypeTable` can supplement **generic signatures**; `MethodParameters` serves **formal parameter names via reflection**. All of them provide clues for observation tools, not a complete copy of the Java source code.