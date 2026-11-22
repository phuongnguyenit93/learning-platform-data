# Using `javap -v` to Inspect Annotations in Class Files

## 1. Why Inspect Annotations in `.class` Files?

Annotations in Java source code can be processed at compile time, stored in bytecode, or remain present for the program to read via reflection. When an application or framework cannot find an annotation as expected, the first question is usually: **did the compiler store that metadata in the right class file and in the right location?**

The `javap` tool included with the JDK can disassemble the structure of a `.class` file. The **`-v`** option (equivalent to `-verbose`) displays detailed data, including *attributes* containing annotations, the constant pool, signatures, methods, and some bytecode instructions. For annotations, the key traces include:

- `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations`: annotations on declarations such as classes, fields, and methods.
- `RuntimeVisibleParameterAnnotations` and `RuntimeInvisibleParameterAnnotations`: annotations on method/constructor **parameter declarations**.
- `RuntimeVisibleTypeAnnotations` and `RuntimeInvisibleTypeAnnotations`: annotations at **type-use locations** such as return types, parameter types, casts, generic arguments, and field types.
- `AnnotationDefault`: the default value of an element declared inside an **annotation interface**.

`javap` is not an annotation processor and does not execute the application: it **reads the compiled class file**. Therefore, it is a useful way to inspect metadata independently of runtime reflection/framework logic.

### What `javap -v` Can Answer

1. Was the annotation actually stored in the class file by the compiler?
2. Is it on a **class**, **field**, **method**, **parameter**, or **type-use**?
3. Does the annotation have `RUNTIME` or `CLASS` retention, judging by the generated attribute group?
4. For repeatable annotations, which container annotation does the compiler use?
5. Which corresponding bytecode *target* does an annotation on a cast or return type have?
6. Where is an annotation element with a default value stored?

**Limitation:** `javap` decodes the metadata of **each specific class file**. It does not apply the superclass annotation lookup rules of `Class.getAnnotations()`, does not run frameworks, and does not prove that an annotation will cause a runtime behavior.

## 2. The Three `@Retention` Policies and Traces in Class Files

Java defines three retention policies:

| Retention | Primary Meaning | Expectation When Inspecting the Class File |
|---|---|---|
| `RetentionPolicy.SOURCE` | Annotation is only for the source/compile phase; the compiler does not retain it in the class file | No corresponding annotation in the attributes of the generated `.class` file |
| `RetentionPolicy.CLASS` | Annotation is written to the class file, though not required to be visible via reflection at runtime | Typically appears in `RuntimeInvisibleAnnotations` or `RuntimeInvisibleTypeAnnotations`, depending on location |
| `RetentionPolicy.RUNTIME` | Annotation is written to the class file and can be accessed via reflection APIs that support that location | Typically appears in `RuntimeVisibleAnnotations` or the appropriate `RuntimeVisible...` group |

If **`@Retention` is not declared**, the default is **`CLASS`**; do not assume the default is `RUNTIME`.

The words “Visible” and “Invisible” are attribute names according to the **JVM class-file format**, not `public`/`private` access levels:

- **`RuntimeVisible...`** indicates the metadata group defined as visible at runtime through the appropriate supporting mechanism.
- **`RuntimeInvisible...`** is still data present in the class file; `javap` or bytecode analysis tools can read it, but standard Java reflection does not directly expose these annotations.
- `SOURCE` annotations have been discarded from the class file; running `javap` after compilation cannot reconstruct all annotations that were once in the source.

**An important distinction:** even if an annotation on a *cast expression* has `RUNTIME` retention and is listed under `RuntimeVisibleTypeAnnotations`, standard Java reflection has no regular API to enumerate every cast inside a method body. Therefore, **“RuntimeVisible” does not mean every location can be read using `Class.getAnnotation()`**.

## 3. Complete Java 17+ Example: Compiling to Inspect with `javap`

Create a practice directory and save the following code into the exact file **`Main.java`**. There is only one `public` top-level class named `Main`; the annotation types and `Demo` are declared package-private in the same file for easy experimentation.

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface RuntimeTag {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface ClassTag {
    String value();
}

@Retention(RetentionPolicy.SOURCE)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface SourceTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Notes.class)
@interface NoteTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Notes {
    NoteTag[] value();
}

