# Single Class Inheritance and the Implicit Relationship with `Object` in Java

## 1. Core Idea: One Direct Superclass, One Root `Object`

Java uses **single class inheritance**: an ordinary class can have only **one direct superclass**. If a class does not write an `extends` clause, its direct superclass **is implicitly `java.lang.Object`**, except for special declaration kinds with their own rules such as `Object`, `enum`, and `record`.

Example:

```java
class Person {
}

class Student extends Person {
}

class GraduateStudent extends Student {
}
```

Class relationships:

```text
java.lang.Object
       |
       v
     Person
       |
       v
     Student
       |
       v
 GraduateStudent
```

- `Person` does not write `extends`, so it inherits directly from `Object`.
- `Student` declares `extends Person`, so its direct superclass is `Person`.
- `GraduateStudent` declares `extends Student`, so its direct superclass is `Student`.
- Both `Student` and `GraduateStudent` are also **indirect** subtypes of `Object`.
- Each class has only one **direct superclass**, but it can have **multiple ancestor classes** along the same chain.
- A class can **implement multiple interfaces**. That does not break the single class inheritance rule.

> **Distinguish between these two statements:** "Each class has only one direct superclass" is true for Java's class inheritance relationship. "An object has only one supertype" is false: an object can have multiple supertypes via its superclass chain and multiple interfaces.

This is the foundation for understanding `extends`, subtype substitutability, constructor chaining, method overriding, dynamic dispatch, and how every object has common capabilities from `Object`.

## 2. What Is `java.lang.Object`?

`java.lang.Object` is the **root class** of the Java class hierarchy. Most objects created from classes (including user-defined classes, library classes, array objects, enum instances, and record instances) have `Object` in their respective supertype hierarchy.

`Object` provides common methods such as:

- `equals(Object)` — equality comparison contract.
- `hashCode()` — hash code, related to the `equals` contract.
- `toString()` — string representation of the object.
- `getClass()` — returns the runtime `Class` object of the receiver.
- `wait(...)`, `notify()`, `notifyAll()` — the object's monitor mechanism.
- `clone()` — a protected method with its own cloning rules.
- `finalize()` — a legacy API that has been deprecated and should not be used for lifecycle design; in modern versions it has been marked for removal.

These methods do not all have the same access modifier or the same ability to be overridden. For example, `toString` and `equals` can be validly overridden; `getClass` is final, so it cannot be overridden.

`java.lang` is imported automatically according to Java rules. Therefore, in ordinary source code, you can write `Object` instead of `java.lang.Object` without having to declare `import java.lang.Object;`.

**Note:** Root class does not mean every variable in Java has the Object type. `int`, `boolean`, and other primitive types **are not classes and do not inherit from Object**.

## 3. Writing `extends Object` or Omitting `extends` Are Both Valid

The two class declarations below have the same meaning regarding the **direct superclass**:

```java
class Book {
}
```

```java
class Book extends Object {
}
```

These are **two alternative declarations with the same name `Book`**, not placed side by side in the same source file/package.

For an ordinary class with no specified superclass, Java treats `Object` as its direct superclass. Writing `extends Object` explicitly is **valid** but usually **redundant**, because it does not make the class inherit any additional capabilities compared to the default.

### Java 17+ Program to Inspect the Superclass Using Reflection

Create the file **`ImplicitObjectDemo.java`**:

```java
class Plain {
}

class Explicit extends Object {
}

public class ImplicitObjectDemo {
    public static void main(String[] args) {
        System.out.println(Plain.class.getSuperclass().getSimpleName());
        System.out.println(Explicit.class.getSuperclass().getSimpleName());

        Plain plain = new Plain();
        System.out.println(plain instanceof Object);
        System.out.println(plain.getClass().getSimpleName());
    }
}
```

Compile and run:

```bash
javac ImplicitObjectDemo.java
java ImplicitObjectDemo
```

**Standard output:**

```text
Object
Object
true
Plain
```

Explanation:

1. `Plain.class.getSuperclass()` returns `Object.class` because Plain has an implicit superclass.
2. `Explicit.class.getSuperclass()` also returns `Object.class`.
3. `plain instanceof Object` is true because an instance of Plain is a Java object and Plain inherits from Object.
4. `plain.getClass()` returns the actual runtime class of the receiver, which here is Plain.

The example uses `Class.getSuperclass()` to **observe the class model**; it does not claim that the JVM must represent every inheritance relationship as a memory diagram like the one above.

## 4. Why Does `Object` Not `extends` Any Class?

`Object` is the stopping point of the superclass chain. If `Object` also had another superclass, it would no longer be the root class.

With `Class.getSuperclass()`:

- On an ordinary class, it returns the `Class` object of its direct superclass.
- On `Object.class`, it returns `null` because Object has no superclass.
- On an interface, primitive type, or `void`, `getSuperclass()` also returns `null` according to this API; those null values **do not mean they are all root classes like Object**.

### Runnable Example

File **`ObjectRootDemo.java`**:

```java
public class ObjectRootDemo {
    public static void main(String[] args) {
        System.out.println(Object.class.getSuperclass() == null);
        System.out.println(Runnable.class.getSuperclass() == null);
        System.out.println(int.class.getSuperclass() == null);
        System.out.println(String.class.getSuperclass().getSimpleName());
    }
}
```

```bash
javac ObjectRootDemo.java
java ObjectRootDemo
```

```text
true
true
true
Object
```

The first three `true` values have **different reasons**:

- `Object` is the root class, so it has no superclass.
- `Runnable` is an interface, not a class with a superclass chain like an ordinary class.
- `int` is a primitive type, with no superclass.

`String` is a final class that inherits directly from Object, so the result on the last line is `Object`.

## 5. Rule: A Class Cannot `extends` Two Classes at the Same Time

Java does not allow:

```java
// Invalid Java syntax:
// class Student extends Person, Account {
// }
```

There is no such thing as "two direct superclasses" for a class declaration. This is a **compile-time error**, not a case where the JVM arbitrarily chooses a superclass.

A clear way to express this:

```java
class Person {
}

class Student extends Person {
}
```

