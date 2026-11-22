# AnnotatedElement and Annotation-Supporting Objects in Java Reflection

In Java, an annotation is metadata attached to a declaration or to a use site of a type. Reflection can read annotations retained at runtime through the **`java.lang.reflect.AnnotatedElement`** interface. Rather than each kind of Reflection object having a completely different way to read annotations, this interface unifies operations such as `getAnnotation(...)`, `getAnnotations()`, `getDeclaredAnnotations()`, and `getAnnotationsByType(...)`.

This lesson answers three questions: **which objects implement `AnnotatedElement`**, **how to look up annotations accurately at runtime**, and **why results vary depending on retention, inheritance, repeatable annotations, and annotation location**.

## 1. What is AnnotatedElement?

`AnnotatedElement` is an interface in the `java.lang.reflect` package. It describes an element that can carry annotations and provides an API for reading annotation metadata via Reflection.

Some important methods:

```java
<T extends Annotation> T getAnnotation(Class<T> annotationType);
Annotation[] getAnnotations();
<T extends Annotation> T getDeclaredAnnotation(Class<T> annotationType);
Annotation[] getDeclaredAnnotations();
<T extends Annotation> T[] getAnnotationsByType(Class<T> annotationType);
<T extends Annotation> T[] getDeclaredAnnotationsByType(Class<T> annotationType);
boolean isAnnotationPresent(Class<? extends Annotation> annotationType);
```

These are **abbreviated illustrative** signatures for learning the API, not standalone source code to compile. `Annotation` is the `java.lang.annotation.Annotation` interface.

Key points:

- Every annotation-reading method returns data that is **observable at runtime**; `@Retention(RetentionPolicy.SOURCE)` and `CLASS` are not guaranteed to be readable via runtime Reflection.
- `getAnnotation(T.class)` returns **a single annotation** of type `T`, or `null` if that type is not “present” as defined by the API.
- `isAnnotationPresent(T.class)` is equivalent in result to `getAnnotation(T.class) != null`.
- `getAnnotations()` returns an array of “present” annotations. `getDeclaredAnnotations()` returns only annotations **directly present** on the element itself.
- `getAnnotationsByType(T.class)` and `getDeclaredAnnotationsByType(T.class)` provide special support for **repeatable annotations**: they can unpack container annotations to retrieve multiple `T` elements.
- Returned annotation arrays can be modified by the caller without altering the results returned by subsequent lookups; annotation objects are immutable and serializable by API contract.

The concepts “present”, “directly present”, “indirectly present”, and “associated” have technical meanings, especially when annotations are allowed to be inherited or repeated. Therefore, all of the methods above must not be treated as synonyms.

## 2. Which Reflection objects support AnnotatedElement?

Not only `Class<?>`, many other metadata objects also implement `AnnotatedElement`:

| Object type | Example of how to obtain | Where are annotations read from? |
| --- | --- | --- |
| `Class<?>` | `Book.class` | Declaration of a class, interface, enum, annotation type, or record |
| `Method` | `Book.class.getDeclaredMethod("read")` | Method declaration |
| `Constructor<?>` | `Book.class.getDeclaredConstructor()` | Constructor declaration |
| `Field` | `Book.class.getDeclaredField("title")` | Field declaration |
| `Parameter` | `method.getParameters()[0]` | Formal parameter declaration |
| `Package` | `Book.class.getPackage()` | Annotations placed on a package, usually in `package-info.java` |
| `Module` | `Book.class.getModule()` | Annotations applied to a module declaration |
| `RecordComponent` | `Person.class.getRecordComponents()[0]` | Record component annotations (Java 16+) |
| `AnnotatedType` and its subtypes | `method.getAnnotatedReturnType()` | Annotations at a **type-use site** (type-use) |

`Method` and `Constructor<?>` both extend `Executable`; objects in this group also have `getParameters()`, `getParameterAnnotations()`, `getAnnotatedParameterTypes()`, `getAnnotatedExceptionTypes()`, and other signature metadata APIs. `Field` has `getAnnotatedType()` to retrieve type-use annotations on the field's type.