@RuntimeTag("class")
@ClassTag("class")
@SourceTag("class")
@NoteTag("first")
@NoteTag("second")
class Demo {

    @RuntimeTag("field")
    @ClassTag("field")
    private String field;

    @RuntimeTag("method")
    public @TypeTag("return") String greet(
            @RuntimeTag("parameter")
            @TypeTag("parameter-type") String input) {

        Object raw = input;
        String result = (@TypeTag("cast") String) raw;
        return result;
    }
}

public class Main {
    public static void main(String[] args) throws Exception {
        Demo demo = new Demo();

        System.out.println(demo.greet("Java"));
        System.out.println("runtime="
                + Demo.class.isAnnotationPresent(RuntimeTag.class));
        System.out.println("class="
                + Demo.class.isAnnotationPresent(ClassTag.class));
        System.out.println("source="
                + Demo.class.isAnnotationPresent(SourceTag.class));
        System.out.println("type="
                + Demo.class.getMethod("greet", String.class)
                        .getAnnotatedReturnType()
                        .isAnnotationPresent(TypeTag.class));
        System.out.println("repeat="
                + Demo.class.getAnnotationsByType(NoteTag.class).length);
    }
}
~~~

The annotations used are intentionally different:

- `RuntimeTag`: `RUNTIME` retention on a class, private field, method, and parameter declaration.
- `ClassTag`: `CLASS` retention on a class and field.
- `SourceTag`: `SOURCE` retention on a class.
- `TypeTag`: `RUNTIME` retention but `@Target(TYPE_USE)`, applied to the return type, parameter type, and cast.
- `NoteTag`: a `@Repeatable` annotation, used twice on `Demo`; `Notes` is the container.

### 3.1. Compile and Run Commands

In the directory containing `Main.java`, use JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -parameters Main.java
java Main
~~~

Output from `java Main`:

~~~text
Java
runtime=true
class=false
source=false
type=true
repeat=2
~~~

This confirms:

1. The `greet` method still runs normally and returns `"Java"`.
2. `RuntimeTag` can be read on `Demo` via reflection.
3. Although `ClassTag` is stored in the class file, `Demo.class.isAnnotationPresent(ClassTag.class)` returns `false`.
4. `SourceTag` does not appear at runtime.
5. `TypeTag` on the **return type** is read by `getAnnotatedReturnType()`; calling `getAnnotation` directly on `Method` is not a substitute for reading all TYPE_USE annotations.
6. The two `NoteTag` annotations are retrieved via `getAnnotationsByType`, even though the class file may store them through a container.

### 3.2. Files Generated After Compilation

Compiling the source above creates `Main.class`, `Demo.class`, and class files for the annotation types `RuntimeTag`, `ClassTag`, `SourceTag`, `TypeTag`, `NoteTag`, and `Notes`.

**To inspect annotations applied to `Demo`, inspect `Demo.class`, not just `Main.class`.** Annotations do not automatically become metadata on `Main` just because both classes are in `Main.java`.

Key command:

~~~bash
javap -v -p Demo
~~~

Or specify the classpath location explicitly:

~~~bash
javap -classpath . -v -p Demo
~~~

- **`-v`** prints detailed attributes, the constant pool, bytecode, and metadata.
- **`-p`** (equivalent to `-private`) shows private members in the output; for example, `field` is declared `private`.
- `Demo` is the binary class name in the current package, whereas `javap -v -p Main` disassembles a different class.
- `-parameters` in the `javac` command stores parameter name metadata (`MethodParameters`), helping verify the name `input`; **it is not a requirement for parameter annotations to be stored**.

The example above uses `--release 17` to instruct the compiler to compile against Java 17 APIs/semantics even if the environment has a newer JDK. If you are using JDK 17 directly, you can still use `javac -encoding UTF-8 -parameters Main.java`.

## 4. Reading `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations`

Near the end of the **`Demo.class`** disassembly, you will see the section of annotations applied to the **class**. An output snippet **abbreviated for explanation** (not a full copy from `javap`):

~~~text
RuntimeVisibleAnnotations:
  ... RuntimeTag(
        value="class"
      )
  ... Notes(
        value=[@NoteTag(value="first"), @NoteTag(value="second")]
      )
