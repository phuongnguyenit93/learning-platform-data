# RECORD_COMPONENT and Record Annotation Propagation Rules in Java

## 1. A Record Component Can Relate to Multiple Annotation Locations

Since Java 16, `record` is a kind of class dedicated to representing a fixed group of data. In Java 17+, the following declaration has a **record component** named `name`:

```java
record Person(String name) {}
```

A record component appears in the **header** of the record, inside the parentheses of `record Person(...)`. It is a distinct language-model element, rather than simply shorthand syntax for a field.

For the example above, Java also has the following related declarations:

- **Component** `name`: describes the data component of the record, accessed via `Class.getRecordComponents()`.
- **Component field** `private final String name`: implicitly declared by the compiler.
- **Accessor** `public String name()`: implicitly declared if the developer does not write it manually.
- **Canonical constructor** `Person(String name)`: has parameters corresponding to each component, either implicitly declared by the compiler or explicitly declared by the developer.

These are distinct locations. When writing `@Mark String name` in the record header, the annotation can appear at **one or more related locations** depending on that annotation's `@Target`.

For example:

```java
record Person(@SomeAnnotation String name) {}
```

You cannot assume by default that `@SomeAnnotation` is attached only to the component, or that it is guaranteed to appear on all of the field, accessor, and constructor parameter. That depends on **which `ElementType`s are permitted** and **whether the member is declared implicitly or explicitly**.

## 2. What Is `ElementType.RECORD_COMPONENT`?

`java.lang.annotation.ElementType.RECORD_COMPONENT` is an enum constant indicating a **record component declaration**. To make an annotation present directly on the record component, declare `@Target(ElementType.RECORD_COMPONENT)` or include this value in the target list:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentInfo {
    String value();
}

record Customer(@ComponentInfo("customer-id") String id) {}
```

When reading via reflection:

```java
var component = Customer.class.getRecordComponents()[0];
ComponentInfo info = component.getAnnotation(ComponentInfo.class);
System.out.println(info.value()); // customer-id
```

This reflection snippet **depends on two conditions**:

1. `@Target(RECORD_COMPONENT)` allows the annotation to be recorded on the record component itself.
2. `@Retention(RUNTIME)` allows the reflection API to read the annotation at runtime.

`@Target` answers **where it is allowed to be attached**; `@Retention` answers **up to which stage the metadata is retained**. If `@Retention` is not declared, the default is `RetentionPolicy.CLASS`; the annotation may still be written by the compiler into the class file, but it will not be visible through the reflection APIs mentioned above.

**Note:** `RECORD_COMPONENT` is not a name for every field generated from a record. `ElementType.FIELD`, `METHOD`, `PARAMETER`, and `TYPE_USE` still have their own distinct meanings.

## 3. Annotation Propagation Rules Table

Suppose we have `record Example(@A String value) {}` and `@A` is declared with `@Retention(RUNTIME)`. Depending on the target set, Java handles it as follows:

| Permitted `ElementType` | Where does the annotation appear? | How to observe |
|---|---|---|
| `RECORD_COMPONENT` | The record component itself | `RecordComponent.getAnnotation(A.class)` |
| `FIELD` | Implicitly declared component field | `getDeclaredField("value").getAnnotation(A.class)` |
| `METHOD` | **Implicitly declared accessor** `value()` | `getMethod("value").getAnnotation(A.class)` |
| `PARAMETER` | **Derived** parameter of the implicit canonical constructor or compact constructor | `getDeclaredConstructor(String.class).getParameters()[0].getAnnotation(A.class)` |
| `TYPE_USE` | Corresponding type-use locations: component type, field type, implicit accessor return type, derived parameter type | `getAnnotatedType()` at the exact location |

An annotation can declare **multiple targets**; the same annotation in the header will be present in multiple places **when the rules allow**. For example:

```java
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@Retention(RetentionPolicy.RUNTIME)
@interface AuditName {
    String value();
}