An important distinction: **an annotation on a method declaration** is not identical to **an annotation on a method's return type**. Both `Method` and `AnnotatedType` are `AnnotatedElement`, but each object represents **a different location** in the source/class file.

Example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonBlank {}

public @NonBlank String getName() {
    return "Ada";
}
```

This is an illustrative snippet that requires importing `java.lang.annotation.*` and placing inside a valid class. `@NonBlank` is attached to **the use of the return type `String`**. To read it, access:

```java
Method m = SomeClass.class.getDeclaredMethod("getName");
boolean found =
        m.getAnnotatedReturnType().isAnnotationPresent(NonBlank.class);
```

This is an illustrative snippet; `SomeClass` must be replaced with the class containing `getName`, handling checked exceptions and importing `Method`. If you only call `m.isAnnotationPresent(NonBlank.class)`, you are querying the **method declaration**, not the return type-use annotation.

## 3. Retention and Target determine where an annotation can be read

An annotation type is typically declared with **meta-annotations**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audit {
    String value();
}
```

This is an annotation declaration that can be placed in valid source code. `@Target` specifies the allowed syntactic locations; `@Retention` specifies the metadata retention level.

| RetentionPolicy | Present in source | Present in class file | Readable by standard runtime Reflection? |
| --- | --- | --- | --- |
| `SOURCE` | Yes | Does not need to be stored | No |
| `CLASS` | Yes | Stored in class file | Not runtime-visible via standard APIs |
| `RUNTIME` | Yes | Stored | Yes, on the corresponding object/element |

If **`@Retention` is not declared**, the default retention of an annotation type is `CLASS`, not `RUNTIME`.

Some common `ElementType` values: `TYPE`, `METHOD`, `FIELD`, `CONSTRUCTOR`, `PARAMETER`, `PACKAGE`, `MODULE`, `RECORD_COMPONENT`, `TYPE_USE`, `TYPE_PARAMETER`, and `ANNOTATION_TYPE`.

Distinguish `TYPE` (annotation on a type declaration), `TYPE_USE` (annotation on a type-use site), and `TYPE_PARAMETER` (annotation on a type parameter declaration such as `<@X T>`). An annotation type can declare multiple targets. In many contexts, a `TYPE_USE` annotation appearing next to a declaration may also be processed by the compiler according to related target rules; therefore, to observe accurately, always inspect the exact `AnnotatedElement` object rather than inferring solely from where `@` appears on the line.

## 4. Complete Java 17+ program: Class, Method, Field, Parameter, and AnnotatedType

Create the file **`AnnotatedElementDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class AnnotatedElementDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD,
            ElementType.FIELD, ElementType.PARAMETER})
    @interface Label {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Tags.class)
    @interface Tag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Tags {
        Tag[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface NonBlank {
    }

    @Label("base")
    @Role("reader")
    @Tag("red")
    @Tag("blue")
    static class Base {
        @Label("field")
        public String id;

        @Label("method")
        public @NonBlank String read(@Label("argument") String input) {
            return input;
        }
    }

    static class Child extends Base {
    }

    public static void main(String[] args) throws NoSuchMethodException,
            NoSuchFieldException {
        AnnotatedElement element = Base.class;
        System.out.println("base label: "
                + element.getAnnotation(Label.class).value());

        System.out.println("child role: "
                + Child.class.getAnnotation(Role.class).value());
        System.out.println("child declared role: "
                + (Child.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("child label: "
                + (Child.class.getAnnotation(Label.class) != null));

        Tag[] tags = Base.class.getAnnotationsByType(Tag.class);
        System.out.println("expanded tags: " + tags.length);
        System.out.println("single tag lookup: "
                + (Base.class.getAnnotation(Tag.class) != null));
        System.out.println("container present: "
                + (Base.class.getDeclaredAnnotation(Tags.class) != null));

        Method method = Base.class.getDeclaredMethod("read", String.class);
        Field field = Base.class.getDeclaredField("id");
        Parameter parameter = method.getParameters()[0];

        System.out.println("method label: "
                + method.getAnnotation(Label.class).value());
        System.out.println("field label: "
                + field.getAnnotation(Label.class).value());
        System.out.println("parameter label: "
                + parameter.getAnnotation(Label.class).value());

        System.out.println("return type-use annotation: "
                + method.getAnnotatedReturnType()
                        .isAnnotationPresent(NonBlank.class));
        System.out.println("method declaration has NonBlank: "
                + method.isAnnotationPresent(NonBlank.class));

        System.out.println("label retention: "
                + Label.class.getAnnotation(Retention.class).value());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AnnotatedElementDemo.java
java AnnotatedElementDemo
```

