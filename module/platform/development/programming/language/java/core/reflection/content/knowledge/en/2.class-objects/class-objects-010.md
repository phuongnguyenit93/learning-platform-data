# Distinguishing a `Class` Object from an Instance of the Described Type in Java

## 1. Two related but non-identical concepts

In Java, an **instance** is an object created from a class or concrete type at runtime. It carries its own state via instance fields and can perform behavior defined by that type. For example, `new Person("An")` creates a `Person` object.

A **`Class` object** is an object of type `java.lang.Class`, provided by the JVM to **describe a type at runtime**: type name, superclass, interfaces, constructors, fields, methods, annotations, etc. For example, `Person.class` is the `Class<Person>` object representing the `Person` type. It is not a `Person` and does not hold the individual `name` state of each `Person`.

Three layers to distinguish:

- **Type declaration:** `class Person { ... }` in source code defines structure and behavior.
- **The type's `Class` object:** `Person.class` is the information describing the `Person` type that the program can query at runtime.
- **Instances of the type:** `new Person("An")` or `new Person("Binh")` are concrete `Person` objects with independent state.

The name `Class` easily causes confusion: `Person.class` is **a Java object**, yet **not an instance of `Person`**; it is itself an instance of `java.lang.Class`. Meanwhile, the expression `Class.class` is the `Class` object describing the `java.lang.Class` type itself.

| Criterion | `Class` object describing `Person` | `Person` instance |
| --- | --- | --- |
| Example | `Person.class`, `person.getClass()` | `new Person("An")` |
| Type of the object itself | `java.lang.Class` | `Person` (or a concrete subclass) |
| What does it represent? | A type recognized by the JVM | A concrete data object |
| State | Information / ability to query type structure | Instance field values, such as `name` |
| Quantity | The same type defined by the same class loader normally shares one `Class` | Many instances of the same type can be created |
| How to obtain | `T.class`, `obj.getClass()`, `Class.forName(...)` | `new`, factory methods, reflection, etc. |
| Used for | Checking types, finding constructors/methods/fields, supporting reflection | Calling behavior and working with concrete data |

**Key distinction:** `Class` answers "**which type** does this object belong to, and how is that type described?"; an instance answers "**which concrete object**, holding what data?". Two different instances can reference the same `Class` object.

## 2. Runnable Java 17+ example

Save with the exact filename `ClassVsInstanceDemo.java`:

```java
import java.lang.reflect.Method;

public class ClassVsInstanceDemo {
    public static class Person {
        private final String name;

        public Person(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<Person> type = Person.class;
        Person an = new Person("An");
        Person binh = new Person("Binh");
        Class<? extends Person> runtimeType = an.getClass();

        System.out.println(type == runtimeType);
        System.out.println(an == binh);
        System.out.println(type.isInstance(an));
        System.out.println(type.isInstance("An"));
        System.out.println(type.getSimpleName());
        System.out.println(type.getClass() == Class.class);

        Method nameMethod = type.getMethod("name");
        System.out.println(nameMethod.invoke(an));
        System.out.println(nameMethod.invoke(binh));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ClassVsInstanceDemo.java
java ClassVsInstanceDemo
```

Expected output:

```text
true
false
true
false
Person
true
An
Binh
```

Step-by-step explanation:

1. `type == runtimeType` is `true`: `Person.class` and `an.getClass()` return the same `Class` object when `an` actually belongs to `Person`.
2. `an == binh` is `false`: two `new` calls create two distinct instances; both are described by the `Person` type.
3. `type.isInstance(an)` is `true`, whereas `type.isInstance("An")` is `false`: this checks whether an **object value** belongs to the described type.
4. `getSimpleName()` returns `Person`, a property of the type; it does not read an instance's `name` data.
5. `type.getClass() == Class.class` is `true`: the `type` object belongs to the `Class` class, even though it is describing the `Person` class.
6. `getMethod("name")` finds the type's shared method descriptor. `invoke(an)` and `invoke(binh)` execute that method on **two different receivers**, thus returning `An` and `Binh`.

