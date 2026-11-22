# ClassBuilder, MethodBuilder, CodeBuilder, and How to Preserve Unchanged Parts

The **Java Class-File API** (package `java.lang.classfile`) enables reading, generating, and transforming `.class` files without manually handling every offset in the constant pool or bytecode. When instrumenting Java, the common operation is not rebuilding the entire class from scratch, but **changing only a few elements and forwarding all remaining elements**.

The focus of this lesson is the three builder levels:

- `ClassBuilder` builds a **class file** from `ClassElement`s: methods, fields, class attributes, and related elements.
- `MethodBuilder` builds **a method** from `MethodElement`s, especially `CodeModel` and method attributes.
- `CodeBuilder` builds the **bytecode body** from `CodeElement`s: JVM instructions, labels, and metadata elements represented at the code level.

The key to preserving unchanged parts is: **at each level, call `builder.with(element)` for elements that do not need modification**. Only descend into deeper levels using `transformMethod(...)` and `transformCode(...)` when you genuinely want to change a specific method or instruction.

> **Version requirement:** The Class-File API became an official API in **JDK 24** (JEP 484). The Java examples run directly with `javac` and `java` from **JDK 24 or later**, **without `--enable-preview`**. JDK 17/21 do not have this stable API; do not copy the examples to JDK 17 and expect them to compile. JDK 22/23 preview builds may have different signatures.

## 1. Mental Model: Read the Model, Feed Elements into the Builder

A class file has a nested structure:

~~~text
Class file (ClassModel)
  |-- class metadata / attributes (ClassElement)
  |-- field (FieldModel, also a ClassElement)
  |-- method (MethodModel, also a ClassElement)
  |      |-- method metadata / attributes (MethodElement)
  |      |-- body (CodeModel, also a MethodElement)
  |               |-- instruction (CodeElement)
  |               |-- label, line info, and code metadata (CodeElement)
  |-- other class-level elements
~~~

Models are an **immutable view** of the class file; parsing is usually **lazy**, so some format errors may surface when accessing deeper parts of the model. Builders are not objects to be kept arbitrarily as long-lived shared state: typically the API passes a builder to a `build` or `transformClass` callback, and you emit elements into the builder within that callback.

| Level | Model | Element Type | Builder | Transform |
| --- | --- | --- | --- | --- |
| Class | `ClassModel` | `ClassElement` | `ClassBuilder` | `ClassTransform` |
| Method | `MethodModel` | `MethodElement` | `MethodBuilder` | `MethodTransform` |
| Code | `CodeModel` | `CodeElement` | `CodeBuilder` | `CodeTransform` |
| Field | `FieldModel` | `FieldElement` | `FieldBuilder` | `FieldTransform` |

Minimal read-and-transform flow:

~~~java
ClassFile api = ClassFile.of();
ClassModel oldClass = api.parse(originalBytes);
byte[] newBytes = api.transformClass(oldClass,
        (classBuilder, element) -> classBuilder.with(element));
~~~

The snippet above is a **code fragment**, requiring an existing variable `originalBytes` of type `byte[]`. It emits **every class element** into `ClassBuilder` to reconstruct a model-equivalent class definition. It **does not guarantee `Arrays.equals(originalBytes, newBytes)`**: constant pool ordering, representation structure, stack maps, or attributes may be processed according to the API's options.

## 2. ClassBuilder: Keeping Classes, Fields, Methods, and Attributes Unchanged

`ClassBuilder` has two important groups of operations:

1. **Adding/creating** new members: `withField(...)`, `withMethod(...)`, `withMethodBody(...)`, `withFlags(...)`, `withSuperclass(...)`, etc.
2. **Forwarding or transforming** members of the original class: `with(ClassElement)`, `transformField(FieldModel, FieldTransform)`, `transformMethod(MethodModel, MethodTransform)`.

When reading a `ClassModel`, if only **one** method needs modification, the safe pattern is:

~~~java
ClassTransform transform = (classBuilder, classElement) -> {
    if (classElement instanceof MethodModel method
            && method.methodName().stringValue().equals("compute")) {
        classBuilder.transformMethod(method, methodTransform);
    } else {
        classBuilder.with(classElement);
    }
};
~~~

