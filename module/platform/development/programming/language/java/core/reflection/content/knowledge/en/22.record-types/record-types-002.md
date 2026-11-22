# RecordComponent: name, type, generic type, and accessor

## 1. What does RecordComponent describe?

The header of a record declaration lists the **record components**:

~~~java
record Position(int x, int y) {
}
~~~

Here there are two components named `x` and `y`, both of type `int`. Java generates the backing fields and the corresponding accessor methods, but **record component**, **field**, and **method** themselves are different concepts.

`java.lang.reflect.RecordComponent` provides metadata for a component declared in the record header. From that metadata, we can learn:

- The component name.
- The type represented as a `Class<?>`.
- The generic type structure represented as a `Type`.
- The access method, called the **accessor**, of the component.
- The record class that declares that component.

This is useful for documentation generators, data model inspectors, or reading components in declaration order. Instead of guessing from all fields and methods of a class, a tool can start from the list of record components.

The `RecordComponent` API has been available since Java 16. The programs in this article use Java 17 or later and do not require preview features.

## 2. Going from Class to the component list

The entry point is `Class.getRecordComponents()`:

~~~java
RecordComponent[] components = Position.class.getRecordComponents();
~~~

The snippet above is for illustration; you need to import `java.lang.reflect.RecordComponent` and declare `Position` when placing it in a program.

There are three cases to distinguish:

| Class token | `isRecord()` | `getRecordComponents()` |
| --- | --- | --- |
| Record class with components | `true` | Non-`null` array containing the components |
| Record class without components, such as `record Empty() {}` | `true` | Empty array |
| Non-record class | `false` | `null` |

The components are returned **in the exact order declared in the record header**. This is the contract of [Class.getRecordComponents](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()).

For example, `record Position(int x, int y)` has the order `x`, then `y`. Do not infer this order by iterating over `getDeclaredFields()` or `getDeclaredMethods()`, because those APIs do not guarantee declaration order.

Additional `static` fields or helper methods in the record body do not become record components either.

## 3. Four main groups of information

| API on `RecordComponent` | Return type | Meaning |
| --- | --- | --- |
| `getName()` | `String` | Declared component name |
| `getType()` | `Class<?>` | Type token; for generics, this is the erased type |
| `getGenericType()` | `Type` | Declared type, which can preserve parameterized structure or type variables |
| `getAccessor()` | `Method` | Corresponding accessor method |
| `getDeclaringRecord()` | `Class<?>` | Record declaring the component |

The [RecordComponent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html) documentation describes these APIs.

`RecordComponent` is not a `Field`. There is no `component.get(record)` or `component.set(record, value)` operation similar to reading/writing a field. To read a value via the accessor, obtain the `Method` and invoke it on a record object.

## 4. Complete program: name, type, generics, and values

The following example has four kinds of components:

- `String code`: ordinary class type.
- `int priority`: primitive type.
- `T weight`, with `T extends Number`: bounded type variable.
- `List<String> tags`: parameterized type.

