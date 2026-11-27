# Annotations on Record Components and Related Members in Java 17

**Topic:** Java 17  
**Chapter:** Record  
**Lesson:** Annotations on components and related members

When declaring a `record`, the elements (*record components*) inside the parentheses do more than describe data. They also determine the members Java generates: a `private final` field for each component, an accessor, and the corresponding parameters of the canonical constructor. Notably, **an annotation written on a record component can appear in multiple places** — depending on the annotation's `@Target` and how the record declares its members.

In Java 17, distinguish clearly between:

- **Record component** in the header, e.g., `name` in `record User(String name) {}`.
- **Component field** implicitly declared by the compiler: `private final String name`.
- **Accessor** corresponding to it: `public String name()`.
- **Canonical constructor parameter**: the `name` parameter in `User(String name)`.
- **Type-use position (type use)**: the type `String` itself in `@Marker String name`, distinct from an annotation on the component declaration.

This is behavior specified by the Java Language Specification (JLS), not a framework manually "copying annotations." A framework can inspect those locations via reflection or annotation processing and handle them according to its own conventions.

> **Version Milestone:** `record` was standardized in Java 16 (JEP 395) and is a stable feature enabled by default in Java 17. The examples below use only stable Java 17 APIs and syntax, without needing preview enabled.

## 1. From Record Components to Record Members

Look at a basic declaration:

```java
record User(long id, String name) {}
```

Conceptually, each component corresponds to the following members:

```text
record User(long id, String name) {}
            │           │
            │           └── component: name
            └────────────── component: id

Each component corresponds to:
  ├── component field: private final ...
  ├── accessor: public ... name()
  └── formal parameter in canonical constructor

The record also gets equals(Object), hashCode(), toString(),
and a canonical constructor.
```

For instance, you can approximate the members provided by the compiler when none are declared explicitly:

```java
// STRUCTURAL ILLUSTRATION ONLY; not a complete equivalent replacement for a record.
final class UserLike {
    private final long id;
    private final String name;

    UserLike(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long id() {
        return id;
    }

    public String name() {
        return name;
    }

    // equals, hashCode, toString are also generated per record rules.
}
```

Record syntax carries richer declarative meaning than the regular class example: a record class inherits `java.lang.Record`, is implicitly `final`, and has specific rules for constructors, components, and members. The `UserLike` example merely helps visualize the locations capable of holding annotations.

**Core focus:** A component **is not identical** to a field. Reflection provides a separate type, `java.lang.reflect.RecordComponent`. An annotation in the header can serve as a component declaration annotation, or propagate to the field, accessor, parameter, or type — strictly according to its permitted targets.

## 2. `@Target` Determines Where an Annotation Belongs

The `@Target` meta-annotation from `java.lang.annotation` declares which Java program elements an annotation may apply to.

For records, the particularly important values are:

| `ElementType` | Corresponding Location | Example Where a Framework May Read It |
|---|---|---|
| `RECORD_COMPONENT` | The record component itself in the header | `RecordComponent.getAnnotation(...)` |
| `FIELD` | The implicitly declared `private final` component field | `Class.getDeclaredField(...).getAnnotation(...)` |
| `METHOD` | The **implicitly declared** accessor | `RecordComponent.getAccessor().getAnnotation(...)` |
| `PARAMETER` | The derived parameter of an **implicit or compact** canonical constructor | `Constructor.getParameters()[i].getAnnotation(...)` |
| `TYPE_USE` | Annotations placed on the **used type** of the component and related declarations | `getAnnotatedType()`, `getAnnotatedReturnType()`, `Parameter.getAnnotatedType()` |

The first four entries deal primarily with **declaration annotations**. `TYPE_USE` deals with **type annotations**, which must be read through the reflection APIs for annotated types.

Example defining an annotation usable in multiple places:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface Label {
    String value();
}
```

When applied:

```java
record Product(@Label("product-code") String code) {}
```

Because `Label` applies to **all four declaration contexts**, this annotation can be observed on the component, the field, the implicitly generated accessor, and the implicitly generated canonical constructor parameter.

### 2.1. Listing Multiple `@Target`s Does Not Create Multiple Components

In `record Product(@Label("product-code") String code) {}`, there is still only **one component** `code`. Java does not create four components corresponding to the four `@Target` values.

Instead, the annotation is evaluated independently when the compiler declares **the derived members**. Thus, metadata is placed on multiple locations of the same record structure.

### 2.2. Specifying a Single Target

The declarations below each have a distinct meaning:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface AccessorOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParameterOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeOnly {}
```

