# Covariant Return Types and Method Contracts in Java Generics Inheritance

## 1. The Problem and Core Takeaways

When a subclass **overrides** a superclass method, Java allows the subclass method to return **a more specific type** than the return type in the parent's contract. This mechanism is called a **covariant return type**. It is very useful when extending generic classes: the superclass defines an operation using type parameter `T`; the subclass fixes `T` to a concrete type, and then provides a more specific result while remaining usable through a superclass reference.

Example:

```java
class Animal {
    String name() { return "animal"; }
}

class Dog extends Animal {
    String bark() { return "gâu"; }
}

class AnimalFactory {
    Animal create() { return new Animal(); }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() { return new Dog(); } // Valid: Dog is a subtype of Animal.
}
```

With `DogFactory`, the `create()` method can return `Dog`, yet a call through an `AnimalFactory` reference still has a contract returning `Animal`. The object's actual behavior is still selected by **dynamic dispatch**, not by the return type at the call site.

Lesson objectives:

- Understand precisely when an override's return type can be more specific.
- Distinguish **return-type covariance** from **invariance of generic type arguments**.
- Read and write accurate contracts when a subclass extends `Parent<T>`, especially `extends Parent<Dog>`.
- Understand restrictions regarding **method parameters, visibility, checked exceptions, `final`/`static`**, and primitive/`void` types.
- Understand the roles of **type erasure** and **bridge methods**, avoiding manual casts or breaking type safety.
- Apply this to factory, repository, provider, builder, and collection APIs with runnable Java 17+ programs.

## 2. What Is a Covariant Return Type?

Suppose `Dog extends Animal`. When overriding an instance method in `AnimalSource` whose result is `Animal`, `DogSource` can return `Dog`:

```java
class AnimalSource {
    public Animal get() {
        return new Animal();
    }
}

class DogSource extends AnimalSource {
    @Override
    public Dog get() {
        return new Dog();
    }
}
```

The core rule is that **the return type of the overriding method must be compatible to substitute for the return type in the overridden method's contract** (*return-type substitutability*). For ordinary reference types, an appropriate subtype of the parent's return type is accepted.

Illustrative calls:

```java
DogSource direct = new DogSource();
Dog dog = direct.get(); // The expression type of get() is Dog.

AnimalSource general = direct;
Animal animal = general.get(); // The expression type of get() is Animal.
```

Both calls run on **the same object** `DogSource` and both execute `DogSource.get()`'s implementation. The static type of the variable at the call site determines what the compiler permits using next:

```java
Dog concrete = direct.get();
concrete.bark();                  // Valid.
Animal generalResult = general.get();
// generalResult.bark();          // Compile error: Animal does not declare bark().
```

The superclass contract guarantees users receive **at least an `Animal`**. The subclass fulfills the contract by providing a `Dog`, which is a valid `Animal`.

### Why Is It Useful?

If Java forced overrides to return the exact `Animal` type, callers of `DogSource` would have to cast:

```java
// Not needed when DogSource.get() returns Dog:
// Dog dog = (Dog) direct.get();
```

Covariant returns give callers a sufficiently specific result type, preserve compile-time checking, and reduce casts in specialized APIs.

## 3. Overriding Must First Satisfy the Method Contract

Covariant returns **only alter the return-type condition**; they do not mean the subclass can arbitrarily modify the method signature. To override properly, Java rules must still be satisfied for:

1. **Method name and parameter list** must match according to override/subsignature rules; you cannot arbitrarily change `Animal` to `Dog` in an **input parameter** and still call it an override.
2. The return type must be **return-type-substitutable** for the parent's return type.
3. The access level of the overriding method must not be **narrower** than the parent method's access level.
4. The overriding method must not declare new or broader checked exceptions than what the parent contract allows (it may declare a narrower set of exceptions).
5. You cannot override `final`, `private`, or `static` methods in the polymorphic instance-method sense. `static` is *method hiding* with its own rules.
6. Constructors **are not overridden methods** and have no return type; applying return-type covariance to constructors is out of scope.

Example with visibility and checked exceptions:

```java
import java.io.IOException;

class Reader {
    protected Animal load() throws IOException {
        return new Animal();
    }
}

class DogReader extends Reader {
    @Override
    public Dog load() {
        return new Dog();
    }
}
```