This is an **illustrative snippet**, not a standalone program; `methodTransform` must be created beforehand. It means:

- If it is the `compute` method, open that method with `MethodBuilder` and apply a method-level transformation.
- If it is a field, constructor, another method, class attribute, version, or another element, **forward the element as-is at the model level** using `with(classElement)`.
- Do not write only the `if (matching method) ...` branch and omit the `else` branch: in the *element stream* transformation model, **failing to emit an element into the builder drops that element** from the output.

### Why Use transformClass Instead of Building from Scratch?

`ClassFile.build(ClassDesc, Consumer<ClassBuilder>)` creates a class using elements you supply yourself; it is suitable for code generation. Meanwhile, `ClassFile.transformClass(ClassModel, ClassTransform)` takes the **old class as its source**, which is convenient for localized transformations. The latter option can also leverage the **original class's constant pool** to preserve and optimize the handling of unchanged parts.

If you manually `build` the entire class again and forget to pass constructors, annotations, generic signatures, fields, interfaces, or attributes into the builder, they may **disappear from the new class file**. When instrumentation requires preserving the public API, that is a serious bug.

## 3. MethodBuilder: Descending Only into the Method to Be Modified

A `MethodModel` consists of multiple method-level elements; `CodeModel` is only **one of those elements**. `MethodBuilder` supports:

| API | Purpose |
| --- | --- |
| `with(MethodElement)` | Emit an unchanged method element into the new method |
| `withFlags(...)` | Set access flags (with restrictions on `ACC_STATIC`) |
| `withCode(Consumer<CodeBuilder>)` | Generate a new method body |
| `transformCode(CodeModel, CodeTransform)` | Transform an **existing** code body and keep unmodified code parts |

Processing pattern:

~~~java
MethodTransform methodTransform = (methodBuilder, methodElement) -> {
    if (methodElement instanceof CodeModel code) {
        methodBuilder.transformCode(code, codeTransform);
    } else {
        methodBuilder.with(methodElement);
    }
};
~~~

This is also a **code fragment**, requiring a `CodeTransform codeTransform`. If the method has annotations, attributes, or other method-level metadata, the `else` branch forwards them. If the method has a `CodeModel`, call `transformCode` so you do not have to manually recreate all instructions and labels.

**Note on flags:** When creating a method from the original class, `ClassBuilder.transformMethod(method, transform)` takes the name, descriptor, and flags from the source method. A method's `ACC_STATIC` flag cannot be arbitrarily changed after `MethodBuilder` has been created; the API enforces that restriction. When creating a new method with `withMethod(...)`, pass the right flags from the start.

### Differences Between withMethod, withMethodBody, and transformMethod

- `withMethod(name, descriptor, flags, handler)`: creates a new method and gives the handler access to `MethodBuilder` to configure both method attributes and code.
- `withMethodBody(name, descriptor, flags, codeHandler)`: a convenience method to create a new method **requiring only flags and a Code attribute**, without custom method attributes.
- `transformMethod(originalMethod, transform)`: builds a new method from a **source method**, able to preserve any method element that is not targeted.

Do not use `withMethodBody` to replace an entire existing method if you need to preserve annotations, the `Exceptions` attribute, signatures, and other metadata that you have not explicitly re-added. In the hands-on example below, we use `transformMethod` and then `transformCode` to replace **a single** opcode.

## 4. CodeBuilder: Keeping All Unrelated Instructions Intact

`CodeModel` represents a method's code body. When iterating over it, you may encounter:

- Actual JVM instructions such as `iload`, `iadd`, `isub`, `ireturn`, `invokevirtual`.
- Elements representing **labels, line numbers, exception handling, and local variable metadata**; these must not be arbitrarily dropped when reconstructing complex methods.
- Metadata elements attached to code regions represented by the Class-File API at the appropriate level.

`CodeBuilder` allows two kinds of operations:

- `codeBuilder.isub()`, `codeBuilder.iload(0)`, `codeBuilder.ireturn()`: **emit new instructions**.
- `codeBuilder.with(codeElement)`: **forward an existing code element** without rewriting it.

Example of replacing one opcode:

~~~java
CodeTransform replaceAdd = (codeBuilder, element) -> {
    if (element instanceof java.lang.classfile.instruction.OperatorInstruction op
            && op.opcode() == Opcode.IADD) {
        codeBuilder.isub();
    } else {
        codeBuilder.with(element);
    }
};
~~~

If the original method contains `iload_1; iload_2; iadd; ireturn`, the transform produces output equivalent to `iload_1; iload_2; isub; ireturn`. All other elements of `CodeModel` are passed to the builder.

This is an intentional change that **replaces a single arithmetic instruction**, preserving the stack shape of the example; it is not a general-purpose instrumentation strategy. In real methods, replacing or inserting instructions can affect stack depth, branch targets, stack maps, and exception handlers. You must understand JVM rules and verify the transformed class.

### Four Ways to Handle an Element in a Transform

| Behavior in Callback | Meaning |
| --- | --- |
| `builder.with(element)` | Keep the element in the output model |
| Emit a new element and do **not** emit the original element | Replace the element |
| Emit no element | Remove the element |
| Emit multiple elements | One source element can become multiple output elements |

That is the *flatMap* nature of the Class-File API. **There is no guarantee of automatically keeping elements that the callback skips.** This differs from `ClassFileTransformer.transform(...)` in Java Instrumentation: if the agent callback returns `null`, the JVM understands that the agent **did not modify the class bytes at that step**. In contrast, callbacks for `ClassTransform`/`MethodTransform`/`CodeTransform` must **explicitly** emit the elements they want to keep.

## 5. Runnable JDK 24+ Example: Change One Instruction, Keep Fields and Other Methods

Goal: create an initial class with a field, a constructor, and two methods. Then use **all three—ClassBuilder, MethodBuilder, and CodeBuilder**—to modify only the `compute(int,int)` method, changing `iadd` to `isub`; all other class elements and method/code elements are forwarded.

This example **processes a .class file on disk**, without attaching to the JVM and without using `java.lang.instrument.Instrumentation`. This makes it easy to verify the class before integrating it into an agent.

### 5.1. File LessonTarget.java

Create the file `LessonTarget.java`:

~~~java
public class LessonTarget {
    private final int base = 7;

    public int compute(int a, int b) {
        return a + b;
    }

    public int untouched(int x) {
        return base + x;
    }
}
~~~

The class has a public default constructor, a `base` field, a `compute` method, and an `untouched` method. `javac` may optimize certain reads of a `final` field, but the class still has the field declaration and the two methods as shown above.

### 5.2. File ClassFileKeepDemo.java

Create the file `ClassFileKeepDemo.java` in the same directory:

~~~java
import java.lang.classfile.*;
import java.lang.classfile.instruction.OperatorInstruction;
import java.lang.reflect.AccessFlag;
import java.nio.file.*;
import java.net.URL;
import java.net.URLClassLoader;

public class ClassFileKeepDemo {
    public static void main(String[] args) throws Exception {
        ClassFile api = ClassFile.of();
        byte[] original = Files.readAllBytes(Path.of("LessonTarget.class"));
        ClassModel model = api.parse(original);

        byte[] updated = api.transformClass(model, (classBuilder, element) -> {
            if (element instanceof MethodModel method
                    && method.methodName().stringValue().equals("compute")) {
                classBuilder.transformMethod(method, (methodBuilder, member) -> {
                    if (member instanceof CodeModel code) {
                        methodBuilder.transformCode(code, (codeBuilder, instruction) -> {
                            if (instruction instanceof OperatorInstruction operation
                                    && operation.opcode() == Opcode.IADD) {
                                codeBuilder.isub();
                            } else {
                                codeBuilder.with(instruction);
                            }
                        });
                    } else {
                        methodBuilder.with(member);
                    }
                });
            } else {
                classBuilder.with(element);
            }
        });

        Path output = Path.of("out");
        Files.createDirectories(output);
        Files.write(output.resolve("LessonTarget.class"), updated);

        System.out.println("sourceMethods=" + model.methods().size());
        System.out.println("rewrittenMethods=" + api.parse(updated).methods().size());
        System.out.println("verifyErrors=" + api.verify(updated).size());

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{output.toUri().toURL()}, null)) {
            Class<?> type = Class.forName("LessonTarget", true, loader);
            Object obj = type.getConstructor().newInstance();
            System.out.println("compute(8,3)="
                    + type.getMethod("compute", int.class, int.class)
                            .invoke(obj, 8, 3));
            System.out.println("untouched(5)="
                    + type.getMethod("untouched", int.class).invoke(obj, 5));
            System.out.println("fieldCount=" + type.getDeclaredFields().length);
        }

        byte[] generated = api.build(
                java.lang.constant.ClassDesc.of("GeneratedOps"),
                builder -> builder.withFlags(AccessFlag.PUBLIC)
                        .withMethodBody("twice",
                                java.lang.constant.MethodTypeDesc.ofDescriptor("(I)I"),
                                ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                                code -> code.iload(0).iconst_2().imul().ireturn()));
        System.out.println("generatedMethods=" + api.parse(generated).methods().size());
    }
}
~~~

