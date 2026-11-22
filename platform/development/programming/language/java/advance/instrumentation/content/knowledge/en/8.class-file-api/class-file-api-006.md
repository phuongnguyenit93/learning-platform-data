# ClassTransform, MethodTransform, CodeTransform and Composing Transforms in the Class-File API

The Java Class-File API provides a way to **read, build, and transform `.class` files** using strongly typed models and builders, rather than manually modifying arbitrary byte arrays. The three key transform types when organizing a transformation are:

- **`ClassTransform`**: handles **class-level** elements such as methods, fields, and attributes.
- **`MethodTransform`**: handles **method-level** elements, including `CodeModel` (the method body) and method attributes.
- **`CodeTransform`**: handles elements inside a **method body** such as instructions, labels, and certain metadata.

The strength of the API is not just having three callback types: you can **compose same-level transforms with `andThen`** and **lift lower-level transforms to a higher level** using factories such as `MethodTransform.transformingCode(...)`, `ClassTransform.transformingMethods(...)`, and `ClassTransform.transformingMethodBodies(...)`.

This lesson explains the transformation contract, how to compose types properly, the order of application, a runnable example on **JDK 24+**, how to verify the resulting class file, and the boundary with `java.lang.instrument.ClassFileTransformer`.

## 1. Java version: why the examples use JDK 24+

**`java.lang.classfile` is a standard API starting in JDK 24**, following preview phases in earlier JDK versions. Interfaces such as `ClassFile`, `ClassModel`, `ClassTransform`, `MethodTransform`, and `CodeTransform` used in this lesson reside in the `java.base` module and require no external dependencies.

- For **JDK 24 and later**: uses the standard API; examples can be compiled normally with `javac --release 24`.
- For **JDK 17**: the `java.lang.classfile` package **does not exist yet**. You cannot compile the examples in this lesson on JDK 17 just by adding imports or changing the `--release` flag.
- For **JDK 22/23**: the Class-File API was in preview and had differences across versions; do not assume all methods/types match the standard JDK 24 release.
- If you must instrument on Java 17, consider bytecode libraries such as ASM, Byte Buddy, or Javassist; or use a tool to generate bytecode with JDK 24+ and then check the **class file version** and compatibility on the target JVM.

Because this topic directly requires the **Class-File API**, examples using JDK 24+ are a more accurate choice than trying to write code calling interfaces that do not exist in Java 17. It is recommended to use JDK 25 or newer when practicing, while compiling with `--release 24` to check compatibility with the initial standard API.

**Do not conflate** the following names:

```text
java.lang.classfile.ClassTransform          // Transform in the Class-File API
java.lang.classfile.MethodTransform         // Transform inside a method
java.lang.classfile.CodeTransform           // Transform on CodeElements
java.lang.instrument.ClassFileTransformer   // JVM instrumentation callback
```

`ClassFileTransformer` is the entry point of the instrumentation mechanism when the JVM loads/retransforms/redefines a class. Inside that callback, you **can use** the Class-File API to produce new bytes; however, `ClassTransform` does not register itself with the JVM.

## 2. Hierarchical model: Model → Element → Transform → Builder

A `.class` file has a nested structure:

```text
ClassModel                            ClassBuilder
  ├── FieldModel                       └── (fields and attributes)
  ├── MethodModel                     MethodBuilder
  │     ├── method attribute             ├── method attribute
  │     └── CodeModel                  CodeBuilder
  │            ├── instruction           ├── instruction
  │            ├── label                 ├── label
  │            └── code metadata         └── code metadata
  └── class attribute
```

Reading a class file:

```java
ClassFile cf = ClassFile.of();
ClassModel original = cf.parse(classBytes);
```

This snippet is only **illustrative code inside a method**, with the `classBytes` variable already prepared. `ClassModel` describes the source class file; the API allows inspecting `MethodModel`s, `FieldModel`s, attributes, and code structure. It is not a copy of a running `java.lang.Class<?>`.

At each level, a transform receives an **output builder** and an **input element**:

| Level | Transform | Input element | Output builder |
|---|---|---|---|
| Class | `ClassTransform` | `ClassElement` | `ClassBuilder` |
| Method | `MethodTransform` | `MethodElement` | `MethodBuilder` |
| Code | `CodeTransform` | `CodeElement` | `CodeBuilder` |

All three are functional interfaces and support lambda syntax `(builder, element) -> { ... }`. Semantically, a transform **is not required to return an element**; it performs the action of *emitting* elements to the builder.

**Three decisions when receiving an element:**

1. **Keep unchanged:** `builder.with(element)`.
2. **Drop:** do not send that element to the builder.
3. **Replace / add new:** send one or more new elements according to the builder's API, optionally omitting the old element.

