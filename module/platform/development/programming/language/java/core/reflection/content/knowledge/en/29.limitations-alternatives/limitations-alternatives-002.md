# Local Variable Names and Debug Information Are Not Standard Core Reflection APIs

## 1. The Problem: What Does Reflection See Inside a Method?

Suppose a Java method has **parameters** `owner`, `amount` and **local variables** `fee`, `label`:

~~~java
public static int compute(String owner, int amount) {
    int fee = amount / 10;
    String label = owner + ":" + fee;
    return label.length();
}
~~~

There are three very different questions:

1. **Which parameter types does the method accept?** Core Reflection answers with `Method.getParameterTypes()`, `getGenericParameterTypes()`, and `getParameterCount()`.
2. **What are the declared names of the parameters?** `Method.getParameters()` returns `Parameter` objects, but original names `owner`, `amount` are reliable only when the class file has corresponding metadata, typically produced by `javac -parameters`.
3. **Which local variables exist in the method body, and what are their names and values?** **There is no `Method.getLocalVariables()` API in Core Reflection.** Names `fee` and `label` may be recorded by the compiler in optional bytecode debug information, but ordinary `java.lang.reflect` APIs do not provide that list and cannot read local values of a running stack frame.

This distinction matters when writing inspectors, serializers, dependency injection containers, dynamic method invocation frameworks, debuggers, or bytecode analysis tools. Learners must separate **class structure**, **method signatures**, **debug metadata**, and **stack frame state at a point in time**.

This lesson focuses solely on Java Core and Reflection limits; specialized bytecode/debug tools are introduced for choosing a solution when needed, not to implement a full debugger.

## 2. Fields, Parameters, and Local Variables Are Three Different Kinds of Data

| Component | Typical declaration | Where it lives / meaning | Appropriate API |
| --- | --- | --- | --- |
| **Instance field** | `private String name;` in a class | State of an object | `Class.getDeclaredFields()`, `Field.get(obj)` as permitted |
| **Static field** | `static int counter;` in a class | State associated with a class | `Class.getDeclaredFields()`, `Field.get(null)` as permitted |
| **Formal parameter** | `String owner, int amount` in method declaration | Input declared in the **method/constructor signature** | `Executable.getParameters()`, `Parameter`, `Method.getParameterTypes()` |
| **Local variable** | `int fee = ...;` in method body | Language-scoped variable inside a method body; may be represented in a local slot/stack or optimized away | No standard Core Reflection API to list/read like `Field` |
| **Temporary value** | Intermediate value in bytecode computation | Not necessarily named in source or stored in a stable location | Specialized bytecode/debug tools, if suitable evidence exists |

**`Field` only describes fields**; it does not represent `int fee` or `String label` inside a method. Therefore, `getDeclaredFields()` is not a solution for "scanning all variables" in a class.

**`Parameter` describes declared parameters of an `Executable`** (`Method` or `Constructor`), not every local variable in a method body. Even though `fee` is used in computation, it does not appear in `getParameters()`.

**A runtime local is also not equivalent to a "fixed memory cell".** The JVM has the concept of each frame's local-variable array, but mapping source variable names to slots depends on the compiler, bytecode scope, optimizations, and optional debug information; it cannot be universally inferred from Reflection APIs.

## 3. How Far Does Core Reflection Access Parameter Metadata?

API example:

~~~java
Method method = Example.class.getDeclaredMethod(
        "compute", String.class, int.class);

Class<?>[] types = method.getParameterTypes();
Parameter[] parameters = method.getParameters();
~~~

This illustrative snippet requires importing `java.lang.reflect.Method` and `java.lang.reflect.Parameter` along with an `Example` class containing the corresponding method; a full runnable example appears in a later section.

APIs worth knowing:

