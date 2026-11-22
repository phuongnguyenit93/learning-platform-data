# Inspecting Line Numbers, Local Variables, and Parameter Names in Java Class Files

## Learning Objectives

After this lesson, you can:

1. Distinguish **source line debug info**, **local variable names and scopes**, and **method/constructor parameter name metadata** in `.class` files.
2. Use `javac -g`, `-g:lines`, `-g:vars`, `-g:source`, `-g:none`, and `-parameters` for the right purposes.
3. Verify with `javap -l`, `javap -v`, `javap -c`, and `java`, instead of merely trusting flags were applied.
4. Recognize `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`, `SourceFile`, and `MethodParameters`, while understanding **not every attribute appears in every file**.
5. Explain why Java Reflection can know parameter counts/types yet return `arg0`, `arg1` without `-parameters`, even when the class has `LocalVariableTable`.
6. Handle differences between info used by debuggers/stack traces, metadata read via Reflection, generic signatures, annotations, compiler optimizations, and transformed class files.
7. Design a reproducible build process and verify the actual artifact, rather than relying on source or IDE settings instead of the running class file.

This lesson belongs to **validation of Java compilation outputs**. Examples use JDK 17+ and run from the terminal without frameworks or IDEs.

## 1. What Information Actually Resides in a .class File?

Java source contains things programmers care about: file names, lines, variables, parameter names, comments, expressions. The compiler turns source into **bytecode and metadata**; not every source detail is needed for the JVM to run the program.

Consider the source:

~~~java
public static String describe(String label, int count) {
    int doubled = count * 2;
    return label + ":" + doubled;
}
~~~

This is an **illustrative method**, not yet a standalone class. When compiling, the JVM needs to know the method descriptor, parameter types, and order; it does not strictly need to know how the programmer named the variable `doubled` or parameter `label`.

Therefore, distinguish:

| Information | Common Class-File Attribute | Use |
| --- | --- | --- |
| Source file name | `SourceFile` | Supports file names in diagnostics/stack traces |
| Map bytecode offset → source line | `LineNumberTable` | Debuggers, stack traces, line breakpoints |
| Local variables, parameters, names, and effective bytecode range | `LocalVariableTable` | Debuggers and binary analysis |
| Generic signature of local variables | `LocalVariableTypeTable` when present | Generic info for debuggers to display richer types |
| Parameter names stored for reflection | `MethodParameters` | `java.lang.reflect.Parameter` and some frameworks |
| Method descriptor | Method structure in class file | JVM knows **types and order** of parameters even without names |
| Generic method/class signature | `Signature` when needed | Generic info; not synonymous with debug local names |
| Annotations on parameters | Runtime-visible/invisible parameter annotation attributes depending on annotation | Separate from parameter names and local variable tables |

Attributes may be absent depending on compiler options, declaration kinds, code structure, target release, and post-compile binary tools. Do not conclude “the compiler got it wrong” just because an attribute is missing from a method that does not need it.

### 1.1 Code Lines and Bytecode Do Not Have a One-to-One Relationship

One line of Java can produce multiple bytecode instructions. Conversely, the compiler can emit bytecode supporting operations where source has no single clear matching line.

`LineNumberTable` does not hold all Java text; it only records **start_pc → line_number** pairs for bytecode regions. It is usually enough for the JVM to describe which line an error occurred on, yet does not allow reconstructing full source or exact original columns/characters.

### 1.2 Local Variable Names Are Not Inside Descriptors

In the JVM, local variable slots can be referenced by index, e.g., `iload_2`. The name `doubled` is helpful for debuggers, yet bytecode can execute without knowing that name. Variable name info exists only if the compiler or another tool writes/retains the appropriate attribute.

### 1.3 Parameter Names for Reflection Follow a Different Metadata Path

`MethodParameters` can store parameter names such as `label` and `count` in the declaration. Java Reflection uses this metadata, rather than **automatically reading names from `LocalVariableTable`**. That is why `-g` and `-parameters` solve two different needs.

## 2. Important Compilation Options

| `javac` Option | Meaning | Info Commonly Present |
| --- | --- | --- |
| Without specifying `-g` | Compiler usually writes line and source file name by default | `LineNumberTable`, `SourceFile` |
| `-g` | Requests generating **all debug info** supported by the compiler | Lines, source, local variable names/scopes |
| `-g:lines` | Line debug info only | `LineNumberTable` |
| `-g:vars` | Local variable debug info only | `LocalVariableTable` and related metadata when needed |
| `-g:source` | Source file debug info only | `SourceFile` |
| `-g:lines,vars,source` | Explicitly specifies all three groups | Lines, variables, source file |
| `-g:none` | Emits no debug info controlled by `-g` | Do not expect line/var/source debug tables |
| `-parameters` | Stores **parameter names of methods and constructors** | `MethodParameters` when applicable |

**Key points to remember:**

- `-g` is not synonymous with `-parameters`.
- `-parameters` does not automatically enable full `LineNumberTable` or `LocalVariableTable`.
- `-g:none -parameters` is an intentional combination: no debug tables, yet parameter name metadata is present.
- `-g:vars` does not by itself guarantee `Parameter.isNamePresent() == true`.
- `--release 17` controls language level, platform APIs, and class-file target; it **does not replace** debug/parameter metadata flags.

Options and defaults can depend on the compiler implementation. For the commands in this lesson, `javac` is the compiler bundled with JDK 17+.

