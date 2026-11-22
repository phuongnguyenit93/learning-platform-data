# Testing the `@Target` and `@Retention` Matrix in Java

## 1. Why Is Matrix Testing Needed?

When building custom annotations, two meta-annotations determine independent characteristics:

- **`@Target`** answers: **at which Java locations** can the annotation be placed? The compiler checks this right at compile time.
- **`@Retention`** answers: **up to which stage** is the annotation information retained? It affects source code, data in `.class` files, and readability via Reflection.

An annotation in a valid location can still "disappear" when running the program if its retention is not `RUNTIME`. Conversely, an annotation using `RUNTIME` still **cannot compile** when attached to the wrong `@Target`.

For example:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Traced {
}
~~~

`@Traced` is allowed on method declarations and can be read via Reflection after compilation. But:

~~~java
// WRONG code, only illustrating a negative test:
// @Traced
// class WrongPlace {}
~~~

will be rejected by the compiler. **`RUNTIME` does not expand the valid locations of `METHOD`.**

For reliable testing, you should not just write one snippet that runs successfully. You need a **positive/negative matrix** by `ElementType`, a **matrix of the three retention policies**, and three verification methods:

1. **Compile-time:** use `javac` to verify that valid samples compile successfully and misplaced samples are rejected.
2. **Class-file level:** use `javap -v` to verify that metadata is actually stored or discarded.
3. **Runtime:** use Reflection to verify that the required annotations are read with the right API.

This is how to isolate **target declaration** errors, **retention** errors, and **wrong-API metadata reading** errors.

## 2. The `ElementType` Matrix in Java 17

Java SE 17 has **12 `ElementType` constants**. Each constant has typical usage locations and different tests.

| `ElementType` | Valid test location (positive test) | Invalid location to test (negative test) |
| --- | --- | --- |
| `TYPE` | `@A class C {}`, interface, enum, record | A type argument element such as `List<@A String>` if only `TYPE` is supported |
| `FIELD` | `@A String field;` | `@A void method() {}` |
| `METHOD` | `@A void execute() {}` | `@A class C {}` |
| `PARAMETER` | `void run(@A String value) {}` | `@A String field;` |
| `CONSTRUCTOR` | `@A C() {}` | `@A void method() {}` |
| `LOCAL_VARIABLE` | `@A int n = 1;` inside a method | Field or method declaration |
| `ANNOTATION_TYPE` | `@A @interface Flag {}` | A regular class |
| `PACKAGE` | Annotation placed before `package ...;` in `package-info.java` | Class declaration |
| `TYPE_PARAMETER` | `class Box<@A T> {}` | Type argument `List<@A String>` if only `TYPE_PARAMETER` is supported |
| `TYPE_USE` | `List<@A String>`, field type, cast, array component... | **Declaration-only** contexts outside the scope of `TYPE_USE`, for example a package annotation |
| `MODULE` | Before `module ... {}` in `module-info.java` | Class declaration |
| `RECORD_COMPONENT` | `record Item(@A String id) {}` | Regular field if only `RECORD_COMPONENT` is supported |

**This is a test planning table**, not source code in a single shared file: `@A` is a placeholder for the corresponding annotation type, and each negative test is compiled **separately**, not mixed with valid examples.

### 2.1. Two Important Exceptions Regarding `TYPE_USE`

`TYPE` means a **type declaration** such as a class/interface, not everywhere the name `String` appears. `TYPE_USE` means **a type use**, for example a type acting as a generic type argument.

However, according to the JLS, `@Target(TYPE_USE)` also allows some **class/interface declaration** and **type parameter declaration** locations. Therefore, you must not write a negative test like "`@A class C {}` with `@Target(TYPE_USE)` will definitely fail"; that assumption is wrong.

To test `TYPE_USE` reliably, use a type **inside a generic**:

~~~java
import java.util.List;

class Example {
    List<@A String> names;
}
~~~

If `@A` has `@Target(TYPE_USE)`, the location above is valid. If it **only** has `@Target(FIELD)`, that type argument location is invalid.

### 2.2. `TYPE_PARAMETER` Differs from `PARAMETER`

`PARAMETER` applies to formal parameters of a method/constructor, while `TYPE_PARAMETER` applies to generic type variables such as `T`. A `T` in `class Box<T>` is **not** a parameter of a method call.

Use two different tests:

~~~java
class GenericBox<@A T> {
}

