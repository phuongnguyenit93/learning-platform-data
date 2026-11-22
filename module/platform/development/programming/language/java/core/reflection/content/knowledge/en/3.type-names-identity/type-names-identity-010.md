# Reflection: `isAssignableFrom`, `cast`, and `asSubclass`

Three methods on `java.lang.Class` help handle **type compatibility at runtime** when a class or object is only known after the program starts running, such as when loading plugins, selecting implementations from configuration, or processing results from reflection. They are related, yet they answer **three different questions**:

| Method | Question | Input | Result |
| --- | --- | --- | --- |
| `target.isAssignableFrom(source)` | Can a value of type `source` be assigned to a variable of type `target`? | `Class<?>` | `boolean` |
| `target.cast(object)` | Is `object` compatible with type `target`? | `Object` | The checked object returned with type `T`, or throws `ClassCastException` |
| `candidate.asSubclass(base)` | Can type `candidate` be viewed as a subclass/implementation type of `base`? | `Class<U>` | The same current `Class` token with static type `Class<? extends U>`, or throws `ClassCastException` |

What they have in common is that they rely on **runtime type identity** and actual inheritance/implementation relationships. They do not create new objects, do not convert data in the sense of value conversion, and do not replace checking generic type arguments.

## 1. Foundation: `Class<T>` Is a Type Token

For example, `String.class` has static type `Class<String>`; `Runnable.class` is `Class<Runnable>`. When a class name is only known at runtime—such as after `Class.forName("...")`—we typically only have `Class<?>`: we know there is a concrete type, but do not know which type it is at compile time.

Suppose:

~~~java
interface Task {}
class EmailTask implements Task {}
class Other {}
~~~

The following relationships are valid:

~~~java
Task task = new EmailTask();   // widening reference conversion
Object value = task;           // valid upcast
~~~

Conversely, `EmailTask task = (EmailTask) someTask` requires checking the actual value at runtime. With reflection, we need to check this relationship through `Class`, because the type name is not always known at compile time.

## 2. `Class.isAssignableFrom(Class<?>)`: Checking the Relationship Between Two Types

Syntax:

~~~java
boolean accepted = Target.class.isAssignableFrom(Source.class);
~~~

**Read from right to left:** "Can a value of type `Source` be assigned to a variable of type `Target`?". Call it on the **target type** and pass the **source type**. The method returns `true` when both types are identical or the source can be converted to the target via **identity conversion** or **widening reference conversion**; it does not count conversions requiring a narrowing cast.

~~~java
Task.class.isAssignableFrom(EmailTask.class);   // true: implements Task
EmailTask.class.isAssignableFrom(Task.class);   // false: reverse direction
Task.class.isAssignableFrom(Task.class);        // true: same type
Object.class.isAssignableFrom(Task.class);      // true: interface also widens to Object
Runnable.class.isAssignableFrom(Thread.class); // true: Thread implements Runnable
~~~

A class can implement multiple interfaces, so type compatibility is broader than an `extends` chain. You do not need an instance `new EmailTask()` to perform this check.

### When should you use it?

When iterating over `Class<?>` obtained from classpath scanning, a plugin registry, or `Class.forName`, check whether it satisfies the desired contract before registering it:

~~~java
Class<?> candidate = EmailTask.class;
if (Task.class.isAssignableFrom(candidate)) {
    // candidate has type Task or a compatible subtype/implementation.
}
~~~

This is only a **type** check. A matching class could still be abstract, an interface, lack a suitable constructor, or be uninstantiable due to access restrictions.

### Primitives and arrays: commonly confused cases

`isAssignableFrom` checks **reference** compatibility and does not mirror every assignment rule in the Java language:

| Expression | Result | Reason |
| --- | --- | --- |
| `long.class.isAssignableFrom(int.class)` | `false` | Primitive widening `int → long` is not applied |
| `int.class.isAssignableFrom(int.class)` | `true` | Same primitive token |
| `Integer.class.isAssignableFrom(int.class)` | `false` | Boxing is not applied |
| `Number[].class.isAssignableFrom(Integer[].class)` | `true` | Reference arrays have covariance |
| `Object[].class.isAssignableFrom(String[].class)` | `true` | `String[]` is a subtype of `Object[]` |
| `Object[].class.isAssignableFrom(int[].class)` | `false` | `int[]` is not an array of `Object` references |
| `Object.class.isAssignableFrom(int[].class)` | `true` | Every array is an `Object` |
| `Cloneable.class.isAssignableFrom(int[].class)` | `true` | Every array implements `Cloneable` |
| `java.io.Serializable.class.isAssignableFrom(int[].class)` | `true` | Every array implements `Serializable` |

Array covariance **does not guarantee** that every element write is safe: an `Object[]` variable referencing a `String[]` still throws `ArrayStoreException` if you try to store an `Integer` in it.

Passing `null` to `isAssignableFrom(null)` throws `NullPointerException` because the method requires a class token to compare against.

## 3. `Class.cast(Object)`: Checking and Casting an Object

`Class<T>.cast(Object)` performs a runtime cast according to the represented type token. The result has static type `T` thanks to the generic parameter of the `Class<T>` token:

~~~java
Object raw = "hello";
String text = String.class.cast(raw); // "hello"
Runnable.class.cast(raw);             // ClassCastException: String does not implement Runnable
~~~

For reference types, you can think of it roughly as a runtime-checked cast. The key difference is that **the target type can be passed in as a parameter**:

~~~java
static <T> T requireType(Class<T> expected, Object value) {
    return expected.cast(value);
}

// Call: String name = requireType(String.class, someObject);
~~~

Cases to remember:

- `target.cast(null)` returns `null` and **does not** throw an exception.
- An object not belonging to the target type or a compatible subtype → `ClassCastException`.
- A successful cast returns **the exact same object reference**, without cloning, converting values, or calling a constructor.
- `int.class.cast(Integer.valueOf(1))` throws `ClassCastException`: `int.class` is a primitive token, while the object is an `Integer`; boxing/unboxing does not happen in `Class.cast`.
- `Class<?> unknown = ...` can still call `unknown.cast(value)`, but the compiler cannot infer it is a `Task`. You need a `Class<Task>` token or a valid token-narrowing step.

If you only need a `true/false` answer for **an object**, use `expected.isInstance(value)` (dynamic equivalent of `instanceof`) instead of catching `ClassCastException` for routine checks.

## 4. `Class.asSubclass(Class<U>)`: Narrowing a *Class Token* Safely

Suppose a scanner returns `Class<?>`, while a downstream API requires `Class<? extends Task>`. Casting the generic directly:

~~~java
// Avoid: unchecked cast, type relationship is not verified at runtime.
// Class<? extends Task> typed = (Class<? extends Task>) candidate;
~~~

has no safety guarantee from the compiler. Instead:

~~~java
Class<?> candidate = EmailTask.class;
Class<? extends Task> typed = candidate.asSubclass(Task.class);
~~~

`asSubclass` checks `Task.class.isAssignableFrom(candidate)` for compatibility and returns **the same `candidate` token** with the new static type. If incompatible, it throws `ClassCastException`:

~~~java
String.class.asSubclass(Task.class); // ClassCastException
Task.class.asSubclass(Task.class);   // Valid: same type
~~~

The name "subclass" in this API includes **the type itself** and types that **implement an interface**. It does not require a direct `extends` branch.

What `asSubclass` changes is **how the compiler views the `Class` token**; it does not cast an object instance. To check an object, use `cast`; to learn the relationship between two tokens without throwing an exception, use `isAssignableFrom`.

## 5. Complete Runnable Example (Java 17+)

