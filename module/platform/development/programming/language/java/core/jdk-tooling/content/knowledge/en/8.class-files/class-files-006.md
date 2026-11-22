# Attributes in Java Class Files

In the Java class file format, an **attribute** is a fixed-structure metadata entry with an explicit length used to describe additional information about a class, field, method, bytecode block, or record component. Attributes tell the JVM and tools such as compilers, debuggers, decompilers, and bytecode analyzers how to interpret additional characteristics of a program.

For example, a class file can contain attributes that describe:

- The bytecode of a method and its exception handler table.
- Source code line numbers corresponding to bytecode offsets.
- Local variable names for debugging.
- Annotations to be read via reflection.
- Generic signatures whose types were erased in bytecode.
- Module, record, sealed class, or nested class relationships.
- Bootstrap data for `invokedynamic` and dynamic constants.

Attributes are part of the **binary format**. They are not synonymous with annotations in source code: annotations are a way to declare metadata, whereas `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations`, and related attributes are specific representations of that metadata in a class file.

## 1. Where Attributes Appear in a Class File

A class file has an overall structure consisting of a magic number, version, constant pool, class information, interfaces, fields, methods, and an attribute list:

~~~text
ClassFile {
    magic
    minor_version
    major_version
    constant_pool
    access_flags
    this_class
    super_class
    interfaces[]
    fields[]
    methods[]
    attributes[]
}
~~~

Each `field_info` and `method_info` structure also has its own attribute list. Some attributes contain nested attribute lists as well. For example, `Code` holds a method's bytecode and contains nested attributes to describe line numbers, local variables, or stack maps.

Therefore, attributes can appear at multiple levels:

- **Class-level:** metadata for the entire class, such as `SourceFile`, `InnerClasses`, `NestMembers`, `Record`.
- **Field-level:** metadata for a field, such as `ConstantValue`, `Signature`, annotations.
- **Method-level:** metadata for a method, such as `Code`, `Exceptions`, `MethodParameters`, `AnnotationDefault`.
- **Code-level:** metadata attached to the bytecode section, such as `LineNumberTable`, `LocalVariableTable`, `StackMapTable`.
- **Record-component-level:** metadata for each record component, including generic signatures and applicable annotations.

Not every attribute is allowed to appear at every level. The valid locations and contents of each attribute are defined in the Java Virtual Machine Specification (JVMS).

## 2. General Binary Structure of `attribute_info`

In a class file, each attribute follows this general structure:

~~~text
attribute_info {
    u2 attribute_name_index;
    u4 attribute_length;
    u1 info[attribute_length];
}
~~~

Meaning:

| Field | Size | Meaning |
|---|---:|---|
| `attribute_name_index` | 2 bytes (`u2`) | Index pointing to a `CONSTANT_Utf8_info` entry in the constant pool containing the attribute name |
| `attribute_length` | 4 bytes (`u4`) | Number of bytes in the `info` payload |
| `info` | Variable length | Attribute-specific data |

For example, names like `Code`, `SourceFile`, or `Signature` are stored as UTF-8 constants in the constant pool. `attribute_name_index` points to the corresponding entry. The `info` section is interpreted according to the specification of each attribute type.

The explicit-length structure lets a class file reader know where each attribute begins and ends. A tool can skip an attribute it does not understand by using `attribute_length` to advance to the next attribute.

**Note:** `u2` and `u4` are unsigned integer types in the class file format specification, not Java data types with those names. When writing a custom parser, read in big-endian order and validate array/length bounds before accessing data.

## 3. How Attributes Differ from Constant Pool, Descriptors, and Access Flags

Each component in a class file serves a distinct role:

| Component | Purpose |
|---|---|
| Constant pool | Stores constants, class names, field/method names, strings, and symbolic references |
| Descriptor | Describes field types and parameter/return type signatures at the JVM level |
| Access flags | Represents modifiers such as `public`, `final`, `static`, `abstract` in the class file format |
| Attribute | Supplements metadata or structured data for classes, fields, methods, code, and record components |

For example, the method:

~~~java
public String greet(int count) {
    return "hello";
}
~~~

has the JVM descriptor:

~~~text
(I)Ljava/lang/String;
~~~

The descriptor specifies the parameter and return types as represented at the JVM level. The `Signature` attribute can supplement generic type information that descriptors cannot express, while `Code` holds the bytecode that executes the method.