`DogReader.load()` widens access from `protected` to `public`, narrows the result type from `Animal` to `Dog`, and removes the checked exception `IOException`. All three are valid.

Invalid example:

```java
class BadDogReader extends Reader {
    // @Override
    // private Animal load() throws Exception {
    //     return new Dog();
    // }
    // Invalid: private narrows access; Exception is broader than IOException.
}
```

**Do not identify overrides solely by asking "are the names the same?"**. Always inspect the full contract, including parameter list, return type, visibility, and exceptions.

## 4. Using `T` of a Generic Superclass

Now consider a parameterized superclass:

```java
class Container<T> {
    private final T value;

    Container(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}
```

When a subclass fixes the type argument:

```java
class DogContainer extends Container<Dog> {
    DogContainer(Dog value) {
        super(value);
    }

    @Override
    public Dog get() {
        return super.get();
    }
}
```

With `DogContainer extends Container<Dog>`, the superclass's type parameter `T` is fixed to `Dog`, so callers see `Container<Dog>.get()` returning `Dog` even without overriding. Overriding in the subclass is still valid, and can add validation, logging, or value transformation when truly needed.

```java
Container<Dog> parentView = new DogContainer(new Dog());
Dog value = parentView.get(); // Checked as Dog.
```

**Two ideas must be kept separate:**

- **Generic substitution:** `T` in `Container<T>` is interpreted as `Dog` in `Container<Dog>`.
- **Return-type covariance:** when overriding a valid method, the subclass can choose a compatible return type that is **more specific** than what the parent method requires.

In this example, the override returning `Dog` is the same specialized type. The next example demonstrates both generic specialization and subtype covariance at the result level.

### When the Return Type Is Narrowed Further

```java
class Mammal extends Animal {}

class MammalContainer extends Container<Mammal> {
    MammalContainer(Mammal value) {
        super(value);
    }
}

class SpecificMammal extends Mammal {}

class SpecificMammalContainer extends Container<Mammal> {
    SpecificMammalContainer(SpecificMammal value) {
        super(value);
    }

    @Override
    public SpecificMammal get() {
        return (SpecificMammal) super.get();
    }
}
```

`Container<Mammal>.get()` has a contract returning `Mammal`. The subclass can return `SpecificMammal` because it is a subtype. However, the cast here is **only safe if an invariant genuinely guarantees every object in the container is a `SpecificMammal`**. If a parent method could be used to change the value to another `Mammal`, this override becomes dangerous.

A better design usually stores the specialized type from the start or enforces an initialization path preserving the invariant, such as using a subclass `extends Container<SpecificMammal>`. Do not use covariance as an excuse for an unproven cast.

## 5. Covariant Return and `extends Parent<String>`

With inheritance using a fixed type argument, Java maps the inherited method signature to a typed contract:

```java
class Parent<T> {
    public T read() {
        return null;
    }
}

class TextChild extends Parent<String> {
    @Override
    public String read() {
        return "Java";
    }
}
```

`String` is the result type that calls to `Parent<String>.read()` expose. By overriding with `String`, the subclass satisfies the contract. At compile time, callers can write:

```java
Parent<String> base = new TextChild();
String result = base.read(); // "Java"; no cast needed.
```

If `Parent<T>` has a bound:

```java
class NumberParent<T extends Number> {
    private final T number;
    NumberParent(T number) {
        this.number = number;
    }
    public T read() { return number; }
}

class IntegerChild extends NumberParent<Integer> {
    IntegerChild(Integer n) {
        super(n);
    }

    @Override
    public Integer read() {
        return super.read();
    }
}
```

`Integer` satisfies `T extends Number`. At the source level, callers of `NumberParent<Integer>` receive `Integer`. When handling erasure in bytecode, the compiler resolves necessary signature differences via bridge methods; clients do not have to write bridges manually.

### Getters Are Not the Only Place for Covariance

You can override a copy-producing method so it returns the subtype itself:

```java
class Copyable<T> {
    private final T value;
    Copyable(T value) { this.value = value; }
    public Copyable<T> copy() {
        return new Copyable<>(value);
    }
}

class StringCopyable extends Copyable<String> {
    StringCopyable(String value) { super(value); }

    @Override
    public StringCopyable copy() {
        return new StringCopyable("copy");
    }
}
```

`StringCopyable` is a subtype of `Copyable<String>`, so return type `StringCopyable` matches the parent's return type `Copyable<String>`. This is the **self-returning API** pattern used in builders, factories, copy/clone methods, and fluent APIs.

This does not mean Java has an automatic "self type" for every inheritance tree. If deeper subclasses need to return the new subclass itself, you may have to override again or consider a generic self-type pattern when needed.

## 6. Distinguishing Return Types from Method Parameter Types

Result covariance does not apply symmetrically to let you arbitrarily change **input parameters**:

```java
class AnimalHandler {
    public Animal handle(Animal item) {
        return item;
    }
}

class DogHandler extends AnimalHandler {
    // NOT an override of handle(Animal).
    public Dog handle(Dog item) {
        return item;
    }
}
```

`handle(Dog)` is an **overload**, because the parameter list changed. Calls via `AnimalHandler` still select the `handle(Animal)` signature; if the subclass does not override that signature, the parent implementation still runs.

To override properly:

```java
class CorrectDogHandler extends AnimalHandler {
    @Override
    public Dog handle(Animal item) {
        return new Dog();
    }
}
```

`CorrectDogHandler.handle(Animal)` keeps the `Animal` parameter while narrowing the result to `Dog`. Adding `@Override` helps the compiler catch confusion between overriding and overloading.

In generic inheritance, remember also that `List<Dog>` is **not** a subtype of `List<Animal>` even though `Dog extends Animal`. That is a matter of **invariance of parameterized types**, distinct from covariance of a single `Dog` return type.

## 7. Important: `List<Dog>` Cannot Replace `List<Animal>`

Suppose the superclass declares:

```java
class AnimalService {
    public java.util.List<Animal> findAll() {
        return java.util.List.of(new Animal());
    }
}
```

A subclass cannot override it with `List<Dog>`:

```java
class BadDogService extends AnimalService {
    // @Override
    // public java.util.List<Dog> findAll() {
    //     return java.util.List.of(new Dog());
    // }
    // Invalid: List<Dog> is not a subtype of List<Animal>.
}
```

Why? If that were accepted, code using an `AnimalService` reference could treat the result as `List<Animal>` and (if the list is mutable) add an `Animal` that is not a `Dog`, breaking the `List<Dog>` contract. Java keeps generic types **invariant** by default.

### Approach 1: Design the Parent Contract with an Appropriate Wildcard

If the API only needs to **supply/read** a list of `Animal`s, the superclass can return `List<? extends Animal>`:

```java
class AnimalCatalog {
    public java.util.List<? extends Animal> animals() {
        return java.util.List.of(new Animal());
    }
}

class DogCatalog extends AnimalCatalog {
    @Override
    public java.util.List<Dog> animals() {
        return java.util.List.of(new Dog());
    }
}
```

Here `List<Dog>` **is a subtype of** `List<? extends Animal>`, so the override is valid. Users of the parent reference read elements as `Animal`; they cannot arbitrarily add an `Animal` into the returned list via the wildcard variable:

```java
AnimalCatalog catalog = new DogCatalog();
java.util.List<? extends Animal> list = catalog.animals();
Animal first = list.get(0);
// list.add(new Animal()); // Compile error: elements have an unknown captured type.
```

With `List<? extends Animal>`, adding concrete values is not guaranteed to be safe; only adding `null` is allowed by the type system (implementations may still reject it).

### Approach 2: Parameterize the Parent Contract with Generics

If the exact element type needs to be preserved, you can design:

```java
class Service<T extends Animal> {
    public java.util.List<T> findAll() {
        return java.util.List.of();
    }
}

class DogService extends Service<Dog> {
    @Override
    public java.util.List<Dog> findAll() {
        return java.util.List.of(new Dog());
    }
}
```

`Service<Dog>.findAll()` already has type `List<Dog>` from substituting `T = Dog`; overriding in `DogService` preserves the exact contract. This is often the right approach when a domain API needs to operate on a single consistent type throughout.

