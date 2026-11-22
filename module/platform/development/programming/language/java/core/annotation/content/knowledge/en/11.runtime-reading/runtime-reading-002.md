# Reading Annotations on Class, Field, Method, and Constructor with Java Reflection

## 1. Where Are Annotations Read at Runtime?

Java annotations are **metadata** attached to a program element. You can declare annotations on a class, field, method, and constructor, and then use the **Java Reflection API** to inspect which annotations are attached at each location. This commonly appears in DI, ORM, testing, validation, and mapping frameworks, or libraries with annotation-based conventions.

To read annotations with reflection at runtime, two basic conditions are required:

1. The annotation type must use **`@Retention(RetentionPolicy.RUNTIME)`**. If it only has `SOURCE` or `CLASS`, the annotation cannot be retrieved through standard reflection APIs.
2. The program must look up the exact **annotated element**: metadata on a class does not automatically become metadata on a field; metadata on a method does not automatically appear on a constructor.

Four commonly used reflection objects:

| Annotated target | Representative API | Example retrieval |
| --- | --- | --- |
| Class/interface/enum/record | `java.lang.Class<?>` | `OrderService.class`; `obj.getClass()` |
| Field | `java.lang.reflect.Field` | `type.getDeclaredField("id")` |
| Method | `java.lang.reflect.Method` | `type.getDeclaredMethod("save", String.class)` |
| Constructor | `java.lang.reflect.Constructor<?>` | `type.getDeclaredConstructor(String.class)` |

`Class`, `Field`, `Method`, and `Constructor` all implement the **`java.lang.reflect.AnnotatedElement`** interface. This interface provides methods such as `getAnnotation(...)`, `getDeclaredAnnotation(...)`, `getAnnotations()`, `getDeclaredAnnotations()`, and the `ByType` methods for reading repeatable annotations.

**Distinction:** Reflection reads annotations on **declarations**; it does not automatically execute business logic or modify field values. If a framework reads `@Transactional` or `@Column` and performs some action, that is behavior built by the framework on top of metadata, not an automatic behavior of Java merely because the annotation was declared.

## 2. Defining an Annotation with RUNTIME Retention and the Right Target

