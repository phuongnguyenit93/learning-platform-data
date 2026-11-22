# Reference Conversion by Assignability in Java Reflection

## 1. Objectives

When invoking a method or constructor using Java Reflection, developers pass arguments through APIs such as `Method.invoke(...)` or `Constructor.newInstance(...)`. These APIs accept `Object` on the caller side, but the **actual parameter** of the target method can be `Animal`, `Serializable`, `Object[]`, an interface, or any reference type. The JVM must determine whether the actual object can be used at that parameter position.

The core rule of this lesson is **assignability**: a reference value can enter a place requiring a target reference type if the object has a runtime type compatible with the target type via inheritance/implementation relationships; `null` is also valid for a reference-type parameter. This is the basis of **widening reference conversion** and reflective argument checking.

After this lesson, you will:

- Understand the exact checking direction of `Target.class.isAssignableFrom(Source.class)`.
- Distinguish widening reference conversion (*widening*), narrowing casts (*narrowing*), and primitive conversions.
- Apply this to `Method.invoke`, `Constructor.newInstance`, and `Field.set`.
- Properly handle interfaces, arrays, `null`, generic type erasure, class loaders, and exceptions.
- Avoid confusing the runtime arguments of the target method with the `Object...` varargs array of the Reflection API itself.

## 2. What does "assignable" mean?

Suppose we have a type hierarchy:

```java
interface Pet {}

class Animal {}

class Dog extends Animal implements Pet {}

class Cat extends Animal {}
```

These are **illustrative declarations**, not a standalone program.

In normal Java code:

```java
Dog dog = new Dog();
Animal animal = dog; // Valid: Dog -> Animal
Pet pet = dog;       // Valid: Dog -> Pet
Object object = dog; // Valid: Dog -> Object
```

When passing `dog` to a method declared as `accept(Animal animal)`, no object copy is needed and the runtime class does not need to change. It is still the **same `Dog` object**, merely used through a wider reference type.

In the opposite direction:

```java
Animal animal = new Animal();
// Dog dog = animal; // Compile error: cannot implicitly narrow.
```

Only an explicitly written cast `(Dog) animal` requests a narrowing check at runtime; for an object whose actual type is `Animal`, the cast fails with `ClassCastException`. **Reflection does not guess, does not automatically downcast an incompatible object, and does not create a new `Dog`.**

Distinguish three points:

| Situation | Can be passed to a `Dog` parameter? | Reason |
| --- | --- | --- |
| Runtime value is `new Dog()` | Yes | Object has the exact target type |
| Variable declared as `Animal` but pointing to `new Dog()` | Yes, when passed via Reflection | Runtime argument check sees the object is actually a `Dog` |
| Runtime value is `new Cat()` | No | `Cat` is not a subtype of `Dog` despite sharing superclass `Animal` |
| `null` | Yes | `null` is valid for any reference-type parameter |
| String `"Dog"` | No | No automatic conversion from a string to a `Dog` object |

**Special point about Reflection:** parameters of `invoke` are received as `Object`, so Reflection-calling source code has no static check like a normal `accept(Dog)` call. Compatibility of the **actual value** is checked when Reflection prepares to invoke the target method.

## 3. `Class.isAssignableFrom`: the checking direction must not be reversed

```java
boolean allowed = TargetType.class.isAssignableFrom(SourceType.class);
```

Equivalent statement: "Can a value of type `SourceType` be placed into a variable/parameter of type `TargetType`?" For reference types, the check is based on identical type, superclass relationships, implemented interfaces, and certain array relationships.

Examples:

```java
Animal.class.isAssignableFrom(Dog.class); // true
Pet.class.isAssignableFrom(Dog.class);    // true
Object.class.isAssignableFrom(Dog.class); // true
Dog.class.isAssignableFrom(Animal.class); // false
Dog.class.isAssignableFrom(Cat.class);    // false
Dog.class.isAssignableFrom(Dog.class);    // true
```

