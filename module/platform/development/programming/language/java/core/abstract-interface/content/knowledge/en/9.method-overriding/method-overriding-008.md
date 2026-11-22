# The Role of @Override in Detecting Incorrect Method Signatures

@Override expresses the intent that a method is overriding or implementing a valid method from a supertype. The compiler checks this assertion. The annotation does not change runtime dispatch; its value is catching errors when a declaration is not what the programmer intended.

## 1. Common Mistake: Accidentally Creating an Overload

~~~java
class Parent {
    public void send(String text) {
        System.out.println("Parent: " + text);
    }
}

class Child extends Parent {
    public void send(Object text) {
        System.out.println("Child: " + text);
    }
}
~~~

send(Object) does not override send(String) because the parameter types differ. With Parent ref = new Child(); ref.send("hello"); the result is still Parent: hello.

If you write:

~~~java
class Child extends Parent {
    @Override
    public void send(Object text) {
        System.out.println("Child: " + text);
    }
}
~~~

the compiler reports that the method does not override/implement a method from a supertype. When the intent is to override send(String), fix the parameter to match and keep @Override.

## 2. Signatures and Easily Confused Changes

| Change in subclass | Does it create an override? |
| --- | --- |
| Changing the method name | No |
| Changing the number or types of parameters | No, usually creates an overload |
| Changing only parameter variable names | It can; variable names are not part of the signature |
| Changing only the return type | Does not create an overload; the return type must be compatible when overriding |
| Changing only throws | Does not create an overload; checked exceptions are still checked |
| Declaring the same signature as a static or private method of the parent | Not an override |
| Implementing an interface method | Can use @Override |

With generics, signatures must be evaluated according to type specialization and subsignature rules, not just by comparing the two declaration lines verbatim. Base&lt;T&gt;.accept(T) can be overridden by accept(String) when a subclass inherits from Base&lt;String&gt;.

## 3. Valid Examples with Classes and Interfaces

~~~java
interface Printer {
    void print(String message);
}

class ConsolePrinter implements Printer {
    @Override
    public void print(String message) {
        System.out.println("In: " + message);
    }
}

class Animal {
    public Number amount() { return 1; }
    public void greet(String value) { }
}

class Dog extends Animal {
    @Override
    public Integer amount() { return 7; } // Covariant return
    public void greet(Object value) { }   // New overload, not using @Override
}
~~~

@Override can be used both when implementing an interface and when overriding a method from a class, including public methods of Object such as toString(), equals(Object), and hashCode().

## 4. What the Annotation Does Not Do

- Does not allow overriding final, private, or static methods.
- Does not bypass visibility, return type, or checked exception rules.
- Does not prove that the method body has correct business logic or that tests are sufficient.
- Does not control runtime dispatch.

@Override has SOURCE-level retention, serving compile-time checking. When the compiler reports “does not override or implement”, check the name, parameter type list, extends/implements relationship, and modifiers of the parent method. Do not remove the annotation to make the error disappear; first verify that you actually want to override rather than create a new overload.