**Decision points in the code:**

1. `ClassFile.of().parse(original)` returns a `ClassModel` to traverse.
2. `transformClass(model, ...)` provides a `ClassBuilder` and each `ClassElement` in turn.
3. Only when the element is a `MethodModel` named `compute` does the program use `classBuilder.transformMethod(...)`. The constructor, `base` field, `untouched` method, and class-level metadata all go through `classBuilder.with(element)`.
4. At the `MethodBuilder` level, only `CodeModel` is passed to `transformCode(...)`; the remaining method elements go through `methodBuilder.with(member)`.
5. At the `CodeBuilder` level, only the `IADD` instruction is changed to `ISUB`; all other code elements go through `codeBuilder.with(instruction)`.
6. `api.verify(updated)` checks the class file for errors. Then a `URLClassLoader` with a `null` parent loads the file from `out/`, avoiding the situation where the original class on the classpath has already been loaded by the application loader.
7. The `GeneratedOps` creation at the end is a **separate generation** example using `ClassBuilder.withMethodBody`/`CodeBuilder`; it does not modify `LessonTarget`. The generated class has only one static method and **no declared constructor**; the goal here is simply to demonstrate how the builder creates a new method.

**This example selects the method by name** because `LessonTarget` has only one `compute`. For real classes with overloads, you must also filter by **method descriptor** (via `MethodModel.methodTypeSymbol()` or the corresponding descriptor data) to avoid accidentally transforming another method with the same name.

### 5.3. Run Commands

Use the command line in the directory containing both files, with `javac`/`java` from **JDK 24+**:

~~~bash
javac LessonTarget.java ClassFileKeepDemo.java
java ClassFileKeepDemo
javap -c -p -classpath out LessonTarget
~~~

The program automatically creates the `out` directory to save the transformed `LessonTarget.class`, **without overwriting** the original in the current directory. Use a dedicated practice directory so old class files do not get mixed in.

**Exact stdout compiled/run on Zulu OpenJDK 24.0.2:**

~~~text
sourceMethods=3
rewrittenMethods=3
verifyErrors=0
compute(8,3)=5
untouched(5)=12
fieldCount=1
generatedMethods=1
~~~

Since `compute(8,3)` originally returned `11`, the result `5` proves that the addition opcode became subtraction. `untouched(5)` still returns `12`, the field count is still `1`, and the method count is still `3` (including the constructor). `verifyErrors=0` means the Class-File API's verification check found no errors in the output.

The `javap -c -p -classpath out LessonTarget` command should show the corresponding body:

~~~text
public int compute(int, int);
  Code:
     0: iload_1
     1: iload_2
     2: isub
     3: ireturn
~~~

Meanwhile, the `untouched` method still has `iadd`. This is how you verify that **the edit took effect at the exact target location**, rather than just looking at a boolean variable reporting success.

## 6. How Exactly Are Unchanged Parts Preserved?

It is important to distinguish between **preserving structural meaning** and **preserving byte-for-byte identity**.

### 6.1. Forwarding an Element Does Not Mean an Identical Binary

`builder.with(element)` transfers the element's content into the new class structure. The API may need to re-emit offsets, constant pool indices, stack maps, and position-dependent structures. The resulting class can still be equivalent in metadata and behavior even if the overall byte sequence of the file differs from the original.

Therefore:

- Verify the class name, superclass/interfaces, fields, methods, flags, required attributes, and relevant bytecode.
- Do not use `Arrays.equals(oldBytes, newBytes)` as the sole criterion for "keeping unchanged parts".
- For signing tools, hash-based caches, or publishing class artifacts, be aware that **rebuilding the file** can change the hash even when behavior is unchanged.
- Do not feed a rewritten class to the JVM just because the parser read it successfully; verify it with `ClassFile.verify` and corresponding execution/tests.

### 6.2. Constant Pool Sharing and Optimization

When calling `ClassFile.transformClass(...)`, the default mode is to share the original constant pool (`SHARED_POOL` option by default). This allows the API to reuse old entries and sometimes **bulk-copy** methods/attributes that do not need transformation, instead of parsing and regenerating every byte.

If you are trying to remove many components, you can consider `ClassFile.ConstantPoolSharingOption` to avoid retaining many unreferenced constant pool entries. However, "not sharing" does not mean all old elements are automatically deleted; the builder still processes whatever elements the transform emits.

### 6.3. Attributes, Annotations, and Debug Information

Standard attributes can belong to multiple levels:

| Example | Relevant Level | How to Avoid Accidental Loss |
| --- | --- | --- |
| `Signature`, `RuntimeVisibleAnnotations` | Class, field, or method depending on the attribute | Forward unmodified elements using `with(...)` at the right level |
| `Exceptions` | Method | Do not replace the entire method with `withMethodBody` unless you recreate the attribute |
| `Code` | Method | Use `transformCode` when only changing instructions |
| Line numbers, local variables | Code model | Do not drop the corresponding code elements; check options |
| `StackMapTable` | Code metadata linked to the JVM verifier | Let the Class-File API handle/generate it per options and verify the result |
| Custom/unknown attributes | The level where the attribute is declared | Check the mapper and processing options; verify preservation |

In JDK 24, the API has processing options for attributes (default `PASS_ALL_ATTRIBUTES`), debug elements (default `PASS_DEBUG`), line numbers (default `PASS_LINE_NUMBERS`), and stack maps (default `STACK_MAPS_WHEN_REQUIRED`). Unknown attributes that are not fully understood may contain **constant pool indices or bytecode offsets** that the tool does not know how to adjust after modification. If preserving a custom attribute is mandatory, use a compatible `AttributeMapper` and test the output with a tool that understands that format, rather than assuming raw byte copying will remain valid after every transformation.

## 7. Convenience APIs for Automatically Preserving Unchanged Parts

If you do not need manual callback control at all three levels, the Class-File API provides **transform combinators** to "descend" into the desired part while automatically forwarding other components.

### 7.1. Transforming Only the Body of Selected Methods

The same idea as the example above can be expressed as follows:

~~~java
CodeTransform changeAdd = (codeBuilder, element) -> {
    if (element instanceof java.lang.classfile.instruction.OperatorInstruction op
            && op.opcode() == Opcode.IADD) {
        codeBuilder.isub();
    } else {
        codeBuilder.with(element);
    }
};

ClassTransform changeOnlyCompute =
        ClassTransform.transformingMethodBodies(
                method -> method.methodName().stringValue().equals("compute"),
                changeAdd);

byte[] result = ClassFile.of().transformClass(model, changeOnlyCompute);
~~~

This is a **code snippet meant to be placed inside a Java program that has `ClassModel model` and imports `java.lang.classfile.*`**, not a complete standalone class. `transformingMethodBodies(predicate, transform)` transforms only the bodies of methods matching the predicate and passes all other class/method elements through to the builder. With this convenience API, the responsibility for keeping metadata unchanged is encapsulated in the combinator.

### 7.2. Lifting Across Levels

A `CodeTransform` can be lifted to the method and class levels:

~~~java
MethodTransform methodTransform = MethodTransform.transformingCode(changeAdd);
ClassTransform classTransform = ClassTransform.transformingMethods(methodTransform);
~~~

This is an **illustrative code snippet**, with `changeAdd` already defined above. This approach transforms the body of **every** method containing the matching opcode unless filtered further; therefore, do not use it indiscriminately in production if only one specific method should change.

The API also provides `ClassTransform.transformingMethods(predicate, methodTransform)`, `ClassTransform.transformingFields(fieldTransform)`, and other overloads, helping narrow down the exact layer of change without manually rewriting passthrough branches.

