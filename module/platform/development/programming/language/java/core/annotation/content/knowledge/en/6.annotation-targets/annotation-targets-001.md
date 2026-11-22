# `@Target` and the `ElementType` Value Set in Java

## 1. Purpose of `@Target`

In Java, an annotation can appear in many locations: on a class, method, field, parameter, type in generics, record component, etc. Not every annotation is valid everywhere. **`@Target` is a meta-annotation that specifies the kinds of locations where an annotation type is allowed to be applied**. Those locations are enumerated by the `java.lang.annotation.ElementType` enum.

Example of an annotation for methods only:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface TraceCall {
}

class Service {
    @TraceCall
    void execute() {
    }
}
~~~

`@TraceCall` is valid on `execute()` because it is a method declaration. Placing `@TraceCall` on a class or field declaration causes an error **right at compile time** because it does not belong to the `METHOD` target. `@Target` does not create logging logic; `TraceCall` only provides metadata, and logging behavior requires a program or framework to actually process it.

Packages to recognize:

- `java.lang.annotation.Target`: an annotation placed **on an `@interface` declaration** to specify usage locations.
- `java.lang.annotation.ElementType`: an enum identifying declaration locations or type-use locations.
- `java.lang.annotation.Retention` and `RetentionPolicy`: determine whether an annotation exists in the source, class file, or at runtime. This is a **different** aspect from where the annotation is allowed to appear.

## 2. Syntax of `@Target`

`Target` declares an element `value()` of type `ElementType[]`. In Java, an element named `value` is allowed to use shorthand syntax, and an array consisting of a single element can omit the curly braces when providing the annotation value.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldOnly {
}

@Target(value = ElementType.FIELD)
@interface AlsoFieldOnly {
}

@Target({ElementType.FIELD, ElementType.METHOD})
@interface FieldOrMethod {
}

@Target(value = {ElementType.FIELD, ElementType.METHOD})
@interface AlsoFieldOrMethod {
}
~~~

`FieldOnly` and `AlsoFieldOnly` have the same set of valid locations; the same applies to the last two declarations. When an annotation is allowed at **multiple** kinds of locations, write the constants inside `{...}` and separate them with commas. The target set has no order of precedence.

An `ElementType` value must not be repeated within a `@Target`:

~~~java
// INVALID code: the same enum constant appears twice.
// @Target({ElementType.FIELD, ElementType.FIELD})
// @interface Invalid {}
~~~

The repetition above is an error in the **target list**, completely different from the rule regarding whether an annotation can be applied repeatedly on a declaration (`@Repeatable`).

### If an Annotation Does Not Declare `@Target`

~~~java
@interface GeneralMark {
}
~~~

According to the Java SE 17 JLS, `GeneralMark` can be used in **every declaration context** but not in a **type context**. Therefore, omitting `@Target` is not a simple way to allow every form of type-use. For example, `List<@GeneralMark String>` is invalid without `@Target(ElementType.TYPE_USE)`.

Using `@Target` explicitly makes the API easier to understand and catches wrong-location errors at compile time.

## 3. All 12 `ElementType` Values in Java 17

Java SE 17 has **12 constants** in `ElementType`. Eleven constants identify kinds of declaration locations or special definitions, and `TYPE_USE` specifies type-use contexts.

| `ElementType` Constant | Target Described | Example or Usage |
| --- | --- | --- |
| `TYPE` | Class, interface (including annotation interface), enum, or record declaration | `@Mark class User {}` |
| `FIELD` | Field declaration, including enum constants | `@Mark String id;` |
| `METHOD` | Method declaration, including annotation type element methods | `@Mark void save() {}` |
| `PARAMETER` | Formal parameter declaration (method, constructor, corresponding `catch` parameter) | `void save(@Mark String s)` |
| `CONSTRUCTOR` | Constructor declaration | `@Mark User() {}` |
| `LOCAL_VARIABLE` | Local variable declaration | `@Mark String temp = "";` |
| `ANNOTATION_TYPE` | Declaration of an annotation type | `@Mark @interface Rule {}` |
| `PACKAGE` | Package declaration | Annotations are typically declared in `package-info.java` |
| `TYPE_PARAMETER` | Type parameter declaration of a generic class, interface, method, or constructor | `class Box<@Mark T> {}` |
| `TYPE_USE` | Type-use locations | `List<@Mark String>`, field types, cast types |
| `MODULE` | Module declaration | `module-info.java` |
| `RECORD_COMPONENT` | Record component declaration | `record User(@Mark String name) {}` |