`Student` only has `Person` as its direct superclass. If Student needs an account, an address, or study tools, a **has-a/composition relationship** is typically used rather than trying to put them into the `extends` list.

```java
class Student extends Person {
    private final StudyNotebook notebook = new StudyNotebook();
}

class StudyNotebook {
}
```

In this example, `Student` inherits from `Person` and **has a `StudyNotebook` component**. This is a valid declaration; it does not have two superclasses.

**Design note:** It is not the lack of multiple class inheritance that forces every relationship to use composition. Inheritance is still appropriate when a subclass is genuinely a kind of the superclass according to its contract. Composition is appropriate when an object **has/uses** another component.

## 6. Single Class Inheritance Does Not Prohibit Multiple Interfaces

A class can inherit from **one class** and implement **multiple interfaces**:

```java
class Person {
}

interface Named {
    String name();
}

interface Identified {
    int id();
}

class Student extends Person implements Named, Identified {
    private final String name;
    private final int id;

    Student(String name, int id) {
        this.name = name;
        this.id = id;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public int id() {
        return id;
    }
}
```

Here:

- `Person` is **one** direct superclass of Student.
- `Named` and `Identified` are **two direct superinterfaces**.
- Student can be used through the types `Student`, `Person`, `Named`, `Identified`, and `Object` when appropriate.
- Implementing multiple interfaces does not turn Java into a multiple **class** inheritance language.

### Standalone Runnable Example with Multiple Supertypes

File **`MultipleInterfacesDemo.java`**:

```java
interface Named {
    String name();
}

interface Identified {
    int id();
}

class Person {
}

class Student extends Person implements Named, Identified {
    @Override
    public String name() {
        return "An";
    }

    @Override
    public int id() {
        return 7;
    }
}

public class MultipleInterfacesDemo {
    public static void main(String[] args) {
        Student student = new Student();

        Named named = student;
        Identified identified = student;
        Person person = student;
        Object object = student;

        System.out.println(named.name());
        System.out.println(identified.id());
        System.out.println(person instanceof Student);
        System.out.println(object instanceof Named);
    }
}
```

```bash
javac MultipleInterfacesDemo.java
java MultipleInterfacesDemo
```

```text
An
7
true
true
```

The variables above hold **the same Student object**; they differ only in **the reference type when the compiler checks calls**. No separate Person object and two interface objects are created at all.

## 7. An Interface Can `extends` Multiple Interfaces

For an interface, the `extends` syntax can list **multiple superinterfaces**:

```java
interface Readable {
    String read();
}

interface Writable {
    void write(String text);
}

interface ReadWrite extends Readable, Writable {
}
```

This is **multiple interface inheritance**; it does not violate the single **class** inheritance rule. A class implementing `ReadWrite` needs to implement the required abstract instance methods according to the contract (unless the class itself is abstract or inherits an appropriate implementation).

Because interfaces can have `default` methods, Java also has conflict resolution rules; when two defaults with the same signature are not resolved automatically, the implementer may have to override them. Those rules do not turn implementing two interfaces into having two superclass classes.

### An Interface Does Not `extends Object`

A subtle point: an interface like `Readable` **does not write and does not implicitly inherit from `Object` through the same superclass mechanism as a class**.

Even so, the actual object implementing the interface is still an `Object` instance, and Java allows many calls to public methods from Object through an interface-typed reference according to interface method member/lookup rules.

Example:

```java
Readable readable = new Document();
System.out.println(readable.toString());
```

This snippet is an **illustrative fragment** assuming `Document implements Readable`. `readable.toString()` can compile because the corresponding public Object method can be called; you must not infer from this that `Readable extends Object` is a valid Java statement.

## 8. An Object Is a Subtype of Every Ancestor Class Along the Same Chain

If:

```java
class Animal {
}

class Mammal extends Animal {
}

class Dog extends Mammal {
}
```

a `Dog` is:

- A `Dog`.
- A `Mammal` by the class inheritance relationship.
- An `Animal`.
- An `Object`.

This relationship allows **upcasting**:

```java
Dog dog = new Dog();
Mammal mammal = dog;
Animal animal = dog;
Object object = dog;
```

The four references can point to the same Dog object. There is no conversion that "slices off the Dog part" as some people associate with other languages. The runtime value remains the same object.

### Runnable Example Checking `instanceof`

File **`SubtypeChainDemo.java`**:

```java
class Animal {
}

class Mammal extends Animal {
}

class Dog extends Mammal {
}

public class SubtypeChainDemo {
    public static void main(String[] args) {
        Dog dog = new Dog();

        Animal animal = dog;
        Object root = animal;

        System.out.println(dog instanceof Mammal);
        System.out.println(dog instanceof Animal);
        System.out.println(animal instanceof Dog);
        System.out.println(root instanceof Object);
        System.out.println(root.getClass().getSimpleName());
    }
}
```

```bash
javac SubtypeChainDemo.java
java SubtypeChainDemo
```

```text
true
true
true
true
Dog
```

`getClass()` reflects **the runtime class Dog**; it does not return Animal or Object just because the reference has been assigned to a supertype.

## 9. Upcasting Does Not Lose Runtime Identity, but Limits Visible Methods at Compile Time

A variable of type `Object` only lets the compiler know the methods available through the Object type (and the characteristics of the expression according to language rules). Therefore:

```java
Object object = new Dog();

// object.bark(); // Invalid if bark belongs only to Dog.
```

**It is not that the Dog object has lost `bark()`**. The issue is that **the static type of the `object` variable** does not declare that method.

You can check and downcast when you are sure the object has an appropriate runtime type:

```java
if (object instanceof Dog dog) {
    dog.bark();
}
```

Java 17 supports **pattern matching for `instanceof`** as shown above. Checking the runtime type before using subtype-specific behavior helps reduce the risk of `ClassCastException`.

### Runnable Program

File **`UpcastAndPatternDemo.java`**:

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }

    String breed() {
        return "shepherd";
    }
}