Do not treat everything in a class file as an attribute. Class names, descriptors, access flags, and the constant pool have their own dedicated structures in the format.

## 4. `Code` — The Attribute Holding Method Bytecode

`Code` is one of the most important attributes. It appears in `method_info` for methods that have a bytecode body. `abstract` or `native` methods have no method body bytecode and therefore do not have a `Code` attribute.

A `Code` attribute contains these main components:

- `max_stack`: maximum depth required for the operand stack in the method.
- `max_locals`: number of local variable slots required in the frame.
- `code_length`: number of bytes in the bytecode array.
- `code[]`: the bytecode instructions.
- `exception_table[]`: bytecode ranges and exception handlers.
- `attributes[]`: nested attributes inside `Code`.

Illustration:

~~~text
method_info
  |
  +-- Code
        |
        +-- max_stack
        +-- max_locals
        +-- code[]
        +-- exception_table[]
        +-- attributes[]
              |
              +-- LineNumberTable
              +-- LocalVariableTable
              +-- StackMapTable
~~~

For example, with the method:

~~~java
static int add(int left, int right) {
    return left + right;
}
~~~

The compiler generates instructions equivalent to loading two local variables, adding them on the operand stack, and returning the result. `Code` stores the actual instruction sequence; do not assume that each Java statement corresponds to exactly one instruction.

### 4.1. Exception Table in `Code`

`exception_table` describes protected bytecode regions and handler locations. Each entry contains:

- `start_pc`: bytecode offset where the protected region starts.
- `end_pc`: offset where the region ends, following the format's boundary rules.
- `handler_pc`: bytecode offset of the handler.
- `catch_type`: exception type to catch; a special value can represent a catch-all/finally handler.

The JVM uses this table when an exception is thrown within the corresponding range to locate the appropriate handler. This is the bytecode-level mechanism for `try-catch`, not the method's `throws` declaration list.

## 5. Attributes for Debugging

The compiler can record additional metadata so debuggers can map bytecode back to source code.

### 5.1. `SourceFile`

`SourceFile` stores the name of the source file used to compile the class, typically a name like `AttributeDemo.java`. It does not contain the full source code content, nor does it guarantee that the source file still exists on the runtime machine.

### 5.2. `LineNumberTable`

`LineNumberTable` maps bytecode offsets to source line numbers. Debuggers use this information to set line breakpoints and show the approximate position when a program pauses.

A single Java line can correspond to multiple instructions, or generate no separate instructions at all. Therefore, line mapping is debugging metadata rather than a strict one-to-one mapping between source lines and bytecode.

### 5.3. `LocalVariableTable`

`LocalVariableTable` stores local variable names, descriptors, slot indices, and the bytecode ranges over which each variable is in scope. Debuggers can use it to display variable names and values in a stack frame.

This information depends on debug options used during compilation. If the compiler does not emit local-variable debug metadata, the debugger may only show slot names or omit the original source variable names.

### 5.4. `LocalVariableTypeTable`

`LocalVariableTypeTable` supplements generic signatures for local variables when needed. `LocalVariableTable` typically describes erased types via descriptors; the type table helps debuggers and tooling know generic type information such as `List<String>`.

### 5.5. `SourceDebugExtension`

`SourceDebugExtension` can store extended debugging information, such as SMAP data in code-generation or source-transformation pipelines. Debugging tools can use this data to map generated code back to the original language or source file.

### 5.6. Controlling Debug Metadata with `javac`

Commonly used options:

~~~text
javac -g -d out AttributeDemo.java
javac -g:none -d out AttributeDemo.java
javac -g:lines,source -d out AttributeDemo.java
javac -g:lines,vars,source -d out AttributeDemo.java
~~~

- `-g` requests generating all debugging information supported by the compiler.
- `-g:none` generates no debugging information.
- `-g:lines,source` selects line numbers and source file information.
- `-g:lines,vars,source` selects line numbers, local variables, and source file information.

These options affect debug metadata in the class file without changing the logical meaning of the program. Some build tools or IDEs may configure debug settings independently.

## 6. Attributes Related to Constants and Declarations

### 6.1. `ConstantValue`

`ConstantValue` is attached to a field to represent an eligible constant initializer value in the class file. The typical case is a `static final` primitive or `String` initialized with a compile-time constant expression.

Example:

~~~java
public class Limits {
    public static final int MAX_RETRIES = 3;
    public static final String MODE = "safe";
}
~~~

The compiler can emit `ConstantValue` for these fields. The JVM uses this metadata when initializing field values according to class file rules.

Not every `final` field has `ConstantValue`. For example:

~~~java
public static final int MAX = Integer.parseInt("3");
~~~

A method call expression is not a compile-time constant expression, so the compiler typically generates initialization code in `<clinit>` instead of using `ConstantValue`.

In addition, the Java compiler may inline compile-time constant values into the bytecode of classes that reference them. If a constant's value is changed in a library, previously compiled client classes may continue using the old value until they are recompiled.

### 6.2. `Exceptions`

`Exceptions` lists the exception types declared in a method's `throws` clause.

Example:

~~~java
void load() throws java.io.IOException {
    // ...
}
~~~

This attribute stores declaration metadata for the compiler, IDEs, and API reflection tools. The JVM does not use it to enforce checked exceptions; checked exceptions are a language and compiler rule. Bytecode can still throw exceptions that are not listed in `Exceptions`.

### 6.3. `Signature`

`Signature` stores the generic signature for a class, field, method, or record component when needed. It preserves generic type information that type-erased JVM descriptors cannot fully represent.

Example:

~~~java
public class Box<T> {
    public T get() {
        return null;
    }
}
~~~

At the JVM level, type `T` is erased to its corresponding bound, typically `Object` if no explicit bound is given. The descriptor of `get()` reflects the erased type; `Signature` stores the generic form so reflection and tools can recover information about `T`.

`Signature` does not make the JVM execute generics as reified types. Java generics remain based on type erasure; the attribute only retains declaration metadata.

### 6.4. `MethodParameters`

`MethodParameters` stores the names and certain flags of method or constructor parameters. The compiler can emit this attribute when using:

~~~text
javac -parameters -d out AttributeDemo.java
~~~

Reflection reads this information via `Executable.getParameters()`, `Parameter.getName()`, and `Parameter.isNamePresent()`.

Do not confuse `MethodParameters` with `LocalVariableTable`:

- `MethodParameters` is method-level parameter name metadata that supports reflection.
- `LocalVariableTable` is debug metadata about local variables/slots and bytecode ranges.
- `-g:vars` and `-parameters` serve two different purposes.

If `MethodParameters` is absent, `Parameter.isNamePresent()` typically returns `false`; the returned name may be a synthesized name such as `arg0`, rather than the original name in source.

### 6.5. `Synthetic` and `Deprecated`

`Synthetic` indicates that an element was generated by the compiler and does not appear directly as a corresponding declaration in source code in the usual sense. Class files can also represent synthetic status via the `ACC_SYNTHETIC` access flag, depending on location and structure.

`Deprecated` is an attribute marking an element as deprecated at the class file level. The `@Deprecated` annotation can also be stored in annotation attributes; tools should read metadata according to their purpose rather than relying on a single indicator alone.

## 7. Annotation Attributes

Annotations in Java are represented by several class file attributes, depending on placement and retention.

| Attribute | Purpose |
|---|---|
| `RuntimeVisibleAnnotations` | Annotations readable via runtime reflection |
| `RuntimeInvisibleAnnotations` | Annotations not returned by standard runtime reflection, but stored in the class file |
| `RuntimeVisibleParameterAnnotations` | Runtime-visible annotations on method parameters |
| `RuntimeInvisibleParameterAnnotations` | Runtime-invisible annotations on parameters |
| `RuntimeVisibleTypeAnnotations` | Runtime-visible type-use annotations |
| `RuntimeInvisibleTypeAnnotations` | Runtime-invisible type-use annotations |
| `AnnotationDefault` | Default value of an annotation type element |

Example:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Marker {
    String value();
}

@Marker("example")
public class AnnotatedType {
}
~~~

The `@Marker("example")` annotation has `RUNTIME` retention, so the class file stores it in the appropriate runtime-visible attribute. Reflection can read it:

~~~java
Marker marker = AnnotatedType.class.getAnnotation(Marker.class);
System.out.println(marker.value());
~~~

Stdout:

~~~text
example
~~~

If an annotation uses `RetentionPolicy.CLASS`, the compiler still stores the metadata, but standard runtime reflection does not return it. With `RetentionPolicy.SOURCE`, the annotation is discarded from the class file after compilation.