record User(@AuditName("user-name") String name) {}
```

In the simple record `User`, `@AuditName` can be found via reflection on the record component, the component field, the implicit accessor, and the parameter of the implicit canonical constructor. This is a **propagation rule applied when the compiler processes the record declaration**; it is not the runtime automatically copying annotations after the class has been loaded.

If an annotation only has `@Target(FIELD)`, placing it in the record header can still be valid because that declaration corresponds to the component field receiving the annotation. However, `RecordComponent.getAnnotation(...)` **does not** see an annotation that only targets `FIELD`. You need to query the field itself. Similarly, an annotation that only targets `METHOD` or `PARAMETER` does not automatically become a direct annotation on `RecordComponent`.

### 3.1. Why Does the Compiler Have a Propagation Mechanism?

The record header is the source declaring the components of the record. From it, the compiler derives the appropriate field, accessor, and canonical constructor. An annotation can define semantics for multiple locations; for example, a library may need to mark both the field and the accessor. The propagation mechanism allows **placing the annotation in the header once** if the target and specific declaration form satisfy the rules.

This does not mean all annotations are copied. Java intentionally selects locations based on `@Target`; declarations written explicitly by the developer have exceptions that need to be understood carefully in the following sections.

## 4. Complete Java 17+ Example: Observing Each Location via Reflection

Create a file named **Main.java** with the following content. The example uses multiple independent annotations to clearly distinguish each target:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.RecordComponent;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface Track {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParamOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {}

record Entry(
        @Track("id")
        @ComponentOnly
        @FieldOnly
        @MethodOnly
        @ParamOnly
        @TypeTag String id
) {}

record CustomAccessor(@Track("id") String id) {
    public String id() {
        return id;
    }
}

record CompactCtor(@Track("id") String id) {
    public CompactCtor {
        if (id == null) {
            throw new IllegalArgumentException();
        }
    }
}

record ExplicitCtor(@Track("id") String id) {
    public ExplicitCtor(String id) {
        this.id = id;
    }
}

public class Main {
    public static void main(String[] args) throws Exception {
        RecordComponent component = Entry.class.getRecordComponents()[0];

        System.out.println("recordTrack="
                + component.isAnnotationPresent(Track.class));
        System.out.println("componentOnly="
                + component.isAnnotationPresent(ComponentOnly.class));
        System.out.println("fieldOnlyOnComponent="
                + component.isAnnotationPresent(FieldOnly.class));
        System.out.println("fieldOnlyOnField="
                + Entry.class.getDeclaredField("id")
                        .isAnnotationPresent(FieldOnly.class));
        System.out.println("methodOnlyOnAccessor="
                + Entry.class.getMethod("id")
                        .isAnnotationPresent(MethodOnly.class));
        System.out.println("paramOnlyOnCtor="
                + Entry.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].isAnnotationPresent(ParamOnly.class));

        System.out.println("typeUseOnComponentType="
                + component.getAnnotatedType().isAnnotationPresent(TypeTag.class));
        System.out.println("typeUseOnFieldType="
                + Entry.class.getDeclaredField("id")
                        .getAnnotatedType().isAnnotationPresent(TypeTag.class));
        System.out.println("typeUseOnAccessorReturn="
                + Entry.class.getMethod("id")
                        .getAnnotatedReturnType().isAnnotationPresent(TypeTag.class));
        System.out.println("typeUseOnParameterType="
                + Entry.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].getAnnotatedType()
                        .isAnnotationPresent(TypeTag.class));

        System.out.println("customAccessorTrack="
                + CustomAccessor.class.getMethod("id")
                        .isAnnotationPresent(Track.class));
        System.out.println("compactCtorParamTrack="
                + CompactCtor.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].isAnnotationPresent(Track.class));
        System.out.println("explicitCtorParamTrack="
                + ExplicitCtor.class.getDeclaredConstructor(String.class)
                        .getParameters()[0].isAnnotationPresent(Track.class));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Exact output on Java 17+:

```text
recordTrack=true
componentOnly=true
fieldOnlyOnComponent=false
fieldOnlyOnField=true
methodOnlyOnAccessor=true
paramOnlyOnCtor=true
typeUseOnComponentType=true
typeUseOnFieldType=true
typeUseOnAccessorReturn=true
typeUseOnParameterType=true
customAccessorTrack=false
compactCtorParamTrack=true
explicitCtorParamTrack=false
```

**How to read the output:**

- `recordTrack=true`: `Track` has `RECORD_COMPONENT`, so it appears on the component.
- `componentOnly=true`: `ComponentOnly` is attached directly to the component.
- `fieldOnlyOnComponent=false`, while `fieldOnlyOnField=true`: an annotation with the `FIELD` target **does not** turn into a direct annotation on `RecordComponent`.
- `methodOnlyOnAccessor=true`: the implicit accessor `id()` carries annotations allowing `METHOD`.
- `paramOnlyOnCtor=true`: the derived parameter of the implicit canonical constructor carries annotations allowing `PARAMETER`.
- The four `typeUse...` lines show that `TYPE_USE` relates to **the type at each location**, not declaration annotations in all places.
- The last three lines illustrate **the exception for explicitly declared members/constructors**. These exceptions are an important part of the rule, not a reflection bug.

The code uses `@Retention(RUNTIME)` so that the results can be observed via reflection. Propagation from the header to the related declarations occurs during compilation, regardless of whether reflection is executed or not.

## 5. Exception 1: Explicitly Written Accessors Do Not Automatically Receive Annotations

Each component has a parameterless accessor with the same name. If no method is written, the compiler declares an implicit accessor and propagates annotations compatible with `METHOD` or `TYPE_USE`.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Readable {}

record AutoAccessor(@Readable String name) {}
```

