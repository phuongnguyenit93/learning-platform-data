# Reference Casting, `instanceof`, and `ClassCastException` in Java

> **Java core — language-basics / Type Conversion**  
> **Requirements:** JDK 17+; a standalone Java file, no external libraries needed.  
> **Objective:** Distinguish reference *upcasting* and *downcasting*, understand the **declared type** and **actual type** of an object, check with `instanceof` (including Java 17 *pattern matching*), and recognize/avoid `ClassCastException` on invalid casts at runtime.

## 1. Reference casting does not turn an object into another object

Consider the hierarchy:

~~~java
abstract class Animal {
    abstract String sound();
}
class Dog extends Animal {
    @Override String sound() { return "woof"; }
    void fetch() { /* only Dog has this behavior */ }
}
class Cat extends Animal {
    @Override String sound() { return "meow"; }
}
~~~

A variable of type `Animal` can reference an object that is actually a `Dog`:

~~~java
Animal pet = new Dog(); // Implicit upcast from Dog to Animal.
~~~

Distinguish two concepts clearly:

- **Declared type / static type:** `Animal` is the type the compiler sees for the variable `pet`. Therefore `pet.sound()` can be called, whereas `pet.fetch()` **does not** compile because `Animal` does not declare a `fetch()` method.
- **Actual type / runtime class:** the object that `pet` points to is still a `Dog`. Java dispatches `pet.sound()` to `Dog`'s override.
- **Reference casting:** changes how the compiler views a reference according to permitted type relationships; **does not create, copy, change the class of, or alter the data** of the object.

If you need `Dog`-specific methods and know for sure the object is actually a `Dog`:

~~~java
Dog dog = (Dog) pet; // Explicit downcast.
dog.fetch();
~~~

After the cast, `pet` and `dog` still point to the **same `Dog` object**. This cast is not like `Integer.parseInt` or converting a string to a number: it does not transform data inside the object.

## 2. How do upcast and downcast differ?

| Case | Example | Explicit cast needed? | Runtime check |
| --- | --- | --- | --- |
| **Upcast** subclass → superclass | `Animal a = new Dog();` | No | Safe by inheritance relationship |
| Upcast to implemented interface | `Runnable r = new Thread();` | No | Safe by `implements` relationship |
| **Downcast** superclass → subclass | `Dog d = (Dog) a;` | Yes | Actual object must be compatible with `Dog` |
| From `Object` → concrete class | `String s = (String) obj;` | Yes | Actual object must be `String` (or suitable subtype) |
| Cast `null` to reference type | `Dog d = (Dog) null;` | Allowed to write | Result remains `null`, **does not throw `ClassCastException`** |

Casting from a supertype down to a subtype **can compile** and still fail at runtime. The compiler only proves the conversion *could* make sense; it does not know for certain the runtime class of every object the variable might point to.

Example:

~~~java
Animal pet = new Cat();
// Dog wrong = (Dog) pet; // At runtime: ClassCastException.
~~~

`Cat` is an `Animal`, **not** a `Dog`; casting the reference to `Dog` cannot change that fact.

Conversely, some casts between classes with no possible conversion relationship are **rejected immediately at compile time**, rather than waiting for `ClassCastException`. Not every `(Type) value` syntax is valid.

## 3. `instanceof` checks the runtime type before downcasting

The `instanceof` operator asks whether the actual referenced object is compatible with the checked type:

~~~java
Animal pet = new Dog();

System.out.println(pet instanceof Dog); // true
System.out.println(pet instanceof Cat); // false
System.out.println(pet instanceof Animal); // true
~~~

**Java 17** supports *pattern matching for `instanceof`*, combining the check with declaring a narrowed variable:

~~~java
if (pet instanceof Dog dog) {
    dog.fetch(); // Compiler knows dog has type Dog.
}
~~~

This is clearer than the old pattern:

~~~java
if (pet instanceof Dog) {
    Dog dog = (Dog) pet;
    dog.fetch();
}
~~~

