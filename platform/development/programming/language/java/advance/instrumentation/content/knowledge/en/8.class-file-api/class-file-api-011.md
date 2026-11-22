# Preserving Debug Information, Standard Attributes, and Unrecognized Attributes with the Java Class-File API

The **Class-File API** (`java.lang.classfile`) allows reading, generating, and transforming `.class` files using a strongly typed Java model. When using this API in build tools or Java agents, simply “keeping runnable code intact” is **not enough**: the resulting `.class` file may need to preserve **source line numbers, local variable information, parameter names, generic signatures, annotations, module/record metadata**, and even **custom attributes from other tools** that the current library does not recognize.

A good transformation must clearly distinguish which attributes **need to be preserved semantically**, which **must be recomputed when bytecode changes**, and which **cannot be guaranteed safe by simply copying the binary payload**. This article clarifies those groups, the API's `PASS_*`/`DROP_*` options, how to handle `UnknownAttribute`, and a runnable Java 24+ experiment to demonstrate the results.

> **Version requirement:** The Class-File API was standardized in **JDK 24 (JEP 484)**. It was in preview in JDK 22/23 and **does not exist in Java 17**. The `java.lang.classfile` manipulation examples below require **JDK 24 or later**, without `--enable-preview`. A normal target class can still be compiled for Java 17, but the program using this API must be compiled and run on a supported JDK.

## 1. What Is an Attribute and Why Preserve It?

A `.class` file does not contain only opcodes. According to JVMS §4, structures such as classes, fields, methods, the `Code` attribute, and record components can carry **attributes**. Each attribute in binary format has a name (via a `CONSTANT_Utf8` entry), a length, and a payload. Names are defined by the JVM for standard attributes; tools can also define custom names that the JVM does not know how to decode.

```text
ClassFile
  ├── constant_pool
  ├── this_class / super_class / interfaces
  ├── fields[]
  │    └── attributes[]                 e.g., ConstantValue, Signature
  ├── methods[]
  │    ├── attributes[]                 e.g., Code, MethodParameters
  │    └── Code
  │         ├── bytecode
  │         ├── exception_table
  │         └── attributes[]            e.g., LineNumberTable, LocalVariableTable
  └── attributes[]                      e.g., SourceFile, RuntimeVisibleAnnotations
```

For example, `javac -g -parameters Sample.java` can produce the following metadata:

- **`SourceFile`**: source file name, useful for displaying stack traces or source mapping.
- **`LineNumberTable`**: maps bytecode positions to source line numbers. Debuggers and stack traces can use this data.
- **`LocalVariableTable`**: local variable names, types, and live scopes; commonly used by debuggers.
- **`LocalVariableTypeTable`**: generic type information for local variables, typically present when there are applicable generic variables and the compiler emits the metadata.
- **`MethodParameters`**: names and flags of declared parameters; controlled by `-parameters` when using `javac`, and distinct from `LocalVariableTable`. Reflection can use it.
- **`Signature`**: generic signature of a class, field, or method. Accidentally dropping it can lose generic information used by reflection/frameworks.
- **`RuntimeVisibleAnnotations` and other annotation attributes**: can directly affect reflection and frameworks such as DI, validation, and serialization.
- **`StackMapTable`**: JVM type verification data. This is **not just debug metadata**; losing it or writing it incorrectly can prevent the class from verifying.
- **Unrecognized attributes**: extensions from compilers, coverage tools, profilers, or frameworks. The parser does not know what the payload means, but the tool that created the attribute may depend on it.

When transforming a class, the goal is not to “keep every byte in the file unchanged”. The goal is to **preserve the necessary semantics** while rebuilding reference indices and offsets affected by the changes.

## 2. Distinguishing the Three Metadata Groups

| Group | Examples | Consequence if Lost / Written Incorrectly |
| --- | --- | --- |
| **Debug information** | `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`, `SourceFile`, `SourceDebugExtension` | May lose line numbers/variable names/scopes or source mapping info; code may still run, but debugging becomes difficult. |
| **Standard attributes with program/JVM meaning** | `Signature`, `MethodParameters`, `RuntimeVisibleAnnotations`, `Exceptions`, `NestHost`, `Record`, `PermittedSubclasses`, `StackMapTable` | May lose metadata needed for reflection, frameworks, class semantics, or validity during verification/linking. |
| **Unrecognized attributes** | Custom names such as `VendorTrace`, `ToolMarker`, `MysteryTag` | The API only sees name + payload; keeping the bytes may be necessary for another tool, but the payload may also contain indices that become stale after transformation. |