RuntimeInvisibleAnnotations:
  ... ClassTag(
        value="class"
      )
~~~

In actual output, names may be printed in different notation, accompanied by **constant-pool indices** like `#14`, positions, encoding types like `s`, or different indented lines. **Do not rely on `#...` numbers or exact ordering:** those are compiler-generated indices and can change when modifying the source.

How to interpret this:

- **`RuntimeVisibleAnnotations`** on `Demo` contains `RuntimeTag("class")` and the **`Notes`** container of the two `NoteTag` annotations.
- **`RuntimeInvisibleAnnotations`** on `Demo` contains `ClassTag("class")`.
- `SourceTag("class")` is absent because `SOURCE` retention instructs the compiler to exclude it from the class file.

### 4.1. Do Not Confuse the Container with Individual Repeated Annotations

Two lines in the source:

~~~java
@NoteTag("first")
@NoteTag("second")
class Demo {}
~~~

are represented by the compiler via the `Notes` container annotation according to `@Repeatable` rules. When viewing `javap -v`, you may find something like `Notes(value=[@NoteTag(...), @NoteTag(...)])`, **not necessarily two sibling `NoteTag` annotations directly in the attribute on the class**.

This explains why:

~~~java
Demo.class.getAnnotationsByType(NoteTag.class).length // 2
~~~

whereas the singular API `getAnnotation(NoteTag.class)` does not automatically unwrap the container to return multiple `NoteTag` annotations. If you need repeated annotations, choose `getAnnotationsByType(...)`.

## 5. Distinguishing Annotations on Classes, Fields, and Methods

In `javap -v -p Demo`, **indentation context and attribute placement** determine which declaration an annotation belongs to.

A class file may be displayed with the following layout:

~~~text
class Demo
  ...

  private java.lang.String field;
    ...
    RuntimeVisibleAnnotations:
      ... RuntimeTag(value="field")
    RuntimeInvisibleAnnotations:
      ... ClassTag(value="field")

  public java.lang.String greet(java.lang.String);
    ...
    RuntimeVisibleAnnotations:
      ... RuntimeTag(value="method")

  ...
RuntimeVisibleAnnotations:
  ... RuntimeTag(value="class")
  ... Notes(...)
~~~

This is an **illustrative diagram** that omits `descriptor`, `flags`, `Code`, `LineNumberTable`, constant-pool indices, and encoding details. Actual entries in `javap` are usually much longer.

**Do not draw conclusions based on matching attribute names:** `RuntimeVisibleAnnotations` can appear **multiple times** because each class, field, and method has its own place for attributes. To determine which declaration an annotation belongs to, look at the **member signature immediately above** or the position at the end of the class information section.

Annotations on private fields will be hard to observe if viewing an abbreviated format; use `-p` to show all members. The `-p` option does not modify the class file and does not turn private annotations into public metadata.

## 6. Parameter Declarations Differ from Parameter Types

In the source, `Demo`'s method has:

~~~java
public @TypeTag("return") String greet(
        @RuntimeTag("parameter")
        @TypeTag("parameter-type") String input) {
    // ...
}
~~~

Here, the two annotations before `String input` have **different application targets**:

- `@RuntimeTag("parameter")` has `@Target(PARAMETER)`, so it is an annotation on the **parameter declaration**.
- `@TypeTag("parameter-type")` has `@Target(TYPE_USE)`, so it is an annotation on the **String type used for the parameter**.

When disassembled, they typically reside in **two different attribute groups**:

~~~text
RuntimeVisibleParameterAnnotations:
  parameter 0:
    ... RuntimeTag(value="parameter")

RuntimeVisibleTypeAnnotations:
  ... METHOD_FORMAL_PARAMETER, param_index=0
      TypeTag(value="parameter-type")
~~~

`parameter 0` is the first parameter in 0-based index order. Distinguish the parameter position in `RuntimeVisibleParameterAnnotations` from the `METHOD_FORMAL_PARAMETER` target code of a **type annotation**.

For example, `@TypeTag("return")` on the return type appears under:

~~~text
RuntimeVisibleTypeAnnotations:
  ... METHOD_RETURN
      TypeTag(value="return")
~~~