| API | Returns | What cannot be inferred |
| --- | --- | --- |
| `Method.getName()` | Method name | Does not give names of variables inside the method body |
| `Method.getParameterCount()` | Number of parameters described in the method descriptor | Does not give local names |
| `Method.getParameterTypes()` | `Class<?>` objects matching runtime parameter types | Does not preserve full generic arguments |
| `Method.getGenericParameterTypes()` | Declared generic type metadata when present | Not local-variable metadata |
| `Method.getParameters()` | Array of `Parameter` in parameter order | Does not mean declared names are always stored |
| `Parameter.getName()` | Parameter name from metadata if present; may be synthesized `arg0`, `arg1` | Not guaranteed to be the name in source code |
| `Parameter.isNamePresent()` | `true` if the class file has a name for that parameter in **MethodParameters** | Does not prove local debug information is present |
| `Parameter.getType()` | Raw runtime type of the parameter | Does not give local values |
| `Parameter.isSynthetic()`, `isImplicit()` | Flags describing compiler-generated/implicit parameters if recorded | Not a measure of all temporary variables in the method body |

**Safe rule:** display `getName()` as the original parameter name only when `isNamePresent()` returns **true**. If `false`, you may get `arg0`, `arg1`, ... by position. These names are useful for fallback display but should not be treated as a stable business contract.

The `-parameters` flag is specifically for storing method/constructor parameter names in the class file for Reflection to read. Do not infer from a stack trace having line numbers that parameter names were stored.

## 4. Runnable Java 17+ Example Comparing Two Compilation Modes

Save the program verbatim as **LocalNameDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class LocalNameDemo {
    public static int compute(String owner, int amount) {
        int fee = amount / 10;
        String label = owner + ":" + fee;
        return label.length();
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        Method method = LocalNameDemo.class.getDeclaredMethod(
                "compute", String.class, int.class);

        System.out.println("method=" + method.getName());
        System.out.println("parameters=" + method.getParameterCount());

        for (Parameter p : method.getParameters()) {
            System.out.println("param=" + p.getName()
                    + ", present=" + p.isNamePresent());
        }

        System.out.println(
                "return=" + method.getReturnType().getSimpleName());
        System.out.println("result=" + compute("Lan", 20));
    }
}
~~~

**Run A — compile with default `javac` configuration, without `-parameters`:**

~~~bash
javac -encoding UTF-8 LocalNameDemo.java
java LocalNameDemo
~~~

Output of the class compiled **without MethodParameters containing parameter names**:

~~~text
method=compute
parameters=2
param=arg0, present=false
param=arg1, present=false
return=int
result=5
~~~

**Run B — recompile the same file with `-parameters`:**

~~~bash
javac -encoding UTF-8 -parameters LocalNameDemo.java
java LocalNameDemo
~~~

Output:

~~~text
method=compute
parameters=2
param=owner, present=true
param=amount, present=true
return=int
result=5
~~~

`result=5` because `fee=20/10=2`, and the string `"Lan:2"` has five characters.

In both runs, **Core Reflection still gets the exact parameter count and types**, still finds the method with `getDeclaredMethod("compute", String.class, int.class)`, and `compute` still runs identically. What changes is **the parameter names stored in the class file and exposed via Parameter**.

More importantly, even with `-parameters` enabled, the program **has no** `method.getLocalVariables()` call to list `fee` and `label` through Reflection. Those are two variables **inside the method body**, a different metadata location from `owner` and `amount`.

**Condition for a valid comparison:** genuinely recompile the same class into the running directory and do not use an old `.class` file on the classpath. Build tools/IDEs may enable `-parameters` or other compiler options according to project configuration; in this hands-on exercise, use `javac` directly with the options written above.

## 5. Debug Information in Bytecode: LocalVariableTable

A class file can contain optional attributes for debugging. For local variable names, the common component is **LocalVariableTable**, located inside a method's **Code** attribute.

An entry of **LocalVariableTable** contains fields such as:

| Field | Meaning |
| --- | --- |
| `start_pc` | Bytecode offset where the described live range begins |
| `length` | Length of the bytecode range over which the entry is meaningful |
| `name_index` | Reference to the variable name in the constant pool |
| `descriptor_index` | Reference to the JVM type descriptor of the variable |
| `index` | Slot in the frame's local-variable array |

This is **metadata attached to a bytecode region**, not a collection of values that always exists and can be accessed from a **Method** object. The same slot can be reused for another variable when live ranges do not overlap; a source variable might not have a corresponding entry in optimized or transformed bytecode.