In the example, `Class<Person>` helps express the `Class` object for `Person` at compile time. `Class<? extends Person>` is for `getClass()` because a `Person` reference can also point to an instance of a subclass; the actual runtime type is determined by the object, not merely by the variable declaration.

## 3. Obtaining a `Class` object as needed

| Scenario | How to obtain | Important detail |
| --- | --- | --- |
| Type known in source | `Person.class` | No need to create a `Person` just to read metadata. |
| Have an instance | `person.getClass()` | Reflects the actual runtime class; `null` causes `NullPointerException`. |
| Only have type name at runtime | `Class.forName("demo.Person")` | Requires binary name, appropriate loader, loading error handling; single-argument form requests initialization. |

For example, with `Object value = "hello";`, `value.getClass() == String.class` is `true`, whereas `value.getClass() == Object.class` is `false`: the variable's declared type does not change the instance's runtime class. For `int` or `void`, you can obtain `int.class`/`void.class` even though there are no corresponding object instances.

All of the paths above obtain metadata about a type; they do not carry individual instances' data. Choosing among class literals, `getClass()`, and `Class.forName` is practiced separately in the corresponding lessons.

## 4. `Class` describes the type; operating on data still needs an instance

Reflection typically follows two steps: **locating a member via `Class`**, then **operating on a specific receiver** if it is an instance member.

- `Person.class.getDeclaredFields()` finds fields **declared directly** in `Person` (does not automatically include inherited fields). Each `Field` describes a member, not the field value of a particular `Person`.
- `Person.class.getMethod("name")` finds a matching `public` method, including inherited `public` methods. `getDeclaredMethod(...)` only looks for methods declared in the class itself, regardless of access level.
- `Method.invoke(person)` requires a compatible `person` receiver for instance methods; a different receiver can produce a different result. For static methods, there is no receiver instance.
- `Person.class.getConstructor(String.class)` finds a public constructor. When you actually need to create an instance via reflection, you can call `getConstructor(String.class).newInstance("Chi")`, with appropriate exception and access handling. The `Class` object itself never turns into a `Person` instance.

Do not confuse `Field`, `Method`, `Constructor` (objects describing members) with values or actions taking place on an instance. Java/module access rules still apply during reflective access; finding metadata does not guarantee every member can be invoked or read/written.

**Static fields are a special case:** static data is attached to the class in its runtime context, without a separate copy per instance. This does not turn `Person.class` into a `Person`, nor does it make instance fields into data of `Class`.

## 5. Type checks: `==`, `isInstance`, `isAssignableFrom`

Three different questions lead to three different checks:

| Expression | What does it ask? | Example result |
| --- | --- | --- |
| `a.getClass() == b.getClass()` | Do two instances have the **exact same runtime type**? | Can be `true` even when `a != b` |
| `type.isInstance(obj)` | Does `obj` belong to the type described by `type`, including subtypes? | `Number.class.isInstance(Integer.valueOf(7))` → `true` |
| `parent.isAssignableFrom(child)` | Can a value of type `child` be assigned to a variable of type `parent`? | `Number.class.isAssignableFrom(Integer.class)` → `true` |

`==` between two `Class` objects checks **runtime type identity**; `==` between two instances checks **object identity**. `isInstance` operates on a value/instance, whereas `isAssignableFrom` operates on two objects describing **types**. For reference types, `isInstance(obj)` normally matches the meaning of `obj instanceof SomeType` (when `SomeType` is known in code).

Another example: an `ArrayList` is an instance of `List` by interface relationship, yet `list.getClass() == List.class` is `false` because `getClass()` returns the actual implementation class, not the interface. Therefore, use `getClass() == T.class` when needing the *exact type*; use `instanceof` or `isInstance` when wanting to accept subtypes/implementations as well.

## 6. Cases that easily cause confusion

### A `Class` can represent a type that cannot create ordinary instances