Forgetting `builder.with(element)` in the default branch **can lose class file data**, rather than simply "leaving it unchanged". This is the most important rule when writing your own transform.

## 3. `ClassTransform`: transforming class-level components

`ClassTransform` processes a stream of `ClassElement`s. Elements can be `MethodModel`, `FieldModel`, or class-level attributes. You can add, keep, modify, or drop an element according to the builder contract.

### 3.1. Small example: removing a method that is no longer needed

```java
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;

ClassTransform dropDebug = ClassTransform.dropping(
        element -> element instanceof MethodModel method
                && method.methodName().stringValue().equals("debug"));
```

This is a **snippet inside a method body**, not a standalone Java file. `ClassTransform.dropping(predicate)` removes matching elements and **keeps non-matching elements**. In the example, the method named `debug` is removed from the resulting class file; other methods and attributes are forwarded.

Equivalent to a handwritten lambda:

```java
ClassTransform dropDebug = (builder, element) -> {
    if (element instanceof MethodModel method
            && method.methodName().stringValue().equals("debug")) {
        return; // Do not emit this method: drop it.
    }
    builder.with(element);
};
```

Here, `return` ends the callback invocation for **one element**; it does not mean stopping the entire transform pipeline. The class may become invalid or the application may encounter `NoSuchMethodError` if other code still references the removed method. Only delete when you understand these constraints.

### 3.2. How to invoke a class-level transform

```java
ClassFile cf = ClassFile.of();
ClassModel model = cf.parse(bytes);
byte[] result = cf.transformClass(model, dropDebug);
```

The variables `bytes` and `dropDebug` must already exist (this is an illustrative snippet). `transformClass` produces a **new class file `byte[]`**. It does not automatically load the new class into the JVM and does not automatically replace an existing `java.lang.Class<?>`.

Some utilities:

- `ClassTransform.ACCEPT_ALL`: forwards all class elements.
- `ClassTransform.dropping(predicate)`: removes class elements matching a condition.
- `ClassTransform.transformingFields(fieldTransform)`: applies a transform to fields.
- `ClassTransform.transformingMethods(methodTransform)`: applies a transform to methods.
- `ClassTransform.transformingMethods(predicate, methodTransform)`: applies only to selected methods.
- `ClassTransform.transformingMethodBodies(predicate, codeTransform)`: applies directly to the code body of selected methods.
- `ClassTransform.andThen(other)`: chains **two ClassTransforms** in order.

Note that `ClassTransform` processes **class elements**; it does not automatically descend into every bytecode instruction. To modify code inside a method, you need to **lift** a `CodeTransform` to the class level, or call the corresponding builder API.

## 4. `MethodTransform`: transforming the structure of each method

`MethodTransform` processes `MethodElement`s and writes results to `MethodBuilder`. Inside a method, the `CodeModel` element describes the code attribute; other elements may contain annotations or metadata.

Example of **only inspecting an element and keeping it unchanged**:

```java
MethodTransform observeMethod = (builder, element) -> {
    System.out.println("method-element=" + element.getClass().getSimpleName());
    builder.with(element);
};
```

This snippet cannot run standalone because it needs the `MethodTransform` import and a context to invoke the transform. Logging the implementation class name is for illustration only: you should not write business logic that depends on internal implementation class names.

When using `ClassTransform.transformingMethods(observeMethod)`, `observeMethod` will be applied to the methods belonging to the class. Elements that are **not methods** are forwarded by the factory to preserve the class structure.

### 4.1. Going from MethodTransform down to CodeTransform

Suppose you already have `CodeTransform codeTransform`. You create:

```java
MethodTransform methodTransform =
        MethodTransform.transformingCode(codeTransform);
```

This factory finds `CodeModel` in the method, applies `codeTransform`, and **keeps other method elements**. Therefore, it is safer and clearer than manually skipping all method attributes.

Then lift it one more level:

```java
ClassTransform classTransform =
        ClassTransform.transformingMethods(
                method -> method.methodName().stringValue().equals("value"),
                methodTransform);
```

Result: only the method named `value` enters `methodTransform`, and then the code inside enters `codeTransform`. Other methods are passed through unmodified.

**Hierarchy order:**

```text
ClassTransform
    └── select MethodModel "value"
            └── MethodTransform
                    └── find CodeModel
                            └── CodeTransform for CodeElement
```

In cases where you only need to manipulate code, you can use the shorthand:

```java
ClassTransform sameScope =
        ClassTransform.transformingMethodBodies(
                method -> method.methodName().stringValue().equals("value"),
                codeTransform);
```

The two snippets above describe **two alternative ways to build the pipeline**, not a requirement to run both. The `transformingMethodBodies` factory directly lifts a `CodeTransform` to a `ClassTransform` for methods matching the predicate.

### 4.2. `MethodTransform` is not used to "delete a method"

