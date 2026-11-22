# Using `javap` to Read Bytecode Before and After Code Insertion

In Java instrumentation, a bytecode transformation can make a program log extra information, measure execution time, invoke hooks, or alter logic. The first way to verify that **instructions were actually inserted** is to take two `.class` versions — **before** and **after** the transformation — and use the standard JDK tool **`javap`** to disassemble and compare them.

This hands-on guide uses **Java 17+**, `javap`, and the **ASM** library to produce a new `.class` file in a reproducible way. The focus is on **reading, comparing, and interpreting `javap` output**. No Java agent running inside the JVM is needed for the main example: **offline** transformation makes it easy to save two distinct class files for straightforward verification.

## 1. What Do You Need to Understand and Verify?

After this lesson, you will be able to:

1. Identify the **exact `.class` file** that `javap` is reading, avoiding confusion between the compiled version, a version inside a JAR, or an instrumented version.
2. Read **method descriptors**, JVM instructions, bytecode offsets, constant pool references, and `stack`/`locals`/`args_size` metadata.
3. Explain how inserting instructions changes the **operand stack**, `max_stack`, code length, and offsets.
4. Compare **before/after** using a bytecode example with observable behavior, while verifying that the program **still returns the correct value**.
5. Recognize the limitation of `javap`: it reads a **class file or a class provided via the classpath/module path**, and cannot automatically see bytecode that exists only in JVM memory after a Java agent transforms it at class-loading time.

> In this article, **code insertion** refers to adding **JVM instructions** into an already-compiled method. Adding `System.out.println(...)` to the **source code and recompiling** also changes the bytecode, but it does not prove that a transformer directly modified the `.class` file.

## 2. What Does `javap` Read, and What Does Its Output Mean?

`javap` is the **class file disassembler** bundled with the JDK. It displays the class structure and, with `-c`, the JVM instructions located in the `Code` attribute of each method that has a body. This tool **does not decompile back to exact Java source**; multiple high-level source constructs can produce the same bytecode patterns, and debug metadata may be stripped.

### 2.1. Options Worth Knowing

| Option | Used to View | Notes |
| --- | --- | --- |
| `-c` | Lists bytecode instructions of methods | Offsets are **byte positions**, not instruction sequence numbers |
| `-v` or `-verbose` | Class header, constant pool, detailed `Code`, `stack`, `locals`, attributes | Long output; very useful for before/after comparison |
| `-p` or `-private` | Displays `private` members as well | Useful so transformed helpers/constructors are not missed |
| `-l` | Line number and local variable tables if recorded in the class file | `LocalVariableTable` is not required to be present |
| `-s` | Descriptors in JVM format | For example `(II)I`: two `int` parameters, returns `int` |
| `-classpath` or `-cp` | Selects the search path for `.class`/JAR files | Often the key point when comparing multiple versions |
| `-sysinfo` | Path, size, timestamp, and SHA-256 of the class being read | Helps verify origin/snapshot |
| `--multi-release 17` | Selects the appropriate class version in a multi-release JAR | Used when comparing `META-INF/versions/...` entries |
| `-version` | Prints the `javap` version | Useful when machines have multiple JDKs installed |

An overview set of commands:

```bash
javap -version
javap -classpath target/classes -p -c -l demo.Calculator
javap -classpath target/classes -p -s demo.Calculator
javap -classpath target/classes -p -v demo.Calculator
javap -classpath target/classes -sysinfo demo.Calculator
```

**How to read a bytecode line**:

```text
4: iload_2
5: ireturn
```

`4` and `5` are offsets in the `code[]` bytecode array, `iload_2` reads local variable slot `2` and pushes the integer onto the operand stack, and `ireturn` pops the integer on top of the stack and terminates the method with that result. An instruction like `invokestatic` is typically 3 bytes long, so offsets **do not necessarily increment by 1**.

### 2.2. Descriptors, Constant Pool, and Frames

For the method `static int add(int a, int b)`:

- The JVM descriptor is **`(II)I`**. `I` represents the `int` type; the parentheses contain the parameters, and the trailing symbol is the return type. `V` represents `void`, `J` is `long`, and `Ljava/lang/String;` is a reference to `String`.
- `javap -v` may print `stack=2, locals=3, args_size=2` for the method body we are about to compile: the operand stack reaches a maximum of **2 units**; the local array has **3 slots** (two parameters and one temporary variable); there are two arguments counted in local slots for this static method.
- The operand stack and local array are two parts of a **frame for a single method invocation**. `iload`/`istore` move values between the two areas. `getstatic`, `invokevirtual`, and `ireturn` operate on the operand stack according to their descriptors.
- Comments such as `#7 // Method java/io/PrintStream.println:(I)V` reference the constant pool; **the `#7` index is not a fixed ID** when regenerating a class. You should compare **instruction semantics + owner/name/descriptor**, not just `#n` numbers.

`javap -l` only includes `LineNumberTable`/`LocalVariableTable` if the compiler emitted them. Do not treat missing variable names or shifted line numbers as proof of a bytecode transformation error.

## 3. A Comparison Workflow Without Version Mix-ups

```text
Original Java Source
      │ javac (Java 17 target)
      ▼
target/classes/demo/Calculator.class          ← BEFORE
      │ read ClassReader, insert JVM instructions, emit ClassWriter
      ▼
target/modified/demo/Calculator.class         ← AFTER
      │
      ├── javap -classpath target/classes  ... demo.Calculator
      └── javap -classpath target/modified ... demo.Calculator
                           │
                           ▼
             Compare opcodes + Code + metadata
                           │
                           ▼
           Run before/after to compare behavior
```

Keep the two output directories **separate** and do not overwrite `target/classes/demo/Calculator.class`. When diagnosing results, the important sequence is: **select the right class file → compare `javap` → run in practice → explain the differences**. The `javap` command does not execute the method it disassembles.

In real-world projects, you can use bytecode snapshots from a build pipeline or the output of a `ClassFileTransformer`; the key point is identifying the exact source bytes of the BEFORE and AFTER versions.

## 4. Full Hands-On Example: Inserting Logging with ASM and Reading `javap`

### 4.1. Preparing Tools and File Structure

You need **JDK 17 or later** (`javac`, `java`, `javap`) and **Apache Maven** to download ASM. This project targets **Java 17 class files** via `<maven.compiler.release>17</maven.compiler.release>`, so it runs on JDK 17+.

```text
javap-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── Calculator.java
                ├── DemoMain.java
                └── BytecodePatch.java
```

Inside the `javap-demo` directory, create the following four files.

**`pom.xml`** — declares the ASM 9.7.1 dependency and build configuration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>javap-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.ow2.asm</groupId>
            <artifactId>asm</artifactId>
            <version>9.7.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/Calculator.java`** — the method to be instrumented:

```java
package demo;

public final class Calculator {
    private Calculator() {}

    public static int add(int a, int b) {
        int sum = a + b;
        return sum;
    }
}
```

**`src/main/java/demo/DemoMain.java`** — the program that calls the method:

```java
package demo;

public final class DemoMain {
    private DemoMain() {}

    public static void main(String[] args) {
        System.out.println("result=" + Calculator.add(3, 4));
    }
}
```

Compile from the `javap-demo` directory:

```bash
mvn -q -DskipTests package
java -cp target/classes demo.DemoMain
javap -classpath target/classes -p -c -l demo.Calculator
javap -classpath target/classes -p -v demo.Calculator
```

The **exact stdout of `java -cp target/classes demo.DemoMain`**:

```text
result=7
```

In `javap -c`, the bytecode segment of **`add`** generated by `javac` in this case is:

```text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: istore_2
     4: iload_2
     5: ireturn