**An `Annotation[]` obtained from `Method.getParameterAnnotations()`** is not completely equivalent to **`AnnotatedType[]` from `Method.getAnnotatedParameterTypes()`**. The two APIs read two different kinds of metadata.

### Is `MethodParameters` an Annotation?

No. The `MethodParameters:` line (if present) describes **parameter names and flags**, such as the name `input` saved by `javac -parameters`. It does not contain declaration/type-use annotations.

Do not conclude that parameter annotations are lost just because the class file lacks `MethodParameters`. These are two independent structures.

## 7. Using `RuntimeVisibleTypeAnnotations` to Inspect Casts and Types Inside Method Bodies

Annotations with `@Target(TYPE_USE)` can appear in contexts such as:

- Method return type: `METHOD_RETURN`.
- Method parameter type: `METHOD_FORMAL_PARAMETER`.
- Field type: `FIELD`.
- Superclass or superinterface: `CLASS_EXTENDS`.
- Cast expression: `CAST`.
- Object creation expression: `NEW`.
- Types in type tests, generic arguments, array dimensions, and other type-use contexts that have corresponding `target_type` codes according to the JVM Specification.

Given the source:

~~~java
Object raw = input;
String result = (@TypeTag("cast") String) raw;
~~~

The actual disassembly has an entry similar to:

~~~text
Code:
  ...
  RuntimeVisibleTypeAnnotations:
    ... CAST, offset=..., type_index=0
        TypeTag(value="cast")
~~~

That is the annotation on the **String type of the cast**, stored along with the metadata of `Code`. The `offset` number indicates the position in bytecode; `type_index` or `type_path` describes the annotated type or type branch when needed. They **are not source line numbers**.

Meanwhile, annotations on the **return type** and **parameter types** are usually displayed in the `RuntimeVisibleTypeAnnotations` attribute attached to the **method**.

**Important distinction:** both the annotation group on the cast and on the return type can be named `RuntimeVisibleTypeAnnotations`, yet they are attached to **different bytecode structures** and have different `target_type` values. Read the attribute's location and target code; do not just search for the annotation name.

### 7.1. What Can Reflection Read?

For example:

~~~java
Demo.class.getMethod("greet", String.class)
        .getAnnotatedReturnType()
        .getAnnotation(TypeTag.class);
~~~

returns `@TypeTag("return")` because this is an annotation on the return type, which has a corresponding `AnnotatedType` API.

However, standard Java reflection **does not have** a call such as `getAllCastAnnotationsInMethod()` to list every cast in bytecode. To inspect a `cast` annotation, use `javap -v` or a bytecode library that supports reading type-annotation attributes.

The same annotation type, the same `RUNTIME` retention, yet **different query surfaces**. Do not use reflection results on a method declaration to deny metadata that has been stored in `Code`.

## 8. Inspecting Annotations with `default`: `AnnotationDefault`

`AnnotationDefault` is not an attribute proving that a class is *using* an annotation. It is an attribute of the **method declaring an element inside an annotation interface**, containing the declared default value.

Standalone source example:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Retry {
    int times() default 3;
    String mode() default "safe";
}
~~~

If you compile `Retry.java` (or a file containing a valid declaration) and then run:

~~~bash
javap -v -p Retry
~~~

you will see each element with a corresponding default in `AnnotationDefault`, for example:

~~~text
public abstract int times();
  ...
  AnnotationDefault:
    default_value: I#...
      3
~~~

The `#...` number varies according to the constant pool. The `mode()` element also has an `AnnotationDefault` attribute with the value `"safe"`.

If a usage site writes `@Retry` without passing `times`, that does not mean the compiler necessarily stores `times=3` at every usage site: **the default value is looked up from the annotation type**, without needing to repeat the default value on each annotated class.

## 9. Inspecting Nested Annotations and Element Values

When disassembling with `javap -v`, you may see representations such as:

- `value="class"`: string value.
- `value=3`: integer.
- `SomeEnum.VALUE`: enum constant.
- `java.lang.String.class` or a constant pool type descriptor: class literal.
- `@Nested(...)`: nested annotation.
- `value=[..., ...]`: array of values, for example the container of repeatable annotations.

