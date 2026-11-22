# 2.2 Primitive Types, `void`, Arrays, `interface`, `enum`, and `record` in the `Class` Model

In Java, `java.lang.Class` is the unified vantage point for inspecting **runtime types**. A `Class<?>` object can represent a regular class, interface, enum, record, array class, one of the eight primitive types, or `void`. That **does not mean** every represented type can be instantiated with `new`, has a constructor, or holds an object to pass to `isInstance`.

After this lesson, you should be able to accurately distinguish these type kinds through Reflection, understand the type relationships of arrays and special types, know how to choose the appropriate API to explore enums/records, and avoid drawing wrong conclusions from `getClass()`, `getSuperclass()`, or `isAssignableFrom()`.

## 1. One `Class<?>` Model, Many Type Natures

The following examples are all valid and all produce a `Class` object:

```java
Class<?> primitive = int.class;
Class<?> noReturn = void.class;
Class<?> array = String[][].class;
Class<?> abstraction = Runnable.class;
Class<?> enumeration = Thread.State.class;
Class<?> recordType = Record.class;
```

**Note:** `Record.class` is the base class `java.lang.Record`, **not** itself a `record` declaration; therefore `Record.class.isRecord()` returns `false`. To have an actual record type, you must declare, for example, `record Point(int x, int y) {}`, and then use `Point.class`.

`Class` answers two different groups of questions:

- **Type classification:** `isPrimitive()`, `isArray()`, `isInterface()`, `isEnum()`, `isRecord()`, `isAnnotation()`.
- **Structure and relationship inspection:** `getComponentType()`, `getSuperclass()`, `getInterfaces()`, `getEnumConstants()`, `getRecordComponents()`, `isAssignableFrom(...)`, `isInstance(...)`.

The classification flags do not substitute for one another. An interface can be an annotation type; an enum can implement an interface; a record can implement an interface; however, only an `enum` declaration has `isEnum() == true`, and only a `record` declaration has `isRecord() == true`.

| Type kind | `Class` example | Primary identification | Direct superclass according to Reflection |
| --- | --- | --- | --- |
| Primitive | `int.class`, `boolean.class` | `isPrimitive()` is `true` | `getSuperclass() == null` |
| `void` | `void.class` | Compare `type == void.class`; `isPrimitive()` is `false` | `null` |
| Array | `int[].class`, `String[][].class` | `isArray()` | `Object.class` |
| Interface | `Runnable.class` | `isInterface()` | `null` |
| Declared enum | `Thread.State.class` | `isEnum()` | `Enum.class` |
| Declared record | `Point.class` with `record Point(...)` | `isRecord()` | `Record.class` |

The table describes `Class.getSuperclass()`, not all type assignment relationships. For example, an array has `Object` as its superclass and simultaneously implements `Cloneable` and `java.io.Serializable`; an interface has no superclass but can extend multiple other interfaces.

## 2. Obtaining a `Class` Object Properly

There are three familiar ways with different scopes:

```java
Class<?> c1 = int.class;                  // class literal: works with primitive/void
Class<?> c2 = "hello".getClass();         // obtained from an actual object
Class<?> c3 = Class.forName("java.lang.String"); // lookup by binary name
```

- `T.class` is checked at compile time; it supports primitive types, `void`, arrays, and reference types.
- `value.getClass()` requires a non-`null` **reference object**. Primitive variables do not have a `getClass()` method. If you write `((Object) 7).getClass()`, boxing creates an `Integer`, so the result is `Integer.class`, **not** `int.class`.
- `Class.forName(String)` looks up the binary name of a reference type or the JVM representation name of an array class; **`Class.forName("int")` and `Class.forName("void")` throw `ClassNotFoundException`**. For primitive types and `void`, use a literal or the `TYPE` constant.

`Class.forName(String)` can also trigger class initialization if the class has not been initialized yet. When only metadata is needed in an analysis tool, consider the overload `Class.forName(name, false, loader)` and still handle `ClassNotFoundException`, access permissions, and the appropriate class loader. For arrays, use the descriptor-form array class name such as `"[I"` or `"[Ljava.lang.String;"`, not the display name `"int[]"` or `"java.lang.String[]"`.