Because `MethodTransform` processes **elements inside an already selected method**, if you want to **delete an entire method**, do it at the `ClassTransform` level, where `MethodModel` is a `ClassElement`. If you recklessly delete `CodeModel` from a concrete method that has code, the resulting class may be invalid.

This is the principle for choosing the operation level: **if you want to remove an object, find the level where that object appears as an element**.

## 5. `CodeTransform`: editing the instruction stream in a method body

`CodeTransform` processes `CodeElement`s. This is the level to use when inserting, changing, or removing a bytecode instruction, label, handler, or metadata modeled by the API at the code level.

### 5.1. Safe pattern: insert an instruction and keep the old instruction

```java
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.ReturnInstruction;

CodeTransform addNopBeforeReturn = (builder, element) -> {
    if (element instanceof ReturnInstruction) {
        builder.nop();
    }
    builder.with(element);
};
```

This is **illustrative code inside a method body**. `builder.nop()` emits an additional `nop` (no-operation) instruction before each return; `builder.with(element)` keeps the return instruction itself and other code elements.

For general logic, inserting instructions other than `nop` requires computing stack effects, labels, exception handlers, and control-flow validity. The API can assist in building class file metadata, but it does not automatically make every logic modification valid.

### 5.2. Instruction removal pattern

```java
import java.lang.classfile.instruction.NopInstruction;

CodeTransform removeNops = (builder, element) -> {
    if (!(element instanceof NopInstruction)) {
        builder.with(element);
    }
};
```

Because `nop` does not affect the operand stack, removing a standalone `nop` is an easy operation to learn how to drop a `CodeElement`. Do not generalize this example into permission to arbitrarily delete `return`, `goto`, label targets, or instructions referenced by other branches: doing so can make the code incorrect or fail verification.

### 5.3. Keeping elements by default is mandatory when you do not want to replace them

In the lambda:

```java
CodeTransform careless = (builder, element) -> {
    if (element instanceof ReturnInstruction) {
        builder.nop();
    }
};
```

**This is a wrong example to identify a bug.** Because `builder.with(element)` is missing, all source elements are not forwarded; the old `return` is also dropped, which can make the method body invalid. When code-reviewing a `CodeTransform`, always check that every branch intentionally keeps, replaces, or drops elements.

## 6. Two directions of composing transforms: `andThen` and "lifting"

There are **two different operations** that are very easy to confuse.

### 6.1. Same-level composition with `andThen`

```java
CodeTransform combinedCode =
        addNopBeforeReturn.andThen(removeNops);
```

Both are `CodeTransform`s, so the method can connect them:

```text
Source CodeModel
     |
     v
addNopBeforeReturn
     |  output elements (including newly added nop)
     v
removeNops
     |  output elements (nop removed)
     v
Target CodeBuilder
```

**`first.andThen(second)` means the element output of `first` is fed into `second`**. It is not "applying two independent lambdas to two copies of the input". The API uses a *chained builder* so it does not necessarily need to create an intermediate classfile on disk.

There are also the forms:

```java
ClassTransform classChain = classTransformA.andThen(classTransformB);
MethodTransform methodChain = methodTransformA.andThen(methodTransformB);
CodeTransform codeChain = codeTransformA.andThen(codeTransformB);
```

This is **sample code with variables A/B already declared**, not a standalone runnable file. Each `andThen` preserves the same type: `ClassTransform`, `MethodTransform`, or `CodeTransform`.

You cannot directly compose **across different levels**:

```java
// Wrong type, does not compile:
ClassTransform wrong = classTransformA.andThen(codeTransformA);
```

**Lift** `codeTransformA` first:

```java
ClassTransform lifted =
        ClassTransform.transformingMethodBodies(codeTransformA);
ClassTransform right = classTransformA.andThen(lifted);
```

Note that `andThen` is directional: if you swap `A.andThen(B)` to `B.andThen(A)`, the result may differ. For bytecode, the second operation always sees the elements emitted by the first operation.

### 6.2. Lifting from a lower level to a higher level

Lift using the factories:

```text
CodeTransform
    |
    +-- MethodTransform.transformingCode(codeTransform)
    |       -> MethodTransform
    |             |
    |             +-- ClassTransform.transformingMethods(methodTransform)
    |                        -> ClassTransform
    |
    +-- ClassTransform.transformingMethodBodies(codeTransform)
            -> ClassTransform directly
```

Lifting can be paired with a predicate to process only selected methods. For example, filtering by method name:

```java
ClassTransform selected = ClassTransform.transformingMethodBodies(
        m -> m.methodName().stringValue().equals("value"),
        addNopBeforeReturn.andThen(removeNops));
```

This is a very useful pattern when you need to apply a small `CodeTransform` to a batch of methods in a class. Instead of rewriting the loop logic for the entire `ClassModel` and each `MethodModel`, you reuse independent transforms.