public class UpcastAndPatternDemo {
    public static void main(String[] args) {
        Object value = new Dog();

        System.out.println(value.getClass().getSimpleName());

        if (value instanceof Dog dog) {
            System.out.println(dog.breed());
            System.out.println(dog.sound());
        }

        Animal animal = (Animal) value;
        System.out.println(animal.sound());
    }
}
```

```bash
javac UpcastAndPatternDemo.java
java UpcastAndPatternDemo
```

```text
Dog
shepherd
woof
woof
```

- `getClass` reads the runtime type.
- `instanceof Dog dog` checks and creates a pattern variable of type Dog when the condition is true.
- `Dog.breed` is only visible when the reference is of type Dog.
- `animal.sound()` is an instance call; it dynamically dispatches to Dog's override even though the static type of `animal` is Animal.

## 10. Inheriting `Object` Methods and Dynamic Dispatch

Because `Object` is a superclass, ordinary classes can use public instance methods inherited from Object according to the access/override rules.

For example, `toString()` can be overridden in a subclass:

```java
class Device {
    @Override
    public String toString() {
        return "Device";
    }
}

class Phone extends Device {
    @Override
    public String toString() {
        return "Phone";
    }
}
```

An `Object` reference to Phone still calls the `Phone.toString()` implementation, because `toString` is an overridable instance method.

### Runnable Example of Dynamic Dispatch from `Object`

File **`ObjectDispatchDemo.java`**:

```java
class Device {
    @Override
    public String toString() {
        return "Device";
    }
}

class Phone extends Device {
    @Override
    public String toString() {
        return "Phone";
    }
}

public class ObjectDispatchDemo {
    public static void main(String[] args) {
        Object a = new Device();
        Object b = new Phone();

        System.out.println(a.toString());
        System.out.println(b.toString());
        System.out.println(b.getClass().getSimpleName());
    }
}
```

```bash
javac ObjectDispatchDemo.java
java ObjectDispatchDemo
```

```text
Device
Phone
Phone
```

`toString()` is selected according to the runtime receiver when overridden. `getClass()` is a final method from Object and is not overridden; it returns the actual runtime Class object of Phone.

**Do not confuse this:** just because a method is originally declared in Object does not mean every subclass must use the default implementation.

## 11. The Constructor Chain Also Reaches `Object`

The implicit relationship with `Object` does not affect only methods. When creating an object of an ordinary class, the constructor chain also goes through the superclass constructors and reaches the `Object` constructor according to the rules.

File **`ConstructorChainToObjectDemo.java`**:

```java
class Base {
    Base() {
        System.out.println("Base()");
    }
}

class Derived extends Base {
    Derived() {
        System.out.println("Derived()");
    }
}

public class ConstructorChainToObjectDemo {
    public static void main(String[] args) {
        Derived derived = new Derived();

        System.out.println(derived instanceof Object);
    }
}
```

```bash
javac ConstructorChainToObjectDemo.java
java ConstructorChainToObjectDemo
```

```text
Base()
Derived()
true
```

Logical sequence:

1. `new Derived()` requests the creation of a Derived instance.
2. `Derived()` has an implicit `super()` call to `Base()` if no explicit constructor invocation is written.
3. `Base()` has an implicit `Object` superclass; the `Object()` constructor is called in the chain.
4. `Object()` prints nothing in this example; then `Base()` prints `Base()`.
5. Returning to `Derived()`, it prints `Derived()`.
6. `derived instanceof Object` is true.

**Note:** `Object` has an accessible no-argument constructor for normal inheritance chains, but this should not be understood to mean that each object carries a separate "Object object" created and assigned via a field. **The same object** is being initialized through the constructor chain.

### `super()` Is Not an Inherited `Object` Method

`super()` is an **explicit constructor invocation**, not a call to an instance method. Constructors are not "inherited" like `toString()`; a subclass needs to define its own constructors if it wants those signatures.

## 12. Superclass with a Parameterized Constructor: A Valid `super()` Does Not Appear Automatically

If the superclass does not have an accessible no-arg constructor, the subclass must choose an appropriate superclass constructor.

Snippet that does not compile:

```java
// class Parent {
//     Parent(int id) { }
// }
//
// class Child extends Parent {
//     Child() { } // Implicitly calls super(), but Parent has no no-arg constructor.
// }
```

Fix:

File **`ExplicitSuperConstructorDemo.java`**:

```java
class Parent {
    private final int id;

    Parent(int id) {
        this.id = id;
        System.out.println("Parent id=" + id);
    }

    int id() {
        return id;
    }
}

class Child extends Parent {
    Child(int id) {
        super(id);
        System.out.println("Child created");
    }
}

public class ExplicitSuperConstructorDemo {
    public static void main(String[] args) {
        Child child = new Child(12);

        System.out.println(child.id());
    }
}
```

```bash
javac ExplicitSuperConstructorDemo.java
java ExplicitSuperConstructorDemo
```

```text
Parent id=12
Child created
12
```

A class can have only one **direct superclass**, yet the superclass chain can still be long. The constructor invocation from Child to Parent, and from Parent to Object (implicitly), follows the required order.

## 13. The Most Important Public Methods of `Object`

| Method | General Meaning | Can It Be Overridden? |
| --- | --- | --- |
| `equals(Object other)` | Compares equality according to contract | **Yes**, must respect the equality contract |
| `hashCode()` | Hash code, compatible with `equals` | **Yes**, consistent with equals |
| `toString()` | String representation of the object | **Yes** |
| `getClass()` | Returns the runtime Class object | **No**, `final` |
| `wait()` / `wait(long)` / `wait(long,int)` | Waits on the receiver's monitor according to conditions | **No**, `final` |
| `notify()` | Wakes up one thread waiting on that monitor according to the rules | **No**, `final` |
| `notifyAll()` | Wakes up the threads waiting on that monitor according to the rules | **No**, `final` |

Some other methods of Object have different access/characteristics:

- `clone()` is `protected`; cloning semantics involve `Cloneable` and separate rules, and **it does not automatically become public on every object**.
- `finalize()` also exists in Java's historical API but is deprecated for removal in Java 17; you should not write resource logic that depends on when finalize runs.
- `Object()` is a **constructor**, not an inherited instance method.

**You should not** describe the methods from Object as an "interface" that subclasses are required to implement. They have implementations in Object (except for the specified override and access rules) and can be used directly when appropriate.

## 14. Default `toString()` Can Be Hard to Read; Override When Needed

If a class does not override `toString()`, Object's implementation typically produces a format based on the class name, the `@` character, and the hexadecimal representation of the hash code. The actual value of the hash code **cannot be predicted as a fixed value** and **must not be assumed to be the object's memory address**.

To make log output easy to understand and tests stable, many classes override it themselves:

File **`ObjectToStringDemo.java`**:

```java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return "Book[title=" + title + "]";
    }
}

