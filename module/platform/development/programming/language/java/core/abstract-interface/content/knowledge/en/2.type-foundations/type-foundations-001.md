# Reference Type and Actual Type of an Object in Java

When working with inheritance, abstract classes, and interfaces, it is necessary to distinguish between the **type of the reference variable** and the **actual type of the object that the variable points to**. This distinction explains why the same method call can run different implementations, why not every method of an object can be called through a variable, and why downcasting sometimes fails.

## 1. Two Different Concepts

Consider the statement:

```java
Animal pet = new Dog("Milo");
```

Assume `Dog extends Animal`:

- The **reference type (declared type, compile-time type)** of `pet` is `Animal`. This is the type the compiler uses to check assignments, member accessibility, method signatures, and overload selection. The declared type of the variable `pet` does not automatically change to `Dog`.
- The **actual type (runtime class / dynamic type)** of the object created by `new Dog(...)` is `Dog`. That object has the state and behavior defined or inherited by `Dog`. `pet.getClass()` returns `Dog.class` when `pet` is not `null`.
- `pet` stores a **reference value to the object**. Assigning from another reference variable only copies the reference value; it does not turn the `Dog` object into a new `Animal` object.

Conceptual diagram:

```text
Variable pet
  declared type: Animal
  value: reference ──────────> object created by new Dog(...)
                               actual class: Dog
                               Animal part + Dog part
```

The two concepts can be viewed through two questions:

| Question | Deciding Factor |
| --- | --- |
| Is the source code `pet.someMethod()` valid? | The reference type `Animal` and the methods that this type declares or inherits |
| For an overridden instance method, which method body runs? | The actual class of the object, here `Dog` |
| Which field is accessed by an expression, or which `static` method is selected? | The type of the expression at compile time |
| Which overload is selected? | The static types of the arguments and the overloads available at compile time |
| Does downcasting to `Dog` succeed at runtime? | Is the actual object compatible with `Dog` at runtime? |

## 2. Upcasting and Polymorphism

If `Dog` is a subtype of `Animal`, Java allows assigning a `Dog` object to an `Animal` reference:

```java
Dog dog = new Dog("Milo");
Animal animal = dog;      // Implicit upcasting: valid
Object value = animal;    // Every Java class inherits from Object
```

All three variables can refer to **the same** `Dog` **object**. Upcasting does not create a copy and does not lose parts of the object. Similarly, an interface can be used as a reference type if the actual object class implements that interface.

```java
interface Trainable {
    void train();
}

class Puppy implements Trainable {
    @Override
    public void train() {
        System.out.println("Training");
    }
}

Trainable t = new Puppy(); // Variable has an interface type; the actual object is Puppy
t.train();                 // Callable because Trainable declares train()
```

The snippet above is an **illustrative code fragment**, not a standalone program file. An abstract class or interface cannot be instantiated directly with standard `new`, but it can still serve as a reference type pointing to an instance of an appropriate concrete class.

Polymorphism occurs when code works through a common type while the behavior still depends on each specific object:

```java
Animal first = new Dog("Milo");
Animal second = new Cat("Luna");

first.sound();  // Body of Dog.sound()
second.sound(); // Body of Cat.sound()
```

Here, `Animal` must declare or inherit the `sound()` method for the two statements to compile. Selecting the corresponding **implementation** of the overridden instance method happens at runtime, based on the actual class of the object.

## 3. Compilable and Runnable Java 17+ Example

Save the entire code below exactly into the file `ReferenceRuntimeTypeDemo.java`:

```java
public class ReferenceRuntimeTypeDemo {

    static abstract class Animal {
        final String name;
        String kind = "Animal field";

        Animal(String name) {
            this.name = name;
        }

        abstract String sound();

        String introduce() {
            return name + ": " + sound();
        }

        static String family() {
            return "Animal static";
        }
    }

    static final class Dog extends Animal {
        String kind = "Dog field";

        Dog(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "woof";
        }

        void fetch() {
            System.out.println(name + " fetches");
        }

        static String family() {
            return "Dog static";
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "meow";
        }
    }

    static String select(Animal animal) {
        return "Animal overload";
    }

    static String select(Dog dog) {
        return "Dog overload";
    }

    public static void main(String[] args) {
        Animal pet = new Dog("Milo");

        System.out.println("declared type: Animal");
        System.out.println("runtime type: " + pet.getClass().getSimpleName());
        System.out.println("sound: " + pet.sound());
        System.out.println("introduce: " + pet.introduce());
        System.out.println("field via Animal: " + pet.kind);
        System.out.println("field via Dog: " + ((Dog) pet).kind);
        System.out.println("static via Animal: " + Animal.family());
        System.out.println("static via Dog: " + Dog.family());
        System.out.println("overload via Animal: " + select(pet));
        System.out.println("overload via Dog: " + select((Dog) pet));

        if (pet instanceof Dog dog) {
            dog.fetch();
        }

        Animal other = new Cat("Luna");
        System.out.println("other: " + other.introduce());
    }
}
```