```

This is an **excerpt** of the `add` method, not the full `javap` stdout: the class also contains a constructor and other metadata sections.

Trace:

| Offset | Instruction | Operand stack after instruction | Key local slots |
| ---: | --- | --- | --- |
| 0 | `iload_0` | `[a]` | `0=a, 1=b, 2=unassigned` |
| 1 | `iload_1` | `[a, b]` | Unchanged |
| 2 | `iadd` | `[a+b]` | Unchanged |
| 3 | `istore_2` | `[]` | `2=a+b` |
| 4 | `iload_2` | `[a+b]` | Unchanged |
| 5 | `ireturn` | Frame terminates | Returns `a+b` |

Because two `int` operands are present together before `iadd`, **`max_stack` is 2**. There are two parameters and one temporary variable, so **`max_locals` is 3**. `javap -v` displays these as `stack=2` and `locals=3` respectively.

### 4.2. Creating a Transformer That Inserts Logging While Preserving the Result

**`src/main/java/demo/BytecodePatch.java`** — a standalone Java program run offline that **does not modify the input file**:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class BytecodePatch {
    private BytecodePatch() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: BytecodePatch <input.class> <output.class>");
        }

        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);
        ClassReader reader = new ClassReader(Files.readAllBytes(input));
        ClassWriter writer = new ClassWriter(
            ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);

        final boolean[] found = {false};
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(
                    int access, String name, String descriptor,
                    String signature, String[] exceptions) {
                MethodVisitor next = super.visitMethod(
                    access, name, descriptor, signature, exceptions);

                if (next == null || !name.equals("add")
                        || !descriptor.equals("(II)I")) {
                    return next;
                }
                found[0] = true;

                return new MethodVisitor(Opcodes.ASM9, next) {
                    @Override
                    public void visitCode() {
                        super.visitCode();

                        // System.out.println(">> add"); at method entry
                        super.visitFieldInsn(
                            Opcodes.GETSTATIC, "java/lang/System",
                            "out", "Ljava/io/PrintStream;");
                        super.visitLdcInsn(">> add");
                        super.visitMethodInsn(
                            Opcodes.INVOKEVIRTUAL, "java/io/PrintStream",
                            "println", "(Ljava/lang/String;)V", false);
                    }

                    @Override
                    public void visitInsn(int opcode) {
                        if (opcode == Opcodes.IRETURN) {
                            // Initial stack: [result:int]
                            super.visitInsn(Opcodes.DUP);
                            // Stack: [result, result]
                            super.visitFieldInsn(
                                Opcodes.GETSTATIC, "java/lang/System",
                                "out", "Ljava/io/PrintStream;");
                            // Stack: [result, result, PrintStream]
                            super.visitInsn(Opcodes.SWAP);
                            // Stack: [result, PrintStream, result]
                            super.visitMethodInsn(
                                Opcodes.INVOKEVIRTUAL,
                                "java/io/PrintStream", "println",
                                "(I)V", false);
                            // Stack: [result] for IRETURN to consume
                        }
                        super.visitInsn(opcode);
                    }
                };
            }
        };

        reader.accept(visitor, ClassReader.SKIP_FRAMES);
        if (!found[0]) {
            throw new IllegalStateException("Method add(II)I not found");
        }
        Files.createDirectories(output.toAbsolutePath().getParent());
        Files.write(output, writer.toByteArray());
    }
}
```

**Mechanics to understand before reading the output:**

- `ClassReader` emits events as it parses the `.class` structure; `ClassVisitor` visits methods; `MethodVisitor` adds instructions only when **the name `add` and descriptor `(II)I`** match. Other methods are forwarded with their original logic untouched.
- `visitCode()` inserts `System.out.println(">> add")` **at the beginning of the method body**. It uses `getstatic` to push `System.out`, `ldc` to push the string, and `invokevirtual PrintStream.println(String)` to consume those two operands.
- `visitInsn(IRETURN)` intercepts the `int` return instruction and inserts `dup`, `getstatic`, `swap`, `invokevirtual PrintStream.println(int)` **before** `ireturn`. `dup` keeps a copy of the result so `ireturn` still has an `int` to return.
- `COMPUTE_MAXS | COMPUTE_FRAMES` tells ASM to recompute stack/locals depths and stack-map frames. `SKIP_FRAMES` skips old frames while reading so ASM can rebuild them. This example only uses very simple JDK types; for complex classes, frame computation still requires appropriate type/class hierarchy resolution.
- This demonstration is **not idempotent**: running the transformer on an already-instrumented class will add the logging again. Always use the BEFORE file as input and write to a different path.

### 4.3. Writing the AFTER Version and Checking Output with `javap`

After saving all three Java files and compiling as in section 4.1, run:

```bash
mvn -q exec:java -Dexec.mainClass=demo.BytecodePatch -Dexec.args="target/classes/demo/Calculator.class target/modified/demo/Calculator.class"

javap -classpath target/modified -p -c -l demo.Calculator
javap -classpath target/modified -p -v demo.Calculator
javap -classpath target/modified -sysinfo demo.Calculator
```

`target/classes/demo/Calculator.class` **remains BEFORE**, while `target/modified/demo/Calculator.class` is **AFTER**. In the `javap -c` output, the new instruction sequences appear in `add` in this order (omitting some offsets and `#n` indices because the writer renumbers them):

```text
getstatic     java/lang/System.out:Ljava/io/PrintStream;
ldc           ">> add"
invokevirtual java/io/PrintStream.println:(Ljava/lang/String;)V

iload_0
iload_1
iadd
istore_2
iload_2

dup
getstatic     java/lang/System.out:Ljava/io/PrintStream;
swap
invokevirtual java/io/PrintStream.println:(I)V
ireturn
```

**This is a simplified opcode outline to show the sequence**, not the verbatim `javap` output. In the real output, `getstatic` and `invokevirtual` include constant-pool indices like `#12`; `ldc` has a comment `// String >> add`; and offsets shift after instruction insertion.

For this specific example, `javap -v` will show that **`locals=3` remains unchanged**, while **`stack=3` replaces `stack=2`**. The reason is that right before `swap`, the stack holds **three category 1 values**: the original result, the duplicate of the result, and `PrintStream`. This is an expected `max_stack` change introduced by the transformer.

### 4.4. Running BEFORE and AFTER to Verify Semantics

Run the **BEFORE** version:

```bash
java -cp target/classes demo.DemoMain
```

Stdout:

```text
result=7
```

Run the **AFTER** version on Linux/macOS (place the modified directory **before** the original directory on the classpath):

```bash
java -cp "target/modified:target/classes" demo.DemoMain
```

On Windows PowerShell/CMD, the classpath separator is **`;`**:

```powershell
java -cp "target/modified;target/classes" demo.DemoMain
```

The **exact stdout from `DemoMain` on the AFTER version**:

```text
>> add
7
result=7
```

These three lines prove that (1) the entry logging instruction executed, (2) the logging instruction before `ireturn` printed the exact value `7`, and (3) the caller still received `7`. When testing a production transformer, expand to multiple parameter sets, multiple return paths, exceptions, and multithreaded behavior; a single passing input is not enough to conclude that a transformer is always correct.

## 5. Systematically Reading Each Change in `javap`

For the same target method `add(II)I`, compare across these items:

| What to Inspect | BEFORE | AFTER | What to Infer |
| --- | --- | --- | --- |
| Method name and descriptor | `add(II)I` | `add(II)I` | Signature was not altered |
| Method entry code | `iload_0` | `getstatic → ldc → invokevirtual` then `iload_0` | Logging was inserted at entry |
| Sum computation region | `iload_0, iload_1, iadd, istore_2, iload_2` | Same logic, higher offsets | Addition/temporary variable unchanged |
| Right before return | `iload_2 → ireturn` | `iload_2 → dup → getstatic → swap → invokevirtual → ireturn` | Logs result while leaving one `int` |
| `max_stack` | `2` | `3` | Valid increase in stack depth |
| `max_locals` | `3` | `3` | No new local variables added |
| `args_size` | `2` | `2` | Parameter slot count unchanged |
| Constant pool | Enough for addition and constructor | Adds references for `System.out`, log string, and `println` | `#n` indices may change |
| `LineNumberTable` | Points to old offsets | Offsets may be shifted | Debug metadata must align with new code |
| Class name / major version | `demo.Calculator`, Java 17 class file | Preserves class name and target version | Did not accidentally change ABI/bytecode level |
| Runtime behavior | `result=7` | Three output lines, ending with `result=7` | Expected side effects, return value preserved |

### 5.1. Why Do Offsets Change?

