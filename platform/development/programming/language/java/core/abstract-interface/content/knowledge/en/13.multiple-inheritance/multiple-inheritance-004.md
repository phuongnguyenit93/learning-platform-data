# Precedence of Concrete Methods Inherited from a Superclass in Java

If a superclass provides a concrete instance method matching an interface's default method, the method from the class takes precedence. This rule is commonly called **class wins**.

~~~java
class Speaker {
    public String describe() { return "class"; }
}
interface Audible {
    default String describe() { return "interface"; }
    default String channel() { return "default channel"; }
}
final class SmartSpeaker extends Speaker implements Audible {}

public class Main {
    public static void main(String[] args) {
        SmartSpeaker speaker = new SmartSpeaker();
        Audible view = speaker;
        System.out.println(speaker.describe());
        System.out.println(view.describe());
        System.out.println(speaker.channel());
    }
}
~~~

Output:

~~~text
class
class
default channel
~~~

Speaker.describe() wins over Audible.describe(). Because the superclass does not have channel(), the class inherits the interface's default. The Audible reference type does not force the instance call to use the default when the class already has a matching method.

Not just any method with the same name is sufficient. Check the signature, return type, visibility, and checked exceptions. A protected method does not automatically satisfy an interface contract requiring public; nor is a static or private method a corresponding instance implementation.

A superclass with an abstract method creates a different situation: the concrete subclass must still fulfill the abstract obligation. If it needs to use the default, it can explicitly override it and call Status.super.status() when Status is an appropriate direct superinterface.

## Self-Check

A superclass has public String name() and an interface has default String name(): which body runs? What if the superclass has no corresponding method, but the interface has a default? Does a protected method satisfy public?

**Answer:** superclass; the default can be used; no.
