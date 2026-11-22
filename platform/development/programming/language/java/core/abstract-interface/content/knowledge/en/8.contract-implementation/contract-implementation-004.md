# Using an Inherited Method from a Superclass to Satisfy an Interface

## 1. Core Idea

When a class declares `implements InterfaceName`, Java requires that concrete class to have a valid implementation for every abstract method of the interface. **It is not mandatory to write the method directly inside the class declaring `implements`**: a concrete, `public` method with a compatible signature **inherited from a superclass** can also satisfy the contract.

For example, the superclass `BaseRecord` already provides `public String code()`. The subclass `Record` inherits this method and declares `implements HasCode`, so Java accepts `Record` even though the class body does not have its own `code()` method.

It is necessary to distinguish two things:

- **Having the method available:** `BaseRecord` defines `code()` and `Record` inherits the implementation.
- **Having the interface type:** only a class declared to implement `HasCode` (or inheriting from a class that already implements that interface) can be used as a `HasCode` value. The fact that the superclass happens to have a method with the same signature does not automatically turn the superclass into an implementation of the interface. Java uses the `implements` declaration, not a mechanism that automatically treats every type with all the required methods as an interface.

## 2. Runnable Java 17+ Example

Save to the file `InheritedInterfaceDemo.java`:

```java
public class InheritedInterfaceDemo {
    interface HasCode {
        String code(); // public abstract by default
    }

    static class BaseRecord {
        public String code() {
            return "BASE-001";
        }
    }

    static class Record extends BaseRecord implements HasCode {
        // Inherits BaseRecord.code(), no override needed.
    }

    static class SpecialRecord extends Record {
        @Override
        public String code() {
            return "SPECIAL-002";
        }
    }

    public static void main(String[] args) {
        HasCode first = new Record();
        HasCode second = new SpecialRecord();

        System.out.println(first.code());
        System.out.println(second.code());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 InheritedInterfaceDemo.java
java InheritedInterfaceDemo
```

Exact output:

```text
BASE-001
SPECIAL-002
```

Step-by-step explanation:

1. `HasCode.code()` is a `public abstract` method even though those two keywords are not written in the interface.
2. `BaseRecord.code()` is a `public` instance method returning `String`, matching the method required by the interface.
3. `Record extends BaseRecord implements HasCode`: the compiler finds the inherited `code()`, so `Record` is a valid concrete class without having to additionally define `code()`.
4. `SpecialRecord` overrides `code()`, so a call through a variable of type `HasCode` still selects the implementation according to the **actual object type**: `Record` prints `BASE-001`, `SpecialRecord` prints `SPECIAL-002`. This is polymorphism with dynamic dispatch.

Note: `BaseRecord` is **not** declared as `HasCode`; the statement `HasCode x = new BaseRecord();` does not compile, whereas `HasCode x = new Record();` is valid.

## 3. Conditions for an Inherited Method to Satisfy the Contract

An inherited method can take the place of implementing the interface's abstract method only if it satisfies Java's override/implement rules:

- **Matching name and parameter list:** having the same name but different parameter types or count is an overload, not an implementation of the requirement. With generics, both signature rules and *type erasure* must be considered.
- **Matching method kind:** if the interface requires an instance method, the satisfying method must be an instance method; a `static` method with the same name cannot serve as an implementation.
- **Sufficient access level:** the implementing method must be `public`, because abstract methods of an interface are `public`. A `protected` or package-private method inherited from a superclass does not meet this requirement.
- **Compatible return type:** the return type must be the same or a valid subtype (*covariant return*) according to Java rules. A method that matches only in name and parameters but has an incompatible return type will not be accepted.
- **Valid checked exceptions:** the implementing method must not declare checked exceptions broader than what the interface contract allows. Unchecked exceptions do not have this same kind of restriction.
- **Method already has a body:** for a concrete subclass, an inherited `abstract` method does not yet provide an implementation; the concrete class must still provide a valid implementation.

A `public final` method already present in the superclass **can still** satisfy the interface if the signature is compatible. `final` only prevents subclasses from overriding that method; it does not prevent using the inherited implementation to fulfill the contract.

## 4. Common Error: Superclass Method Is Not public

The following snippet **intentionally does not compile**:

```java
interface Executable {
    void execute();
}

class Base {
    protected void execute() {
        System.out.println("Run");
    }
}

class Job extends Base implements Executable {
    // Error: the inherited execute() is only protected,
    // whereas Executable.execute() requires public.
}
```

`protected` allows subclasses to access the method, but it is **not** sufficient to implement the `public` contract of the interface. It can be fixed by overriding it with `public` access:

```java
class Job extends Base implements Executable {
    @Override
    public void execute() {
        super.execute();
    }
}
```

In the fixed version, `Job.execute()` is the `public` entry point satisfying `Executable`; `super.execute()` still reuses the superclass's logic. The two code blocks in this section illustrate the error and the fix, not standalone programs with `main`.

Some similar pitfalls:

- The superclass has `static void execute()` while the interface requires `void execute()`: a static method cannot fulfill an instance contract.
- The superclass has `public void execute(int n)` but the interface requires `void execute()`: the parameters differ, so it does not satisfy the requirement.
- The superclass only declares `public abstract void execute()`: the concrete subclass still needs to implement it.
- The superclass has a `private` method with the same name: a private method is not inherited by the subclass as a method that can be overridden to satisfy the interface.

## 5. What If the Interface Has a default Method?

The **class wins** rule: when a superclass provides a suitable inherited instance method, it takes precedence over a `default` method with the same signature from the interface. This is intentional behavior, allowing a default method to be added to an interface without unexpectedly replacing the existing logic of the superclass.

Save the following snippet to the file `ClassWinsDemo.java`:

```java
public class ClassWinsDemo {
    interface Greeter {
        default String greet() {
            return "from interface";
        }
    }

    static class Parent {
        public String greet() {
            return "from parent";
        }
    }

    static class Child extends Parent implements Greeter {
    }

    public static void main(String[] args) {
        Child child = new Child();
        Greeter asInterface = child;

        System.out.println(child.greet());
        System.out.println(asInterface.greet());
    }
}
```

Run `javac -encoding UTF-8 ClassWinsDemo.java`, then `java ClassWinsDemo`. Output:

```text
from parent
from parent
```

Even though the second reference has type `Greeter`, the method invoked is still the implementation inherited from `Parent`. If the subclass validly overrides `greet()`, the overriding implementation is called instead.

## 6. When Should You Leverage an Inherited Method?

This approach is suitable when the superclass already has an implementation that matches the semantics of the interface and you want the subclass to clearly declare the contract without duplicating code. For example, a superclass already has a reliable `id()` operation, while the subclass needs to be passed into an API that accepts the `Identifiable` interface.

When evaluating the design, ask yourself:

1. Does the inherited method have the exact **meaning** promised by the interface, or does it merely happen to share the same signature?
2. Does the method fully satisfy `public` access, signature, return type, and checked exceptions?
3. Will changes in the superclass alter the behavior of the subclasses implementing the interface?
4. If a subclass needs its own behavior, should it explicitly override the method rather than inheriting it as-is?

**Remember:** `implements` establishes a commitment regarding type and contract; a suitable `public` method inherited from a superclass can fulfill that commitment. Java checks validity at compile time and selects the implementation matching the actual object at runtime.