**Do not replace the contract with raw `List` or unchecked casts** just to silence the compiler: doing so hides type-relationship errors and can lead to `ClassCastException` when consuming data.

## 8. Generic Interfaces and Covariant Return Types

Covariant returns do not apply only between two classes. A class implementing an interface can also return a more specific type than the interface's required result type:

```java
interface Producer<T> {
    T produce();
}

class AnimalProducer implements Producer<Animal> {
    @Override
    public Dog produce() {
        return new Dog();
    }
}
```

`Producer<Animal>.produce()` has a contract returning `Animal`; returning `Dog` satisfies the contract, because `Dog extends Animal`.

Using it through the interface:

```java
Producer<Animal> producer = new AnimalProducer();
Animal item = producer.produce();
```

Key point: `AnimalProducer implements Producer<Animal>` does **not** make it a `Producer<Dog>`:

```java
// Producer<Dog> dogs = new AnimalProducer(); // Invalid.
```

An instance may produce a `Dog`, yet the interface's type argument remains `Animal`; generic assignment obeys invariance.

### When an Interface Fixes the Result Type Directly

```java
interface StringProvider {
    CharSequence text();
}

class FixedStringProvider implements StringProvider {
    @Override
    public String text() {
        return "Hello";
    }
}
```

`String implements CharSequence`, so `String` is a valid covariant return type. This pattern appears in SDK interfaces, builders, and adapters when an implementation provides an object with a more specific API.

## 9. Type Erasure and Bridge Methods: Why Does Polymorphism Still Work?

Java generics are implemented primarily via **type erasure**. When the compiler compiles `class Source<T extends Animal>`, `T` is typically replaced with the bound `Animal` in the corresponding bytecode signature. The subclass `Source<Dog>` has an overriding method returning type `Dog`.

Conceptual example:

```java
class Source<T extends Animal> {
    public T read() {
        return null;
    }
}

class DogSource extends Source<Dog> {
    @Override
    public Dog read() {
        return new Dog();
    }
}
```

After erasure, the JVM sees method descriptors with different return types. To ensure calls through `Source<Dog>` still reach `DogSource.read()`'s implementation, the compiler may generate a synthetic **bridge method** that forwards the erased-signature call to the specialized method.

This is a key mechanism for preserving **polymorphism** when generic method signatures and covariant returns meet. Bridge methods:

- Are generated by the compiler when needed; they are not methods you write in source code.
- Typically carry `synthetic` and `bridge` flags in bytecode.
- Can be observed via reflection using `Method.isBridge()` or `javap -c -p`.
- Do not mean the runtime maintains a separate specialized class for `Source<Dog>`.
- Are not a reason to omit `@Override`, use raw types, or cast manually.

In the complete example in section 12, `DogSource` overrides both `read()` and `copy()`. With the Java compiler tested, reflection counts **2 bridge methods** due to the more specific signatures. If you modify the design or compiler version, you should not rely on the bridge method count as a business-logic contract.

### Should You Write Bridge Methods Manually?

No. Source code only needs to write the proper override and let the compiler handle runtime compatibility. Manually writing two methods differing only in return type is **also invalid**, because Java does not allow overloading by return type alone.

## 10. Primitive Results, `void`, Checked Exceptions, and `static`

The `Dog`/`Animal` examples all involve **reference types**. For primitives and `void`, covariance does not apply as in class inheritance:

```java
class BaseCount {
    int size() { return 1; }
}

class ChildCount extends BaseCount {
    // @Override long size() { return 1L; } // Invalid: long cannot replace int.
    @Override int size() { return 2; } // Valid.
}
```

`int` and `long` have widening numeric conversions in expression assignments, yet **do not form a subtype relationship** to change return types when overriding. Likewise, a method returning `void` must be overridden with a method returning `void`.

### Checked Exceptions

```java
import java.io.IOException;
import java.io.FileNotFoundException;

class ParentLoader {
    Animal load() throws IOException { return new Animal(); }
}

class ChildLoader extends ParentLoader {
    @Override
    Dog load() throws FileNotFoundException { return new Dog(); }
}
```

`FileNotFoundException` is a subtype of `IOException`, so the subclass narrows both the checked exception and the return type — both are valid. Conversely, adding `throws Exception` when the superclass only allows `IOException` is invalid.