An annotation with only `@Target(FIELD)` **can still be written on a record component** so the compiler propagates it to the component field. The same applies to `METHOD`, `PARAMETER`, and `TYPE_USE`. This does not mean the annotation appears in all places, or automatically becomes an annotation on the component itself.

Example:

```java
record Example(
        @ComponentOnly
        @FieldOnly
        @AccessorOnly
        @ParameterOnly
        @TypeOnly String value
) {}
```

In this record, each annotation is read at the location it targets. Specifically, `@ComponentOnly` stays only on the component and **does not** automatically become an annotation on the field, accessor, or constructor parameter.

## 3. Propagation Rules for Annotations on Components

Consider a record with no manually declared accessor or canonical constructor:

```java
record Order(@Label("order-id") String id) {}
```

With `@Label` having the targets from Section 2, the compiler handles each site independently:

1. **Component:** If the annotation applies to `RECORD_COMPONENT`, it belongs to the component's metadata.
2. **Field:** If it applies to `FIELD`, it is placed on the `private final String id` field provided by the record.
3. **Accessor:** If it applies to `METHOD`, it is placed on the `id()` accessor **if the accessor is implicitly generated**.
4. **Canonical constructor parameter:** If it applies to `PARAMETER`, it is placed on the parameter derived from the header **if the constructor uses the derived parameter list**.
5. **Type use:** If it applies to `TYPE_USE`, type annotation metadata accompanies the corresponding derived type positions.

The table below summarizes the case where **the record does not explicitly declare an accessor or canonical constructor**:

| `@Target` of annotation in header | `RecordComponent` | Field | Implicit accessor | Implicit constructor parameter |
|---|:---:|:---:|:---:|:---:|
| `RECORD_COMPONENT` only | Yes | No | No | No |
| `FIELD` only | No | Yes | No | No |
| `METHOD` only | No | No | Yes | No |
| `PARAMETER` only | No | No | No | Yes |
| `RECORD_COMPONENT, FIELD, METHOD, PARAMETER` | Yes | Yes | Yes | Yes |
| `TYPE_USE` only | Read via **annotated type**, not declaration annotation | Read via annotated type | Read via annotated return type | Read via annotated parameter type |

**Note:** The table shows where the annotation is placed when its targets match. Reading it directly via reflection at runtime also requires `@Retention(RUNTIME)`.

### 3.1. Annotation with `RECORD_COMPONENT` but Without `FIELD`

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ApiName {
    String value();
}

record Customer(@ApiName("customer_name") String name) {}
```

In this case:

- `Customer.class.getRecordComponents()[0].getAnnotation(ApiName.class)` finds the annotation.
- `Customer.class.getDeclaredField("name").getAnnotation(ApiName.class)` returns `null`.
- The `name()` accessor and constructor parameter also lack this annotation as a declaration annotation.

This is the right choice if metadata **should describe only the component**.

### 3.2. Annotation Applicable Only to Fields

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface StoredField {}

record Customer(@StoredField String name) {}
```

`@StoredField` is propagated by the compiler to the `name` field. Calling `RecordComponent.getAnnotation(StoredField.class)` does not return that annotation because `StoredField` does not target `RECORD_COMPONENT`.

A library that scans only fields and a library that scans only record components **may see different metadata**, even when reading the exact same record. That is why understanding the introspection mechanism of your tooling matters.

## 4. Reflection Example Observing All Four Locations Simultaneously

The following complete example demonstrates an annotation with multiple targets and uses reflection to inspect the result.

Create `RecordAnnotationDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface AuditTag {
    String value();
}

record Invoice(@AuditTag("invoice-code") String code) {}

public class RecordAnnotationDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Invoice> type = Invoice.class;

        RecordComponent component = type.getRecordComponents()[0];
        Field field = type.getDeclaredField("code");
        Method accessor = type.getDeclaredMethod("code");

        Constructor<Invoice> constructor =
                type.getDeclaredConstructor(String.class);
        Parameter parameter = constructor.getParameters()[0];

        System.out.println("Component: "
                + component.isAnnotationPresent(AuditTag.class));
        System.out.println("Field: "
                + field.isAnnotationPresent(AuditTag.class));
        System.out.println("Accessor: "
                + accessor.isAnnotationPresent(AuditTag.class));
        System.out.println("Parameter: "
                + parameter.isAnnotationPresent(AuditTag.class));
    }
}
```