class Service {
    void send(@A String message) {
    }
}
~~~

Each fragment needs to define `@A` with the corresponding target. Do not use a `@Target(PARAMETER)` annotation to annotate `T` and then treat the compile error as a Java generics error.

### 2.3. Record Component and Propagation

`RECORD_COMPONENT` has been a separate target since Java 16. A record component is related to the generated field, accessor, and constructor parameter, but an annotation placed on the component **is not present by default on all related declarations**.

When testing a record, you should check directly via:

~~~java
recordClass.getRecordComponents()[0]
           .isAnnotationPresent(YourAnnotation.class);
~~~

This is a fragment using a declared `Class<?> recordClass` and annotation type `YourAnnotation`, **not a standalone program**. If you need to check propagation to the field/accessor/parameter, you must set `@Target` accordingly and test the JLS rules separately.

## 3. The `@Retention` Matrix: Three Observation Stages

`java.lang.annotation.RetentionPolicy` defines three policies:

| Policy | In source/annotation processing | In the class file after `javac` | Standard runtime Reflection |
| --- | --- | --- | --- |
| `SOURCE` | Can be processed by a processor at compile time | Not retained at the usage site | Not visible |
| `CLASS` | Can be processed by a processor | Retained as metadata not intended for runtime reflection | Not visible |
| `RUNTIME` | Can be processed by a processor | Retained as metadata readable at runtime | Visible with the right API |

An annotation type that **does not declare `@Retention`** has a default retention of **`CLASS`**, not `RUNTIME`.

For example:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeMark {}

@Target(ElementType.TYPE)
@interface DefaultMark {} // Default retention: CLASS.
~~~

All of the above definitions are valid. If these four annotations are placed together on one class, `javac` must accept them regarding **target**, but they have **different retentions**.

### 3.1. Observing in `.class` with `javap -v`

For an annotation attached directly to a class and Java 17 `javac`:

- `SOURCE`: there is no information about that annotation usage in the class file.
- `CLASS`: usually located under the `RuntimeInvisibleAnnotations` attribute.
- `RUNTIME`: usually located under the `RuntimeVisibleAnnotations` attribute.

`DefaultMark` also belongs to the `CLASS` group because it has no `@Retention`.

The attribute names above are **names in the class-file format**, not a Java API enabling runtime Reflection to read `CLASS`. A specialized bytecode tool can still read `RuntimeInvisibleAnnotations` from the file, but `Class.getAnnotation()` is not used to read this group.

### 3.2. Reading with Runtime Reflection: Using the Right Path

At runtime:

~~~java
type.getAnnotation(RuntimeMark.class);
type.isAnnotationPresent(RuntimeMark.class);
~~~

can see the RUNTIME annotation on the type, but:

~~~java
type.getAnnotation(SourceMark.class); // null
type.getAnnotation(ClassMark.class);  // null
~~~

cannot see SOURCE or CLASS. The two lines are a fragment with the variable `Class<?> type`.

**Not having `RUNTIME` does not mean the annotation was never seen by the compiler.** Annotation processors usually run on source before the compiler drops SOURCE retention, so these are two independent testing steps.

## 4. Number of Test Cases: Not Just Mechanically Multiplying 12 × 3

There are **12 target types × 3 retention policies = 36 conceptual pairs**, but you do not necessarily have to write 36 different test files for a small module.

A reasonable design based on **test partitioning**:

1. One positive test for each target kind, compiled with `javac`.
2. One negative test placing the same annotation into a **context that is definitely disallowed**.
3. For a target supporting easily verifiable Reflection such as `TYPE`, run all of `SOURCE`, `CLASS`, `RUNTIME`, and **default retention**.
4. Add runtime tests for `FIELD`, `METHOD`, `PARAMETER`, `CONSTRUCTOR`, `TYPE_USE`, `TYPE_PARAMETER`, `RECORD_COMPONENT`.
5. Use class-file-level tests for `CLASS` and especially for metadata that **lacks a general runtime Reflection API**, such as annotations on a local variable declaration.
6. For `PACKAGE` and `MODULE`, use separate structural files rather than forcing them into a single Java file with `main`.

The goal is not to create the largest number of tests, but to **cover semantic boundaries that are easy to get wrong**.

## 5. Complete Java 17 Program Testing Multiple Targets and Retentions