Important version history: `TYPE_PARAMETER` and `TYPE_USE` were added in Java 8, `MODULE` in Java 9, and `RECORD_COMPONENT` in Java 16. They are all present in Java 17.

Essential distinctions:

- **`FIELD` differs from `LOCAL_VARIABLE`**: a member variable is a field, whereas a variable declared inside a method body is a local variable; not every Java variable should be called a field.
- **`METHOD` differs from `CONSTRUCTOR`**: a constructor has its own target; you cannot use the `METHOD` target simply because a constructor has a parameter list.
- **`PARAMETER` differs from `TYPE_PARAMETER`**: one marks the variable that receives an argument when calling a method/constructor; the other marks a generic type symbol such as `T`.
- **`TYPE` differs from `ANNOTATION_TYPE`**: `TYPE` is broader and also includes annotation interface declarations; `ANNOTATION_TYPE` applies only to `@interface` declarations.
- **`RECORD_COMPONENT` differs from `FIELD`**: a component declared in a record header has its own reflection model, even though the compiler may generate the corresponding field, accessor, and constructor parameter.
- **`TYPE_USE` differs from `TYPE`**: one describes **a type being used**, while the other primarily describes **a type definition declaration**.

## 4. Declaration Annotations and Type-Use Annotations

This is the most important distinction when learning `@Target`.

### Annotation on a Declaration

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface AuditedField {
}

class Account {
    @AuditedField
    String number;
}
~~~

`@AuditedField` marks the **field declaration** `number`. A processor can inspect the field carrying this metadata. It does not change the `String` type, does not perform encryption on its own, and does not execute any action.

### Annotation on a Type Use

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface TaggedType {
}

class Names {
    List<@TaggedType String> names;
}
~~~

`@TaggedType` marks **the `String` type as a type argument** in `List<String>`. This is a type-use, different from attaching an annotation to the `names` field itself.

`TYPE_USE` can also be used on return types, field types, parameter types, cast types, types in `new` expressions, parts of arrays or generics, and many other type-use locations defined by the JLS. For example, `(@TaggedType String) input` annotates the target type of the cast, but **does not make the cast safer** or automatically add validation.

A point to avoid overstating: `@Target(TYPE_USE)` can also be placed on **class/interface declarations and type parameter declarations** according to Java rules. It is not simply limited to expression bodies. The essence of `TYPE_USE` is the language's **type contexts** scope, which has overlapping rules with declaration contexts.

### `TYPE_PARAMETER` Differs from `TYPE_USE`

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_PARAMETER)
@interface GenericDeclaration {
}

@Target(ElementType.TYPE_USE)
@interface TypeArgument {
}

class Box<@GenericDeclaration T> {
    List<@TypeArgument String> items;
}
~~~

`@GenericDeclaration` marks **when the type variable `T` is defined**. `@TypeArgument` marks **the `String` type passed into the generic `List`**. When you want to support both kinds of locations, you can declare `@Target({ElementType.TYPE_PARAMETER, ElementType.TYPE_USE})` if that fits the API; however, keep in mind that a `TYPE_USE` annotation also has permitted declaration locations under the JLS.

### Classification Based on Metadata, Not Just Written Text

Example:

~~~java
@Target(ElementType.FIELD)
@interface OnField {
}

@Target(ElementType.TYPE_USE)
@interface OnType {
}

class Entry {
    @OnField
    private @OnType String key;
}
~~~

`@OnField` targets the field declaration, while `@OnType` targets the **type of the field**. At runtime, if the retention is `RUNTIME`, the two kinds can be read through different APIs:

- `Field.getAnnotation(OnField.class)`: looks up the field's declaration annotation.
- `Field.getAnnotatedType().getAnnotation(OnType.class)`: looks up the type annotation of the field's type.

In the case where an annotation type targets **both `FIELD` and `TYPE_USE`**, the JLS also specifies how an annotation at one syntactic position can belong to both contexts. You need to check the targets and language rules before concluding that it is only a declaration or type-use annotation.

## 5. Standalone Runnable Java 17 Example