Compile and run:

```bash
javac --release 17 RecordAnnotationDemo.java
java RecordAnnotationDemo
```

Output:

```text
Component: true
Field: true
Accessor: true
Parameter: true
```

**How to read the output:**

- `RecordComponent` represents the component declared in the header.
- `Field` is the reflection object for the corresponding storage field.
- `Method` is the `code()` accessor.
- `Parameter` is the parameter of the canonical constructor `Invoice(String code)`.

All four values are `true` **because `@AuditTag` targets all four locations** and is retained until runtime. With a narrower `@Target`, one or more results will be `false`.

## 5. When Writing an Accessor Explicitly: Annotations Do Not Propagate to That Accessor

A record generates accessors automatically when the author does not declare them. However, you can declare an accessor to control the returned value:

```java
record Profile(String displayName) {
    @Override
    public String toString() {
        return displayName;
    }

    public String displayName() {
        return displayName.strip();
    }
}
```

If an accessor is declared **explicitly**, Java **does not automatically copy annotations from the component** to that method, even if the annotation has `@Target(METHOD)`.

### 5.1. A Case That Easily Causes Surprises

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.RECORD_COMPONENT, ElementType.METHOD})
@interface Expose {}

record Account(@Expose String username) {
    public String username() {  // Explicitly declared accessor
        return username;
    }
}
```

Using reflection:

```java
boolean onComponent = Account.class.getRecordComponents()[0]
        .isAnnotationPresent(Expose.class);

boolean onAccessor = Account.class.getDeclaredMethod("username")
        .isAnnotationPresent(Expose.class);

System.out.println(onComponent); // true
System.out.println(onAccessor);  // false
```

**Why?** The metadata on the component still exists, yet this accessor was provided manually by the developer. The rule for propagating to an **implicit accessor** no longer applies.

### 5.2. Wanting the Annotation Present on Both the Component and Explicit Accessor

Attach the annotation directly to the method:

```java
record Account(@Expose String username) {
    @Expose
    public String username() {
        return username;
    }
}
```

Now `@Expose` appears on the component **and** the accessor, because both places are explicitly annotated. This is the right approach if your application framework reads getter/accessor annotations from `Method`.

### 5.3. Scope of Impact

Explicitly declaring an accessor only changes the rule for that accessor:

- The component still receives annotations matching `RECORD_COMPONENT`.
- The component field is still compiler-declared and receives annotations matching `FIELD`.
- Canonical constructor parameters follow the constructor rules in the next section.
- An explicit accessor only has the annotations declared directly on it; it does not automatically inherit annotations from the component.

Do not modify other declarations just to "stay in sync" if the framework does not actually need annotations in those places.

## 6. Canonical Constructors: Implicit, Compact, and Explicit Normal

A record has a canonical constructor taking parameters matching the components in exact order. Three forms commonly appear:

| Form | Example | Where do parameters come from? |
|---|---|---|
| Implicit constructor | `record User(String name) {}` | Compiler derives from header |
| Compact constructor | `record User(String name) { User { ... } }` | Compiler still derives from header |
| Explicitly written normal canonical constructor | `record User(String name) { User(String name) { ... } }` | Author explicitly declares the parameter list |

This distinction matters for annotations with `@Target(PARAMETER)`.

### 6.1. Implicit Constructor Receives Parameter Annotations

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface CheckedInput {}

record Customer(@CheckedInput String name) {}
```

The `name` parameter of the compiler-generated constructor receives `@CheckedInput`. Because the annotation does not target `RECORD_COMPONENT`, reflection on `RecordComponent` does not see it as a declaration annotation.

### 6.2. Compact Constructors Still Use the Derived Parameter List

```java
import java.util.Objects;

record Customer(@CheckedInput String name) {
    Customer {
        Objects.requireNonNull(name);
    }
}
```

Although the author supplies a body to validate data, a compact constructor **does not redeclare the parameter list**. The `name` parameter is still derived from the header, so `@CheckedInput` can appear on the constructor parameter.

The `Objects.requireNonNull(name)` code illustrates **developer-written** validation. `@CheckedInput` itself in this example does not automatically execute any validation logic.