### 6.3. How to combine both directions

Organization example:

```text
CodeTransform A (insert nop) --andThen--> CodeTransform B (remove nop)
                                 |
                                 v
               MethodTransform.transformingCode(A.andThen(B))
                                 |
                                 v
    ClassTransform.transformingMethods(filter, methodTransform)
                                 |
                            andThen
                                 |
                                 v
             ClassTransform.dropping(debug method)
                                 |
                                 v
                    ClassFile.transformClass(...)
```

Here the pipeline has two kinds of ordering:

1. **Inside the method body**: A then B.
2. **On the ClassElement stream**: the method body processing step, then the debug method removal step.

The later class-transform step can observe the output from the earlier class-transform step; any component not forwarded will not reach the final output.

## 7. Complete JDK 24+ example: combining all three transform types

Practice goals:

- Read a class file containing three methods: `value`, `debug`, and `main`.
- Use **`CodeTransform`** A to insert `nop` right before the return of the `value` method.
- Use **`CodeTransform`** B to remove the `nop` that A just generated; the two transforms are chained with `andThen`.
- Use **`MethodTransform.transformingCode`** to attach A+B to a method's code.
- Use **`ClassTransform.transformingMethods`** to select the `value` method.
- Use **`ClassTransform.dropping`** to drop the `debug` method.
- Chain the two `ClassTransform`s with `andThen`, write the new class file, check `ClassFile.verify`, and run the resulting class.

This lesson **does not use a Java agent** to avoid mixing up the API's byte processing order with when the JVM registers a transformer. All logic runs offline on `.class` files, making it easy to inspect inputs and outputs.

Directory structure:

```text
classfile-transform-demo/
├── src/
│   ├── TransformDemo.java
│   └── demo/
│       └── Target.java
├── out/                 (created by javac)
└── patched/             (created by the program itself)
```

### 7.1. Source class `src/demo/Target.java`

```java
package demo;

public final class Target {
    private Target() {
    }

    public static int value() {
        return 7;
    }

    public static void debug() {
        System.out.println("debug should not run");
    }

    public static void main(String[] args) {
        System.out.println("value=" + value());
    }
}
```

`debug()` is not called from `main`, so removing it in the example does not cause the application to fail. `value()` has a single `ireturn`, allowing us to record exactly one `nop` added and one `nop` removed in the subsequent pipeline.

### 7.2. Tool `src/TransformDemo.java`

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.MethodModel;
import java.lang.classfile.MethodTransform;
import java.lang.classfile.instruction.NopInstruction;
import java.lang.classfile.instruction.ReturnInstruction;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;

public final class TransformDemo {
    private TransformDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path input = Path.of("out", "demo", "Target.class");
        Path output = Path.of("patched", "demo", "Target.class");

        ClassFile cf = ClassFile.of();
        ClassModel original = cf.parse(input);

        AtomicInteger inserted = new AtomicInteger();
        AtomicInteger removed = new AtomicInteger();

        // A: add nop before each return.
        CodeTransform addNop = (builder, element) -> {
            if (element instanceof ReturnInstruction) {
                builder.nop();
                inserted.incrementAndGet();
            }
            builder.with(element);
        };

        // B: also receives nops generated by A and drops them.
        CodeTransform dropNop = (builder, element) -> {
            if (element instanceof NopInstruction) {
                removed.incrementAndGet();
            } else {
                builder.with(element);
            }
        };

        // Same-level composition: CodeTransform -> CodeTransform.
        CodeTransform codePipeline = addNop.andThen(dropNop);

        // Lift CodeTransform -> MethodTransform.
        MethodTransform methodPipeline =
                MethodTransform.transformingCode(codePipeline);

        // Lift MethodTransform -> ClassTransform,
        // apply only to the value method.
        ClassTransform changeValue =
                ClassTransform.transformingMethods(
                        m -> m.methodName().stringValue().equals("value"),
                        methodPipeline);

        // An independent ClassTransform that drops the debug method.
        ClassTransform dropDebug = ClassTransform.dropping(
                element -> element instanceof MethodModel method
                        && method.methodName()
                                .stringValue().equals("debug"));

        // Compose two ClassTransforms in order.
        ClassTransform combined = changeValue.andThen(dropDebug);

        byte[] result = cf.transformClass(original, combined);

        // Re-parse the resulting model and use the verify API.
        ClassModel updated = cf.parse(result);
        boolean debugPresent = updated.methods().stream()
                .anyMatch(m -> m.methodName()
                        .stringValue().equals("debug"));
        boolean verified = cf.verify(result).isEmpty();

        Files.createDirectories(output.getParent());
        Files.write(output, result);

