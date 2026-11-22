# `MethodModel`, `CodeModel`, and selecting the right method by name and descriptor

When building a Java instrumentation agent or a bytecode reading/modifying tool, **selecting the wrong method** can cause serious bugs: modifying the wrong overload, modifying a compiler-generated bridge method by mistake, or attempting to replace the `Code` of an `abstract` method. The Java **Class-File API** helps read `.class` structures as strongly typed models. At the method level, the two key models are **`MethodModel`** and **`CodeModel`**.

The first rule to remember:

> **Select a method in a class file using both `methodName` and the *method descriptor*.** Comparing only a name like `process` is not enough, because a class can have multiple overloads with the same name; the JVM descriptor also includes the return type.

This article walks through reading `ClassModel.methods()`, looking up by name and descriptor, traversing from `MethodModel` down to `CodeModel`, handling cases without `Code`, and applying selection predicates to a bytecode transformation pipeline.

## 1. JDK version and API scope

The API resides in the **`java.lang.classfile`** package, part of the `java.base` module. It was introduced as a preview in JDK 22 (JEP 457), second preview in JDK 23 (JEP 466), and **standardized in JDK 24 (JEP 484)**.

| JDK | Usage |
|---|---|
| 17–21 | **No** public `java.lang.classfile` yet to compile this example; use a library like ASM if you need to process class files on these JVMs |
| 22–23 | The API is in **preview** state, signatures/usage may differ from the standard version; requires the corresponding preview configuration |
| **24+** | `java.lang.classfile` is an official API; the model-reading snippets in this article use **JDK 24** and do not require `--enable-preview` |

You can still use `javac --release 17` to produce **target class files compatible with Java 17**, and then use **an analysis program running on JDK 24** to read them. These are two separate things: **the bytecode version being analyzed** and **the JDK running the analysis tool**.

## 2. Model tree from class to code

Diagram:

~~~text
bytes of a .class file
          │
          ▼ ClassFile.of().parse(bytes or Path)
      ClassModel
          │
          └── methods() : List<MethodModel>
                 │
                 ├── methodName() : Utf8Entry
                 ├── methodType() : Utf8Entry (JVM descriptor)
                 ├── methodTypeSymbol() : MethodTypeDesc
                 ├── flags() : AccessFlags
                 └── code() : Optional<CodeModel>
                                │
                                ├── CodeElement in order
                                │   ├── Instruction (executable JVM opcode)
                                │   └── PseudoInstruction (label, line, ...)
                                ├── exceptionHandlers()
                                └── Code-related attributes
~~~

| Model | Description | When to use |
|---|---|---|
| `ClassModel` | A parsed class file, containing metadata, fields, methods, and class attributes | Finding methods in the right class |
| `MethodModel` | A method in the class file's `methods` table; contains name, descriptor, flags, and method elements | **Selecting the exact overload** and reading method-level attributes |
| `CodeModel` | Contents of a method's `Code` attribute; an ordered sequence of `CodeElement`s | Analyzing or transforming bytecode instructions |
| `Instruction` | An actual JVM instruction, with `opcode()` | Distinguishing opcodes from labels and metadata |
| `ClassTransform`/`MethodTransform`/`CodeTransform` | Transformations at the class/method/code level | Passing only the selected method into the modification pipeline |

`ClassModel.methods()` returns a list of `MethodModel`. **`MethodModel` is not the same as `CodeModel`**: the name, flags, and descriptor live at the method level, while the bytecode body (if present) lives in `CodeModel`.

`ClassFile.parse(...)` builds the model to **analyze bytes**; it does not invoke `main`, does not automatically execute code in the `.class`, and is not `ClassLoader#defineClass`. Models may be parsed/enriched lazily (*lazy*), so malformed data errors can still surface when deeply accessing an element.

## 3. Reading `MethodModel` with the right data types

The JDK 24 API of `MethodModel` provides these accessors:

~~~java
Utf8Entry methodName();
Utf8Entry methodType();
MethodTypeDesc methodTypeSymbol();
Optional<CodeModel> code();
AccessFlags flags();
~~~

These are **API description signatures**, not a standalone runnable Java class. Note: `methodName()` and `methodType()` return **`Utf8Entry`**, not `String`. You can retrieve the string content using `.stringValue()` or compare directly against a string using `.equalsString(...)`:

~~~java
boolean sameName = method.methodName().equalsString("calculate");
boolean sameDescriptor = method.methodType().equalsString("(I)I");

if (sameName && sameDescriptor) {
    // This is the exact method with the requested name + descriptor.
}
~~~

In this snippet, `method` is a `MethodModel` obtained from `ClassModel.methods()`. `equalsString` avoids constructing an intermediate `String` just for comparison; `stringValue()` is suitable for logging.

If you want to work with a structured descriptor instead of a string:

~~~java
import java.lang.constant.MethodTypeDesc;

MethodTypeDesc wanted = MethodTypeDesc.ofDescriptor("(I)I");
boolean matches = method.methodName().equalsString("calculate")
        && method.methodTypeSymbol().equals(wanted);
~~~

This is also **an illustrative snippet inside a method**; both `method` and `wanted` must be in an appropriate scope. `MethodTypeDesc.ofDescriptor` represents the descriptor as a symbolic method type, and from the symbolic descriptor you can call `.descriptorString()` to output the JVM string.

## 4. What is a JVM method descriptor?

The structure of a method descriptor is:

~~~text
(parameter_type_1 parameter_type_2 ...) return_type
~~~

**There are no commas, spaces, parameter names, Java-style package names, or `public`/`static` keywords.** The descriptor stored in a class file contains **all parameter types and the return type**, whereas overloading rules in *Java source* are based on the parameter list (not differing solely by return type).

Fundamental symbols:

| Java | Descriptor |
|---|---|
| `byte` | `B` |
| `char` | `C` |
| `double` | `D` |
| `float` | `F` |
| `int` | `I` |
| `long` | `J` |
| `short` | `S` |
| `boolean` | `Z` |
| `void` (used only in the return position) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| `int[][]` | `[[I` |

Examples:

| Java declaration | Method name in `.class` | Descriptor |
|---|---|---|
| `int calculate(int x)` | `calculate` | `(I)I` |
| `long calculate(long x)` | `calculate` | `(J)J` |
| `String calculate(String s)` | `calculate` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `void log(String s, int n)` | `log` | `(Ljava/lang/String;I)V` |
| `String[] copy(String[] a)` | `copy` | `([Ljava/lang/String;)[Ljava/lang/String;` |
| `void accept(int[][] data)` | `accept` | `([[I)V` |
| `static void main(String[] args)` | `main` | `([Ljava/lang/String;)V` |
| No-argument constructor | `<init>` | `()V` |
| Static initializer | `<clinit>` | `()V` |

Object names use forward slashes `/` according to the **internal name** inside `L...;`; do not use `Ljava.lang.String;`. Array dimensions are represented by the number of `[` characters.

Common incorrect examples:

~~~text
Wrong: calculate(int):int
Wrong: calculate(I):I
Wrong: calculate(Ljava.lang.String;)Ljava.lang.String;
Right: calculate(I)I
Right: calculate(Ljava/lang/String;)Ljava/lang/String;
~~~

The final notation in the `Right` lines is **name + descriptor for human readability**, not a single descriptor string. When calling the API, pass `name = "calculate"` and `descriptor = "(I)I"` as **two separate arguments**.

## 5. Why compare both name and descriptor?

A valid class can have multiple `MethodModel`s that all satisfy `methodName().equalsString("calculate")`:

~~~java
public static int calculate(int value) { return value + 1; }

public static long calculate(long value) { return value + 2L; }

public static String calculate(String value) {
    return "[" + value + "]";
}
~~~

All three share the name `calculate`, but their descriptors are respectively:

~~~text
(I)I
(J)J
(Ljava/lang/String;)Ljava/lang/String;
~~~