Expected stdout:

```text
base label: base
child role: reader
child declared role: false
child label: false
expanded tags: 2
single tag lookup: false
container present: true
method label: method
field label: field
parameter label: argument
return type-use annotation: true
method declaration has NonBlank: false
label retention: RUNTIME
```

Explanation:

1. `Base.class` has `@Label("base")`, so it can be assigned to a variable of type `AnnotatedElement` and have `getAnnotation(Label.class)` called on it.
2. `Role` has `@Inherited` and is attached to `Base`. `Child.class.getAnnotation(Role.class)` receives the role metadata from the superclass; `Child.class.getDeclaredAnnotation(Role.class)` returns `null` because `Child` does not declare it directly.
3. `Label` does not have `@Inherited`. Therefore, `Child.class.getAnnotation(Label.class)` is `null` even though `Base` carries that label.
4. The two `@Tag` annotations are repeatable. The compiler stores them via the `@Tags` container; `getAnnotationsByType(Tag.class)` unpacks the container into two elements, whereas `getAnnotation(Tag.class)` does not automatically unpack the container in the same way.
5. `Method`, `Field`, and `Parameter` are all `AnnotatedElement`. Each object provides annotations on the exact declaration it represents.
6. `getAnnotatedReturnType()` returns an `AnnotatedType` object that can carry `@NonBlank`, whereas the `Method` declaration itself does not carry the `NonBlank` declaration annotation.
7. The annotation type `Label.class` is also a `Class`, so Reflection can query the `@Retention` meta-annotation on the annotation type itself; the result is the enum `RUNTIME`.

The program uses `getParameters()` to obtain the `Parameter` object. **The `javac -parameters` option is not required just to read parameter annotations**; that option primarily stores source parameter names so that `Parameter.getName()` can display the declared name instead of a synthesized name.

## 5. Distinguishing getAnnotation and getDeclaredAnnotation

`getAnnotation(T.class)` and `getDeclaredAnnotation(T.class)` differ when there is **an inherited annotation on a class**:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("base")
class BaseType {
}

class DerivedType extends BaseType {
}
```

This is a declaration example requiring `import java.lang.annotation.*`, without `main`.

Result:

```java
Category inherited = DerivedType.class.getAnnotation(Category.class);
Category direct = DerivedType.class.getDeclaredAnnotation(Category.class);

System.out.println(inherited.value()); // base
System.out.println(direct == null);      // true
```

This code only runs when placed inside a method that can access the declared types. `@Inherited` does **not** mean methods, fields, or interfaces always pass annotations down to corresponding elements in a subclass:

- `@Inherited` only affects the annotation inheritance mechanism **when the inspected element is a class**, along the superclass chain.
- Annotations on an interface are not “inherited” by an implementing class via `@Inherited`.
- An overriding method does not automatically receive annotations from the overridden method. If a tool needs to fall back to a superclass method, it must design the lookup step by signature itself.
- A field hiding another field is also not automatically assigned the superclass field's annotations.

If a subclass has an annotation of the same type declared directly, that annotation wins over the inheritance path for that annotation type; direct and inherited declarations are not arbitrarily combined in the single-annotation lookup API.

## 6. getAnnotations / getDeclaredAnnotations: which set is returned?

`getAnnotations()` returns “present” annotations; `getDeclaredAnnotations()` returns only “directly present” annotations. The two arrays can differ when a class inherits an annotation marked with `@Inherited`.

In the program in section 4, `Child.class.getAnnotations()` sees the inherited `Role`; `Child.class.getDeclaredAnnotations()` does not contain `Role`.

If an annotation type is repeatable, multiple occurrences may be encoded as a **container annotation**; in that case, `getAnnotations()` or `getDeclaredAnnotations()` may give you the **container** rather than each individual component annotation. Therefore, when you want to read all `@Tag` annotations, use `getAnnotationsByType(Tag.class)` instead of casting the `getAnnotations()` array to `Tag[]`.

Do not rely on the order of the `getAnnotations()` array as a core part of general logic. When generating reports or building a UI, sort/identify by annotation type and meaningful attributes rather than depending on incidental order.

## 7. Repeatable annotations and the two ByType variants

An annotation is repeatable when declared with `@Repeatable(Container.class)` and having a valid container:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Flags {
    Flag[] value();
}
```

