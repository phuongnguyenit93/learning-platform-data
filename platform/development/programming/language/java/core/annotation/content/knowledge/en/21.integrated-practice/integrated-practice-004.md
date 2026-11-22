# Integrated Practice: Comparing Results When Changing @Target, @Retention, and @Inherited in Java

## 1. Practice Objectives

Three Java meta-annotations often appear together in an annotation type definition:

- `@Target`: **which syntactic locations** the annotation is allowed to be placed on. The compiler checks this when compiling code that uses the annotation.
- `@Retention`: up to which stage information about **an annotation usage** is retained: source only, class file, or inspectable via reflection at runtime.
- `@Inherited`: when an annotation type is applied to a **class**, Java reflection can see the annotation from the **superclass** if the subclass has not declared an annotation of the same type. It does **not** automatically apply in the same way to interfaces or overridden methods.

Three independent yet interacting questions:

1. **Is it allowed to be attached here?** → `@Target`.
2. **Is there still data to observe after compilation?** → `@Retention`.
3. **When reading on a subclass, is the superclass's annotation included?** → `@Inherited` (and only when the data is available for that way of reading).

The goal is to **change one factor at a time under controlled conditions**, predict the outcome, and then verify against `javac`, `java`, and `javap`. You should not change multiple factors simultaneously on the first attempt, because compile-time errors, missing runtime metadata, and inheritance rules are different causes.

## 2. Overview Comparison Table

| Meta-annotation | Primary effect | When is it observed? | If changed |
| --- | --- | --- | --- |
| `@Target(TYPE)` | Only allows the annotation on matching type declarations | `javac` checks placement | Placing it on a method/field not in the target → compilation error |
| `@Target({TYPE, FIELD, METHOD})` | Allows it on type, field, and method | `javac` | The same annotation can be used at multiple metadata levels |
| No `@Target` declared | Can be used on the declaration contexts that Java allows by default; does not implicitly allow all type-use contexts | `javac` | Broader syntactic scope than a restricted target |
| `@Retention(SOURCE)` | Usage is only needed at source/compile time | Annotation processor/compiler | Usage is not stored in the target class file; reflection does not see it |
| `@Retention(CLASS)` | Retains metadata in the class file | `javap -v`, bytecode reader | Standard reflection does not see it |
| `@Retention(RUNTIME)` | Retains metadata and supports runtime reflection | `Class/Field/Method.getAnnotation` | Can be read when querying the right element and the annotation is present |
| No `@Retention` declared | Defaults to `CLASS` | Bytecode / runtime | Do not assume runtime reflection can read it |
| `@Inherited` | Allows looking up a class annotation from the superclass when conditions are met | Reflection on `Class` | Subclass can read the superclass's annotation |
| Without `@Inherited` | Does not apply a special inheritance mechanism | Reflection on `Class` | `Child.class.getAnnotation(T.class)` does not receive T that only exists on the parent |

**Remember:** `@Target` does **not** determine metadata lifetime. `@Retention` does **not** allow placing an annotation on an invalid target location. `@Inherited` does **not** make metadata automatically propagate to all members or interfaces. They are three dimensions of an annotation contract.

## 3. Experiment Design: Change Only One Variable

For controlled testing, use three fixture groups:

- **Group A – Target:** place the same annotation on a class, field, method, and constructor; change the `ElementType` list and observe which cases `javac` accepts/rejects.
- **Group B – Retention:** attach three annotations with the same `@Target` but with `SOURCE`, `CLASS`, and `RUNTIME` respectively; inspect the class file with `javap` and compare with reflection results.
- **Group C – Inherited:** attach a runtime annotation to a superclass, create a subclass without declaring the annotation, a subclass with its own annotation, an annotated interface, and an overridden method; compare `getAnnotation` with `getDeclaredAnnotation`.

In the standalone program section below, a single Java 17 compilation will cover groups B and C while also providing valid target examples. Code snippets that are **intentionally invalid** for testing Target are kept separate; do not put uncompilable code into the main program.