If instrumentation code only does:

~~~java
model.methods().stream()
        .filter(method -> method.methodName().equalsString("calculate"))
        .findFirst();
~~~

then it **selects the first matching element in class-file order**, which may not be the overload you intended to modify. `findFirst()` does not provide any business rule for picking the right overload.

**Always pair the name condition with the descriptor**:

~~~java
model.methods().stream()
        .filter(method -> method.methodName().equalsString("calculate")
                && method.methodType().equalsString("(I)I"))
        .findFirst();
~~~

In a valid class file, the **name + descriptor** pair uniquely identifies a method within a class; when performing instrumentation, you should still check **match count = 1** and report a clear error when the target is missing, rather than silently skipping it. Do not use "name + parameter count" as a substitute for the descriptor: two overloads with the same number of parameters but different types are still different methods.

## 6. JDK 24 hands-on: parsing `.class` and selecting the exact overload

This lab uses **three independent Java files** with matching file/class names. Use JDK **24 or newer** to run `InspectMethods`; `Sample` and `Contract` are compiled with `--release 17` to demonstrate that the API can read older class file versions.

Structure:

~~~text
classfile-lab/
├── Sample.java
├── Contract.java
├── InspectMethods.java
└── out/                 generated during compilation
~~~

### 6.1. `Sample.java`

~~~java
public final class Sample {
    public static int calculate(int value) {
        return value + 1;
    }

    public static long calculate(long value) {
        return value + 2L;
    }

    public static String calculate(String value) {
        return "[" + value + "]";
    }

    public static int combine(int left, int right) {
        return left + right;
    }
}
~~~

Three overloads differ by parameter type, while also having descriptors corresponding to their return types. `Sample` has a default constructor generated by `javac`, meaning the class file will also contain `<init>()V` even though the example does not write an explicit constructor.

### 6.2. `Contract.java`

~~~java
public interface Contract {
    int calculate(int value);
}
~~~

This interface method is `abstract` and **has no `Code` body**. It will be used to test the case where `MethodModel.code()` returns `Optional.empty()`.

### 6.3. `InspectMethods.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeModel;
import java.lang.classfile.Instruction;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

public final class InspectMethods {
    private static boolean matches(
            MethodModel method, String name, String descriptor) {
        return method.methodName().equalsString(name)
                && method.methodType().equalsString(descriptor);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: InspectMethods <file.class> <name> <descriptor>");
        }

        String name = args[1];
        String descriptor = args[2];

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));

        List<String> candidates = model.methods().stream()
                .filter(method -> method.methodName().equalsString(name))
                .map(method -> method.methodName().stringValue()
                        + method.methodType().stringValue())
                .sorted()
                .toList();

        for (String candidate : candidates) {
            System.out.println("candidate=" + candidate);
        }

        List<MethodModel> matches = model.methods().stream()
                .filter(method -> matches(method, name, descriptor))
                .toList();

        if (matches.size() != 1) {
            throw new IllegalArgumentException(
                    "Expected exactly one method, found " + matches.size());
        }

        MethodModel selected = matches.get(0);
        System.out.println("selected="
                + selected.methodName().stringValue()
                + selected.methodType().stringValue());

        Optional<CodeModel> code = selected.code();
        System.out.println("code=" + code.isPresent());

        code.ifPresent(body -> {
            long instructions = body.elementStream()
                    .filter(element -> element instanceof Instruction)
                    .count();
            System.out.println("instructions=" + instructions);
            System.out.println("handlers="
                    + body.exceptionHandlers().size());
        });
    }
}
~~~

**Selection breakdown:**

