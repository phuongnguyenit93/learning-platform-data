# Field in Java Reflection: name, declaring class, raw type, and generic type

## 1. Objectives

When using Java Reflection to inspect a data field, the four fundamental questions are:

1. **What is the field's name?** → `Field.getName()`.
2. **Which class or interface actually declares the field?** → `Field.getDeclaringClass()`.
3. **What is the field's runtime type after generic erasure?** → `Field.getType()`.
4. **What is the type declared in the generic signature?** → `Field.getGenericType()`.

These four pieces of information serve different purposes. For example, a serializer needs the name to map the property, needs the declaring class to determine the declaration location, needs the raw type to know whether the field is a `List` or `Map`, and needs the generic type to know whether it is `List<String>` or `List<Integer>`. Do not use the result of one method to answer another method's question.

A `java.lang.reflect.Field` object is **metadata describing a field declaration** in a class/interface. It does not itself hold the field values of individual objects. To read a value, `field.get(receiver)` is needed; this operation involves access permissions and is not the focus of the four properties being studied.

Example:

```java
class Book {
    private String title;
    private java.util.List<String> tags;
}
```

With `Field f = Book.class.getDeclaredField("tags")`:

| Question | Method | Result |
|---|---|---|
| Field name? | `f.getName()` | `"tags"` |
| Who declared it? | `f.getDeclaringClass()` | `Book.class` |
| Raw type? | `f.getType()` | `java.util.List.class` |
| Generic type? | `f.getGenericType()` | A `ParameterizedType` object representing `java.util.List<java.lang.String>` |

This is an illustrative example of metadata, not yet a standalone program with a `main` method; a complete runnable program appears in section 8.

## 2. From `Class<?>` to a `Field` object

We obtain `Field` through `Class<?>`, not by creating `Field` with `new`:

```java
Class<?> type = Book.class;
Field tags = type.getDeclaredField("tags");
```

It requires `import java.lang.reflect.Field;` and handling `NoSuchFieldException`.

Common lookup APIs:

| `Class` API | What does it find? | Includes inherited fields? |
|---|---|---|
| `getDeclaredField(String name)` | A field declared by the current class/interface **itself**, regardless of `private`, `protected`, package-private, or `public` | No |
| `getDeclaredFields()` | All fields declared by the current class/interface **itself** | No |
| `getField(String name)` | A `public` field according to Reflection lookup rules | Possibly |
| `getFields()` | The `public` fields visible to the type according to API rules | Possibly |

**Declared does not mean private.** It only indicates that the field is declared directly on the type under inspection. Even a `public` field in a parent class will not appear in `Child.class.getDeclaredFields()` if `Child` does not declare that field.

With `getDeclaredField("x")`, if the current class does not declare `x`, Java throws `NoSuchFieldException`. If you want to look up an inherited `public` field, see `getField`. If you need to scan all parent classes, including non-public fields, you must manually traverse via `getSuperclass()` and call `getDeclaredFields()` on each class.

Note: Java Reflection **does not guarantee the order** of the array from `getDeclaredFields()` or `getFields()`. Schema-exporting tools that need a stable order must sort by name and their own rules. Additionally, the compiler can generate **synthetic fields**, so a tool that only cares about business fields sometimes needs to check `field.isSynthetic()` before processing.

## 3. `Field.getName()`: the field's name

API signature:

```java
String getName()
```

`getName()` returns **the field's name** as a `String`. This is the declared member name, not:

- The class name or package name.
- The field's value in an object.
- The JavaBeans property name following getter/setter conventions.
- A database column name or a JSON key name assigned by a framework.
- A name containing the generic type, modifiers, or declaring class.

Example:

```java
class Inventory {
    private long quantity;
    public static final int MAX_ITEMS = 100;
}
```

```java
Field one = Inventory.class.getDeclaredField("quantity");
Field two = Inventory.class.getDeclaredField("MAX_ITEMS");

System.out.println(one.getName()); // quantity
System.out.println(two.getName()); // MAX_ITEMS
```