Run in the directory containing the file:

```bash
javac ReferenceRuntimeTypeDemo.java
java ReferenceRuntimeTypeDemo
```

Expected output:

```text
declared type: Animal
runtime type: Dog
sound: woof
introduce: Milo: woof
field via Animal: Animal field
field via Dog: Dog field
static via Animal: Animal static
static via Dog: Dog static
overload via Animal: Animal overload
overload via Dog: Dog overload
Milo fetches
other: Luna: meow
```

**Explanation of each important behavior:**

1. `Animal pet` determines the declared type; `new Dog(...)` determines the actual object class. The printed line `declared type: Animal` is a label we wrote manually in the code; Java does not provide `pet.getDeclaredType()` to directly retrieve the declared type of a variable at runtime.
2. `pet.sound()` executes `Dog.sound()` due to **dynamic dispatch**. Inside `Animal.introduce()`, the call to `sound()` is also dispatched to `Dog.sound()`, even though the body of `introduce()` resides in the superclass.
3. `pet.kind` selects the `Animal.kind` field; `((Dog) pet).kind` selects the `Dog.kind` field. Fields are **hidden (field hiding)**; field access does not have dynamic dispatch like calling an overridden method.
4. `Animal.family()` and `Dog.family()` demonstrate **static method hiding**, not overriding. Static methods should be called via the class name to make the intent clear. If you write `pet.family()`, Java still selects the version based on the declared type `Animal`, not the `Dog` object.
5. `select(pet)` selects the `select(Animal)` overload at compile time because the argument has the declared type `Animal`. Casting the expression to `Dog` makes `select((Dog) pet)` select the `select(Dog)` overload; the cast succeeds only because the actual object is a `Dog`.
6. `other` is also an `Animal` reference, but it points to a `Cat`, so `other.introduce()` calls `Cat.sound()`.

## 4. What the Reference Type Makes Visible

Suppose `Animal` declares `sound()`, while only `Dog` declares `fetch()`:

```java
Animal a = new Dog("Milo");
a.sound(); // Valid: Animal declares sound()
a.fetch(); // COMPILE ERROR: cannot find fetch() on type Animal
```

This is an **error-explaining code fragment**, not a snippet included in the runnable program in section 3. The object is still a `Dog` and still has the `fetch()` behavior, but the compiler can only rely on the interface exposed by the `Animal` type. Java does not automatically allow calling subclass-specific methods through a superclass variable.

To call `fetch()`, use a reference of the appropriate type after checking the object:

```java
Animal a = new Dog("Milo");
if (a instanceof Dog dog) { // Pattern matching for instanceof, Java 16+
    dog.fetch();
}
```

The type of the expression also determines member visibility according to the `public`, `protected`, package-private, and `private` access rules. The fact that a member exists in an object does not mean every location in the program has permission to access that member.

### Instance Calls, Field Access, Static Calls, and Overloads

| Mechanism | When Is It Decided? | Short Rule |
| --- | --- | --- |
| Choosing callable method signatures | Compile time | Based on the reference type and access permissions |
| Running the body of an overridden instance method | Runtime | Based on the actual class of the object |
| Accessing a field with the same name in superclass/subclass | Compile time | Based on the type of the access expression |
| Calling a `static` method with the same name | Compile time | Hiding based on the class/reference type |
| Selecting the `doWork(Animal)` or `doWork(Dog)` overload | Compile time | Based on the static type of the argument |
| Constructor | When creating the object | `new Dog(...)` creates a `Dog` object; constructors are not overridden |
| `private` or `final` methods | By declaration rules | These methods cannot be overridden |

Distinguish two easily confused terms: **overriding** is when a subclass provides a new body for an instance method with an appropriate signature from its superclass/interface; **overloading** is when multiple methods share the same name but have different parameter lists. Overriding creates runtime polymorphism, whereas overload resolution is static.

## 5. Downcasting: Changing the View, Not the Object

Casting from a superclass reference down to a subclass is called **downcasting**:

```java
Animal a = new Dog("Milo");
Dog d = (Dog) a;     // Valid and succeeds at runtime
d.fetch();
```

The cast `(Dog) a` does not create a new object, does not change the class of the object, and does not change the declared type of variable `a`. It produces a reference expression of type `Dog` after a runtime compatibility check.

You cannot infer that *every* `Animal` is a `Dog`:

```java
Animal a = new Cat("Luna");
Dog d = (Dog) a; // Compiles, but throws ClassCastException at runtime
```

Reason: `Cat` and `Dog` are both subclasses of `Animal`, but the actual object is a `Cat`. The cast is valid only if the actual object is an instance of the target type or a corresponding subtype. A safe, readable approach:

```java
void handle(Animal animal) {
    if (animal instanceof Dog dog) {
        dog.fetch();
    } else {
        System.out.println("Not a Dog");
    }
}
```

This is an **illustrative method** placed in an appropriate class, using the `Animal`/`Dog` classes from the main example. If the requirement can be solved with a common polymorphic method on `Animal`, prefer that design over checking each subclass sequentially.

An **upcast** is normally a safe, implicit conversion from a subclass to a superclass/interface. A **downcast** requires a runtime check; for unrelated reference types that the compiler knows for certain cannot be converted, the cast itself is even rejected at compile time.

## 6. `instanceof`, `getClass()`, and `null`

Two different ways of checking:

- `obj instanceof Dog` returns `true` if the object is non-null and compatible with `Dog`, including instances of subclasses of `Dog` (if `Dog` is not `final`).
- `obj.getClass() == Dog.class` is true only when the **exact actual class** is `Dog`. Calling `getClass()` on `null` throws `NullPointerException`.

Example:

```java
Object obj = "Java";
System.out.println(obj instanceof String);             // true
System.out.println(obj.getClass() == String.class);     // true

Object empty = null;
System.out.println(empty instanceof String);           // false
// empty.getClass(); // NullPointerException
```

The snippet above is an illustrative code fragment inside a method. `null` has no actual object class because **no object** is being referenced. You can assign `null` to a reference-type variable, but you cannot call an object's instance method through a null value. The cast `(Dog) null` evaluates to `null` and does not throw `ClassCastException` at the time of the cast.

An object has **one specific actual class** when created, yet can be compatible with multiple reference types (its superclasses and interfaces). `instanceof` checks type compatibility; `getClass()` tells you the exact actual class. You should not mechanically use a `getClass()` comparison to replace `instanceof`, because the two expressions answer two different questions.

## 7. Common Misconceptions

**Misconception 1: "If the variable is `Animal`, then the object is `Animal`."** Wrong for `Animal a = new Dog(...)`: the variable has the static type `Animal`, and the object has the actual class `Dog`. Even if `Animal` is an abstract class, declaring a variable of type `Animal` is still valid.

**Misconception 2: "Both overriding and overloading are selected by the actual class."** Overriding of instance methods uses dynamic dispatch. Overloading is resolved at compile time based on the types of the argument expressions, like `select(pet)` in the example.

**Misconception 3: "Fields are polymorphic like methods."** Field access follows the expression type; a field with the same name in a subclass is hiding. Use an instance method (such as an overridable getter) if you need polymorphic behavior, instead of relying on field hiding.

**Misconception 4: "Downcasting turns the object into the subclass."** A cast only changes the type of the **reference expression** that the code is using and performs a check when needed; the object still keeps the class determined at creation time.

**Misconception 5: "`instanceof` is always equivalent to `getClass() == ...`."** `instanceof` accepts subtypes, whereas comparing `getClass()` requires the exact actual class to match; `null` also produces a different result.

**Misconception 6: "A collection's type automatically changes because its elements are a subclass."** `List<Dog>` is not a subtype of `List<Animal>` in Java, even though `Dog extends Animal`. This is the invariance rule of generic type arguments, independent of the fact that a `Dog` element can be assigned to an `Animal` variable. You can use `List<? extends Animal>` to read elements as `Animal` when appropriate.

## 8. How to Analyze an Expression Yourself

When you encounter `Base x = new Derived();` and `x.action()`, answer in order:

1. **What type is variable `x` declared as?** The compiler uses that type to determine whether the method exists and is accessible.
2. **Which class was the object `x` points to created from?** If `action()` is an overridden instance method, the corresponding implementation of the actual class will run.
3. **Are you calling an instance method, a static method, an overload, or accessing a field?** Only overridden instance methods have dynamic dispatch in the sense discussed here.
4. **Is there a cast or `instanceof`?** Check the compatibility of the actual class, and remember that the static type of the expression after the cast can affect overload resolution and member access.
5. **Can the reference be `null`?** Check before dereferencing if the data flow allows null.

### Quick Self-Check

**Question 1.** Given `Animal a = new Dog("Milo");`, which method does `a.sound()` call if `Dog` overrides `sound()`? — **`Dog.sound()`**, provided the call is valid under the `Animal` type.

**Question 2.** Why might `a.fetch()` fail to compile, even though `a.getClass()` is `Dog.class`? — Because **the declared type `Animal` does not expose `fetch()`**; the compiler does not rely on the runtime result of `getClass()` to allow the call.

**Question 3.** Where does `Animal a = new Cat("Luna"); Dog d = (Dog) a;` fail? — The cast can **compile**, but it throws **`ClassCastException` at runtime**, because the object is a `Cat`.

**Remember:** the reference type controls **what the code can ask for**; the actual class of the object determines **which implementation runs** when calling an overridden instance method. Properly understanding these two layers is the foundation for designing APIs with abstract classes/interfaces and using polymorphism safely.