`Code.code[]` is a **byte array**, not an array of Instruction objects. Some opcodes occupy one byte (such as `iadd`, `dup`, `swap`, `ireturn`), whereas `getstatic` and `invokevirtual` encode the opcode plus a constant-pool index, typically occupying **3 bytes**. `ldc` in the example typically occupies **2 bytes** when the pool index fits in `u1`; if the index is large, the writer may use `ldc_w`. Therefore, you should not hardcode final offset numbers into tests.

For before/after comparisons, prefer **opcode patterns and stack effects**. If exact offsets are needed (e.g., for branches or exception handlers), take the **actual offsets from the current output**, not from earlier comments or examples.

### 5.2. Tracing the Operand Stack at `ireturn`

Right after `iload_2`: `[result]`, with the top on the right.

```text
[ result ]                    ; after iload_2
[ result, result ]            ; dup
[ result, result, out ]       ; getstatic System.out
[ result, out, result ]       ; swap
[ result ]                    ; invokevirtual println(int)
[ ]                           ; ireturn, callee frame terminates
```

`invokevirtual println(int)` consumes `out` and the copy of `result`, returning `void` so it pushes no new value. `ireturn` uses the remaining **original** value. If `dup` were omitted, the logging call would consume the result, leaving `ireturn` without a valid operand and causing the JVM verifier to reject the class.

This transformation is specific to **`IRETURN`** (`int` values). `LRETURN`/`DRETURN` require appropriate handling for category 2 values (e.g., `dup2` with a suitable stack layout), `ARETURN` requires a logger descriptor taking a reference, and the `RETURN` opcode of a `void` method has no return value to duplicate. `ATHROW` is an abrupt completion path and requires separate handling design.

## 6. Techniques for Diffing Output and Detecting Wrong Classpaths

For large output files, create **two `javap` snapshots** and diff them:

```bash
javap -classpath target/classes  -p -c -v demo.Calculator > before.javap.txt
javap -classpath target/modified -p -c -v demo.Calculator > after.javap.txt
diff -u before.javap.txt after.javap.txt
```

In PowerShell, you can export both files and compare them:

```powershell
javap -classpath target/classes -p -c -v demo.Calculator > before.javap.txt
javap -classpath target/modified -p -c -v demo.Calculator > after.javap.txt
Compare-Object (Get-Content before.javap.txt) (Get-Content after.javap.txt)
```

Raw diff tools will also flag changed constant-pool indices, SHA hashes, sizes, and offsets. When evaluating correctness, group differences by **signature → new instructions → stack effects → branches/handlers → attributes**. Do not treat every index/offset change as an error.

**Verifying you are looking at the right class:** run two `-sysinfo` commands with the two classpaths. For two classes with different bytes, the size and SHA-256 will normally differ; the path in `-sysinfo` helps catch mispointed paths. If BEFORE and AFTER outputs are identical, check in order: the transformer output path, classpath ordering, exact class name selection, and whether a build step overwrote the output file. The directory containing AFTER must come **before** BEFORE in the runtime classpath when running the transformed version.

**A few notes regarding classpath and modules:**

- For JARs, specify the JAR path in `-classpath`, e.g., `javap -classpath target/app.jar -c -p demo.Calculator`; the class must have an entry matching its package.
- For modular programs, select the right `--module-path` / `--module` to locate the module containing the class; do not infer from classpath alone.
- For multi-release JARs, use `--multi-release` to select the right class file for the version being compared, and check the `javap` JDK version in use.
- If multiple JDKs coexist, `javac` producing a newer class version than the running `javap` can cause unexpected results. Check `java -version`, `javac -version`, and `javap -version`; the Maven target in this example is Java 17.
- Java bytecode generated by different compilers or different optimization/debug flags can produce different bytecode (more/fewer locals, variable names, offsets, synthetic methods); always compare builds produced under the **same input conditions**.

## 7. Runtime Insertion with a Java Agent: A Crucial Limitation of `javap`

In the example above, ASM writes to **`target/modified/demo/Calculator.class`**, so `javap` can read the AFTER version. With a Java agent using `Instrumentation.addTransformer` and `ClassFileTransformer.transform`, the transformation may exist only **during class loading or retransformation inside the JVM**. The `target/classes/demo/Calculator.class` file on disk **does not change on its own**.

