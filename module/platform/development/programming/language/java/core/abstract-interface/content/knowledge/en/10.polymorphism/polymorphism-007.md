# ClassCastException and Restrictions on Invalid Casting in Java

## 1. Reference Casting Does Not Transform Objects

In Java, the **static type** of an expression is checked at compile time; the **actual (runtime) type** of the object determines whether a downcast succeeds and which polymorphic method is called.

`ClassCastException` is a runtime exception that occurs when a reference cast is accepted at compile time, but the actual object is incompatible with the target type. Casting only asks Java to check or view a reference as another type; it does not turn a `Bicycle` object into a `Car` and does not call a constructor to convert the object.

| Case | Example | Result |
| --- | --- | --- |
| Upcasting to a superclass/interface | `Vehicle v = new Car();` | Automatic, safe based on the type relationship |
| Downcasting to a subclass | `Car c = (Car) v;` | Explicit; may fail at runtime |
| Two unrelated classes | `Car c = (Car) new Bicycle();` | Compile-time error if the two classes have no valid type relationship |

A variable of type `Vehicle` can point to a `Car` or a `Bicycle`. Therefore, `(Car) vehicle` can succeed if the actual object is a `Car`, but throws `ClassCastException` if the actual object is a `Bicycle`.

## 2. What Do Compile-Time and Runtime Check?

1. **Compile-time:** The compiler examines the static types and the relationships between them. If a reference conversion is invalid under Java rules, the code is rejected immediately; the program does not run and there is no runtime exception.
2. **Runtime:** For downcasts allowed by the compiler, the JVM checks the actual type of the object. If the object is not of the target type or a compatible subclass, the cast throws `ClassCastException`.

Example that compiles but throws an exception at runtime:

~~~java
Vehicle vehicle = new Bicycle("B-2");
Car car = (Car) vehicle;
~~~

`vehicle` has the static type `Vehicle`, so the compiler knows it could reference a `Car`. However, the object actually created is a `Bicycle`; a cast cannot change that.

The following snippet produces a compile-time error when `Car` and `Bicycle` are two unrelated classes:

~~~java
Car car = (Car) new Bicycle("B-2"); // Compile-time error
~~~

The static type of the expression is already `Bicycle`, so the compiler knows it cannot be a `Car`. Assigning that object to a variable of the general type `Vehicle` does not change its actual type; it only allows the subsequent cast to pass the static type check, and then still fail at runtime.

## 3. Java 17+ Example: Safe Downcasting with instanceof

Save the following code to **CastSafetyDemo.java**:

~~~java
abstract class Vehicle {
    private final String id;

    protected Vehicle(String id) {
        this.id = id;
    }

    public final String id() {
        return id;
    }

    abstract String kind();
}

final class Car extends Vehicle {
    Car(String id) {
        super(id);
    }

    @Override
    String kind() {
        return "Car";
    }

    String honk() {
        return "beep";
    }
}

final class Bicycle extends Vehicle {
    Bicycle(String id) {
        super(id);
    }

    @Override
    String kind() {
        return "Bicycle";
    }
}

public class CastSafetyDemo {
    public static void main(String[] args) {
        Vehicle first = new Car("C-7");
        System.out.println("Kind: " + first.kind());

        if (first instanceof Car car) {
            System.out.println("Car id: " + car.id());
            System.out.println("Sound: " + car.honk());
        }

        Vehicle second = new Bicycle("B-2");
        System.out.println("Kind: " + second.kind());

        try {
            Car wrong = (Car) second;
            System.out.println(wrong.honk());
        } catch (ClassCastException error) {
            System.out.println("Rejected: Bicycle is not a Car");
        }

        Object value = "hello";
        try {
            Integer number = (Integer) value;
            System.out.println(number);
        } catch (ClassCastException error) {
            System.out.println("Rejected: String is not an Integer");
        }

        Object nothing = null;
        Car absent = (Car) nothing;
        System.out.println("Null cast: " + (absent == null));
    }
}
~~~

Compile and run using JDK 17 or later:

~~~bash
javac CastSafetyDemo.java
java CastSafetyDemo
~~~

Exact output:

~~~text
Kind: Car
Car id: C-7
Sound: beep
Kind: Bicycle
Rejected: Bicycle is not a Car
Rejected: String is not an Integer
Null cast: true
~~~

Explanation:

- `first.kind()` calls `Car`'s method via polymorphism. No downcast is needed to invoke behavior already in the superclass.
- `first instanceof Car car` both checks the actual type and creates the pattern variable `car` in the true branch. Pattern matching syntax for `instanceof` has been available since Java 16, so it works in Java 17.
- `(Car) second` compiles because the static type is `Vehicle`, but fails because the actual object is a `Bicycle`. The line calling `wrong.honk()` does not execute.
- `(Integer) value` fails because the actual object is a `String`, even though the variable has the static type `Object`.
- Casting `null` to `Car` does not cause a `ClassCastException`. The result remains `null`; calling a method on that variable will cause a `NullPointerException`.