### 7.3. Composing Multiple Transforms

Transforms of the same kind can be chained with `andThen(...)`:

~~~java
CodeTransform combined = firstCodeTransform.andThen(secondCodeTransform);
~~~

This **illustrative snippet** requires two existing transform variables. Elements emitted by the first transform become the input to the second transform, in order. Do not arbitrarily swap the two steps if the second step depends on the output of the first.

When building a Java agent with multiple instrumentation steps, clarify the method/instruction filter conditions at each level and ensure transformers do not accidentally apply the same change repeatedly.

## 8. From Class-File API to Java Instrumentation

`java.lang.classfile` is a **bytecode processing** library, whereas `java.lang.instrument.ClassFileTransformer` is the mechanism for **receiving class bytes from the JVM and returning new class bytes**. The two APIs complement each other, but they are not identical.

Conceptual code example in a `ClassFileTransformer` implementation:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (!"com/example/OrderService".equals(className)) {
        return null; // Do not replace class bytes at this instrumentation step.
    }

    ClassFile api = ClassFile.of();
    ClassModel model = api.parse(classfileBuffer);
    return api.transformClass(model, myClassTransform);
}
~~~

This snippet is **illustrative code to be placed inside a class implementing `ClassFileTransformer`**, with `myClassTransform` already initialized to type `ClassTransform`; by itself it is **not a complete program**.

Distinguish two kinds of "keeping unchanged":

- **Inside the Class-File API**: `classBuilder.with(element)` / `methodBuilder.with(element)` / `codeBuilder.with(element)` passes the element into the result.
- **Outside, in Java Instrumentation**: `ClassFileTransformer.transform(...)` returns `null` if there are no replacement class bytes; if you want to change bytecode, return a valid `byte[]`.

When handling **already-loaded** classes, `Instrumentation.retransformClasses(...)` and `redefineClasses(...)` also have structural restrictions: you cannot arbitrarily add/remove fields, change method signatures, or change supertypes as you can when creating a new class. The fact that the Class-File API can produce a `byte[]` does not mean the JVM is required to accept it during a retransform/redefine. Check JVM capabilities, modifiability, and contracts before applying.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Emitting only the target method and forgetting `classBuilder.with(otherElement)` | Other fields/methods/class attributes may be lost | Use an `else -> with(element)` branch |
| Entering `MethodBuilder` but forgetting `methodBuilder.with(...)` | Method annotations/attributes may be lost | Transform only `CodeModel`, pass through everything else |
| Entering `CodeBuilder` but only generating new instructions and dropping all labels | Branches/exception handlers may break | Keep unchanged code elements; check labels |
| Using `withMethodBody` for a method with rich metadata | Does not automatically preserve method attributes | Use `transformMethod` or re-emit each attribute manually |
| Filtering methods only by name in a class with overloads | May accidentally modify multiple methods | Also filter by appropriate descriptor/flags |
| Confusing `builder.with(element)` with `ClassFileTransformer.transform() == null` | Drops elements in the new class | Distinguish the scopes of the two APIs |
| Expecting byte-for-byte identical output to input | False alarm when constant pool/stack maps differ | Compare semantics, metadata, and behavior |
| Assuming bytes are valid just because they parse | The JVM may reject them during verify/load | Use `verify`, `javap`, and actual runtime tests |
| Forgetting the Java version | `package java.lang.classfile does not exist` on older JDKs | Compile/run on JDK 24+ |
| Missing a custom attribute mapper | Attributes are not preserved/rewritten with the right meaning | Configure an `AttributeMapper` and test the artifact |
| Using Class-File API to add a field to an already-loaded class and then retransforming | Violates JVM TI restrictions | Separate load-time transformation from retransform/redefine |
| Reusing a builder outside its callback or at the wrong builder level | Broken structure, build error, or race condition | Use the builder only inside the handler, emitting the right element type |

In a real tool, include automated tests comparing **before-and-after method/field lists**, important annotations/attributes, and then load the output to verify behavior. For bytecode containing branches, try/catch, synchronized blocks, or invokedynamic, add corresponding verifier-level and runtime tests.

## 10. Safe Workflow When Instrumenting Only Part of a Class

