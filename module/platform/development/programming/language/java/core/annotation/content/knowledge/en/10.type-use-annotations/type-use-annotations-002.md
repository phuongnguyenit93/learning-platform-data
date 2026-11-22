# TYPE_USE on Field, Parameter, and Return Types in Java

## 1. `TYPE_USE` Describes *Type Use* Locations

In Java, an annotation can be attached to the **declaration** of a field, method, or parameter; since Java 8, annotations can also be attached to a **type being used** at various locations in code. To define an annotation type for those locations, use `ElementType.TYPE_USE` in `@Target`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface TypeHint {
    String value();
}
```

With this annotation type, the following examples are all ways of attaching it to a **type**:

```java
// These snippets only illustrate locations and do not form a standalone runnable file.
class Example {
    private @TypeHint("field-type") String name;

    public @TypeHint("return-type") String normalize(
            @TypeHint("parameter-type") String input) {
        return input.strip();
    }
}
```

- `@TypeHint("field-type") String` marks the **type of field `name`**.
- `@TypeHint("parameter-type") String` marks the **type of parameter `input`**.
- `@TypeHint("return-type") String` marks the **return type `String`** of the `normalize` method.

**Key point:** `TYPE_USE` pertains to **where a type appears in the source code**, not an operation that “attaches an annotation to every object of that type”. Metadata is not automatically attached to individual `String` objects created at runtime; it is described at the type declaration/use location in the program.

The locations above differ from attaching an annotation directly to a **field declaration**, **parameter declaration**, or **method declaration**. Although the syntax may look very similar, Java distinguishes those locations and provides corresponding Reflection APIs.

## 2. Three Core Cases

### 2.1 Field Type

Example:

```java
class Account {
    private @TypeHint("account-id") String id;
}
```

Here `id` is the field; `String` is the field's type. The annotation sits at the type location, so a processor can tell that the **type of field `id`** carries the metadata `"account-id"`.

How to retrieve the metadata with Reflection (for an annotation with `RUNTIME` retention):

```java
Field field = Account.class.getDeclaredField("id");
AnnotatedType annotatedType = field.getAnnotatedType();
TypeHint hint = annotatedType.getAnnotation(TypeHint.class);
```

`Field.getAnnotatedType()` returns an `AnnotatedType` object describing the **declared type of the field**, including annotations at the type-use location. In contrast, `Field.getDeclaredAnnotation(TypeHint.class)` queries for an **annotation directly on the field declaration**; if the `TypeHint` type only has `@Target(TYPE_USE)`, that is not the right way to query the annotation on the type.

### 2.2 Parameter Type

Example:

```java
class AccountService {
    void find(@TypeHint("account-id") String id) {}
}
```

`@TypeHint` is on the `String` type of the `id` parameter. You can read the parameter types in order using:

```java
Method method = AccountService.class.getDeclaredMethod("find", String.class);
AnnotatedType[] parameterTypes = method.getAnnotatedParameterTypes();
TypeHint hint = parameterTypes[0].getAnnotation(TypeHint.class);
```

The `getAnnotatedParameterTypes()` array corresponds to the formal parameters of the method. In the example above, there is only one parameter, so element `[0]` represents the marked `String` type.

Do not confuse this API with `Method.getParameterAnnotations()`, which reads annotations on the **parameter declaration**. An annotation type with `@Target(PARAMETER)` is specifically for parameter declarations, whereas `@Target(TYPE_USE)` is specifically for type-use locations. An annotation declared to allow multiple `ElementType` values may have rules applying to both groups; when reading it, you must clearly identify which metadata you actually want.

### 2.3 Return Type

Example:

```java
class AccountService {
    public @TypeHint("result-type") String getName() {
        return "Lan";
    }
}
```

This is an annotation **on the returned `String` type**, not an annotation marking the `getName` method in the sense of `ElementType.METHOD`.

Querying the correct location with Reflection:

```java
Method method = AccountService.class.getDeclaredMethod("getName");
AnnotatedType returnType = method.getAnnotatedReturnType();
TypeHint hint = returnType.getAnnotation(TypeHint.class);
```

If you only query `method.getAnnotation(TypeHint.class)`, you are asking for metadata of the **method declaration**. The annotation on the return type is located in `getAnnotatedReturnType()`.

**A method can simultaneously have metadata in multiple locations**: on the method declaration itself, on the return type, on each parameter declaration, and on each parameter's type. The consumer must choose the corresponding API.

## 3. Comparing `TYPE_USE` with `FIELD`, `PARAMETER`, `METHOD`

| `ElementType` | What does it mark? | Conceptual example | Core Reflection API |
| --- | --- | --- | --- |
| `FIELD` | Field declaration | `@FieldTag private String id;` | `Field.getAnnotation(...)` |
| `TYPE_USE` on field | Type used to declare the field | `private @TypeTag String id;` | `Field.getAnnotatedType()` |
| `PARAMETER` | Parameter declaration | `void save(@ParamTag String id)` | `Parameter.getAnnotation(...)` or `Method.getParameterAnnotations()` |
| `TYPE_USE` on parameter | Type of the parameter | `void save(@TypeTag String id)` | `Method.getAnnotatedParameterTypes()` |
| `METHOD` | Method declaration | `@MethodTag String load()` | `Method.getAnnotation(...)` |
| `TYPE_USE` on return | Return type of the method | `@TypeTag String load()` | `Method.getAnnotatedReturnType()` |

The table examples use hypothetical annotation names `FieldTag`, `ParamTag`, `MethodTag`, and `TypeTag`; the corresponding types must be declared before compiling.

There are two points to keep in mind:

1. **The `@Target` target restricts valid locations**. Allowing only `FIELD` does not mean the annotation can be attached to a type argument such as `List<@Tag String>`; attaching it there requires `TYPE_USE`.
2. **Similar-looking source locations do not mean metadata resides in the same place when read by Reflection**. In particular, before a parameter type or before a return type, an annotation may belong to either a declaration context or a type-use context depending on what the annotation type is declared to support. Design and query the right kind of metadata.

### Example of Declaration and Type Annotations Side by Side

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface SensitiveField {}

@Target(ElementType.TYPE_USE)
@interface NonNullHint {}

class Customer {
    @SensitiveField
    private @NonNullHint String email;
}
```