Compile-time annotation processing and runtime annotation reflection are two different mechanisms. Processors read annotations through the compiler model; reflection reads runtime-visible annotations from class files while the application runs.

## 8. Attributes for Nested Classes, Nests, Records, and Sealed Classes

Newer Java versions added attributes to describe language constructs and class relationships.

### 8.1. `InnerClasses`

`InnerClasses` describes member or nested classes associated with a class file. It provides information such as the inner class, outer class, simple name, and corresponding access flags.

### 8.2. `EnclosingMethod`

`EnclosingMethod` identifies the enclosing class and method/constructor of a local or anonymous class. Tooling can use this metadata to understand where the class was declared.

### 8.3. `NestHost` and `NestMembers`

Nestmate metadata represents the nest relationship among classes that share `private` access within the same nest. A member class can point to its nest host, while the host lists the valid nest members.

This mechanism supports `private` access between nestmates without requiring the compiler to generate synthetic accessor methods as in older mechanisms.

### 8.4. `Record`

`Record` describes the record components of a record class. It stores the name, descriptor, and metadata associated with each component. Record components can also have generic signatures and applicable annotations.

Example:

~~~java
public record Point(int x, int y) {
}
~~~

The class file can contain a `Record` attribute representing the two components `x` and `y`. In addition, the record has compiler-generated members such as accessors, a constructor, and standard methods.

### 8.5. `PermittedSubclasses`

`PermittedSubclasses` stores the list of classes permitted to extend or implement a sealed class or interface.

Example:

~~~java
public sealed interface Shape permits Circle, Rectangle {
}

final class Circle implements Shape {
}

final class Rectangle implements Shape {
}
~~~

This metadata allows the JVM and tooling to validate the permitted subtype set according to sealed type rules.

## 9. Module and `invokedynamic` Attributes

### 9.1. Module Attributes

When compiling `module-info.java`, the module descriptor class file can contain these attributes:

- `Module`: module name, flags, version, `requires`, `exports`, `opens`, `uses`, and `provides`.
- `ModulePackages`: list of packages belonging to the module when needed.
- `ModuleMainClass`: main class designated for the module when present.
- `ModuleTarget`, `ModuleResolution`, `ModuleHashes`: additional metadata used by certain module/toolchain workflows.

These attributes enable the JVM and tools to understand the module graph and packaging metadata. They typically appear in the special `module-info.class` file.

### 9.2. `BootstrapMethods`

`BootstrapMethods` provides bootstrap method information and bootstrap arguments for constant pool entries such as `CONSTANT_InvokeDynamic_info` or corresponding dynamic constants.

Modern Java code can use `invokedynamic` for string concatenation, lambdas, and method references. When a class file contains call sites that require bootstrapping, this attribute stores the data the JVM uses to link the call site according to the specified mechanism.

Not every class or method has `BootstrapMethods`. The attribute only appears when the class file contains content that requires bootstrapping.

## 10. `StackMapTable` and Bytecode Verification

`StackMapTable` is an attribute inside `Code` that stores stack map frames for the bytecode verifier. Frames describe the type state of local variables and the operand stack at specific bytecode offsets.

The JVM uses this information during verification to check that bytecode obeys type-safety rules, such as not using a value with a type incompatible with the frame state.

Points to remember:

- `StackMapTable` is verification metadata, not a runtime snapshot of a Java thread stack.
- The compiler normally generates stack map frames when compiling Java source.
- Bytecode transformation tools must update frames appropriately; if bytecode and stack maps are inconsistent, the JVM may reject loading the class with a verification error.
- `-Xverify:all` can request stricter JVM verification in some environments, though options and behavior should be checked for the specific JDK version.

Distinguish `StackMapTable` from `LineNumberTable` and `LocalVariableTable`: one serves verification, while the other two primarily serve debugging.

## 11. Inspecting Attributes with `javap -v`

`javap` is the tool included with the JDK for inspecting class files. The `-v` or `-verbose` option displays detailed information, including the constant pool and attributes.