        System.out.println("insertedNops=" + inserted.get());
        System.out.println("removedNops=" + removed.get());
        System.out.println("debugPresent=" + debugPresent);
        System.out.println("verified=" + verified);
        System.out.println("saved=patched/demo/Target.class");
    }
}
```

**Why is this example useful?**

1. `addNop` actually adds a new `CodeElement` using `builder.nop()`.
2. `dropNop` comes after `addNop` and receives the emitted elements, including the newly generated `nop`. If `andThen` only ran two transforms on two independent copies, the `removed` counter would not prove this relationship.
3. `MethodTransform.transformingCode` preserves method elements other than code, and `ClassTransform.transformingMethods(filter, ...)` leaves unselected methods unchanged.
4. `dropDebug` is a **class-level** transform because it removes an entire `MethodModel`.
5. `combined` represents a unified transformation; `ClassFile.transformClass` produces the bytes of the new class file.
6. `ClassFile.verify` is an additional check; it does not replace testing application behavior and all runtime constraints.

### 7.3. Compiling

Open a terminal in the `classfile-transform-demo` directory, make sure you are using **JDK 24+**, then run:

```bash
java -version
javac -version
mkdir out

javac --release 24 -encoding UTF-8 -d out src/demo/Target.java src/TransformDemo.java
```

With JDK 24+ using the standard API, **`--enable-preview` is not needed**, `--add-exports` is not needed, and downloading ASM is not needed. `--release 24` is only valid if `javac` is run from a JDK that supports that release.

On Windows PowerShell, cmd, or Unix shell, `mkdir out` can be replaced with the corresponding directory creation command if the directory already exists. All subsequent commands assume `out/demo/Target.class` and `out/TransformDemo.class` have been created.

### 7.4. Running the transform tool

```bash
java -cp out TransformDemo
```

Expected stdout **on JDK 24+ when the tool runs successfully**:

```text
insertedNops=1
removedNops=1
debugPresent=false
verified=true
saved=patched/demo/Target.class
```

How to read this:

- `insertedNops=1`: the `value()` method has one return instruction; A emits an extra `nop` before that instruction.
- `removedNops=1`: B observed and dropped the `nop` emitted by A; this is the effect of `A.andThen(B)`.
- `debugPresent=false`: `ClassTransform.dropping` removed the `debug` method from the resulting class file.
- `verified=true`: the API reported no errors via `cf.verify(result)`.
- `saved=...`: the new bytes were written to a separate file, without overwriting `out/demo/Target.class`.

The transformed class still has the `value` and `main` methods, without `debug`. Since `nop` was added and then removed, the logic of `value()` still returns `7`.

### 7.5. Running the new class file

```bash
java -cp patched demo.Target
```

Stdout:

```text
value=7
```

Here `patched` is the classpath, not `out`: that way the JVM loads **the transformed version**. If you accidentally run `java -cp out demo.Target`, you will run the original class and fail to verify the tool's output.

Try comparing:

```bash
javap -classpath out demo.Target
javap -classpath patched demo.Target
```

In `javap`'s output, the original class has the `debug` method, while the new class does not. Use `javap -c -classpath patched demo.Target` if you want to inspect the instructions of the methods. There is no need to set up an agent JAR or use the Attach API for this step.

### 7.6. Try swapping the order to see non-commutativity

In `TransformDemo.java`, replace:

```java
CodeTransform codePipeline = addNop.andThen(dropNop);
```

with:

```java
CodeTransform codePipeline = dropNop.andThen(addNop);
```

This is **a single change in the complete file in section 7.2**, not a new standalone program. After recompiling and running the tool:

- `dropNop` runs first, so it does not see the `nop` that A has not yet emitted.
- `addNop` runs afterward, so the new `nop` is kept in the output bytes.
- With the `Target` class generated by `javac` in this example (which has no initial `nop` in `value()`), the `removedNops` counter is expected to be `0`, while `insertedNops` remains `1`.
- The program still prints `value=7`, because `nop` does not change behavior; the difference is more clearly visible with `javap -c`.

**Conclusion:** `A.andThen(B)` and `B.andThen(A)` are not necessarily equivalent. When manipulating real bytecode such as inserting calls, changing method owners, altering branches, or editing exception handlers, the difference can affect program behavior, not just the number of `nop`s.

## 8. Choosing the right transform level for each problem

| Requirement | Appropriate transform | Explanation |
|---|---|---|
| Delete the entire `debug()` method | `ClassTransform` | `MethodModel` is a `ClassElement` |
| Modify an attribute component of a method | `MethodTransform` | `MethodElement` belongs to a method |
| Insert an instruction before `return` | `CodeTransform` | `ReturnInstruction` is a `CodeElement` |
| Edit all method bodies | `ClassTransform.transformingMethodBodies(codeXform)` | Lifts a code transform to the entire class |
| Edit only the `value()` method | `ClassTransform.transformingMethods(filter, MethodTransform.transformingCode(codeXform))` | Filters the method, then processes the code |
| Compose two instruction-changing transforms | `codeA.andThen(codeB)` | Two transforms at the same `CodeTransform` level |
| Compose two class-structure-modifying transforms | `classA.andThen(classB)` | Two transforms at the same `ClassTransform` level |
| Transform a `MethodModel` directly from a builder | `ClassBuilder.transformMethod(model, methodTransform)` | Class-level builder API |
| Transform a `CodeModel` directly inside a builder | `MethodBuilder.transformCode(model, codeTransform)` | Method-level builder API |

**`MethodBuilder.transformCode(...)`** and **`ClassBuilder.transformMethod(...)`** are direct call paths when you are actively building a class/method with a builder. The `transformingCode` and `transformingMethods` factories are better suited when you want to express a reusable pipeline across multiple elements.

You should not create a `ClassTransform` specifically for individual instructions and traverse the whole tree manually when `CodeTransform` and lifting factories already exist. Conversely, you should not force an entire-method deletion down into `CodeTransform`.

## 9. Going further: `atStart`, `atEnd`, and stateful transforms

In addition to the per-element handler (`accept`), transforms support **lifecycle hooks**:

- `atStart(builder)`: runs before processing the member elements of a structure.
- `accept(builder, element)`: processes each element.
- `atEnd(builder)`: runs after finishing processing the elements.

Example scenario needing `atStart`: inserting an instruction at the beginning of a method body before existing instructions. Scenario needing `atEnd`: after scanning a class, adding an attribute that was not seen or completing an aggregation operation. These hooks must be applied at the right element level and require considering labels/stack maps when adding code.

The following pattern only **illustrates organizing a stateful transform** and is not a standalone Java file:

```java
CodeTransform countReturns = CodeTransform.ofStateful(() ->
        new CodeTransform() {
            private int count;

            @Override
            public void accept(CodeBuilder builder, CodeElement element) {
                if (element instanceof ReturnInstruction) {
                    count++;
                }
                builder.with(element);
            }

            @Override
            public void atEnd(CodeBuilder builder) {
                System.out.println("returns=" + count);
            }
        });