```text
   classfileBuffer (input bytes inside transformer)
                │
                ▼
       ClassFileTransformer.transform(...)
                │
                ├─ returns modifiedBytes → JVM defines/retransforms class
                │
                └─ when debugging, write modifiedBytes → snapshot/demo/Calculator.class
                                              │
                                              ▼
                                javap -classpath snapshot -c -v demo.Calculator
```

Therefore, **`javap` run outside the JVM cannot automatically read the contents of a class transformed in memory by an agent**. If you need to compare an agent's AFTER version, capture the **actual bytes returned by the transformer**, save them under a package-matching path or put them into a snapshot JAR, and then run `javap` on the snapshot. With retransformation, the input bytes may not be the previously instrumented version; clearly record which point in time and transformation pass each snapshot belongs to.

The following **snippet inside `transform` (not a standalone program)** illustrates the idea of dumping bytes to disk; it assumes `modifiedBytes` is the computed byte array and the target class has already been filtered:

```java
// Inside ClassFileTransformer code, only for the selected class:
Path dump = Path.of("snapshots/after/demo/Calculator.class");
Files.createDirectories(dump.getParent());
Files.write(dump, modifiedBytes);
return modifiedBytes;
```

In a real agent, do not dump all classes indiscriminately to the same filename: the same binary class name can be loaded by multiple `ClassLoader`s, undergo multiple transformation passes, or be generated by another module. Include the loader/pass in the snapshot name and ensure file writing does not cause blocking I/O or unhandled exceptions inside the transformer.

## 8. Technical Checklist When Bytecode Has Branches, Exceptions, or Constructors

A transformer beyond a simple example may **work on one execution path and break on another**. When reading `javap -v` for a complex transformation, check:

1. **Descriptors and operand stack types:** `invoke*` instructions must consume the right receiver/arguments, and the result must match the expected type. Return opcodes must match the return type.
2. **Branches and loops:** `if*`, `goto`, `tableswitch`, and `lookupswitch` use offset-based branch targets. When inserting instructions, branch offsets and switch padding can change; use the writer to recompute them.
3. **Exception table:** each entry has `start_pc`, `end_pc`, `handler_pc`, `catch_type`. Inserting instructions before or inside a protected region can alter the exception-catching range or execution order.
4. **`StackMapTable`:** the verifier requires consistent type states at corresponding control-flow points. `COMPUTE_FRAMES` helps recompute them but does not guarantee semantic correctness for every transformer, especially when ASM must resolve a common superclass across a different class loader environment.
5. **`LineNumberTable` and `LocalVariableTable`:** offsets can shift; preserve/adjust debug metadata while remembering that these tables may be absent and the class will still be valid.
6. **`max_stack` and `max_locals`:** `COMPUTE_MAXS` computes the limits, but cannot fix broken stack logic. Adding new temporary variables may require new local slots; two slots for `long`/`double`.
7. **Constructor `<init>`:** the `this` object is not fully initialized before the superclass or sibling constructor call; do not arbitrarily operate on that reference at entry.
8. **Side effects of inserted code:** a logger can throw exceptions, cause re-entrancy, alter side-effect ordering, increase latency, or cause deadlocks. A transformation that passes verification can still break the application.
9. **Verification errors:** `VerifyError`, `ClassFormatError`, `NoClassDefFoundError`, and `UnsupportedClassVersionError` must be distinguished; `javap` shows the bytes but **does not prove** the class will be accepted by the JVM under all configurations. Running the application and tests is a necessary follow-up step.

The concrete example in section 4 only inserts into a static method with no branches or handlers, making stack reasoning straightforward and the result clearly observable.

