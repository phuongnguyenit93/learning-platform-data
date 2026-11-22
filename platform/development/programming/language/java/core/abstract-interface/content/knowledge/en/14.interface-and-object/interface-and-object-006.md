# Limitations of the Cloneable Marker Interface in Java

Cloneable is a marker indicating to the default Object.clone() mechanism that an object is allowed to be cloned. It does not declare a copy method, does not grant public access, and does not guarantee an independent copy or preserve all class invariants.

## 1. A marker indicates capability and does not provide an operation

~~~java
public interface Cloneable {
}
~~~

This is what the standard java.lang.Cloneable interface looks like: it has no methods. Therefore, a variable of type Cloneable cannot call x.clone(); the compiler does not find a clone() method in the interface. Object.clone() is declared protected and must be called from a context with appropriate access permissions. The public API and interface contract are covered in the article on protected clone.

With the default behavior of Object.clone(), the runtime checks whether the object belongs to a class that implements Cloneable, including through inheritance. If not, it throws CloneNotSupportedException. If so, it creates a new object of the same runtime class and copies the field values as a shallow copy.

~~~text
Object.clone() is called
    |
    +-- object does not support Cloneable
    |       -> CloneNotSupportedException
    |
    +-- object supports Cloneable
            -> creates a new object of the same runtime class
            -> copies field values
            -> does not recursively clone every referenced object
~~~

A class can define a method named clone() in its own way. You should not infer that every method with the same name uses the Object.clone() mechanism.

## 2. Program demonstrating shallow copy

~~~java
public class CloneableLimitsDemo {
    static final class Address {
        String city;
        Address(String city) { this.city = city; }
    }