Here, `AutoAccessor.name()` is declared **implicitly**. With runtime retention, `getMethod("name").isAnnotationPresent(Readable.class)` returns `true`.

Conversely:

```java
record ManualAccessor(@Readable String name) {
    public String name() {
        return name;
    }
}
```

Because `name()` is declared **explicitly** by the developer, the record component's annotation **does not propagate** to this accessor's declaration. If metadata is needed on the accessor, it must be annotated **directly on the method**:

```java
record ManualAccessorFixed(@Readable String name) {
    @Readable
    public String name() {
        return name;
    }
}
```

The two annotations in the final example sit at two locations with different roles: the annotation in the header is the metadata source for the component and its corresponding permitted locations; the annotation on the method is metadata for the explicitly written accessor.

**Note on `TYPE_USE`:** the rule for explicit accessors also applies when an annotation is needed on the **return type** of the accessor. Do not infer that the return type of a manually written method is guaranteed to have the same type-use annotations as the record component type in the header. You need to declare the annotation at the appropriate type-use position of that method.

## 6. Exception 2: Fully Declared Canonical Constructors

A record has a **canonical constructor** taking one parameter for each component with the exact corresponding name and type. If the compiler generates the constructor automatically, the parameters are derived from the header, carrying annotations with compatible `PARAMETER` or `TYPE_USE` targets.

However, with a **normal canonical constructor** written in full, the developer declares the constructor parameters and explicitly decides the annotations on those parameters:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Input {}

record AutoCtor(@Input String name) {}