### 2.1 Does `-g` Store Runtime Values of Variables?

No. `LocalVariableTable` contains metadata such as **names, types, and live scopes corresponding to bytecode regions**, not runtime values at each point in execution. Values only exist while the program runs, on stack frames/heap per the JVM model and runtime optimizations.

A debugger can leverage metadata to show names/types and attempt to read values currently present at a breakpoint. However, if a variable has gone out of scope, been optimized out, or the frame changed, the value may no longer be observable.

### 2.2 Does `-parameters` Turn Java into a Language Supporting Named Arguments?

No. Java does not allow calling methods by parameter name like:

~~~java
// This is INVALID Java syntax:
describe(label: "job", count: 3);
~~~

The snippet above only illustrates **invalid** syntax; do not put it into a compiled project.

`-parameters` serves metadata: reflection, dependency injection tools, web binding, serialization, and some frameworks can utilize parameter names. It does not alter method call syntax, bytecode signatures, or how Java overload resolution works.

## 3. Preparing a Runnable Java 17+ Example

Create a new directory, for example:

~~~text
classfile-metadata-demo/
├── DebugInfoDemo.java
└── out/
    ├── default/
    ├── debug/
    ├── vars/
    ├── params/
    ├── all/
    └── none/
~~~

Only one Java source file is needed; output directories are separated to **avoid mixing class files from different compilation runs**.

Check tools:

~~~bash
javac -version
java -version
javap -version
~~~

If wanting to observe Java 17 compatibility on a newer JDK, use `--release 17` in commands. If `javac` reports release 17 is unsupported, check the active JDK.

### 3.1 Creating Output Directories

**Linux/macOS Bash/Zsh:**

~~~bash
mkdir -p out/default out/debug out/vars out/params out/all out/none
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/default, out/debug, out/vars, out/params, out/all, out/none | Out-Null
~~~

From here, all commands run at the root directory containing `DebugInfoDemo.java`.

### 3.2 Complete Source Code — DebugInfoDemo.java

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public final class DebugInfoDemo {

    private DebugInfoDemo() {
    }

    public static String describe(String label, int count) {
        int doubled = count * 2;
        String result = label + ":" + doubled;
        return result;
    }

    public static void main(String[] args) throws Exception {
        System.out.println(describe("job", 3));

        Method method = DebugInfoDemo.class.getDeclaredMethod(
                "describe", String.class, int.class);

        for (Parameter parameter : method.getParameters()) {
            System.out.println(
                    "parameter=" + parameter.getName()
                    + ", present=" + parameter.isNamePresent());
        }
    }
}
~~~

This is a **standalone program** for Java 17+.

- `describe` has two parameters `label` and `count`.
- Local variables `doubled`, `result` are genuinely used so they appear meaningfully in the variable name table when compiled with `-g`.
- `main` prints a stable business result, then uses Reflection to retrieve method `describe(String,int)`.
- `getDeclaredMethod(...)` uses parameter types and method name to locate the declaration; it does not require stored parameter names.
- `Parameter.getName()` can return the real source name or a synthetic name `arg0`, `arg1`.
- `isNamePresent()` is the explicit way to check whether a name has valid metadata; do not rely on whether the string starts with `arg`.

## 4. Experiment A — Default Compilation, Observing Source Lines

Run:

~~~bash
javac --release 17 -encoding UTF-8 -d out/default DebugInfoDemo.java
java -cp out/default DebugInfoDemo
~~~

Program stdout when `-parameters` is not enabled:

~~~text
job:6
parameter=arg0, present=false
parameter=arg1, present=false
~~~

`job:6` comes from `count=3` and `doubled=6`. The two names `arg0`, `arg1` are fallbacks provided by Reflection when name info is absent, **not evidence that source code named the two parameters that way**.

### 4.1 Viewing LineNumberTable

~~~bash
javap -classpath out/default -l -p DebugInfoDemo
~~~

`-l` tells `javap` to display source line and local variable tables **if present**; `-p` shows private members as well. In default `javac` output, you typically see `LineNumberTable` entries for methods with bytecode.

Check further:

~~~bash
javap -classpath out/default -v -p DebugInfoDemo
~~~

`-v` is verbose, displaying constant pool, attributes, code, and metadata details. Look for:

~~~text
SourceFile:
LineNumberTable:
~~~

These are **labels to look for**, not the complete `javap` output. Constant-pool index order, offsets, line numbers, and how each attribute prints vary by source/compiler version.

### 4.2 Why Is LocalVariableTable Missing?

Default `javac` normally emits source line/file info yet **does not request complete local-variable debug info**. Thus `javap -l` can show `LineNumberTable` without a `LocalVariableTable` containing `doubled` or `result`.

Do not mistake this for non-existent variables. The program used the variables at runtime; it is simply that variable names **were not stored as debug metadata**.

### 4.3 Does Reflection Receive Parameter Names?

The program returned `present=false`. Therefore, runtime lacks source parameter name metadata in the way `java.lang.reflect.Parameter` trusts. The compiler still knows `describe` takes `String` and `int`; type info lives in the method descriptor and is provided by Reflection.

**Conclusion A:** default line metadata does not imply local variable metadata or reflection parameter names.

## 5. Experiment B — Enabling -g to See Local Variables

Recompile **from original source** into a dedicated output:

~~~bash
javac --release 17 -encoding UTF-8 -g -d out/debug DebugInfoDemo.java
javap -classpath out/debug -l -p DebugInfoDemo
~~~

Inside method `describe`, `javap` will have a `LocalVariableTable` entry, with rows showing names like:

~~~text
label
count
doubled
result
~~~

These are **names to look for in the table**, not four lines of stdout or the exact complete output. The real table usually has columns `Start`, `Length`, `Slot`, `Name`, and `Signature`.

Some observations:

- In static method `describe`, parameters and local variables use local variable slots according to the JVM.
- Names `label` and `count` can appear in `LocalVariableTable` when `-g` is enabled.
- Names `doubled` and `result` can appear along with the bytecode ranges where they are valid.
- `LocalVariableTable` does not replace `MethodParameters`; the two metadata sources serve different purposes.

### 5.1 Running the -g Build

~~~bash
java -cp out/debug DebugInfoDemo
~~~

Stdout remains:

~~~text
job:6
parameter=arg0, present=false
parameter=arg1, present=false
~~~

This is an important experiment: **`-g` gives debuggers variable names, yet Reflection still does not receive source parameter names** without `-parameters`. There is no contradiction; they read different class-file attributes.

### 5.2 What Does the LocalVariableTable Say?

A `LocalVariableTable` row roughly represents:

~~~text
Start   Length   Slot   Name       Signature
...     ...      ...    doubled    I
...     ...      ...    result     Ljava/lang/String;
~~~

The `...` here means **bytecode offsets vary by compiler**, not mandatory output lines; the table only illustrates the shape of the information.

- `Start` and `Length` define the bytecode range where the entry is meaningful.
- `Slot` is the local variable index in the JVM frame.
- `Name` is the name stored by the compiler.
- `Signature` in this table is usually the type descriptor, e.g., `I` for `int` or `Ljava/lang/String;` for `String`.
- In instance methods, slot 0 is usually `this`; in static methods, there is no instance `this` parameter.
- Two variables with non-overlapping live ranges can reuse the same slot; do not infer that every variable name occupies a unique slot the entire time.

Do not confuse offsets in `LocalVariableTable` with source line numbers. They describe **bytecode regions**, whereas `LineNumberTable` maps bytecode to Java lines.

### 5.3 LocalVariableTypeTable Relates to Generic Types

With code containing generic local variables (e.g., `List<String>`) and when the compiler stores matching info, you may see `LocalVariableTypeTable` representing a richer generic signature than the raw descriptor in `LocalVariableTable`.

This does **not** mean every class must have `LocalVariableTypeTable` after `-g`. If a method has no generic local variables needing extra signatures, that attribute may be absent.

`LocalVariableTypeTable` serves local debug metadata; do not confuse it with method/class `Signature` used to describe generic declarations.

## 6. Experiment C — Storing Only Variable Names with -g:vars

Compile:

~~~bash
javac --release 17 -encoding UTF-8 -g:vars -d out/vars DebugInfoDemo.java
javap -classpath out/vars -l -p DebugInfoDemo
~~~

You will find `LocalVariableTable` for applicable code. However, because only `vars` was requested, **do not expect `LineNumberTable` or `SourceFile` from other debug groups to be enabled**.

To emit all three groups explicitly:

~~~bash
javac --release 17 -encoding UTF-8 -g:lines,vars,source -d out/vars DebugInfoDemo.java
~~~

The final command overwrites output in the same `out/vars` directory, so run it **only after checking the -g:vars build**, or use a new directory if wanting to keep both versions to compare. It illustrates syntax for combining group names; it is not a required step to complete experiment C.

### 6.1 Using Each Debug Group Separately

| Flag | Question to Answer |
| --- | --- |
| `-g:lines` | Can bytecode be correlated with source lines? |
| `-g:source` | Is source file name info stored? |
| `-g:vars` | Are local variable names/scopes present for debugging? |
| `-g:lines,vars,source` | Can all three kinds of info be present? |
| `-g:none` | When debug metadata is removed, how do outputs/stack traces change? |

These are **compiler** choices, not instructions to `javap` on what to hide/show. `javap` simply reads attributes actually present in the class file.

## 7. Experiment D — Enabling -parameters So Reflection Sees Names

Compile into a dedicated output:

~~~bash
javac --release 17 -encoding UTF-8 -parameters -d out/params DebugInfoDemo.java
java -cp out/params DebugInfoDemo
~~~

Stdout:

~~~text
job:6
parameter=label, present=true
parameter=count, present=true
~~~

The first line is unchanged because method runtime behavior does not depend on parameter names. The next two lines changed because `MethodParameters` stores declaration names.

### 7.1 Verifying MethodParameters with javap

~~~bash
javap -classpath out/params -v -p DebugInfoDemo
~~~

Look inside method `describe`:

~~~text
MethodParameters:
  Name                           Flags
  label
  count
~~~

This is a **directional excerpt**, not guaranteeing identical whitespace/column output. What matters is that names `label` and `count` belong to the `MethodParameters` section of method `describe`.

The `MethodParameters` section can also contain flags describing synthetic/mandated parameters depending on the declaration; do not assume every class/method has only the parameters authors see in source.

### 7.2 Why Does -parameters Not Replace -g?

Run:

~~~bash
javap -classpath out/params -l -p DebugInfoDemo
~~~