public class ObjectToStringDemo {
    public static void main(String[] args) {
        Book book = new Book("Java Core");

        Object asObject = book;

        System.out.println(book);
        System.out.println(asObject.toString());
    }
}
```

```bash
javac ObjectToStringDemo.java
java ObjectToStringDemo
```

```text
Book[title=Java Core]
Book[title=Java Core]
```

`System.out.println(book)` uses the object's string representation; overriding it makes the output meaningful and independent of the default hash code.

Not every class is required to override `toString`, but if you want to log/debug a value-like object, this approach is often helpful.

## 15. Default `equals(Object)`: Comparing the Same Object

The `equals` implementation inherited from `Object` considers two references equal only when they represent **the same object** according to identity equality (equivalent to `==` in that case).

File **`ObjectEqualsIdentityDemo.java`**:

```java
class Token {
    private final String code;

    Token(String code) {
        this.code = code;
    }
}

public class ObjectEqualsIdentityDemo {
    public static void main(String[] args) {
        Token first = new Token("A");
        Token second = new Token("A");
        Token alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(alias));
    }
}
```

```bash
javac ObjectEqualsIdentityDemo.java
java ObjectEqualsIdentityDemo
```

```text
false
false
true
```

The two Token objects have the same `code="A"` but are two different instances, so by default `equals` does not treat them as equal. If the domain wants to compare values by code, the class needs to override `equals`/`hashCode` consistently, or use a type with value semantics such as a record when appropriate.

### Do Not Confuse `==` with `equals`

- `a == b`, when both are references, checks whether they have the same reference value.
- `a.equals(b)` is an instance method call and may have a different implementation in the runtime class.
- If `a` is null, `a.equals(b)` causes a `NullPointerException`; you can use `Objects.equals(a,b)` when null-safe equality is needed.
- `String.equals` compares contents according to String's contract; **it does not use Object's default identity equality**.

## 16. Overriding `equals` Must Be Consistent with `hashCode`

Important contract: if `a.equals(b)` is true, `a.hashCode()` and `b.hashCode()` must return equal results as required. Conversely, two objects having the same hash code **are not necessarily equal**.

Example of an immutable value-like class:

File **`ObjectEqualsHashDemo.java`**:

```java
import java.util.Objects;

final class ProductId {
    private final String value;

    ProductId(String value) {
        this.value = Objects.requireNonNull(value);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof ProductId id)) {
            return false;
        }
        return value.equals(id.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return "ProductId[" + value + "]";
    }
}

public class ObjectEqualsHashDemo {
    public static void main(String[] args) {
        ProductId first = new ProductId("P1");
        ProductId second = new ProductId("P1");

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first);
    }
}
```

```bash
javac ObjectEqualsHashDemo.java
java ObjectEqualsHashDemo
```

```text
false
true
true
ProductId[P1]
```

Key points:

1. The overriding method has the signature `public boolean equals(Object other)`, not just `equals(ProductId)`.
2. Pattern matching `instanceof ProductId id` can be used on Java 17.
3. The two ProductId objects differ in identity but are equal in `value` according to the class contract.
4. `hashCode` is consistent with `equals` by being based on the same field.
5. A `final` class avoids certain equality complexities when subclasses add state.

**Do not infer that** `hashCode()` is the physical address or must be unique for every object; two different values can share the same hash code.

## 17. Which Object Methods Cannot Be Overridden?

Some Object methods are `final`, for example:

```java
final Class<?> getClass()
final void notify()
final void notifyAll()
final void wait() throws InterruptedException
```

The snippet above is a **shortened signature list for readability**; `wait` also has overloads. This is not valid class source code to place verbatim into your file.

Because they are `final`:

- A subclass cannot override `getClass()` to "fake" its runtime class.
- A subclass cannot override the final `wait`/`notify`/`notifyAll` versions of Object.
- You can still **call** public final methods when the API conditions are met.

In particular, the `wait`/`notify` methods are used with **the monitor of the receiver object itself**; if called when the thread does not hold the monitor under the proper conditions, an `IllegalMonitorStateException` can be thrown.

This thread synchronization mechanism is **not** the inheritance constructor chain, nor is it related to creating multiple superclasses. In modern concurrent code, utilities in `java.util.concurrent` often express intent more clearly when appropriate.

## 18. An `Object` Reference Can Hold Instances from Many Different Classes

Because Object is a supertype of class instances, a variable of type Object can successively hold references to different objects:

```java
Object item = "Java";
item = Integer.valueOf(42);
item = new StringBuilder("text");
```

On each assignment, **the variable** `item` changes its reference value; the actual object is not type-converted or altered in code.

### Runnable Program with Various Kinds of Values

File **`ObjectReferenceDemo.java`**:

```java
public class ObjectReferenceDemo {
    public static void main(String[] args) {
        Object text = "Java";
        Object number = Integer.valueOf(42);
        Object array = new int[] {1, 2};

        System.out.println(text.getClass().getSimpleName());
        System.out.println(number.getClass().getSimpleName());
        System.out.println(array instanceof Object);
        System.out.println(array.getClass().isArray());
    }
}
```

```bash
javac ObjectReferenceDemo.java
java ObjectReferenceDemo
```

```text
String
Integer
true
true
```

`int[]` is **an array object**, so a reference to it can be held in an Object variable. However, the individual `int` elements inside are still primitive values, not `Integer` objects.

## 19. Primitive `int` Does Not `extends Object`, Whereas Wrapper `Integer` Does

A primitive type such as `int` is not a class, has no superclass, and does not directly contain Object methods.

Invalid example:

```java
// int number = 42;
// number.getClass(); // Invalid: int is a primitive and has no instance method.
```

However, when boxing:

```java
Object boxed = 42;
```

Java can **autobox** the `int` value into an `Integer` object and then assign its reference to type Object. This is a **conversion**, not because `int extends Object`.

### Runnable Example

File **`BoxingObjectDemo.java`**:

```java
public class BoxingObjectDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Object boxed = primitive;

        System.out.println(boxed instanceof Integer);
        System.out.println(boxed.getClass().getSimpleName());
        System.out.println(((Integer) boxed).intValue());
    }
}
```

```bash
javac BoxingObjectDemo.java
java BoxingObjectDemo
```

```text
true
Integer
42
```

**Remember:** autoboxing allows using a primitive value in many contexts that require a reference type. It **does not turn the `int` type itself into a subclass of Object**.

## 20. Array Objects Have a Relationship with `Object` but Do Not Declare `extends`

Java arrays are created using the syntax:

```java
int[] numbers = new int[3];
String[] names = new String[2];
```

An array is an **object**. An array object:

- Can be assigned to a variable of type `Object`.
- Has the appropriate methods from Object (such as `getClass`, `toString`).
- Has its own runtime array class created/managed by the JVM.
- Can be considered to implement `Cloneable` and `java.io.Serializable` according to Java array rules.
- Has a special `length` **field**, not an instance method `length()` from Object.

There is no `class int[] extends Object` source code written by the programmer using class declaration syntax.

File **`ArrayObjectRelationDemo.java`**:

```java
public class ArrayObjectRelationDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};
        Object object = numbers;

        System.out.println(object instanceof Object);
        System.out.println(object instanceof Cloneable);
        System.out.println(object instanceof java.io.Serializable);
        System.out.println(numbers.length);
        System.out.println(object.getClass().isArray());
    }
}
```

```bash
javac ArrayObjectRelationDemo.java
java ArrayObjectRelationDemo
```

```text
true
true
true
3
true
```

**Do not confuse** an array object with **the primitive type of its elements**. `int` is primitive, whereas `int[]` is a reference type representing an array object.

### Array Covariance Is Not Multiple Class Inheritance

Reference-type Java arrays have covariant subtype rules under appropriate conditions; for example, `String[]` can be upcast to `Object[]`. However, writing an element of the wrong runtime component type can throw `ArrayStoreException`. This is an array type system rule; it **does not** give a class two direct superclasses.

## 21. A `record` Is a Class, but Its Direct Superclass Is Not Object

Java 17 supports `record`. A record class is a kind of class specialized for value-like data carriers, with **`java.lang.Record`** as its superclass defined by the language. `Record` itself has `Object` as its superclass.

```text
java.lang.Object
        |
        v