For example, suppose you want to annotate a class, field, method, and constructor with the same annotation type:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Info {
    String value();
}
```

Explanation:

- `@Retention(RUNTIME)` retains the metadata so reflection calls can read it at runtime.
- `@Target(TYPE)` allows placement on class declarations (and other applicable type declarations), `FIELD` on field declarations, `METHOD` on method declarations, and `CONSTRUCTOR` on constructor declarations.
- `String value()` is a required element. When applying it, you can use the shorthand form `@Info("mô tả")`.
- `@Target` only determines **where an annotation can be applied**, whereas `@Retention` determines **retention and observability**. The two are independent.
- Even though an annotation can be placed on multiple targets, **each location has its own metadata**. For example, `@Info` on a class does not automatically appear in `getAnnotation(Info.class)` of each method.

If `@Retention` is not declared, the default is `RetentionPolicy.CLASS`, so runtime reflection cannot read that annotation. An annotation with `@Retention(SOURCE)` can be useful for the compiler or annotation processors, but it is not present in the class file for reflection to read.

## 3. Standalone Java 17+ Example: Reading All Four Locations

All declarations below reside in **a single file** named `ReflectionAnnotationDemo.java`. It includes the runtime annotation `@Info`, the `@CompileOnly` annotation that is not available through reflection, the inheritable `@Team` annotation to demonstrate behavior on classes, and a business class containing annotated fields, methods, and constructors.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.TYPE,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.CONSTRUCTOR
})
@interface Info {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface CompileOnly {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Team {
    String value();
}

@Info("payment-service")
@CompileOnly
@Team("backend")
class PaymentService {
    @Info("transaction-id")
    private final String id;

    @Info("public-constructor")
    public PaymentService(String id) {
        this.id = id;
    }

    @Info("private-constructor")
    private PaymentService() {
        this("default");
    }

    @Info("pay-method")
    public String pay(int amount) {
        return id + ":" + amount;
    }

    @Info("internal-validation")
    private void validate() {
    }
}

class PaymentChild extends PaymentService {
    PaymentChild() {
        super("child");
    }
}

public class ReflectionAnnotationDemo {
    public static void main(String[] args)
            throws NoSuchFieldException, NoSuchMethodException {
        Class<PaymentService> type = PaymentService.class;
        Info classInfo = type.getAnnotation(Info.class);
        System.out.println("Class: " + classInfo.value());
        System.out.println("CLASS retention visible: "
                + type.isAnnotationPresent(CompileOnly.class));

        Field idField = type.getDeclaredField("id");
        System.out.println("Field: "
                + idField.getAnnotation(Info.class).value());

        Method payMethod = type.getDeclaredMethod("pay", int.class);
        System.out.println("Method: "
                + payMethod.getAnnotation(Info.class).value());

        Method validateMethod = type.getDeclaredMethod("validate");
        System.out.println("Private method: "
                + validateMethod.getAnnotation(Info.class).value());

        Constructor<PaymentService> publicCtor =
                type.getDeclaredConstructor(String.class);
        System.out.println("Constructor: "
                + publicCtor.getAnnotation(Info.class).value());

        Constructor<PaymentService> privateCtor =
                type.getDeclaredConstructor();
        System.out.println("Private constructor: "
                + privateCtor.getAnnotation(Info.class).value());

        System.out.println("Child inherited Team: "
                + PaymentChild.class.getAnnotation(Team.class).value());
        System.out.println("Child declares Team: "
                + (PaymentChild.class.getDeclaredAnnotation(Team.class) != null));
        System.out.println("Child inherits Info: "
                + (PaymentChild.class.getAnnotation(Info.class) != null));
    }
}
```

Using **JDK 17 or higher**, open a terminal in the directory containing the file:

```bash
javac --release 17 ReflectionAnnotationDemo.java
java ReflectionAnnotationDemo
```

**Stdout:**

```text
Class: payment-service
CLASS retention visible: false
Field: transaction-id
Method: pay-method
Private method: internal-validation
Constructor: public-constructor
Private constructor: private-constructor
Child inherited Team: backend
Child declares Team: false
Child inherits Info: false
```

Analysis:

1. `PaymentService.class` is the `Class<PaymentService>` object representing the type. `getAnnotation(Info.class)` finds the `@Info("payment-service")` metadata **on the class**.
2. `@CompileOnly` has `CLASS` retention, so `isAnnotationPresent(CompileOnly.class)` returns `false` when read via reflection, even though the annotation declaration exists in both the source and class files.
3. `getDeclaredField("id")` retrieves the `private final String id` field. `Field.getAnnotation(Info.class)` returns `"transaction-id"`, not the annotation on the class.
4. `getDeclaredMethod("pay", int.class)` uses the **method name and parameter type list** to locate the method. Because the method takes an `int`, `int.class` must be passed; `getDeclaredMethod("pay")` will not find this method.
5. `getDeclaredMethod("validate")` retrieves the parameterless `private` method. You can **read annotations** from the returned `Method` object **without calling `setAccessible(true)`**.
6. `getDeclaredConstructor(String.class)` retrieves the constructor taking a string; `getDeclaredConstructor()` retrieves the no-arg constructor, even though it is `private`. Both have their own annotations.
7. `@Team` is marked with `@Inherited`, so `PaymentChild.class.getAnnotation(Team.class)` retrieves the value from the superclass, whereas `getDeclaredAnnotation(Team.class)` only checks annotations declared directly on `PaymentChild` and returns `null`.
8. `@Info` is **not** marked with `@Inherited`, so `PaymentChild.class.getAnnotation(Info.class)` returns `null` even though the superclass carries `@Info`.