This snippet uses the types declared in section 2 and is illustrative.

### 3.1. Three easily confused APIs

| API | Actual question | Notes |
| --- | --- | --- |
| `targetType.isAssignableFrom(sourceType)` | Does the relationship between **two `Class<?>` objects** allow assigning the source type to the target type? | `sourceType` must be non-`null`; passing `null` raises `NullPointerException`. |
| `targetType.isInstance(value)` | Is this **runtime object** an instance of the target type? | Returns `false` when `value == null`, even though `null` can still be validly passed to a reference parameter. |
| `targetType.cast(value)` | Casts the object according to the `Class` type at runtime | Returns `null` if `value == null`; throws `ClassCastException` if the object is incompatible. |

Therefore, if you want to **check an argument before calling Reflection**, a reference type check typically takes the form:

```java
static boolean acceptsReference(Class<?> targetType, Object value) {
    if (targetType.isPrimitive()) {
        throw new IllegalArgumentException("Reference parameter required");
    }
    return value == null || targetType.isInstance(value);
}
```

This is an **illustrative helper**, not a standalone runnable program. It handles `null` explicitly instead of using only `isInstance`. You can also obtain `value.getClass()` and call `targetType.isAssignableFrom(...)` when `value` is non-`null`.

You must not take the declared type of the **caller-side Java variable** to decide, because Reflection receives the actual object value. For example, a variable `Animal candidate = new Dog();` still has runtime class `Dog`.

### 3.2. Primitive relationships differ from reference relationships

`Class.isAssignableFrom` for primitives requires the **exact same primitive type**:

```java
int.class.isAssignableFrom(int.class);   // true
long.class.isAssignableFrom(int.class);  // false
Object.class.isAssignableFrom(int.class);// false
```

This does not mean Reflection does not support primitive widening in any API: `Method.invoke` and `Constructor.newInstance` can **unbox wrappers** and apply appropriate **widening primitive conversion** for primitive parameters. That is a different mechanism and should be studied separately. **Do not use `isAssignableFrom` to simulate all primitive argument rules**.

In this lesson, we analyze only **reference type conversion** between objects/arrays/interfaces and `null` arguments.

## 4. Assignability in three Reflection usage sites

### 4.1. `Method.invoke`

```java
Method method = Example.class.getDeclaredMethod("accept", Animal.class);
method.invoke(null, new Dog());
```

This is **illustrative code**, assuming `Example.accept(Animal)` is static, `java.lang.reflect.Method` is imported, and `Animal`, `Dog` types exist. The argument `new Dog()` is compatible with the declared parameter `Animal`; Reflection executes the call.

If you pass a `new Object()` to an `Animal` parameter, the argument is invalid: `Method.invoke` throws `IllegalArgumentException` **before running the target method body**. There is no automatic conversion from `Object` to `Animal`.

If a target method **itself throws an exception after being called**, `Method.invoke` typically wraps that exception in `InvocationTargetException`; do not confuse it with `IllegalArgumentException` caused by **argument mismatch** during call preparation.

### 4.2. `Constructor.newInstance`

```java
Constructor<Example> constructor =
        Example.class.getDeclaredConstructor(Animal.class);
Example instance = constructor.newInstance(new Dog());
```

This snippet is illustrative, assuming `Example` has the appropriate constructor and `java.lang.reflect.Constructor` is imported. Argument compatibility rules are similar to method invocation: `Dog` can satisfy `Animal`; an incompatible object is rejected.

Note: `getDeclaredConstructor(...)` looks up a constructor by **exact declared parameter types**. It does not find constructors by assignability:

```java
// If the class only has constructor Example(Animal), the query below
// cannot find constructor Example(Dog):
// Example.class.getDeclaredConstructor(Dog.class);
```

**Member lookup** and **argument checking at invocation** are two separate phases.

### 4.3. `Field.set`

```java
Field field = Example.class.getDeclaredField("animal");
field.setAccessible(true);
field.set(example, new Dog());
```