In addition to **LocalVariableTable**, a class file may have **LocalVariableTypeTable** to describe generic type signatures of some variables. Whether these tables appear depends on the compiler, debug-generation mode, and class-file transformation steps.

Metadata types often confused with one another:

| Attribute / Mechanism | Information | Common way to generate / read |
| --- | --- | --- |
| **MethodParameters** | Names and flags of certain method/constructor parameters | `javac -parameters`; `Executable.getParameters()` |
| **LocalVariableTable** | Name/type/slot/bytecode range of locals, may include parameters | `javac -g:vars` or `-g`; view with `javap -l`, bytecode parser, debugger |
| **LocalVariableTypeTable** | Generic type signature for certain local variables | Debug metadata when emitted |
| **LineNumberTable** | Maps bytecode offsets to source lines | `javac` debug lines; debuggers and stack traces can leverage it |
| **SourceFile** | Source file name | Debug source metadata |
| **StackMapTable** | Type information used for bytecode verification | **Not** a list of source local names |

These tables **do not replace one another**. In particular, **`-g:vars` does not make `Parameter.isNamePresent()` become true** under the `Parameter` API contract: that method checks name information declared via **MethodParameters**, not using LocalVariableTable to reconstruct parameter names.

## 6. javac Options: How Does `-parameters` Differ from `-g:vars`?

| Compilation command | Parameter names via Core Reflection | LocalVariableTable |
| --- | --- | --- |
| `javac LocalNameDemo.java` | Typically `arg0`, `arg1`, `isNamePresent=false` | By default `javac` does not enable local-variable debug info |
| `javac -parameters LocalNameDemo.java` | `owner`, `amount`, `isNamePresent=true` | Does not thereby request `LocalVariableTable` |
| `javac -g:vars LocalNameDemo.java` | Still no parameter names via `Parameter.isNamePresent()` if `-parameters` is missing | Has local debug info as supported by the compiler |
| `javac -parameters -g:vars LocalNameDemo.java` | Has parameter names | Has local metadata |
| `javac -g LocalNameDemo.java` | Not automatically equivalent to `-parameters` | Generates full debug info, including local variables |
| `javac -g:none -parameters LocalNameDemo.java` | Still has parameter names thanks to `-parameters` | Does not request local-variable debug info |

**Note:** `-g:vars` selects metadata only for local variables; if you also need line numbers/source file, use `-g` or an appropriate combination such as `-g:lines,vars,source`.

To directly observe the structure in bytecode, run in sequence:

~~~bash
javac -encoding UTF-8 -parameters -g LocalNameDemo.java
javap -v -p LocalNameDemo
javap -c -l -p LocalNameDemo
~~~

In `javap -v`, look for the **MethodParameters** section of method **compute**; inside the method's **Code** section, look for **LocalVariableTable**. `javap -l` lists line information and local tables when present. The following abbreviated illustration shows the idea, **not a verbatim copy of every output line**:

~~~text
MethodParameters:
  Name    Flags
  owner
  amount

LocalVariableTable:
  Start  Length  Slot  Name    Signature
  ...
  ...           ...   owner   Ljava/lang/String;
  ...           ...   amount  I
  ...           ...   fee     I
  ...           ...   label   Ljava/lang/String;
~~~

The numbers `Start`, `Length`, and `Slot` depend on the bytecode the compiler emits. Do not write tests relying on slot numbers and offsets assumed to be stable across JDK versions or compiler options.

**Important explanation:** seeing `fee` and `label` with a class-file reader proves the bytecode has **debug metadata** about them. That **does not add a** `getLocalVariables()` **method** to the Reflection **Method** object, and **does not mean their values can be read from any time or thread**.

## 7. Variable Names and Running Variable Values Are Two Separate Problems

### Reading Variable Names from a Class File

A bytecode analysis tool can read the **LocalVariableTable** if it exists. It must decode the class-file structure and map local slots to bytecode ranges; that is the job of a class-file/bytecode tool, not a `Field.get` operation.

If a class was compiled without debug metadata, or was stripped, obfuscated, or transformed, original local names may no longer remain. **Accurate recovery of source names from bytecode alone cannot be guaranteed.** Decompilers sometimes invent guessed names; those are not proven original names.