In the example using `-parameters` without `-g`, you normally **do not** have a `LocalVariableTable` for variables `doubled` and `result`, because `-parameters` does not ask the compiler to store local variable names. The `MethodParameters` section is viewed via `javap -v` rather than inferred from `javap -l`.

Typical scenario:

- Reflection prints `label` and `count`.
- A debugger may not see the names `doubled` and `result` without `LocalVariableTable`.
- Stack traces can still have line numbers because default debug lines are still emitted by javac.

**Conclusion D:** parameter name metadata for Reflection is independent of local variable debug info.

## 8. Experiment E — Combining -g and -parameters

Run:

~~~bash
javac --release 17 -encoding UTF-8 -g -parameters -d out/all DebugInfoDemo.java
javap -classpath out/all -v -p DebugInfoDemo
java -cp out/all DebugInfoDemo
~~~

In the class file you can verify:

- `SourceFile` for the source name.
- `LineNumberTable` for bytecode-line mapping.
- `LocalVariableTable` for variables `doubled`, `result`, and relevant local info.
- `MethodParameters` for names `label`, `count`.

Stdout:

~~~text
job:6
parameter=label, present=true
parameter=count, present=true
~~~

This is a convenient choice when **debugging with local variable names** while also wanting **frameworks/reflection to read source parameter names**.

### 8.1 What Is Not Changed by These Flags?

For `DebugInfoDemo` code compiled at the same Java level:

- The business result `job:6` does not change.
- Parameter types of `describe(String,int)` do not change.
- Java method invocation does not become a named-argument call.
- `-g` and `-parameters` do not embed runtime variable values into the class file.
- `-parameters` does not add a new runtime parameter to the method.
- Extra attributes may make the class file larger, yet are not proof that an algorithm runs faster/slower by any fixed formula.

## 9. Experiment F — -g:none While Still Having -parameters

A very useful test to prove independence:

~~~bash
javac --release 17 -encoding UTF-8 -g:none -parameters -d out/none DebugInfoDemo.java
java -cp out/none DebugInfoDemo
javap -classpath out/none -v -p DebugInfoDemo
~~~

Stdout:

~~~text
job:6
parameter=label, present=true
parameter=count, present=true
~~~

`-g:none` requests stripping debug metadata belonging to the `-g` group; however, `-parameters` still asks the compiler to store parameter name info. Thus you can see `MethodParameters` without `LineNumberTable`, `LocalVariableTable`, and `SourceFile` from debug flags.

If you need a build requesting no debug metadata **and also not keeping source parameter names**, you can compile separately:

~~~bash
javac --release 17 -encoding UTF-8 -g:none -d out/none DebugInfoDemo.java
~~~

**Note:** the last command overwrites the artifact in `out/none` created by `-g:none -parameters`. Run it only after inspecting and recording the prior build, or change output to another directory if wanting to keep both to compare.

After recompiling **without `-parameters`**, Reflection reverts to `arg0`/`arg1` and `isNamePresent()==false`.

## 10. Summary of Six Configurations

| Output | Flag | `LineNumberTable` | `LocalVariableTable` | `MethodParameters` for `describe` | Reflection names |
| --- | --- | --- | --- | --- | --- |
| `out/default` | Default | Yes (usually) | No (usually) | No | `arg0`, `arg1` |
| `out/debug` | `-g` | Yes | Yes | No | `arg0`, `arg1` |
| `out/vars` | `-g:vars` | No per flag request | Yes | No | `arg0`, `arg1` |
| `out/params` | `-parameters` | Yes (default) | No (default) | Yes | `label`, `count` |
| `out/all` | `-g -parameters` | Yes | Yes | Yes | `label`, `count` |
| `out/none` | `-g:none -parameters` | No | No | Yes | `label`, `count` |

The table describes verification expectations with **standard JDK 17+ javac**, `DebugInfoDemo` source, and the specific commands. Do not treat this as a rule for all tools generating/transforming class files (Kotlin, Scala, obfuscators, bytecode instrumentation, ahead-of-time compilers...). When needing certainty, run `javap` on the **final artifact**.

If you ran commands overwriting `out/vars` or `out/none` in earlier sections, recompile that column's original configuration before comparing with the table.

## 11. Inspecting Each Attribute with javap

### 11.1 `javap -l`: Line and Local Variable Tables

~~~bash
javap -l -p -classpath out/all DebugInfoDemo
~~~

`-l` asks to display the class's line/local-variable tables when present. With matching source/flags, you see information per method.

**Do not use `javap -l` alone to check `MethodParameters`.** That table is shown clearly in verbose output.

### 11.2 `javap -v`: Inspecting Attributes and Method Metadata

~~~bash
javap -v -p -classpath out/all DebugInfoDemo
~~~

Look for the labels:

~~~text
SourceFile
LineNumberTable
LocalVariableTable
MethodParameters
~~~

`-v` also prints the constant pool, method descriptors, class flags, bytecode metadata, and many other attributes. Displayed information varies by class.

### 11.3 `javap -c`: Bytecode Helps Understand Slots and Instructions

~~~bash
javap -c -p -classpath out/all DebugInfoDemo
~~~

In method `describe`, you can see instructions related to parameters and multiplication (e.g., `iload_1`, multiplying by 2) and string concatenation per the active JDK compiler's mechanism. Do not hard-expect a specific instruction sequence because compilers can implement string concatenation differently, especially on modern JDKs with `invokedynamic`.

