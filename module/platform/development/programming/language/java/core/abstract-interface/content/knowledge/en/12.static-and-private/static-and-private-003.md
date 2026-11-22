# Static methods are not inherited by subinterfaces or implementing classes

A static method declared in an interface belongs to that interface. The `extends` relationship between interfaces and `implements` between a class and an interface **do not make a static method an inherited member**. This rule differs from class static methods, which can be inherited and hidden by subclasses according to their own rules.

## 1. Subinterfaces inherit default methods but do not inherit static methods

~~~java
interface ParentApi {
    static String version() {
        return "parent";
    }

    default String greet() {
        return "hello";
    }
}

interface ChildApi extends ParentApi {
    static String version() {
        return "child";
    }
}

final class ApiImpl implements ChildApi {
    static String version() {
        return "class";
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println(ParentApi.version());
        System.out.println(ChildApi.version());
        System.out.println(ApiImpl.version());

        ParentApi api = new ApiImpl();
        System.out.println(api.greet());
    }
}
~~~

Compile on JDK 8 or later using `javac -encoding UTF-8 --release 8 Main.java` and run `java Main`. Stdout:

~~~text
parent
child
class
hello
~~~

`ChildApi.version` is a new static method declared by `ChildApi`; it does not override `ParentApi.version`. Similarly, `ApiImpl.version` is a class method, independent of the interface static methods. The three calls are selected according to the type name on the left side of the dot.

In contrast, `greet` is a default instance method inherited from `ParentApi`. The call `api.greet()` is valid because it goes through an object implementing the interface.

If `ChildApi` does not declare `version` itself, the expression `ChildApi.version()` will be invalid. `ParentApi.version()` must be called using the exact name of the interface that declares the method.

## 2. Implementing classes do not have to implement static methods

An implementing class only has to provide the missing abstract instance methods. An interface static method does not create an implementation obligation, nor is it inherited by the class as a method of the class itself.

~~~java
interface Codec {
    static String encode(String value) {
        return "[" + value + "]";
    }

    String decode(String text);
}

final class BracketCodec implements Codec {
    @Override
    public String decode(String text) {
        return text.substring(1, text.length() - 1);
    }
}
~~~

`Codec.encode("Java")` is valid. The following calls are invalid if `BracketCodec` does not declare a corresponding method itself:

~~~java
// BracketCodec.encode("Java");
// new BracketCodec().encode("Java");
// Codec codec = new BracketCodec();
// codec.encode("Java");
~~~

Do not confuse the error at `BracketCodec.encode` with an access permission error: the `Codec.encode` method is public, yet it is still not inherited into the class. Access permissions and inheritance rules are two different issues.

## 3. A static method with the same name is not an override

A subinterface or implementing class can declare its own static method with the same name as a static method of a parent interface as long as it does not conflict with an inherited instance method. These static declarations are independent. Do not use `@Override` to mark them.

~~~java
interface Root {
    static int parse(String value) {
        return Integer.parseInt(value);
    }
}

interface StrictRoot extends Root {
    static int parse(String value) {
        return Root.parse(value) + 1;
    }
}
~~~

`Root.parse("10")` returns `10`, whereas `StrictRoot.parse("10")` returns `11`. The method in the subinterface defines its own behavior; it does not replace the method in the parent interface.

There is an important boundary: if the parent interface already has a default or abstract instance method with a given signature, the subinterface cannot declare a static method with the same signature to replace the inherited instance method. Static and instance methods cannot be mixed as if they were the same extension point.

## 4. Comparison with class static methods

~~~java
class Base {
    static String kind() {
        return "base";
    }
}

class Derived extends Base {
}
~~~

`Derived.kind()` is valid because a subclass can inherit a suitable static method from the superclass. If the subclass declares a corresponding static method, that is *method hiding*, not polymorphic overriding.

For interfaces, static methods are not inherited down to subinterfaces or implementing classes. Also, do not generalize that all static members follow the same rules: interface fields are `public static final` and can be inherited according to the rules that apply to fields, whereas static methods cannot.

| Case | Rule |
|---|---|
| Subclass inherits a static method from a parent class | Possible; a method with the same signature in the subclass can hide the parent method |
| Subinterface inherits a static method from a parent interface | No |
| Implementing class inherits a static method from an interface | No |
| Subinterface inherits a default instance method | Yes, according to inheritance and conflict-resolution rules |
| Implementing class must override an interface static method | No |

**Self-check**

- Can `ChildApi.version()` call a method declared only in `ParentApi`? **No.**
- Does an implementing class have to implement static methods of an interface? **No.**
- If a subtype declares a static method with the same name itself, does it override the parent interface's method? **No; it is a separate declaration.**