`Class<?>` is a **metadata object**; it does not automatically create an instance of the corresponding type. Do not equate `Class` with an instance, or assume that seeing a `Class` means there is definitely a public constructor.

## 3. Eight Primitives and `void`: Having a `Class` Without Being a Reference Type

The eight primitives are `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Each type has exactly one corresponding `Class` in a JVM, such as `int.class`. The wrapper's `TYPE` constant matches the literal:

```java
System.out.println(int.class == Integer.TYPE);   // true
System.out.println(boolean.class == Boolean.TYPE); // true
System.out.println(void.class == Void.TYPE);      // true
System.out.println(int.class.isPrimitive());      // true
System.out.println(void.class.isPrimitive());     // false
System.out.println(Integer.class.isPrimitive());  // false
System.out.println(Void.class.isPrimitive());     // false
```

`void` expresses that a method returns no value; it is not a data type used to declare variables that hold values. Although `void.class` exists, there is no `void[]` array, no `void` instance can be created, and `void` is not among the eight types recognized by `isPrimitive()`. `Void.class` is the class `java.lang.Void`, distinct from `void.class`; having similar names does not make them the same type.

Reflection checks to remember:

```java
int.class.getSuperclass() == null             // true
void.class.getSuperclass() == null            // true
int.class.isInstance(Integer.valueOf(5))      // false
int.class.isAssignableFrom(int.class)         // true
long.class.isAssignableFrom(int.class)        // false
Number.class.isAssignableFrom(int.class)      // false
Number.class.isAssignableFrom(Integer.class)  // true
```

`isAssignableFrom` reflects type relationships in the runtime model, and **does not apply** numeric widening (`int` to `long`) or boxing (`int` to `Integer`) like Java's expression conversion rules. Similarly, `isInstance(Object)` cannot accept a primitive directly; the `Object` argument after boxing is a wrapper, so `int.class.isInstance(...)` remains `false`.

When writing a framework that receives method parameters, separate `int.class` and `Integer.class` precisely. They may need conversion/boxing rules at the method invocation layer, but they cannot substitute for each other via `isAssignableFrom` alone.

## 4. Arrays: Dynamically JVM-Generated Classes with Components and Dimensions

Every array in Java is a **reference object** with a `Class` dedicated to its element type and number of dimensions. `String[].class`, `String[][].class`, and `int[].class` are distinct types. `isArray()` recognizes them; `getComponentType()` returns the type of the element at **one dimension immediately inside**:

```java
int[][].class.isArray()                          // true
int[][].class.getComponentType() == int[].class  // true
int[].class.getComponentType() == int.class      // true
String[].class.getComponentType() == String.class // true
String.class.getComponentType() == null          // true
```

For `int[][]`, the component type is `int[]` (a reference type), whereas for `int[]`, the component type is the primitive `int`. To find the innermost element type, loop `getComponentType()` until `isArray()` is no longer true.

### 4.1. Array Names Used by Reflection

`getTypeName()` displays a human-readable name, while `getName()` of an array class returns the JVM type name:

| `Class` | `getTypeName()` | `getName()` |
| --- | --- | --- |
| `int[].class` | `int[]` | `[I` |
| `boolean[].class` | `boolean[]` | `[Z` |
| `double[][].class` | `double[][]` | `[[D` |
| `String[].class` | `java.lang.String[]` | `[Ljava.lang.String;` |
| `String[][].class` | `java.lang.String[][]` | `[[Ljava.lang.String;` |

One `[` for each dimension; primitive codes include `Z` (boolean), `B` (byte), `S` (short), `C` (char), `I` (int), `J` (long), `F` (float), `D` (double). For reference types, use `L<binary name>;`. The code `V` can appear in a method return type descriptor for `void`, but it **does not** form a valid `[V` array class.

If meant for human readers, prefer `getTypeName()`; if interacting with binary names/descriptors or `Class.forName`, pay attention to the `getName()` convention. `getSimpleName()` and `getCanonicalName()` serve different naming purposes; the canonical name can be `null` for local/anonymous classes, so do not assume every type has a canonical name.

### 4.2. Inheritance Relationships and Covariance

Any array is an `Object` and implements both `Cloneable` and `java.io.Serializable`:

```java
String[].class.getSuperclass() == Object.class        // true
Object.class.isAssignableFrom(int[].class)            // true
Cloneable.class.isAssignableFrom(int[].class)         // true
java.io.Serializable.class.isAssignableFrom(int[].class) // true
```

**Reference-type arrays are covariant:** because `String` is a subtype of `Object`, `String[]` is a subtype of `Object[]`.

```java
Object[].class.isAssignableFrom(String[].class) // true
Object[].class.isAssignableFrom(int[].class)    // false
Object[].class.isAssignableFrom(int[][].class)  // true
```

The last line is noteworthy: each element of `int[][]` is an `int[]` object; therefore `int[][]` is compatible with `Object[]`, whereas `int[]` is not. Arrays of primitives are not covariant to `Object[]` because the `int` element itself is not a reference object.

Covariance is additionally checked **at runtime** when writing elements:

```java
Object[] values = new String[1];
values[0] = "ok";             // valid
// values[0] = Integer.valueOf(3); // compiles but throws ArrayStoreException
```

The compiler only sees an `Object[]` variable, while the JVM protects the actual element type `String`. For APIs handling dynamic arrays, check `isArray()`, `getComponentType()`, and the element type before writing; the `java.lang.reflect.Array` library supports creating/reading/writing arrays via Reflection, but having an array `Class` does not mean the array accepts arbitrary element types.

## 5. Interface: A Reference Type That Can Have Multiple Superinterfaces

`Runnable.class.isInterface()` is `true`, even though you cannot do `new Runnable()` directly. For an interface:

- `getSuperclass()` always returns `null`, **not** `Object.class`.
- `getInterfaces()` gives the **directly declared** superinterfaces; to check the entire indirect relationship, use `isAssignableFrom()` or traverse the interface tree yourself.
- `Interface.class.isAssignableFrom(Concrete.class)` can be `true` if the class implements the interface directly or indirectly.
- `isInstance(object)` returns `true` if the object is an instance implementing that interface.

Example:

```java
interface Named { String name(); }
interface Audited extends Named {}
class Service implements Audited {
    @Override public String name() { return "service"; }
}
```

In code within the same compilation scope, `Named.class.isAssignableFrom(Service.class)` and `Audited.class.isAssignableFrom(Service.class)` are both `true`, while `Service.class.getInterfaces()` only contains `Audited.class`. `Named.class.getSuperclass()` equals `null`.

An annotation is also a kind of interface in Java's model: for `@interface Marker {}`, both `Marker.class.isAnnotation()` and `Marker.class.isInterface()` are `true`. If you need to classify annotations separately, check `isAnnotation()` **before** `isInterface()`. Do not use `Modifier.isInterface(getModifiers())` to distinguish annotations from regular interfaces; the `isAnnotation()` flag states the intent more clearly.

## 6. Enum: A Special Class with Fixed Constants

An enum such as `enum Direction { NORTH, SOUTH }` is a reference type generated by the compiler as a class directly derived from `java.lang.Enum<Direction>`, not an interface and not a primitive.

- `Direction.class.isEnum()` is `true`; `Enum.class.isEnum()` is `false`.
- `Direction.class.getSuperclass() == Enum.class` is `true` (the generic part `Enum<Direction>` can be viewed via `getGenericSuperclass()`).
- `Direction.class.getEnumConstants()` returns an array of constants in **declaration order**. For non-enum types, the method returns `null`, so check `isEnum()` before iterating.
- `Enum.valueOf(Direction.class, "NORTH")` looks up a constant by exact name; `name()` is the declared name, while `toString()` may be overridden by the enum to display differently.
- An enum can implement interfaces and have its own methods/fields; `getDeclaredFields()` may include other members as well, so do not retrieve constants simply by taking every field in the class.

**Common edge case:** an enum constant with its **own class body** has an anonymous runtime class. In that case `constant.getClass().isEnum()` may be `false`, even though `constant.getDeclaringClass().isEnum()` is still `true`.

```java
enum Mode {
    BASIC,
    CUSTOM {
        @Override String description() { return "custom"; }
    };
    String description() { return "basic"; }
}
```

With this declaration, `Mode.CUSTOM.getClass().isEnum()` returns `false`; `Mode.CUSTOM.getDeclaringClass() == Mode.class` returns `true`. The `getDeclaringClass()` method here belongs to the **`Enum` instance**, which is different from `Class.getDeclaringClass()` used to look up the declaring class of a nested/member type. If you need to determine the enum type from a **constant**, use `Enum.getDeclaringClass()`.

## 7. Record: A Data Class with an Explicit Component Structure

A record (standard since Java 16, fully available in Java 17+) is a **reference class** with public components declared in its header, for example:

```java
record Point(int x, int y) {}
record Person(String name, java.util.List<String> tags) {}
```

For `Point`, the compiler provides corresponding private final fields, `x()`/`y()` accessors, a canonical constructor, and default implementations for `equals`, `hashCode`, and `toString` (unless validly declared to replace them). A record has `java.lang.Record` as its direct superclass, is `final` by default, and can implement interfaces but cannot extend arbitrary classes. `Record.class.isRecord()` is `false`; `Point.class.isRecord()` is `true`.

A record carries a **shallow** notion of immutability: a component reference cannot be reassigned like an ordinary field, but the object it points to can still change if that object itself is mutable. For instance, `Person.tags()` can return a mutable `List`; do not automatically infer deep immutability.

Use `Class.getRecordComponents()` to retrieve metadata true to the record's nature, in header declaration order:

```java
for (java.lang.reflect.RecordComponent rc : Point.class.getRecordComponents()) {
    System.out.println(rc.getName() + ": " + rc.getType().getTypeName());
}
```

Output:

```text
x: int
y: int
```

Each `RecordComponent` provides `getName()`, `getType()` (erased type), `getGenericType()` (preserves generic information from the declaration if present), `getAccessor()`, and corresponding annotation metadata. For example, with `Person`, the `tags` component has `getType() == java.util.List.class`, while `getGenericType().getTypeName()` can display `java.util.List<java.lang.String>`.

`getRecordComponents()` returns **`null` if not a record**, and an **empty** array if it is a record with no components (`record Empty() {}`). Therefore, avoid calling `.length` or iterating directly before confirming `isRecord()`.

A record component is a header-level concept, not entirely identical to a JavaBeans property: the accessor is named `name()`, **not required** to be `getName()`. Iterating over all `getDeclaredFields()` and inferring components can easily confuse other fields or their order, because that API does not guarantee field order. When reading a record via Reflection, rely on `getRecordComponents()` and `getAccessor()`.

## 8. Complete Java 17+ Example: Comparing the Six Type Groups

Save the following snippet to **`ClassModelDemo.java`**. This is a standalone program containing an interface, an enum implementing the interface, and a record whose accessor automatically implements the interface:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

interface DisplayName {
    String displayName();
}

enum Stage implements DisplayName {
    NEW, DONE;
    @Override public String displayName() {
        return name();
    }
}

record Task(String displayName, int attempts) implements DisplayName {}

public class ClassModelDemo {
    public static void main(String[] args) {
        System.out.println("primitive(int): " + int.class.isPrimitive());
        System.out.println("primitive(void): " + void.class.isPrimitive());
        System.out.println("void == Void.TYPE: " + (void.class == Void.TYPE));
        System.out.println("Void.class primitive: " + Void.class.isPrimitive());

        System.out.println("array(int[][]): " + int[][].class.isArray());
        System.out.println("component(int[][]): "
                + int[][].class.getComponentType().getTypeName());
        System.out.println("name(int[][]): " + int[][].class.getName());
        System.out.println("name(String[]): " + String[].class.getName());
        System.out.println("array superclass Object: "
                + (String[].class.getSuperclass() == Object.class));
        System.out.println("array implements Cloneable: "
                + Cloneable.class.isAssignableFrom(String[].class));
        System.out.println("String[] -> Object[]: "
                + Object[].class.isAssignableFrom(String[].class));
        System.out.println("int[] -> Object[]: "
                + Object[].class.isAssignableFrom(int[].class));

        System.out.println("interface(DisplayName): "
                + DisplayName.class.isInterface());
        System.out.println("Stage implements DisplayName: "
                + DisplayName.class.isAssignableFrom(Stage.class));
        System.out.println("enum(Stage): " + Stage.class.isEnum());
        System.out.println("enum constants: "
                + Arrays.toString(Stage.class.getEnumConstants()));

        System.out.println("record(Task): " + Task.class.isRecord());
        System.out.println("record superclass Record: "
                + (Task.class.getSuperclass() == Record.class));
        System.out.println("record components:");
        for (RecordComponent component : Task.class.getRecordComponents()) {
            System.out.println("  " + component.getName() + ": "
                    + component.getType().getTypeName());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 ClassModelDemo.java
java ClassModelDemo
```

Exact stdout (excluding comment/shell command lines):

```text
primitive(int): true
primitive(void): false
void == Void.TYPE: true
Void.class primitive: false
array(int[][]): true
component(int[][]): int[]
name(int[][]): [[I
name(String[]): [Ljava.lang.String;
array superclass Object: true
array implements Cloneable: true
String[] -> Object[]: true
int[] -> Object[]: false
interface(DisplayName): true
Stage implements DisplayName: true
enum(Stage): true
enum constants: [NEW, DONE]
record(Task): true
record superclass Record: true
record components:
  displayName: java.lang.String
  attempts: int
```

Explanation of three easily confused points in the output: `void` has a `Class` literal but is not a primitive according to `isPrimitive`; `int[][]` has component `int[]` and binary name `[[I`; `Task` is a true record because it is declared with `record`, not merely because it directly extends `Record`. `Task` automatically generates the `displayName()` method with the same signature as the interface contract.

## 9. Checking Subtypes with `isAssignableFrom`: Mind the Direction

The syntax is **`Target.class.isAssignableFrom(Source.class)`**: whether a value of type `Source` can be treated as type `Target` in the reference/runtime assignment model. `Target` on the left is the side that **receives** the value.

| Expression | Result | Why |
| --- | --- | --- |
| `Object.class.isAssignableFrom(String.class)` | `true` | `String` is a subtype of `Object` |
| `Runnable.class.isAssignableFrom(Thread.class)` | `true` | `Thread` implements `Runnable` |
| `long.class.isAssignableFrom(int.class)` | `false` | Does not perform primitive widening |
| `Integer.class.isAssignableFrom(int.class)` | `false` | Does not auto-box |
| `Object.class.isAssignableFrom(int[].class)` | `true` | Arrays are objects |
| `Object[].class.isAssignableFrom(int[].class)` | `false` | The `int` element is primitive |
| `Object[].class.isAssignableFrom(int[][].class)` | `true` | Elements are `int[]` references |
| `Record.class.isAssignableFrom(Task.class)` | `true` | `Task` extends `Record` |

`isInstance(value)` is a check on an existing **object**, close to the runtime meaning of `instanceof`; for example `Runnable.class.isInstance(new Thread())` is `true`. Use `isAssignableFrom` when you have two `Class` objects, and use `isInstance` when you have a `Class` and an `Object` value. For primitive/void, `isInstance` cannot receive a primitive instance.

## 10. Classifying Types for Reflection Tools

The order of checks matters because `void` does not satisfy `isPrimitive()`, while an annotation satisfies `isInterface()`. The following method can be placed in a Java 17+ class:

```java
static String classify(Class<?> type) {
    if (type == void.class)   return "void";
    if (type.isPrimitive())   return "primitive";
    if (type.isArray())       return "array";
    if (type.isAnnotation())  return "annotation";
    if (type.isInterface())   return "interface";
    if (type.isEnum())        return "enum";
    if (type.isRecord())      return "record";
    return "ordinary class";
}
```

This is **an illustrative method**, not a standalone program file: add it to a class and call it from `main` to run. This order allows directly distinguishing the main declaration forms. An enum constant object with its own class body may be classified as `"ordinary class"` if `constant.getClass()` is passed; to classify the declared enum type, pass `constant.getDeclaringClass()`.

When building a mapper, serializer, DI container, debugger, or API documentation generator, choose separate processing paths: for arrays get the component type; for enums get constants; for records get components/accessors; for interfaces get contract information; for primitive/void handle with separate rules. Do not retrieve constructors or iterate over fields under a uniform assumption for every `Class`.

## 11. Common Mistakes and How to Fix Them

1. **Equating `int.class` with `Integer.class`.** Fix by distinguishing primitive and wrapper; `Integer.TYPE == int.class` but `Integer.class != int.class`. Reflection `isAssignableFrom` does not auto-box.
2. **Assuming `void.class.isPrimitive()` is `true`.** Fix with a separate `type == void.class` branch; do not create instances or arrays of `void`.
3. **Using `Class.forName("int")` or `Class.forName("String[]")`.** Fix by using class literals for primitives, and JVM descriptors like `"[I"` or `"[Ljava.lang.String;"` for arrays. `String[]` is not the binary name of the array class.
4. **Thinking `int[]` is an `Object[]`.** `int[]` is an `Object`, but its `int` elements are not references. Conversely, `int[][]` is compatible with `Object[]` because its elements are `int[]`.
5. **Writing into an `Object[]` pointing to a `String[]` with an arbitrary element type.** The compiler accepts some assignments, and the JVM may throw `ArrayStoreException`; guard by checking the actual element type.
6. **Concluding an interface has superclass `Object` because every implementation is an object.** `Interface.class.getSuperclass()` is actually `null`; use `getInterfaces()` and `isAssignableFrom()` to check contracts.
7. **Using `enumConstant.getClass().isEnum()` to find the declared enum.** Constants with a class body have an anonymous subclass; use `enumConstant.getDeclaringClass()`.
8. **Using `getDeclaredFields()` to infer record order and structure.** Use `getRecordComponents()` (in header order), `getAccessor()`, and `getGenericType()`; only call when `isRecord()` is true.
9. **Thinking records are deeply immutable, or every record has a `getX()` getter.** Component fields cannot be reassigned, but referenced mutable objects can still change; the standard accessor is named `x()`.
10. **Thinking `Class<?>` preserves all generic arguments.** `List<String>.class` is invalid; `List.class` is only the raw class after erasure. When declared generics are needed, inspect `Type`, `getGenericType()`, `getGenericSuperclass()`, or the appropriate generic Reflection APIs.

## 12. Self-Check

**Question 1.** Predict the results of `int[][].class.getComponentType().isArray()` and `int[][].class.getComponentType().getComponentType() == int.class`.

**Answer:** Both are `true`; `int[][] → int[] → int` with each call to get the component type.

**Question 2.** For `enum Flag { ON, OFF }`, what do `Flag.class.getEnumConstants().length`, `Enum.class.isEnum()`, and `Flag.class.isEnum()` return?

**Answer:** `2`, `false`, and `true`, respectively. `Enum` is the superclass of declared enums, but `Enum` itself is not an enum declaration.

**Question 3.** For `record Empty() {}`, what are `Empty.class.isRecord()`, `Empty.class.getRecordComponents().length`, and `Record.class.getRecordComponents()`?

**Answer:** `true`, `0`, and `null`. A record with no components is still a record; the superclass `Record` is not a record.

**Question 4.** Why is `Object[].class.isAssignableFrom(int[][].class)` `true` while `Object[].class.isAssignableFrom(int[].class)` is `false`?

**Answer:** In the first dimension of `int[][]`, the element is `int[]` (a reference object). Meanwhile, the element of `int[]` is the primitive `int`, so `int[]` cannot be treated as `Object[]`.

**Question 5.** Distinguish between `MyInterface.class.getInterfaces()`, `MyInterface.class.getSuperclass()`, and `MyInterface.class.isInterface()`.

**Answer:** The first API returns direct superinterfaces, the second API returns `null`, and the third API returns `true` if `MyInterface` is declared as an interface.

**Question 6.** If you need to get the name and generic type of the component in `record Holder(java.util.List<String> values) {}`, which API should you use?

**Answer:** `Holder.class.getRecordComponents()[0].getName()` and `getGenericType()`. `getType()` returns `List.class`, whereas `getGenericType()` retains the `String` information declared in the component signature.

## Standard Reference Documentation

- Java SE 21 `Class`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html — accurately describes `isPrimitive`, `isArray`, `isInterface`, `isEnum`, `isRecord`, `getEnumConstants`, `getRecordComponents`, and type relationships.
- Java SE 21 `RecordComponent`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html — `getType`, `getGenericType`, `getAccessor`, and component annotations.
- Java Language Specification, sections Arrays, Enum Classes, Record Classes: https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html ; https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html .