## 9. Common Errors and How to Fix Them

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| No logging seen in `javap` AFTER | Reading BEFORE by mistake or wrong classpath | Check `-sysinfo` path; point `-classpath` to `target/modified` |
| `javap` shows new opcodes but runtime shows no log | JVM loads BEFORE due to classpath order, another JAR, or another class loader | Put AFTER first; check loaded class source and classpath |
| `javap -c` only shows public methods | Target member is private or package-private | Use `-p` |
| Variable name `sum` not visible | Missing `LocalVariableTable`/debug info | Compile with `javac -g` or inspect `iload_2`/`istore_2`; do not assume the variable is gone |
| Diff shows many different `#n` values | Constant pool was reorganized/regenerated | Compare symbol owner/name/descriptor instead of indices |
| Offsets increase unevenly | Variable-length instructions, `ldc_w`, `tableswitch` padding | Rely on actual opcodes/targets in `javap` |
| `VerifyError` right after transformation | Wrong stack type, frame, branch target, or return | Trace the stack, inspect `StackMapTable`, run verifier and tests |
| Logged result is right but caller receives wrong value | Return value not preserved or operand altered | Trace `dup`/`swap` and `println` descriptor |
| `-v` reports unexpected `stack`/`locals` | Transformer added stack/locals or compiler changed | Calculate stack along execution paths, inspect opcodes/descriptors |
| `NoSuchMethodError` when running patch tool | Wrong ASM/plugin version loaded | Check dependency tree and ASM version on classpath |
| Running patch multiple times duplicates logs | Offline transformation is not idempotent | Always start from original BEFORE; manage snapshots |
| Assuming `javap` sees agent runtime changes | Agent only modifies bytes inside the JVM | Dump the bytes actually returned by the transformer, then run `javap` |

## 10. Advanced Practice and Self-Check Questions

**Exercise 1.** Add two `System.out.println` calls at the beginning and end of a `void` method: which opcode-matching logic should replace `IRETURN`?

**Answer:** `RETURN`. There is no value on the stack to `dup`; if logging at every exit point, you must also consider exceptions/`ATHROW` and handlers.

**Exercise 2.** For `static long total(long x)`, why can't you duplicate the result with `dup` before `lreturn`?

**Answer:** `long` is category 2, occupying two stack units. `dup` only applies to category 1 values; in this case, `dup2` can be used with the proper stack shape and logger descriptor `(J)V`.

**Exercise 3.** After inserting `getstatic; ldc; invokevirtual` at method entry, why do the offsets of `iload`/`ireturn` increase while `locals` stays the same?

**Answer:** The code gained instruction bytes, but no new local variables were allocated. Those logging instructions use the operand stack.

**Exercise 4.** Does `javap -classpath target/classes ...` necessarily see transformations applied at runtime by `-javaagent`?

**Answer:** No. `javap` reads bytes from the path you provide; to inspect the transformed version, you must have a snapshot of the corresponding bytes.

**Exercise 5.** Two `javap` outputs show `#17` and `#21` for the same `println:(I)V` call. Does this automatically indicate a behavioral change?

**Answer:** No. A constant pool index is its position within a specific class file; what matters here is the target method and descriptor of the call instruction.

### Self-Acceptance Checklist for the Example

- [ ] `mvn -q -DskipTests package` succeeds on JDK 17+.
- [ ] `javap` BEFORE contains `iload_0, iload_1, iadd, istore_2, iload_2, ireturn` in `add`.
- [ ] The bytecode transformer generates `target/modified/demo/Calculator.class` without overwriting BEFORE.
- [ ] `javap` AFTER contains entry logging and result logging in the right positions; `add(II)I` retains its name/descriptor.
- [ ] `javap -v` shows `stack` changing from **2 → 3**, while `locals` remains **3** in method `add`.
- [ ] Running BEFORE prints `result=7`; running AFTER prints the three lines `>> add`, `7`, `result=7`.
- [ ] Able to trace the operand stack through `dup`, `getstatic`, `swap`, `println(int)`, and `ireturn` without guessing.
- [ ] Verified the correct classpath and understood the limitation of `javap` for runtime Java agents.

## References

1. Oracle JDK 17, **The `javap` Command** — syntax and options `-c`/`-l`/`-p`/`-v`/`-s`/`-sysinfo`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
2. Java Virtual Machine Specification, **Frames (`2.6)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6
3. Java Virtual Machine Specification, **Code attribute (`4.7.3), StackMapTable (`4.7.4)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3
4. Java Virtual Machine Specification, **Instructions (`6)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
5. ASM Javadoc, **ClassReader, ClassWriter, MethodVisitor**: https://asm.ow2.io/javadoc/
6. ASM, **Developer Guide**: https://asm.ow2.io/developer-guide.html