The scope of the **pattern variable** depends on control flow: in the `if` block above, `dog` is only usable on the branch where the check is guaranteed to succeed. Do not use that name outside locations where the compiler guarantees it has been assigned.

**Note on `null`:** `null instanceof Dog` and `variableNull instanceof Dog` both evaluate to **`false`**; `instanceof` does not cause an NPE simply because the left operand is `null`. If a `null` reference is cast to a valid reference type, the result remains `null`; an NPE can only happen **when you subsequently try to use it as an object**.

## 4. Compilable and runnable Java 17+ program

Create the file **ReferenceCastDemo.java**:

~~~java
public final class ReferenceCastDemo {
    private abstract static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        abstract String sound();
    }

    private static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "woof";
        }

        String fetch() {
            return name() + " fetched";
        }
    }

    private static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "meow";
        }
    }

    private static String describe(Animal animal) {
        if (animal instanceof Dog dog) {
            return "dog:" + dog.name();
        }
        if (animal instanceof Cat cat) {
            return "cat:" + cat.name();
        }
        return "none";
    }

    public static void main(String[] args) {
        Animal pet = new Dog("Milo"); // Upcast.
        System.out.println("runtimeType="
                + pet.getClass().getSimpleName());
        System.out.println("polymorphicSound=" + pet.sound());
        System.out.println("isDog=" + (pet instanceof Dog));
        System.out.println("isCat=" + (pet instanceof Cat));

        Dog dog = (Dog) pet; // Valid downcast.
        System.out.println("sameObject=" + (pet == dog));
        System.out.println("fetch=" + dog.fetch());
        System.out.println("describeDog=" + describe(pet));

        Animal another = new Cat("Luna");
        System.out.println("catSound=" + another.sound());
        System.out.println("describeCat=" + describe(another));

        try {
            Dog wrong = (Dog) another; // Runtime is Cat.
            System.out.println(wrong.fetch());
        } catch (ClassCastException ex) {
            System.out.println("animalCastFailed=true");
        }

        Object number = Integer.valueOf(7);
        System.out.println("objectIsString="
                + (number instanceof String));
        try {
            String wrong = (String) number;
            System.out.println("unexpected=" + wrong);
        } catch (ClassCastException ex) {
            System.out.println("objectCastFailed=true");
        }

        Animal absent = null;
        System.out.println("nullInstanceof=" + (absent instanceof Dog));
        Dog nullDog = (Dog) absent; // Casting a null reference is valid.
        System.out.println("nullCast=" + (nullDog == null));
        System.out.println("describeNull=" + describe(absent));
    }
}
~~~

Open a terminal in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ReferenceCastDemo.java
java ReferenceCastDemo
~~~

**Exact expected output:**

~~~text
runtimeType=Dog
polymorphicSound=woof
isDog=true
isCat=false
sameObject=true
fetch=Milo fetched
describeDog=dog:Milo
catSound=meow
describeCat=cat:Luna
animalCastFailed=true
objectIsString=false
objectCastFailed=true
nullInstanceof=false
nullCast=true
describeNull=none
~~~

Explanation:

1. `pet` is declared as `Animal` but its runtime class is `Dog`; calling `pet.sound()` executes `Dog.sound()` via polymorphism.
2. `(Dog) pet` succeeds and `pet == dog` is `true` because casting **does not create a new object**.
3. `describe` uses pattern matching `instanceof` to check the type and directly obtain a properly typed `dog`/`cat` variable without a separate cast.
4. `(Dog) another` compiles because `another` has type `Animal`, yet at runtime it is a `Cat`, so it throws `ClassCastException`.
5. `number` actually holds an `Integer`. `number instanceof String` returns false; `(String) number` throws `ClassCastException`.
6. `absent` is `null`: `instanceof` returns false, and casting to `Dog` still yields `null`. Only invoking a method through that reference risks throwing `NullPointerException`.

The `catch` blocks are used **solely to demonstrate runtime check failures**; in production code, prefer proper checks, API design, or polymorphism instead of using exceptions as routine branching conditions.

