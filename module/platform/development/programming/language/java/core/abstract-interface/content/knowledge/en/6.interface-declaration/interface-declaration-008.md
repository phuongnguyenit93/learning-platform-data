# Distinguishing Regular Interfaces from Annotation Interfaces in Java

## 1. Two Kinds of Interfaces, Two Purposes

A regular `interface` declares a **behavioral contract**. A class can `implements` it, a variable can hold a reference to an implementing object, and the program calls methods through the interface type.

`@interface` is the syntax for declaring an **annotation type** (annotation interface). It defines structured metadata to attach to a class, method, field, or other location; the compiler, an annotation processor, a framework, or Reflection code can read that metadata. `@interface` is not an `@` symbol placed in front of an existing interface.

| Criterion | Regular interface | Annotation interface |
| --- | --- | --- |
| Declaration | `interface Exporter { ... }` | `@interface ExportInfo { ... }` |
| Purpose | Behavioral contract and polymorphism | Metadata template |
| Main members | Abstract, default, static, private methods; constants | Parameterless elements, which may have default values |
| Usage | `class C implements Exporter` | `@ExportInfo(owner = "Team")` |
| How to read | Call methods on an object | Read metadata using Reflection or compile-time tools |
| Type relationships | Can `extends` and have classes `implements` it | Cannot declare `extends` arbitrarily; its relationship with `java.lang.annotation.Annotation` is defined by Java |

## 2. Annotation Elements Are Not Regular Methods

Example of an annotation declaration:

```java
@interface JobInfo {
    String owner();
    int priority() default 3;
    String[] tags() default {};
}
```

`owner`, `priority`, and `tags` are **annotation elements**. They take no parameters, have no method body, and have restricted return types. Valid types include primitives, `String`, `Class`, enums, annotation types, and one-dimensional arrays of those types. `void`, `Object`, `List<String>`, multidimensional arrays, and elements with parameters are all invalid.

An element without a default value is required when using the annotation. An element with `default` can be omitted. The `default` keyword here provides a **default metadata value**, not the code of a default method.

```java
@JobInfo(owner = "Team A", tags = {"batch", "demo"})
final class ImportJob {}
```

`priority` receives the value 3 because the annotation does not provide another value. If an annotation has only an element named `value`, a shorthand syntax such as `@Role("admin")` can be used instead of `@Role(value = "admin")`.

## 3. Target and Retention

Two common meta-annotations:

- `@Target` specifies the locations where the annotation is allowed to be attached, such as `TYPE` for type declarations or `METHOD` for methods.
- `@Retention` specifies the stage up to which the annotation is retained: `SOURCE` is only for source code/compilation; `CLASS` is stored in the class file; `RUNTIME` allows Reflection to read it at runtime.

If `@Retention` is not declared, the default is `CLASS`. To read an annotation at runtime, declare `@Retention(RetentionPolicy.RUNTIME)`. An annotation with SOURCE retention can still be read by an annotation processor during the compilation step.

Other meta-annotations include `@Documented`, `@Inherited`, and `@Repeatable`. `@Inherited` applies to annotation queries on a superclass according to Java rules; it does not automatically propagate annotations across interfaces or method overrides.

## 4. Java 17 Example: Behavior and Metadata Coexisting

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

interface Executable {
    void execute();

    default String category() {
        return "task";
    }
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface JobInfo {
    String owner();
    int priority() default 3;
}

@JobInfo(owner = "Team A")
final class ImportJob implements Executable {
    @Override
    public void execute() {
        System.out.println("importing");
    }
}

public class Main {
    public static void main(String[] args) {
        Executable job = new ImportJob();
        job.execute();
        JobInfo info = ImportJob.class.getAnnotation(JobInfo.class);
        System.out.println(info.owner());
        System.out.println(info.priority());
        System.out.println(Executable.class.isAnnotation());
        System.out.println(JobInfo.class.isAnnotation());
    }
}
```

Output:

```text
importing
Team A
3
false
true
```

`ImportJob implements Executable` creates a behavioral contract relationship. `@JobInfo(owner = "Team A")` attaches metadata to the class; it does not automatically add an `execute` method, does not make the class implement the annotation, and does not perform business behavior on its own. What effect an annotation has depends on the compiler, processor, framework, or code that reads it.

## 5. Common Mistakes

- Using `@interface` when you want every implementation to provide a method: use a regular interface.
- Declaring an element of type `List<String>` or with parameters: annotation elements have restricted types and must take no parameters.
- Omitting a required element: provide a value when attaching the annotation or set an appropriate default.
- Expecting an annotation to automatically protect, validate, or initialize a service: code or a framework is needed to actively process the metadata.
- Forgetting `RUNTIME` and expecting `getAnnotation` to read the metadata: the default retention is CLASS.
- Confusing `@Deprecated interface OldApi` (a regular interface with an annotation attached) with `@interface Marker` (an annotation type declaration).

**Self-check:** If a class is annotated with `@RequiresPermission("write")`, does that automatically block unauthorized users from calling methods? No; the annotation only provides metadata. An actual checking mechanism is needed to enforce the policy.