1. `ClassFile.of().parse(Path.of(args[0]))` reads the class file into a `ClassModel`.
2. `model.methods()` retrieves **all methods**. We print the list of candidates with the same name, **sorted** so the demo output is deterministic and easy to inspect.
3. `matches` compares **both name and descriptor** via `Utf8Entry.equalsString`.
4. If there is exactly one match, we obtain the target `MethodModel`.
5. `selected.code()` returns `Optional<CodeModel>`; therefore, the example **does not call `get()` blindly**.
6. `CodeModel.elementStream()` contains ordered `CodeElement`s. The `element instanceof Instruction` filter counts only **real opcodes**, avoiding counting labels, line numbers, and pseudo-instructions as opcodes.
7. `exceptionHandlers()` reads the list of exception-handling entries of the `Code` attribute, independent of instruction counting.

For class files from `javac`, `abstract` or `native` methods have no `Code` attribute, so `code()` returns empty. This case is completely valid; do not treat it as a parse error.

### 6.4. Compile and run

From the `classfile-lab` directory, create `out`. Bash/Git Bash:

~~~bash
mkdir -p out
~~~

Or PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Then use **JDK 24+**:

~~~bash
javac --release 17 -d out Sample.java Contract.java
javac -d out InspectMethods.java
java -cp out InspectMethods out/Sample.class calculate '(I)I'
~~~

Note: `--release 17` **applies only to `Sample` and `Contract`**. If you add `--release 17` when compiling `InspectMethods`, the Java compiler will report that the `java.lang.classfile` package cannot be found, because it is only a standard API starting in JDK 24.

**Expected output** when practicing with JDK 24 `javac` and the sample classes above:

~~~text
candidate=calculate(I)I
candidate=calculate(J)J
candidate=calculate(Ljava/lang/String;)Ljava/lang/String;
selected=calculate(I)I
code=true
instructions=4
handlers=0
~~~

Explanation of `instructions=4`: `javac` typically compiles `return value + 1` into the opcodes `iload_0`, `iconst_1`, `iadd`, `ireturn`. The other two `candidate` entries with the same name but different descriptors still appear in the list so you can see the exact filtering condition.

Try changing the target descriptor:

~~~bash
java -cp out InspectMethods out/Sample.class calculate '(J)J'
~~~

`selected` will be `calculate(J)J`. The opcode count may vary by overload, so you should not apply the `instructions=4` result of `(I)I` to every method.

Try a method without `Code`:

~~~bash
java -cp out InspectMethods out/Contract.class calculate '(I)I'
~~~

Output:

~~~text
candidate=calculate(I)I
selected=calculate(I)I
code=false
~~~

The application **does not print** `instructions` or `handlers` when `code()` is empty. This is intentional behavior from `Optional.ifPresent`, not because the JVM has "0 instructions" in an abstract method.

Try passing `(D)D` to search for a non-existent overload. The demo throws `IllegalArgumentException` with `Expected exactly one method, found 0` instead of mistakenly picking `calculate(int)`.

## 7. Using `MethodTypeDesc` to avoid malformed descriptor comparisons

For a fixed set of methods, comparing two `Utf8Entry` instances with `equalsString` is very direct. If constructing descriptors dynamically, `MethodTypeDesc` is more useful:

~~~java
import java.lang.constant.MethodTypeDesc;

MethodTypeDesc target =
        MethodTypeDesc.ofDescriptor("(Ljava/lang/String;)Ljava/lang/String;");

boolean selected = method.methodName().equalsString("calculate")
        && method.methodTypeSymbol().equals(target);
~~~

The snippet above is placed **inside a method that already has a `MethodModel method` variable**, not as a standalone program. This approach has two advantages: it requires the descriptor to have valid JVM syntax and turns the second condition into comparing a symbolic method type. `method.methodTypeSymbol().descriptorString()` can be used to log the descriptor.

A common mistake is using a **Java source** representation like `"(java.lang.String)java.lang.String"` as the argument to `MethodTypeDesc.ofDescriptor`. This factory requires JVM syntax: `"(Ljava/lang/String;)Ljava/lang/String;"` **without a leading space**.

If you want to build a descriptor symbolically from its components:

~~~java
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;

MethodTypeDesc target = MethodTypeDesc.of(
        ClassDesc.of("java.lang.String"),
        ClassDesc.of("java.lang.String"));