The two snippets above must be placed in the same context with `Field` imported; they illustrate that a field's name does not depend on whether the field is an instance field or `static final`.

When mapping a `Field` to an external schema, **you should not use `getName()` as an immutable key name** if the source name may change. A framework may actively handle annotations or a naming strategy, such as camelCase to snake_case, but `Field.getName()` itself does not perform that transformation.

A class may contain compiler-generated fields whose names do not appear as normal declarations in source code. When scanning a business schema, consider `isSynthetic()` and appropriate exclusion rules.

## 4. `Field.getDeclaringClass()`: the actual declaring type

Signature:

```java
Class<?> getDeclaringClass()
```

The result is a `Class<?>` object representing **the type that declared the field**, regardless of which type the caller used to find the field.

Suppose:

```java
class Parent {
    public String id;
}

class Child extends Parent {
    public int age;
}
```

```java
Field inherited = Child.class.getField("id");
Field own = Child.class.getDeclaredField("age");

System.out.println(inherited.getDeclaringClass() == Parent.class); // true
System.out.println(own.getDeclaringClass() == Child.class);        // true
```

Because `id` is declared in `Parent`, looking it up via `Child.class` **does not change** its declaring class.

### 4.1. Distinguishing closely related concepts

| Expression | What does it ask? |
|---|---|
| `Child.class` | The `Class` chosen as the **lookup starting point** |
| `field.getDeclaringClass()` | The class/interface that **declares the field itself** |
| `field.getDeclaringClass().getName()` | The full name (binary name) of the declaring class |
| `field.getDeclaringClass().getSimpleName()` | The simple name, convenient for display but not guaranteed unique |
| `field.getClass()` | The runtime type of the **Reflection metadata object**, not the class declaring the field |
| `field.getType()` | The data type of the **field**, not the declaring class |

Do not use `field.getType()` to infer the class containing the field. For example, in `class User { String name; }`: the declaring class of `name` is `User`, while the raw type is `String`.

### 4.2. Inheritance, field hiding, and declaring class

Java allows a subclass to declare a field with the same name as its parent class (field hiding). The two fields remain **two distinct members** with different declaring classes, even when their names are identical:

```java
class Parent {
    public String code;
}

class Child extends Parent {
    public int code;
}
```

```java
Field parentCode = Parent.class.getDeclaredField("code");
Field childCode = Child.class.getDeclaredField("code");

System.out.println(parentCode.getName().equals(childCode.getName())); // true
System.out.println(parentCode.getDeclaringClass() == Parent.class);    // true
System.out.println(childCode.getDeclaringClass() == Child.class);      // true
System.out.println(parentCode.getType() == childCode.getType());      // false
```

Do not identify a field solely by name if scanning multiple inheritance levels. A sensible identifier key in an analysis system can consist of **declaring class and field name** (along with class loader context when needed), because `Parent.code` and `Child.code` are two different fields.

When scanning a system with multiple class loaders, a string class name is also insufficient to accurately determine `Class` identity. Two class loaders can load types with the same binary name but different identities.

## 5. `Field.getType()`: raw type at runtime

Signature:

```java
Class<?> getType()
```

The result is always a `Class<?>`, describing **the field's type at runtime after generic erasure rules**. For non-generic fields, this is simply the normal declared type; for generic type parameters, type argument information is generally not present in the `getType()` result.

Example:

```java
class Data {
    String title;
    int count;
    int[] scores;
    java.util.List<String> names;
    java.util.Map<String, Integer> ages;
}
```

| Field | `getType()` | `getType().getTypeName()` |
|---|---|---|
| `title` | `String.class` | `java.lang.String` |
| `count` | `int.class` | `int` |
| `scores` | `int[].class` | `int[]` |
| `names` | `List.class` | `java.util.List` |
| `ages` | `Map.class` | `java.util.Map` |