## 4. @Target: Changing Annotation Placement Can Change Compilation Results

Suppose we define:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface TypeLabel {}
~~~

`@Target(ElementType.TYPE)` means the annotation is used on matching **type declarations**, such as a class or interface. With the illustrative code:

~~~java
@TypeLabel
class Catalog {}

@TypeLabel
interface Marker {}
~~~

Both placements above are valid. However, attempting to attach it to a field:

~~~java
class Catalog {
    @TypeLabel
    private int count;
}
~~~

is an **intentionally uncompilable example**: annotation type `TypeLabel` does not apply to a field. Attaching it to a method or constructor is also invalid if the target is only `TYPE`.

To allow multiple locations, modify the definition:

~~~java
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Label {}
~~~

Then the same `@Label` can be placed on a class, field, method, and constructor following valid Java syntax.

### 4.1. When Changing Target, What Stays the Same?

If `@Label` still has `RUNTIME` retention, expanding `@Target` from `TYPE` to `{TYPE, FIELD, METHOD}` does not automatically change the annotation's retention, does not copy the annotation on the class to fields/methods, and does not make the JVM automatically process the metadata. It **only** allows writing those new valid annotation placements.

Conversely, narrowing `@Target` causes **new source code** that attaches the annotation at a removed location to fail compilation. Old class files are not automatically rewritten; if the annotation has already been published as a library, changing Target must be evaluated as a contract change for all usage sites.

### 4.2. TYPE, TYPE_USE, TYPE_PARAMETER, and PARAMETER Are Not the Same

Three easily confused pairs:

| ElementType | Annotated location | Example |
| --- | --- | --- |
| `TYPE` | Matching class/interface/enum/annotation type/record declaration | `@Label class Catalog {}` |
| `FIELD` | Field declaration | `@Label int size;` |
| `METHOD` | Method declaration | `@Label void run() {}` |
| `CONSTRUCTOR` | Constructor declaration | `@Label Catalog() {}` |
| `PARAMETER` | Method/constructor parameter declaration | `void run(@Label String arg) {}` |
| `TYPE_PARAMETER` | Generic type parameter declaration | `class Box<@Label T> {}` |
| `TYPE_USE` | A type use location | `List<@Label String> names;` |
| `PACKAGE` | Package declaration | `package-info.java` |
| `MODULE` | JPMS module declaration | `module-info.java` |

The examples in the table are **illustrative syntax**; to compile them, `Label` must be defined with the corresponding target and the necessary types/imports must be provided.

An annotation placed on a **field declaration** is not synonymous with an annotation attached to a **generic type argument**. `@Target(TYPE_USE)` is a different concept from `@Target(TYPE)`. Reflection also has different APIs: `Field.getAnnotation(...)` reads declaration annotations, whereas `Field.getAnnotatedType()` and the `AnnotatedType` APIs read appropriate type-use metadata.

### 4.3. What Does Missing @Target Mean?

When `@Target` is not declared, Java allows the annotation on the default **declaration** kinds specified by the language. This does not mean the annotation is automatically valid everywhere in Java syntax or automatically accepts every `TYPE_USE`. If the metadata has a clear scope, declaring the target explicitly helps the compiler prevent mistakes early.

## 5. @Retention: SOURCE, CLASS, and RUNTIME Leave Different Traces

With the same target:

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
~~~

Each annotation **can be attached** to a class. However, the compiler processes the **annotation usage** according to retention:

- **SOURCE:** an annotation processor or compiler can see it during source compilation; in the class file of the annotated class, there is no metadata for that annotation usage.
- **CLASS:** the information is still written into the class file of the annotated element; for declaration annotations, it is typically located in `RuntimeInvisibleAnnotations`. Standard Java reflection does **not** provide it.
- **RUNTIME:** the information remains in the class file and can be read by standard reflection on the right `AnnotatedElement`; for declaration annotations, it is typically located in `RuntimeVisibleAnnotations`.

The word “invisible” does not mean a bytecode reader cannot see it. `javap -v` can display both `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations`.