**Do not equate “not an opcode” with “unimportant”.** Removing `LineNumberTable` may not affect runtime behavior but leaves stack traces without line numbers; removing `RuntimeVisibleAnnotations` can alter framework behavior; and mishandling `StackMapTable` can cause a `VerifyError`.

Similarly, **`MethodParameters` is not `LocalVariableTable`**. Requesting to drop debug pseudo-instructions with `DROP_DEBUG` does not mean parameter information, annotations, or `SourceFile` are also removed.

## 3. How the Class-File API Models Attributes

The API reads bytes into a model:

```java
// Illustrative code inside a method; bytes is a byte[] of a valid class.
ClassFile cf = ClassFile.of();
ClassModel model = cf.parse(bytes);
List<Attribute<?>> classAttributes = model.attributes();
```

The illustrative code requires importing `java.lang.classfile.ClassFile`, `ClassModel`, `Attribute`, and `java.util.List`. `ClassModel` provides both the list of fields/methods, child models, and traversal over `ClassElement`s.

There are **two important perspectives**:

1. **Attributes with their own models**: for example `SourceFileAttribute`, `SignatureAttribute`, `RuntimeVisibleAnnotationsAttribute`, `UnknownAttribute`. They can be inspected via `model.attributes()` or looked up using the corresponding mapper (`findAttribute(...)`).
2. **Information “flattened” into the related model**: `LineNumberTable` is not simply a `ClassElement`; lines appear as `LineNumber` pseudo-instructions in `CodeModel`. Similarly, `LocalVariableTable` entries are traversed as `LocalVariable`; `LocalVariableTypeTable` entries are `LocalVariableType`. `BootstrapMethods` also has a representation tied to the constant pool. You cannot guarantee preserving them merely by iterating over class-level attributes and writing them back.

Java 24+ example to count debug pseudo-instructions:

```java
// model: ClassModel read from ClassFile.of(...).parse(bytes)
// Illustrative snippet inside a method; requires importing LineNumber, LocalVariable.
long lineEntries = model.methods().stream()
    .flatMap(method -> method.code().stream())
    .flatMap(code -> code.elementStream())
    .filter(element -> element instanceof LineNumber)
    .count();

long localEntries = model.methods().stream()
    .flatMap(method -> method.code().stream())
    .flatMap(code -> code.elementStream())
    .filter(element -> element instanceof LocalVariable)
    .count();
```

Whether these pseudo-instructions are surfaced or excluded from traversal depends on the **options** of the `ClassFile` context. Not every method has `Code` (e.g., abstract/native), so `method.code()` returns `Optional<CodeModel>`.

## 4. Preservation Options in `ClassFile.of(...)`

An intentional configuration to **prioritize preserving** metadata:

```java
ClassFile preserving = ClassFile.of(
    ClassFile.DebugElementsOption.PASS_DEBUG,
    ClassFile.LineNumbersOption.PASS_LINE_NUMBERS,
    ClassFile.AttributesProcessingOption.PASS_ALL_ATTRIBUTES
);
```

This configuration is suitable when you need to keep existing data, but it **does not replace validation** if bytecode, class structure, or the constant pool changes.

| Option | Meaning |
| --- | --- |
| `DebugElementsOption.PASS_DEBUG` | Allows processing debug pseudo-instructions such as `LocalVariable`, `LocalVariableType`, `CharacterRange`. This is the default. |
| `DebugElementsOption.DROP_DEBUG` | Drops those debug pseudo-instructions from traversal and the builder when the related structure is processed. |
| `LineNumbersOption.PASS_LINE_NUMBERS` | Preserves `LineNumber` elements when processing `CodeModel`. This is the default. |
| `LineNumbersOption.DROP_LINE_NUMBERS` | Drops `LineNumber` from traversal and the builder; does not stop bytecode execution from working. |
| `AttributesProcessingOption.PASS_ALL_ATTRIBUTES` | Attempts to preserve original attributes during transformation, including those whose stability cannot be verified; this is the default. |
| `AttributesProcessingOption.DROP_UNKNOWN_ATTRIBUTES` | Drops attributes whose dependencies are classified as `AttributeStability.UNKNOWN` during transformation. |
| `AttributesProcessingOption.DROP_UNSTABLE_ATTRIBUTES` | Drops attributes with dependencies of level `UNSTABLE` or higher (including the `UNKNOWN` group) during transformation. |

The **debug** options and **attribute stability** options are separate decisions. For example, you can request to keep debug pseudo-instructions while dropping unknown attributes. Or you can keep all class-level attributes while dropping line numbers in code. Do not lump everything together as “debug attributes”.

### 4.1. Default “PASS” Does Not Guarantee Every Transformation Preserves Data

The Class-File API allows transforming by feeding each element into a builder:

```java
ClassFile cf = ClassFile.of();
ClassModel source = cf.parse(inputBytes);
byte[] result = cf.transformClass(source, ClassTransform.ACCEPT_ALL);
```

`ClassTransform.ACCEPT_ALL` passes class-level elements through the builder. When the library sees that a structure has not changed, it can optimize by **copying an entire byte region** rather than exploding it into individual code elements (*bulk copy*). Conversely, when transforming method bodies, processing `CodeModel` walks through line/variable/label elements and applies the debug options.

Therefore, **`DROP_DEBUG` is not a global switch that “deletes every debug entry in any output file”**. If a code body is bulk-copied intact, the result can still retain the debug attributes of that block. To intentionally drop pseudo-instructions, the transform must **actually enter method bodies**, for example:

```java
ClassFile drop = ClassFile.of(
    ClassFile.DebugElementsOption.DROP_DEBUG,
    ClassFile.LineNumbersOption.DROP_LINE_NUMBERS
);

byte[] withoutCodeDebug = drop.transformClass(
    drop.parse(originalBytes),
    ClassTransform.transformingMethodBodies(CodeTransform.ACCEPT_ALL)
);
```

Here, `CodeTransform.ACCEPT_ALL` still keeps the code elements **presented to it**, while the debug types have already been excluded from traversal by the options. The difference between **bulk-copy** and **explode/rebuild** is important to remember when inspecting metadata after a transformation.

### 4.2. An Attribute Can Be “Preserved” Yet No Longer Correct

Standard attributes usually have a **mapper** that understands the constant pool, labels, or related structures. When the API rebuilds, the mapper can update those modeled indices.

For an **unrecognized** attribute, the payload is just opaque bytes. The API cannot automatically know whether the payload contains:

- Indices into the constant pool (e.g., pointing to names/descriptors);
- Bytecode offsets or exception handler indices;
- Reordered field/method/interface indices;
- Version info, checksums, or compiler/tool-specific layouts.

If the constant pool changes or bytecode shifts and you only copy the payload, the attribute may **still exist in binary form while being semantically wrong**. Thus, `PASS_ALL_ATTRIBUTES` is a **preservation policy**, not a promise to automatically remap every unknown format.

## 5. Standard Attributes: Preserve Structure Correctly, Not Just Copy Names

When transforming a method body, metadata that references **instruction positions** must be handled alongside the code changes.

| Attribute / Model | Typical Dependency | How to Preserve Safely |
| --- | --- | --- |
| `LineNumberTable` → `LineNumber` | Bytecode position corresponding to source line | Keep/update line entries according to the new instructions; do not copy old offsets verbatim if instructions are added. |
| `LocalVariableTable` → `LocalVariable` | Slot + start/end scope labels | Keep label scopes valid; update scopes and slots when changing code/local variables. |
| `LocalVariableTypeTable` → `LocalVariableType` | Similar to local-variable scope, plus generic signature | Keep synchronized with `LocalVariableTable` and descriptor/signature when still applicable. |
| `StackMapTable` | Frames/types at control-flow-relevant positions | Let the API rebuild stack maps where appropriate, or supply exact frames with explicit configuration; verify output on the JVM. |
| `SourceFile` / `SourceDebugExtension` | Source name / source mapping data | Keep if it still accurately describes the code; renaming/merging sources may require updates. |
| `MethodParameters` | Method parameter names and flags | Keep if the method descriptor/signature is unchanged; if the signature changes, update to match. |
| `Signature` | Generic signature of class, field, method | Keep when still valid after transformation; do not equate with the JVM descriptor. |
| `RuntimeVisibleAnnotations` / type annotations | Annotated target, sometimes index/offset/target | Check positions and validity after changing code or member lists. |
| `Record`, `NestHost`, `NestMembers`, `PermittedSubclasses` | Structural relationships between classes/members | Do not arbitrarily delete or keep metadata that no longer matches the constructed class. |

**Example:** if you instrument a method by inserting new instructions at the start of the method, a `LineNumberTable` that only stores absolute offsets from the old version can point to the wrong instructions; the Class-File API represents line numbers and local-variable scopes via code elements/labels to support corresponding reconstruction. You still need to decide **which source line makes sense** for the new instrumentation instructions: there is no single guess that is universally right for every framework.

**Note:** `StackMapTable` and `BootstrapMethods` are handled specially by the API and do not always appear as simple elements you can manually `with(attribute)` at every level. Use builders/transforms appropriate for the model rather than manually copying an attribute's byte block and hoping indices remain valid.

## 6. Unrecognized Attributes: What Is `UnknownAttribute`?

When encountering an attribute that has no mapper in `Attributes` and no registered custom mapper, the Class-File API can represent it as an `UnknownAttribute`.

Basic operations:

```java
// Illustrative code with a ClassModel containing an unknown attribute at the class level.
for (Attribute<?> attr : model.attributes()) {
    if (attr instanceof UnknownAttribute unknown) {
        System.out.println(unknown.attributeName().stringValue()
                + " payloadBytes=" + unknown.contents().length);
    }
}
```

Meaning:

- `attributeName()` returns the attribute name in the constant pool.
- `contents()` returns the **uninterpreted** payload; seeing a byte array does not allow concluding its format or dependencies.
- `UnknownAttribute` is not a “broken attribute”; it may be valid metadata that another tool understands and the JVM ignores according to class-file rules.
- Which levels an unknown attribute can appear at depends on the API version and class-file structure. In JDK 24, the `UnknownAttribute` documentation states that it is not delivered as an element of `CodeModel` traversal; do not assume iterating only over code elements catches every unknown attribute.

### 6.1. Three Strategies for Handling Unknown Attributes

**Preserve (`PASS_ALL_ATTRIBUTES`)** when you do not change structures that the payload might reference, want to preserve another tool's metadata, and accept that the payload is not semantically verified. This is the default, suitable for minimal transformations or verified round-trips.

**Drop (`DROP_UNKNOWN_ATTRIBUTES`)** when the output does not need unknown formats and the risk of keeping a payload with stale indices/offsets outweighs the risk of losing metadata. Understand that another tool may need that attribute; the JVM running without error does not prove external data is still intact.

**Define a custom mapper (`AttributeMapperOption.of(...)`)** if you know the custom format: write the corresponding `AttributeMapper` and `CustomAttribute`, modeling the indices/labels, applicable structures, multiplicity, and stability of the attribute so the API has data to update properly. This is the sustainable approach when your tool **owns** that metadata or must preserve its contract.

Note that a custom mapper has lower priority than the standard mappers in `Attributes`; do not use it to override the meaning of a standard attribute built into the JDK.

## 7. JDK 24+ Experiment: Observing Keep, Drop Debug, and Keep/Drop Unknown

The experiment consists of two Java files, requiring no Maven/Gradle or external libraries. We use a small class compiled with `-g -parameters`, then a Class-File API program parses and round-trips it:

1. **Original:** has `SourceFile`, `RuntimeVisibleAnnotations`, `MethodParameters`, `LineNumberTable`, and `LocalVariableTable`.
2. **Default round-trip:** `ClassTransform.ACCEPT_ALL` preserves the existing metadata.
3. **Unknown fixture:** on a test **copy** of the bytes, rename the **UTF8 name of the `SourceFile` attribute** to an unknown name of the same length, `MysteryTag`. This is a custom manipulation solely to create a test fixture, not for use as a production class-file editor.
4. **`PASS_ALL_ATTRIBUTES`:** the fixture still has `MysteryTag` after transformation.
5. **`DROP_UNKNOWN_ATTRIBUTES`:** the fixture no longer has `MysteryTag` after transformation.
6. **`DROP_DEBUG + DROP_LINE_NUMBERS` while traversing `CodeModel`:** debug pseudo-instructions are dropped, while `SourceFile`, annotations, and `MethodParameters` remain.

### 7.1. `Sample.java` — Input Class

```java
@Deprecated
public class Sample {
    public static int sum(int left, int right) {
        int total = left + right;
        return total;
    }
}
```

`@Deprecated` on the class produces suitable annotation metadata in the class file; `-parameters` preserves the parameter names of `sum`; `-g` tells `javac` to emit full supported debug metadata. The default constructor also has code and line numbers. The file must be named `Sample.java`.

