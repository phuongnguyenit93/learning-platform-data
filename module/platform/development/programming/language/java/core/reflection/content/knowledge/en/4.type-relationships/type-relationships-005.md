# Distinguishing Declared Relationships from Actual Object Types in Java Reflection

## 1. Why Distinguish These Two Kinds of Type Information?

In Java, a reference expression has a **declared type** (declared/static type) determined by source code at compile time, whereas the object that the reference points to has an **actual runtime class** (runtime class). These two pieces of information can differ, yet must be assignment-compatible.

```java
Animal animal = new Dog();
```

Suppose `Dog extends Animal`:

- `Animal` is the declared type of the local variable `animal`. The compiler uses this type to check method calls, member access, and overload selection.
- `Dog` is the actual class of the object created by `new Dog()`. `animal.getClass()` returns the `Class` object representing `Dog`.
- `Dog` must be a suitable subtype of `Animal` for the assignment to be valid. **The declared type does not automatically change to `Dog`** after the assignment.
- An object carries information about its own actual class; it does not carry information that a specific variable was declared as `Animal`. Multiple variables with different declared types can reference the same object.

**Common trap:** `animal.getClass()` does **not** return `Animal.class` in the example above. It returns `Dog.class`. Standard Reflection on `Object` does not provide an API to obtain the declared type of the local variable `animal` from that reference.

## 2. Reading the Right Data with Reflection

| What question needs an answer? | API / information source | Meaning |
| --- | --- | --- |
| Which class does this object actually belong to? | `obj.getClass()` | The runtime class of a non-`null` object. |
| What kind of value is the field **declared** to accept? | `Field.getType()` | `Class<?>` representing the declared type of the field; for generics, this is the erased type. |
| What class of object does the field currently hold? | `Field.get(instance)` then `value.getClass()` | Must read the actual value and check for `null`. |
| What return type does the method declare? | `Method.getReturnType()` | The return type in the method declaration; not the class of the value returned by a particular call. |
| What parameter types does the method declare? | `Method.getParameterTypes()` | The declared parameter types. Actual arguments can be instances of subtypes. |
| In which class is the member declared? | `Field.getDeclaringClass()`, `Method.getDeclaringClass()` | **The class that owns the member declaration**, not the type of the field, argument, or result. |
| What does a class declare it extends/implements? | `Class.getSuperclass()`, `Class.getInterfaces()` | Inheritance relationships declared on the class under inspection. |
| Can a type accept a value of another type? | `Target.class.isAssignableFrom(Source.class)` | Checks type compatibility in the `Source` → `Target` direction. |
| Is an object an instance of a type? | `Target.class.isInstance(obj)` | Equivalent to a dynamic type check like `obj instanceof Target` for reference types. |

The names `getDeclaredField()`, `getDeclaredFields()`, and `getDeclaredMethod()` mean finding only members **declared directly in the queried class**, rather than searching inherited members. The word "Declared" here does **not** mean returning the declared type of a *variable referencing* the object.

For example, `Box.class.getDeclaredField("pet").getType()` gets the type of the `pet` field in `Box`, whereas `box.pet.getClass()` gets the class of the object currently held in that field.

## 3. Compilable and Runnable Java 17+ Example

Save the following program verbatim into a file named `DeclaredVsRuntime.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.util.List;

public class DeclaredVsRuntime {
    public static class Animal {
        public String speak() {
            return "Animal";
        }
    }

    public static class Dog extends Animal {
        @Override
        public String speak() {
            return "Woof";
        }

        public void fetch() {}
    }

    public static class Box {
        public Animal pet = new Dog();
        public List<Animal> friends = List.of(new Dog());
    }

    public static void inspect(Animal input) {
        System.out.println("parameter actual = "
                + input.getClass().getSimpleName());
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Animal animal = new Dog();
        System.out.println("reference runtime = "
                + animal.getClass().getSimpleName());

        Box box = new Box();
        Field petField = Box.class.getDeclaredField("pet");
        Object petValue = petField.get(box);
        System.out.println("field declared = "
                + petField.getType().getSimpleName());
        System.out.println("field actual = "
                + petValue.getClass().getSimpleName());
        System.out.println("field owner = "
                + petField.getDeclaringClass().getSimpleName());

        Method speak = Animal.class.getDeclaredMethod("speak");
        System.out.println("method owner = "
                + speak.getDeclaringClass().getSimpleName());
        System.out.println("return declared = "
                + speak.getReturnType().getSimpleName());
        System.out.println("invoke result = " + speak.invoke(animal));

        Method inspect = DeclaredVsRuntime.class
                .getDeclaredMethod("inspect", Animal.class);
        System.out.println("parameter declared = "
                + inspect.getParameterTypes()[0].getSimpleName());
        inspect(animal);

        System.out.println("Animal accepts Dog = "
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog accepts Animal = "
                + Dog.class.isAssignableFrom(Animal.class));
        System.out.println("is Animal instance = "
                + Animal.class.isInstance(animal));

        Field friendsField = Box.class.getDeclaredField("friends");
        ParameterizedType genericType =
                (ParameterizedType) friendsField.getGenericType();
        System.out.println("generic argument is Animal = "
                + (genericType.getActualTypeArguments()[0] == Animal.class));
    }
}
```