java.lang.Record
        |
        v
record Point(int x, int y)
```

Someone writing a record **cannot choose a superclass themselves** with `extends SomeClass`. That does not mean a record has two direct superclasses; there is still only one, specified by Java.

### Java 17 Example

File **`RecordSuperclassDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordSuperclassDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(Point.class.getSuperclass().getSimpleName());
        System.out.println(point instanceof Object);
        System.out.println(point);
    }
}
```

```bash
javac RecordSuperclassDemo.java
java RecordSuperclassDemo
```

```text
Record
true
Point[x=2, y=3]
```

A record also has generated implementations for `equals`, `hashCode`, and `toString` according to the records contract. Those methods relate to Object, but **they do not prove that every ordinary object automatically has value-based equality**.

**Note:** A record containing a mutable component reference such as `StringBuilder` or an array **is not automatically deeply immutable**. The superclass rule and content immutability are two different issues.

## 22. `enum` Is Also a Special Class with Superclass `Enum`

A Java enum has a language-defined superclass: `java.lang.Enum` (usually understood in its generic form `Enum<E>` for an enum type `E`). `Enum` is a class and inherits from `Object`.

```text
java.lang.Object
        |
        v
java.lang.Enum
        |
        v
enum Status { NEW, DONE }
```

You cannot declare:

```java
// enum Status extends SomeClass { NEW, DONE } // Invalid.
```

Enums still have an indirect relationship with Object and can implement interfaces according to enum rules.

### Runnable Example

File **`EnumSuperclassDemo.java`**:

```java
enum Status {
    NEW, DONE
}

public class EnumSuperclassDemo {
    public static void main(String[] args) {
        System.out.println(Status.class.getSuperclass().getSimpleName());

        Object value = Status.NEW;
        System.out.println(value instanceof Enum);
        System.out.println(value instanceof Object);
        System.out.println(value.toString());
    }
}
```

```bash
javac EnumSuperclassDemo.java
java EnumSuperclassDemo
```

```text
Enum
true
true
NEW
```

`Status.NEW` is an enum constant belonging to the runtime enum class Status. It has `Object` in its superclass chain via `Enum`, but it does not have two superclass classes.

**Do not misunderstand:** There can be constant-specific class bodies in an enum and certain runtime class details, but the fundamental way to learn about the direct superclass of an enum declaration is its relationship with `java.lang.Enum`.

## 23. `final` Class: Still Inherits from Object, but Cannot Be Subclassed

A `final class` can **inherit from a superclass**, but it cannot serve as the superclass for a new subclass declared by a client.

```java
final class Receipt {
}
```

`Receipt` does not write `extends`, so it inherits directly from Object. However:

```java
// class SpecialReceipt extends Receipt { } // Error: Receipt is final.
```

`final` does not mean "Receipt inherits from nothing"; it only restricts **the ability of other classes to extend Receipt**.

An important example in the JDK is `String`: it is a final class and has Object as its superclass. Many value classes and other classes can also be final while still maintaining their Object relationship according to the rules.

## 24. `abstract` Class: Still Has Only One Direct Superclass

`abstract` allows a class to express an abstraction that does not yet have a full implementation and prevents direct instantiation with `new AbstractClass()`.

```java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}
```

`Shape` does not write `extends`, so its direct superclass is Object. `Circle` extends one class, Shape. Even though Shape has an abstract method, it is **not an interface** and still obeys single class inheritance.

An abstract class can itself extend one superclass and implement multiple interfaces. It cannot have two direct superclass classes.

**Note:** An abstract class still has constructors used in subclass constructor chaining, static/instance fields, and implemented instance methods. You cannot conclude "it is abstract, so it has no Object".

## 25. `sealed` Classes Restrict Subclasses and Do Not Allow Multiple Class Inheritance

Java 17 has `sealed` types, used to control which types are allowed to inherit/implement within the corresponding hierarchy.

Example:

```java
sealed class Vehicle permits Car, Bike {
}