`javap -c` returns bytecode, **not a decompiler reconstructing exact Java source**. Combine `-c` with `-l`/`-v` to correlate bytecode offsets, line maps, and local variable names.

### 11.4 `javap -p` Does Not Reveal Non-Existent Information

`-p` (equivalent to asking to view private members) displays the demo's private constructor and non-public members too. It does not “recover” local variable names or parameter names if the class file does not store those names.

If you do not see `MethodParameters`, `LocalVariableTable`, or `SourceFile`, check **compiler options, output directory, and artifact** before concluding `javap` is wrong.

## 12. Stack Traces and LineNumberTable

When a program throws an exception, the JVM can use class-file metadata to print the source file name and line number. This usually relies on `SourceFile` and `LineNumberTable`. If information is missing, stack traces may show only class/method names and descriptions like `Unknown Source`.

### 12.1 ExceptionTraceDemo.java Example

~~~java
public final class ExceptionTraceDemo {
    public static void main(String[] args) {
        crash();
    }

    private static void crash() {
        throw new IllegalStateException("boom");
    }
}
~~~

Run with a dedicated output:

~~~bash
javac --release 17 -encoding UTF-8 -d out/default ExceptionTraceDemo.java
java -cp out/default ExceptionTraceDemo
~~~

The program intentionally throws an exception. Stderr content will contain `IllegalStateException: boom` and stack frames for `crash`/`main`, usually with file name and lines when metadata is present. **Do not hard-expect the entire stack trace** because file paths, line numbers, and formatting may differ if source is edited.

Then try:

~~~bash
javac --release 17 -encoding UTF-8 -g:none -d out/none ExceptionTraceDemo.java
java -cp out/none ExceptionTraceDemo
~~~

This time the stack trace usually lacks file names/lines because debug attributes were not generated, and may display `Unknown Source`.

Note: the two commands above reuse `DebugInfoDemo`'s existing output dirs while creating **a differently named class**. This does not overwrite `DebugInfoDemo.class`; even so, when precisely validating an artifact, it is best to use a separate output directory for each major test.

### 12.2 LineNumberTable Is Not a Perfect Source Map

Even when line info is present:

- One source line can generate multiple bytecode instructions.
- Multiple expressions on the same line can be assigned the same line.
- Compilers can emit code supporting language constructs without perfect per-character mapping.
- The JIT may inline or optimize at runtime; debugging values/frames depends on the JVM's ability to reconstruct state.
- Stack traces may not show every frame in all execution/optimization scenarios or asynchronous errors in the exact same way.

Therefore, `LineNumberTable` is useful debug information, not a copy of the full source.

## 13. Parameter Names, Reflection, and Constructors

### 13.1 Important Reflection APIs

A `java.lang.reflect.Parameter` has:

- `getName()`: the name string provided by Reflection.
- `isNamePresent()`: whether the name is actually present in class-file metadata per API.
- `getType()`: raw type of the parameter.
- `getParameterizedType()`: generic type information when present.
- `isSynthetic()`, `isImplicit()`: special info about parameters generated by the language/compiler.
- `getAnnotations()`: runtime-visible annotations on the parameter if present.

`isNamePresent()` matters more than comparing the name against `arg0`: valid source code **can genuinely name a parameter `arg0`**. Looking solely at the string does not tell whether it came from metadata or fallback.

### 13.2 Both Methods and Constructors Have Parameter Metadata

`-parameters` requests storing parameter names for both methods and constructors when applicable. Example of a constructor:

~~~java
public final class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
~~~

This is a **standalone Java class** placed in `Order.java`, not a class with `main`. You can verify with `javap -v -p Order` after compiling with `-parameters`.