Create a single file named **`AnnotationMatrixDemo.java`**. The program runs standalone and requires no libraries outside the JDK.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeMark {}

@Target(ElementType.TYPE)
@interface DefaultMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.CONSTRUCTOR)
@interface ConstructorMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeUseMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface TypeParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.LOCAL_VARIABLE)
@interface LocalMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface RecordComponentMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface AnnotationTypeMark {}

@AnnotationTypeMark
@interface MetaAnnotated {}

@SourceMark
@ClassMark
@RuntimeMark
@DefaultMark
class MatrixSample<@TypeParameterMark T> {
    @FieldMark
    private @TypeUseMark String name = "ok";

    private List<@TypeUseMark String> tags = List.of("a");

    @ConstructorMark
    MatrixSample() {}

    @MethodMark
    void execute(@ParameterMark String input) {
        @LocalMark int attempts = 1;
        if (attempts < 0) {
            throw new AssertionError(input);
        }
    }
}

record MatrixRecord(@RecordComponentMark String id) {}

public class AnnotationMatrixDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> type = MatrixSample.class;
        Field name = type.getDeclaredField("name");
        Field tags = type.getDeclaredField("tags");
        Method execute = type.getDeclaredMethod("execute", String.class);

        AnnotatedParameterizedType tagType =
                (AnnotatedParameterizedType) tags.getAnnotatedType();

        System.out.println("SOURCE visible: "
                + type.isAnnotationPresent(SourceMark.class));
        System.out.println("CLASS visible: "
                + type.isAnnotationPresent(ClassMark.class));
        System.out.println("RUNTIME visible: "
                + type.isAnnotationPresent(RuntimeMark.class));
        System.out.println("DEFAULT visible: "
                + type.isAnnotationPresent(DefaultMark.class));

        System.out.println("FIELD declaration: "
                + name.isAnnotationPresent(FieldMark.class));
        System.out.println("FIELD type use: "
                + name.getAnnotatedType()
                      .isAnnotationPresent(TypeUseMark.class));
        System.out.println("GENERIC type argument: "
                + tagType.getAnnotatedActualTypeArguments()[0]
                         .isAnnotationPresent(TypeUseMark.class));

        System.out.println("METHOD declaration: "
                + execute.isAnnotationPresent(MethodMark.class));
        System.out.println("PARAMETER declaration: "
                + execute.getParameters()[0]
                         .isAnnotationPresent(ParameterMark.class));
        System.out.println("CONSTRUCTOR declaration: "
                + type.getDeclaredConstructor()
                      .isAnnotationPresent(ConstructorMark.class));
        System.out.println("TYPE_PARAMETER declaration: "
                + type.getTypeParameters()[0]
                      .isAnnotationPresent(TypeParameterMark.class));
        System.out.println("RECORD_COMPONENT declaration: "
                + MatrixRecord.class.getRecordComponents()[0]
                      .isAnnotationPresent(RecordComponentMark.class));
        System.out.println("ANNOTATION_TYPE declaration: "
                + MetaAnnotated.class
                      .isAnnotationPresent(AnnotationTypeMark.class));
    }
}
~~~

Run from the directory containing the file, using JDK 17+:

~~~bash
javac -encoding UTF-8 AnnotationMatrixDemo.java
java AnnotationMatrixDemo
~~~

**Exact stdout:**

~~~text
SOURCE visible: false
CLASS visible: false
RUNTIME visible: true
DEFAULT visible: false
FIELD declaration: true
FIELD type use: true
GENERIC type argument: true
METHOD declaration: true
PARAMETER declaration: true
CONSTRUCTOR declaration: true
TYPE_PARAMETER declaration: true
RECORD_COMPONENT declaration: true
ANNOTATION_TYPE declaration: true
~~~

### 5.1. Why Do the First Lines Have false/true Like That?

`MatrixSample` carries the four annotations `SourceMark`, `ClassMark`, `RuntimeMark`, `DefaultMark`, all of which have target `TYPE`, so they **all pass the compile-time target check**.

However, Reflection at runtime only sees `RuntimeMark`. `SourceMark` was stripped because of `SOURCE`; `ClassMark` is retained in the class file but not for Reflection; `DefaultMark` has default retention `CLASS`, so it also does not show up via `Class.isAnnotationPresent`.

This result **does not say** `SourceMark` "does not exist"; it is still an annotation type that can be recognized by the compiler and annotation processors.