```

`CodeBuilder`, `CodeElement`, `ReturnInstruction`, and `CodeTransform` are APIs already imported in an enclosing class/method outside the snippet above. Each time the transform is reused via `ofStateful(supplier)`, the supplier creates an implementation with **isolated state** for that traversal pass. That avoids leaking counter variables across methods/classes when the same transform instance is lifted and applied multiple times.

You should not use an uncontrolled shared `count` instance variable if the transform might be reused across multiple threads or multiple methods. `AtomicInteger` in the section 7 example is a counter **intentionally used in a single test run on exactly one selected method**, not a general stateful architecture for a production agent.

Besides `ofStateful`, transform types have convenience factories `endHandler(...)`, `dropping(...)` (where supported), and `ACCEPT_ALL`. Use them when the logic is simple to avoid writing boilerplate to handle all elements manually.

## 10. When you need to transform bytecode in a Java agent

The Class-File API generates class bytes, while `java.lang.instrument` decides **when the JVM hands bytes to the agent** and how the agent registers with the JVM.

Integration flow:

```text
premain/agentmain
   |
   +--> instrumentation.addTransformer(...)
                |
                v
       ClassFileTransformer.transform(...)
                |
                v
       ClassFile.of().parse(classfileBuffer)
                |
                v
       ClassTransform (may lift MethodTransform/CodeTransform)
                |
                v
       ClassFile.transformClass(...) -> byte[]
                |
                v
       return new bytes to the JVM
```

**Integration callback pattern (snippet belonging to a `ClassFileTransformer` class; does not include agent, manifest, or registration):**

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (!"demo/Target".equals(className)) {
        return null;
    }

    try {
        ClassFile cf = ClassFile.of();
        ClassModel model = cf.parse(classfileBuffer);
        return cf.transformClass(model, combined);
    } catch (RuntimeException failure) {
        System.err.println("Transformation failed: " + failure);
        return null;
    }
}
```

In this snippet, the `combined` variable is a validly constructed `ClassTransform` within the scope of the enclosing class/instance. Full imports/deployment context are also required; **this is not a self-running program**.

Points to remember:

- `className` is in internal form `"demo/Target"`, not `"demo.Target"`; it can be `null` in certain situations.
- `return null` means **do not change bytecode in this callback**; it does not mean blocking other transformers.
- Return a new array only when an appropriate transformation occurs; do not directly mutate the JVM's `classfileBuffer`.
- An agent using the standard Class-File API must run on a JVM new enough to provide the API; you cannot put a class compiled with JDK 24 into a JVM 17 and expect the agent to load.
- With retransform/redefine, the JVM has restrictions on class structure changes (for example, you cannot freely add/remove methods); therefore, **the `debug` removal step** in the offline example **is not** a change that can be arbitrarily applied to an already loaded class.
- Do not let the agent's instrumentation cause infinite recursion when the agent accidentally instruments its own helper classes.
- If using classfile bytes to load into a real system, you need to check the class version, dependencies, module access, bytecode verifier, and application behavior.