The example only **reads metadata**; it does not access field values or invoke private methods/constructors. It also does not create an instance of `PaymentService` or `PaymentChild`. Annotations on declarations can already be read from `Class` and the corresponding reflection objects.

## 4. Reading Annotations on a Class

Basic example:

```java
Class<PaymentService> type = PaymentService.class;
Info info = type.getAnnotation(Info.class);

if (info != null) {
    System.out.println(info.value());
}
```

`Class.getAnnotation(Info.class)` returns the `Info` annotation according to the "present annotation" rules of `AnnotatedElement`, or `null` if absent. Always handle the `null` case when writing code meant for multiple classes instead of assuming the annotation definitely exists.

Some commonly used APIs:

| API on `Class` | Result |
| --- | --- |
| `isAnnotationPresent(Info.class)` | `true` if an annotation of that type is considered present by the API rules; `false` otherwise |
| `getAnnotation(Info.class)` | An `Info` annotation or `null` |
| `getDeclaredAnnotation(Info.class)` | Only an `Info` annotation declared directly on the class, or `null` |
| `getAnnotations()` | Runtime annotations present on the class, including applicable inherited annotations |
| `getDeclaredAnnotations()` | Runtime annotations **declared directly** on the class |
| `getAnnotationsByType(Info.class)` | Array of annotations of that type; supports repeatable annotations and applicable inheritance rules |
| `getDeclaredAnnotationsByType(Info.class)` | Array of annotations of that type declared on the class, without checking the superclass |

**Do not rely on the order of the array returned by `getAnnotations()` or `getDeclaredAnnotations()`** when multiple different annotation types are present. If you want a specific annotation, query by `Info.class` instead of taking `[0]` and assuming it is the desired annotation.

### 4.1. Annotation Inheritance on Classes

An annotation is only "inherited" in the sense of `Class.getAnnotation`/`getAnnotations` when the annotation type has **`@Inherited`**, and it applies along the **superclass** chain. Placing `@Inherited` on an annotation does not cause methods/fields/constructors to automatically inherit the annotation; implemented interfaces also do not pass annotations to a class through this mechanism.

In the example:

- `Team` is defined with `@Inherited`; if a subclass does not declare `@Team` itself, `getAnnotation(Team.class)` can obtain it from the superclass.
- `Info` does not have `@Inherited`; a subclass does not receive `@Info` from its parent via `getAnnotation(Info.class)`.
- `getDeclaredAnnotation` on a subclass does **not** automatically look up the superclass even if the annotation type has `@Inherited`.

If a subclass declares an annotation of the same type itself, it can override the corresponding inherited result. If a program needs to merge metadata across multiple class levels, it must implement its own superclass traversal rules.

## 5. Reading Annotations on a Field

`Field` represents a **field declaration**, not an individual value in an instance.

```java
Field field = PaymentService.class.getDeclaredField("id");
Info info = field.getAnnotation(Info.class);
System.out.println(info.value()); // transaction-id
```

APIs for finding fields:

- `getDeclaredField("id")`: finds a field declared **directly in the class**, including `private`, `protected`, package-private, and `public` fields; it does **not** find fields inherited from a superclass.
- `getField("id")`: finds a **public field** belonging to the class or appropriately inherited; it cannot be used to retrieve the private field `id` in the example.
- `getDeclaredFields()`: all fields declared directly in the class, which may include *synthetic* fields generated by the compiler. You should not rely on the returned order.
- `getFields()`: the public fields defined by the API as members of the class, including appropriately inherited ones.

Once you have a `Field`, call `field.getAnnotation(Info.class)` to read metadata on the field declaration. For a class with multiple objects, the annotation on the field declaration is shared metadata; **it is not a separate copy created for each object**.

### Reading an Annotation and Reading a Field Value Are Two Different Things

```java
Info metadata = field.getAnnotation(Info.class);
// metadata.value() is "transaction-id"
// field.get(instance) is a different operation: reading the field value on an instance
```