Because `List<String>` and `List<Integer>` both have the raw type `List.class`, comparing `getType()` alone **does not distinguish** them. Similarly, `Map<String, Integer>` and `Map<String, Long>` both return `Map.class`.

For a field declared using a type variable:

```java
class Holder<T extends Number> {
    T value;
    T[] values;
}
```

`getType()` of `value` is `Number.class` because the erasure of `T extends Number` uses the first bound `Number`. For `values`, the erasure is `Number[]`. If `T` has no explicit bound, the erasure is normally `Object`; when there are multiple bounds, the first bound determines the erasure.

A practical point: `getType()` returns a `Class` that can be used with `isPrimitive()`, `isArray()`, `getComponentType()`, and `isAssignableFrom()`. However, checking type assignability with `Class.isAssignableFrom` is a different topic from recovering generic type arguments.

## 6. `Field.getGenericType()`: declared type, including generic signature

Signature:

```java
Type getGenericType()
```

`java.lang.reflect.Type` is a common interface for multiple forms of type descriptions in Reflection. `getGenericType()` reads type information according to the generic declaration (when the necessary metadata is present); **it does not determine the kind of object currently assigned to the field**.

Common forms:

| `Type` kind | Meaning | Field example |
|---|---|---|
| `Class<?>` | Non-parameterized type / primitive / regular array type | `String name`, `int age`, `String[] names` |
| `ParameterizedType` | Generic type used with type arguments | `List<String> tags`, `Map<String, Integer> counts` |
| `TypeVariable<?>` | Type variable declared on a class/method/constructor | `T value` in `class Box<T>` |
| `GenericArrayType` | Array whose component type is a parameterized type or type variable | `T[] items`, `List<String>[] groups` |
| `WildcardType` | Wildcard typically appearing as a type argument inside `ParameterizedType` | `List<? extends Number> numbers`: the wildcard is the argument inside `List` |

**Note:** For `List<? extends Number> numbers`, `field.getGenericType()` returns the **`ParameterizedType`** of `List<...>`; you only encounter `WildcardType` when retrieving elements of `getActualTypeArguments()`. Do not cast the result of `getGenericType()` directly to `WildcardType` in this case.

### 6.1. `ParameterizedType`

Example:

```java
Field field = Data.class.getDeclaredField("names");
Type type = field.getGenericType();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
    System.out.println(raw.getTypeName());
    System.out.println(arguments[0].getTypeName());
}
```

In the context of `Data.names` being `List<String>` from section 5, output:

```text
java.util.List
java.lang.String
```

This is a non-standalone illustrative snippet: it requires importing `Field`, `Type`, `ParameterizedType`, and defining `Data`. `ParameterizedType.getRawType()` returns a `Type`; in the case of `List<String>` it represents `java.util.List`. The `String` argument is in `getActualTypeArguments()`.

With a nested type `Map<String, List<Integer>>`, the second type argument of `Map` is itself a `ParameterizedType`. To reach `Integer`, you must traverse level by level, **not just read one level**.

### 6.2. `TypeVariable<?>`

With `class Box<T extends Number> { T value; }`:

- `getType()` of `value` → `Number.class`.
- `getGenericType()` of `value` → `TypeVariable<?>` named `T`.
- `((TypeVariable<?>) type).getBounds()` returns the list of declared upper bounds; in the example above it has `Number`.

Do not confuse bound information with a concrete type argument. Knowing `T extends Number` only guarantees that `T` has an upper bound constraint; it **does not say** whether a particular instance currently holds an `Integer` or a `Double`.

### 6.3. `GenericArrayType`

Example:

```java
class Bag<T extends Number> {
    T[] values;
    java.util.List<String>[] groups;
}
```

- `values`: `getType()` is `Number[].class` while `getGenericType()` is `GenericArrayType` with generic component type being variable `T`.
- `groups`: `getType()` is `List[].class`, while `getGenericType()` represents an array with component type `List<String>`, typically a `GenericArrayType`.
- Regular `int[]` or `String[]` uses `Class<?>` for `getGenericType()` because the component is not a type variable or parameterized type.