This is an illustrative snippet with a field declared as `Animal animal` in object `example`. `Field.set` checks that the assigned object is valid for the **field type**. If the field is `Animal`, it accepts `Dog` or `Cat`, but rejects `String` with `IllegalArgumentException`.

`setAccessible(true)` only addresses part of access control; it **does not turn the field's type into `Object`**. In addition, `final` fields or module boundaries may carry their own constraints on mutability, independent of assignability. Do not use `Field.set` as a shortcut to force invalid types.

## 5. Complete Java 17+ program and exact output

Save the following code to **`AssignabilityDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

public class AssignabilityDemo {
    interface Pet { String sound(); }
    static class Animal {}

    static final class Dog extends Animal implements Pet {
        public String sound() { return "woof"; }
    }

    static final class Cat extends Animal {}

    static final class Receiver {
        private Animal stored;

        Receiver(Animal animal) {
            System.out.println("constructor=" + animal.getClass().getSimpleName());
        }

        static void describe(Animal animal) {
            System.out.println("method=" + animal.getClass().getSimpleName());
        }

        static void speak(Pet pet) {
            System.out.println("interface=" + pet.sound());
        }

        static void describeNullable(Animal animal) {
            System.out.println("null=" + (animal == null));
        }

        static void array(Object[] objects) {
            System.out.println("array=" + objects.getClass().getSimpleName());
        }

        static void requireDog(Dog dog) {
            System.out.println("dog=" + dog.sound());
        }

        static void generic(List<String> values) {
            System.out.println("generic-size=" + values.size());
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Animal<-Dog="
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Pet<-Dog="
                + Pet.class.isAssignableFrom(Dog.class));
        System.out.println("Dog<-Animal="
                + Dog.class.isAssignableFrom(Animal.class));
        System.out.println("Object[]<-String[]="
                + Object[].class.isAssignableFrom(String[].class));
        System.out.println("String[]<-Object[]="
                + String[].class.isAssignableFrom(Object[].class));
        System.out.println("Object<-int="
                + Object.class.isAssignableFrom(int.class));
        System.out.println("Animal.isInstance(null)="
                + Animal.class.isInstance(null));

        Constructor<Receiver> constructor =
                Receiver.class.getDeclaredConstructor(Animal.class);
        Receiver receiver = constructor.newInstance(new Dog());

        Method describe = Receiver.class.getDeclaredMethod(
                "describe", Animal.class);
        describe.invoke(null, new Dog());

        Method speak = Receiver.class.getDeclaredMethod("speak", Pet.class);
        speak.invoke(null, new Dog());

        Method nullable = Receiver.class.getDeclaredMethod(
                "describeNullable", Animal.class);
        nullable.invoke(null, new Object[] { null });

        Method array = Receiver.class.getDeclaredMethod("array", Object[].class);
        array.invoke(null, (Object) new String[] { "a", "b" });

        Field stored = Receiver.class.getDeclaredField("stored");
        stored.setAccessible(true);
        stored.set(receiver, new Dog());
        System.out.println("field="
                + stored.get(receiver).getClass().getSimpleName());

        try {
            Method onlyDog = Receiver.class.getDeclaredMethod(
                    "requireDog", Dog.class);
            onlyDog.invoke(null, new Cat());
        } catch (IllegalArgumentException exception) {
            System.out.println("wrong-argument="
                    + exception.getClass().getSimpleName());
        }

        try {
            stored.set(receiver, "not an Animal");
        } catch (IllegalArgumentException exception) {
            System.out.println("wrong-field="
                    + exception.getClass().getSimpleName());
        }

        Method generic = Receiver.class.getDeclaredMethod(
                "generic", List.class);
        generic.invoke(null, List.of(10, 20));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 AssignabilityDemo.java
java AssignabilityDemo
```

**Stdout verified with JDK 21 using `--release 17`:**