Create `AttributeDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Marker {
    String value();
}

@Marker("class")
public class AttributeDemo {
    private static final int LIMIT = 3;

    @Marker("method")
    public static <T> T identity(T value) {
        return value;
    }

    public static String label(String name) {
        return "Hello, " + name + " (" + LIMIT + ")";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println(identity("Java"));
        System.out.println(label("Java"));

        Method method =
                AttributeDemo.class.getDeclaredMethod("identity", Object.class);

        System.out.println(method.getParameters()[0].getName());
        System.out.println(method.getParameters()[0].isNamePresent());
        System.out.println(AttributeDemo.class.getAnnotation(Marker.class).value());
        System.out.println(method.getAnnotation(Marker.class).value());
    }
}
~~~

Create the output directory and compile with debug metadata and parameter metadata:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -g -parameters -d out AttributeDemo.java
~~~

macOS/Linux:

~~~sh
mkdir -p out
javac -g -parameters -d out AttributeDemo.java
~~~

Run:

~~~text
java -cp out AttributeDemo
~~~

Stdout:

~~~text
Java
Hello, Java (3)
value
true
class
method
~~~

`javap` command:

~~~text
javap -v -p -classpath out AttributeDemo
~~~

In the output, look for the corresponding sections:

- `major version: 61` if compiled with JDK 17.
- `ConstantValue` for the `LIMIT` field.
- `Signature` for the generic method `identity`.
- `RuntimeVisibleAnnotations` for the `Marker` annotation.
- `MethodParameters` for the parameter name `value`.
- `Code` for method bytecode.
- `LineNumberTable` and `LocalVariableTable` from compiling with `-g`.
- `StackMapTable` on methods that require frames.

Exact output details can vary by JDK version and code structure. For example, an attribute only appears if the source code or compiler options produce the corresponding metadata.

### 11.1. Comparing Without Debug Metadata and Parameter Metadata

Recompile without debug or parameter metadata:

~~~text
javac -g:none -d out AttributeDemo.java
~~~

Run again:

~~~text
java -cp out AttributeDemo
~~~

The first lines remain the same. However, parameter names may no longer be recognized by reflection:

~~~text
Java
Hello, Java (3)
arg0
false
class
method
~~~

The specific reflection name when `MethodParameters` is missing may be a synthesized form such as `arg0`. Runtime annotations are still readable because `@Retention(RetentionPolicy.RUNTIME)` is independent of `-g` and `-parameters`.

## 12. Unknown Attributes and Custom Attributes

A class file can contain attributes defined by a tool, framework, or bytecode ecosystem outside the standard attribute set. For example, a bytecode manipulation library may record custom metadata for analysis or instrumentation.

A JVM implementation conforming to the JVMS must ignore attributes it does not recognize. This allows class files to carry extra metadata that the JVM does not need to understand to execute standard bytecode.

However, there are practical limitations:

- Standard Java compilers do not provide source-level syntax to declare an arbitrary custom attribute.
- Creating custom attributes typically requires a bytecode library or class file writing tool.
- Tools that read/write class files should preserve unknown attributes if lossless round-tripping is required.
- Just because the JVM ignores an attribute does not mean all other tools will; bytecode analyzers or transformers may need to understand it.
- Do not place information required for correct program execution into a custom attribute that the JVM does not understand.

Attributes have their own structure and are identified by name, but interpreting `info` is only meaningful when a consumer knows the definition of that attribute.

## 13. How Attributes Affect Size, Compatibility, and Tooling

Attributes add metadata to class files, which can increase file size. Debug metadata, annotations, generic signatures, bootstrap methods, and module metadata can all contribute to size.

Practical impacts:

- **Debugging:** `LineNumberTable` and `LocalVariableTable` help debuggers display line numbers and variable names.
- **Reflection:** runtime-visible annotations and `MethodParameters` help frameworks read metadata.
- **Generic tooling:** `Signature` allows reflection and tooling to read generic declarations after bytecode type erasure.
- **Verification:** `StackMapTable` supports bytecode verification.
- **Language features:** `Record`, `PermittedSubclasses`, nest, and module attributes represent modern Java constructs.
- **Bytecode transformation:** instrumentation, shading, obfuscation, or compiler plugins must update or preserve relevant attributes.

Do not strip all attributes just to reduce size. Some metadata is essential for correctness or compatibility, while other metadata only supports debugging or tooling. Understand what each attribute does before stripping it.

## 14. Common Errors When Reading or Processing Attributes

### `javap` cannot find the class

**Cause:** incorrect classpath or incomplete class name.

**Resolution:** verify the output directory and use `javap -classpath out package.ClassName`. For classes in the default package, use the exact class name.

### Missing `LineNumberTable` or `LocalVariableTable`

**Cause:** the compiler did not emit debug metadata or the build tool disabled debug info.

**Resolution:** compile with `javac -g`; check Maven/Gradle/IDE compiler settings. `-g:none` removes these debug metadata attributes.

### Reflection does not see parameter names

**Cause:** the class file lacks `MethodParameters`, usually because `-parameters` was omitted.

**Resolution:** compile with `javac -parameters`; re-check `Parameter.isNamePresent()`. `-g` alone does not replace `-parameters`.

### Reflection cannot read an annotation

**Cause:** the annotation lacks `RetentionPolicy.RUNTIME`, is not placed on the appropriate target, or is being queried on the wrong element.

**Resolution:** check `@Retention`, `@Target`, and use the appropriate reflection API for the class, method, field, or parameter.

### `ClassFormatError` or verification errors

**Cause:** corrupted class file, invalid attribute length, bytecode mismatching stack map frames, or a bytecode transformation tool writing invalid metadata.

**Resolution:** identify the source of the class file, run `javap -v` to inspect its structure, rebuild from source, or update the bytecode tool. If the error appears after instrumentation/obfuscation, check whether the tool preserves and updates required attributes.

### Generic signature differs from descriptor

**Cause:** generic types are erased when generating bytecode; `Signature` stores the additional declaration information.

**Resolution:** compare the descriptor with `Signature` in `javap -v`. This difference is by design in Java generics, not necessarily a class file error.

## 15. Workflow for Inspecting Attributes in a Class File

When investigating a class file, you can follow this order:

1. **Identify the actual class file:** check the classpath/module path to be sure you are reading the intended version of the class.
2. **Inspect the header:** use `javap -v` to check the major/minor version and constant pool.
3. **Inspect declarations:** check access flags, descriptors, fields, and methods.
4. **Inspect class-level attributes:** look for `SourceFile`, annotations, module, nest, record, or sealed metadata.
5. **Inspect field/method attributes:** check `ConstantValue`, `Signature`, `Exceptions`, `MethodParameters`, and annotations.
6. **Inspect `Code`:** examine bytecode, the exception table, and nested attributes.
7. **Cross-check compiler options:** verify `-g`, `-parameters`, `--release`, and build configuration.
8. **If bytecode transformation is involved:** compare the class file before and after, and confirm the tool preserves required attributes.
9. **Verify at runtime:** run the application or a reflection test to confirm metadata is visible to the JVM/tooling as expected.

Useful commands:

~~~text
javap -v -p -classpath out AttributeDemo
javap -c -p -classpath out AttributeDemo
javap -l -p -classpath out AttributeDemo
javap -s -p -classpath out AttributeDemo
~~~

- `-v`: verbose class file information, including attributes.
- `-c`: disassemble bytecode.
- `-l`: display line/local variable tables if present.
- `-s`: display internal type signatures/descriptors.
- `-p`: show private members as well.

## 16. Summary Checklist

- [ ] Attributes are structured metadata/data in a class file, not synonymous with source annotations.
- [ ] Each attribute has `attribute_name_index`, `attribute_length`, and `info`.
- [ ] The attribute name points to a `CONSTANT_Utf8_info` entry in the constant pool.
- [ ] Attributes can appear at class, field, method, `Code`, or record component levels as specified.
- [ ] `Code` contains bytecode, an exception table, and nested attributes.
- [ ] `LineNumberTable` and `LocalVariableTable` support debugging.
- [ ] `MethodParameters` relates to reflection parameter names; use `-parameters`.
- [ ] `Signature` preserves generic metadata after type erasure.
- [ ] `ConstantValue` applies to eligible constant fields.
- [ ] `Exceptions` describes declared exceptions, not a JVM checked-exception enforcement mechanism.
- [ ] `StackMapTable` supports bytecode verification.
- [ ] Runtime-visible annotations are stored in the appropriate annotation attributes.
- [ ] `Record`, `PermittedSubclasses`, nest, and module attributes represent modern Java constructs.
- [ ] Use `javap -v` to inspect attributes in actual class files.
- [ ] When transforming bytecode, preserve or update required metadata.

Attributes form the flexible metadata layer of Java class files. Understanding their general binary structure and grouping attributes by purpose will help you read `javap` output, explain reflection and debugger behavior, analyze bytecode, and diagnose issues when compilers or build tools produce unexpected class files.