### 6.3. Explicit Normal Canonical Constructors Have Independent Annotations

```java
record Customer(@CheckedInput String name) {
    Customer(String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}
```

Because the normal canonical constructor declares the `String name` parameter explicitly, `@CheckedInput` on the component **is not automatically copied onto the explicitly written parameter**.

If a library inspects constructor parameters and needs that metadata, declare it directly:

```java
record Customer(@CheckedInput String name) {
    Customer(@CheckedInput String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}
```

The two `@CheckedInput` annotations serve **two contexts**: in the header and on the parameter of the explicitly written constructor.

### 6.4. Example Verifying the Difference with Reflection

```java
import java.lang.annotation.*;
import java.lang.reflect.Constructor;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputMark {}

record ImplicitRecord(@InputMark String value) {}

record CompactRecord(@InputMark String value) {
    CompactRecord {
        if (value == null) throw new IllegalArgumentException("null");
    }
}

record ExplicitRecord(@InputMark String value) {
    ExplicitRecord(String value) {
        this.value = value;
    }
}

public class ConstructorAnnotationDemo {
    static boolean marked(Class<?> type) throws ReflectiveOperationException {
        Constructor<?> ctor = type.getDeclaredConstructor(String.class);
        return ctor.getParameters()[0].isAnnotationPresent(InputMark.class);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println(marked(ImplicitRecord.class));
        System.out.println(marked(CompactRecord.class));
        System.out.println(marked(ExplicitRecord.class));
    }
}
```

Compile and run `ConstructorAnnotationDemo.java`:

```bash
javac --release 17 ConstructorAnnotationDemo.java
java ConstructorAnnotationDemo
```

Output:

```text
true
true
false
```

The lesson here is not that compact constructors have a special "manual copy" mechanism. Both implicit and compact constructors use the **derived formal parameter list** from the record header per JLS 8.10.4. Meanwhile, a normal canonical constructor declares its own parameters and thus carries independent metadata.

### 6.5. Do Not Confuse Canonical Constructors with Auxiliary Constructors

A record can have additional constructors, but they must delegate by calling another constructor of the same record, such as `this(...)`:

```java
record Customer(String name, int level) {
    Customer(String name) {
        this(name, 1);
    }
}
```

Annotations on components are evaluated for **the corresponding canonical constructor parameter**, not automatically copied to every parameter of every auxiliary constructor.

## 7. `TYPE_USE`: Annotations on Type Usage Positions

An annotation with `@Target(TYPE_USE)` describes **a position where a type is used**, rather than directly annotating a field, method, parameter, or component declaration.

Example:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonEmptyType {}

record Document(@NonEmptyType String title) {}
```

In `record Document(@NonEmptyType String title) {}`:

- `@NonEmptyType` applies to the use of type `String` on the component.
- The corresponding type metadata can appear on the component field's type, the implicit accessor's return type, and the derived constructor parameter's type.
- `RecordComponent.getAnnotation(NonEmptyType.class)` is not the right API for reading a **type annotation**.
- Use `RecordComponent.getAnnotatedType()`, and on related members use `getAnnotatedType()` or `getAnnotatedReturnType()`.

### 7.1. Reflection for `TYPE_USE`

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface FormatHint {}

record Report(@FormatHint String title) {}

public class TypeUseAnnotationDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        RecordComponent component = Report.class.getRecordComponents()[0];
        Field field = Report.class.getDeclaredField("title");
        Method accessor = Report.class.getDeclaredMethod("title");
        Parameter parameter = Report.class.getDeclaredConstructor(String.class)
                .getParameters()[0];

        System.out.println(component.getAnnotatedType()
                .isAnnotationPresent(FormatHint.class));
        System.out.println(field.getAnnotatedType()
                .isAnnotationPresent(FormatHint.class));
        System.out.println(accessor.getAnnotatedReturnType()
                .isAnnotationPresent(FormatHint.class));
        System.out.println(parameter.getAnnotatedType()
                .isAnnotationPresent(FormatHint.class));

        // This checks declaration annotations on RecordComponent, not type use:
        System.out.println(component.isAnnotationPresent(FormatHint.class));
    }
}
```

Compile and run:

```bash
javac --release 17 TypeUseAnnotationDemo.java
java TypeUseAnnotationDemo
```

Output:

```text
true
true
true
true
false
```