Save everything into **`ClassCompatibilityDemo.java`**. The example covers interfaces, assignment direction, arrays, primitives, object casting, and narrowing a token to instantiate an implementation via reflection.

~~~java
public class ClassCompatibilityDemo {
    interface Task { String run(); }

    static final class EmailTask implements Task {
        public EmailTask() {}

        @Override
        public String run() { return "sent"; }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> candidate = EmailTask.class;

        System.out.println("Task <- EmailTask: " + Task.class.isAssignableFrom(candidate));
        System.out.println("EmailTask <- Task: " + EmailTask.class.isAssignableFrom(Task.class));
        System.out.println("Task <- Task: " + Task.class.isAssignableFrom(Task.class));
        System.out.println("Object <- Task: " + Object.class.isAssignableFrom(Task.class));
        System.out.println("Number[] <- Integer[]: " + Number[].class.isAssignableFrom(Integer[].class));
        System.out.println("Object[] <- int[]: " + Object[].class.isAssignableFrom(int[].class));
        System.out.println("Object <- int[]: " + Object.class.isAssignableFrom(int[].class));
        System.out.println("long <- int: " + long.class.isAssignableFrom(int.class));
        System.out.println("int <- int: " + int.class.isAssignableFrom(int.class));

        Object obj = new EmailTask();
        Task task = Task.class.cast(obj);
        System.out.println("cast: " + task.run());
        System.out.println("null cast: " + (Task.class.cast(null) == null));

        Class<? extends Task> typedClass = candidate.asSubclass(Task.class);
        Task created = typedClass.getDeclaredConstructor().newInstance();
        System.out.println("asSubclass: " + created.run());

        try { Task.class.cast("text"); }
        catch (ClassCastException e) {
            System.out.println("cast error: " + e.getClass().getSimpleName());
        }