final class Car extends Vehicle {
}

final class Bike extends Vehicle {
}
```

`Vehicle` does not write `extends`, so it still inherits from Object. `Car` and `Bike` each have one direct superclass, Vehicle.

`sealed` controls **the list of permitted direct subclasses**; it does not change the rule that each class has only one direct superclass. Valid subclasses must satisfy the `final`, `sealed`, or `non-sealed` rules in the applicable context.

If you need a class to represent multiple capabilities, use multiple interfaces instead of trying to create "sealed multiple class inheritance".

## 26. `Object` Does Not Make Every Cast Valid

Even though every ordinary class instance is an Object, you **cannot** arbitrarily downcast an Object reference to any class without runtime compatibility.

File **`ObjectCastDemo.java`**:

```java
class Cat {
    String meow() {
        return "meow";
    }
}

class Dog {
    String bark() {
        return "woof";
    }
}

public class ObjectCastDemo {
    public static void main(String[] args) {
        Object value = new Cat();

        System.out.println(value instanceof Cat);
        System.out.println(value instanceof Dog);

        try {
            Dog wrong = (Dog) value;
            System.out.println(wrong.bark());
        } catch (ClassCastException ex) {
            System.out.println("invalid downcast");
        }

        Cat cat = (Cat) value;
        System.out.println(cat.meow());
    }
}
```

```bash
javac ObjectCastDemo.java
java ObjectCastDemo
```

```text
true
false
invalid downcast
meow
```

`Cat` and `Dog` may both inherit from Object, but they are **two different class branches**. A Cat object does not turn into a Dog just because both share the superclass Object.

If you are unsure of the type, use `instanceof` or design an appropriate common abstraction instead of casting blindly.

## 27. Object Methods via an Interface Variable

An interface **does not have Object as its superclass like an ordinary class**, yet Java allows the appropriate public Object methods to be visible through an interface-typed reference.

Runnable example:

File **`InterfaceObjectMethodsDemo.java`**:

```java
interface Named {
    String name();
}

final class Person implements Named {
    private final String value;

    Person(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }

    @Override
    public String toString() {
        return "Person(" + value + ")";
    }
}

public class InterfaceObjectMethodsDemo {
    public static void main(String[] args) {
        Named named = new Person("An");

        System.out.println(named.name());
        System.out.println(named.toString());
        System.out.println(named instanceof Object);
    }
}
```

```bash
javac InterfaceObjectMethodsDemo.java
java InterfaceObjectMethodsDemo
```

```text
An
Person(An)
true
```

Here `named` has static type Named, while the runtime object is Person:

- `named.name()` calls the interface method implementation in Person.
- `named.toString()` is valid and dispatches to `Person.toString()`.
- `named instanceof Object` is true because the runtime value is a Person instance, which inherits from Object through the class chain.

**An accurate way to put it:** Object is the root superclass **of the implementing class**, while an interface has its own set of method member/subtyping rules; do not use the syntax `interface Named extends Object`.

## 28. Having a Direct Superclass Does Not Mean the Superclass Must Declare Fields

Example:

```java
class Marker {
}

class Tagged extends Marker {
}
```

`Tagged` still inherits from Marker (and Object), even though Marker has no fields, custom methods, or explicit constructor. Inheritance is **a type relationship in the language**, not merely "copying useful lines of code".

However, inheriting from an empty class solely to act as a marker type may be unnecessary. A marker interface or annotation sometimes communicates intent more flexibly because it does not occupy the class's single superclass slot.

**From an API design perspective:** The decision to write `extends SomeBase` affects all future subclasses; avoid taking up class inheritance capability just for a detail that is easily expressed using an interface or composition.

## 29. `Object` References and General Collections

Because Object can hold references to many class instances, a `List<Object>` can store multiple kinds of elements:

```java
java.util.List<Object> values = java.util.List.of(
        "Java",
        Integer.valueOf(7),
        Boolean.TRUE
);
```

However, when reading:

```java
Object value = values.get(0);
```

the compiler only knows that `value` is Object. If the code needs String-specific operations, you must cast safely or design a generic collection with a more specific element type such as `List<String>`.

### Runnable Example

File **`ObjectListDemo.java`**:

```java
import java.util.List;

public class ObjectListDemo {
    public static void main(String[] args) {
        List<Object> mixed = List.of("Java", 7, true);

        for (Object value : mixed) {
            System.out.println(value.getClass().getSimpleName()
                    + ":" + value);
        }
    }
}
```

```bash
javac ObjectListDemo.java
java ObjectListDemo
```

```text
String:Java
Integer:7
Boolean:true
```

The primitive literals `7` and `true` are boxed into wrapper objects when passed to the corresponding generic method. It is not because primitive types have Object as a superclass.

**Do not use `List<Object>` everywhere just for convenience.** A specific generic type like `List<Student>` helps the compiler check types, helps the IDE suggest methods, and avoids unnecessary runtime casts.

## 30. There Is No "Separate Object Object Inside Every Object"

A visual model of a hierarchy often draws:

```text
Object
  |
  Animal
    |
    Dog
```

This is a diagram of **subtyping/class inheritance relationships**, not an assertion that each `new Dog()` creates three independent objects: `Object`, `Animal`, and `Dog`.

In Java:

```java
Dog dog = new Dog();
Animal a = dog;
Object o = dog;
```

The three variables can refer to **the same object**. `dog == a` and `a == o` are both true when the variables are assigned as above.

The superclass constructors participate in initializing **the same object being created** according to instance initialization rules. They do not create a new object for each superclass via `new Parent()`.

This understanding is important when analyzing aliasing, state, method overriding, and identity.

## 31. Notes on Static Methods and Fields in a Superclass

A subclass can use static members of its superclass according to inheritance/access rules, but that is **not dynamic polymorphism** like instance overrides.

```java
class Parent {
    static String name() {
        return "Parent";
    }
}