Integrating as above turns `ClassTransform` into **a tool inside** `ClassFileTransformer`, rather than making the two interface types become one.

## 11. Validity checks and practical limitations

### 11.1. `verify` is a necessary but insufficient step

```java
boolean verified = ClassFile.of().verify(transformedBytes).isEmpty();
```

This is an illustrative snippet with `transformedBytes` already generated. `verify` checks class bytes against verification rules provided by the API, but **does not guarantee correct business behavior**: you still need to test the actual class, invoke methods, and confirm the results.

When a transformation affects stack map frames, branches, exception tables, or the constant pool, you need to understand how the builder handles them and the options in `ClassFile`. Newly modified classes might compile from source normally yet fail when loaded by the JVM if invalid class bytes are produced.

### 11.2. A Model is descriptive data, not an executing class

`ClassFile.of().parse(input)` does not load `java.lang.Class<?>` into the JVM. It only creates a model for the file bytes. `ClassFile.of().transformClass(model, transform)` returns new bytes; if you do not write them out or pass them to a class loader/agent, **there is no runtime change**.

### 11.3. Keeping bytecode unchanged does not mean keeping every byte identical

Parsing → building can change representation details, constant pool ordering, instruction layout, or metadata depending on builder/option choices, even when logical behavior is preserved. You should not test by requiring `Arrays.equals(oldBytes, newBytes)` when the goal is **preserving semantics**. Check the class version, methods/fields to keep, verification, and behavior.

### 11.4. You must actively keep elements when writing callbacks

Across all three transform types, the safest default is:

```java
builder.with(element);
```

If there is a branch to replace or remove, make it explicit in that branch. When writing a `switch` on `CodeElement`, you must consider new elements added in later JDK releases. Do not assume all instruction/attribute types have already been listed.

### 11.5. Watch out for filtered methods having multiple overloads

The condition `m.methodName().stringValue().equals("value")` selects **all methods with the same name**, including overloads with different descriptors. If the system has `value()` and `value(int)`, filtering by name will apply to both. When precision is needed, also filter by **method descriptor** via the corresponding `MethodModel` API. This lesson's example has no overloads, so only one method is selected.

### 11.6. Do not arbitrarily delete control-flow-related elements

`NopInstruction` is an easy exercise to test because it does not alter the operand stack. However, dropping `LabelTarget` or `ExceptionCatch` without checking references can break control flow; dropping returns/branches or replacing invoke instructions can cause wrong stack effects. You need to understand `CodeModel`, `CodeBuilder`, stack maps, and JVM rules before making deep modifications.

## 12. Common errors and how to handle them

| Symptom | Common cause | Resolution |
|---|---|---|
| `package java.lang.classfile does not exist` | Using JDK 17 or older than the standard release | Use JDK 24+; check `java -version`, `javac -version` |
| `--release 24` is not supported | `javac` is older than JDK 24 | Use JDK 24+ |
| `ClassTransform.andThen(codeTransform)` does not compile | Two transforms are at different levels | Lift CodeTransform to ClassTransform first |
| Result is missing methods/attributes | Callback forgot `builder.with(element)` | Have a default branch forwarding elements to keep |
| Have a CodeTransform but method is unchanged | Did not lift into method/class or wrong filter | Use `transformingCode`, `transformingMethods`, or `transformingMethodBodies` |
| `debug` still exists | Pipeline lacks `ClassTransform.dropping` or wrong name filter | Check `MethodModel.methodName()` |
| `removedNops=0` | The nop-removing stage ran **before** the nop-adding stage or there were no input nops | Check `andThen` order |
| Class verifies but behavior is wrong | Transformation logic is structurally valid but business logic is wrong | Run runtime/behavior tests |
| `VerifyError`/load error in JVM | Invalid stack maps, labels, class version, or code | Inspect classfile, verify, `javap`, check version/branches |
| Runtime still runs the old class | Using classpath `out` instead of `patched` | Run `java -cp patched demo.Target` |
| `NoSuchMethodError` after removing a method | Other code still calls the removed method | Check references and API compatibility before dropping |
| State is shared across multiple methods | Reusing a transform with a mutable counter | Use `ofStateful` or per-traversal state |
| Agent running on Java 17 fails to load | Agent uses Java 24+ API/class version | Choose a compatible runtime or another bytecode tool |
| Want to redefine a loaded class while deleting a method | Redefine/retransform limitations | Separate build-time/offline workflows from live instrumentation |