Run on JDK 17 or higher:

```bash
javac DeclaredVsRuntime.java
java DeclaredVsRuntime
```

Stdout output:

```text
reference runtime = Dog
field declared = Animal
field actual = Dog
field owner = Box
method owner = Animal
return declared = String
invoke result = Woof
parameter declared = Animal
parameter actual = Dog
Animal accepts Dog = true
Dog accepts Animal = false
is Animal instance = true
generic argument is Animal = true
```

Explanation of key points:

1. `Animal animal = new Dog()` is valid because `Dog` inherits from `Animal`. `getClass()` reads the object's class, so it prints `Dog`.
2. `petField.getType()` stays fixed at `Animal.class` because that is the declared type in `Box`; `petField.get(box)` currently returns a `Dog` object. If other code assigns a different subtype to `box.pet`, the field's declared type remains `Animal`.
3. `petField.getDeclaringClass()` returns `Box.class`: `Box` is where the field is declared, **not** the type of the field's value.
4. `Animal.class.getDeclaredMethod("speak")` yields the `Method` whose declaring class is `Animal` and declared return type is `String`. When `speak.invoke(animal)` runs, Java still applies **dynamic dispatch** for overridden instance methods, so it executes `Dog.speak()` and yields `Woof`. `Method.invoke` does not disable polymorphism.
5. `inspect` declares parameter `Animal`; this call passes a `Dog` object. `getParameterTypes()` knows only the declared type of the parameter, while `input.getClass()` sees the actual object.
6. `Animal.class.isAssignableFrom(Dog.class)` returns `true` in the direction "an `Animal` variable can accept a `Dog` object". Swapping the two sides is not equivalent.
7. `friendsField.getGenericType()` reads the `List<Animal>` information preserved in the field declaration metadata; doing so does not prove that every element added at runtime has the exact class `Animal` (an element may be a `Dog`).

## 4. What Does the Declared Type Determine, and What Does the Actual Type Determine?

### Member Access and Overload Resolution Are Determined at Compile Time

```java
Animal a = new Dog();
a.speak();   // Valid: speak is declared in Animal.
// a.fetch(); // Compile error: Animal does not declare fetch.
```

Even though the object is a `Dog`, the method name `fetch` does not appear on the static type `Animal`. To call subtype-specific functionality, check the dynamic type first and then use the narrowed variable:

```java
if (a instanceof Dog dog) {
    dog.fetch();
}
```

Overloading (`choose(Animal)` and `choose(Dog)`) is selected primarily by the type of the passed expression at compile time; overriding (`Animal.speak()` overridden by `Dog`) is selected dynamically based on the object's class at runtime. Therefore, you cannot use `obj.getClass()` to infer which overload Java selected from the original call-site syntax.

### Invoking Overridden Methods Follows the Actual Type

With `Animal a = new Dog()`, the expression `a.speak()` uses the declaration visible through `Animal` yet the behavior of `Dog`. In Reflection, if you have a `Method` for an instance method on a superclass, `method.invoke(a)` likewise dispatches to the appropriate overridden implementation (except for cases with special rules like `static` or `private`; `Method.invoke` cannot override methods that are not overridden).

### A Field Has a Stable Declared Type While Its Value Changes

`Field.getType()` reflects only the field's signature, independent of any specific instance. An `Animal pet` field can sequentially hold `new Dog()`, a subtype `Cat`, or `null`. Use `Field.get(obj)` to obtain the **value at the moment of reading**; only if it is not `null` can `getClass()` be called. For a `static` field, `Field.get(null)` is a valid way to read it if access permissions allow; `null` in this case is the `get` receiver argument, not the dynamic class of the value.

## 5. Checking Type Relationships Without Reversing Direction

`Class.isAssignableFrom` has a direction that is especially easy to confuse:

```java
boolean canStoreDogInAnimal = Animal.class.isAssignableFrom(Dog.class); // true
boolean canStoreAnimalInDog = Dog.class.isAssignableFrom(Animal.class); // false
```