## 4. Use instanceof or Polymorphism Instead of Blind Casting

If subclass-specific behavior is truly needed, check the type first:

~~~java
if (vehicle instanceof Car car) {
    System.out.println(car.honk());
} else {
    System.out.println("Vehicle is not a Car");
}
~~~

In older versions of Java, you can write:

~~~java
if (vehicle instanceof Car) {
    Car car = (Car) vehicle;
    System.out.println(car.honk());
}
~~~

`instanceof` returns `false` when the reference is `null`. A pattern variable helps avoid checking one variable and accidentally casting a different reference. Do not use `try/catch` as a routine way to probe an object's type; check before using it.

Even so, **no downcast is needed if the behavior belongs to the common contract**:

~~~java
Vehicle vehicle = new Car("C-8");
System.out.println(vehicle.kind());
~~~

`kind()` is declared on `Vehicle`, so polymorphism handles it properly. Only cast when you need specialized behavior not yet present on the superclass/interface. If the code contains too many `instanceof` branches, consider moving the behavior into subclasses or redesigning the abstraction.

## 5. Interfaces, Arrays, and Generics: Easily Confused Cases

Casting rules also apply to interfaces. A cast may be accepted by the compiler based on a general static type, yet fail because the object does not implement the target interface:

~~~java
Object value = "hello";
Runnable task = (Runnable) value; // ClassCastException at runtime
~~~

`String` does not implement `Runnable`. With a more specific static type, the compiler can reject the cast immediately if no valid type relationship exists.

Several cases need to be distinguished:

- **Primitive cast:** Casting `int` to `byte` can lose data, but it does not cause `ClassCastException`. This is a numeric conversion, not a reference cast.
- **Arrays:** Java arrays are covariant. `Object[] values = new String[1]; values[0] = 42;` throws `ArrayStoreException` when storing an `Integer` into an array that is actually a `String[]`; this exception is different from `ClassCastException`.
- **Generics and type erasure:** Generic type arguments are usually not fully retained for runtime checking. Casting to a generic type may only check the raw type, and an error then occurs when retrieving elements.
- **Unchecked cast:** The compiler may warn that it cannot verify the type arguments. A warning does not mean the cast is safe.

The following generic example is a standalone illustration, not part of `CastSafetyDemo`:

~~~java
import java.util.List;

Object value = List.of("text");
@SuppressWarnings("unchecked")
List<Integer> numbers = (List<Integer>) value;
Integer first = numbers.get(0); // ClassCastException when retrieving the element
~~~

The cast to `List<Integer>` may only check that the object is a `List`. The actual list contains a `String`; when the result of `get(0)` is converted to `Integer`, the cast inserted by the compiler to satisfy the target type fails. In production code, do not use `@SuppressWarnings` to hide unverified assumptions; avoid raw types and validate input data.

## 6. Handling ClassCastException Intentionally

Prioritize preventing invalid casts before they happen rather than catching exceptions to probe types.

- Use a superclass/interface and polymorphism if the behavior already belongs to the common contract.
- For data with an overly broad static type such as `Object`, check with `instanceof` before calling specific behavior.
- For APIs or external data, clearly define the allowed types and reject data that does not satisfy the contract.
- Only catch `ClassCastException` when there is a specific business reason; do not swallow the exception and continue as if the operation succeeded.
- Do not use class names or display strings in place of type checks.

Distinguish **casting** from **conversion**: reference casting checks an object's compatibility. Actual conversion, such as parsing a string into a number with `Integer.parseInt(text)`, uses conversion APIs and can throw `NumberFormatException` if the string is invalid.

## 7. Checklist and Common Mistakes

Before every cast, ask:

1. What is the static type of the expression?
2. Does the compiler allow the conversion? If not, it is a compile-time error, not a runtime exception.
3. Can the actual type be the target type? If unsure, use `instanceof` or fix the design.
4. Can the method be called through the superclass/interface to eliminate the cast?
5. With generics/raw types, does the runtime check actually guarantee the element type?
6. On failure, will the program reject the data explicitly or silently continue?

Common mistakes include thinking a cast transforms an object, assuming every superclass reference points to the same subclass, confusing a compile-time error with `ClassCastException`, ignoring unchecked cast warnings, or catching exceptions too broadly.

**Remember:** Upcasting is usually automatic and safe; downcasting must be grounded in the actual type. The compiler checks casts based on static types, whereas the JVM checks the object at runtime. Use polymorphism when possible and `instanceof` before needing specialized behavior.