    static final class Person implements Cloneable {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        @Override
        public Person clone() {
            try {
                return (Person) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    static final class WithoutMarker {
        @Override
        public WithoutMarker clone() throws CloneNotSupportedException {
            return (WithoutMarker) super.clone();
        }
    }

    static final class SafePerson {
        final String name;
        final Address address;

        SafePerson(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        SafePerson copy() {
            return new SafePerson(name, new Address(address.city));
        }
    }

    public static void main(String[] args) throws CloneNotSupportedException {
        Person original = new Person("Lan", new Address("Hà Nội"));
        Person cloned = original.clone();
        System.out.println(original != cloned);
        System.out.println(original.address == cloned.address);
        cloned.address.city = "Huế";
        System.out.println(original.address.city);

        SafePerson safe = new SafePerson("Minh", new Address("Đà Nẵng"));
        SafePerson independent = safe.copy();
        independent.address.city = "Cần Thơ";
        System.out.println(safe.address.city);

        try {
            new WithoutMarker().clone();
        } catch (CloneNotSupportedException e) {
            System.out.println(e.getClass().getSimpleName());
        }

        int[][] matrix = {{1, 2}};
        int[][] matrixClone = matrix.clone();
        System.out.println(matrix != matrixClone);
        System.out.println(matrix[0] == matrixClone[0]);
    }
}
~~~

Output:

~~~text
true
true
Huế
Đà Nẵng
CloneNotSupportedException
true
true
~~~

The Person instances are two different objects after cloning, but they share the same Address reference. Modifying the address through the clone also changes the data seen by the original. SafePerson.copy() explicitly creates a new Address, so the two objects do not share the address. WithoutMarker compiles, but super.clone() throws CloneNotSupportedException because the object does not support the marker. For multidimensional arrays, cloning the outer array does not clone the inner arrays.

## 3. What Cloneable does not guarantee

Cloneable does not define:
- A deep copy of the entire object graph.
- That two objects after cloning must be equal according to equals().
- Rules for keeping, clearing, or generating new business IDs.
- How to copy sockets, file descriptors, locks, listeners, caches, or transactions.
- A consistent snapshot while multiple threads are modifying state.
- That constructors or field initializers re-run to validate invariants.

Object.clone() creates an object without running the target class's constructor the way new normally does. Therefore, if the constructor registers listeners, validates data, or initializes resources, a shallow clone can bypass those steps. A final field only forbids reassigning the reference after initialization; it does not make the referenced object immutable. For example, final Address is still shared in the program above.

Not every clone is wrong. A shallow copy may be suitable for a class designed with all primitive state or immutable references. However, the marker does not prove that; the class must define and test its copy semantics.

## 4. Inheritance and mutable state

If a superclass implements Cloneable, a subclass usually supports the marker through inheritance as well. That does not automatically guarantee that new fields in the subclass are copied properly according to business logic. A mutable List newly added to the subclass is still shared after a shallow clone. The superclass can also override clone() with its own contract, so you must not assume that every call path goes straight to Object's default implementation.

Java arrays are a special case: arrays support clone(). Cloning a primitive array creates a new array with the primitive values copied. For reference arrays or multidimensional arrays, the elements are references and are not recursively cloned. Therefore, matrix.clone() creates a new outer array while still sharing each inner array.

## 5. When should you use a copy constructor or factory?

~~~java
public final class Snapshot {
    private final String name;
    private final java.util.List<String> tags;

    public Snapshot(String name, java.util.List<String> tags) {
        this.name = java.util.Objects.requireNonNull(name);
        this.tags = java.util.List.copyOf(tags);
    }

    public Snapshot(Snapshot source) {
        this(source.name, source.tags);
    }

    public Snapshot copy() {
        return new Snapshot(this);
    }

    public java.util.List<String> tags() {
        return tags;
    }
}
~~~

Snapshot uses List.copyOf to keep the list unmodifiable through the returned API. Because the elements are immutable Strings, sharing elements is safe for this example; List.copyOf is not a general-purpose deep copy for mutable elements.

A copy constructor or static factory makes it clear which fields are shared and which are copied, and allows invariants to be checked in the constructor. If a polymorphic copy contract is needed, you can define a separate interface:

~~~java
interface Copyable<T> {
    T copy();
}
~~~

Even so, the copy() signature still needs to document the degree of independence, potential errors, and state preservation rules. If an object is already immutable, cloning may not be necessary; reusing the instance is usually simpler.

## 6. Common mistakes

| Assumption | Issue | How to handle |
| --- | --- | --- |
| implements Cloneable means callers can invoke clone() from anywhere | Object.clone() remains protected | Provide a public API if truly needed |
| Cloneable has a clone() method | The marker interface is empty | Distinguish the marker from Object's method |
| Clone automatically copies every nested object | Object.clone() is shallow by default | Explicitly copy each mutable field that needs independence |
| final fields are not shared | final does not make the referenced object immutable | Check the identity and state of child objects |
| Clone runs the constructor | The clone mechanism does not use constructors like new | Use a constructor/factory if invariants need to be re-established |
| Cloneable guarantees safe cloning across inheritance | A subtype may add state or resources | Design and test the contract across the entire hierarchy |

## 7. Design checklist

1. Determine which API allows callers to request a copy; do not rely on the marker to infer visibility.
2. Decide which mutable objects are allowed to be shared between the original and the copy.
3. Check whether any final fields reference mutable objects.
4. Check whether the constructor establishes invariants, registers listeners, or manages resources.
5. With inheritance, inspect fields added by subtypes as well.
6. Test identity with == and check state mutations after copying; equals() returning true does not mean two objects do not share state.
7. Consider a copy constructor, static factory, or a clearly named copy() when controlled copy semantics are needed.

Self-check:
- A class only implements Cloneable without overriding clone(): can external callers invoke it by default? No.
- If an object does not support Cloneable, yet a public clone() calls super.clone(), what happens? The default mechanism throws CloneNotSupportedException.
- Why can final Address still be shared after cloning? Cloning copies the reference value, while final only prevents reassigning the field.
- After cloning the outer array of a two-dimensional array, is it completely independent? No; the inner arrays are still shared.

Cloneable only enables a special behavioral branch of Object.clone(). It does not replace a copy contract designed by the API, nor does it guarantee a safe copy. Choose Cloneable when compatibility with this mechanism is needed and you have clearly defined shallow/deep copying, invariants, and shared state.