**Subtle note:** the compiler can generate a class file for the **annotation type definition** `SourceMark`. `SOURCE` refers to retaining **usages of @SourceMark on target elements**, not completely deleting the class file of the annotation type itself from the compilation output.

### 5.1. If Retention Is Changed from RUNTIME to CLASS

Suppose `@State("ready")` is read via:

~~~java
State state = Catalog.class.getAnnotation(State.class);
~~~

This snippet is illustrative, assuming `State` already exists. If the source of `Catalog` is **recompiled** when `State` has switched to `Retention(CLASS)`, runtime reflection no longer sees the annotation as before. If only the annotation definition in a JAR is replaced while keeping the **old class file** that was previously compiled with `RUNTIME` retention, you cannot assume the old file is automatically rewritten. When testing a retention change, you must check the **actual bytecode being executed** and recompile the usages that need to be compared.

### 5.2. @Retention and Processing Time

`Retention(SOURCE)` can certainly serve an **annotation processor** at compile time. `Retention(CLASS)` can serve **bytecode analysis**. `Retention(RUNTIME)` serves reflection or frameworks operating at runtime. No policy automatically instructs the JVM to invoke a method merely because an annotation exists.

If the business requirement is a runtime annotation that controls validation, routing, or authorization, there must be a **component that consumes it and applies the rules**. Changing `Retention` without changing the reader tool can cause the system to miss metadata or misinterpret configuration.

## 6. @Inherited: Not Ordinary Java Member Inheritance

Declaration:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface FamilyLabel {
    String value();
}
~~~

With:

~~~java
@FamilyLabel("parent")
class Base {}

class Child extends Base {}
~~~

then `Child.class.getAnnotation(FamilyLabel.class)` can return the annotation from `Base`, because:

1. `FamilyLabel` has `@Inherited`.
2. The annotation is attached to a **class declaration** (`Base`).
3. `Child` is a **subclass** in the superclass chain, not merely a class implementing an interface.
4. The metadata has `RUNTIME` retention, so reflection can read it.

Meanwhile:

~~~java
Child.class.getDeclaredAnnotation(FamilyLabel.class)
~~~

returns `null` if `Child` itself does not declare the annotation. The word `Declared` means **only declarations on that element itself are considered**, without automatically checking the superclass.

### 6.1. What If the Subclass Declares It Itself?

If:

~~~java
@FamilyLabel("child")
class Child extends Base {}
~~~

`Child.class.getAnnotation(FamilyLabel.class).value()` returns `"child"`. The annotation directly on the child determines the result for that type, instead of forcing the parent's value to be read.

This does not mean Java automatically **merges** annotation values across all superclasses. For repeatable annotations, the `getAnnotationsByType` APIs have specialized rules. If the business logic needs to accumulate metadata across multiple levels, you must explicitly write logic to traverse superclasses and handle combining them.

### 6.2. Interfaces Do Not Propagate @Inherited to Implementing Classes

Example:

~~~java
@FamilyLabel("interface")
interface Contract {}

class ContractImpl implements Contract {}
~~~

`ContractImpl.class.getAnnotation(FamilyLabel.class)` does **not** automatically see `@FamilyLabel("interface")` on `Contract`. `@Inherited` is designed for looking up annotations **on a class via its superclass**, not for traversing all interfaces that a class implements.

A framework can actively look up metadata on interfaces, but that is the framework's own rule, not the default result of `Class.getAnnotation`.

### 6.3. Overridden Methods Do Not Automatically Receive the Parent Method's Annotation

Even when the annotation type is marked `@Inherited` and targets `METHOD`:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

class Base {
    @MethodMark
    public void process() {}
}

class Child extends Base {
    @Override
    public void process() {}
}
~~~

`Child.class.getDeclaredMethod("process").getAnnotation(MethodMark.class)` returns `null`. The reason is that `@Inherited` does not establish metadata inheritance for **methods**. Java method overriding and the reflection mechanism of annotation declarations are two different issues.