Create the single **`TargetDemo.java`** file below to directly observe targets for field, method, type-use, generic type parameter, and record component.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMarker {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface GenericMarker {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentMarker {
}

class Storage<@GenericMarker T> {
    @Label("database-key")
    private @TypeMarker String code = "A-01";

    @Label("read")
    String read() {
        return code;
    }
}

record Item(@ComponentMarker int id) {
}

public class TargetDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field = Storage.class.getDeclaredField("code");
        Method method = Storage.class.getDeclaredMethod("read");

        System.out.println("Field label: "
                + field.getAnnotation(Label.class).value());
        System.out.println("Method label: "
                + method.getAnnotation(Label.class).value());
        System.out.println("Type-use on field type: "
                + field.getAnnotatedType()
                       .isAnnotationPresent(TypeMarker.class));
        System.out.println("Type parameter: "
                + Storage.class.getTypeParameters()[0]
                       .isAnnotationPresent(GenericMarker.class));
        System.out.println("Record component: "
                + Item.class.getRecordComponents()[0]
                       .isAnnotationPresent(ComponentMarker.class));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac TargetDemo.java
java TargetDemo
~~~

Exact **stdout** output:

~~~text
Field label: database-key
Method label: read
Type-use on field type: true
Type parameter: true
Record component: true
~~~

Explanation:

1. `Label` has two targets, `FIELD` and `METHOD`, so `Field.getAnnotation` and `Method.getAnnotation` see the corresponding values.
2. `TypeMarker` has `TYPE_USE` and is placed on the field's `String` type. Therefore, it is accessed via `field.getAnnotatedType()`.
3. `GenericMarker` targets the declaration of `T` in `Storage<T>`; `Class.getTypeParameters()[0]` returns a `TypeVariable` from which annotations retained at runtime can be accessed.
4. `ComponentMarker` targets the `id` component in the record, which is read via `Class.getRecordComponents()[0]`.
5. All of them are declared with `@Retention(RUNTIME)` because this example uses **runtime reflection** to observe metadata.

You can create a compile-time error yourself to understand targets. Change `Label` to:

~~~java
@Target(ElementType.METHOD)
@interface Label {
    String value();
}
~~~

After this change, `@Label("database-key")` placed on the `code` field is no longer valid. Simply adding `@Retention(RUNTIME)` cannot fix the error, because retention does not change the set of permitted locations.

Similarly, if you change `GenericMarker` to target `METHOD`, placing it on `T` of `Storage<T>` will be rejected by the compiler. This is an error **at source/compile time**, without even running the program.

## 6. Two Special Locations: Package and Module

### Package: `ElementType.PACKAGE`

An annotation attached to a package declaration is usually placed in **`package-info.java`**. The following multi-file example only describes project structure, not a standalone program.

File `src/example/library/PackageTag.java`:

~~~java
package example.library;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
public @interface PackageTag {
}
~~~

File `src/example/library/package-info.java`:

~~~java
@PackageTag
package example.library;
~~~

`@PackageTag` marks **the `example.library` package**; it does not automatically turn every class in the package into a class annotated with `@PackageTag`.

### Module: `ElementType.MODULE`

In a project using the Java Platform Module System, an annotation targeting `MODULE` is used on the module declaration in `module-info.java`. Syntax example:

~~~java
@com.example.ModuleTag
module example.app {
}
~~~

To compile, `com.example.ModuleTag` must be a valid annotation type defined with `@Target(ElementType.MODULE)`, and the module must also be properly arranged in the project. The snippet above is **only an illustrative fragment** and cannot run standalone without the annotation definition and module structure.

## 7. `RECORD_COMPONENT` and What to Note About Propagation

A record:

~~~java
record Person(String name, int age) {
}
~~~

has two record components, `name` and `age`, in its header. The `RECORD_COMPONENT` target is used for that location:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ColumnName {
    String value();
}

record Person(@ColumnName("full_name") String name) {
}
~~~

This is an illustrative snippet that is standalone in terms of types, without a `main` method. If you read `Person.class.getRecordComponents()[0].getAnnotation(ColumnName.class)`, you can retrieve the value `full_name`.

Java has **propagation** rules: an annotation written on a record component can be propagated to the corresponding field, accessor, or constructor parameter if the annotation type is allowed to be applied in those declaration/type contexts. When an annotation targets only `RECORD_COMPONENT`, you should not assume it will be visible on the field or method. To accurately read **component** information, use `RecordComponent` and an appropriate retention.

## 8. `@Target` and `@Retention` Solve Two Different Problems

| Aspect | `@Target` | `@Retention` |
| --- | --- | --- |
| Question | **Where** is the annotation placed? | **Until when** is the metadata stored? |
| Values | One or more `ElementType` values | One `RetentionPolicy` |
| Example | `@Target(METHOD)` | `@Retention(RUNTIME)` |
| Compiler check | Whether the annotation placement is valid | Whether the metadata needs to be kept in the class file/runtime |
| Automatically runs business logic? | No | No |

`RetentionPolicy.SOURCE` is only needed for the source/compiler; `RetentionPolicy.CLASS` stores metadata in the class file, though runtime reflection typically does not access it; `RetentionPolicy.RUNTIME` supports reflection where appropriate APIs exist.

An important note about `LOCAL_VARIABLE`: runtime reflection does not provide `LocalVariable.getAnnotation()` to freely query local variable declarations inside a method body. You cannot assume that simply having `@Retention(RUNTIME)` makes every annotation on a local variable accessible like on a class or field. Annotations **on the type** of a local variable have different bytecode emission rules than annotations **on the declaration** of that variable.

## 9. Common Misconceptions

**Misconception 1 — `TYPE` can be used everywhere a type name appears.** False. `TYPE` primarily applies to class/interface/enum/record definition declarations; a type used in `List<@Mark String>` requires `TYPE_USE`.

**Misconception 2 — `TYPE_PARAMETER` and `PARAMETER` are the same.** False. `<T>` is a generic type parameter; `void method(String input)` has a formal parameter.

**Misconception 3 — `FIELD` includes every variable.** False. Local variables have `LOCAL_VARIABLE`; record components have a dedicated target.

**Misconception 4 — A constructor is a `METHOD`.** False. An annotation directly on a constructor declaration requires the `CONSTRUCTOR` target.

**Misconception 5 — Omitting `@Target` is equivalent to specifying every `ElementType`.** False. The default rule covers declaration contexts; type contexts are not included.

**Misconception 6 — `ANNOTATION_TYPE` is identical to `TYPE`.** False. `ANNOTATION_TYPE` covers only `@interface` declarations, while `TYPE` has a broader scope.

**Misconception 7 — `TYPE_USE` strictly never includes declaration locations.** False. Java allows certain cases such as class/interface declarations and type parameters according to JLS rules.

**Misconception 8 — `@Target` can trigger validation or logging.** False. It only restricts locations; a processor or framework is needed to carry out business logic.

**Misconception 9 — A runtime annotation on a record component is guaranteed to be present on the accessor/field.** False if targets and propagation rules are not taken into account.

**Misconception 10 — Adding `@Retention(RUNTIME)` will allow an annotation with the wrong target to compile.** False, because target and retention are independent.

## 10. Exercises and Answers

**Exercise 1.** An annotation has `@Target({ElementType.FIELD, ElementType.PARAMETER})`. Can it be placed on a member variable, a local variable, a method parameter, and a method declaration?  
**Answer:** Yes on a member variable (field) and a parameter declaration; no on a local variable and a method declaration.

**Exercise 2.** If you want to apply `@Mark` in `Map<String, @Mark Integer>`, which target is needed?  
**Answer:** `TYPE_USE`; `Integer` here is a type argument.

**Exercise 3.** Which part does `class Container<@Mark T>` attach the annotation to?  
**Answer:** The generic type parameter declaration `T`; use `TYPE_PARAMETER` (or an annotation type supporting type contexts according to the JLS).

**Exercise 4.** Does `@Target(ElementType.METHOD)` allow placement on a constructor?  
**Answer:** No. A constructor declaration requires `CONSTRUCTOR`.

**Exercise 5.** Can `@Target(ElementType.TYPE)` be used on the declaration `@interface MyRule`?  
**Answer:** Yes. An annotation interface is a kind of interface; `ANNOTATION_TYPE` is the narrower choice if you only want it applied to annotation types.

**Exercise 6.** Why is `Field.getAnnotation(Mark.class)` not always the way to read a `TYPE_USE` annotation placed before a field's type?  
**Answer:** Declaration annotations and type annotations can reside in different metadata locations. For a type-use annotation on a field's type, use `Field.getAnnotatedType()`.

**Exercise 7.** Does adding `@Retention(RUNTIME)` make `@Target(FIELD)` valid to use on a method?  
**Answer:** No. Retention does not change the target.

**Exercise 8.** In `TargetDemo.java`, if the target of `ComponentMarker` is changed to only `METHOD`, what happens?  
**Answer:** `@ComponentMarker` on the record component `id` becomes invalid, so compilation fails.

## 11. Authoritative References

- [JLS Java SE 17 — §9.6.4.1 `@Target`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1)
- [JLS Java SE 17 — §9.7.4 Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4)
- [Java SE 17 API — `ElementType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html)
- [Java SE 17 API — `Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html)

Designing an annotation begins with determining **whether you are annotating a declaration or a type use**. Once you have chosen the right `ElementType`, add the retention and processing logic that suit your application's needs.