        try { String.class.asSubclass(Task.class); }
        catch (ClassCastException e) {
            System.out.println("asSubclass error: " + e.getClass().getSimpleName());
        }
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 ClassCompatibilityDemo.java
java ClassCompatibilityDemo
~~~

Exact stdout (compiled and run with `--release 17`):

~~~text
Task <- EmailTask: true
EmailTask <- Task: false
Task <- Task: true
Object <- Task: true
Number[] <- Integer[]: true
Object[] <- int[]: false
Object <- int[]: true
long <- int: false
int <- int: true
cast: sent
null cast: true
asSubclass: sent
cast error: ClassCastException
asSubclass error: ClassCastException
~~~

The error-catching lines print the **exception type name** via `getSimpleName()`, so they do not depend on error message details across JDK versions. Both `cast` and `asSubclass` only verify compatibility: the constructor call via `getDeclaredConstructor().newInstance()` is what actually creates the object.

## 6. Applying in Plugin / Factory Design

A factory can receive a class name from configuration and a type contract from the caller. **The following snippet is an illustrative method**, which must be placed inside a Java class with a valid implementation provided; it is not a standalone program:

~~~java
static <S> S create(String className, Class<S> contract)
        throws ReflectiveOperationException {
    Class<?> raw = Class.forName(className);

    if (!contract.isAssignableFrom(raw)) {
        throw new IllegalArgumentException(
                raw.getName() + " does not implement " + contract.getName());
    }

    Class<? extends S> implementation = raw.asSubclass(contract);
    return implementation.getDeclaredConstructor().newInstance();
}
~~~

Step-by-step explanation:

1. `Class.forName(className)` loads/retrieves the class token by its full name; in the single-argument overload, class initialization may occur. You should not arbitrarily load class names from untrusted input.
2. `contract.isAssignableFrom(raw)` checks whether the contract is satisfied; if not, it throws a clear business error.
3. `raw.asSubclass(contract)` brings the checked relationship into the **static type** `Class<? extends S>`, convenient for reflection APIs.
4. `getDeclaredConstructor().newInstance()` invokes the no-argument constructor and returns an object of type `S`. You must ensure the class is concrete and the constructor exists and is accessible; otherwise reflection can throw `NoSuchMethodException`, `InstantiationException`, `IllegalAccessException`, or `InvocationTargetException`.

Another place might receive an object from a framework or reflection and apply the contract:

~~~java
Object value = /* result from framework */ null;
Task task = Task.class.cast(value); // May return null; check for null if the contract forbids it.
~~~

`cast` **does not guarantee non-null**. If the result can be empty, you must check for `null` according to business requirements. In the factory above, a successful constructor call returns an object; whether that class behaves safely/validly remains a separate responsibility of the application.

## 7. Limitations and Common Mistakes

**Wrong direction of `isAssignableFrom`.** When filtering classes implementing `Task`, write `Task.class.isAssignableFrom(candidate)`. Writing it backward as `candidate.isAssignableFrom(Task.class)` usually filters the wrong types or drops the subtypes you want to select.

**Equating `Class` with an instance.** `Task.class.isAssignableFrom(EmailTask.class)` compares two types; `Task.class.isInstance(object)` checks an instance and returns a boolean; `Task.class.cast(object)` checks an instance and returns a `Task`-typed reference or throws an error; `EmailTask.class.asSubclass(Task.class)` checks a token and returns a token with a narrower generic type. Do not substitute them for one another arbitrarily.

**Assuming `cast` converts values.** `String.class.cast(123)` does not turn `123` into `"123"`. Use value conversion APIs such as `String.valueOf` or appropriate parsing when the requirement is data conversion.

**Assuming these methods verify generic parameters.** Because of type erasure, `List.class.isAssignableFrom(ArrayList.class)` only verifies the raw type relationship; it does not prove elements are `String` or `Integer`. There is no `List<String>.class` literal in Java. To verify element types, you must inspect the contents or read appropriate generic metadata (`ParameterizedType`) when that metadata is actually present.

**Confusing primitives with wrappers.** `Integer.class` differs from `int.class`; `Integer.class.isAssignableFrom(int.class)` is `false`. Neither primitive widening nor boxing/unboxing is applied by `isAssignableFrom`. `Class.cast` also does not convert an object into a primitive.

**Ignoring class loaders.** Two classes with the same full name defined by two different defining class loaders can still be two distinct runtime types. Thus matching names are not enough for `isAssignableFrom`, `cast`, or `asSubclass` to succeed; plugin systems must pay attention to how contract interfaces are shared across loaders.

**Assuming type compatibility means instantiability.** `asSubclass` does not check whether a class is `abstract` or an interface, whether a suitable constructor exists, accessibility, exceptions from constructors, or side effects during class loading. `Class.newInstance()` is deprecated; prefer `getDeclaredConstructor().newInstance()` when reflective construction is needed.

**Passing null without care.** `isAssignableFrom(null)` and `asSubclass(null)` throw `NullPointerException`, whereas `cast(null)` returns `null`. When designing APIs, define clearly which inputs are accepted.

## 8. Choosing a Method by Scenario

- Have **two `Class` objects** and only need to decide whether to accept a subtype → `target.isAssignableFrom(candidate)`.
- Have **an object**, need a typed value, and accept an exception if wrong → `target.cast(object)`.
- Have **an object** and only want to test first and branch → `target.isInstance(object)`.
- Have a **`Class<?>`** from reflection and need to convert it to **`Class<? extends Contract>`** to pass to an API or obtain a typed constructor → `candidate.asSubclass(Contract.class)`.

A common sequence in runtime extensibility is: **load `Class<?>` token → check `Contract.class.isAssignableFrom(raw)` → narrow via `raw.asSubclass(Contract.class)` → instantiate via constructor → use the value as `Contract`**. If an object comes from another source, you can use `Contract.class.cast(value)` to check right at the boundary where the object is received.

Standard documentation: [Java SE 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html), sections `isAssignableFrom`, `cast`, `asSubclass`, and `isInstance`.