System.out.println(target.descriptorString());
~~~

This is a code snippet inside a method. Stdout is:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

`MethodTypeDesc.of(returnType, parameterTypes...)` takes the **return type first**, followed by the parameter types. This differs from the display order of a descriptor string, where the return type comes **after the `)`**.

## 8. Why can't the return type be omitted when matching?

The Java language does not allow declaring two overloads in **the same class** that differ only by return type:

~~~java
int get();
String get();
~~~

The two lines above are **an illustration of invalid Java code**, not a snippet to compile. However, the JVM identifies a method by **name + descriptor**, and the descriptor includes the **return type**.

A common real-world case is a **bridge method** generated by the compiler for a generic interface or covariant return:

~~~java
interface Provider<T> {
    T get();
}

final class StringProvider implements Provider<String> {
    @Override
    public String get() {
        return "ok";
    }
}
~~~

When `javac` generates `StringProvider.class`, the class typically has both:

~~~text
get()Ljava/lang/String;    // method implementing the logic
get()Ljava/lang/Object;    // synthetic bridge, forwarding to the method above
~~~

The second method carries the `ACC_BRIDGE` and `ACC_SYNTHETIC` flags. If you instrument only by the name `get`, you might select the **bridge** instead of the intended implementation method. If you instrument both without care, you may record **two measurements** for a single call.

To observe:

~~~bash
javac --release 17 -d out StringProvider.java
javap -p -v out/StringProvider.class
~~~

For the snippet above, save `Provider` and `StringProvider` in **the file `StringProvider.java`** (neither is declared `public`); or split them into two files by name to compile. In the `javap -v` output, inspect the **name, descriptor, and flags** of each method. When selecting the target to modify, using only `get` is insufficient; you must specify `()Ljava/lang/String;` or `()Ljava/lang/Object;`.

Beyond bridge methods, generic information such as `List<String>` usually lives in the `Signature` attribute, whereas **JVM descriptors use erased types (*erasure*)**, for example `Ljava/util/List;`. `CodeModel` and method descriptors describe compiled bytecode, and do not restore the original Java source syntax.

## 9. What does `CodeModel` allow you to read?

`MethodModel.code()` returns `Optional<CodeModel>`. When present, `CodeModel` describes the **`Code`** attribute in `method_info`, which contains information such as instructions, the exception handler table, and auxiliary attributes:

~~~text
MethodModel
    │
    ├── name, descriptor, access flags, attributes
    └── CodeModel (if present)
            ├── Instruction: executable JVM opcode
            ├── LabelTarget / LineNumber: pseudo-instruction
            ├── exceptionHandlers(): exception table entries
            └── Code attributes: e.g., StackMapTable (attribute access)
~~~

How to count/display opcodes:

~~~java
CodeModel body = selected.code().orElseThrow();

body.elementStream()
        .filter(element -> element instanceof Instruction)
        .map(element -> ((Instruction) element).opcode())
        .forEach(System.out::println);
~~~

This is **an excerpt using the `MethodModel selected` variable chosen in the previous step**. `Instruction.opcode()` returns an `Opcode` enum identifying the instruction. The printed output can vary depending on the compiler or specific code; you should not try to guess bytecode offsets from element indices in the stream.

Why is filtering needed? **`CodeElement` is not synonymous with `Instruction`.** Labels and line numbers can sit between opcodes in the model; the element count or index in `elementList()` **is not a bytecode PC offset**. When instrumenting, you must keep jump labels, exception ranges, stack-map frames, and code attributes consistent with the final bytes.

`body.exceptionHandlers()` yields the exception-catching entries in the `Code` attribute. A method without `try/catch` may have 0 handlers, but a compiled `finally` or `try-with-resources` can still generate handlers even though the source does not appear to have a direct `catch`.

Do not confuse `CodeModel.exceptionHandlers()` with `throws` declared on a method: `throws` is represented by the `Exceptions` attribute at the method level, not runtime exception-handling entries.