### `static` and `final` Rules

`static` methods do not participate in dynamic dispatch like instance overrides; using the same name/signature in a subclass is **hiding**. Do not put `@Override` on a `static` method:

```java
class BaseFactory {
    static Animal create() { return new Animal(); }
}

class ChildFactory extends BaseFactory {
    // Hiding a static method, not polymorphic overriding.
    static Dog create() { return new Dog(); }
}
```

Compatibility rules when hiding still apply; do not use hiding as a substitute for overriding to represent object state.

`final` methods cannot be overridden and thus cannot provide covariant return types via overriding; `private` methods are not inherited as overridable methods. Constructors never have a return type and are not subject to covariance rules.

## 11. Self-Returning Subtype APIs: Factories, Copies, and Builders

A common application of covariant returns is when a subclass wants fluent or clone/copy operations to return **the specialized object type itself**:

```java
class BuilderBase {
    public BuilderBase configure() {
        return this;
    }
}

class DogBuilder extends BuilderBase {
    @Override
    public DogBuilder configure() {
        return this;
    }

    Dog build() {
        return new Dog();
    }
}
```

Callers of `DogBuilder` invoking `configure()` receive `DogBuilder` and can chain `build()` without casting:

```java
DogBuilder builder = new DogBuilder();
Dog dog = builder.configure().build();
```

However, when an API requires returning **each final subtype across multiple levels**, a covariant return override at one level does not automatically "morph" for new subclasses. You must override at deeper subclasses or consider the self-bounded generics pattern (*CRTP-like pattern*):

```java
abstract class Fluent<S extends Fluent<S>> {
    protected abstract S self();

    public S configure() {
        return self();
    }
}

final class Specialized extends Fluent<Specialized> {
    @Override
    protected Specialized self() {
        return this;
    }

    Specialized finish() {
        return this;
    }
}
```

This pattern preserves the return type across the API using a generic parameter; it differs from merely overriding a single method returning `Base` to return `Child`. Use it when a hierarchy has multiple builder/fluent classes that genuinely need type safety, without forcing extra complexity onto small APIs.

## 12. Standalone, Tested Java 17+ Program

Create a file named **`CovariantReturnDemo.java`**. The program below demonstrates covariant return types simultaneously on an ordinary method, a bounded generic superclass, an interface, a collection wildcard, and bridge methods.

```java
import java.util.List;
import java.util.Arrays;
import java.lang.reflect.Method;

public class CovariantReturnDemo {
    static class Animal {
        private final String name;
        Animal(String name) { this.name = name; }
        String name() { return name; }
    }

    static final class Dog extends Animal {
        Dog(String name) { super(name); }
        String bark() { return "gâu"; }
    }

    static class Source<T extends Animal> {
        private final T value;
        Source(T value) { this.value = value; }
        public T read() { return value; }
        public Source<T> copy() { return new Source<>(value); }
    }

    static final class DogSource extends Source<Dog> {
        DogSource(Dog value) { super(value); }
        @Override public Dog read() { return super.read(); }
        @Override public DogSource copy() { return new DogSource(read()); }
    }

    interface Provider<T> {
        T get();
    }

    static final class AnimalProvider implements Provider<Animal> {
        @Override public Dog get() { return new Dog("Nâu"); }
    }

    static class AnimalCatalog {
        public List<? extends Animal> animals() {
            return List.of(new Animal("Chung"));
        }
    }

    static final class DogCatalog extends AnimalCatalog {
        @Override public List<Dog> animals() {
            return List.of(new Dog("Mực"), new Dog("Vàng"));
        }
    }

    public static void main(String[] args) {
        DogSource child = new DogSource(new Dog("Bim"));
        Source<Dog> parent = child;
        System.out.println("parent: " + parent.read().name());
        System.out.println("child: " + child.read().bark());
        System.out.println("copy: " + child.copy().read().name());

        Provider<Animal> provider = new AnimalProvider();
        System.out.println("provider: " + provider.get().name());

        AnimalCatalog catalog = new DogCatalog();
        System.out.println("catalog: " +
                catalog.animals().stream().map(Animal::name).toList());

        long bridges = Arrays.stream(DogSource.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .count();
        System.out.println("bridges: " + bridges);
    }
}
```