### 7.2. `AttributeInspector.java` — Complete Class-File API Program

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.attribute.SourceFileAttribute;
import java.lang.classfile.attribute.RuntimeVisibleAnnotationsAttribute;
import java.lang.classfile.attribute.MethodParametersAttribute;
import java.lang.classfile.attribute.UnknownAttribute;
import java.lang.classfile.instruction.LineNumber;
import java.lang.classfile.instruction.LocalVariable;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class AttributeInspector {
    private static final ClassFile KEEP = ClassFile.of(
            ClassFile.DebugElementsOption.PASS_DEBUG,
            ClassFile.LineNumbersOption.PASS_LINE_NUMBERS,
            ClassFile.AttributesProcessingOption.PASS_ALL_ATTRIBUTES);

    public static void main(String[] args) throws Exception {
        byte[] original = Files.readAllBytes(Path.of("Sample.class"));
        byte[] same = KEEP.transformClass(
                KEEP.parse(original), ClassTransform.ACCEPT_ALL);
        byte[] unknown = renamedAttributeFixture(original);

        byte[] withUnknown = KEEP.transformClass(
                KEEP.parse(unknown), ClassTransform.ACCEPT_ALL);

        ClassFile dropUnknown = ClassFile.of(
                ClassFile.AttributesProcessingOption.DROP_UNKNOWN_ATTRIBUTES);
        byte[] withoutUnknown = dropUnknown.transformClass(
                dropUnknown.parse(unknown), ClassTransform.ACCEPT_ALL);

        ClassFile dropDebug = ClassFile.of(
                ClassFile.DebugElementsOption.DROP_DEBUG,
                ClassFile.LineNumbersOption.DROP_LINE_NUMBERS);
        byte[] withoutDebug = dropDebug.transformClass(
                dropDebug.parse(original),
                ClassTransform.transformingMethodBodies(CodeTransform.ACCEPT_ALL));

        print("original", original);
        print("roundTrip", same);
        print("unknownFixture", unknown);
        print("keepUnknown", withUnknown);
        print("dropUnknown", withoutUnknown);
        print("dropDebug", withoutDebug);
    }

    private static void print(String label, byte[] bytes) {
        ClassModel model = KEEP.parse(bytes);
        boolean source = model.attributes().stream()
                .anyMatch(a -> a instanceof SourceFileAttribute);
        boolean annotations = model.attributes().stream()
                .anyMatch(a -> a instanceof RuntimeVisibleAnnotationsAttribute);
        boolean parameters = model.methods().stream()
                .flatMap(m -> m.attributes().stream())
                .anyMatch(a -> a instanceof MethodParametersAttribute);
        long lines = model.methods().stream()
                .flatMap(m -> m.code().stream())
                .flatMap(c -> c.elementStream())
                .filter(e -> e instanceof LineNumber).count();
        long locals = model.methods().stream()
                .flatMap(m -> m.code().stream())
                .flatMap(c -> c.elementStream())
                .filter(e -> e instanceof LocalVariable).count();
        long unknown = model.attributes().stream()
                .filter(a -> a instanceof UnknownAttribute &&
                        a.attributeName().stringValue().equals("MysteryTag"))
                .count();
        System.out.printf(
                "%s source=%s annotations=%s parameters=%s lines=%d locals=%d unknown=%d%n",
                label, source, annotations, parameters, lines, locals, unknown);
    }

    private static byte[] renamedAttributeFixture(byte[] input) {
        byte[] bytes = input.clone();
        byte[] from = "SourceFile".getBytes(StandardCharsets.US_ASCII);
        byte[] to = "MysteryTag".getBytes(StandardCharsets.US_ASCII);
        int count = 0;
        for (int i = 0; i <= bytes.length - from.length; i++) {
            boolean matches = true;
            for (int j = 0; j < from.length; j++) {
                if (bytes[i + j] != from[j]) {
                    matches = false;
                    break;
                }
            }
            if (matches) {
                System.arraycopy(to, 0, bytes, i, to.length);
                count++;
            }
        }
        if (count != 1) {
            throw new IllegalStateException(
                    "Unexpected SourceFile markers: " + count);
        }
        return bytes;
    }
}
```

The code above uses the standard **JDK 24+** API and is a standalone program. No module declaration or `--add-modules` is needed when compiling both files with a full JDK.

**Why is this fixture valid for the test?** For this sample class, the UTF8 name `SourceFile` appears exactly once, and both `SourceFile` and `MysteryTag` are **10 ASCII bytes** long. Replacing the UTF8 payload of the **attribute name** without changing its length turns the class-level `SourceFile` into an unknown attribute named `MysteryTag`. It is only meant to test the **pass/drop** policy; the inner payload still has the original `SourceFile` structure, so do not infer that this is a real `MysteryTag` business format. If changing the source or compiler causes the name to appear multiple times, the `count != 1` guard forces a stop.

Do not apply this byte-string search-and-replace operation to any class file outside of testing. Any real class-file modification should go through the proper model and handle the constant pool correctly.

### 7.3. Compiling and Running

Place both files in a new directory and run with **JDK 24 or later**:

```bash
javac -version
javac -g -parameters Sample.java
javac AttributeInspector.java
java AttributeInspector
```

The `-g` option of `javac` enables source line and local variable information; `-parameters` enables parameter metadata. The `javac AttributeInspector.java` command must use JDK 24+ because importing `java.lang.classfile` is not available in Java 17. On Windows PowerShell, these commands also run directly when the JDK is configured in `PATH`.

**Verified stdout on OpenJDK 24.0.2** (with no other JVM agent interfering with the test files):

```text
original source=true annotations=true parameters=true lines=3 locals=4 unknown=0
roundTrip source=true annotations=true parameters=true lines=3 locals=4 unknown=0
unknownFixture source=false annotations=true parameters=true lines=3 locals=4 unknown=1
keepUnknown source=false annotations=true parameters=true lines=3 locals=4 unknown=1
dropUnknown source=false annotations=true parameters=true lines=3 locals=4 unknown=0
dropDebug source=true annotations=true parameters=true lines=0 locals=0 unknown=0
```

Output explanation table:

| Line | What Is Demonstrated |
| --- | --- |
| `original` | The class has standard/debug metadata; no unknown attribute yet. |
| `roundTrip` | `ClassTransform.ACCEPT_ALL` preserves the sample class's information during round-trip. |
| `unknownFixture` | `SourceFile` is renamed to `MysteryTag` on a **copy**, so `source=false`, `unknown=1`; annotations, parameters, lines, and local variables remain. |
| `keepUnknown` | `PASS_ALL_ATTRIBUTES` retains one `UnknownAttribute` in this controlled case. |
| `dropUnknown` | `DROP_UNKNOWN_ATTRIBUTES` removes `MysteryTag` from the result. |
| `dropDebug` | When forcing traversal and rebuilding of code bodies, `DROP_DEBUG`/`DROP_LINE_NUMBERS` remove local-variable and line pseudo-instructions; other standard attributes remain. |

**Why `lines=3` and `locals=4`?** With `javac 24.0.2` and this sample class, there are three line-number entries (including the constructor and the `sum` method) and four local-variable entries (`this` in the constructor, plus `left`, `right`, `total` in `sum`). This is the result of the specific configuration/compiler; when changing the source or compiler version, the counts may differ. The core guarantee of the experiment is the **preserved-from-original vs. dropped-in-reprocessed** relationship, not memorizing the entry counts.

**Easiest detail to miss:** even though `dropDebug` no longer has `LineNumber`/`LocalVariable`, it still has `SourceFile` and `MethodParameters`. You must choose preservation policies for **each kind of metadata**, and cannot assume one option deletes everything related to debugging.

### 7.4. Further Inspection with `javap`

On the original class:

```bash
javap -v -p Sample
javap -l -p Sample
```

You can look for the `SourceFile`, `RuntimeVisibleAnnotations`, `MethodParameters`, `LineNumberTable`, and `LocalVariableTable` entries. Note that the `AttributeInspector` program in this article only keeps the transformed results **in `byte[]` arrays** and does not write them to files. Therefore, running `javap Sample` still shows the **original** `Sample.class` data; it cannot automatically display the in-memory `withUnknown` or `withoutDebug` arrays. To use `javap` on transformed output, you must explicitly write those bytes to a file and inspect that file.

In real applications, after transformation you should also run `ClassFile.verify(...)`, test class loading, and test framework/reflection behavior to ensure the output has **valid** metadata, not just attribute names that look like the original.

## 8. Working with Custom Attributes of Known Format

If a tool adds a custom attribute, such as `TraceSpanMap` containing bytecode offsets, there are two scenarios:

**Pass-through only**: you do not change the code layout/constant pool, or you know the data policy allows keeping the payload as-is. You can use `PASS_ALL_ATTRIBUTES` and `ClassTransform.ACCEPT_ALL`, then verify the attribute is still written to the file. This is a practical strategy for transforms that do not touch related structures.

**Must modify code/constant pool**: merely keeping the old `byte[]` does not guarantee offsets/indices remain valid. In this case, model `TraceSpanMap` with a **custom `AttributeMapper`**. The reader/writer mapper understands the structure, attaches the data to the appropriate model, and declares the attribute's stability. You can register the mapper with:

```java
// Illustrative API code, not a standalone program.
// customMapperResolver is an implemented Function<Utf8Entry, AttributeMapper<?>>.
ClassFile cf = ClassFile.of(
    ClassFile.AttributeMapperOption.of(customMapperResolver)
);
```

The custom mapper must return `null` if it does not recognize the queried name, and the name returned by the mapper must match the name being parsed. Do not arbitrarily declare an opaque payload as “stable”: if it contains code offsets or constant-pool indices, its stability depends on your transformation operations.

**Note on backward/forward compatibility:** A future JDK may add new standard attributes. If the parser uses `UnknownAttribute` to preserve such an attribute, that data may carry meaning for a newer JVM. If your tool **must understand the entire structure** before being allowed to modify it, check the major version and element types, and safely decline processing when encountering something unrecognized. If you only modify a small part, you can pass through the remaining parts under an appropriate contract and QA.

## 9. In a Java Agent: How Should `classfileBuffer` Be Handled?

A `ClassFileTransformer` can use the Class-File API directly on the `classfileBuffer` array passed in by the JVM. The code below **only illustrates the idea** and is not a standalone agent class:

```java
// Inside ClassFileTransformer.transform(...) on JDK 24+:
if (!"demo/example/Target".equals(className)) {
    return null;
}