record ManualCtor(@Input String name) {
    public ManualCtor(String name) {
        this.name = name;
    }
}
```

- `AutoCtor`: the parameter of the implicit canonical constructor has `@Input`.
- `ManualCtor`: the parameter `String name` in the fully written constructor **does not automatically receive** `@Input` from the header.

If the annotation is needed on the fully written parameter, place it directly on the parameter:

```java
record ManualCtorFixed(@Input String name) {
    public ManualCtorFixed(@Input String name) {
        this.name = name;
    }
}
```

This still holds even if the annotation in the header also includes `RECORD_COMPONENT`, `FIELD`, and `METHOD`: `@Target` allows multiple locations, but it **does not remove the exception for an explicitly declared normal canonical constructor**. Writing an annotation on the constructor parameter also does not automatically update the record component in reverse.

### 6.1. Special Case: Compact Constructor

A compact constructor has the syntax:

```java
record Compact(@Input String name) {
    public Compact {
        if (name == null) {
            throw new IllegalArgumentException("name");
        }
    }
}
```

The `public Compact { ... }` part **does not declare a parameter list**. The compiler derives the parameters from the record header, so the `@Input` annotation with target `PARAMETER` **is still propagated** to the parameter of the compact canonical constructor. That is why the complete example outputs `compactCtorParamTrack=true` while `explicitCtorParamTrack=false`.

A compact constructor also does not require manually assigning fields in its body; after the body completes normally, the compiler assigns the component fields from the corresponding parameters. In the example above, the body only validates `name`.

## 7. How Does `TYPE_USE` Differ from `RECORD_COMPONENT`?

`ElementType.RECORD_COMPONENT` targets the **component declaration**. `ElementType.TYPE_USE` targets a **type-use location**, such as the `String` type in `record R(String value)`, the field type, the accessor return type, or the derived parameter type.

For example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NotEmptyType {}

record Message(@NotEmptyType String text) {}
```

To read the annotation on the **type** of the component:

```java
boolean found = Message.class.getRecordComponents()[0]
        .getAnnotatedType()
        .isAnnotationPresent(NotEmptyType.class);
```

If `NotEmptyType` only has `TYPE_USE`, calling `getAnnotation(NotEmptyType.class)` **directly on the RecordComponent declaration** does not necessarily yield a value; the tested example yields `false` on the declaration when only the `TYPE_USE` target is present, whereas `getAnnotatedType()` yields `true`.

For annotations targeting `TYPE_USE`, inspecting the type-use annotations of the related members requires using the corresponding API:

```java
// Individual lines illustrating the reflection API, not a standalone Main.java:
Message.class.getDeclaredField("text").getAnnotatedType();
Message.class.getMethod("text").getAnnotatedReturnType();
Message.class.getDeclaredConstructor(String.class)
        .getParameters()[0].getAnnotatedType();
```

A record can have complex types, such as `List<@NotEmptyType String>`. In that case, the annotation targets the **type argument String**; to inspect it, you must traverse the `AnnotatedType` tree and `AnnotatedParameterizedType` instances, rather than querying only the annotation of the outer type `List`.

Important: Java allows **multiple different annotation layers** on the same component: declaration annotations attached to the component and type-use annotations attached to the component's type. Be sure to analyze the exact layer of metadata you need.

## 8. Annotation Propagation Does Not Mean Automatic Validation

Suppose a library defines an annotation for validation:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.PARAMETER
})
@interface Required {}

record Request(@Required String token) {}
```

Java will store the annotation on the permitted declarations corresponding to the record. **However, the annotation itself does not check `token != null`**. The propagation rules only govern metadata; for validation to take effect, there must be code or a framework that actively reads the annotation and performs the check.

In addition, a framework reading **field annotations** does not mean it reads **record-component annotations**. For example:

- Code using `RecordComponent.getAnnotation(Required.class)` observes the `RECORD_COMPONENT` target.
- Code using `Field.getAnnotation(Required.class)` observes the `FIELD` target on the component field.
- Code using `Parameter.getAnnotation(Required.class)` observes constructor parameters that have the annotation; for a fully declared constructor, you must check whether the annotation has been re-declared there.
- Code using `Method.getAnnotation(Required.class)` requires `METHOD` in the target and an appropriate accessor or an annotation written directly on an explicit accessor.

If a library scans multiple locations, the same annotation can appear in multiple places; the library itself is responsible for avoiding duplicate processing when that is inappropriate. Do not assume an annotation runs automatically just because `@Target` contains multiple locations.

## 9. Common Mistakes When Working with Annotations on Records

### 9.1. Declaring Only `@Target(RECORD_COMPONENT)` and Expecting to See the Annotation on the Field

```java
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentTag {}

