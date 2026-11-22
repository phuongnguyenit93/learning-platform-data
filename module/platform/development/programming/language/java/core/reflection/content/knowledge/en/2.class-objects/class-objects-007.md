# Class Representing Primitives, void, Arrays, Interfaces, Enums, and Records

## 1. Why do all of these types have a Class object?

In Java Reflection, `java.lang.Class<?>` is the object describing **a type at runtime**. Not only ordinary classes like `String`, Java also has `Class` objects for the eight primitive types, `void`, every array type, interfaces, enums, and records. You use it to query which category a type belongs to, what components it has, and what inheritance/implementation relationships it participates in.

A `Class` object is **not** an instance of the type being described. For example, `int.class` describes the `int` type, yet it is itself an object of type `Class`; `void.class` exists even though no `void` value can be created. The declared type of a variable holding metadata is typically `Class<?>` so it can accept many different kinds of types.

| Described kind | Example of getting `Class` | Typical check | Meaning |
| --- | --- | --- | --- |
| Primitive | `int.class`, `boolean.class` | `isPrimitive()` | One of the eight primitive types |
| `void` | `void.class` | `isPrimitive()` returns `true`; compare separately with `void.class` | Represents the absence of a return value |
| Array | `String[].class`, `int[][].class` | `isArray()` | Array type, independent of its component type |
| Interface | `Runnable.class` | `isInterface()` | Interface type; annotations are also interfaces |
| Enum | `Level.class` with `enum Level` | `isEnum()` | Enum class declared in source code |
| Record | `Person.class` with `record Person(...)` | `isRecord()` | Record class and its list of record components |

An ordinary class such as `String.class` can return `false` for **all** of the checks in the table; that does not mean `Class` fails to recognize it. These checks classify characteristics of the type, not a test of "is this a `Class` object or not".

## 2. Ways to get a Class object

- **Class literal**: `int.class`, `void.class`, `int[].class`, `Runnable.class`, `Level.class`, `Person.class`. This is the clearest way when the type is known at compile time.
- **From an object**: `value.getClass()` tells the runtime class of the object. `getClass()` cannot be called on primitive values or `void`; when a primitive is boxed, the result is the wrapper class (`Integer`, `Boolean`, etc.), not the primitive type.
- **From a type name at runtime**: `Class.forName("java.lang.String")` searches by binary name. For arrays, the input name must follow JVM syntax, such as `"[I"` for `int[]` and `"[[Ljava.lang.String;"` for `String[][]`. Neither `Class.forName("int")` nor `Class.forName("java.lang.String[]")` works for lookup and both throw `ClassNotFoundException`.

Example:

~~~java
Class<?> primitive = int.class;
Class<?> noValue = void.class;
Class<?> array = String[][].class;
Class<?> wrapper = Integer.valueOf(42).getClass();

System.out.println(primitive == Integer.TYPE);    // true
System.out.println(noValue == Void.TYPE);          // true
System.out.println(wrapper == Integer.class);      // true
System.out.println(wrapper == int.class);          // false
~~~

The snippet above is a **fragment placed inside a Java method**, not a standalone program. `Integer.TYPE` and `Void.TYPE` reference the `Class` objects of `int` and `void`, respectively. `Class.forName(String)` can trigger class initialization; if you only need to load metadata without initializing the class, there is the overload `Class.forName(name, false, loader)` (which still requires a valid name and an appropriate class loader).

## 3. Primitives and void: same isPrimitive(), different semantics

Java has eight primitives: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, and `double`. Each type has its own `Class` provided by the JVM. **`void.class.isPrimitive()` also returns `true`** according to the `Class` API contract, even though `void` is not a type for variables or objects with values; that is a special case to handle before classifying "primitives with values".

~~~java
System.out.println(int.class.isPrimitive());     // true
System.out.println(void.class.isPrimitive());    // true
System.out.println(Integer.class.isPrimitive()); // false
System.out.println(int[].class.isPrimitive());   // false
System.out.println(void.class.getName());        // void
~~~

Notes:

- `int.class != Integer.class`: primitive and wrapper are two different types; autoboxing does not make them the same `Class` object.
- `Class#isInstance(Object)` cannot replace checking primitive values: the value passed to the `Object` parameter must be a reference, and `int.class.isInstance(Integer.valueOf(1))` returns `false`.
- There is no valid `void[]`, and no object can be created with `void.class`. When reflecting on methods, `Method#getReturnType() == void.class` indicates the method returns `void`.
- `getSuperclass()` for primitives and `void` returns `null`; `isInterface()` and `isArray()` both return `false`.

## 4. Arrays: an array's Class differs from its component's Class

Every array type has its own `Class`: `int[].class` differs from `int.class`, and `int[][].class` differs from `int[].class`. Arrays are always **reference types** even when holding primitive elements. Java provides `isArray()` and `getComponentType()` to peel off one dimension at a time:

~~~java
Class<?> matrix = int[][].class;
System.out.println(matrix.isArray());                           // true
System.out.println(matrix.getComponentType() == int[].class);  // true
System.out.println(matrix.getComponentType()
                         .getComponentType() == int.class);     // true