If a field is private, **reading annotations via `Field.getAnnotation` does not require bypassing access checks**. However, to read the value of a private field using `field.get(instance)`, you must account for access control and module rules; `setAccessible(true)` is not always permitted (especially when working across a named module that does not open the package).

You should not call `setAccessible(true)` solely for the purpose of reading annotations.

## 6. Reading Annotations on a Method

`Method` represents a **method declaration**. When multiple methods share the same name (*overloading*), they must be distinguished by their parameter type list.

```java
Method method = PaymentService.class.getDeclaredMethod("pay", int.class);
Info info = method.getAnnotation(Info.class);
System.out.println(info.value()); // pay-method
```

Lookup methods:

| API | Search scope |
| --- | --- |
| `getDeclaredMethod("pay", int.class)` | Method with the specified name/parameter signature declared **on the class itself**, at any access level |
| `getMethod("pay", int.class)` | `public` method, including methods inherited according to reflection rules |
| `getDeclaredMethods()` | Methods declared on the class itself, including private ones, but excluding methods only inherited from a parent |
| `getMethods()` | Public methods, including appropriately inherited methods |

`getDeclaredMethod` and `getMethod` accept `Class<?>` objects representing the **parameter types** in exact order. For a method with no parameters, simply write `getDeclaredMethod("validate")` or pass empty varargs. The return type does not appear in the method lookup parameters; Java does not allow overloading by return type alone.

Metadata can still be retrieved from a `private` method:

```java
Method privateMethod = PaymentService.class.getDeclaredMethod("validate");
Info metadata = privateMethod.getAnnotation(Info.class);
System.out.println(metadata.value()); // internal-validation
```

**Annotations on methods are not automatically inherited via `@Inherited`.** If a subclass overrides a method from its parent without redeclaring the annotation, querying the `Method` object of the overriding method does not automatically return the annotation from the superclass method. A framework may implement its own logic to search for annotations along the inheritance hierarchy, but that is a framework-specific mechanism.

For annotations placed on **method parameters**, the corresponding reflection object is `Parameter` or APIs such as `Method.getParameterAnnotations()`; this is a **different** metadata location from annotations attached to the method itself. Do not expect `Method.getAnnotation(...)` to see an annotation placed only on a parameter.

## 7. Reading Annotations on a Constructor

`Constructor<?>` represents a constructor declaration, which may have overloads with different parameter lists.

```java
Constructor<PaymentService> constructor =
        PaymentService.class.getDeclaredConstructor(String.class);

Info info = constructor.getAnnotation(Info.class);
System.out.println(info.value()); // public-constructor
```

Distinctions:

- `getConstructor(String.class)` only returns a **public constructor** matching the parameter list.
- `getDeclaredConstructor(String.class)` returns a constructor declared on the class itself, **whether public or private**.
- `getConstructors()` returns the public constructors declared in the class.
- `getDeclaredConstructors()` returns the constructors declared in the class at all access levels.

**Constructors are not inherited** from a superclass. A subclass has its own set of constructors, so looking up a constructor on a subclass does not automatically retrieve constructors from the superclass.

In the example, `PaymentService` has two constructors carrying different `@Info` annotations. If you retrieve the no-arg constructor:

```java
Constructor<PaymentService> ctor =
        PaymentService.class.getDeclaredConstructor();
Info info = ctor.getAnnotation(Info.class);
System.out.println(info.value()); // private-constructor
```

Reflection can read annotations on a private constructor without calling `setAccessible(true)`. However, **invoking a private constructor** with `ctor.newInstance()` is a different operation, subject to access control checks, and may fail. Do not confuse **reading metadata** with **instantiating an object**.

A class that only has a compiler-generated default constructor will not automatically receive annotations you might expect on an explicitly written constructor; to annotate a constructor, declare the constructor and place the annotation in the right location. For records, enums, or member inner classes, constructor signatures at the reflection level may have additional characteristics, so you need to determine the exact actual parameters when looking them up.