Similarly, fields and constructors do not automatically copy annotations from declarations in the parent class. Constructors are not even **inherited** like methods. If you use `Child.class.getMethod("process")` when the child **does not override**, you can obtain the `Method` object of the method inherited from the parent; reading the annotation in that case belongs to the method **on the parent**, not the `@Inherited` mechanism of an annotation on the child method.

### 6.4. Does @Inherited Have Any Effect If Retention Is Not RUNTIME?

`@Inherited` only specifies the **class annotation lookup** rule in the appropriate language/reflection model. If the annotation type has `SOURCE` or `CLASS` retention, standard reflection APIs at runtime do not see the annotation usage on the class, so `@Inherited` cannot make metadata already absent from reflection “reappear”. The two conditions that need to work together when you want to read inherited annotations at runtime are **`@Inherited` and `@Retention(RUNTIME)`**.

## 7. Standalone Java 17+ Program: Verifying All Core Conclusions

Create a single file named **`AnnotationMetaComparisonDemo.java`** containing the following annotation types and test classes. The file uses the default package to make it easy to run experiments from the terminal; real-world projects normally place them in a named package.

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@interface RuntimeMark { String value(); }

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface FamilyLabel { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalLabel { String value(); }

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

@SourceMark
@ClassMark
@RuntimeMark("base")
@FamilyLabel("parent")
@LocalLabel("direct-only")
class BaseService {
    @SourceMark @ClassMark @RuntimeMark("field")
    private int count;

    @SourceMark @ClassMark @RuntimeMark("method") @MethodMark
    public void process() {}
}

class ChildService extends BaseService {
    @Override public void process() {}
}

@FamilyLabel("interface")
interface ServiceContract {}
class InterfaceImpl implements ServiceContract {}

@FamilyLabel("child")
class OverridingChild extends BaseService {}

public class AnnotationMetaComparisonDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<BaseService> base = BaseService.class;
        Class<ChildService> child = ChildService.class;

        System.out.println("source-visible="
                + base.isAnnotationPresent(SourceMark.class));
        System.out.println("class-visible="
                + base.isAnnotationPresent(ClassMark.class));
        System.out.println("runtime-base="
                + base.getAnnotation(RuntimeMark.class).value());
        System.out.println("runtime-field="
                + base.getDeclaredField("count")
                      .getAnnotation(RuntimeMark.class).value());
        System.out.println("runtime-method="
                + base.getDeclaredMethod("process")
                      .getAnnotation(RuntimeMark.class).value());

        System.out.println("child-family="
                + child.getAnnotation(FamilyLabel.class).value());
        System.out.println("child-local-label="
                + child.isAnnotationPresent(LocalLabel.class));
        System.out.println("child-declared-lookup="
                + (child.getDeclaredAnnotation(FamilyLabel.class) != null));
        System.out.println("child-runtime="
                + (child.getAnnotation(RuntimeMark.class) != null));
        System.out.println("interface-inherited="
                + (InterfaceImpl.class.getAnnotation(FamilyLabel.class) != null));

        Method override = child.getDeclaredMethod("process");
        System.out.println("method-inherited="
                + (override.getAnnotation(MethodMark.class) != null));
        System.out.println("child-own-family="
                + OverridingChild.class.getAnnotation(FamilyLabel.class).value());
    }
}
~~~

### 7.1. Compile and Run

From the directory containing the file above, using **JDK 17 or later**:

~~~bash
javac --release 17 AnnotationMetaComparisonDemo.java
java AnnotationMetaComparisonDemo
~~~

**Exact stdout:**

~~~text
source-visible=false
class-visible=false
runtime-base=base
runtime-field=field
runtime-method=method
child-family=parent
child-local-label=false
child-declared-lookup=false
child-runtime=false
interface-inherited=false
method-inherited=false
child-own-family=child
~~~

The program was **compiled with `javac --release 17` and executed** on a Java 17–compatible JDK; the results above match the program's stdout.

### 7.2. Analysis from Start to Finish