## 13. Self-check exercises

### Exercise 1: choosing the transform level

To completely remove the `debug` method in a class, what should you use?

**Answer:** `ClassTransform`, because `MethodModel` is a `ClassElement`. `MethodTransform` processes elements **inside** a method, not the condition to delete the entire method.

### Exercise 2: composing two CodeTransforms

`A` adds `nop` before each return; `B` removes all `nop`s. What does `A.andThen(B)` produce?

**Answer:** `B` receives the elements that `A` just emitted, so the new `nop` is removed; return and other elements are still kept if the callbacks have `builder.with(element)`.

### Exercise 3: reversing the order

With the same two transforms above, is `B.andThen(A)` the same as `A.andThen(B)`?

**Answer:** Not necessarily. If the input has no nops, B removes nothing; A adds nop afterward, so nop is kept in the output.

### Exercise 4: composing across levels

Why can't you write `classTransform.andThen(codeTransform)`?

**Answer:** `ClassTransform.andThen` requires a `ClassTransform`; `CodeTransform` operates on `CodeElement`, not `ClassElement`. You must lift it using `ClassTransform.transformingMethodBodies(codeTransform)` or via `MethodTransform.transformingCode`.

### Exercise 5: processing all method bodies

Given `CodeTransform ct`. Write an expression that applies it to all method bodies in a class.

**Answer:**

```java
ClassTransform result = ClassTransform.transformingMethodBodies(ct);
```

This is an expression in a context that has `ct` and imports `ClassTransform`; it is not yet a standalone class.

### Exercise 6: preserving method structure

Given `CodeTransform ct`, but you only need to change code while keeping the remaining method attributes. Which factory do you use?

**Answer:** `MethodTransform.transformingCode(ct)`. It processes `CodeModel` and forwards other method elements.

### Exercise 7: taking a model and returning bytes

After `ClassFile.of().parse(bytes)`, you have `ClassTransform t`. Which API creates the new class file?

**Answer:**

```java
byte[] output = ClassFile.of().transformClass(
        ClassFile.of().parse(bytes), t);
```

This is a snippet using existing `bytes` and `t`; the output is a new classfile array, not automatically installed by the JVM.

### Exercise 8: minimum JDK

Can the entire example be compiled with JDK 17 `javac`?

**Answer:** No. The `java.lang.classfile` API was standardized in JDK 24; the exercise requires JDK 24+.

### Exercise 9: validity

Why is `cf.verify(newBytes).isEmpty()` still not enough to declare the tool "correct"?

**Answer:** It is an API check on bytes/classfile; it does not prove method logic, compatibility with all callers, module/class loader behavior, and runtime behavior. You need additional application tests and alignment with the goal.

### Exercise 10: agent integration

Does a `ClassTransform` run automatically when a class is loaded by the JVM?

**Answer:** No. A caller must invoke `ClassFile.transformClass`. If you want to automatically transform when the JVM loads a class, you must register an appropriate `java.lang.instrument.ClassFileTransformer` and call the Class-File API inside the callback.

## 14. Summary

- **ClassTransform / MethodTransform / CodeTransform** are the three transformation layers corresponding to **ClassElement / MethodElement / CodeElement**.
- **`builder.with(element)`** is how to keep an element; not emitting an element is how to drop it; emitting new elements is how to replace or add.
- **`A.andThen(B)`** composes **two transforms at the same level**, where B processes A's output, not an independent copy of the input.
- **Lifting** brings `CodeTransform` into `MethodTransform` and `ClassTransform` via factories, enabling reuse of small bytecode logic within larger structures.
- **`ClassFile.transformClass(model, transform)`** produces new class file bytes. It does not automatically modify a running class.
- **JDK 24+** is the proper requirement to use the standard API. Java 17 does not have `java.lang.classfile`.
- For instrumentation problems, **ClassFileTransformer** (JVM callback) and **ClassTransform** (byte processing operation) are **two distinct responsibilities that can work together**.
- When writing real transforms, you must test **bytes, verifier, behavior, and compatibility**, not just see that compilation succeeds.

## Official references

- [Oracle JDK 25: Package `java.lang.classfile` — reading, lifting, and composing transforms](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html).
- [Oracle JDK 25: `ClassFileTransform` — contracts for `accept`, `atStart`, `atEnd`, `andThen`, and `ofStateful`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFileTransform.html).
- [Oracle JDK 25: `ClassTransform`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html).
- [Oracle JDK 25: `MethodTransform`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/MethodTransform.html).
- [Oracle JDK 25: `CodeTransform`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/CodeTransform.html).
- [Oracle JDK 25: `ClassFile` — parse, transformClass, and verify](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html).
- [OpenJDK: JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484).