This is a standalone snippet of annotation type declarations, requiring `import java.lang.annotation.*`. Usage example:

```java
@Flag("fast")
@Flag("verified")
class Task {
}
```

Distinction:

| API | Meaning |
| --- | --- |
| `getAnnotation(Flag.class)` | Finds one “present” `Flag`; does not automatically unpack the container to return two `Flag`s |
| `getDeclaredAnnotation(Flag.class)` | Finds one directly present `Flag`; does not automatically unpack the container |
| `getAnnotationsByType(Flag.class)` | Retrieves “associated” `Flag`s, unpacking the container and applying inheritance if conditions are met |
| `getDeclaredAnnotationsByType(Flag.class)` | Retrieves `Flag` directly or indirectly via the container **on the element itself**, without searching superclasses |

Both `Task.class.getAnnotationsByType(Flag.class)` and `Task.class.getDeclaredAnnotationsByType(Flag.class)` yield two elements in the example because both are declared on `Task` itself.

If you want a repeatable annotation to **also be inherited** from a superclass, you must design `@Inherited` compatibility for both the component annotation and the container according to Java requirements, and then consider the “associated” rules. Do not simply assume that when a subclass adds an annotation of the same type, the ByType result automatically merges all annotations from the superclass: an annotation directly or indirectly present on the subclass can **shadow the result from the superclass** for the same annotation type.

## 8. Declaration annotations differ from type-use annotations

This is the easiest point to confuse because both are accessed through `AnnotatedElement`.

### Declaration annotations

An annotation with target `METHOD`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Logged {
}
```

attaches to the method declaration:

```java
@Logged
public String find() {
    return "found";
}
```

These are illustrative snippets that must be placed in an appropriate class context. To read it, obtain the `Method` and call `method.isAnnotationPresent(Logged.class)`.

### Type-use annotations

An annotation with target `TYPE_USE`:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ImportantType {
}
```

can attach to a return type, field type, parameter type, generic type argument, array component, wildcard, or superclass/interface use depending on valid syntax.