## 10. From a method-selection predicate to Class-File transformation

Once you have a **name + descriptor** predicate, you can reuse it with `ClassTransform.transformingMethodBodies(...)` to direct the transformation **only into the `Code` of the target method**:

~~~java
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;

ClassTransform selective = ClassTransform.transformingMethodBodies(
        method -> method.methodName().equalsString("calculate")
                && method.methodType().equalsString("(I)I"),
        CodeTransform.ACCEPT_ALL
);

byte[] rebuilt = ClassFile.of().transformClass(model, selective);
~~~

**This is a fragment placed inside a method that already has `ClassModel model`**, not a standalone program. `CodeTransform.ACCEPT_ALL` is an **identity code transform**: it passes through code elements without **intentionally changing logic**. The example only demonstrates how to apply **the exact method filter** in the pipeline. To actually insert logging or change logic, you need to replace `ACCEPT_ALL` with an appropriate `CodeTransform`, preserving all class-file invariants.

`ClassTransform.transformingMethods(Predicate<MethodModel>, MethodTransform)` is the option when you need to process **the entire method model**; `transformingMethodBodies` only processes the **Code** of methods selected by the predicate, forwarding other elements through the builder per the API contract. For `abstract`/`native` methods, there is no `Code` to transform; you should check `method.code().isPresent()` if your business logic requires a method body to exist.

A suitable workflow for instrumentation:

1. Parse **the exact bytes of the right class** (`ClassModel`), without ambiguous name-only matching.
2. Select the method by **name + full JVM descriptor**, considering `ACC_BRIDGE` and `ACC_SYNTHETIC` flags.
3. Distinguish methods with `Code` from methods without `Code`.
4. Apply `ClassTransform`/`MethodTransform`/`CodeTransform` only to the intended target.
5. Verify the output bytes (`ClassFile.verify(...)` returns a list of errors if any) and test loading the class in a JVM.
6. If used as a Java agent: verify that the JVM supports the agent's class file version—do not load JDK 24-compiled code into a Java 17 JVM and expect the API to exist.

When modifying running methods with `Instrumentation.redefineClasses` or `retransformClasses`, there are also **class redefinition** constraints (you cannot arbitrarily add/remove fields/methods or change signatures) and compatible transformer requirements. The Class-File API helps build bytes; it **does not by itself grant** instrumentation capabilities.

## 11. Cross-checking with `javap` and handling missing methods

Useful commands:

~~~bash
javap -p -s out/Sample.class
javap -p -c out/Sample.class
javap -p -v out/Sample.class
~~~

- `-p`: displays non-public members as well.
- `-s`: displays JVM **descriptors**, useful for copying accurately into predicates.
- `-c`: disassembles opcodes.
- `-v`: class file details, flags, constant pool, attributes, and code.

If a lookup returns 0 results:

- Ensure you have **the right `.class` file**; different class loaders can have classes with the same name but different bytes.
- Print all `methodName() + methodType()` in the right `ClassModel` to see the actual overloads.
- Check `int` (`I`) vs `long` (`J`), `String` (`Ljava/lang/String;`) vs `String[]` (`[Ljava/lang/String;`).
- Check `void` (`V`), return type notation, parentheses `(` `)`, and the trailing `;` on reference types.
- If it is a generic method, use **the erased descriptor**, do not copy type parameters like `List<String>` from source.
- If the target is a constructor, look for **`<init>`** instead of the Java class name; for a static initializer, the name is **`<clinit>`**.

If a method is found but `code()` is empty, check its flags. `abstract` or `native` methods validly **have no `Code`**. If 1 method is found but the tool still modifies the wrong target, check **the `ACC_BRIDGE`/`ACC_SYNTHETIC` flags**, the right class loader, and whether the predicate was actually used in the transform.