`int.class` and `void.class` are `Class` objects, yet no Java object instance corresponds to `int` or `void` in the sense of using `new`. If autoboxing occurs, `Integer.valueOf(5).getClass()` returns `Integer.class`, **not** `int.class`.

Arrays are reference types with actual array objects: `new String[2].getClass() == String[].class` is `true`. Interfaces/abstract classes also have `Class` objects even though they cannot be instantiated directly. Enum, record, and annotation types all have `Class` objects describing their types.

### "One `Class` per class" must be understood together with class loaders

Within the same runtime definition, instances of the same type share that definition's `Class` object. However, the JVM can load the **same binary name** through **different defining class loaders**, creating distinct runtime types and distinct `Class` objects. Hence, **equal class names alone are not enough to establish that two `Class` objects are the same runtime type**. Conversely, increasing the number of instances does not create a new `Class` object per instance.

### Generics do not create separate runtime types per type argument

`new java.util.ArrayList<String>()` and `new java.util.ArrayList<Integer>()` share the same runtime class `java.util.ArrayList`. Due to **type erasure**, calling `getClass()` on the two objects does not reveal whether elements are `String` or `Integer`; generic type information on a field, method, superclass declaration, etc., if preserved in metadata, must be inspected using the corresponding generic reflection APIs rather than inferred from an `ArrayList`'s `getClass()`.

### `Class<T>` and instances `T` are not interchangeable

`Class<Person>` is not `Person`. Do not pass `Person.class` to an API expecting a `Person` instance; nor use `new Person(...)` where a `Class<Person>` type-descriptor object is required. When needing to cast a value, `Person.class.cast(obj)` checks/casts the value to `Person` at runtime and can throw `ClassCastException`; it **does not create an instance**. `Person.class.isInstance(obj)` only checks and returns a boolean.

## 7. Workflow for choosing the right API when writing code

1. **Type already known in source code and metadata needed?** Use `Person.class`; no need to create a dummy `Person` just to call `getClass()`.
2. **Have an object and need its exact actual class?** Use `obj.getClass()` after ensuring `obj != null`.
3. **Have a type name provided by configuration/plugin?** Consider `Class.forName(...)`, class loader/modules, and loading/initialization errors.
4. **Need to get methods/fields/constructors?** Look up metadata via `Class`; when operating on instance members, supply a receiver and obey access rules.
5. **Need to check whether an object matches a type?** Use `instanceof` or `Class.isInstance`; when examining the relationship between two types, use `Class.isAssignableFrom`; when comparing exact runtime types, compare `Class` with `==`.

Avoid these mistakes: thinking `Person.class` holds a specific person's data; imagining two `new Person(...)` calls create two different `Class` objects; equating a variable's declared type with the value's `getClass()`; using `getClass() == Interface.class` to check an interface; calling `getClass()` on `null`; assuming obtaining metadata lets you access private members regardless of module and access control.

## 8. Self-check

**Question 1.** `Person p1 = new Person("A"); Person p2 = new Person("B");` — what are `p1 == p2` and `p1.getClass() == p2.getClass()`?

**Answer:** `false` and `true`, respectively (assuming the two variables hold two `Person` instances created as above within the same type definition). Two distinct objects sharing the same runtime class.

**Question 2.** Why does a variable declared as `Object x = "text";` have `x.getClass() == String.class`?

**Answer:** `getClass()` returns the **actual type of the instance** (`String`), not the declared type of the variable (`Object`).

**Question 3.** Can you use `Person.class.getMethod("name")` to find the method and immediately deduce the name of every `Person` instance?

**Answer:** No. `Method` describes the type's method. To know each person's name, you must invoke it on the appropriate receiver, e.g. `method.invoke(p1)` and `method.invoke(p2)`; the results can differ.

Once you understand that **`Class` is the object describing a type**, whereas an **instance is the object carrying concrete state and behavior**, reflection operations, type checks, and polymorphism in Java become much more consistent.