Example driver `ConstructorProbe.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorProbe {
    public static void main(String[] args) throws Exception {
        Constructor<Order> c =
                Order.class.getDeclaredConstructor(String.class);

        for (Parameter p : c.getParameters()) {
            System.out.println(
                    p.getName() + ":" + p.isNamePresent());
        }
    }
}
~~~

Compile both sources into a new output:

~~~bash
javac --release 17 -encoding UTF-8 -parameters -d out/all Order.java ConstructorProbe.java
java -cp out/all ConstructorProbe
~~~

Stdout:

~~~text
id:true
~~~

If the compiler did not store parameter names, Reflection usually prints `arg0:false`. That does not stop the constructor from accepting `String` and creating the object.

### 13.3 Synthetic, Implicit, and Mandated Parameters

Some Java constructs have hidden or compiler-added parameters, for example:

- Constructors of non-static inner classes may need a parameter representing the outer instance.
- Enum constructors have internal parameters serving name and ordinal.
- Different compilers can generate bridge/synthetic methods.
- Record constructors and special language constructs have their own rules.

When analyzing such methods/constructors, do not assume parameter counts/names in bytecode always match the exact source declaration you see. Use `Parameter.isImplicit()`, `isSynthetic()`, `Method.isBridge()`, and appropriate class-file flags, while testing empirically.

**No need to apply these exceptions to the `describe(String,int)` method** in the demo: it is a normal static method with the exact two parameters declared by the author.

### 13.4 Parameter Names Are Not Annotations or Generic Metadata

- `-parameters` stores names; it does not determine `@Retention(RUNTIME)`.
- `Parameter.getAnnotations()` depends on annotation retention and related class-file attributes.
- Method generic signatures follow a separate metadata path, not `LocalVariableTable` or `MethodParameters`.
- Seeing parameter names does not prove the code has validation annotations, doc comments, or default argument values.

Do not use `MethodParameters` to infer information the class file did not store.

## 14. Can Using -g:vars Retrieve Reflection Parameter Names?

This is an especially common confusion. Compare:

~~~bash
javac --release 17 -g -d out/debug DebugInfoDemo.java
java -cp out/debug DebugInfoDemo
~~~

with:

~~~bash
javac --release 17 -parameters -d out/params DebugInfoDemo.java
java -cp out/params DebugInfoDemo
~~~

In the first run:

- Debuggers/`javap -l` can see parameter names as local variables in `LocalVariableTable`.
- Reflection can still return `arg0`/`arg1` and `isNamePresent()==false`.

In the second run:

- Reflection returns `label`/`count` with `isNamePresent()==true`.
- Debug local names like `doubled`/`result` are not emitted by default just because `-parameters` is set.

Two tools inspect **two different kinds of class-file attributes**. Some older frameworks had mechanisms trying to read local variable debug info to infer parameter names, yet do not confuse those framework-specific mechanisms with Java Reflection's `Parameter.isNamePresent()` contract.

## 15. IDEs, Gradle, Maven, and Build Configuration Differences

In an IDE, the Build/Run button may use separate compiler settings or delegate to Gradle/Maven. Therefore, the IDE displaying parameter names does not prove the released binary was compiled with `-parameters`. A debugger can read local variable names from the IDE's output while the CI build artifact had debug tables stripped.

### 15.1 Gradle Groovy DSL

Example in `build.gradle` of a Java project:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
    options.debug = true
}
~~~

This is Gradle Java plugin configuration, **not a standalone Java program**.

- `-parameters` asks the compiler to store parameter names.
- `options.debug = true` requests debug information; how Gradle specifically passes compiler arguments depends on version and task configuration.
- If needing to restrict debug info by group (lines/vars/source), inspect the task's compiler args and ensure no conflicting flags exist.
- In multi-project Gradle builds, check the corresponding tasks of each module; do not assume one build file applies to all artifacts.

Kotlin DSL example in `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
    options.debug = true
}
~~~

This is also a **configuration snippet**, requiring the appropriate Gradle Java plugin and JavaCompile task.

### 15.2 Maven Compiler Plugin

In `pom.xml`, a form of Maven Compiler Plugin configuration:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
                <debug>true</debug>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is a configuration snippet inside a **full POM**; the plugin and version must support the elements used. `parameters` and `debug` correspond to two different needs. Maven may have overriding properties/plugin configurations or profiles; inspect the effective config.

### 15.3 Do Not Look Only at sourceCompatibility or release

`--release 17` is useful for source/API/class-file compatibility, yet does not by itself certify `MethodParameters` is present. A project needing Java 17 runtime **and** reflection parameter names must verify both release and the `-parameters` flag.

### 15.4 Process for Verifying the Final Artifact

1. Identify the actual compiler/JDK used by IDE, Gradle, Maven, or CI.
2. Record exact compiler options.
3. Compile to a **clean output directory**.
4. Open the class/JAR **to be released** with `javap -v -p` and `javap -l`.
5. Check `LineNumberTable`, `LocalVariableTable`, `MethodParameters` on methods of interest.
6. Run Reflection tests with classpath pointing strictly to the final artifact.
7. If obfuscation/shading/instrumentation exists, re-inspect the artifact **after transformation**.
8. Avoid inferring from class files of an old build sitting in another directory.

A JAR can contain classes compiled with different flags, especially when merging multiple modules or third-party dependencies. Concluding “the whole JAR has parameter names” is only reasonable after verifying the critical classes.

## 16. When Class Files Are Obfuscated or Metadata Is Stripped

Shrink/obfuscate/bytecode transform tools can rename classes/methods/fields, delete debug attributes, or keep/remove `MethodParameters` depending on rules. Thus output from `javac -g -parameters` may not retain identical metadata after packaging.

### 16.1 Observable Consequences

- Loss of `LineNumberTable`: stack traces no longer have useful source line numbers.
- Loss of `SourceFile`: missing source file name in frames.
- Loss of `LocalVariableTable`: debuggers cannot read declared local variable names.
- Loss of `MethodParameters`: Reflection `isNamePresent()` can revert to false, and frameworks depending on parameter names may fail.
- Renamed classes/members: stack traces can become hard to read without a deobfuscation mapping.

**Not every tool strips attributes with the same defaults.** Read the specific tool's rules/docs, then verify the transformed binary with `javap`.

### 16.2 Metadata and Privacy

Local variable/parameter names can expose some internal terminology, business logic, or data domain names. However, stripping debug info is **not a secret-protection measure**: bytecode can still be analyzed and constants may remain in the class file.

Do not store passwords/API keys in source and rely on `-g:none` to “hide” them. Do not place secrets in client artifacts when unnecessary.

### 16.3 Trade-offs

Keeping metadata helps stack traces/debugging and some frameworks; stripping can reduce binary size and exposed source info. Configuration should be based on actual operational needs, rather than assuming “release builds must always strip all debug info” or “every class must unconditionally enable -g”.

## 17. Edge Cases When Observing Metadata

### 17.1 Non-Java Compiled Source

Class files from Kotlin, Scala, or other JVM languages can have line/variable/parameter info following their own compiler rules. Do not assume `javac -g` was used just because you see `LineNumberTable`.