Distinguishing `RecordComponent.getAnnotations()` from `RecordComponent.getAnnotatedType().getAnnotations()` is essential when developing reflection libraries.

### 7.2. With Generic Types, Annotation Placement Is Even More Granular

```java
record Inbox(
        java.util.List<@FormatHint String> messages
) {}
```

Here, `@FormatHint` is placed on the **type argument `String`**, not directly on the `List` type itself. To read annotations on a type argument, drill into `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`:

```java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

RecordComponent component = Inbox.class.getRecordComponents()[0];

AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) component.getAnnotatedType();

AnnotatedType elementType =
        listType.getAnnotatedActualTypeArguments()[0];

System.out.println(elementType.isAnnotationPresent(FormatHint.class));
// true
```

This snippet is intended to be used alongside the `Inbox` and `FormatHint` definitions above.

Similarly, annotations can be placed inside more complex type-use positions such as arrays, wildcards, or nested generics. When checking annotations on these types, do not inspect only `getAnnotations()` on the outermost element.

### 7.3. `TYPE_USE` Does Not Enforce Validation Automatically

A custom `@NonEmptyType` or `@FormatHint` annotation **is merely metadata**. Java does not automatically check for blank strings or enforce formatting. To get that behavior, you must write validation logic or integrate a tool/framework that understands the annotation.

Do not mistake type-metadata propagation for propagation of validation logic.

## 8. `@Retention` Determines Runtime Visibility via Reflection

`@Target` specifies **valid placement**; `@Retention` specifies **how long metadata is kept**.

| Retention Policy | Meaning | Readable via Java Reflection at Runtime? |
|---|---|---|
| `SOURCE` | Used in source; compiler discards annotation from class file | No |
| `CLASS` | Kept in class file per retention rules, but not required/exposed via runtime reflection | No |
| `RUNTIME` | Metadata kept and exposed to runtime reflection | Yes |

Example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface RuntimeSchemaName {
    String value();
}

record Payload(@RuntimeSchemaName("payload_id") long id) {}
```

`Payload.class.getRecordComponents()[0].getAnnotation(RuntimeSchemaName.class)` returns the annotation with value `"payload_id"`.

If `RuntimeSchemaName` is defined with `SOURCE` or `CLASS` retention, failing to find the annotation at runtime **does not prove the annotation was declared in the wrong spot**. It may simply not be retained for reflection.

**Practice tip:** When writing libraries that inspect records via reflection, check **both `@Target` and `@Retention`**, rather than looking solely at where the annotation appears in source code.

## 9. Annotations on the Record Class Differ from Annotations on Components

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DomainType {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface DomainField {}

@DomainType
record Customer(@DomainField String name, int age) {}
```

The two annotations serve two purposes:

- `@DomainType` sits on **the `Customer` class**, readable via `Customer.class.getAnnotation(DomainType.class)`.
- `@DomainField` sits on **the `name` component**, readable via `Customer.class.getRecordComponents()[0].getAnnotation(DomainField.class)`.

There is no default rule copying an annotation from the record class to all components. Conversely, component annotations do not automatically become annotations on the record class.

**`@Inherited` does not solve this either.** `@Inherited` applies to looking up **class** annotations along class inheritance via reflection rules; it does not create annotation inheritance across record components, fields, and accessors. Since records are implicitly `final`, there are no record subclasses to inherit from anyway.

## 10. Annotations on Records and Framework Implications

In real applications, records are commonly used as DTOs, messages, or data-transfer objects. Libraries may read annotations from different locations:

| How a Library Inspects a Record | Element Read | What to Check When Annotating |
|---|---|---|
| Scans record components | `Class.getRecordComponents()` | Does the annotation have `RECORD_COMPONENT` and appropriate retention? |
| Scans fields | `Class.getDeclaredFields()` | Does the annotation have `FIELD`? |
| Scans accessors | `Class.getDeclaredMethods()` or `RecordComponent.getAccessor()` | Does the annotation have `METHOD`? Is the accessor auto-generated or hand-written? |
| Scans constructor parameters | `Constructor.getParameters()` | Does the annotation have `PARAMETER`? Is the constructor implicit/compact or explicit normal? |
| Scans type uses | `AnnotatedType` | Does the annotation have `TYPE_USE` and is the right type/generic level inspected? |

For example, an annotation targeting both `RECORD_COMPONENT` and `FIELD` might be read from the component by one framework and from the field by another. **Do not assume every framework scans the same site** or processes records identically. Actual compatibility depends on the library version and how it supports records.