### Reading Local Values While a Method Is Executing

The runtime value of a local belongs to a **stack frame** and an execution point, not a property of a class or instance. A debugger must suspend/inspect the right thread and frame and use appropriate debug/VM mechanisms; it also depends on JVM capabilities, debug info, optimization state, variable scope, and connection permissions/capabilities.

For instance, in a debugger, `fee` can be observed while execution is paused on a line that uses it. Once the method has returned, however, the corresponding frame no longer exists to retrieve local values like an object field. `Method` cannot read `fee`'s value back merely by knowing the method name.

**Stack traces** are not local data either: `StackTraceElement` has class name, method name, and source file/line when available, but does not contain the names and values of all local variables. `StackWalker` provides advanced frame-metadata traversal, not a debugger-style API to read all locals.

### Specialized Tools When Truly Needed

| Need | Tooling direction | Limitations to understand |
| --- | --- | --- |
| Display public API parameter names/types | Core Reflection `Method.getParameters()` + `-parameters` | Optional metadata; must check `isNamePresent()` |
| Inspect list of locals in bytecode | `javap`, class-file parser; ASM library when a project needs it | Debug metadata is not guaranteed to exist |
| Pause program and inspect stack frames/locals | **JDI/JDWP**, IDE debugger | Info may be missing; values depend on frame state, permissions, and debug session |
| Instrumentation/agent/VM tooling | **JVMTI**, specialized agent, or suitable observability tools | High technical scope; depends on VM capabilities and deployment policy |
| Track values for business purposes | Logging/tracing/telemetry explicitly emitted by code | Design what data to record; avoid collecting sensitive info |

With **JDI** (Java Debug Interface), a debugger can query local-variable metadata from a method and read values in a stack frame when valid; missing debug metadata can result in **AbsentInformationException**. This is a dedicated debugging API, **not synonymous with Core Reflection used in ordinary applications**.

## 8. Practical Limitations for Auto-Generation Tools

### Do Not Rely on Parameter Names Without Verification

If you write a router that invokes methods by parameter name, a compiler without `-parameters` may provide only `arg0`, `arg1`. This happens especially easily when libraries are compiled outside your control or build pipelines are inconsistent.

When parameter names matter for an API contract, do the following:
1. Explicitly specify compiler flags for sources you control.
2. Use `Parameter.isNamePresent()` to detect missing metadata.
3. Define a fallback or explicit configuration error; do not guess parameter names from position.
4. Consider an annotation declaring a stable key (for example a custom annotation) when it is truly a data contract.

### Do Not Turn Debug Metadata into an API Contract

`LocalVariableTable` is designed for debugging and may be missing or differ between builds. Do not use `fee` or `label` as stable keys in serializers, configuration, JSON, or user interfaces.

Renaming a local variable does not change the method signature as Reflection uses it to look up `getDeclaredMethod`; however, if a tool depends on names from debug bytecode, that tool becomes fragile. A compiler can eliminate or alter locals when optimizing, and instrumentation can rewrite metadata as well.

### Do Not Conclude Metadata Reflects All Source

A local in source may have its scope split, share slots, or fail to appear as a distinct observable variable. Some compiler-generated variables may also appear, while source variables lose their names. Use only what the class file actually records; do not claim completeness.

### Do Not Try to Access Locals Using setAccessible(true)

`AccessibleObject.setAccessible(true)` relates to access checks on **Reflection members** such as fields/methods/constructors within permitted boundaries; it does not create an API to query locals of a stack frame. There is no `Field` for variable `fee` to apply `Field.get` to.

## 9. Common Misconceptions

