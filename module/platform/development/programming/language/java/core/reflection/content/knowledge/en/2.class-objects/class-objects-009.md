# Do Not Create `Class` with a Normal Constructor

## 1. Where does the issue lie?

In Java Reflection, `java.lang.Class<T>` is the **object describing a type at runtime**: type name, modifiers, superclass, interfaces, methods, fields, constructors, annotations, etc. Each variable of type `Class<?>` holds a reference to the type's metadata, not a business object of that type.

For example, the three expressions below have different meanings:

```java
Person person = new Person();        // Create a Person instance
Class<Person> type = Person.class;    // Get the Class object describing Person
Class<?> runtimeType = person.getClass(); // Get the Class of an existing instance
```

If you write:

```java
Class<?> type = new Class<>(); // Compile error
```

Java does not allow it. **`java.lang.Class` does not provide a `public` constructor for application code to create a `Class` object itself using `new`.** The JVM manages these objects during type loading/definition. Arbitrarily creating a `Class` would break the link between metadata and the type definition that the JVM actually knows, verifies, and executes.

This is an important distinction: **not being able to do `new Class(...)`** does not mean **not being able to do `new Person(...)`**. You still instantiate a normal class using its own constructor when the constructor allows it.

## 2. Why does the JVM manage `Class` objects?

When the runtime needs to know a type, the JVM uses class loading, linking, and (when appropriate conditions occur) initialization. The `Class` object is the gateway reflecting the type definition recognized by the runtime.

- `Class` represents **the type**, whereas `new Person()` creates an **instance** of type `Person`.
- Source code cannot self-supply internal type information and validity guarantees by calling `new Class()`.
- For the same type defined by the same **defining class loader**, ordinary ways of getting `Class` reference the same `Class` object. Two different class loaders can define two separate types even with the same binary name.
- *Loading*, *linking*, and *initialization* are distinct steps; obtaining `Class` does not always mean the type's static initializer has run.

Understand the phrase "`Class` has no normal constructor" in terms of the API contract: **there is no public constructor for applications to call**. There is no need to rely on the count or signatures of internal JDK implementation constructors to explain this mechanism.

## 3. Valid ways to obtain a `Class` object

| Way | Example | When to use? |
| --- | --- | --- |
| Class literal | `Person.class` | Type is already known at compile time; safe and clear. |
| `Object.getClass()` | `person.getClass()` | Already have an object and need its actual runtime type. |
| `Class.forName(String)` | `Class.forName("com.example.Person")` | Only have the type's binary name as a string, common in config/plugins; can throw `ClassNotFoundException`. |
| `Class.forName(String, boolean, ClassLoader)` | `Class.forName(name, false, loader)` | Need to choose the class loader and control class initialization. |
| `ClassLoader.loadClass(String)` | `loader.loadClass(name)` | Want to ask the chosen class loader to find/load the type; typically does not actively initialize the class at this step. |

Distinguish carefully:

- `Person.class` is a **class literal**, not a constructor call; it does not create a `Person`, and the expression itself does not trigger `Person` initialization.
- `person.getClass()` returns the actual runtime type. When `Person` has subclasses, this value can differ from `Person.class`. If `person == null`, the call causes `NullPointerException`.
- `Class.forName(String)` uses a *binary name* and by default requests initialization of the found class; depending on the case, it can raise loading/initialization errors. The three-parameter form with `initialize = false` avoids requesting initialization in that call.
- `ClassLoader.loadClass` and `Class.forName` handle type names and loaders; they **do not invoke an instance constructor** of the described class.
- When knowing a type via a string, you must handle the case where the class is not found; do not assume any arbitrary string name is valid.

## 4. Runnable example: three paths to the same metadata

Save the following contents as **`ClassMetadataDemo.java`**:

```java
public class ClassMetadataDemo {
    static class Person {
        final String name;

        Person(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<Person> fromLiteral = Person.class;

        Person person = new Person("Lan");
        Class<?> fromObject = person.getClass();

        // getName() returns the exact binary name,
        // even when Person is a nested class.
        Class<?> fromName = Class.forName(Person.class.getName());

        System.out.println(fromLiteral == fromObject);
        System.out.println(fromLiteral == fromName);
        System.out.println(fromLiteral.getName());
        System.out.println(person.name);
    }
}
```

Compile and run with Java 17+:

```bash
javac ClassMetadataDemo.java
java ClassMetadataDemo
```

Expected output:

```text
true
true
ClassMetadataDemo$Person
Lan
```

Step-by-step explanation:

1. `Person.class` gets `Person`'s metadata; it does not execute `new Person(...)`.
2. `new Person("Lan")` creates an instance. `person.getClass()` gets that instance's metadata.
3. `Class.forName(Person.class.getName())` finds the exact type by binary name (`$` separates nested classes in binary names).
4. All three variables `fromLiteral`, `fromObject`, and `fromName` reference the same `Class` object in this example, because it is the same type and same defining class loader. The `==` operator checks reference identity.
5. The last line reads the `name` field from the **`Person` instance**, not from `Class<Person>`.

If `Person` is declared in a package, the binary name has the package prefixed; using `Person.class.getName()` helps avoid confusing source names and binary names.

## 5. Obtaining `Class` is not instantiating the described type

Reflection allows fetching a constructor **of the described type** and invoking that constructor to create an instance, if access permissions and the type allow it. This is a completely different operation from `new Class(...)`.

Save as **`ReflectiveConstructionDemo.java`**:

```java
public class ReflectiveConstructionDemo {
    public static class Greeting {
        public Greeting() {
        }

        public String say() {
            return "Hello";
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Greeting> type = Greeting.class;

        // Constructor<Greeting> describes Greeting's constructor.
        Greeting instance = type.getDeclaredConstructor().newInstance();

        System.out.println(type.getSimpleName());
        System.out.println(instance.say());
        System.out.println(instance.getClass() == type);
    }
}
```

```bash
javac ReflectiveConstructionDemo.java
java ReflectiveConstructionDemo
```

Output:

```text
Greeting
Hello
true
```

Here:

- `Greeting.class` returns `Class<Greeting>`.
- `getDeclaredConstructor()` gets metadata for `Greeting`'s no-argument constructor.
- `Constructor.newInstance()` creates **a new `Greeting`**, not a new `Class`.
- The example uses a `public` constructor to avoid access restrictions.

In practical usage, a matching constructor signature is required; the constructor might not exist, might be inaccessible, might throw an exception, or the type might not be directly instantiable (such as an interface/abstract class). Avoid `Class.newInstance()`: this API is deprecated; use `getDeclaredConstructor(...).newInstance(...)` for clearer constructor and exception handling.

## 6. Getting metadata does not mean initializing the class

A class literal like `LazyType.class` only gets the object describing the type; it does not automatically run `LazyType`'s static initializer. In contrast, `Class.forName(LazyType.class.getName())` requests class initialization if not yet initialized. If you need metadata by name without actively initializing, use `Class.forName(name, false, loader)` with an appropriate loader.

Both ways still return a **`Class` object**, and class initialization (running `static` code) still differs from **creating an instance** via `new LazyType()` or invoking a constructor through Reflection. Initialization sequences and exceptions belong to the separate lesson on class lifecycle.

## 7. `Class` also describes types without ordinary instance constructors

`Class` is not only for classes that can be instantiated with `new`:

```java
Class<?> primitiveType = int.class;
Class<?> voidType = void.class;
Class<?> arrayType = String[].class;
Class<?> interfaceType = Runnable.class;
```

- `int.class`, `void.class`, and `String[].class` are all valid `Class` objects.
- `Runnable.class` describes an interface; interfaces have no instance constructor to call with `new Runnable()`.
- You must not infer from having a `Class<?>` that the type has a no-argument constructor or can be directly instantiated.
- `Class.forName("int")` is not how to get `int.class`; primitive names are not looked up that way.
- Due to type erasure, `List<String>.class` is invalid syntax; use `List.class`. Specific type argument information may need analysis via `Type`/`ParameterizedType` in an appropriate context, rather than residing in a separate `Class<List<String>>`.

This further shows that `Class` represents **a runtime type**, not a class that applications construct themselves via a constructor.

## 8. Common mistakes and fixes

| Mistake or misconception | Problem | Correct approach |
| --- | --- | --- |
| `new Class<>()` | `Class` has no public constructor for applications. | Use `SomeType.class`, `obj.getClass()`, or `Class.forName(...)`. |
| Using `SomeType.class` and expecting an instance of `SomeType` | Class literal only gets type metadata. | Call `new SomeType(...)` or constructor reflection when an instance is needed. |
| Using `Class.forName("Person")` for nested/packaged types without the proper binary name | Class not found for the supplied name. | Use the full binary name or `Person.class.getName()`. |
| Calling `value.getClass()` when `value` is null | `NullPointerException`. | Check for null or use `SomeType.class` if the type is known. |
| Assuming `Class.forName(...)` is always safe and side-effect free | The single-argument overload can trigger class initialization and related exceptions. | Handle errors, consider the three-argument overload when initialization control is needed. |
| Calling `getDeclaredConstructor().newInstance()` on any `Class<?>` | There may be no matching constructor, insufficient access rights, or a non-instantiable type. | Check the type kind, constructors, access rights, and handle `ReflectiveOperationException` appropriately. |
| Using `Class.newInstance()` | Old deprecated API, less clear about constructors and thrown errors. | Use `getDeclaredConstructor(...).newInstance(...)`. |
| Treating the same class name as the same type across all class loaders | Runtime type identity also depends on the defining class loader. | Check actual loaders/types when working with plugins, runtime modules, or custom loading. |

## 9. Choosing the right API in practice

- **Type known in advance**: prefer `Foo.class`; the compiler checks the type name and gives an appropriate generic type, e.g. `Class<Foo>`.
- **Already have an object**: use `obj.getClass()` to know the exact runtime type, especially with inheritance/polymorphism.
- **Have a type name from configuration**: use `Class.forName(...)`, while controlling input data, class loader, initialization timing, and exceptions.
- **Need to create an instance dynamically**: first obtain `Class`, then locate and invoke a constructor **of the described type**; do not try to create another `Class` with `new`.

## 10. Self-check

1. Why does `Person.class` return a `Class<Person>` without needing `new Class<Person>()`?
2. Under what condition are `Person.class` and `new Person().getClass()` the same? When a variable of type `Person` points to a subclass, when can the result differ?
3. How does `Class.forName(String)` differ from `Person.class` regarding name specification and the ability to trigger static initialization?
4. What type of object does calling `type.getDeclaredConstructor().newInstance()` create?
5. Why are `int.class` and `Runnable.class` valid values even though normal instance constructors cannot be called on them?

**Remember:** `Class` is a metadata object managed by the JVM/runtime. You **obtain a `Class` reference via a class literal, an instance, a type name, or a class loader**, and then use that metadata to inspect or work with the type. You **do not create `Class` objects with a normal constructor**; constructor reflection (when applicable) is used to create **an instance of the described type**.