### 10.1. When Changing an Accessor to Normalize Data

```java
record User(String username) {
    public String username() {
        return username.strip();
    }
}
```

If there used to be a `@Target(METHOD)` annotation on the component and you then add an explicit accessor, that annotation **no longer propagates to the accessor**. A framework reading annotations from `Method` may change behavior, even though the header annotation remains untouched.

Therefore, when writing a custom accessor, check which annotations reflection-based components expect and declare them directly on the accessor if needed.

### 10.2. When Replacing a Compact Constructor with a Normal Canonical Constructor

```java
// Compact form: parameters are derived from components.
record A(@ParameterOnly String name) {
    A {
        java.util.Objects.requireNonNull(name);
    }
}
```

```java
// Normal form: author explicitly declares parameters.
record B(@ParameterOnly String name) {
    B(String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}
```

For `@Target(PARAMETER)` annotations, switching constructor forms can change the annotations observable on **constructor parameters via reflection**. This is an important difference in libraries that inspect parameter metadata.

If a library expects the annotation on `B`'s normal constructor parameter, place `@ParameterOnly` directly at `B(@ParameterOnly String name)`.

### 10.3. Annotations Do Not Replace Record Validation

```java
record Account(String number) {
    Account {
        if (number == null || number.isBlank()) {
            throw new IllegalArgumentException("number is required");
        }
    }
}
```

This is ordinary Java validation inside a compact constructor. Annotations can **describe** constraints; Java code or a configured framework must **enforce** them. Do not assume adding an annotation alone makes data validate itself.

## 11. Compile-Time Annotation Processing

Beyond runtime reflection, annotation processors can access record structure while processing source code. In Java 17, the `javax.lang.model` API supports records, including:

- `ElementKind.RECORD` representing the record class.
- `ElementKind.RECORD_COMPONENT` representing a record component.
- `RecordComponentElement`, the interface for component elements, used to inspect corresponding metadata.
- Annotation processors can read component metadata and related elements according to their own logic.

This is **a different mechanism from runtime reflection**. An annotation with `SOURCE` retention can still be useful during compile-time processing, even though it does not appear in `getAnnotation(...)` at runtime.

Conceptual processing example:

```java
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;

static void inspect(Element element) {
    if (element.getKind() == ElementKind.RECORD_COMPONENT) {
        System.out.println("Record component: " + element.getSimpleName());
    }
}
```

This snippet illustrates the body of a processor or utility running inside annotation processing; it is not a standalone Java program callable outside a processor environment.

**Principle:** Metadata propagated by the compiler in a record does not mean every processor or library automatically merges it into one unified view. Each tool must explicitly choose which locations and element kinds it reads.

## 12. Common Misconceptions and Pitfalls

### 12.1. "Putting an annotation on a component puts it on the field, getter, and constructor"

Not always true. Propagation depends on `@Target`, retention, and whether members are compiler-generated or explicitly declared by the programmer.

**How to handle:** Read the annotation's `@Target`, then check which site the framework inspects.

### 12.2. "`RECORD_COMPONENT` is the only target allowed in the header"

False. `FIELD`, `METHOD`, `PARAMETER`, and `TYPE_USE` can also be written in the header for Java to apply in the proper contexts. That does not mean they all show up in `RecordComponent.getAnnotations()`.

### 12.3. "Writing an explicit accessor preserves auto-propagated annotations"

False. Explicit accessors do not automatically receive annotations from the component. If an annotation is needed on the accessor, declare it directly.

### 12.4. "A compact constructor drops parameter annotations"

False. Compact constructors still use the parameter list derived from components; annotations applicable to `PARAMETER` are applied to those parameters.

### 12.5. "A normal canonical constructor automatically inherits parameter annotations from the header"

False. When constructor parameters are explicitly declared, parameter annotations can differ from component annotations. Declare them directly on the constructor parameter when required by tooling.

### 12.6. "`getAnnotations()` and `getAnnotatedType()` read the same information"

False. The first API reads **declaration annotations** of the element. The second provides information about **type annotations** on type uses.

### 12.7. "Having `@Target(RECORD_COMPONENT)` guarantees reflection can read it"

False if retention is not `RUNTIME`. `@Target` and `@Retention` answer two different questions.

### 12.8. "Annotations automatically validate record data"