```text
Animal<-Dog=true
Pet<-Dog=true
Dog<-Animal=false
Object[]<-String[]=true
String[]<-Object[]=false
Object<-int=false
Animal.isInstance(null)=false
constructor=Dog
method=Dog
interface=woof
null=true
array=String[]
field=Dog
wrong-argument=IllegalArgumentException
wrong-field=IllegalArgumentException
generic-size=2
```

### 5.1. Interpreting the results

- `Animal<-Dog=true` and `Pet<-Dog=true` show that a `Dog` object can serve both a superclass parameter and an interface parameter it implements.
- `Dog<-Animal=false` shows the reverse direction is not allowed when only the **`Animal` type** is known. However, an actual runtime value of `Dog` can still be passed into a `Dog` parameter via Reflection.
- `Object[]<-String[]=true` shows **array covariance** for reference element types.
- `Animal.isInstance(null)=false` does not contradict `null=true`: the `isInstance` API evaluates an **instance**, whereas `null` is permitted for a **reference parameter**.
- The constructor and two method calls all accept `Dog` compatible with `Animal`/`Pet`; there is no need to manually convert the object to another class.
- `Field.set` accepts `Dog` when the field is declared as type `Animal`. With `String`, it rejects with `IllegalArgumentException`.
- Method `requireDog(Dog)` cannot accept `Cat`, even though `Cat` is also an `Animal`.
- `generic-size=2` intentionally demonstrates the limitation of type erasure, explained in section 7.

## 6. Three easily overlooked cases: `null`, interfaces, and arrays

### 6.1. The `null` argument

`null` is compatible with **every reference type**, including `String`, interfaces, arrays, and user-declared classes. It **cannot be passed to a primitive parameter** such as `int` or `boolean` under standard invoke mechanics.

For `Method.invoke`, the API signature itself is `invoke(Object obj, Object... args)`. To avoid ambiguity between one `null` argument and a `null` varargs argument array, pass explicitly:

```java
method.invoke(targetObject, new Object[] { null });
```

This is illustrative code: `method` has **exactly one reference-type parameter**, and `targetObject` is a valid receiver; if the method is static, target can be `null`. If you pass a `null` argument array directly into the API's varargs, Reflection may interpret it as **having no array containing arguments**, leading to an argument count mismatch. Declaring `new Object[]{null}` makes the intent clear.

### 6.2. Interfaces and multiple inheritance branches

A class can implement multiple interfaces. Therefore, an object can be assignable to multiple target types **that have no direct superclass/subclass relationship with each other**. For example, `Dog implements Pet`: checking `Pet.class.isAssignableFrom(Dog.class)` returns `true`.

With `Class<?>`, use subtype/runtime type relationships. Avoid comparing `getSimpleName()` strings or assuming you only need to inspect `getSuperclass()`; a valid path may come from an **interface**.

### 6.3. Array covariance and element checks on write

For reference-element arrays, `String[]` is a subtype of `Object[]`, so:

```java
Object[] values = new String[1];
values[0] = "ok";  // valid
// values[0] = 42; // compiles, but throws ArrayStoreException at runtime
```

This is illustrative code. The array **is still a real `String[]` at runtime**, so the JVM checks every element-store operation. Writing an `Integer` into a `String[]` array causes `ArrayStoreException` even though the variable has type `Object[]`.

**Primitive arrays differ:** `int[]` is a subtype of `Object`, `Cloneable`, and `java.io.Serializable`, but **is not** a subtype of `Object[]` (because `int` elements are not references). That is:

```java
Object.class.isAssignableFrom(int[].class);      // true
Object[].class.isAssignableFrom(int[].class);    // false
```

## 7. Generic type erasure: assignability does not check `T`

Java generics mostly have their type parameters erased at runtime (*type erasure*). For example, the method:

```java
static void generic(List<String> values) {
    System.out.println(values.size());
}
```

This is an excerpt from the `AssignabilityDemo` program. The raw runtime parameter type of this method is **`List.class`**, so the call:

```java
Method m = Receiver.class.getDeclaredMethod("generic", List.class);
m.invoke(null, List.of(10, 20));
```