class Child extends Parent {
    static String name() {
        return "Child";
    }
}
```

If:

```java
Parent p = new Child();
System.out.println(p.name()); // "Parent" — static method hiding.
```

This is an **illustrative fragment inside a method**, not a standalone program. Static method selection is based on the appropriate compile-time information, not dispatched by the runtime receiver like an instance override.

**The `extends Object` relationship does not turn static methods into dynamic methods**. To understand Java polymorphism, you must distinguish between:

- Instance method overriding → runtime dispatch.
- Static method hiding → compile-time method resolution.
- Field hiding → the field is selected by compile-time type/lookup.
- Constructor → not overridden; invoked in the constructor chain.

Do not rely on an object expression to call a static method; using `Parent.name()` or `Child.name()` is clearer.

## 32. Design Mistakes When Overusing the Root Superclass

Statements like "everything is an Object so just pass Object" often lead to designs lacking type safety:

```java
void process(Object value) {
    // Must check the type, cast, and handle multiple cases.
}
```

There are better options depending on your needs:

- **Common superclass** when there is a genuine is-a relationship and meaningful shared instance behavior.
- **Interface** when multiple unrelated classes support the same capability.
- **Generics** when an algorithm processes the same structure while preserving type information.
- **Composition/delegation** when a class needs to use another object, rather than being a subtype of it.
- **Record/value object** when you need to carry data with a clear contract.

For example, if both Printer and FileLogger have `write(String)`, a `Writable` interface may be more useful than forcing both to extend an abstract class just to share the method signature. By implementing multiple interfaces, they can still retain the ability to extend another appropriate superclass.

## 33. Common Mistakes in Single-Inheritance Exercises

| Mistake | Why It Is Wrong | How to Understand / Fix |
| --- | --- | --- |
| "Without `extends`, a class has no superclass" | An ordinary class implicitly has Object | Check `Class.getSuperclass()` |
| "Java allows `extends A,B`" | A class has only one direct superclass | Use implementing interfaces/composition |
| "Every class directly extends Object" | Many classes extend an intermediate superclass | Object can be an indirect ancestor |
| "Object also extends a superclass" | Object is the root class | `Object.class.getSuperclass()==null` |
| "An interface implicitly `extends Object` like a class" | Interface rules are different | Objects implementing the interface are still Objects |
| "`implements A,B` is multiple class inheritance" | A and B are interfaces | Distinguish class vs. interface |
| "Having two fields with the same name in a subclass is field overriding" | Field hiding, not dynamic dispatch | Review compile-time field access |
| "Upcasting creates a new superclass instance" | Same object, only the reference type changes | Compare with `==` |
| "An Object variable can directly call any subclass method" | The compiler only knows the static type Object | Use an interface / safe downcast |
| "Sharing the Object superclass makes every cast valid" | The runtime object must be compatible with the target type | Use `instanceof`/pattern |
| "Default Object.equals compares field content" | Default equality is based on identity | Override equals/hashCode or use a record |
| "Default hashCode is the RAM address" | There is no such contract | Do not rely on memory addresses |
| "Override equals without needing hashCode" | Breaks the contract of hash-based collections | Override both consistently |
| "`getClass` can be overridden like `toString`" | getClass is final | Use the implementation from Object itself |
| "The Object constructor does not participate in instance construction" | The constructor chain reaches Object | Consider implicit/explicit super |
| "All final classes have no superclass" | Final only forbids subclasses | A final class still inherits |
| "A record directly extends Object" | A record extends `java.lang.Record` | Object is an indirect ancestor |
| "An enum directly extends Object" | An enum extends `java.lang.Enum` | Object is an indirect ancestor |
| "An array is not an object because its elements can be int" | An array is a reference type/object | `array instanceof Object` |
| "int has `getClass()` because of boxing" | int is primitive; boxing creates Integer | Distinguish conversion from inheritance |
| "Not declaring a constructor skips Object()" | The default constructor still calls the superclass chain | Compiler inserts an implicit invocation |
| "If the superclass has no no-arg constructor, a subclass cannot exist" | You can call explicit `super(args)` | Provide a valid constructor |
| "Single inheritance means a single supertype" | One ancestor chain + multiple interfaces | Distinguish direct superclass and supertypes |
| "Sealed allows a class to inherit multiple classes" | Sealed restricts permitted subclasses | Still one direct superclass |

## 34. Comprehensive Practice: Predict the Output Before Running

File **`SingleInheritanceTraceDemo.java`**:

```java
interface RunnableThing {
    void run();
}

class RootItem {
    RootItem() {
        System.out.println("RootItem()");
    }

    String label() {
        return "root";
    }
}

class SpecializedItem extends RootItem implements RunnableThing {
    SpecializedItem() {
        System.out.println("SpecializedItem()");
    }

    @Override
    String label() {
        return "special";
    }

    @Override
    public void run() {
        System.out.println("running");
    }

    @Override
    public String toString() {
        return "SpecializedItem";
    }
}