False. Annotations are usually metadata. Input validation requires corresponding Java code or a framework configured to process the annotations.

## 13. Self-Practice Exercises

### Exercise 1. Determine Where the Annotation Appears

Given:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
@interface Limited {}

record Item(@Limited String code) {}
```

**Question:** Among the component, field, accessor, and implicit canonical constructor parameter, which sites have the declaration annotation `@Limited` at runtime?

**Answer:** The field and the constructor parameter. The component lacks `RECORD_COMPONENT`, and the accessor lacks `METHOD`.

### Exercise 2. Explicit Accessor

Given:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.RECORD_COMPONENT, ElementType.METHOD})
@interface Visible {}

record Document(@Visible String title) {
    public String title() {
        return title;
    }
}
```

**Question:** What does `Document.class.getDeclaredMethod("title").isAnnotationPresent(Visible.class)` return?

**Answer:** `false`, because the accessor is explicitly declared by the author. The component still has `@Visible` due to target `RECORD_COMPONENT`.

### Exercise 3. Canonical Constructor

Given:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Required {}

record Profile(@Required String name) {
    Profile(String name) {
        this.name = name;
    }
}
```

**Question:** Does reflection on the parameter of `Profile(String name)` see `@Required`? If you want it to, how do you fix it?

**Answer:** No. Place `@Required` directly before `String name` in the normal canonical constructor, or consider a compact constructor if it fits your needs.

### Exercise 4. Distinguishing Type Use and Declaration

Given:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Normalized {}

record Account(@Normalized String code) {}
```

**Question:** Should you use `RecordComponent.getAnnotation(Normalized.class)` or `RecordComponent.getAnnotatedType().getAnnotation(Normalized.class)`?

**Answer:** Use `getAnnotatedType().getAnnotation(...)`. `@Normalized` targets the type use of `String`, not a declaration annotation on the component.

### Exercise 5. Annotations and Validation

Given:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface NotEmpty {}

record Tag(@NotEmpty String value) {}
```

**Question:** Can you create `new Tag("")`?

**Answer:** Yes, if there is no other validation logic. `@NotEmpty` in this example is only metadata. A record does not automatically generate validation from custom annotations.

## 14. Checklist When Troubleshooting Annotation Issues on Records

When a tool reports "annotation not found," check step-by-step:

1. **How is `@Target` defined on the annotation?** Does it include the appropriate `RECORD_COMPONENT`, `FIELD`, `METHOD`, `PARAMETER`, or `TYPE_USE`?
2. **Does the annotation have `@Retention(RUNTIME)`?** If not, runtime reflection cannot read it.
3. **Which element does the tool inspect?** `RecordComponent`, `Field`, `Method`, `Parameter`, or `AnnotatedType`?
4. **Is the accessor explicitly declared?** If yes, header annotations do not automatically propagate to the accessor.
5. **Which form is the canonical constructor?** Implicit and compact use derived parameters; normal canonical constructors declare parameters independently.
6. **Is the annotation inside a generic type argument or array type?** If it is `TYPE_USE`, inspect the right node in the `AnnotatedType` tree.
7. **Does the framework version in use support records?** Do not assume Java supporting records automatically makes every library read metadata the way you expect.

These steps are usually enough to distinguish an annotation placement mistake from a difference in how a library reads metadata.

## 15. Official Documentation

- [Java Language Specification 17 — `8.10 Record Classes`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record structure, components, and related members.
- [JLS 17 — `8.10.3 Record Members`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): annotation propagation to component fields and implicit accessors; difference with explicit accessors.
- [JLS 17 — `8.10.4 Record Constructor Declarations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): derived parameter lists, compact and normal canonical constructors.
- [JLS 17 — `9.7.4 Where Annotations May Appear`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): valid positions for declaration and type-use annotations.
- [JDK 17 API — `RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): `getAnnotation`, `getAnnotatedType`, `getAccessor`, and other reflection APIs.
- [JDK 17 API — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): reading annotations on type-use positions.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): design rationale and standardization of records in Java 16.

**Takeaway:** An annotation in a record's header can serve multiple contexts, yet **does not automatically appear everywhere**. Check `@Target` and `@Retention`, distinguish declaration annotations from `TYPE_USE`, and consider whether accessors and the canonical constructor are implicit or explicitly declared. That is the key to using annotations on records reliably and predictably in Java 17.