- `source-visible=false`: `@SourceMark` is for compile time only and is not detected at runtime by `Class.isAnnotationPresent`.
- `class-visible=false`: `@ClassMark` can still reside in the class file of `BaseService` but is not exposed by standard reflection.
- `runtime-base=base`: `@RuntimeMark("base")` is marked `RUNTIME` and placed directly on the class.
- `runtime-field=field`: another annotation usage is attached to the declaration of field `count`. You must retrieve the corresponding `Field`.
- `runtime-method=method`: similarly, you must retrieve the corresponding `Method` declared on the parent.
- `child-family=parent`: `@FamilyLabel` has `@Inherited`, so `ChildService` sees the annotation of `BaseService`.
- `child-local-label=false`: `@LocalLabel` also has `RUNTIME` retention, but **does not have @Inherited**, so the subclass does not see it.
- `child-declared-lookup=false`: `ChildService` does not declare `FamilyLabel` directly. `getDeclaredAnnotation` does not automatically search the superclass.
- `child-runtime=false`: `@RuntimeMark` is not marked with `@Inherited`; merely having `RUNTIME` retention does not mean it appears on the subclass.
- `interface-inherited=false`: an annotation on an interface is not received by an implementing class via `@Inherited`.
- `method-inherited=false`: `@MethodMark` has `@Inherited` but is placed on a method, which does not create an annotation inheritance mechanism when the method is overridden.
- `child-own-family=child`: the subclass has `@FamilyLabel("child")` directly, so the result does not take `"parent"` from the superclass.

**An important testing detail:** the lines printing `false` are observed results under specific conditions. Do not infer from them that the compiler cannot see SOURCE annotations, that CLASS annotations have disappeared from bytecode, or that interfaces are not supported by the JVM.

## 8. Using javap to Confirm That CLASS Retention Still Exists

After compiling the main program, run:

~~~bash
javap -v BaseService
~~~

Use `javap -v` to inspect the class file of the **annotated class**, not just the class file of the annotation type itself.

In the verbose output, you will see information similar to:

~~~text
RuntimeVisibleAnnotations:
  RuntimeMark(...)
  FamilyLabel(...)
  LocalLabel(...)

RuntimeInvisibleAnnotations:
  ClassMark
~~~

This is a **simplified presentation format**, not the verbatim stdout of `javap`. The actual output includes constant pool indices, descriptors, and other metadata.

At the class declaration level:

- `@RuntimeMark`, `@FamilyLabel`, `@LocalLabel` appear in `RuntimeVisibleAnnotations`.
- `@ClassMark` is located in `RuntimeInvisibleAnnotations`.
- `@SourceMark` has **no** annotation entry on the `BaseService` class because its retention is `SOURCE`.

In `BaseService.class`, the annotated fields/methods also have their own corresponding attribute sections; class metadata should not be conflated with method/field metadata when reading `javap` output. The two kinds `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations` are **class-file format** details, whereas `RetentionPolicy` is how the policy is declared in source code.

## 9. Practice: Changing One Meta-Annotation at a Time and Predicting the Outcome

Perform these one at a time; each time **edit the source and recompile**, without making multiple changes simultaneously. The predictions below assume the relevant lines of code remain identical to the main program except for the stated change.

### Experiment A1 — Narrowing the Target of RuntimeMark

Change:

~~~java
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
~~~

on `RuntimeMark` to:

~~~java
@Target(ElementType.TYPE)
~~~

**Prediction:** `javac` reports errors at `@RuntimeMark("field")` and `@RuntimeMark("method")`, because this annotation is no longer applicable to fields and methods. The error occurs **before runtime**; there is no stdout from a newly compiled program if only the failing source is used.

**Fix:** either widen the target back, or remove the two usages on the field and method. If you remove them while keeping code that calls `getAnnotation(RuntimeMark.class).value()` on the field/method, you must update the code to check for `null` to avoid a `NullPointerException`.

### Experiment A2 — Expanding Target Instead of Changing Retention