## 12. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Filtering only by `methodName` | Picks the wrong overload or a bridge method | Match **both name and descriptor** |
| Comparing `method.methodName().equals("calculate")` | `Utf8Entry` is not a String | Use `equalsString("calculate")` |
| Using `"(int)int"` as a descriptor | Not valid JVM syntax | Use `"(I)I"` |
| Using dots in an object descriptor | String does not match | `Ljava/lang/String;` |
| Omitting the return type from the descriptor | Loses method identity information at the bytecode level | Descriptor must include the return type |
| Matching generic methods with `List<String>` syntax | Does not match the erased descriptor | Check `javap -s`, use `Ljava/util/List;` |
| Calling `method.code().get()` on an abstract method | `NoSuchElementException` | Handle `Optional.empty()` |
| Treating every `CodeElement` as an opcode | Miscounts due to pseudo-instructions | Filter for `Instruction` |
| Treating `methods()` order as a target selection rule | Breaks easily when the compiler changes order | Filter uniquely by name + descriptor |
| Trying to compile API examples with `--release 17` | `java.lang.classfile` does not exist in release 17 | Run the analysis tool on **JDK 24+** |
| Modifying code without verifying bytes | May fail verification/stack map/handlers | Verify model/bytes and test in a JVM |
| Parsing a class and assuming code has been executed | Misjudges side effects | Distinguish **parsing a file** from **loading/executing a class** |

## 13. Self-check questions

1. **How do `MethodModel` and `CodeModel` differ?** `MethodModel` contains the method's identifier, flags, and elements; `CodeModel` contains the `Code` attribute if the method has a body.
2. **There are 3 `calculate` overloads. Is comparing only the name enough to identify the right method?** No; you must compare the descriptor as well.
3. **What is the descriptor of `int calculate(int)`?** `(I)I`.
4. **What is the descriptor of `String calculate(String)`?** `(Ljava/lang/String;)Ljava/lang/String;`.
5. **Why shouldn't `MethodModel.methodType()` be compared against `(int)int`?** Because it represents a **JVM method descriptor**, not Java source syntax.
6. **What does `MethodModel.code()` return for an interface abstract method?** `Optional.empty()`.
7. **To count opcodes in `CodeModel`, can you use `elementList().size()`?** No; the list also includes pseudo-instructions.
8. **`StringProvider` has a `get()` method returning `String` and a synthetic bridge returning `Object`; how should you select?** By **both name and descriptor**, while also checking flags if needed.
9. **Does `java.lang.classfile` exist in JDK 17?** No. It is an official API starting in JDK 24.
10. **Should `ClassTransform.transformingMethodBodies` filter by bare name?** No; use a name + descriptor predicate to preserve the remaining overloads.
11. **Two class loaders have the same class name. Is knowing only the class name enough to decide which bytes to instrument?** No; you must identify **the right class loader/definition** when integrating with instrumentation.
12. **Does `ClassFile.verify(...)` returning an empty list prove that application logic is correct?** No; it is a class-file verification step, and behavioral testing is still required.

### Official documentation

- [OpenJDK JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484).
- [Java SE 24 — `ClassFile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `transformClass`, `verify`.
- [Java SE 24 — `ClassModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html): `methods()`.
- [Java SE 24 — `MethodModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html): `methodName`, `methodType`, `methodTypeSymbol`, `code`.
- [Java SE 24 — `CodeModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeModel.html): `CodeElement` and handler table.
- [Java SE 24 — `Utf8Entry`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/constantpool/Utf8Entry.html): `stringValue`, `equalsString`.
- [Java SE 24 — `ClassTransform`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `transformingMethods`, `transformingMethodBodies`.
- [Java SE 24 — `Instruction`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/Instruction.html): `opcode()`.
- [Java VM Specification — Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html#jvms-4.3.3).

**Key takeaway:** `ClassModel` finds **the right class**; `MethodModel` selects **the right method by `name + descriptor`**; `CodeModel` exists only when the method has a `Code` section; and `CodeTransform` is the step that performs controlled bytecode changes. To instrument safely, identify the exact target before modifying any instruction.