### 17.2 Generated Code

Annotation processors can generate Java source and the compiler creates corresponding classes. Line info may point into **generated source**, not user-written files. If needing a source map back to the original declaration, build tools/processors must maintain appropriate metadata; `LineNumberTable` does not inherently know code-generation rules.

### 17.3 Lambdas and Synthetic Methods

The Java compiler can generate synthetic methods to implement lambdas or language constructs. These methods do not necessarily map one-to-one with user-declared source methods. Debug metadata and parameter names of synthetic methods do not necessarily match the meaning of the source declaration.

### 17.4 Compiler Optimizations and Local Variable Scopes

`LocalVariableTable` marks bytecode ranges, not an exact runtime value timeline. Variables can reuse local slots or be optimized at runtime. A debugger might not display an out-of-scope variable or might be unable to retrieve values after JIT optimization.

### 17.5 Having MethodParameters Without LineNumberTable

This is **not a corrupted file**. It can be the valid result of `-g:none -parameters`, or due to post-processing. Reflection can still know parameter names even when stack traces lack source lines.

### 17.6 Having LineNumberTable Without Parameter Names

Also completely normal. This is the common default state of `javac`: stack traces have line numbers, yet Reflection `isNamePresent()==false` for methods not compiled with `-parameters`.

## 18. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Reflection prints `arg0`, `arg1` | Missing `MethodParameters` | Compile with `-parameters`, check `javap -v` |
| Even with `-g`, Reflection still has `isNamePresent=false` | Confused `LocalVariableTable` with `MethodParameters` | Add `-parameters`, clean compile |
| `javap -l` shows no local variable names | Missing `-g:vars`/`-g` or method has no matching metadata | Check `-g` and artifact |
| `javap -v` shows no `SourceFile` | `-g:none`, `-g:vars`, or stripping | Build with `-g:source`/`-g` if needed |
| Stack trace shows `Unknown Source` | No matching source/line info | Check `SourceFile` and `LineNumberTable` |
| One file has `MethodParameters`, another does not | Different compiler task/module/tool | Check build options per module |
| Debugger cannot inspect a variable | Scope, slot reuse, optimization, or missing debug info | Check `LocalVariableTable` and breakpoint |
| `javap` output differs from IDE | IDE and CLI using different outputs | Check actual class/JAR paths |
| Recompiled yet still seeing old metadata | Stale output/wrong classpath ordering | Compile to new directory, exact `javap -classpath` |
| Constructor parameter names differ from expected | Synthetic/implicit parameters or generated code | Use `Parameter.isSynthetic/isImplicit` and inspect binary |
| Obfuscated class lost names | Post-processing deleted/altered attributes | Run `javap` on post-obfuscation artifact |
| `-g:vars` has name `label` yet runtime still prints `arg0` | Local variable metadata is not reflection parameter metadata | Use `-parameters` |
| `javap` cannot find class | Wrong classpath root or qualified class name | Check `-classpath` and `.class` file |
| JVM runs despite no debug info | Debug attributes are non-essential for bytecode execution | Do not treat running successfully as proof metadata exists |

### 18.1 How to Identify the Class Being Loaded by the JVM

In situations with multiple JARs/outputs having the same class name, check the classpath and class-loading info. With HotSpot/JDK 17+, for example:

~~~bash
java -Xlog:class+load=info -cp out/all DebugInfoDemo
~~~

The command can print many log lines containing class names and load sources; log details depend on implementation. Search for `DebugInfoDemo` and the binary path; do not treat the entire log as fixed output.

### 18.2 Do Not Confuse Inspecting Metadata with Fixing Runtime Bugs

A program can compile, run, and return the right result without line names or local names. Conversely, a file full of debug tables can still contain bugs or lack runtime dependencies. `javap` helps **verify what the compiler wrote**, not guarantee business correctness.

## 19. Frequently Asked Questions

### Q1. Why does `javap -l` have lines without local variables?

Because by default `javac` usually emits line/source info, while local variable names require `-g` or `-g:vars`. Check flags and binary again.

### Q2. Does `-parameters` work for private methods?

It can store parameter names of methods/constructors regardless of access level when applicable. Use `javap -v -p` to inspect private members. Reflection still requires access permissions and matching module rules if wanting to **invoke** a private method; reading metadata does not grant execution permission.

### Q3. Does `isNamePresent()==false` mean parameter types are also lost?

No. The method descriptor still specifies types and order. Reflection can know parameter counts/types without knowing source names.

### Q4. Can exact variable names be recovered from bytecode?

Not guaranteed. If the compiler did not store names in `LocalVariableTable` or similar metadata, a decompiler may guess names, yet cannot guarantee recovering original names.

### Q5. Does `-g` need to be enabled for web frameworks using parameter binding?

Depends on the framework. With standard Java Reflection, `-parameters` is the direct way to make `Parameter.isNamePresent()` true. Other frameworks may have their own mechanisms. Do not treat `-g` as a reliable substitute for `-parameters`.

### Q6. Can `-parameters` be used simultaneously with `-g:none`?

Yes. Experiment F illustrates that parameter metadata can remain even when debug info is stripped.

### Q7. Does LocalVariableTable store the names of all variables?

Not necessarily. It stores applicable entries emitted by the compiler and allowed by flags; optimizations, live scopes, method kinds, and bytecode post-processing affect what remains visible. There is no guarantee every source declaration has a single, immutable entry.