## 5. Distinguishing `ClassCastException` from similar errors

| Symptom | Error type / behavior | Reason |
| --- | --- | --- |
| `Animal x = new Cat(); Dog d = (Dog) x;` | **ClassCastException** at runtime | Runtime object is `Cat`, not `Dog` |
| `Object x = Integer.valueOf(7); String s = (String) x;` | **ClassCastException** at runtime | `Integer` cannot be viewed as `String` |
| `Dog d = (Dog) null;` | Succeeds, `d == null` | Casting `null` does not raise `ClassCastException` |
| `d.fetch()` when `d == null` | **NullPointerException** | Calling a method on a `null` reference |
| `Animal a = new Dog(); a.fetch();` | **Compile error** | Declared type `Animal` has no `fetch()` |
| `String s = (String) new Dog(...);` with unrelated classes | **Compile error** | No Java-accepted cast exists between those two class types |
| Assigning `Dog[]` to `Animal[]` then storing a `Cat` | Possible **ArrayStoreException** | Runtime checks array element type, not direct reference cast |

`ClassCastException` reflects **a reference incompatible with the type the program attempts to cast to**; NPE indicates there is no object at the dereferenced pointer. The two errors have different causes and fixes.

## 6. When should you cast, and when should you avoid casting?

**Prefer polymorphism** if behavior can be described by a supertype or interface:

~~~java
Animal pet = new Dog("Milo");
System.out.println(pet.sound()); // No need to know subtype.
~~~

Only downcast when subtype-specific APIs are genuinely needed and compatibility is checked:

~~~java
if (pet instanceof Dog dog) {
    System.out.println(dog.fetch());
}
~~~

Some principles:

- **Rely on type contracts:** an API returning `Animal` does not mean the object is always a `Dog`. Do not cast just because “it worked in a quick test”.
- **Do not catch `ClassCastException` instead of `instanceof`** in normal control flow; catch exceptions appropriately when handling abnormal failures or at error-handling boundaries.
- **Use pattern matching judiciously:** `instanceof Dog dog` is cleaner than checking and then casting repeatedly, yet overusing many subtype checks may signal a design needing polymorphism/strategy.
- **Do not confuse casting with value conversion:** `(String) Integer.valueOf(7)` is not how you turn a number into a string; use `String.valueOf(7)` if you genuinely want to convert content.
- **Note generic type erasure:** you cannot use `obj instanceof java.util.List<String>` to check full type arguments at runtime; checking `instanceof List<?>` only confirms the raw class/type, not that every element is a `String`.

## 7. Self-practice exercises

**Exercise 1.** Given `Animal a = new Dog("Max");`. Why is `a.sound()` valid while `a.fetch()` does not compile? Write a safe way to call `fetch()`.

**Exercise 2.** Given `Animal animal = new Cat("Miu");`. Predict `animal instanceof Dog` and the behavior of `(Dog) animal`; point out when the error occurs.

**Exercise 3.** Substitute `Animal animal = null;` into the `instanceof` check. What is the result? Why does `(Dog) animal` itself not throw NPE or `ClassCastException`?

**Exercise 4.** Given `Object obj = Integer.valueOf(5);`. Compare the behavior of `obj instanceof String`, `(String) obj`, and `String.valueOf(obj)`.

**Exercise 5.** Modify the `describe` method in the program to use the `instanceof` pattern for subtypes; if passed a `Dog`, `Cat`, or `null` object, the printed output should match accordingly.

### Takeaways

**Reference casting changes the variable's type view, not the object itself.** Upcasts are generally safe and require no cast. Downcasts require a compatible runtime object, otherwise **`ClassCastException`** is thrown. Use **`instanceof`** or Java 17 pattern matching to check when a subtype API is needed, keeping in mind that **`null instanceof Type` is false** and **casting a `null` reference still yields `null`**. When only common behavior is needed, prefer **polymorphism** over casting.