Keep `@Retention(RUNTIME)` on `RuntimeMark`, add `ElementType.CONSTRUCTOR` to `@Target`, and then add an explicit constructor annotated with `@RuntimeMark("ctor")` to `BaseService`.

**Prediction:** the compiler allows it. When retrieving the matching `Constructor<?>` and reading `getAnnotation(RuntimeMark.class)`, the value `"ctor"` is observed. The results on the class, field, and method **do not automatically change** due to expanding the target. The annotation on the constructor is also not automatically propagated to the class or methods.

### Experiment B1 — Changing RUNTIME to CLASS

Change only `@Retention(RetentionPolicy.RUNTIME)` on `RuntimeMark` to:

~~~java
@Retention(RetentionPolicy.CLASS)
~~~

Keep the `@RuntimeMark` annotations on the class, field, and method. **Prediction:** after recompiling, the metadata for the `RuntimeMark` usages is written into the class file under CLASS retention, but is not visible through reflection. If you run the **unmodified program** with the `getAnnotation(...).value()` calls, it may throw a `NullPointerException` at the line reading `runtime-base` because `getAnnotation(RuntimeMark.class)` returns `null`. To see all the new results clearly, update the test program to use safe checks such as:

~~~java
System.out.println(
    BaseService.class.isAnnotationPresent(RuntimeMark.class)); // false
~~~

Do not conclude that `@RuntimeMark` is missing from the class file solely from `false`. Use `javap -v BaseService` to see the information in `RuntimeInvisibleAnnotations`.

### Experiment B2 — Changing CLASS to SOURCE

Change `@Retention(CLASS)` on `ClassMark` to `SOURCE`, recompile, and run `javap -v BaseService`.

**Prediction:** the `@ClassMark` usages are no longer stored in the target class file. Reflection remains `false` as before. This is an example showing that **two different configurations can produce the same reflection result but different bytecode**.

### Experiment B3 — Changing CLASS to RUNTIME

Change `@Retention(CLASS)` on `ClassMark` to `RUNTIME` and recompile.

**Prediction:** `BaseService.class.isAnnotationPresent(ClassMark.class)` changes from `false` to `true`; the annotation can also be read from the corresponding field and method. In `javap -v`, the `ClassMark` usage appears in the visible group instead of the invisible group. Its `@Target` remains unchanged.

### Experiment C1 — Removing @Inherited from FamilyLabel

Keep `RUNTIME` but remove the `@Inherited` line on `FamilyLabel`, then recompile the program. When running the **unmodified code**, `child.getAnnotation(FamilyLabel.class)` will return `null`, so the subsequent `.value()` call can cause a `NullPointerException`.

To observe the output without crashing, change that specific print statement to:

~~~java
System.out.println(
    ChildService.class.getAnnotation(FamilyLabel.class) != null);
~~~

**Prediction:** prints `false`. Meanwhile, `BaseService.class.getAnnotation(FamilyLabel.class)` still reads the value `"parent"` because the annotation is still directly on the parent class and has `RUNTIME` retention. Removing `@Inherited` does not delete the annotation on the parent itself.

### Experiment C2 — Keeping Inherited While Changing Retention to CLASS

Keep `@Inherited` on `FamilyLabel` but change its retention from `RUNTIME` to `CLASS`; recompile. `ChildService.class.getAnnotation(FamilyLabel.class)` does not see the annotation at runtime because metadata on `BaseService` is not exposed by reflection. `@Inherited` cannot compensate for an unsuitable retention.

### Experiment C3 — Adding FamilyLabel Directly on ChildService

Keep `@Inherited` and `RUNTIME`; add:

~~~java
@FamilyLabel("child-direct")
class ChildService extends BaseService {
    @Override public void process() {}
}
~~~

**Prediction:** `ChildService.class.getAnnotation(FamilyLabel.class).value()` returns `"child-direct"`. At the same time, `ChildService.class.getDeclaredAnnotation(FamilyLabel.class)` is no longer `null`, because the annotation is now declared directly on the child.

### Experiment C4 — Annotating an Interface