Save into `RecordComponentDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.List;

public class RecordComponentDemo {
    public record Parcel<T extends Number>(
            String code, int priority, T weight, List<String> tags) {
    }

    static String kind(Type type) {
        if (type instanceof Class<?>) {
            return "Class";
        }
        if (type instanceof ParameterizedType) {
            return "ParameterizedType";
        }
        if (type instanceof TypeVariable<?>) {
            return "TypeVariable";
        }
        return "Other";
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Parcel<Integer> parcel =
                new Parcel<>("P-7", 2, 3, List.of("fragile"));

        RecordComponent[] components = Parcel.class.getRecordComponents();

        System.out.println("components: "
                + Arrays.stream(components)
                        .map(RecordComponent::getName)
                        .toList());

        for (RecordComponent component : components) {
            Method accessor = component.getAccessor();
            System.out.println(component.getName()
                    + " | type=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | kind=" + kind(component.getGenericType()));
            System.out.println("accessor=" + accessor.getName()
                    + "; parameters=" + accessor.getParameterCount()
                    + "; genericReturn="
                    + accessor.getGenericReturnType().getTypeName());
            System.out.println("value=" + accessor.invoke(parcel));
        }

        Object priority = components[1].getAccessor().invoke(parcel);
        System.out.println("boxed priority: "
                + priority.getClass().getSimpleName());

        TypeVariable<?> weightType =
                (TypeVariable<?>) components[2].getGenericType();
        System.out.println("weight bounds: "
                + Arrays.stream(weightType.getBounds())
                        .map(Type::getTypeName)
                        .toList());

        ParameterizedType tagsType =
                (ParameterizedType) components[3].getGenericType();
        System.out.println("tags arguments: "
                + Arrays.stream(tagsType.getActualTypeArguments())
                        .map(Type::getTypeName)
                        .toList());

        System.out.println("declaring record: "
                + (components[0].getDeclaringRecord() == Parcel.class));

        Parcel<Double> other =
                new Parcel<>("P-8", 1, 2.5, List.of("local"));
        System.out.println("same runtime class: "
                + parcel.getClass().equals(other.getClass()));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 RecordComponentDemo.java
java RecordComponentDemo
~~~

Exact output:

~~~text
components: [code, priority, weight, tags]
code | type=java.lang.String | generic=java.lang.String | kind=Class
accessor=code; parameters=0; genericReturn=java.lang.String
value=P-7
priority | type=int | generic=int | kind=Class
accessor=priority; parameters=0; genericReturn=int
value=2
weight | type=java.lang.Number | generic=T | kind=TypeVariable
accessor=weight; parameters=0; genericReturn=T
value=3
tags | type=java.util.List | generic=java.util.List<java.lang.String> | kind=ParameterizedType
accessor=tags; parameters=0; genericReturn=java.util.List<java.lang.String>
value=[fragile]
boxed priority: Integer
weight bounds: [java.lang.Number]
tags arguments: [java.lang.String]
declaring record: true
same runtime class: true
~~~

The program checks the kind of `Type` through public interfaces such as `ParameterizedType` and `TypeVariable`. It does not print JDK internal implementation class names to infer generic kinds.

### 4.1. Component name is the name in the declaration

`getName()` yields `code`, `priority`, `weight`, and `tags`, matching the header of `Parcel`.

This name is not:

- The string value stored in the component, such as `P-7`.
- The name of the class implementing a value.
- A getter name following JavaBeans conventions.

Record accessors use the component name: `code()`, `priority()`, `weight()`, `tags()`. Do not assume they take the form `getCode()` or `getWeight()`.

The `javac -parameters` option is not required for `RecordComponent.getName()` to know component names. This is record component metadata, not guessing parameter names of an arbitrary method.

### 4.2. getType gives a Class token

For `code`, the token is `String.class`. For `priority`, the token is `int.class`.

For the `weight` component declared as `T`, where `T extends Number`, the erased type is `Number`; therefore `getType()` gives `Number.class`.

For `tags`, the token is `List.class`. There is no class literal `List<String>.class` to return.

This helps choose the right tool: use `getType()` when you need a class token for matching or looking up Reflection signatures; use `getGenericType()` when you need to understand the fuller declared type structure.

### 4.3. getGenericType preserves declaration information

The results in the program:

| Component | `getType()` | `getGenericType()` |
| --- | --- | --- |
| `code` | `String.class` | A `Class` representing `String` |
| `priority` | `int.class` | A `Class` representing `int` |
| `weight` | `Number.class` | `TypeVariable` named `T` |
| `tags` | `List.class` | `ParameterizedType` representing `List<String>` |

Because `Class` also implements `Type`, the result of `getGenericType()` is not always a `ParameterizedType`. Casting every result to `ParameterizedType` will make the program fail on components like `code` and `priority`.

In the experiment, the type variable `T` has the bound `Number`, readable via `TypeVariable.getBounds()`. The parameterized type of `tags` has the argument `String`, readable via `ParameterizedType.getActualTypeArguments()`.

### 4.4. Metadata T does not automatically change to Integer per object

The `parcel` object is created via the declaration `Parcel<Integer>`, yet the metadata of the `weight` component is still `T`, not automatically `Integer`.

At the end of the program, the `Parcel<Double>` object and the `Parcel<Integer>` object have the same runtime class. `RecordComponent` is obtained from the declaring class `Parcel`, so it does not separately store the generic arguments of each external variable.

If a tool has additional context, such as a field declared as `Parcel<Integer>`, it can analyze the `Type` of that context and build a `T -> Integer` mapping. That is a separate generic resolution step; `component.getGenericType()` by itself does not perform this step from an instance alone.

Nor should you infer that seeing the value `3` proves every value of `T` is `Integer`. The value being read and the declared type are two different kinds of information.

## 5. Type is structured, not just a string to print

`getTypeName()` is useful when presenting results to readers. If a tool needs to process types, use the `Type` interfaces to traverse the structure.

Some cases you may encounter:

| Component type in declaration | Erased type, with `T extends Number` if applicable | `Type` form usually needing handling |
| --- | --- | --- |
| `String` | `String` | `Class` |
| `int` | `int` | `Class` of primitive type |
| `String[]` | `String[]` | `Class` of array |
| `List<String>` | `List` | `ParameterizedType` |
| `T` | `Number` | `TypeVariable` |
| `T[]` | `Number[]` | `GenericArrayType` |

For a component like `List<? extends Number>`, the outermost object is a `ParameterizedType`; the inner type argument is a `WildcardType`. If a tool inspects generics thoroughly, it needs to handle nesting instead of checking only one level.

Do not parse the `getTypeName()` string by splitting commas and angle brackets instead of using the structural APIs. Generic types can be nested multiple levels deep, with wildcards, type variables, and generic arrays.

`getGenericSignature()` provides the generic signature representation as a metadata string. If the goal is to understand the declared type, `getGenericType()` is usually a clearer starting point.

Generic metadata does not replace data validation either. Reading the `List<String>` declaration does not automatically iterate over and verify every element in a running list.

## 6. Accessors connect metadata to a specific object

`getAccessor()` returns `java.lang.reflect.Method`. For a valid Java record, that is the corresponding accessor method, having the component's name, taking no parameters, and returning the component's type.

Example in the program:

~~~java
Method accessor = component.getAccessor();
Object value = accessor.invoke(parcel);
~~~

This snippet separates two tasks:

1. `getAccessor()` retrieves the method metadata.
2. `invoke(parcel)` executes the method on the `parcel` object.

`RecordComponent` itself does not hold an instance's value. Two objects of the same record class share the component description but can have different values.

### Primitive types are boxed when passing through Object

In the example, `priority()` returns `int`. However, `Method.invoke(...)` returns `Object`, so the integer result is boxed into `Integer`.

Therefore:

- `component.getType()` of `priority` is still `int.class`.
- The object received from `invoke(...)` has the class `Integer`.
- This is not the component's metadata changing from `int` to `Integer`.

If a component has a reference type and the accessor returns `null`, the Reflection result can also be `null`. Do not call `getClass()` on the value just read without accounting for that case.

### Conditions and errors when calling an accessor

| Situation | Outcome to watch for |
| --- | --- |
| Passing an instance incompatible with the method's declaring class | Can throw `IllegalArgumentException` |
| Passing `null` as the receiver object for an instance accessor | Throws `NullPointerException` |
| Calling a method not accessible from the current code | Can throw `IllegalAccessException` |
| Accessor itself throws an exception during execution | Exception is wrapped in `InvocationTargetException` |

An accessor being `public` does not mean an inaccessible record class or a module boundary is automatically bypassed. The complete example uses a `public` nested record inside a `public` class, so it does not need to open access with `setAccessible(true)`.

## 7. Accessors can be user-defined

Do not assume that calling an accessor is always equivalent to returning the exact reference stored in the private field. A record can declare an explicit accessor with its own body.

The following example uses defensive copying for an array component:

- The constructor copies the input array.
- The accessor returns a copy.
- Reflection invokes that accessor like a normal method call.

Save into `RecordAccessorDemo.java`:

~~~java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class RecordAccessorDemo {
    public record Packet(byte[] bytes) {
        public Packet {
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        byte[] original = {1, 2};
        Packet packet = new Packet(original);
        RecordComponent component =
                Packet.class.getRecordComponents()[0];

        byte[] first =
                (byte[]) component.getAccessor().invoke(packet);
        System.out.println("accessor: "
                + component.getAccessor().getName());
        System.out.println("return type: "
                + component.getType().getTypeName());
        System.out.println("first read: " + Arrays.toString(first));
        System.out.println("same as original: " + (first == original));

        first[0] = 9;
        byte[] second =
                (byte[]) component.getAccessor().invoke(packet);
        System.out.println("after changing result: "
                + Arrays.toString(second));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 RecordAccessorDemo.java
java RecordAccessorDemo
~~~

Output:

~~~text
accessor: bytes
return type: byte[]
first read: [1, 2]
same as original: false
after changing result: [1, 2]
~~~

After modifying the array received on the first read, the subsequent read still gives `[1, 2]`. `getAccessor().invoke(packet)` executed the `bytes.clone()` code rather than returning the backing field directly.

This example does not mean every record automatically copies arrays or collections. Records do not guarantee deep immutability for reference data. The copying behavior in the program comes from the explicitly written constructor and accessor.

When building a record-reading tool, choosing the accessor or reading the field directly is a decision about observed behavior. The accessor is the record's method interface and can contain logic; reading a field is a different operation that often also requires handling private access.

## 8. Choosing output data: component schema and runtime values

When designing a record inspection tool, separate two outputs with different purposes:

| Output | Data source | Example with `Parcel<T>` |
| --- | --- | --- |
| Schema (*schema*) | `getName()`, `getType()`, `getGenericType()` | Component `weight` declared with type `T extends Number` |
| Values of an instance | `getAccessor().invoke(instance)` | `weight` currently has value `3` |

The schema can be built once from `Parcel.class`; reading values requires a suitable instance. If using `LinkedHashMap` to pair component names with accessor values, iterate over the `RecordComponent[]` array in header order. The resulting object is only a snapshot of the values returned by the accessors; it does not automatically deep-copy lists or mutable objects inside the record.

Building a complete value reader must also decide how to handle `null`, access errors, and `InvocationTargetException`. Generic metadata does not replace those data checks.

## 9. Common pitfalls

**Equating RecordComponent with Field.** A record component is related to a backing field and an accessor, but it is a distinct kind of metadata. To get a field by name, use the field APIs; to read via the accessor, call `getAccessor()`.

**Using getType to conclude all generic information is lost.** `getType()` gives the erased token; `getGenericType()` can preserve type variables and the parameterized structure of the declaration.

**Casting every Type to ParameterizedType.** Components of type `int`, `String`, or `T` do not have the same `Type` form as `List<String>`.

**Assuming that having `Parcel<Integer>` means the weight metadata must be `Integer`.** Component metadata belongs to the generic declaring class; replacing `T` with a concrete argument requires additional resolution context.

**Constructing getter names getX following JavaBeans.** Record accessors use the component name. Getting `getAccessor()` directly avoids relying on an incorrect naming convention.

**Forgetting that invoke executes code.** An explicit accessor can copy data, check conditions, or throw exceptions.

**Using null as if it meant a record without components.** `getRecordComponents() == null` means the class is not a record; a record without components gives an empty array.

**Relying on field or method order.** When component order is needed, get the `RecordComponent` list itself.

## 10. Self-check

1. For `record Position(int x, int y)`, is the accessor of `x` named `x` or `getX`?
2. In the `Parcel<T extends Number>` example, why is `weight.getType()` equal to `Number.class` while `weight.getGenericType()` represents `T`?
3. Can `getGenericType()` of `List<String> tags` be cast to `Class<?>` to obtain `List<String>.class`?
4. How does the `getRecordComponents()` result of an ordinary class differ from that of a record without components?
5. Why is the value read via the accessor of `int priority` an `Integer` when held in `Object`?
6. If an accessor copies an array itself, does calling the accessor with Reflection skip that copying logic?
7. Can `RecordComponent` tell the value of a component on its own without a record object?
8. Why does a `readComponents` function use `LinkedHashMap` instead of relying on the arbitrary iteration order of another map?

Answers:

1. The name is `x`, and the call in Java code is `position.x()`.
2. `getType()` uses the erased type; the variable `T` has bound `Number`. `getGenericType()` describes the declaration's type variable.
3. No. It is a `ParameterizedType`; there is no class literal for such a parameterized type.
4. An ordinary class gives `null`; a record without components gives an empty array.
5. `Method.invoke` returns `Object`, so primitive results are boxed.
6. No. Reflection executes that accessor method itself.
7. No. It describes the declaration; to read values via the accessor, you must provide an appropriate instance.
8. To preserve the exact component order provided by `getRecordComponents()`.
