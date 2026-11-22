# Protected Object.clone() and an Interface's Public Requirement

Object.clone() has protected access. An interface can declare clone() as a public method, but an implementing class must provide an appropriate public implementation; the protected method inherited from Object does not satisfy the interface's public contract.

## 1. Access Scope of Object.clone()

The base signature has the form:

~~~java
protected native Object clone() throws CloneNotSupportedException;
~~~

- **protected** is a compile-time access rule. Code in the same package can access it under package rules; subclasses can access it under protected conditions. Code outside the package cannot arbitrarily call someObject.clone().
- **native** indicates that the implementation comes from the runtime rather than an ordinary Java body.
- **CloneNotSupportedException** is a checked exception that the method can throw when the object does not support the default cloning mechanism.
- **Object** is the return type of the original method. An override can use a more specific return type according to the covariant return type rule.

A compile-time access error differs from CloneNotSupportedException at runtime. A call can be rejected because the caller does not have access permission, or the caller has access permission but the cloning mechanism is not supported.

## 2. An Interface Requires a Public Method

Regular methods in an interface are public by default. An interface does not have protected methods:

~~~java
interface PublicClone {
    Object clone() throws CloneNotSupportedException;
}
~~~

Even without writing the public modifier, clone() in PublicClone is still public. If a class only inherits protected Object.clone(), it does not yet satisfy the public method required by PublicClone. The class must override clone() as public; Java allows widening access when overriding, but does not allow narrowing the access of a public method.

~~~java
interface PublicClone {
    Object clone() throws CloneNotSupportedException;
}

class InvalidNote implements PublicClone {
    // Invalid: inherited Object.clone() is still protected.
    // The class must provide an appropriate public implementation.
}
~~~

The name clone is not forbidden in an interface. The issue is that the implementation's visibility must satisfy the public contract.

## 3. Complete Example

~~~java
public class InterfaceCloneDemo {
    interface PublicClone {
        Object clone() throws CloneNotSupportedException;
    }

    static final class Note implements PublicClone, Cloneable {
        private final String text;

        Note(String text) {
            this.text = text;
        }

        @Override
        public Note clone() throws CloneNotSupportedException {
            return (Note) super.clone();
        }

        String text() {
            return text;
        }
    }

    public static void main(String[] args) throws CloneNotSupportedException {
        Note original = new Note("Java");
        PublicClone publicView = original;
        Note copy = original.clone();
        Object throughInterface = publicView.clone();

        System.out.println(copy.text());
        System.out.println(original == copy);
        System.out.println(throughInterface.getClass().getSimpleName());
    }
}
~~~

Output:

~~~text
Java
false
Note
~~~

Note declares public clone(), returns Note using a covariant return type, and calls super.clone(). PublicClone allows the caller to call clone() through a variable of the interface type. Cloneable is a separate mechanism: it allows the default Object.clone() to create a copy; it does not make clone public and does not declare a clone() method.

## 4. Visibility and Cloning Capability Are Not the Same

| Case | Result |
| --- | --- |
| Class implements Cloneable but does not override clone() | Compiles; inherited method remains protected |
| Interface requires public clone(), class only inherits protected clone() | Does not satisfy the interface contract |
| Class overrides clone() as public and supports Cloneable | Can expose clone publicly; default super.clone() creates a copy |
| Class has public clone() calling super.clone() but does not support Cloneable | Can compile, but the Object.clone() mechanism throws CloneNotSupportedException |
| Class does not use Object.clone() and writes its own clone() method | Behavior depends on the implementation defined by the class |

Cloneable is an empty marker interface. Therefore, a variable of type Cloneable cannot call clone() through that interface itself. If an API needs a polymorphic copy operation, define an interface with a copy() method that has clear semantics.

## 5. Shallow Copy and API Choices

By default, Object.clone() copies field values. Primitive fields have their values copied; reference fields copy the reference, so internal mutable objects can be shared between the original and the clone. Public visibility does not make a copy a deep copy.

~~~java
class Profile implements Cloneable {
    StringBuilder label = new StringBuilder("Java");

    @Override
    public Profile clone() throws CloneNotSupportedException {
        return (Profile) super.clone();
    }
}
~~~

The two Profile instances after cloning are two different objects, but they can share the StringBuilder. If independent state is needed, the implementation must explicitly copy the mutable fields. A copy constructor or static factory often expresses intent better and can re-run validation in the constructor.

References:
- [Java SE 17 API: Object.clone()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone())
- [Java SE 17 API: Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html)
- [JLS 17 §9.4: Interface Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4)
- [JLS 17 §8.4.8: Overriding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8)

Self-check:
- Does Cloneable declare clone()? No.
- Can an interface require protected clone()? No; regular interface methods are public.
- Why does public clone() not guarantee a deep copy? Because Object.clone() shallow-copies the fields.