Keep `@Inherited` and `RUNTIME` on `FamilyLabel`. Even though the `ServiceContract` interface has `@FamilyLabel("interface")`, `InterfaceImpl.class.getAnnotation(FamilyLabel.class)` still returns `null` if `InterfaceImpl` is not annotated directly and does not receive the annotation from a matching superclass.

### Experiment C5 — Annotating a Method with @Inherited

The main program already has `@Inherited` on the annotation type `MethodMark` and `@MethodMark` on the method `BaseService.process()`. `ChildService.process()` overrides it without declaring `@MethodMark`, so looking it up on the overridden method returns `null`. Changing the Target of `MethodMark` to include `TYPE` can allow this annotation to also be placed on a class, but does **not** make the overridden method automatically receive the parent method's annotation.

## 10. Predicted Outcome Matrix (Quick Reference)

The following table considers the case where the annotation is attached **directly to Base**, the class `Child extends Base` has no annotation of the same type, and runtime code uses `Class.getAnnotation(T.class)`. Scenarios where the target does not allow placement on a class are excluded from the start.

| Does Target allow TYPE? | Retention | Has @Inherited? | Can Base's annotation be read via reflection? | Does Child see Base's annotation via `getAnnotation`? |
| --- | --- | --- | --- | --- |
| Yes | `SOURCE` | No | No | No |
| Yes | `SOURCE` | Yes | No | No |
| Yes | `CLASS` | No | No | No |
| Yes | `CLASS` | Yes | No | No |
| Yes | `RUNTIME` | No | Yes | No |
| Yes | `RUNTIME` | Yes | Yes | **Yes** |
| No | Any | Any | **Cannot be attached to Base from new source** | No valid source case to test inheritance under the assumption |

Additional conditions: the annotation must be on a **class declaration**, not an interface or method; the source/class files must be compiled with annotation type definitions compatible with the configuration being tested. `getDeclaredAnnotation` on Child will **not** check the parent in any row of the table. If Child attaches annotation T itself, evaluate the direct annotation on Child first instead of applying the table meant for an unannotated Child.

Here is a quick rule of thumb: if you want an annotation to **be readable from a subclass via runtime reflection**, the minimal design typically includes:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DomainLabel {}
~~~

Of course, the actual name and target must reflect the business meaning; do not blindly add `@Inherited` just to make retrieving metadata convenient if you do not want the parent class policy to apply to subclasses.

## 11. Rules for getAnnotation and getDeclaredAnnotation in the Experiment

Three questions need to be distinguished:

1. **Does this element declare the annotation directly?** Use `getDeclaredAnnotation(T.class)`.
2. **Is annotation T considered present on the element?** Use `getAnnotation(T.class)`; for `Class`, if T is inherited and the conditions match, it can read from the superclass.
3. **Are there multiple repeatable usages of T?** Use `getAnnotationsByType(T.class)` or `getDeclaredAnnotationsByType(T.class)` to handle `@Repeatable` and container annotations.

Do not use `getAnnotation(T.class) == null` to conclude “there are no usages of T” when T is repeatable and has entries inside a container: the single-annotation API does not automatically unwrap the container. In the main practice program, the annotations are not repeatable, so this issue does not affect stdout.

**Note:** `@Inherited` applies according to the lookup rule on **Class**, not as “every declaration inherited by Java inherits metadata”. A superclass method found via `getMethod` may cause you to read the superclass method itself, rather than an annotation automatically copied by Java onto the subclass's overridden method.

## 12. Common Mistakes When Comparing the Three Meta-Annotations