`javap` often also displays parts like `#14(#15=s#34)` to describe constant-pool references and element-value types. This is class-file structure, not Java source syntax to be copied verbatim into `@Annotation(...)`.

If the value displayed in `javap` differs from what you expected in the source, check:

1. Have you compiled the **right source**?
2. Is `javap` reading the **right output directory/JAR and the right classpath**?
3. Is that a value passed directly at the usage site or a **default** in the annotation type?
4. Does the annotation use `@Repeatable` and a container so the displayed structure differs from the source?
5. Have constant-pool indices changed due to a different compiler build, while the logical value remains the same?

Do not assume every formatting detail is a stable API across compiler versions. **Attribute names and class-file format semantics** are what need to be checked against; indices, offsets, and formatting may change.

## 10. Using `javap` with the Right Classpath, Package, Class File, and JAR

In real projects, class files may reside in `target/classes`, `build/classes/java/main`, or a JAR. In that case, running `javap Demo` in the source directory may report that the class could not be found or read the wrong class with the same name.

### For Classes in a Package

If the source has:

~~~java
package com.example.annotation;

class Demo {}
~~~

and has been compiled to the `out` directory, use the full binary name:

~~~bash
javap -classpath out -v -p com.example.annotation.Demo
~~~

**Do not pass `Demo.java` to inspect annotations in a class file.** `javap` works with class files, while `javac` processes source files.

### For Classes Inside a JAR

If `app.jar` contains `com/example/annotation/Demo.class`:

~~~bash
javap -classpath app.jar -v -p com.example.annotation.Demo
~~~

### With a Class File Path

Some `javap` invocations accept passing a direct path to the class file:

~~~bash
javap -v -p out/com/example/annotation/Demo.class
~~~

However, using **`-classpath` plus the binary class name** is usually easier to control when there are packages, classes with duplicate names, or multiple output roots.

### Inner/Nested Classes and the `$` Character

The compiler assigns binary names in the form `Outer$Nested`. In shells that perform `$` expansion, **quote** or escape names containing `$`, for example in Bash:

~~~bash
javap -classpath out -v -p 'com.example.Outer$Nested'
~~~

Do not rely on the source file name matching the nested class name.

## 11. Diagnostic Workflow When Reflection Cannot Find an Annotation

When `clazz.getAnnotation(MyAnnotation.class)` returns `null`, use the short workflow below:

1. **Verify the actual class.** Check the package, output folder, and JAR version. The command `javap -classpath <output> -v -p <binary-name>` must point to the right class.
2. **Search for the annotation type name** in the output. If it only appears in the **constant pool** without an annotation attribute at the required location, do not rush to conclude that the annotation was applied. The constant pool may contain a reference that appears for another purpose.
3. **Identify the retention.** If `SOURCE`, do not expect to see a class-file annotation. If `CLASS`, it will be in the `RuntimeInvisible...` group; if `RUNTIME`, look for the corresponding `RuntimeVisible...` group.
4. **Check the right target.** A class annotation differs from a field annotation; a parameter declaration differs from a parameter **type**; a return type differs from a method declaration.
5. **Check repeated annotations.** If the source has multiple `@NoteTag` annotations, look at the `Notes` container and try `getAnnotationsByType(NoteTag.class)`.
6. **Check inheritance rules.** `@Inherited` can cause reflection on a subclass to see a superclass annotation **even though the subclass does not contain that annotation in its class file**. In that case, also inspect the superclass's class file.
7. **Distinguish Java reflection from frameworks.** A framework may scan the method/interface/type hierarchy according to its own rules, whereas `javap` only reports the data actually present in the class file.
8. **Clean rebuild when needed.** If the source recently changed retention/target/values, delete old build outputs using a build process permitted by the project and recompile; avoid inspecting outdated class files.
9. **Cross-check with two tests.** Use `javap -v` to know what bytecode stores; use reflection tests to know what the runtime API sees.

`javap` is very powerful for explaining **why** metadata is present or absent, but it does not replace testing annotation processor logic, static checkers, dependency injection, or framework validation.

## 12. Common Misconceptions and Mistakes

### 12.1. Running `javap -c` and Not Seeing Annotations

`-c` focuses on method bytecode. If the goal is class-file metadata, use **`-v`**. You can combine `-c -v -p` when you want both bytecode analysis and detailed attributes.