`@SensitiveField` marks the **declaration of field `email`**, while `@NonNullHint` marks the **`String` type of the field**. This is a complete snippet in terms of declarations, but it has no `main` and is not intended to execute as a standalone program.

An annotation named `NonNullHint` **does not automatically make `String` forbid `null` values**. Java does not enforce nullability checks simply because a custom annotation is present. To check it, you need an annotation processor, a static analyzer, a validation framework, or runtime logic designed to understand that marker.

## 4. Complete Java 17+ Example: Querying Type Annotations

Create the file **`TypeUseLocationsDemo.java`**. The program demonstrates the three main locations as well as a type argument location in a generic; the annotations have `RUNTIME` retention so Reflection can read them.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface TypeMark {
    String value();
}

class DocumentStore {
    private @TypeMark("field-type") String id;

    private List<@TypeMark("generic-argument") String> labels;

    public @TypeMark("return-type") String find(
            @TypeMark("parameter-type") String key) {
        return key;
    }
}

public class TypeUseLocationsDemo {
    private static void printMark(String label, AnnotatedType type) {
        TypeMark mark = type.getAnnotation(TypeMark.class);
        System.out.println(label + ": "
                + (mark == null ? "(none)" : mark.value()));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field idField = DocumentStore.class.getDeclaredField("id");
        printMark("Field type", idField.getAnnotatedType());

        Method find = DocumentStore.class
                .getDeclaredMethod("find", String.class);
        printMark("Parameter type",
                find.getAnnotatedParameterTypes()[0]);
        printMark("Return type",
                find.getAnnotatedReturnType());

        Field labelsField = DocumentStore.class
                .getDeclaredField("labels");
        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) labelsField.getAnnotatedType();
        printMark("Generic argument",
                listType.getAnnotatedActualTypeArguments()[0]);

        System.out.println("Field declaration: "
                + idField.isAnnotationPresent(TypeMark.class));
        System.out.println("Method declaration: "
                + find.isAnnotationPresent(TypeMark.class));
    }
}
```

Compile/run with JDK 17+ in the directory containing the file:

```bash
javac -encoding UTF-8 TypeUseLocationsDemo.java
java TypeUseLocationsDemo
```

Stdout:

```text
Field type: field-type
Parameter type: parameter-type
Return type: return-type
Generic argument: generic-argument
Field declaration: false
Method declaration: false
```

### Line-by-Line Analysis

- `idField.getAnnotatedType()` reads `@TypeMark("field-type")` on the **field type**.
- `find.getAnnotatedParameterTypes()[0]` reads `@TypeMark("parameter-type")` on the **first parameter's type**.
- `find.getAnnotatedReturnType()` reads `@TypeMark("return-type")` on the **return type**.
- `labelsField.getAnnotatedType()` describes the type `List<String>`. Because this is a parameterized type, you can cast it to `AnnotatedParameterizedType` and then call `getAnnotatedActualTypeArguments()[0]`: this is the `String` type element inside `List<...>`.
- `idField.isAnnotationPresent(TypeMark.class)` is `false` because the `TypeMark` type **targets only `TYPE_USE`**, not the `FIELD` declaration.
- `find.isAnnotationPresent(TypeMark.class)` is `false` because an annotation on the **return type** is not an annotation on the **method declaration**.

Nothing in the example causes `find` to be invoked; we only read type information. The two fields do not need to be initialized because the code does not access **field values**. The consumer in the example is the Reflection calls in `main`, not an auto-executing framework.

If you omit `@Retention(RetentionPolicy.RUNTIME)`, the default retention of a custom annotation is `CLASS`; annotation data on types is no longer exposed through commonly used runtime Reflection APIs. Therefore, `RUNTIME` here is a prerequisite to demonstrate retrieving metadata at runtime.

## 5. A Type Annotation on a Field Type Differs from the Value Inside the Field

A type-use annotation is not an object that “sticks to” runtime data. Consider the example:

```java
class Inventory {
    @TypeMark("part-code")
    String codeA;