### 5.2. Distinguishing Field Declaration and Field Type

`MatrixSample.name` has two annotations with two different targets:

~~~java
@FieldMark
private @TypeUseMark String name = "ok";
~~~

`FieldMark` belongs to the **field declaration**, read via `Field.isAnnotationPresent(FieldMark.class)`.

`TypeUseMark` belongs to the **field's `String` type**, read via `Field.getAnnotatedType().isAnnotationPresent(TypeUseMark.class)`.

If a test only calls `Field.getAnnotation(TypeUseMark.class)`, you are testing the **wrong API** and may mistakenly conclude that RUNTIME retention does not work. A negative result when reading the wrong location **is not proof** that the compiler lost the annotation.

### 5.3. Testing Generic Type Arguments

`List<@TypeUseMark String>` places the annotation on the **type argument `String`**, not the `tags` field declaration. That is why the example uses `AnnotatedParameterizedType` and gets `getAnnotatedActualTypeArguments()[0]`.

If an annotation only has `TYPE_PARAMETER`, it fits the `<T>` declaration of `MatrixSample`, but is **invalid** at `List<@A String>` when `String` is a type argument.

### 5.4. Testing Records and Annotation Types

`MatrixRecord` uses `RECORD_COMPONENT`, read with `Class.getRecordComponents()`. Do not only inspect the record's synthetic/implicit field or accessor and assume that is a direct test of the record component.

`@AnnotationTypeMark` is on the `@interface MetaAnnotated` declaration, matching target `ANNOTATION_TYPE`. It does not automatically mark classes carrying `@MetaAnnotated`.

### 5.5. Why Does `LOCAL_VARIABLE` Have No Runtime Line?

`@LocalMark` is valid on the local variable declaration `attempts`, so the program **compiles successfully**. However, standard Reflection does not have `LocalVariable.getAnnotation()` to inspect annotations on every local variable in bytecode.

Even when `@LocalMark` uses `RUNTIME`, you should not write an assertion saying "runtime reflection must see LocalMark on the local variable". **Valid target** and **API-accessible at runtime** are not synonymous. A type-use annotation on a type in a local variable is a different mechanism, with separate storage rules in the class file.

## 6. Testing Retention with `javap -v`

After compiling the program in section 5, run:

~~~bash
javap -v MatrixSample
~~~

Look for the attributes generated for annotations attached directly to **class MatrixSample**:

- `RuntimeVisibleAnnotations`: includes `RuntimeMark`.
- `RuntimeInvisibleAnnotations`: includes `ClassMark` and `DefaultMark`.
- `SourceMark`: **not retained** as an annotation on the class in `MatrixSample.class`.

Elements such as `TypeUseMark` can also appear in `RuntimeVisibleTypeAnnotations`, because that is **type-use metadata**, not a declaration annotation on the class. The class-file format distinguishes multiple attributes; when checking, you must look for the right **annotated element** and the right **metadata location**.

### Why Do `javap` and Reflection Need Separate Testing?

- `javap -v` is a **class-file inspection tool**, helping detect annotations retained in bytecode even when Reflection does not read them.
- Reflection only exposes annotations retained until runtime through the **appropriate API**.
- A `CLASS` annotation appearing in `RuntimeInvisibleAnnotations` is the **correct** result, not a compiler error just because Reflection returns `null`.
- For `SOURCE`, Reflection returning `null` is correct; the absence of metadata at the usage site in `.class` is also correct.

You should not combine testing `SOURCE` with runtime-only reflection and expect a positive result.

## 7. Negative Tests: Intentionally Creating Wrong-Target Code

Negative tests must be **compiled separately** and expected to make `javac` return a non-zero exit code. Do not mix them into `AnnotationMatrixDemo.java`, because doing so will prevent the positive tests from running as well.

After compiling the file in section 5, create each of the files below in the same directory. The annotation types in the demo are all package-private in the **unnamed package**, so test snippets in the same directory/package can reference them.

### 7.1. Wrong `METHOD` Target on a Class

File **`WrongClass.java`**:

~~~java
@MethodMark
class WrongClass {
}
~~~

Run:

~~~bash
javac -encoding UTF-8 -cp . WrongClass.java
~~~

**Expected:** compilation **fails** because `MethodMark` only supports `ElementType.METHOD`, not a class declaration.

### 7.2. Wrong `FIELD` Target on a Type Argument