| Location | Appropriate API |
| --- | --- |
| Method return type | `Method.getAnnotatedReturnType()` |
| Field type | `Field.getAnnotatedType()` |
| Formal parameter type | `Executable.getAnnotatedParameterTypes()` |
| Declared throws type | `Executable.getAnnotatedExceptionTypes()` |
| Superclass type | `Class.getAnnotatedSuperclass()` |
| Interface types | `Class.getAnnotatedInterfaces()` |
| Parameterized type and type arguments | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` |
| Annotated array type | `AnnotatedArrayType.getAnnotatedGenericComponentType()` |
| Annotated wildcard bounds | `AnnotatedWildcardType.getAnnotatedLowerBounds()` / `getAnnotatedUpperBounds()` |

For example, `List<@ImportantType String>` does not mean the entire `Field` declaration is marked with `@ImportantType`. To find the annotation on the **type argument `String`**, you need to start from `field.getAnnotatedType()`, check `AnnotatedParameterizedType`, and then read the element `getAnnotatedActualTypeArguments()[0]`. Simply calling `field.getAnnotation(ImportantType.class)` is querying the wrong location.

The difference also appears on type parameter declarations such as `class Box<@Tag T>` if `Tag` allows `TYPE_PARAMETER`. In that case, the annotation can be read from `TypeVariable<?>` or the appropriate type-use position according to metadata; do not call `Box.class.getAnnotation(Tag.class)` and expect it to be a class annotation.

## 9. Package, Module, RecordComponent, and annotations in other locations

### Package

Package annotations are typically declared in the `package-info.java` file:

```java
@com.example.annotations.PublicPackage
package com.example.domain;
```

This is a **structure-describing** example; the annotation type must exist and have `@Target(PACKAGE)` and `@Retention(RUNTIME)` to be observed at runtime via `Package`. In a program that has a class belonging to the package:

```java
Package p = SomeDomainClass.class.getPackage();
boolean present = p.isAnnotationPresent(PublicPackage.class);
```

This is a snippet, not a standalone program. `getPackage()` may need null/class-loader handling when writing general-purpose tools, and you should not look for package annotations by retrieving annotations on an arbitrary class in the package.

### Module

`java.lang.Module` implements `AnnotatedElement`. Annotations with target `MODULE` can be placed on a module declaration in `module-info.java` (following syntax rules). For example, `SomeClass.class.getModule().getAnnotations()` reads annotations of the module, **not** of the class.

### Record component

`RecordComponent` (Java 16+) is a Reflection object from `Class.getRecordComponents()`. It represents a **record component**, distinct from the backing field, accessor method, or constructor parameter even though the compiler generates the related members. If you want to inspect annotations on a record component, choose the exact `RecordComponent` and specify `@Target(RECORD_COMPONENT)`. Java also has rules for propagating valid annotations onto elements derived from a record component; tools should not assume that the results when reading the field, accessor, constructor parameter, and record component will always be identical.

## 10. Annotation objects and internal attributes

Once an annotation is obtained:

```java
Label label = Base.class.getAnnotation(Label.class);
String value = label.value();
Class<? extends Annotation> annotationType = label.annotationType();
```

This is a snippet using `Label`/`Base` from the example in section 4 and importing `java.lang.annotation.Annotation`. An annotation instance implements the corresponding annotation interface, so elements like `value()` are invoked as attribute-reading methods.

The `Annotation` API also has `annotationType()`, `equals(...)`, `hashCode()`, and `toString()`. Do not rely on the runtime class name implementing the annotation; implementations may use proxies or internal JDK details. Rely on the annotation interface and the documented attribute values.

An annotation attribute can be a primitive, String, Class, enum, annotation, or an array of valid types. If class files or libraries change out of sync, reading an attribute can encounter metadata errors such as `TypeNotPresentException`, `EnumConstantNotPresentException`, `AnnotationTypeMismatchException`, `IncompleteAnnotationException`, or `AnnotationFormatError` depending on the cause. Tools processing third-party plugins/class files should have proper diagnostic paths rather than assuming every annotation always has a well-formed structure.

## 11. Workflow for targeting annotation discovery accurately

When developing a framework/validator/documentation generator:

1. **Choose the element:** class, method, constructor, field, parameter, package, module, record component, or type-use. This is the most important step.
2. **Verify retention:** the annotation type you want to read must have `@Retention(RUNTIME)`; if the metadata is not runtime-visible, Reflection will not see it as expected.
3. **Choose the scope:** `getDeclaredAnnotation(s)` if considering only direct annotations; `getAnnotation(s)` if you want “present” semantics and accept class inheritance where applicable.
4. **Choose cardinality:** for repeatable annotations, use `getAnnotationsByType` or `getDeclaredAnnotationsByType` to read the elements inside the container.
5. **Check declaration vs. type-use:** a method annotation lives on `Method`, while a return type annotation lives on `Method.getAnnotatedReturnType()`.
6. **Consider inheritance structure:** an overriding method does not automatically inherit the parent method's annotations; write a hierarchy-scanning policy if the framework requires it.
7. **Distinguish metadata from execution access:** reading annotations does not automatically grant permission to invoke private methods, modify fields, or bypass JPMS access rules.
8. **Read attributes safely:** note that an annotation may be missing at runtime, present only at a different location, or have an incompatible class file structure.
9. **Test across multiple element kinds:** test at least direct annotations, non-inherited annotations, repeatable containers, method/parameter annotations, and type-use annotations.

## 12. Common mistakes

| Misconception | Correct understanding |
| --- | --- |
| Every annotation in source code can be read via Reflection | Only annotations retained at runtime and at the matching location are visible through the API |
| `@Retention` defaults to RUNTIME | The default is CLASS |
| `Class<?>` is the only type supporting `AnnotatedElement` | `Method`, `Field`, `Constructor`, `Parameter`, `Package`, `Module`, `RecordComponent`, `AnnotatedType`, etc. also support it |
| `getAnnotations()` and `getDeclaredAnnotations()` are always identical | A class can inherit an `@Inherited` annotation without declaring it directly |
| `@Inherited` works on method overrides | It applies only to class annotation inheritance rules via superclasses |
| `getAnnotation(Tag.class)` returns all repeatable tags | Use `getAnnotationsByType(Tag.class)` to unpack the container |
| A subclass automatically merges repeatable annotations from its parent | The “associated” rule is not simply concatenating all levels; annotations on the subclass can shadow the parent's result |
| An annotation on the return type is on the Method declaration | You must read `method.getAnnotatedReturnType()` |
| Parameter annotations require `javac -parameters` | That option is mainly for parameter names; runtime parameter annotations have their own API |
| Annotations on a superclass method automatically appear when a subclass overrides it | An overriding method is a new declaration; a hierarchy lookup policy is needed if business logic requires it |
| Being able to read a private method's annotations means having permission to invoke it | Metadata readability and method invocation accessibility are two separate questions |
| Any `AnnotatedElement` object can be cast to `Class<?>` | Different metadata types implement the same interface; use `instanceof` or a common contract |

## 13. Self-check

1. **Why does `Child.class.getAnnotation(Role.class)` see `Role` while `getDeclaredAnnotation(Role.class)` does not?** Because `Role` has `@Inherited` on `Base` and `Child` does not declare it itself.
2. **If an annotation type uses `@Retention(CLASS)`, can `getAnnotation(...)` on a running class read it reliably?** No. That metadata is not runtime-visible via standard Reflection.
3. **Do two `@Tag` annotations on the same class return one element from `getAnnotation(Tag.class)`?** No; repeatable annotations are normally stored via a container and must be read with `getAnnotationsByType(Tag.class)`.
4. **Can `Field` and `Method` be stored in the same `AnnotatedElement` interface variable?** Yes. Both implement the interface.
5. **Where must an `@NonBlank` annotation attached to the return type `String` be read?** `method.getAnnotatedReturnType()`, not directly as a `Method` declaration annotation.
6. **What must be done to find an annotation on the type `String` in `List<@X String>`?** Traverse `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` from the annotated type of the element containing that type.
7. **An overriding method does not carry `@Label` from the superclass method; what should be done if a framework wants fallback behavior?** Walk the method hierarchy by signature with an explicit policy; do not assume `@Inherited` applies to methods.
8. **Why does reading `Parameter.getAnnotation(...)` not require parameter names in the class file?** Because parameter annotation metadata is stored and read separately from storing source names via `-parameters`.
9. **Is it allowed to use `getAnnotation(...)` as a way to bypass access restrictions for calling non-public methods?** No. Annotation metadata does not alter Reflection or module access permissions.

**Key takeaway:** `AnnotatedElement` is the unified interface for **reading annotations of the right element**. Pick the right object (declaration or type-use), verify runtime retention, distinguish direct vs. inherited annotations, and use the `ByType` APIs for repeatable annotations to avoid missing metadata.

### Official references

- [Java SE 17 — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 17 — Executable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [Java SE 17 — RecordComponent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Java Language Specification — Annotation interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6)