is accepted by Reflection, even though the list of values contains `Integer`. In this example, the method only calls `size()`, so it prints `generic-size=2` without accessing elements under the assumption of `String`.

**Important consequences:**

- `List.class.isAssignableFrom(ArrayList.class)` can return `true`, but `Class<?>` carries no information about `List<String>` vs. `List<Integer>` to check individual elements.
- `Method.getParameterTypes()` gives raw `Class<?>` types; `Method.getGenericParameterTypes()` can provide `ParameterizedType` metadata describing the `List<String>` declaration.
- Generic metadata **does not automatically turn into a full runtime check** for every element during a Reflection call.
- If the method body reads an element as `String`, the compiler-inserted cast can throw `ClassCastException` **inside** the method. When invoked via Reflection, that exception is typically wrapped in `InvocationTargetException`.

If the program requires element verification, appropriate business/runtime checks must be implemented; `isAssignableFrom` on raw `Class<?>` alone is not enough.

## 8. Class loaders and type identity

Assignability checks the **actual runtime `Class<?>` object**, not merely the class name string. Two types with the same binary name defined by **two different class loaders** are not automatically the same type or subtypes of each other.

Theoretical example: plugin A and plugin B both load a definition of `com.example.PluginData` but via independent class loaders. If the class in B has no valid inheritance relationship with the class in A, then:

```text
typeFromA.getName().equals(typeFromB.getName()) -> true
typeFromA.isAssignableFrom(typeFromB)           -> false
```

This is an **illustrative scenario**, not a complete program setting up two class loaders. In plugin frameworks, app servers, or hot-reload environments, checking class names is not enough. Inspect `getClassLoader()`, the type loading source, and loader delegation boundaries as well.

## 9. Self-check exercises

1. Add `interface Trainable {}` and have `Dog implements Pet, Trainable`. Predict `Trainable.class.isAssignableFrom(Dog.class)` and try calling a method accepting `Trainable`.
2. Keep the variable `Animal value = new Dog();`, and invoke a target method accepting `Dog` via Reflection. Explain why the **runtime value** is compatible even though the variable's static type is `Animal`.
3. Call `Receiver.array(Object[])` with `String[]` and compare three approaches: casting `(Object)`, wrapping in `new Object[]{...}`, and passing the array directly.
4. Change `generic(List<String>)` to read `values.get(0)` into a `String` variable; try passing `List.of(10)` via Reflection and observe `InvocationTargetException.getCause()`.
5. Create a field declared as `Pet` and try `Field.set` with `new Dog()`, `new Cat()`, and `null`. Predict the behavior based on assignability.
6. Explain for yourself why `Object.class.isAssignableFrom(int.class)` is `false` whereas `Object.class.isAssignableFrom(Integer.class)` is `true`.

## 10. Checklist before calling Reflection

- Identify the **formal parameter type** using `getParameterTypes()` or `Field.getType()`.
- For non-`null` values, check `targetType.isInstance(value)` or `targetType.isAssignableFrom(value.getClass())` **when target is a reference type**.
- For `null`, confirm the target parameter is a reference type and package `Object[]` with the right count.
- Do not mix downcasting, parsing, primitive conversion, or generic verification into the scope of **reference assignability**.
- For an argument that is an array, check how Java packages `Object...` of `invoke`.
- When errors occur, distinguish **member lookup**, **access permissions**, **invalid arguments**, and **exceptions from the method body**.
- In plugin/multi-class-loader environments, rely on true `Class<?>` identity rather than name strings.

**Takeaway:** Reference conversion via Reflection is based on the **actual runtime type** and the **assignability** relationship with the target parameter/field type. `Target.class.isAssignableFrom(Source.class)` is a question about two types; `Target.class.isInstance(value)` is a question about a non-`null` value. By checking in the right direction, handling `null` explicitly, and distinguishing the varargs layer of `Method.invoke`, you can diagnose most reference conversion errors in Reflection.