File **`WrongTypeArgument.java`**:

~~~java
import java.util.List;

class WrongTypeArgument {
    List<@FieldMark String> values;
}
~~~

Run:

~~~bash
javac -encoding UTF-8 -cp . WrongTypeArgument.java
~~~

**Expected:** fails, because `@FieldMark` belongs to a field declaration, not the `String` type in a type argument.

### 7.3. Wrong `PARAMETER` on a Type Parameter

File **`WrongTypeParameter.java`**:

~~~java
class WrongTypeParameter<@ParameterMark T> {
}
~~~

Run:

~~~bash
javac -encoding UTF-8 -cp . WrongTypeParameter.java
~~~

**Expected:** fails because `T` is a **type parameter**, not a formal parameter. `@TypeParameterMark T` is the valid test.

### 7.4. Wrong `METHOD` on a Constructor

File **`WrongConstructor.java`**:

~~~java
class WrongConstructor {
    @MethodMark
    WrongConstructor() {
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 -cp . WrongConstructor.java
~~~

**Expected:** fails because a constructor declaration requires `ElementType.CONSTRUCTOR`, not `METHOD`.

### How to Write Automated Tests

You can use JUnit, Gradle compile-testing, or the JDK `JavaCompiler` API to check the **compilation exit code** and diagnostic category. For a simple test, what is required is not matching the **entire error message** verbatim (since wording can vary across JDK releases and locales), but rather:

- Positive sample: **exit code = 0**.
- Negative sample: **non-zero exit code**.
- The error comes from an invalid target, **not** from missing annotation definitions, a wrong classpath, a wrong Java source level, or an unrelated typo.

If using a shell script, you should compile the negative snippets **file by file** and assert each separately, so that one failure does not mask other test cases.

## 8. Testing `PACKAGE` and `MODULE` Requires Special File Structures

These two targets should not be stuffed into a single class with `main`, because Java syntax requires different declaration locations.

### `ElementType.PACKAGE`

A project can have two separate files in `src/demo/api/`:

**`PackageTag.java`**:

~~~java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackageTag {
}
~~~

**`package-info.java`**:

~~~java
@PackageTag
package demo.api;
~~~

This is a **multi-file project fragment**, not part of `AnnotationMatrixDemo.java`. Within the same package, `@PackageTag` is used without needing an import. Attaching `@PackageTag` to a normal class will cause a target error.

Compile from the directory containing `src`:

~~~bash
javac -encoding UTF-8 -d out src/demo/api/PackageTag.java src/demo/api/package-info.java
~~~

When retention is `RUNTIME`, you can use `Package.getPackage` in an appropriate context or `SomeClass.class.getPackage().isAnnotationPresent(PackageTag.class)` once there is a class in that package. To avoid depending on a package with no loaded classes yet, the test should include an additional public class in the package and then retrieve its `Class.getPackage()`.

### `ElementType.MODULE`

An annotation on a module must be placed at the `module` declaration in **`module-info.java`** of the Java Platform Module System.

Illustrative example, **not a standalone single-file program**:

~~~java
@demo.api.ModuleTag
module demo.application {
}
~~~

`demo.api.ModuleTag` must have `@Target(ElementType.MODULE)` and be validly present in the module graph; the project must have a suitable module layout and compiler options. The goal of the test case is to verify that the **module declaration** is annotated with the right target and to check the metadata according to retention via the appropriate module/class-file API. Using `@ModuleTag` directly on a class is a negative test.

For packages/modules, you should design a **fixture project** instead of trying to put all examples into the main file. Module testing may require `--module-source-path`, `--module-path`, or multi-module compile commands that differ from a standard classpath test.

## 9. Testing Annotation Processing with `SOURCE` Retention

The `SOURCE/CLASS/RUNTIME` matrix is incomplete if you only check `javap` and Reflection. Many annotations are designed **solely for annotation processors**.

Example marker:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateBuilder {
}
~~~

A processor can retrieve the `TypeElement` instances annotated with `@GenerateBuilder` during compilation via:

~~~java
roundEnv.getElementsAnnotatedWith(GenerateBuilder.class)
~~~

This is a **fragment inside a processor**, not a standalone runnable snippet. A good integration test:

1. Compiles and activates a real processor (via `-processor` or service).
2. Compiles a class carrying `@GenerateBuilder`, asserting that the processor emits a valid diagnostic or generates the expected file.
3. Verifies that the generated file exists and compiles successfully.
4. Verifies that runtime Reflection **does not see `@GenerateBuilder`** on the original class, matching `SOURCE` retention.

If the compiler does not load the processor, the test checking "whether the SOURCE annotation is processed" has a broken setup. **SOURCE retention is not the reason a processor fails to run**; the cause may be the processorpath, registration, source level, or annotation type support.

## 10. Test Matrix by Layer and Case

| Case | Input | Compile | Class file / Reflection |
| --- | --- | --- | --- |
| T1 | `@Target(METHOD)` on method | Succeeds | If RUNTIME: `Method.isAnnotationPresent` true |
| T2 | `@Target(METHOD)` on class | Fails | Reflection is not run |
| T3 | `@Target(FIELD)` on type argument | Fails | Reflection is not run |
| T4 | `@Target(TYPE_USE)` on `List<@A String>` | Succeeds | Read via `AnnotatedParameterizedType` when RUNTIME |
| T5 | `@Target(TYPE_PARAMETER)` on `T` declaration | Succeeds | Read via `TypeVariable` when RUNTIME |
| T6 | `@Target(RECORD_COMPONENT)` on record header | Succeeds | Read via `RecordComponent` when RUNTIME |
| R1 | `SOURCE` on class | Succeeds | No annotation use in class file; Reflection false |
| R2 | `CLASS` on class | Succeeds | RuntimeInvisibleAnnotations; Reflection false |
| R3 | `RUNTIME` on class | Succeeds | RuntimeVisibleAnnotations; Reflection true |
| R4 | No `@Retention` declared | Succeeds | Default CLASS; Reflection false |
| L1 | `@Target(LOCAL_VARIABLE)` on local | Succeeds | No general Reflection API for local declarations |
| P1 | `@Target(PACKAGE)` on `package-info.java` | Succeeds | Check package metadata according to retention |
| M1 | `@Target(MODULE)` on `module-info.java` | Succeeds | Check module metadata according to retention |

For complex targets and `TYPE_USE`, you should add `RUNTIME` cases on type annotations in bytecode. Do not infer that every `@Retention(RUNTIME)` must be read through **the same** `getAnnotation()` call on `Class`: the metadata location determines the appropriate Reflection API.

## 11. Common Mistakes When Writing Test Suites

**Mistake 1 — only testing valid annotations without testing invalid targets.** The compiler may accept all code in the test suite without confirming that the annotation is restricted as designed. Use negative compile tests.

**Mistake 2 — putting negative code together with runnable demos.** An intentional negative snippet will make the entire project fail to compile. Separate files/fixtures or use a test harness.

**Mistake 3 — seeing that `CLASS` cannot be read via Reflection and reporting a retention bug.** That is the expected behavior. Verify using `javap -v` or a class-file reader.

**Mistake 4 — assuming omitting `@Retention` defaults to RUNTIME.** Java defaults to CLASS.

**Mistake 5 — confusing `TYPE` with `TYPE_USE`.** `List<@A String>` is a type argument; `TYPE` alone is not enough.

**Mistake 6 — treating `TYPE_PARAMETER` and `PARAMETER` as the same.** A generic `T` differs from a method/constructor parameter.

**Mistake 7 — testing `@Target(TYPE_USE)` with a negative test on a class declaration.** There are declaration positions permitted by `TYPE_USE`; you need to pick a context that is truly out of scope.

**Mistake 8 — using `Field.getAnnotation` to conclude that a type-use annotation was lost.** You must read it via `Field.getAnnotatedType()`.

**Mistake 9 — using `RUNTIME` on a local variable and expecting to find it with regular Reflection.** Runtime retention does not create new Reflection APIs for local declarations.

**Mistake 10 — equating a record component annotation with an annotation on the accessor/field.** Test via `RecordComponent`; if you want to check propagation, test it independently.

**Mistake 11 — matching compiler error messages verbatim only.** Messages/locales may differ; check the exit code, error code if supported by the framework, and the right context.

**Mistake 12 — a negative test fails due to setup, yet is still counted as PASS.** You must verify that the actual error comes from the **target**; a wrong classpath or missing source does not prove the annotation restricts targets properly.

**Mistake 13 — skipping processor discovery when testing SOURCE.** An annotation processor only runs when the compiler activates it; the test setup must specify `-processor` or registration.

**Mistake 14 — a test relying on Reflection execution order or the list order of `getDeclaredMethods()`.** Query by name or a clear sort key instead; do not rely on iteration order.

## 12. Test Suite Design Checklist

A solid matrix test suite should include:

1. **Target inventory:** list the `ElementType` values supported by the annotation type and the locations intentionally unsupported.
2. **Positive compile tests:** at least one valid example for each relevant target.
3. **Negative compile tests:** at least one example that is invalid specifically due to the target.
4. **Retention test:** SOURCE, CLASS, RUNTIME, and the case where `@Retention` is not declared.
5. **Class-file inspection:** distinguish `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations`, and `RuntimeVisibleTypeAnnotations` when needed.
6. **Reflection path:** use `Class`, `Field`, `Method`, `Parameter`, `AnnotatedType`, `TypeVariable`, `RecordComponent` in the right context.
7. **Special contexts:** package-info, module-info, record component, generic type argument, and local declaration.
8. **Processor setup:** if SOURCE is consumed by an annotation processor, verify that the processor ran and produced results.
9. **Java version:** clearly specify JDK 17+; module, record, and type-use have different version histories.
10. **Negative-test isolation:** do not let an intentionally invalid file break the positive suite.
11. **Stable assertions:** compare booleans, exit status, and metadata types; avoid relying on exact compiler messages.
12. **CI matrix:** when needed, repeat across the JDKs and compilers/build tools that the project actually supports.

## 13. Self-Check Exercises

**Question 1.** Do `@Target(METHOD)` and `@Retention(RUNTIME)` allow attaching an annotation to a class?  
**Answer:** No. A wrong target causes a compile error even when retention is RUNTIME.

**Question 2.** With `@Retention(CLASS)` on a class, `javap -v` can see the metadata, yet `Class.isAnnotationPresent` returns false. Is this a bug?  
**Answer:** No. CLASS metadata is not exposed by runtime Reflection.

**Question 3.** If `@Retention` is omitted, what is the default?  
**Answer:** `RetentionPolicy.CLASS`.

**Question 4.** Is `List<@A String>` a test for `TYPE`, `TYPE_USE`, or `TYPE_PARAMETER`?  
**Answer:** `TYPE_USE`, because `String` is a **type argument**.

**Question 5.** What location does `class C<@A T>` test?  
**Answer:** The **type parameter** declaration `T`; the `TYPE_PARAMETER` target is appropriate, and `TYPE_USE` also includes these positions according to the JLS.

**Question 6.** Why can you not rely on Reflection to test all `LOCAL_VARIABLE` cases?  
**Answer:** Standard Reflection does not provide a general API to query annotations on local variable declarations.

**Question 7.** `getAnnotation` on `Field` returns false, whereas `getAnnotatedType` returns true for the same annotation type name. Can this happen?  
**Answer:** Yes, if the annotation is in the field's **type-use context**, not on the field declaration.

**Question 8.** When a negative compilation fails because the annotation type is missing from the classpath, can that be considered a PASS for the target test?  
**Answer:** No. You must verify that the error is specifically caused by the annotation being placed at an invalid location.

**Practical exercise:** Compile and run `AnnotationMatrixDemo.java`, then run `javap -v MatrixSample` to inspect the RuntimeVisible and RuntimeInvisible metadata. Create the four negative files in section 7 separately, and verify that every file fails to compile due to an invalid target. Finally, add a `@Target(TYPE_USE)` annotation on an array element type and design your own `AnnotatedArrayType` Reflection test; distinguish between an annotation on the array component and an annotation on the array type itself based on syntactic position.

## 14. Official Java SE 17 Documentation

- [JLS §9.6.4.1 — `@Target`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): rules for applying annotations.
- [JLS §9.6.4.2 — `@Retention`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2): retention rules.
- [JLS §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): declaration/type contexts.
- [Java SE 17 — `ElementType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html): all target enum constants.
- [Java SE 17 — `RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): SOURCE, CLASS, RUNTIME.
- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): Reflection contract for annotations.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): tool for viewing class-file metadata.

**Conclusion:** Testing `@Target` and `@Retention` requires three perspectives: **compiler, class file, and runtime Reflection**. Prove both valid and wrong-target cases; distinguish metadata that is not retained from metadata present in `.class` files yet hidden at runtime; and always read an annotation with the API matching **where it is attached**.
