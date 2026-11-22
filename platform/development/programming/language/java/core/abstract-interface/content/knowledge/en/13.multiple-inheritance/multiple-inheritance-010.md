# Distinguishing Method, Constant, and Member Type Conflicts in Java Interfaces

The same name across multiple interfaces can belong to different kinds of members. Method resolution rules do not apply identically to static methods, fields, or member types.

| Member | Characteristics | Identification |
| --- | --- | --- |
| Abstract method | Contract without a body | A single implementation can satisfy multiple compatible contracts |
| Default method | Instance method with a body | Check specificity and conflicts |
| Static method | Belongs to the interface that declares it | JsonCodec.format() |
| Field | Implicitly public static final | SmallLimits.LIMIT |
| Member type | Implicitly public static nested type | LocalOptions.Policy |

## Static Methods

~~~java
interface JsonCodec {
    static String format() { return "JSON"; }
}
interface XmlCodec {
    static String format() { return "XML"; }
}
class Codec implements JsonCodec, XmlCodec {}

public class StaticMethodsDemo {
    public static void main(String[] args) {
        System.out.println(JsonCodec.format());
        System.out.println(XmlCodec.format());
    }
}
~~~

Output:

~~~text
JSON
XML
~~~

Codec does not inherit static methods like instance methods and does not need to override them.

## Constants with the Same Name

~~~java
interface SmallLimits { int LIMIT = 10; }
interface LargeLimits { int LIMIT = 100; }
class Config implements SmallLimits, LargeLimits {
    int smallLimit() { return SmallLimits.LIMIT; }
    int largeLimit() { return LargeLimits.LIMIT; }
}
~~~

SmallLimits.LIMIT and LargeLimits.LIMIT are two separate static fields. Fields are not overridden polymorphically; using the qualified name clearly indicates the source of the value.

Class fields are also looked up statically by reference type:

~~~java
class Parent { String label = "parent"; }
class Child extends Parent { String label = "child"; }
public class FieldHidingDemo {
    public static void main(String[] args) {
        Parent value = new Child();
        System.out.println(value.label);
        System.out.println(((Child) value).label);
    }
}
~~~

The output is parent then child: this is field hiding, not method overriding.

## Member Types with the Same Name

~~~java
interface LocalOptions { class Policy {} }
interface RemoteOptions { class Policy {} }
class OptionReader implements LocalOptions, RemoteOptions {
    LocalOptions.Policy local = new LocalOptions.Policy();
    RemoteOptions.Policy remote = new RemoteOptions.Policy();
}
~~~

LocalOptions.Policy and RemoteOptions.Policy are two different types. Nested types cannot override or merge those two types; use explicitly qualified names.

## How to Analyze

1. Determine whether the member is a method, static method, field, or type.
2. For methods, examine the signature, body, overriding, and specificity.
3. For static methods, call them through the interface that owns the method.
4. For fields/types with the same name, use qualified names.
5. Do not infer precedence from interface declaration order.

## Self-Check

How many implementations do two compatible abstract String id() methods require? What must be done for two independent default String send() methods? How should two LIMIT fields with the same name be accessed? Are LocalOptions.Policy and RemoteOptions.Policy the same type?

**Answers:** one; override to resolve; qualify with the interface name; no.