`GenericArrayType.getGenericComponentType()` gives access to the generic element type. You should not cast `getGenericType()` of every array field to `Class<?>`.

### 6.4. `WildcardType`

With the field:

```java
java.util.List<? extends Number> numbers;
```

We retrieve the wildcard from the type argument of `List`:

```java
ParameterizedType listType =
        (ParameterizedType) field.getGenericType();
Type argument = listType.getActualTypeArguments()[0];

if (argument instanceof WildcardType wildcard) {
    Type[] uppers = wildcard.getUpperBounds();
    Type[] lowers = wildcard.getLowerBounds();
    // Here the upper bound is Number and there is no explicit lower bound.
}
```

This snippet requires `field` pointing to the `numbers` field, along with Reflection imports; it is not a standalone program. With `List<? super Integer>`, `getLowerBounds()` contains `Integer`; the default upper bound is `Object`. With `List<?>`, the default upper bound is `Object` and lower bounds are empty.

### 6.5. Type variables are not automatically "resolved" through subclasses

Consider:

```java
class Box<T> {
    public T item;
}

class StringBox extends Box<String> {
}
```

When calling:

```java
Field inherited = StringBox.class.getField("item");
System.out.println(inherited.getDeclaringClass() == Box.class); // true
System.out.println(inherited.getGenericType().getTypeName());   // T
```

The metadata of field `item` **is declared in `Box<T>`**, so `getGenericType()` yields `T`, even when looked up via `StringBox.class`. It does not automatically turn into `String.class`.

To infer `T = String` in the subclass context, you need to analyze the generic superclass/interface relationship (`StringBox.class.getGenericSuperclass()` returns a form containing `Box<String>`), then build a mapping from type variables to type arguments and apply it across inheritance levels. Java Reflection provides the data to do this, but **there is no single `Field.getGenericType()` operation that automatically performs the entire mapping according to a runtime object**.

## 7. Comparing `getType()` and `getGenericType()` across scenarios

| Field declaration | `getType().getTypeName()` result | `getGenericType().getTypeName()` result |
|---|---|---|
| `String name` | `java.lang.String` | `java.lang.String` |
| `int count` | `int` | `int` |
| `String[] names` | `java.lang.String[]` | `java.lang.String[]` |
| `List<String> tags` | `java.util.List` | `java.util.List<java.lang.String>` |
| `Map<String, Integer> scores` | `java.util.Map` | `java.util.Map<java.lang.String, java.lang.Integer>` |
| `T value`, in `T extends Number` | `java.lang.Number` | `T` |
| `T[] values`, in `T extends Number` | `java.lang.Number[]` | `T[]` |
| `List<? extends Number> ranks` | `java.util.List` | `java.util.List<? extends java.lang.Number>` |

The strings above are the typical display format of `Type.getTypeName()` on Java 17. They are very useful for observation/logging, but when **analyzing type structure** use `instanceof` with `Class`, `ParameterizedType`, `TypeVariable`, `GenericArrayType`, and `WildcardType`. Do not parse generics by splitting strings at `<`, commas, or `>`: that approach fails with nested types, nested classes, and many other type kinds.

A generic `Type` may point to an unloadable class or invalid signature metadata; when reading generic signatures, Reflection can throw errors such as `TypeNotPresentException`, `MalformedParameterizedTypeException`, or `GenericSignatureFormatError` in corrupted/missing metadata contexts. For tools analyzing bytecode from not-fully-controlled sources, you should handle these cases intentionally.

## 8. Runnable Java 17+ program: observing all four properties

Create file **`FieldMetadataDemo.java`** with the content:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;
import java.util.Map;

public class FieldMetadataDemo {
    static class Parent {
        public String inheritedCode;
        public String code;
    }

    static class Box<T extends Number> extends Parent {
        private String label;
        public T value;
        public T[] values;
        public List<String> tags;
        public Map<String, List<? extends Number>> scores;
        public int[] counts;
        public int code;
    }

