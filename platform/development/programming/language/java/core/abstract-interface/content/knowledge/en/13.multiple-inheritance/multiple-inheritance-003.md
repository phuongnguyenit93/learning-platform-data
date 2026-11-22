# Multiple Compatible Abstract Declarations and Common Return Types in Java

A class can implement multiple interfaces with a single method when the signatures are compatible and the return type satisfies every contract. Having the same name is not enough; both parameters and return type must be considered.

## Covariant return type

~~~java
interface ObjectValue { Object value(); }
interface StringValue { String value(); }

final class TextValue implements ObjectValue, StringValue {
    @Override
    public String value() { return "Java"; }
}

public class Main {
    public static void main(String[] args) {
        TextValue value = new TextValue();
        Object a = ((ObjectValue) value).value();
        String b = ((StringValue) value).value();
        System.out.println(a);
        System.out.println(b);
        System.out.println(b.length());
    }
}
~~~

Output:

~~~text
Java
Java
4
~~~

String is a subtype of Object, so one String value() satisfies both contracts. The reference type determines the result type that the compiler allows to be used.

## When Are They Incompatible?

~~~java
interface StringSource { String value(); }
interface IntegerSource { Integer value(); }
// Intentionally invalid:
// class InvalidSource implements StringSource, IntegerSource {}
~~~

String and Integer do not have a suitable subtype relationship for one method with the same signature to satisfy both. You cannot overload by changing only the return type.

Covariant returns apply to reference types and do not allow replacing int with long. Primitive conversions in expressions do not make two declarations compatible for overriding.

Before merging methods, check the signature, return type, type arguments, and business meaning. Number amount() and Integer amount() can share Integer amount(); an implementation returning Object does not satisfy a contract requiring String.

## Self-Check

What return type can Number get() and Integer get() use? Can String get() and Integer get() be overloaded? Do int and long have covariant returns?

**Answer:** Integer; no; no.

Reference: [JLS §8.4.5 — Method Result](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.5).