Compile and run (JDK 17 or newer):

```bash
javac --release 17 -Xlint:all CovariantReturnDemo.java
java CovariantReturnDemo
```

**Exact stdout** of the version above (compiled with `--release 17 -Xlint:all` and executed successfully):

```text
parent: Bim
child: gâu
copy: Bim
provider: Nâu
catalog: [Mực, Vàng]
bridges: 2
```

Line-by-line explanation:

1. `Source<Dog> parent = child` is valid because `DogSource extends Source<Dog>`. The static type of `parent.read()` is `Dog` per `T = Dog`; the runtime implementation is `DogSource.read()`.
2. `child.read().bark()` is valid because the subclass overrides to return `Dog`, allowing use of `Dog`'s own API.
3. `child.copy()` returns `DogSource` — a subtype of `Source<Dog>` — thanks to covariant return, so chaining `read()` continues with the right type.
4. `Provider<Animal> provider` uses `AnimalProvider.get()`'s implementation returning `Dog`. This is valid because `Dog` is an `Animal`; it does **not** give variable `provider` the type `Provider<Dog>`.
5. `AnimalCatalog.animals()` returns `List<? extends Animal>`, allowing `DogCatalog.animals()` to override with `List<Dog>`. The list of names preserves the order from `List.of(...)`.
6. Reflection counts compiler-generated bridge methods in `DogSource` for `read()` and `copy()`. This part is only to verify the compilation mechanism, not a condition that application logic should depend on.

**Determinism note:** `Dog.name()` comes from class `Animal`, and the string `gâu` is written explicitly; the order of `List.of(...)` matches the input. The code does not depend on time zones, networking, file I/O, or random data. On a standard compiler installation compatible with this example, the bridge method count accurately reflects the specialized overrides; if signatures change, the count may change.

## 13. Common Mistakes

| Symptom / code snippet | Cause | Proper fix |
| --- | --- | --- |
| `Animal get()` in parent, `Object get()` in child | Broadening return type instead of returning a subtype; fails contract | Keep `Animal` or return a subtype such as `Dog`. |
| `int count()` in parent, `long count()` in child | Primitives are not covariant along class inheritance | Keep `int` in the override. |
| `List<Animal> findAll()` in parent, `List<Dog> findAll()` in child | Generic type arguments are invariant | Change parent contract to `List<? extends Animal>` if read-only, or parameterize parent as `Service<T>`. |
| Overriding `handle(Animal)` with `handle(Dog)` | Changing parameter creates an overload instead of an override | Keep the parameter list; narrow only a valid result type. |
| Adding `throws Exception` when parent only declares `IOException` | Checked exception is broader than contract | Keep or narrow checked exceptions. |
| Narrowing `public` to `protected` or `private` | Overrides cannot reduce accessibility | Keep `public` or widen access where valid. |
| Putting `@Override` on a `static` method | Static methods are hidden, not dynamically overridden | Design an instance method if polymorphism is needed. |
| Overriding a `final` method | `final` forbids overriding | Revise design, use composition, or use another extension method. |
| Calling `new Parent<Dog>` and casting to `Parent<Animal>` | Invariance; casting does not make the contract safe | Use `Parent<? extends Animal>` for reading, or an appropriate generic API. |
| Forgetting `@Override` | Typos/signature errors easily become unintended overloads | Add `@Override` on every genuine override. |
| Manually casting `(Dog) super.get()` without invariant control | Can cause `ClassCastException` | Fix type argument in parent or enforce invariant, avoiding groundless casts. |
| Trying to overload two methods differing only in return type | Java does not resolve overloads by return type alone | Use different names or meaningful different parameters. |
| Manually writing bridge methods thinking erasure breaks polymorphism | The compiler already generates bridges when needed | Write type-safe overrides and let the compiler handle bytecode. |
| Using raw `List`/`Source` to silence generic errors | Strips type checking; may emit unchecked warnings | Fix the real type relationships instead of hiding warnings. |

### How to Read Compiler Errors When Overriding

When the compiler reports an "incompatible" return type, answer in order:

1. What is the **exact parent method signature after substituting type arguments**? Is `T` fixed to `Dog`, `Animal`, or `List<Animal>`?
2. Does the child method genuinely override (same name/valid parameter list), or only overload?
3. Is the child's result type an appropriate subtype of the parent's result type **after generic substitution**?
4. If the result is a generic type, does a subtype relationship actually exist, or are you mistakenly inferring `List<Dog> extends List<Animal>` from `Dog extends Animal`?
5. Do access levels, checked exceptions, `static`, or `final` block overriding?
6. Are raw types or unchecked conversions from legacy code obscuring the signature you see?

This checklist is more effective than trying to add casts and silence warnings one by one.

## 14. Practice Exercises

**Exercise 1 — Basic override.** Create `class Vehicle` and `class Bike extends Vehicle`. Write `VehicleFactory.create(): Vehicle` and `BikeFactory.create(): Bike`. Call through a `VehicleFactory` variable pointing to `BikeFactory`, noting the difference between the static type of the result and the runtime class.

**Exercise 2 — Generic superclass with a fixed type.** Write `class Box<T>` with `T get()`. Create `class BikeBox extends Box<Bike>` and override `get()` if you want to add behavior. Show why `Box<Bike> ref = new BikeBox(...)` is valid and `Box<Vehicle> ref = new BikeBox(...)` is invalid.

**Exercise 3 — Covariant factory result.** Write `class CopySource<T>` with `CopySource<T> duplicate()`. Create `class StringSource extends CopySource<String>` with an override returning `StringSource`. Explain why the subclass return type does not break the parent contract.

**Exercise 4 — Collections and wildcards.** Given `List<Vehicle> vehicles()` in the parent. Try overriding with `List<Bike> vehicles()` and observe the error. Change the parent result type to `List<? extends Vehicle>` and verify the override becomes valid. Try `list.add(new Vehicle())` on a `List<? extends Vehicle>` variable and explain why the compiler rejects it.

**Exercise 5 — Generic interface.** Define `Provider<T>` with `T get()`. Create `Provider<Vehicle>` using an implementation returning `Bike`. Why does `Provider<Bike> p = ...` not follow validly just from the implementation returning `Bike`?

**Exercise 6 — Bytecode bridges.** Compile the `Source<T extends Animal>`/`DogSource` example, and run `javap -c -p` on the subclass (with the corresponding nested class name). Locate the compiler-generated `bridge` methods; explain why calls through a parent reference still reach the child override.

**Exercise 7 — Exception contract.** A superclass declares `Animal read() throws IOException`. Write an overriding subclass method returning `Dog`, optionally declaring `throws FileNotFoundException`. Try replacing `IOException` with `Exception` in the override and explain the error.

**Exercise 8 — Reading signatures.** Suppose `class AnimalRepo<T extends Animal> { List<T> all(); }`. Create `class DogRepo extends AnimalRepo<Dog>`. What is the result type of `all()`? Is `@Override` needed simply to inherit it? Why is trying to override it to return `List<Animal>` invalid?

## 15. Quick Summary

- **Covariant returns** allow overriding an instance method with a return type that is a valid subtype of the return type required by the parent contract.
- In generic inheritance, you must **substitute the superclass's type parameters** before determining the result type in the subclass, e.g., `Parent<T>` with `extends Parent<Dog>`.
- `Dog extends Animal` **does not imply** `List<Dog> extends List<Animal>`. Invariance of generic types and covariance of return types are two distinct concepts.
- `List<Dog>` can substitute for `List<? extends Animal>` when the contract only needs to read values as `Animal`.
- Return types can narrow, whereas **parameters, access levels, checked exceptions, and `static`/`final`** must still obey override rules.
- **Bridge methods** are compiler details that combine erasure with polymorphism; you do not need to implement them yourself.
- Choose the API contract first, use `@Override` and exact generic types, and verify at compile time; do not use raw types or unchecked casts to mask invalid type relationships.

When reading an override in a generic class, ask yourself one final question: **"If a caller only knows about the superclass, will the result returned by the subclass always satisfy that contract?"** If the answer can be proven by the compiler through proper subtyping and generics, covariant returns are a powerful tool for specializing APIs while preserving substitutability.