| Misconception | Fact | How to verify |
| --- | --- | --- |
| "`getDeclaredFields()` sees every variable in a class" | Only fields declared on that class; does not list variables inside methods | Compare the Field list with source containing `fee`, `label` |
| "`getParameters()` returns local variable names" | It returns formal parameters of the method/constructor | Compare `owner`, `amount` with `fee`, `label` |
| "With `-g`, `Parameter.isNamePresent()` is definitely true" | `-g` and `-parameters` are two different metadata mechanisms | Compile both configurations and run the program |
| "`-parameters` stores all local variables" | It stores parameter-name metadata, not enabling local debug tables for that purpose | Use `javap -v -p` |
| "If `LocalVariableTable` has a name, `Method` can read the local value" | Bytecode metadata differs from runtime frame data | Check the actual API of `java.lang.reflect.Method` |
| "A stack trace gives all local values" | Stack traces contain call location/frame metadata, not a list of local values | Print `new Exception().getStackTrace()` |
| "`arg0` is definitely the name the author chose" | Usually a fallback name when MethodParameters is absent | Check `isNamePresent()` |
| "Decompilers always accurately recover source names" | May generate guessed names when debug metadata is missing | Compare classes compiled with `-g:none` vs `-g` |

## 10. Step-by-Step Practice

**Exercise 1 — Parameter names:** run `LocalNameDemo` after compiling without `-parameters`, then enable that flag. Record the changes in `getName()` and `isNamePresent()`; explain why `getParameterCount()` does not change.

**Exercise 2 — Debug metadata:** compile with `-g:vars` without `-parameters`. Use `javap -v -p` to find `LocalVariableTable`; run `LocalNameDemo` and explain why `Parameter.isNamePresent()` can still be false.

**Exercise 3 — Both metadata types present:** compile with `-parameters -g`, inspect **MethodParameters** and **LocalVariableTable** in `javap -v`. Compare `owner`/`amount` with `fee`/`label` across the different tables.

**Exercise 4 — Without debug:** compile with `-g:none` then inspect with `javap -l -p`. Note which information is missing, and why the application still runs properly even without source local names.

**Exercise 5 — Fields vs locals:** add `private int counter;` to the class, use `LocalNameDemo.class.getDeclaredFields()`. Point out the **counter** field while local variables **fee** and **label** are absent.

**Exercise 6 — Inspector design:** write a function accepting a `Method` that outputs the method name, list of parameter types, and parameter names if `isNamePresent()`; if names are missing, print labels **parameter #0**, **parameter #1**. Do not rely on fallback names as if they were source names.

## 11. Knowledge Self-Check

**Question 1.** Can `Method.getParameters()` and `Class.getDeclaredFields()` read `fee` in the example?  
**Answer:** No. `fee` is a local inside the method body; those two APIs describe formal parameters and fields.

**Question 2.** Why can `getName()` be `arg0` even when the source name is `owner`?  
**Answer:** The class file may lack MethodParameters recording original names; check `isNamePresent()`.

**Question 3.** How does the `-parameters` flag differ from `-g:vars`?  
**Answer:** `-parameters` stores formal parameter names for Core Reflection; `-g:vars` stores local-variable debug information in bytecode.

**Question 4.** Is knowing the name `label` from `javap` enough to retrieve its current value using Reflection?  
**Answer:** No. Debug metadata does not imply an active frame exists and does not create an API to read local values in `java.lang.reflect`.

**Question 5.** If a framework needs stable parameter-name keys, what should it do?  
**Answer:** Control builds with `-parameters`, validate metadata, or use explicit contract annotations/metadata.

**Question 6.** Do JDI and JVMTI belong to the same API tier as ordinary Reflection?  
**Answer:** No. They are specialized debugger/VM tooling mechanisms with their own operating conditions and permissions.

**Completion criteria:** you can explain the difference between **field – formal parameter – local variable**, run two compilations producing different `isNamePresent()` results, identify **MethodParameters** and **LocalVariableTable** when reading bytecode, and know when a debugger or class-file tooling is required instead of trying to force Reflection.

## 12. Authoritative References

- [Java SE: `java.lang.reflect.Parameter` and `isNamePresent()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html) — semantics of parameter names via MethodParameters.
- [Java SE: `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html) — shared API for Method and Constructor.
- [JDK `javac` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — `-parameters`, `-g`, `-g:vars` options.
- [JVMS, Class File Format §4.7](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html) — MethodParameters, LocalVariableTable, LocalVariableTypeTable.
- [Java SE: `com.sun.jdi` package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/package-summary.html) — debugging mechanism outside Core Reflection.

Debug information is a useful data source when present and used for its intended purpose; **it is not a guarantee that default Reflection APIs can recover the names or values of all local variables in a Java method**.