## 8. getAnnotation, getDeclaredAnnotation, and getAnnotationsByType

All four reflection types in this article implement the `AnnotatedElement` interface. The APIs have important differences:

### `getAnnotation(T.class)`

Returns an annotation of type `T` **considered present**, or `null`. For `Class`, `@Inherited` rules may allow retrieving the annotation from a superclass. For `Field`, `Method`, and `Constructor`, the same annotation inheritance mechanism as on classes does not apply.

### `getDeclaredAnnotation(T.class)`

Only considers annotations **declared directly on the element itself** (does not search superclasses). Use this when you want to avoid picking up inherited metadata at the class level.

### `getAnnotations()` and `getDeclaredAnnotations()`

Return an array of annotations visible via reflection (or only those declared directly). When iterating over the elements, you should check `annotation.annotationType()` and not rely on the ordering across different annotation types.

### `getAnnotationsByType(T.class)` and `getDeclaredAnnotationsByType(T.class)`

Especially useful when `T` is a **repeatable annotation** declared with `@Repeatable(Container.class)`. When multiple uses of `@T` are represented by the compiler through the container, `getAnnotation(T.class)` can return `null`, whereas `getAnnotationsByType(T.class)` unwraps the appropriate container and returns all component annotations according to the API rules.

Illustrative example (assuming `Tag` is a repeatable annotation type with `RUNTIME` retention):

```java
@Tag("read")
@Tag("write")
class ReportEndpoint {}
```

Instead of only calling `ReportEndpoint.class.getAnnotation(Tag.class)`, use `getAnnotationsByType(Tag.class)` if you need **all Tags**. Similarly, `getDeclaredAnnotationsByType` is limited to the current declaration site.

**Note:** This is only illustrative syntax; to compile, `Tag` and its container must be properly declared with `@Repeatable`. Repeatable annotations are a matter of multiplicity and how reflection queries them, and do not change the nature of `Class`, `Field`, `Method`, or `Constructor`.

## 9. Distinguishing Declaration Annotations from TYPE_USE and TYPE_PARAMETER

Not all annotations visible in source code are found using `field.getAnnotation(...)`.

For example, an annotation defined with `@Target(ElementType.TYPE_USE)` can be placed on **a type use**, such as a method return type, an array element type, or a generic type argument. Type-use metadata is exposed through APIs in the `AnnotatedType` family, for example:

- `Field.getAnnotatedType()`;
- `Method.getAnnotatedReturnType()`;
- `Method.getAnnotatedParameterTypes()`;
- `Constructor.getAnnotatedParameterTypes()`.

Meanwhile, `Field.getAnnotation(...)` looks for annotations **directly on the field declaration**; `Method.getAnnotation(...)` looks for annotations **directly on the method declaration**. When an annotation has multiple targets or its syntax places the annotation in a type-use position, you need to check the right API for the kind of metadata you want to read.

Similarly, annotations on a **type parameter** of a class/method (`ElementType.TYPE_PARAMETER`) and annotations on a **regular parameter** of a method/constructor (`ElementType.PARAMETER`) belong to different locations. Reading annotations on a class/method declaration does not mean reading all metadata on every element inside it.