1. **Choose the right Java version**: use JDK 24+; verify the agent's runtime if integrating into another JVM.
2. **Parse the source** into a `ClassModel`, checking the class name/version/metadata that must be preserved.
3. **Define method selection criteria** (name + descriptor, and sometimes class loader/module) so you do not modify the wrong overload.
4. **Use `transformClass`**, descending at the class level only into target `MethodModel`s; use `with(...)` for everything else.
5. **At the method level**, descend only into the `CodeModel` that needs changing, and use `with(...)` for the remaining method elements.
6. **At the code level**, replace/insert only instructions whose stack/flow impact has been analyzed, and emit `with(...)` for all unchanged elements.
7. **Verify the output** using `ClassFile.verify(newBytes)`, `javap -v/-c`, metadata diffs, and runtime tests.
8. **If integrating into Instrumentation**, check permissions/capabilities/redefine or retransform limits and handle errors in the transformer in a controlled manner.

Thus, "keeping unchanged parts intact" is not a global switch; it is **an explicit element-emission contract at each builder level**, supported by convenience transforms and the API's ability to leverage parts of the original class file.

## 11. Exercises and Answers

**Exercise 1.** In `ClassTransform`, why is a callback that handles only a `MethodModel` named `compute` without an `else` branch dangerous?

**Exercise 2.** A method has `RuntimeVisibleAnnotations` and `Code`. You only want to change one `IADD` instruction. Why is `transformMethod(...)` with `methodBuilder.transformCode(...)` more appropriate than recreating the method with `withMethodBody(...)`?

**Exercise 3.** If `CodeTransform` encounters a `LabelTarget`, `LineNumber`, or an instruction that does not need modification, what must be done to keep it?

**Exercise 4.** `ClassFile.verify(updated)` returns an empty list. Can you conclude that the metadata and behavior of the entire application are completely correct?

**Exercise 5.** Why is `ClassFile.of().transformClass(model, ClassTransform.ACCEPT_ALL)` not required to produce bytes identical to the input?

**Exercise 6.** You have a `CodeTransform` that changes `IADD` to `ISUB`, but you only want to apply it to `compute(int,int)`. Which utility helps keep the other methods unchanged?

**Exercise 7.** An agent wants to change the implementation of an already-loaded method. `ClassFile.transformClass(...)` produces a valid class file that also adds a field. Can you be sure `retransformClasses(...)` will accept it?

**Answers:**

1. In the *flatMap* model, an element not emitted into the builder is dropped from the new class file. You must call `classBuilder.with(element)` for every unchanged component.
2. `transformMethod` takes the source method's metadata; the `methodBuilder.with(member)` branch keeps method elements that are not `CodeModel`. `transformCode` changes only the code; `withMethodBody` does not automatically carry over the method attributes that need to be kept.
3. Call `codeBuilder.with(element)` on that element; do not assume the API will automatically add it back if the callback skips it.
4. **No.** The verifier is a necessary check, but you still need method/field/attribute checks, behavioral tests, and runtime environment constraint checks.
5. Because the Class-File API may restructure the constant pool, stack maps, or metadata when building; forwarding elements preserves model equivalence, not byte-for-byte identity.
6. `ClassTransform.transformingMethodBodies(predicate, codeTransform)`, using a predicate that checks both **name and descriptor** when overloads exist.
7. **No.** Adding a field to a currently loaded class exceeds the standard limits of retransform/redefine, even if the generated class file is valid.

## 12. Official Documentation

- [Java SE 24 — Package `java.lang.classfile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): models, elements, builders, transforms, pass-through patterns, and constant pool sharing.
- [Java SE 24 — `ClassBuilder`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassBuilder.html): `withField`, `withMethod`, `withMethodBody`, `transformMethod`.
- [Java SE 24 — `MethodBuilder`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodBuilder.html): `withCode`, `transformCode`, method-level metadata.
- [Java SE 24 — `CodeBuilder`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html): emitting JVM instructions, labels, operations on code elements.
- [Java SE 24 — `ClassFile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `build`, `transformClass`, `verify`, processing options.
- [Java SE 24 — `ClassTransform` and `MethodTransform`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): convenience transforms and how to preserve unchanged parts.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): design motivation and standardization of the API in JDK 24.