ClassFile cf = ClassFile.of(
    ClassFile.DebugElementsOption.PASS_DEBUG,
    ClassFile.LineNumbersOption.PASS_LINE_NUMBERS,
    ClassFile.AttributesProcessingOption.PASS_ALL_ATTRIBUTES
);
ClassModel input = cf.parse(classfileBuffer);
byte[] output = cf.transformClass(input, ClassTransform.ACCEPT_ALL);
return output;
```

This is a **round-trip** example without logic changes. In a real agent, when performing code transformations, replace `ClassTransform.ACCEPT_ALL` with your transform and **preserve all elements you do not intend to change**. Do not mutate the `classfileBuffer` array provided by the JVM directly. If you do not want to transform anything, returning `null` is simpler and cheaper than rebuilding the class file.

Because **multiple agents/transformers** may be present, `classfileBuffer` is not necessarily the class on disk: an earlier transformer may have already modified metadata. You must **parse the bytes received in the callback**, rather than reloading `.class` from a resource and overwriting another agent's transformation chain.

When retransforming/redefining an already-loaded class, JVM structural modification limits still apply. Attribute preservation documentation does not grant permission to add/remove fields/methods in an already-loaded class. Changes to instruction positions or stack maps still need to be re-verified on the actual output class.

## 10. QA Before Shipping Transformed Class Files

After building the new `byte[]` or `.class`, you should verify at **three levels**:

### 10.1. Structural Level

- Parse the output with `ClassFile.of().parse(output)` and inspect **class, field, method, and code**; compare the relevant attribute lists with the input.
- Count/compare `LineNumber`, `LocalVariable`, `LocalVariableType` or directly inspect the corresponding attributes as needed; do not only count total class-level attributes.
- Check that `SourceFile`, `MethodParameters`, `Signature`, annotations, `Record`, `Nest*`, and other required attributes remain valid for the new structure.
- For unknown/custom attributes, record **name, attachment location, length, and checksum** to observe differences; merely keeping the checksum identical does not prove the payload is still valid after constant pool/code offset changes.
- Do not use `Arrays.equals(input, output)` as the sole criterion. A transformed class file may have a reordered constant pool while preserving equivalent behavior.

### 10.2. JVM Level

- Use `ClassFile.verify(output)` where appropriate and load/run the output class on the target JVM version.
- For instrumented code, test exception branches, complex methods, generic signatures, nested classes, records, and annotated classes.
- When stack maps are regenerated, run the actual verifier; `VerifyError`/`ClassFormatError` indicates invalid output, not an error that can be ignored as “just debug”.
- Check the class file version and valid structural changes if redefining an already-loaded class.

### 10.3. User Tooling Level

- Open a debugger, set breakpoints on the right source lines, and check that stack traces still include line numbers.
- Inspect local variables and parameter names when tooling requires them.
- Verify reflection/frameworks still see the expected annotations and generic/method-parameter metadata.
- If third-party software reads unknown/custom attributes, run **that tool's integration tests**; preserving the payload byte-for-byte is not enough to guarantee the tool still understands it when indices or offsets have changed.

## 11. Common Issues and Fixes

| Symptom | Common Cause and How to Fix |
| --- | --- |
| Class runs, but stack traces lack line numbers | `LineNumberTable` was dropped or rebuilt incorrectly; check `PASS_LINE_NUMBERS` and the code transform. |
| Debugger does not show variable names | Check `-g` at compile time and `LocalVariableTable`/`PASS_DEBUG`; obfuscated code may have stripped names at the source. |
| Reflection parameter names missing even though local-variable info exists | `MethodParameters` is distinct from `LocalVariableTable`; check `-parameters` and how method attributes are passed through. |
| Generic metadata lost | Check `Signature` and related attributes; do not compare only the JVM descriptor. |
| Annotations disappear after transformation | Check `RuntimeVisibleAnnotations`/type annotations and target locations; annotations cannot be treated as optional debug metadata. |
| `DROP_DEBUG` is enabled, yet output still has line/local tables | The code body may have been bulk-copied; try passing through `CodeTransform` to process pseudo-instructions and re-check. |
| `DROP_UNKNOWN_ATTRIBUTES` does not remove standard attributes | Expected per the option's scope: it targets attributes with `UNKNOWN` stability; to drop standard attributes, use an appropriate policy/transform. |
| Unknown attribute still exists, but the reading tool reports an error | The payload may contain stale constant-pool indices/code offsets; you need a format-aware mapper or a policy not to pass it through. |
| `VerifyError` appears after changing bytecode | Check code flow, stack map frames, labels/offsets/exception handlers, class structure, and target JVM. |
| Only checking `ClassModel.attributes()` and not seeing `LineNumberTable` | Line numbers are modeled as `LineNumber` inside `CodeModel`; you must traverse at the right level. |
| Byte-for-byte comparison of transformed class does not match the original | May be due to constant pool/layout; verify attribute semantics, the verifier, and runtime behavior. |
| Program using `java.lang.classfile` fails to compile on JDK 17 | The standard API is only available from JDK 24; use JDK 24+ and do not enable preview for the standard release. |

## 12. Self-Check Exercises

**Question 1.** A transformer wants to add logging at the start of a method while keeping debugging working. Is preserving the `LineNumberTable` bytes from the old class sufficient?

**Answer:** No. Line entries must be kept/updated according to the new code positions; adding bytecode can shift offsets. Work through `CodeModel` and verify breakpoints/line mapping after transformation.

**Question 2.** In the example, why does `unknownFixture` have `source=false` even though it still has line numbers?

**Answer:** The fixture renames the **class-level `SourceFile`** to `MysteryTag` on a copy of the bytes, while the debug attributes inside `Code` are untouched. `SourceFile` and `LineNumberTable` are two separate types.

**Question 3.** Does enabling `DROP_DEBUG` automatically remove `RuntimeVisibleAnnotations` and `MethodParameters`?

**Answer:** No. Those attributes have different meanings and are modeled separately. For example, `dropDebug` still preserves both annotations and method parameter metadata.

**Question 4.** An unknown attribute contains bytecode offsets, and a transform inserts instructions in the middle of a method. Does `PASS_ALL_ATTRIBUTES` automatically adjust the offsets inside the unknown payload?

**Answer:** No. Because the payload's structure is unknown, the API does not have enough information to fix offsets. You need a custom mapper that understands the format, or you should not preserve the attribute if correctness cannot be guaranteed.

**Question 5.** When rebuilding an entire class with `ClassTransform.ACCEPT_ALL`, can you guarantee the output is always byte-for-byte identical to the input?

**Answer:** No. The contract focuses on the class model and semantics; there may be bulk-copy optimizations or structural re-representations. Verify the model and behavior instead of requiring identical file checksums.

**Question 6.** Why must you pay attention to whether a transform enters `CodeModel` when using options to drop debug pseudo-instructions?

**Answer:** If code is bulk-copied because it is unchanged, the library may preserve the old attribute bytes. Only when processing a method body via `CodeTransform` do the `DROP_*` options decide whether debug pseudo-instructions are passed to the builder.

**Question 7.** If another tool writes a custom attribute and you want to preserve it across constant pool changes, where should you start?

**Answer:** The format documentation for that attribute: identify its dependencies on the constant pool/labels/offsets, then build an appropriate custom `AttributeMapper` or agree on a drop policy if it cannot be reconstructed accurately.

## 13. Summary and References

**Key takeaways when using the Class-File API for instrumentation:**

1. Preserve **debug metadata** when needed via `PASS_DEBUG` and `PASS_LINE_NUMBERS`, while ensuring `CodeModel` is processed properly; debug lines/local variables may need remapping when instructions move.
2. Keep **standard attributes** valid by passing through model elements and letting mappers/builders handle the constant pool/labels; do not drop annotations, generic signatures, runtime metadata, or stack maps just because they are not opcodes.
3. For **unrecognized attributes**, `PASS_ALL_ATTRIBUTES` attempts to keep the payload, while `DROP_UNKNOWN_ATTRIBUTES`/`DROP_UNSTABLE_ATTRIBUTES` selectively drop groups with unsafe dependencies. Preserving bytes **does not mean** preserving semantics across every transformation.
4. When you know a custom attribute's format, use `AttributeMapperOption` and a dependency-aware mapper instead of “blind copying”.
5. Always verify **class structure, verification, and debugger/framework behavior** on the output, especially for instrumentation that modifies bytecode.

**Official sources (Java 24/25 and JVMS):**

- [JEP 484 — Class-File API, standardized in JDK 24](https://openjdk.org/jeps/484)
- [Java 24 API — ClassFile and options](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java 25 API — Class-File API package guide: reading, attributes, transforms](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html)
- [Java 25 API — AttributesProcessingOption: PASS_ALL / DROP_UNKNOWN / DROP_UNSTABLE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.AttributesProcessingOption.html)
- [Java 25 API — ClassTransform.ACCEPT_ALL and ClassTransform.transformingMethodBodies](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [Java 24 API — UnknownAttribute](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/attribute/UnknownAttribute.html)
- [JVMS §4.7 — Attributes](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html#jvms-4.7)