### Q8. Why does `getParameters()` return two objects even without `-parameters`?

Because the method descriptor contains two parameter types. `-parameters` is required to store names/extra metadata, not to determine parameter counts.

## 20. Exercises with Answers

### Exercise 1 — Predicting Reflection When Enabling Only -g

Commands:

~~~bash
javac --release 17 -g -d out/debug DebugInfoDemo.java
java -cp out/debug DebugInfoDemo
~~~

**Answer:** `job:6` and two lines `parameter=arg0, present=false`; `parameter=arg1, present=false`. `-g` primarily creates line/source/local-variable debugging metadata, and does not automatically create `MethodParameters`.

### Exercise 2 — Predicting Reflection When Enabling Only -parameters

~~~bash
javac --release 17 -parameters -d out/params DebugInfoDemo.java
java -cp out/params DebugInfoDemo
~~~

**Answer:** `parameter=label, present=true`; `parameter=count, present=true`. Parameter name metadata is stored; variable names `doubled`/`result` are not in LocalVariableTable by default unless `-g` is enabled.

### Exercise 3 — Checking the Source Line Table

You need to verify class `DebugInfoDemo` has `LineNumberTable`. Which command is appropriate?

**Answer:** `javap -classpath out/default -l -p DebugInfoDemo` or `javap -v -p -classpath out/default DebugInfoDemo`. Simply viewing `.java` source does not prove the class file stored line metadata.

### Exercise 4 — Difference Between Source Lines and Bytecode Offsets

`LocalVariableTable` has `Start=...`, `Length=...`; are those Java line numbers?

**Answer:** No. They describe the bytecode region where a variable is active. `LineNumberTable` is what maps from bytecode positions to source lines.

### Exercise 5 — Enabling Both Debug and Parameters

Need to let debuggers view local variable names while Reflection reads parameter names. Which flags?

**Answer:** `-g -parameters` (or `-g:lines,vars,source -parameters`). After compiling, verify with `javap -l/-v` and `Parameter.isNamePresent()`.

### Exercise 6 — Why Are Stack Traces Missing Line Numbers?

The class was compiled with `-g:none`. Why do stack traces lack line/source info?

**Answer:** The compiler did not store the debug line/source attributes that stack traces use to map bytecode back to source. The program can still run normally.

### Exercise 7 — Constructors

Compile `Order` and `ConstructorProbe` with `-parameters`. What does the driver print?

**Answer:** `id:true` because constructor parameter `id` is stored in metadata. Without that flag, the typical example prints `arg0:false`.

### Exercise 8 — Avoiding Binary Confusion

`javap -v` sees `MethodParameters`, yet the application still prints `arg0`. Investigation steps?

**Answer:** Confirm both `javap` and `java` use the same class/JAR, with the right classpath root and ordering. Check for duplicate class names, stale outputs, or bytecode transforms; use class-loading logs when needed.

### Exercise 9 — Impact of Obfuscation

A JAR passed through a shrinker no longer has `LocalVariableTable`, whereas the original output had it. Can you conclude the compiler did not use `-g`?

**Answer:** No. The shrinker may strip metadata. Inspect the artifact before and after transformation along with tool rules.

### Exercise 10 — Metadata Security

Does `-g:none` completely protect secrets inside bytecode?

**Answer:** No. It only asks to omit debug attributes; constants or code logic can still be read from the class file. Do not embed secrets into artifacts.

## 21. Self-Validation Checklist

- [ ] I know `-g` and `-parameters` serve different purposes.
- [ ] I compiled the same source into **separate** outputs for each configuration.
- [ ] I used `javap -l` to inspect `LineNumberTable` and `LocalVariableTable`.
- [ ] I used `javap -v` to look for `MethodParameters`.
- [ ] I know `SourceFile` and `LineNumberTable` support stack traces/debuggers.
- [ ] I distinguish bytecode offsets, local slots, and source lines.
- [ ] I verified Reflection using `getName()` and `isNamePresent()`.
- [ ] I understand why `-g` is not enough for Java Reflection parameter names.
- [ ] I tested `-g:none -parameters` to prove independence.
- [ ] I do not infer variable/parameter names from program stdout.
- [ ] I know metadata can be altered by build tools/obfuscators.
- [ ] I inspect the **final** artifact instead of checking source only.
- [ ] I understand debug metadata holds no runtime values and does not change method call syntax.
- [ ] I do not confuse the presence of debug attributes with application correctness.

## References

- [Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-g`, `-g:...`, `-g:none`, `-parameters`.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): options `-l`, `-v`, `-c`, `-p`.
- [Java SE 17 — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): `getName()`, `isNamePresent()`.
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): `LineNumberTable`, `LocalVariableTable`, `MethodParameters`, and other attributes.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): Reflection method metadata.

## Conclusion

**Having source lines, having local variable names, and having parameter names are three distinct capabilities of a class file.** `-g`/`-g:...` controls debug information, while `-parameters` enables storing parameter metadata so Java Reflection can read source names via `Parameter.isNamePresent()`. Check `javap -l/-v` on the exact binary, verify with a Reflection program running with the right classpath, and note that post-processing can modify those attributes. Understanding the difference between `LineNumberTable`, `LocalVariableTable`, and `MethodParameters` equips you to diagnose stack traces missing lines, debuggers missing local names, or frameworks failing to retrieve parameter names.
