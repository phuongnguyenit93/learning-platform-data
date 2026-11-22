# Distinguishing override, overload, and static method hiding in Java

The three mechanisms can appear together in a class hierarchy, but they differ in **how a method is selected**:

- **Override:** a subclass provides an implementation for an overridable instance method. After the signature is selected at compile time, runtime dispatch chooses the method body based on the actual object.
- **Overload:** the same name but different parameter type lists. The compiler selects the appropriate signature from the static types of the arguments and the available methods.
- **Static method hiding:** a subclass declares a static method corresponding to an inherited static method. The method is resolved according to the type at compile time, not according to the runtime object.

## 1. Comparison table

| Criteria | Override | Overload | Static hiding |
| --- | --- | --- | --- |
| Parameter list | Corresponding signature | Different parameter types/count/order | Corresponding static signature |
| Requires inheritance | Yes, or implementing an interface | Not required | Yes, with an appropriate class inheritance relationship |
| Selection | Instance body based on the runtime object | Signature based on the static type at compile time | Static method based on the type at compile time |
| Runtime polymorphism | Yes | Not for overloading itself; the selected signature can still be overridden | No |
| @Override | Recommended | Not for plain overloading | Not applicable |

Return type, modifiers, and throws do not create a new overload if the parameter list does not change. Static/instance methods with the same signature in an inheritance relationship cause an error instead of creating a special dispatch mechanism.

## 2. Combined example

~~~java
public class DispatchDemo {
    static class Base {
        String pick(Object value) { return "Base(Object)"; }
        String pick(String value) { return "Base(String)"; }
        static String kind() { return "Base"; }
    }

    static class Child extends Base {
        @Override
        String pick(Object value) { return "Child(Object)"; }

        String pick(Integer value) { return "Child(Integer)"; }
        static String kind() { return "Child"; }
    }

    public static void main(String[] args) {
        Base base = new Child();
        Child child = new Child();

        System.out.println(base.pick("hi"));
        System.out.println(base.pick(Integer.valueOf(3)));
        System.out.println(child.pick(Integer.valueOf(3)));
        System.out.println(base.kind());
        System.out.println(child.kind());
    }
}
~~~

~~~bash
javac DispatchDemo.java
java DispatchDemo
~~~

~~~text
Base(String)
Child(Object)
Child(Integer)
Base
Child
~~~

- base.pick("hi"): the compiler selects the pick(String) overload visible in Base. Child does not override this signature, so Base.pick(String) runs.
- base.pick(Integer.valueOf(3)): the Base type does not have a pick(Integer) overload, so pick(Object) is selected; runtime dispatch goes to Child.pick(Object).
- child.pick(Integer.valueOf(3)): the static type Child also has the pick(Integer) overload, so the compiler selects that signature.
- base.kind() and child.kind() select the static method based on the static type of the expression. In real code, Base.kind() and Child.kind() should be called for clarity.

## 3. Common pitfalls

**Changing parameters creates an overload:** if the parent has convert(Object) and the child only declares convert(String), the child has not implemented convert(Object); a concrete subclass may still fail to compile if the parent method is abstract.

**Overloading with null:** if both call(String) and call(Integer) exist, the call call(null) is ambiguous because neither type is more specific than the other. With call(Object) and call(String), call(null) selects String.

**Static methods are not polymorphic:** calling a static method through an object variable still uses the compile-time type of the expression. A static method in an interface is also not inherited by an implementing class like a static method of a superclass; call it via the interface name.

**Practical check:** before concluding that a method is an override, determine the static type of the receiver, the selected overload signature, and only then consider which instance method is overridden at runtime. The article on @Override covers how to have the compiler catch incorrect signature errors early.