### 12.2. Not Seeing a `SOURCE` Annotation and Thinking the Compiler Ignored It

`SOURCE` retention is designed **not to exist in the class file**. An annotation processor or the compiler can still use it during compilation. `javap` not showing it is **semantically correct**, not proof that the source lacks the annotation.

### 12.3. `RuntimeInvisible` Means a Private Annotation

Incorrect. “Invisible” relates to **runtime reflection visibility**, not the `private` modifier. `javap -p` shows private members; it does not turn `CLASS` retention into `RUNTIME`.

### 12.4. Searching Only `RuntimeVisibleAnnotations` When the Annotation Is `TYPE_USE`

TYPE_USE annotations usually reside in `RuntimeVisibleTypeAnnotations`, potentially under `Code` when on a cast, or under the method when on a return/parameter type. Look for the right attribute group and `target_type`.

### 12.5. Seeing the Container and Thinking Repeated Annotations Were Lost

Two `@NoteTag` annotations may be represented via the `@Notes` container. Look at the `value=[@NoteTag(...), ...]` elements and use `getAnnotationsByType()` when checking at runtime.

### 12.6. Checking `getAnnotations` on a Subclass While `javap` on the Subclass Has No Annotation

For annotation types with `@Inherited`, Java reflection can traverse the **superclass chain**. When `javap` reads only the subclass file, it **does not synthesize superclass metadata**. Inspect the parent class file.

### 12.7. Confusing an Annotation Name in the Constant Pool with an Applied Annotation

The `Constant pool` contains type name strings, UTF-8 constants, and referenced descriptors. The appearance of an annotation name here is **not sufficient** to prove that a specific declaration has the annotation; you must check the actual attribute at the required member/class/type location.

### 12.8. Reading the Wrong File Due to Classpath

If a project has multiple output folders or dependency JARs, `javap` may analyze a different version of the class than the running program. You need to control the classpath and binary name; you can use class loader/resource diagnostics if you suspect the runtime classpath differs from the build artifact.

### 12.9. Relying on a Specific `#NN` or Offset

The constant pool and bytecode offsets are detailed data dependent on the compiler and code. Adding a field or modifying a statement can change `#NN` numbers, `offset` values, and `LineNumberTable` even though the annotation meaning has not changed. Do not write tests that compare the entire `javap -v` output as a stable interface.

## 13. Practical Checklist

- [ ] Did you compile successfully with the right JDK/source compatibility?
- [ ] Did you run `javap -v -p` with the **right class file**, classpath, and package?
- [ ] Did you identify whether the annotation is on a class, field, method, parameter declaration, or type-use?
- [ ] Did you distinguish between **`RuntimeVisible`**, **`RuntimeInvisible`**, and **`SOURCE`** retention?
- [ ] Did you inspect `RuntimeVisibleParameterAnnotations` or `RuntimeVisibleTypeAnnotations` if the annotation is at a parameter/type-use?
- [ ] If using `@Repeatable`, did you inspect the container annotation and try `getAnnotationsByType`?
- [ ] If it is an annotation default element value, did you inspect `AnnotationDefault` on the **annotation type**?
- [ ] Did you note the difference between metadata in the class file and metadata that reflection/frameworks actually read?

## 14. Official References

- [JDK 17 `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `-v`, `-p`, `-classpath` options and how to specify classes.
- [Java SE 17 JLS `9.6.4.2 — `@Retention`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2): retention policies and the `CLASS` default.
- [Java SE 17 JVM Spec `4.7.16–`4.7.22](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.16): format of annotation-related attributes and `AnnotationDefault`.
- [Java SE 17 API — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): runtime annotation lookup rules, including `@Repeatable` and `@Inherited`.
- [Java SE 17 API — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): API for reading annotations on types at supported locations.

**Remember:** compile and run **`javap -v -p <ClassName>`** to verify the **metadata actually stored in `.class`**. `RUNTIME` typically goes into `RuntimeVisible...`; `CLASS` into `RuntimeInvisible...`; `SOURCE` is not stored. To read the output correctly, observe the **exact attribute, member, and target type**, rather than merely searching for the annotation name string in the output. Also use reflection tests when you need to confirm how the application sees that metadata.
