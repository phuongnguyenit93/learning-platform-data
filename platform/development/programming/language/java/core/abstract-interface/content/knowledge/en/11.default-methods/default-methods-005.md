# Inheriting Default Methods Through a Subinterface in Java

When a subinterface `extends` a superinterface, it inherits the eligible methods of the superinterface, including default methods. If the subinterface does not redeclare the method, an implementing class can use that default across multiple levels of inheritance.

## 1. Inheriting As-Is

```java
public class DefaultInheritanceDemo {
    interface Greeter {
        default String greet(String name) {
            return "Hello, " + name;
        }
    }

    interface NamedGreeter extends Greeter {
        String kind();
    }

    static final class ConsoleGreeter implements NamedGreeter {
        @Override
        public String kind() {
            return "console";
        }
        // greet(String) is inherited.
    }

    public static void main(String[] args) {
        NamedGreeter greeter = new ConsoleGreeter();
        System.out.println(greeter.greet("Java"));
        System.out.println(greeter.kind());
    }
}
```

Output:

```text
Hello, Java
console
```

`NamedGreeter` does not need to redeclare `greet`. `ConsoleGreeter` only implements the abstract method `kind`, yet `greet` can still be called on a reference of type `NamedGreeter`.

## 2. Subinterface Provides a New Default

A subinterface can override a default method with another default method. The subinterface's version is selected because it lies on a more specific branch.

```java
interface BasicLabel {
    default String label() {
        return "base";
    }
}

interface DetailedLabel extends BasicLabel {
    @Override
    default String label() {
        return BasicLabel.super.label() + "-detailed";
    }
}

final class Service implements DetailedLabel {
}
```

`new Service().label()` returns `base-detailed`. In this example, the subinterface changes the default behavior for its entire branch. The `BasicLabel.super.label()` syntax is used right where the subinterface directly inherits from `BasicLabel`; the detailed conditions for this syntax are discussed separately in the article on qualified super calls.

## 3. Multiple Superinterfaces

If a subinterface inherits two default methods with the same signature from two superinterfaces with no specificity relationship, Java does not automatically choose one. The subinterface needs to override the method to decide the behavior, or redeclare it as abstract to require implementing classes to provide an implementation.

```java
interface Left {
    default String side() { return "left"; }
}

interface Right {
    default String side() { return "right"; }
}

interface Combined extends Left, Right {
    @Override
    default String side() {
        return Left.super.side() + " + " + Right.super.side();
    }
}

final class CombinedImpl implements Combined {
}
```

`new CombinedImpl().side()` returns `left + right`. If there is no override in `Combined`, the two competing default methods will cause a compilation error. There is no rule that prioritizes the interface listed first.

When a subinterface overrides a superinterface's default, the implementing class receives the more specific version. If two unrelated interfaces both declare competing defaults, the conflict must be resolved explicitly. If the class/superclass has a matching concrete instance method, the class method can take precedence.

## 4. Choosing a Design Approach

- **Do not redeclare:** keep the superinterface's default.
- **Override with a new default:** provide a different shared behavior for the subinterface branch.
- **Redeclare as abstract:** forgo inheriting the implementation for that signature and require a suitable implementation. This case has its own conditions and consequences, explained in the article on re-abstraction.

These options apply per signature; redeclaring one method does not make the superinterface's other default methods disappear.

## Self-Check

1. Does a class that only implements a subinterface need to re-implement every default method from its superinterface?
2. Why does a subinterface's default method win over the default from the superinterface it overrides?
3. How does Java handle it when two independent superinterfaces both provide a default method with the same signature?
4. Does the order of interfaces in the `implements` clause determine which one wins?

**Remember:** A subinterface can keep the superinterface's default as-is, provide a new default, or require an explicit implementation. When there are multiple method sources, specificity relationships, conflicts, and concrete methods inherited from a class must be considered.