public class SingleInheritanceTraceDemo {
    public static void main(String[] args) {
        SpecializedItem item = new SpecializedItem();

        RootItem parent = item;
        Object root = item;
        RunnableThing task = item;

        System.out.println(parent.label());
        System.out.println(root.toString());
        System.out.println(item instanceof Object);
        System.out.println(item.getClass().getSuperclass().getSimpleName());
        task.run();
    }
}
```

```bash
javac SingleInheritanceTraceDemo.java
java SingleInheritanceTraceDemo
```

**Output:**

```text
RootItem()
SpecializedItem()
special
SpecializedItem
true
RootItem
running
```

### Detailed Solution

1. `new SpecializedItem()` goes through the superclass constructor chain: `Object()` prints nothing, `RootItem()` prints, and then `SpecializedItem()` prints.
2. `RootItem parent = item` upcasts the reference; no new RootItem object is created.
3. `Object root = item` also points to the same SpecializedItem object.
4. `RunnableThing task = item` points to the same object via the interface type.
5. `parent.label()` is an instance method override, dispatches to `SpecializedItem.label()`, and prints `special`.
6. `root.toString()` calls SpecializedItem's override and prints `SpecializedItem`.
7. `item instanceof Object` is true.
8. `item.getClass()` is SpecializedItem; its direct superclass is RootItem, not Object, so it prints `RootItem`.
9. `task.run()` calls the interface instance method implementation and prints `running`.

**Takeaway from the program:** an object can be viewed through **multiple supertype references**, yet a subclass still has only **one direct superclass**.

## 35. Extended Exercises with Suggested Answers

**Exercise 1.** Draw the superclass chain of `class C extends B`, `class B extends A`, `class A`.

*Answer:* `Object → A → B → C`. C has B as its direct superclass, and A/Object are indirect ancestors.

**Exercise 2.** Is `class D extends A, B` valid if A and B are classes?

*Answer:* No. Java does not support multiple class inheritance syntax.

**Exercise 3.** Is `class D extends A implements X,Y` valid if X/Y are interfaces and the required methods are implemented?

*Answer:* Yes, provided all inheritance, access, and method implementation rules are satisfied and there are no unresolved conflicts.

**Exercise 4.** If `class A` does not have `extends`, what does `A.class.getSuperclass()` return?

*Answer:* `Object.class` for a standard ordinary class.

**Exercise 5.** If `Object.class.getSuperclass()` is called, is an exception thrown?

*Answer:* No. It returns `null`.

**Exercise 6.** Can a `record Point(int x,int y)` write `extends Shape`?

*Answer:* No. A record class has `java.lang.Record` as its direct superclass defined by the language.

**Exercise 7.** What is the direct superclass of `enum Direction`?

*Answer:* `java.lang.Enum`, not Object directly.

**Exercise 8.** Is `Object o = new int[2];` valid?

*Answer:* Yes. An array is an object even though its element type `int` is primitive.

**Exercise 9.** Is `Object o = 10;` valid?

*Answer:* Yes, when boxing conversion applies; it does not prove that `int` is a subclass of Object.

**Exercise 10.** If two objects have `equals` returning true, must their `hashCode` values be the same?

*Answer:* Yes, according to the equals/hashCode contract that implementations must follow.

**Exercise 11.** If two objects have the same `hashCode`, are they necessarily equal?

*Answer:* No. Hash collisions are valid.

**Exercise 12.** If `Object o = new Dog();`, will `o.bark()` be accepted by the compiler when bark is declared only in Dog?

*Answer:* No. Use a Dog reference or safe pattern matching/casting.

**Exercise 13.** Does the call `o.toString()` use Dog's override?

*Answer:* Yes, if Dog overrides toString validly; runtime dispatch resolves to the appropriate implementation.

**Exercise 14.** Can `final class A` `extends B`?

*Answer:* Yes, when B is permitted to be inherited from; `final` forbids other classes from extending A.

**Exercise 15.** If the superclass has only a `Base(int)` constructor, why can a subclass constructor without `super(...)` be invalid?

*Answer:* Implicit `super()` cannot find an accessible no-arg superclass constructor; a valid `super(value)` call must be used.

**Exercise 16.** Do interfaces have an "implicit Object superclass"?

*Answer:* No, not under ordinary class inheritance. An interface has a relationship with public Object methods/subtyping according to its own rules; an object implementing the interface still has a class chain reaching Object.

**Exercise 17.** Given a `String`, can you write `class MyString extends String`?

*Answer:* No. String is a final class and cannot be subclassed.

**Exercise 18.** Does `Class.getSuperclass()` returning null for an interface mean the interface is a root class similar to Object?

*Answer:* No. An interface does not have a class superclass chain of that kind.

## 36. Self-Assessment Checklist for Correct Understanding

- [ ] Do I know that each ordinary class has only **one direct superclass**?
- [ ] Do I know that without declaring `extends`, an ordinary class implicitly inherits from `Object`?
- [ ] Do I understand that Object is the root class and `Object.class.getSuperclass()==null`?
- [ ] Do I distinguish between **direct superclass**, **superclass chain**, and all supertypes?
- [ ] Do I know that `implements` can list multiple interfaces?
- [ ] Do I understand that an interface `extends` multiple interfaces, but does not `extends Object` like an ordinary class?
- [ ] Do I distinguish between **is-a** and **has-a**, and avoid using extends just to reuse behavior?
- [ ] Can I draw Object→A→B→C and explain that upcasting does not create a new object?
- [ ] Do I know which Object methods can be overridden and that `getClass` is final?
- [ ] Do I understand that `toString`, `equals`, and `hashCode` have their own contracts?
- [ ] Do I know that default Object equality differs from the value equality of String/record?
- [ ] Do I use `instanceof` before downcasting when the runtime type is uncertain?
- [ ] Do I avoid confusing primitive boxing with inheritance of primitives?
- [ ] Do I know that arrays are objects and have relationships with Object, Cloneable, and Serializable?
- [ ] Do I know that the direct superclass of `record` is `Record` and of `enum` is `Enum`?
- [ ] Do I understand that `final` and `sealed` restrict subclasses without creating multiple superclasses?
- [ ] Do I know that the constructor chain of ordinary classes goes back to `Object`?
- [ ] Do I understand that `super(...)` is a constructor invocation, not an inherited method?
- [ ] Do I distinguish static method hiding from instance method overriding?
- [ ] Can I inspect the superclass with reflection and recognize the different cases that return `null`?
- [ ] Have I tried the Java 17+ programs with filenames matching the public class, `javac`/`java` commands, and reliable stdout?

---

**End-of-lesson takeaway:** Java has **single class inheritance**: each ordinary class has only **one direct superclass**. If `extends` is not written, that superclass defaults to **`java.lang.Object`**; with multiple levels of `extends`, Object is still the ancestor class at the root. Java does not allow `extends ClassA, ClassB`, but allows **implementing multiple interfaces**, and an interface can `extends` multiple interfaces. Object provides common methods such as `equals`, `hashCode`, `toString`, and `getClass`, and participates in the constructor chain; **upcasting to Object does not create a new object**. Do not confuse the exceptions that have their own rules: `record` directly extends `Record`, `enum` directly extends `Enum`, arrays are objects, and primitive types are not subclasses of Object. Understanding these properly helps build accurate class relationships, use polymorphism safely, and design maintainable Java APIs.