    static class IntegerBox extends Box<Integer> {
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Field tags = Box.class.getDeclaredField("tags");

        System.out.println("Name: " + tags.getName());
        System.out.println("Declaring: "
                + tags.getDeclaringClass().getSimpleName());
        System.out.println("Raw type: " + tags.getType().getTypeName());
        System.out.println("Generic type: "
                + tags.getGenericType().getTypeName());

        ParameterizedType tagsType =
                (ParameterizedType) tags.getGenericType();
        System.out.println("Tags argument: "
                + tagsType.getActualTypeArguments()[0].getTypeName());

        Field value = Box.class.getDeclaredField("value");
        Type valueGeneric = value.getGenericType();
        TypeVariable<?> variable = (TypeVariable<?>) valueGeneric;

        System.out.println("Value raw: " + value.getType().getTypeName());
        System.out.println("Value generic: " + valueGeneric.getTypeName());
        System.out.println("Value bound: "
                + variable.getBounds()[0].getTypeName());

        Field values = Box.class.getDeclaredField("values");
        Type valuesGeneric = values.getGenericType();
        GenericArrayType genericArray = (GenericArrayType) valuesGeneric;

        System.out.println("Values raw: "
                + values.getType().getTypeName());
        System.out.println("Values generic: " + valuesGeneric.getTypeName());
        System.out.println("Array component: "
                + genericArray.getGenericComponentType().getTypeName());

        Field scores = Box.class.getDeclaredField("scores");
        ParameterizedType scoresType =
                (ParameterizedType) scores.getGenericType();
        ParameterizedType nestedList = (ParameterizedType)
                scoresType.getActualTypeArguments()[1];
        WildcardType wildcard = (WildcardType)
                nestedList.getActualTypeArguments()[0];

        System.out.println("Scores raw: "
                + scores.getType().getTypeName());
        System.out.println("Scores generic: "
                + scores.getGenericType().getTypeName());
        System.out.println("Wildcard upper: "
                + wildcard.getUpperBounds()[0].getTypeName());

        Field inherited = IntegerBox.class.getField("inheritedCode");
        Field childCode = Box.class.getDeclaredField("code");
        Field parentCode = Parent.class.getDeclaredField("code");

        System.out.println("Inherited declaring: "
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("Hidden parent declaring: "
                + parentCode.getDeclaringClass().getSimpleName());
        System.out.println("Hidden child declaring: "
                + childCode.getDeclaringClass().getSimpleName());

        Field subclassValue = IntegerBox.class.getField("value");
        System.out.println("Subclass field generic: "
                + subclassValue.getGenericType().getTypeName());
        System.out.println("Subclass generic parent: "
                + IntegerBox.class.getGenericSuperclass().getTypeName());
    }
}
```

Run in the directory containing the file, using JDK 17 or newer:

```bash
javac FieldMetadataDemo.java
java FieldMetadataDemo
```

Expected output:

```text
Name: tags
Declaring: Box
Raw type: java.util.List
Generic type: java.util.List<java.lang.String>
Tags argument: java.lang.String
Value raw: java.lang.Number
Value generic: T
Value bound: java.lang.Number
Values raw: java.lang.Number[]
Values generic: T[]
Array component: T
Scores raw: java.util.Map
Scores generic: java.util.Map<java.lang.String, java.util.List<? extends java.lang.Number>>
Wildcard upper: java.lang.Number
Inherited declaring: Parent
Hidden parent declaring: Parent
Hidden child declaring: Box
Subclass field generic: T
Subclass generic parent: FieldMetadataDemo$Box<java.lang.Integer>
```

**Result analysis:**

1. `tags.getName()` returns the exact name as declared; `getDeclaringClass()` is `Box`, even though the field `tags` has type `List`.
2. `tags.getType()` only keeps `List`. `tags.getGenericType()` keeps the `String` type argument, so the metadata is represented as a `ParameterizedType`.
3. The `value` field declared as `T extends Number` has raw type `Number`, but its generic type is variable `T`; `TypeVariable.getBounds()` returns `Number`.
4. The `values` field declared as `T[]` has raw type `Number[]` and generic type `T[]`. `GenericArrayType.getGenericComponentType()` returns `T`.
5. The `scores` field has nested generics; to get the wildcard bound you must descend through `Map` → `List` → wildcard. The type argument `? extends Number` has upper bound `Number`.
6. `IntegerBox.class.getField("inheritedCode")` returns `Parent`'s field. The same name `code` in `Parent` and `Box` forms **two Fields** with different declaring classes.
7. `IntegerBox.class.getField("value")` returns the Field declared on `Box`, so the generic type is still `T`. The generic superclass of `IntegerBox` has `Box<Integer>`, which is **separate** metadata to examine when resolving type variables.

In the last line, `IntegerBox.class.getGenericSuperclass().getTypeName()` displays the binary name of the nested class `Box` as `FieldMetadataDemo$Box<...>`. The `$` symbol is part of the binary name of a nested class, not a formatting error.

In the example, nested classes are used to place all types in **a single file**. The names shown via `getSimpleName()` are `Box`/`Parent`; distinguish this from `Class.getName()`, which includes the enclosing name and the `$` symbol for nested classes.

## 9. Simple and order-stable metadata traversal

When building a schema-reading tool, we often want to list fields by name, declaring class, raw type, and generic type. An illustrative helper:

```java
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public final class FieldPrinter {
    public static void printDeclaredFields(Class<?> type) {
        Field[] fields = type.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName));