## 10. Common Mistakes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `getAnnotation(...)` returns `null` even though the annotation exists in source | Retention is not `RUNTIME`; wrong element queried; or repeatable annotation is wrapped indirectly | Check `@Retention`, `@Target`, placement location, and consider `getAnnotationsByType` |
| `getDeclaredField("id")` throws `NoSuchFieldException` | The field is not declared in that class, has a different name, or resides in a superclass | Verify the exact class/name; traverse superclasses or use the appropriate API if it is a public field |
| `getDeclaredMethod("pay")` throws `NoSuchMethodException` | The method actually has an `int` parameter | Use `getDeclaredMethod("pay", int.class)` |
| `getMethod("validate")` does not find the method | The method is `private` | Use `getDeclaredMethod("validate")` |
| `getConstructor()` does not find a private constructor | `getConstructor` only looks up public constructors | Use `getDeclaredConstructor()` |
| Annotations on a subclass differ from expectations | `@Inherited` only supports superclass lookup for annotations on class declarations | Distinguish between `getAnnotation` and `getDeclaredAnnotation` |
| Can read annotations on a private member but cannot read its value or invoke the member | Reflection metadata and **runtime access** permissions are two separate issues | Respect Java access control/JPMS; do not arbitrarily enable `setAccessible` |
| Read `@Info` on the class but do not see `@Info` of a method | Metadata is attached to different declarations | Retrieve the specific `Method` or `Field` object and call `getAnnotation` on it |
| Iterating over `getDeclaredMethods()` and assuming the first element is the desired method | Reflection array order is not part of the contract; synthetic/bridge methods may be present | Filter by name, parameter signature, modifiers, and required conditions |

### Always Handle the Case Where an Annotation Is Absent

A library that scans multiple classes should not do:

```java
Info info = type.getAnnotation(Info.class);
String value = info.value(); // May throw NullPointerException if the annotation is missing
```

Instead, use:

```java
Info info = type.getAnnotation(Info.class);
if (info != null) {
    System.out.println(info.value());
}
```

Both snippets are **illustrations inside a method** where a variable `type` of type `Class<?>` and the annotation type `Info` are already declared; they are not standalone programs. You can also use `isAnnotationPresent(Info.class)` to check beforehand, but if you need element values, retrieving the annotation once and checking for `null` is usually sufficient.

### When Reflection Cannot Find a Member

Lookup methods by name/signature may throw `NoSuchFieldException` or `NoSuchMethodException`. These are **element-not-found** errors, which are different from `getAnnotation(...) == null`, meaning **the reflected element exists, but the annotation was not found**. The two cases must be handled separately when designing a metadata reader.

### Do Not Assume Annotations Execute Logic on Their Own

For example, `@Info("pay-method")` does not cause `pay` to be invoked, does not log automatically, and does not alter transactions. Reflection only returns metadata. If you want to use that information for routing, validation, or logging, you must write separate processing code while validating types, values, and business rules.

## 11. How to Organize an Annotation Reader in a Project

A controlled approach:

1. **Define the annotation contract:** which declaration types the annotation is meant to mark and whether it must have `RUNTIME` retention.
2. **Define the scanning scope:** reading a specific class, all fields, methods, constructors, or multiple classes. Do not scan the entire classpath unnecessarily.
3. **Choose the right element-lookup API:** `getDeclaredField`/`getDeclaredMethod`/`getDeclaredConstructor` for directly declared elements (including private ones); APIs without `Declared` for public members according to their respective rules.
4. **Look up and check for null:** `getAnnotation` when expecting a single annotation; `getAnnotationsByType` for repeatable annotations.
5. **Specify inheritance clearly:** if reading a class annotation with `@Inherited`, distinguish between directly declared data and data that may be considered inherited. For fields/methods, do not arbitrarily apply class-annotation inheritance logic.
6. **Do not mix reading with execution:** the metadata scanner should extract and validate annotations first; business-processing code comes as a subsequent step.
7. **Consider access permissions and modules:** reading annotations on a private member typically does not require calling `setAccessible`; invoking a private member or reading a private field's value has its own protection rules.
8. **Test with Java 17+:** place annotations on class/field/method/constructor, and include a `CLASS`-retention annotation and a subclass to verify absence and inheritance cases.

**Key takeaway:** `Class`, `Field`, `Method`, and `Constructor` all allow reading runtime annotations via `AnnotatedElement`, but each reflection object describes **a different declaration level**. Start with the right member, verify retention, use the appropriate `getAnnotation`/`getDeclaredAnnotation`/`getAnnotationsByType` method, and only then interpret the metadata according to your business logic.