| Misconception | Reality |
| --- | --- |
| “`@Target(TYPE)` makes the annotation stored in the class file” | Target only restricts placement; Retention determines whether data is kept in the class file |
| “`@Retention(RUNTIME)` means the annotation takes effect automatically” | It only supports runtime access; actual code/framework is needed to process the metadata |
| “`@Inherited` makes a SOURCE annotation appear at runtime” | No; SOURCE metadata does not exist in runtime reflection |
| “CLASS and SOURCE are the same because both return false in reflection” | False; CLASS is still stored in bytecode, whereas SOURCE is not |
| “`@Inherited` propagates an interface annotation to implementing classes” | No; this standard inheritance follows the class's superclass |
| “Overridden methods automatically inherit the parent method's annotation” | No, even when the annotation type has `@Inherited` |
| “`getDeclaredAnnotation` also retrieves annotations from the parent” | No; Declared only checks the current element |
| “Expanding Target automatically adds the annotation to all new members” | No; it only expands where the annotation can be written in source code |
| “An annotation attached to a class will be visible when reading Field.getAnnotation” | No; the annotation must actually be attached to the field |
| “Changing retention in a JAR automatically updates attributes in previously compiled class files” | No; you must inspect the bytecode and recompile the annotated source to test changes under the new contract |
| “If the compiler rejects @Target, the JVM fails at runtime” | No valid new class file is produced for invalid source; the error occurs at compile time |
| “@Inherited is required for every annotation” | No; use it only when the class-level metadata semantics are designed to apply to subclasses |

A sign of flawed testing is relying on a single `false` result. When you get `false`, you must determine whether it means **no metadata at runtime**, **simply not inherited**, **reading at the wrong location**, or **no direct annotation**.

## 13. How to Test in a Project Using a Framework

For example, suppose a system uses `@RequiresPermission` on a class and wants subclasses to automatically receive the parent's policy. When `@Inherited` and `@Retention(RUNTIME)` are added, components using `Class.getAnnotation(RequiresPermission.class)` can receive the annotation from a matching superclass. However:

- The framework may use the `getDeclaredAnnotations()` API and **not** receive inherited metadata even though the annotation type has `@Inherited`.
- The framework may traverse interfaces, method overrides, or container annotations according to its own policy, **independent of** standard reflection rules.
- `@Target(TYPE)` allows attaching to a class, but whether the policy propagates from the class to methods is decided by the framework.
- A security policy should clearly document and test **when the superclass policy applies**, **when a child overrides it**, **whether merging occurs**, and **behavior when metadata is absent**. Do not rely solely on meta-annotations to claim that authorization is protected.

Therefore, when comparing actual results, check both **Java's contract** and **the framework consumer's contract**. Java reflection provides certain default rules, while a framework may apply different ones.

## 14. Practice Evaluation Checklist

You have completed this practice when you can:

- [ ] Predict valid/invalid targets for class, field, method, constructor, parameter, and type-use.
- [ ] Explain why code attaching an annotation to an invalid target **fails to compile**, without even running.
- [ ] State clearly that the default of `@Retention` is `CLASS` and omitting `@Target` does not imply supporting all type-use contexts.
- [ ] Compile the Java 17 program and compare SOURCE/CLASS/RUNTIME stdout against reflection.
- [ ] Use `javap -v BaseService` to verify that CLASS remains in the class file even though reflection returns `false`.
- [ ] Explain the difference between reading metadata on a class, field, and method.
- [ ] Predict `getAnnotation` and `getDeclaredAnnotation` on Child when `@Inherited` is enabled/disabled.
- [ ] Point out why an annotation on an interface is not received by an implementing class through the `@Inherited` mechanism.
- [ ] Point out why an annotation on a superclass method does not automatically propagate to an overridden method.
- [ ] Predict the outcome when a subclass directly declares an annotation of the same type as the superclass.
- [ ] Avoid changing Target, Retention, and Inherited simultaneously in a single experiment when the goal is to isolate the cause.
- [ ] When replacing an annotation library version, distinguish between old class files and recompiled class files.
- [ ] If the annotation drives a framework, identify the **consumer** and test the framework logic itself, not just reflection.

**Remember:** `@Target` determines **where it can be attached**, `@Retention` determines **the retention level of metadata**, and `@Inherited` governs **how reflection looks up annotations on a subclass from its superclass**. Changing each meta-annotation can lead to **compilation errors**, **class-file/reflection differences**, or **inheritance lookup differences** — these three kinds of outcomes must be evaluated separately before combining them into a complete annotation design.
