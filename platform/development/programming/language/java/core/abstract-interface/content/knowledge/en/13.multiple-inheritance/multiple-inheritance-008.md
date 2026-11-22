# Superclass Abstract Method Blocks Default Implementation in Java

An abstract method inherited from a superclass remains an obligation of the subclass. A default method with the same signature in an interface does not automatically fulfill that obligation; a concrete subclass requires a valid implementation.

~~~java
interface Greeter {
    default String greet() { return "hello from interface"; }
}
abstract class Base {
    public abstract String greet();
}
// This concrete class is invalid if it does not override:
// class Broken extends Base implements Greeter {}

final class Person extends Base implements Greeter {
    @Override
    public String greet() {
        return "hello from Person";
    }
}
public class Main {
    public static void main(String[] args) {
        Base base = new Person();
        Greeter greeter = (Greeter) base;
        System.out.println(base.greet());
        System.out.println(greeter.greet());
    }
}
~~~

Output:

~~~text
hello from Person
hello from Person
~~~

Person.greet() is the actual implementation; if it is removed while keeping Person concrete, Base.greet() remains abstract.

## Call the default intentionally if you want to use it

~~~java
@Override
public String greet() {
    return "custom: " + Greeter.super.greet();
}
~~~

This is a replacement body for the method in the class, not an additional declaration. The class still provides its own implementation; Greeter.super.greet() only reuses the default in a valid direct superinterface context.

## Comparison with a concrete superclass

If the superclass has public String greet() with a suitable body, the subclass can inherit that method; the class method takes precedence over the default. The difference is that a concrete method already provides a body, whereas an abstract method keeps the obligation on the subclass.

An abstract class can also intentionally redeclare a default method as abstract:

~~~java
abstract class StrictGreeter implements Greeter {
    @Override
    public abstract String greet();
}
~~~

A concrete subclass of StrictGreeter must implement greet(). This is a design choice to force the class branch to provide its own behavior.

Reference: [JLS §8.4.8.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.4).

## Self-check

A superclass has public abstract String status(); an interface has default status(). Can a concrete subclass omit it? What if the superclass has a compatible concrete method? Can the default be called from an override?

**Answer:** no; the superclass's concrete method takes precedence; yes, via a valid qualified super call.