How to read it: `Target.class.isAssignableFrom(Source.class)` means **a reference of type Target can be assigned a value of type Source** according to the API's type compatibility rules. This is useful when a framework wants to verify whether an implementation class satisfies an interface/superclass.

When you already have an **object** rather than a pair of `Class` objects, use `Target.class.isInstance(value)` to check (returns `false` for `null`). If you need to cast via Reflection, `Target.class.cast(value)` produces a type-checked reference, throwing `ClassCastException` if the value is incompatible. In regular Java, `instanceof` and pattern matching are usually clearer:

```java
Object candidate = new Dog();
if (candidate instanceof Animal animal) {
    System.out.println(animal.speak()); // Woof
}
```

`getSuperclass()` and `getInterfaces()` describe the **direct declared relationships** of a class, not necessarily listing all ancestors/transitive interfaces. When you want to ask about assignability and interface implementation across multiple levels, `isAssignableFrom` is usually more suitable than manually traversing every level.

## 6. Commonly Confused Cases

**`null` has no actual class to reflect on.** A variable `Animal a = null` still has declared type `Animal` in source code, but `a.getClass()` throws `NullPointerException`. Always check the value before asking for its runtime class.

**Generics undergo type erasure.** A field `List<Animal> friends` has `Field.getType() == List.class`. `Field.getGenericType()` can yield a `ParameterizedType` carrying the `Animal` argument from the declaration signature. However, `friends.getClass()` is the list's implementation class; it does not provide `List<Animal>` or the exact runtime class of each element. Element types can only be checked on each existing element, if non-`null`. `getGenericType()` is not a machine that "resolves" every actual type argument from an instance.

**Primitives differ from objects.** For an `int count` field, `Field.getType() == int.class`. When calling `Field.get(instance)`, Reflection boxes the result into an `Integer`; calling `getClass()` on the boxed value sees `Integer.class`, not `int.class`. `int.class` has no primitive-type instance on which to call `getClass()`.

**Arrays and interfaces.** `Object o = new String[2]` has `o.getClass() == String[].class`. Although a `String[]` array can be assigned to `Object[]` (array covariance), attempting to store an incompatible element into the actual array causes Java to throw `ArrayStoreException`. Both the assignability relationship and the array's runtime class must be considered.

**Proxies and dynamically generated classes.** If an object is a dynamic proxy, `getClass()` returns the proxy class generated at runtime, rather than the interface under which the reference was declared. Check whether it implements the interface with `SomeInterface.class.isInstance(proxy)` or `isAssignableFrom`; do not compare the proxy class name against the interface name.

**Class metadata is not variable metadata.** `Class<?> runtimeClass = value.getClass()` only carries the object's `Class`. Standard Reflection primarily inspects class, field, method, and constructor structures; there is no `getDeclaredType()` on `Object` to ask for the source type of each local reference. You can use `Field`, `Method`, or `Parameter` to read the declaration of the **corresponding member**, once you know which program element you want to inspect.

**Access permissions still apply.** `getDeclaredField` can find a `private` field, but `Field.get` or `Method.invoke` can throw `IllegalAccessException` if access has not been permitted. Java modules can restrict deep reflection; knowing the runtime class does not automatically grant permission to open internal members.

## 7. How to Choose the API in Real-World Problems

When processing an object in a framework, start from the specific question:

1. **API contract**: need to know the *declared* property, parameter, or return type? Read `Field.getType()`, `Method.getParameterTypes()`, `Method.getReturnType()`, and `getGenericType()`/`getGenericReturnType()` when generic metadata is needed. This is the foundation for schema validation, binding, and converter selection.
2. **Value at runtime**: need to know what class the current object actually is? Read `value.getClass()` after checking for `null`. Do not use it in place of the declared signature.
3. **Compatibility**: need to ask whether an implementation class is assignable to an API type? Use `targetType.isAssignableFrom(candidateType)`; if you already have a value, use `targetType.isInstance(value)`.
4. **Polymorphic behavior**: need to invoke an overridden instance method? Use a normal Java call or `Method.invoke` when reflection is genuinely needed; the actual class determines the dispatched implementation.
5. **Member declaration source**: need to know which class a `Field`/`Method` belongs to? Use `getDeclaringClass()`, do not infer it from `getType()` or the value's `getClass()`.

**Self-check:** with the declaration `Number n = Integer.valueOf(7)`, the variable type is `Number`, `n.getClass()` is `Integer.class`, and `Number.class.isAssignableFrom(Integer.class)` is `true`. If `n` is changed to `null`, the declared type is still `Number`, yet there is no runtime object on which to call `getClass()`. This is the distinction to maintain consistently when reading and writing Reflection code.