record Item(@ComponentTag String id) {}
```

`ComponentTag` only targets the component. If the logic uses `getDeclaredField("id").getAnnotation(ComponentTag.class)`, not finding the annotation is **according to contract**. To make it appear on the field, the annotation type must allow `FIELD`; at the same time, appropriate retention is needed if you want to observe it via reflection.

### 9.2. Looking Only at `RecordComponent.getAnnotations()` and Concluding All Annotations Are Missing

An annotation with `@Target(FIELD)` or `@Target(TYPE_USE)` can be valid on the record header, yet it is observed on the corresponding field or annotated type. Each reflection object's `getAnnotations()` API reflects only **the exact location** of that object.

### 9.3. Thinking `@Retention(RUNTIME)` Causes Propagation

Retention indicates whether an annotation is preserved for use at runtime. Propagation from the record header to related declarations is governed by the Java language/compiler. Retention **does not replace** target and **does not cause explicitly written accessors or constructors to automatically receive annotations**.

### 9.4. Failing to Re-check Where Annotations Appear After Refactoring an Accessor or Constructor

Replacing an implicit accessor with an explicit accessor can cause annotations targeting `METHOD` to no longer appear on the accessor. Replacing an implicit canonical constructor with a fully written normal canonical constructor can cause annotations targeting `PARAMETER` to no longer appear on the parameter. You need to re-examine metadata at the location where the framework reads it, and explicitly write annotations where necessary.

### 9.5. Confusing It with `@Inherited`

`@Inherited` relates to a **class-level annotation** being queried along the superclass chain according to its rules. A record component is not a class inheritance mechanism; `@Inherited` is not a solution for propagating metadata from a component to a field, method, or parameter.

### 9.6. Placing an Annotation with an Incompatible Target

`@Target(ElementType.TYPE)` only applies to type declarations such as a class/interface/record **as a whole**, and does not allow placing that annotation before a **component name**. Similarly, without `@Target(RECORD_COMPONENT)` or an appropriate related target, you should not assume the annotation can be placed on the header. The compiler will check for valid target applicability.

## 10. Checklist When Designing and Using Annotations for Records

1. **Identify the exact object from which metadata is read.** Are you reading `RecordComponent`, `Field`, `Method`, `Parameter`, or `AnnotatedType`? Each one is different.
2. **Declare `@Target` according to actual needs.** Use only `RECORD_COMPONENT` if it is strictly component metadata; add `FIELD`, `METHOD`, `PARAMETER`, or `TYPE_USE` if consumers genuinely need them.
3. **Choose the right retention.** If runtime reflection reads the annotation, use `RUNTIME`; if it is only needed for build-time processing, consider `SOURCE` or `CLASS` accordingly.
4. **Check explicitly written members.** Manually written accessors and manually written normal canonical constructors do not receive all annotations from the header the way derived members do.
5. **Check compact constructors.** Compact constructor parameters are derived, so compatible metadata targeting `PARAMETER` can be propagated.
6. **Write tests using reflection or test the annotation processor** against the exact surface that consuming code reads. Do not infer behavior just by looking at the `record` syntax.
7. **Avoid duplicate processing.** If the same annotation appears in multiple places, the consumer must clearly define its semantics and precedence order.

## 11. Official References and Conclusion

- [Java SE 17 JLS §8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): components in the header and their relationship to record members.
- [Java SE 17 JLS §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): component fields, implicit accessors, and the exception for explicitly declared accessors.
- [Java SE 17 JLS §8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): implicit constructors, normal canonical constructors, compact constructors, and derived parameter lists.
- [Java SE 17 JLS §9.6.4.1 — `@Target`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): the declaration/type contexts in which an annotation is permitted to be used.
- [Java SE 17 API — `RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): how to read annotations and annotated types of a component via reflection.

**Key takeaway:** `RECORD_COMPONENT` is a distinct annotation target. An annotation placed in a record header can propagate to **the field, the implicit accessor, the derived parameter of the canonical constructor, and type-uses** if `@Target` allows it. **Explicitly written accessors** and **fully declared normal canonical constructors** require their own metadata at those respective locations. Only by reading annotations at the right location and checking the proper retention can you know what information actually exists in the program.