System.out.println(String.class.getComponentType() == null);    // true
~~~

`getComponentType()` removes only **one** array dimension each time. `Class#getTypeName()` is convenient for displaying human-readable names, whereas an array's `getName()` returns JVM descriptor syntax:

| Expression | Value |
| --- | --- |
| `int[].class.getName()` | `[I` |
| `int[][].class.getName()` | `[[I` |
| `String[].class.getName()` | `[Ljava.lang.String;` |
| `String[][].class.getName()` | `[[Ljava.lang.String;` |
| `String[][].class.getTypeName()` | `java.lang.String[][]` |

The `[` character denotes one dimension; `I` is the descriptor for `int`, while `L...;` wraps the binary name of a reference class. Given an array object, `Array.getLength(array)` reads the element count and `Array.newInstance(componentType, length)` creates an array via reflection. `int[].class.getSuperclass() == Object.class` is `true`; every array type also implements `Cloneable` and `java.io.Serializable`. They are **not** classified as primitives just because their elements are primitives.

## 5. Interfaces: detection and determining type assignability

`SomeInterface.class.isInterface()` returns `true` for interfaces; `getSuperclass()` of an interface returns `null`. To know whether a class can be assigned to an interface variable, use `isAssignableFrom` in the right direction:

~~~java
interface Reader { void read(); }
final class FileReaderImpl implements Reader {
    public void read() {}
}

System.out.println(Reader.class.isInterface());                    // true
System.out.println(Reader.class.isAssignableFrom(
        FileReaderImpl.class));                                     // true
System.out.println(FileReaderImpl.class.isAssignableFrom(
        Reader.class));                                             // false
~~~

This is a fragment describing types and statements in a valid context; a complete standalone program is in section 8. Read `A.class.isAssignableFrom(B.class)` as: "Can an object of type `B` be assigned to a variable of type `A`?". `Reader.class.isInstance(new FileReaderImpl())` also returns `true`; it checks **an object**, whereas `isAssignableFrom` compares **two types**.

An annotation declared with `@interface` is also a kind of interface. Thus, for an annotation type, both `isInterface()` and `isAnnotation()` can be `true`. If a program must distinguish annotations from regular interfaces, check `isAnnotation()` first.

## 6. Enums: recognizing enum classes and retrieving constants

For `enum Level { LOW, HIGH }`, `Level.class.isEnum()` returns `true`. `Level.class.getEnumConstants()` returns a `Level[]` array containing the constants in declaration order; for non-enum types, `getEnumConstants()` returns `null`. An empty result array for an enum is valid if the enum declares no constants.

~~~java
enum Level { LOW, HIGH }

System.out.println(Level.class.isEnum());                    // true
System.out.println(java.util.Arrays.toString(
        Level.class.getEnumConstants()));                     // [LOW, HIGH]
System.out.println(String.class.getEnumConstants() == null); // true
System.out.println(Enum.class.isEnum());                     // false
~~~

`Enum` is the **base class** of enums; it itself is not declared with `enum`, so `Enum.class.isEnum()` is `false`. An enum constant with its own class body may have `constant.getClass()` as an anonymous subclass, causing `constant.getClass().isEnum()` to return `false`; to determine the **enum declaring the constant**, use `constant.getDeclaringClass()`. Do not assume every enum object returns the same `getClass()` in that case.

## 7. Records: metadata via record components

Records (standardized in Java 16, stable on Java 17+) declare their set of data components directly in the header:

~~~java
record Person(String name, int age) {}
~~~

`Person.class.isRecord()` returns `true`. `Person.class.getRecordComponents()` returns `RecordComponent[]` in **header declaration order**. Each `RecordComponent` provides the name (`getName()`), type (`getType()`), generic type (`getGenericType()`), and accessor method (`getAccessor()`).

~~~java
for (java.lang.reflect.RecordComponent component
        : Person.class.getRecordComponents()) {
    System.out.println(component.getName()
            + ": " + component.getType().getSimpleName());
}
// name: String
// age: int
~~~

`getRecordComponents()` returns `null` if the type is **not a record**, but returns a non-null, possibly empty array if the type **is a record**. Therefore, check `isRecord()` or `null` before iterating. `Record.class.isRecord()` is `false` because `java.lang.Record` is only the base class; a concrete record class has `Record` as its direct superclass and is `final`.

**A record component differs from a Java field.** `getDeclaredFields()` returns field metadata described by the JVM, whereas `getRecordComponents()` reflects the component contract declared in the header and preserves header order. A record has `private final` component fields, public accessors, and basic compiler-generated methods, but immutability is **shallow**: if a component holds a reference to a mutable object, its internal data can still change.

## 8. Complete compilable and runnable Java 17+ example

Create the file `ReflectionClassKindsDemo.java` with the following contents. The example combines all six type categories into one program and prints verifiable properties:

~~~java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class ReflectionClassKindsDemo {
    interface Payment { void pay(); }

    static final class Card implements Payment {
        public void pay() {}
    }

    enum Level { LOW, HIGH }

    record Person(String name, int age) {}

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("int/void: " + int.class.isPrimitive() + "/" + void.class.isPrimitive());
        System.out.println("int vs Integer.TYPE: " + (int.class == Integer.TYPE));
        System.out.println("wrapper distinct: " + (int.class != Integer.class));

        Class<?> grid = String[][].class;
        System.out.println("array: " + grid.isArray() + ", name=" + grid.getName());
        System.out.println("component: " + grid.getComponentType().getTypeName());
        System.out.println("loaded int[]: " + (Class.forName("[I") == int[].class));

        System.out.println("interface: " + Payment.class.isInterface());
        System.out.println("implemented: " + Payment.class.isAssignableFrom(Card.class));
        System.out.println("enum: " + Level.class.isEnum());
        System.out.println("constants: " + Arrays.toString(Level.class.getEnumConstants()));
        System.out.println("record: " + Person.class.isRecord());
        for (RecordComponent component : Person.class.getRecordComponents()) {
            System.out.println("component: " + component.getName() + ":" + component.getType().getSimpleName()
                    + ", accessor=" + component.getAccessor().getName());
        }
        System.out.println("Enum base: " + Enum.class.isEnum());
        System.out.println("Record base: " + Record.class.isRecord());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac ReflectionClassKindsDemo.java
java ReflectionClassKindsDemo
~~~

Exact stdout (verified with Java 21, Java 17-compatible code):

~~~text
int/void: true/true
int vs Integer.TYPE: true
wrapper distinct: true
array: true, name=[[Ljava.lang.String;
component: java.lang.String[]
loaded int[]: true
interface: true
implemented: true
enum: true
constants: [LOW, HIGH]
record: true
component: name:String, accessor=name
component: age:int, accessor=age
Enum base: false
Record base: false
~~~

Because `Person` is a record nested inside the demo class, its full binary name contains `$` (`ReflectionClassKindsDemo$Person`), yet `Person.class.getSimpleName()` is still `Person`. The example deliberately uses `getSimpleName()` for components so the output stays stable and avoids package dependencies.

## 9. Application: classifying types in a reflection tool

A schema inspector, serializer, or metadata viewer can accept any `Class<?>` and decide how to handle it. The order of checks helps avoid confusing `void` with value-holding primitives and annotations with ordinary interfaces:

~~~java
static String classify(Class<?> type) {
    if (type == void.class) return "void";
    if (type.isPrimitive()) return "primitive";
    if (type.isArray()) return "array";
    if (type.isAnnotation()) return "annotation";
    if (type.isInterface()) return "interface";
    if (type.isEnum()) return "enum";
    if (type.isRecord()) return "record";
    return "ordinary/other class";
}
~~~

Place this method inside a class; this is an **illustrative fragment**, while section 8 is the standalone runnable program. If given `int[][]`, you can traverse `getComponentType()` multiple times to obtain both the dimension count and the element type. If given an enum, `getEnumConstants()` retrieves the list of valid values. If given a record, `getRecordComponents()` retrieves the exact component list in definition order. For interfaces, use `isAssignableFrom()` to check compatible implementations.

Do not infer a type is a record just because it has a `name()` method or multiple `final` fields: you must use `isRecord()`. Similarly, do not treat every subclass of `Enum` as an enum declaration, and do not identify an interface solely by the `abstract` modifier.

## 10. Common misconceptions and self-check

1. **Primitive vs. wrapper:** `int.class` and `Integer.class` differ. `new Integer(...)` is also unnecessary; boxing to `Integer` does not turn metadata into `int.class`.
2. **`void` is special:** `void.class.isPrimitive()` is `true`, but `void` has no valid instances or arrays; compare `type == void.class` when needing to distinguish it specifically.
3. **Arrays are distinct types:** `int[].class.isArray()` is `true`, `int[].class.isPrimitive()` is `false`, and `getComponentType() == int.class` is `true`.
4. **Type names for loading:** `Class.forName("int")` fails; `Class.forName("[I")` finds `int[]`. `getTypeName()` is for readable display; an array's `getName()` carries the JVM descriptor format.
5. **Direction of assignability:** `Interface.class.isAssignableFrom(Implementation.class)` checks whether an implementation can be assigned to the interface; the reverse is usually `false`.
6. **Enums/records are concrete declared types:** `Enum.class.isEnum()` and `Record.class.isRecord()` are both `false`; to get constants or components, inspect the actual declared class.
7. **API return values:** `getEnumConstants()` and `getRecordComponents()` can return `null` when the type is not of that kind. Do not iterate directly before checking.

Answer for yourself:

- Is `int[][].class.getComponentType() == int[].class` true or false? **True**, because each component lookup strips only one dimension.
- Can `void.class.isPrimitive()` be used to decide whether a type can hold a primitive value? **No**; `void` is an exception even though the API returns `true`.
- If a class has `final` fields and accessors looking like a record, is `isRecord()` guaranteed to be `true`? **No**; only a class actually declared with `record` satisfies the condition.
- If receiving `Class<?>` from an external plugin, how do you distinguish an annotation interface from a regular interface? **`isAnnotation()` before `isInterface()`**.

Authoritative references for further lookup: [Javadoc `Class` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Javadoc `RecordComponent` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html), and [JLS 17 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).