    String codeB;
}
```

Both fields have the Java type `String`; the annotation describes **how the type is used in the declaration of `codeA`**, rather than defining an entirely new `String` class. The same `String` value can be assigned to both fields (if other code allows it), and no error occurs automatically just because of this marker.

The complete example in Section 4 lets readers observe metadata per **individual field and method signature**: `@TypeMark("field-type")` belongs to the use of `String` in `DocumentStore.id`, while `@TypeMark("parameter-type")` belongs to the type of parameter `key` in the `find` method signature.

If you need a rule like “`email` must not be null”, decide clearly which processor enforces that rule. For example, static analysis might warn at compile time, whereas runtime validation will require code to be called before the data is used. Java SE does not automatically enforce the meaning of `NonNullHint` from the marker name.

## 6. The Generic Case: `List<@TypeMark String>`

`TYPE_USE` is not only used at the three outer positions. It can also describe a **type component deep inside a type expression**:

```java
import java.util.List;

class Report {
    List<@TypeMark("item-type") String> items;
}
```

Here `List` is the **outer container type**; `String` is the **type argument**. The annotation attaches to `String` inside `<...>`, not automatically to `List` or the `items` field.

Therefore:

- `field.getAnnotatedType()` returns information about the outer `List<String>` field type.
- After checking that the object is an instance of `AnnotatedParameterizedType`, use `getAnnotatedActualTypeArguments()` to obtain the argument types along with their annotations.
- The `AnnotatedType` object of the `String` argument can return `@TypeMark("item-type")` via `getAnnotation(TypeMark.class)`.

A processor handling metadata in generics needs to **traverse the type structure properly**. If it only checks `field.getAnnotation(TypeMark.class)`, it will miss information deep inside the type argument.

Similarly, with array types, the position of an annotation before the component type name and annotations at each array level can differ. Use `AnnotatedArrayType` and `getAnnotatedGenericComponentType()` when you need to inspect that structure; this article focuses on field, parameter, and return types.

## 7. How `TYPE_USE` Differs from `TYPE` and `TYPE_PARAMETER`

| Target | Core meaning | Example |
| --- | --- | --- |
| `ElementType.TYPE` | Attached to a class, interface, enum, annotation type, or record declaration | `@EntityLike class Order {}` |
| `ElementType.TYPE_USE` | Attached at a type-use location | `@TypeMark("x") String id;`, `List<@TypeMark("x") String>` |
| `ElementType.TYPE_PARAMETER` | Attached to a type parameter **declaration** | `class Box<@ParameterTag T> {}` |

The examples in the table are illustrative and require defining the corresponding annotation types.

The word `TYPE` in `TYPE_USE` does not mean it only attaches to a **class declaration**; it refers to *type contexts* such as field, parameter, and return types, casts, generic type arguments, and several other contexts permitted by Java. Moreover, `TYPE_USE` also applies at certain type/type-parameter declaration locations according to the language rules; this does not make it synonymous with `TYPE` or `TYPE_PARAMETER` in all situations. Always specify the exact locations you intend to support.

If you only want an annotation to be written on a class declaration, `@Target(TYPE)` expresses that intent more directly. If you want to annotate the **return type** of a method, `@Target(TYPE_USE)` is the appropriate target. If you want to mark the method declaration itself, choose `@Target(METHOD)`.

## 8. Annotations Used in Type Contexts: Compiler, Runtime, and Checking Tools

The fact that an annotation can appear on `String` or `List<String>` does not mean the compiler always knows what it means. There are three separate steps:

1. **Java checks syntax and location**: `@Target(TYPE_USE)` allows valid type-use locations, and the compiler verifies that metadata elements have the right types.
2. **Retention policy**: `@Retention(SOURCE)` lets a processor/analyzer work at compile time; `CLASS` keeps metadata in bytecode, though standard Reflection cannot see it; `RUNTIME` allows Reflection APIs that support annotated types to retrieve it.
3. **A processor interprets the meaning**: a static checker may understand `@NonNull`, a serialization library may read type annotations, or a framework may route custom processing. Without a consumer, an annotation remains just metadata.

Some annotations in validation/nullability libraries have very similar names yet differ in `@Target`, `@Retention`, and processing mechanisms. You should not rely on the name `NonNull` / `Nullable` to infer that an annotation definitely applies to type use or is definitely checked by Java.

### A Note on Reflection

The `getAnnotatedType()` API and related APIs represent annotations located at **type uses**. The `getAnnotations()` APIs directly on `Class`, `Method`, `Field`, or `Parameter` serve a different purpose; they are not the default mechanism for traversing an entire nested type tree.

If metadata sits inside `Map<@A String, List<@B Item>>`, the consumer must access the generic type and descend into the corresponding type arguments to read it completely. Reading “declaration annotations” and reading “type-tree annotations” are two independent operations.

## 9. Common Mistakes

**Mistake 1: Treating `@Target(TYPE_USE)` as a way to change Java's type system.** Annotations do not create new types on their own and do not make the compiler forbid null by default. A processor that understands the metadata is required.

**Mistake 2: Calling `Field.getAnnotation` to read an annotation attached only to the field type.** Choose `Field.getAnnotatedType()`, then read from the `AnnotatedType`.

**Mistake 3: Calling `Method.getAnnotation` to read a return-type annotation.** Choose `Method.getAnnotatedReturnType()`.

**Mistake 4: Calling `Method.getParameterAnnotations()` to read an annotation on a type argument of a generic parameter.** You need `getAnnotatedParameterTypes()` and to traverse further into the annotated type structure if necessary.

**Mistake 5: Thinking `FIELD`, `PARAMETER`, and `METHOD` are equivalent to `TYPE_USE`.** Those targets describe declaration kinds, whereas `TYPE_USE` refers to locations where types appear.

**Mistake 6: Forgetting retention when checking at runtime.** Custom annotations default to `CLASS`; to be readable by runtime Reflection, `RUNTIME` is required.

**Mistake 7: Thinking attaching an annotation to `List<@Mark String>` directly marks the `List` field.** The marker sits on the type argument `String`, so the consumer must traverse `AnnotatedParameterizedType`.

**Mistake 8: Ignoring the actual annotation type's `@Target`.** An annotation allowed by a framework on a method declaration is not necessarily allowed on a return type, even though they look very close in source code.

## 10. Self-Check Exercises

**Question 1.** Given `@Target(TYPE_USE) @interface Mark {}`, what does `private @Mark String name;` mark?

Answer: **The `String` type at the field `name` location**; it does not automatically mark every `String` value in the program.

**Question 2.** Can an annotation with only `@Target(METHOD)` be placed on `List<@Mark String>`?

Answer: **No.** That is a type argument, which requires an annotation supporting `TYPE_USE`.

**Question 3.** You attach `@TypeMark` to the return type of `load()`. Is `method.getAnnotation(TypeMark.class)` guaranteed to find it?

Answer: **No.** For an annotation that only supports `TYPE_USE`, use `method.getAnnotatedReturnType().getAnnotation(TypeMark.class)`.

**Question 4.** Which API retrieves `@TypeMark` on the first parameter type of a method?

Answer: `method.getAnnotatedParameterTypes()[0]`, and then read the annotation on that `AnnotatedType` object.

**Question 5.** Given `List<@TypeMark("element") String>`, why does accessing `field.getAnnotatedType().getAnnotation(TypeMark.class)` directly usually not find `"element"`?

Answer: Because the marker is on the **type argument `String`**, not on the outer `List` type. You must use `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.

**Question 6.** Can `@Target(TYPE_USE)` be combined with `@Retention(SOURCE)`?

Answer: **Yes.** Target specifies where the annotation may be attached, while retention specifies how long the metadata is retained. With `SOURCE`, a static analyzer/processor can read it at compile time, but runtime Reflection cannot see it.

**Question 7.** Does attaching a `TYPE_USE`-only `@NonNullHint` to `String` ensure that `String name = null;` will be rejected by javac?

Answer: **No.** A custom annotation does not inherently have null-checking behavior; you need a tool or processor that actually understands and enforces the rule.

**Question 8.** Why does the `TypeUseLocationsDemo` program print `Field declaration: false` while printing `Field type: field-type`?

Answer: Because the two APIs query two **different** metadata locations: the `FIELD` declaration and the type use of `String`.

Key takeaway: **`TYPE_USE` marks type-use locations**, whereas annotations attached to the declaration itself use targets such as `FIELD`, `PARAMETER`, and `METHOD`. To read a type annotation via Reflection, obtain the `AnnotatedType` at the exact field, parameter, or return-type location; for generics/arrays, continue descending into the type tree if the metadata lies at a deeper level.