        for (Field field : fields) {
            if (field.isSynthetic()) {
                continue;
            }

            System.out.println(
                    field.getDeclaringClass().getName() + "#"
                    + field.getName() + " : "
                    + field.getType().getTypeName() + " / "
                    + field.getGenericType().getTypeName());
        }
    }
}
```

This snippet is a **utility class** without `main` and needs to be called from another program, e.g., `FieldPrinter.printDeclaredFields(SomeClass.class)`. It only **reads metadata** and does not require `setAccessible(true)` to obtain the name/type.

Sorting with `Comparator.comparing(Field::getName)` ensures a stable order **within a list of declared fields of the same class**; if you combine fields from multiple classes in the same hierarchy (which may have duplicate names), add the declaring class to the sort criteria. Code that prints the generic type with `getTypeName()` is for display; a real analyzer should inspect the `Type` structure as in section 6.

`getDeclaredFields()` can return private, protected, or package-private fields, but **only lists metadata**. If you proceed to read values with `Field.get(receiver)`, access permissions must be checked separately. Finding a field does not mean having permission to use it.

## 10. Practical applications of the four properties

### 10.1. JSON mapping / object serialization

A mapper can build a schema as follows:

- `getName()`: default property name, before considering annotations/naming strategies.
- `getDeclaringClass()`: find the original field in the hierarchy, distinguishing hidden fields.
- `getType()`: handle primitives, arrays, enums, and collections/maps at the class level.
- `getGenericType()`: read `List<Order>`, `Map<String, Price>`, or type variables to decide how to handle elements.

If `getGenericType()` is omitted, the mapper only sees `List` and may lose the **declared** element type information. However, if a field declares `T` in a generic superclass, `getGenericType()` alone **is not enough** to infer what `T` is in a concrete subclass.

### 10.2. Dependency injection / framework scanning

A framework can read annotated fields, determine the raw type to find candidate beans, and use the generic type to resolve injection points such as `Repository<User>`. Whether a field resides in a superclass affects the declaring class, annotations, and processing order.

Do not infer that two fields sharing the same raw type have the same injection meaning: `Repository<User>` and `Repository<Order>` share the same raw type `Repository` but have different type arguments.

### 10.3. API schema / validation

A data description generator tool can display field names and declarations; it needs to distinguish:

- `String` vs `List<String>`;
- `List<? extends Number>` vs `List<Number>`;
- `T extends Number` vs a concrete type `Integer`;
- a field in a parent class vs a field hidden by a child class.

That metadata describes **constraints and declared signatures**, and cannot by itself guarantee that runtime state/values satisfy all conditions if the framework still allows raw/unchecked data.

## 11. Common mistakes

| Mistake | Why is it wrong? | Correct approach |
|---|---|---|
| Using `getName()` to get the String value of a field | `getName()` only returns the declared name | To read the value, use `get(receiver)` and handle permissions |
| Using `getType()` to distinguish `List<String>` and `List<Integer>` | Both are erased to `List.class` | Analyze `getGenericType()` |
| Casting every `getGenericType()` to `ParameterizedType` | Primitives, regular classes, type variables, or generic arrays have other `Type` kinds | Check `instanceof` and handle by branch |
| Assuming `getDeclaringClass()` is always equal to the class used to call `getField` | Public fields can be inherited | Read the declaring class on the `Field` itself |
| Assuming a hidden field is the same field | Two classes declare two different members | Distinguish by declaring class and name |
| Assuming `getGenericType()` of field `T` returns `String` when the subclass is `Box<String>` | Metadata stores the declared signature at `Box<T>` | Analyze the generic superclass/interface and map type variables |
| Reading a wildcard by directly casting `List<? extends Number>` to `WildcardType` | The outer type is `ParameterizedType` | Get the wildcard from `getActualTypeArguments()` |
| Relying on the order of `getDeclaredFields()` | The API promises no specific order | Sort yourself |
| Trying to open private access just to read metadata | Metadata such as name, declaring class, and type does not require reading values | Only check permissions when actually calling `get`/`set` |
| Treating a string class name as a global identity | Different class loaders can create different `Class` objects with the same name | Use `Class<?>`/loader in the proper context when needed |
| Splitting `Type.getTypeName()` strings to "parse" generics | Nested generics/wildcards/arrays make manual parsing error-prone | Branch on the `Type` structure |

## 12. Checklist and self-check questions

Checklist when inspecting a field:

1. Identify the **lookup class** using `SomeClass.class`, `instance.getClass()`, or a valid `Class<?>` source.
2. Choose `getDeclaredField(s)` if you need direct declarations; choose `getField(s)` if you want to query potentially inherited public fields.
3. Read `field.getName()` and `field.getDeclaringClass()` to identify the field.
4. Read `field.getType()` for the erased type as `Class<?>`.
5. Read `field.getGenericType()` for the generic declaration, checking `instanceof` to analyze the `Type` structure.
6. For field `T`, if you need the subclass's concrete type argument, build a type variable mapping across the generic hierarchy.
7. When reading/writing values, handle permissions and receiver separately from metadata; do not assume `getDeclaredField` has granted access.
8. For a scanner, decide how to handle synthetic fields, hidden fields, and listing order.

Self-check:

- A field declared as `List<String> names`: how do `getType()` and `getGenericType()` differ?
- `Child.class.getField("id")` finds a field declared by `Parent`: what does `getDeclaringClass()` return?
- In `class Box<T extends Number> { T value; T[] values; }`, what are the raw types of the two fields?
- What kind of `Type` does `getGenericType()` return for `List<? extends Number>`? Where do you get `WildcardType`?
- When field `T` is declared in `Box<T>`, why might looking it up via `Box<String>` through a subclass still show `T`?
- Why must `Parent.code` and `Child.code` be treated as two separate fields?
- When a tool only needs to list private field names/types, is it strictly necessary to call `setAccessible(true)`?

**Remember:** `Field.getName()` is the **name**, `getDeclaringClass()` is the **declaring location**, `getType()` is the **erased type as a `Class`**, and `getGenericType()` is the **declared signature type as a `Type`**. These four answers work together to understand a field's structure; none of them automatically reveals the field's value or grants access to that value.

Java 17 standard documentation: [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html), [`ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html).