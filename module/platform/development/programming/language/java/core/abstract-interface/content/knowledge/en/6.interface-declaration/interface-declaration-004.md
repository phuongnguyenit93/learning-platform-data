# Interfaces Extending One or More Interfaces with extends

## 1. Syntax and Subtype Relationship

An interface uses `extends` to inherit from one or more interfaces. The list of superinterfaces is separated by commas:

```java
interface Identified {
    String id();
}

interface Named {
    String name();
}

interface CatalogEntry extends Identified, Named {
    String category();
}
```

`CatalogEntry` inherits the contracts of `Identified` and `Named`, while also adding `category()`. A value of type `CatalogEntry` can also be used through the type `Identified` or `Named`. This is a subtype relationship; no object copy is created.

An interface cannot `extends` a class, and Java prohibits inheritance cycles. The syntax `interface Child implements Parent` is incorrect; `implements` is used in class declarations.

## 2. Which Members Are Inherited?

| Superinterface member | Main rule |
| --- | --- |
| Abstract instance method | Becomes part of the subinterface contract; a concrete class must satisfy it if no valid implementation exists yet. |
| `default` instance method | Can be inherited along with its implementation, unless overridden or there is a conflict. |
| `public static final` constant field | Can be referenced through the subinterface, though duplicate names can be ambiguous. |
| `static` method | Not inherited as a method of the subinterface; invoke it through the name of the interface that declares it. |
| `private` method | An internal helper of the declaring interface; not inherited. |

The inheritance relationship is transitive. If `Leaf extends Middle` and `Middle extends Root`, a class implementing `Leaf` must also satisfy the remaining abstract contracts of `Middle` and `Root`.

## 3. Compatible Abstract Declarations

Two superinterfaces can declare abstract methods with the same signature:

```java
interface Reader {
    String read();
}

interface TextSource {
    String read();
}

interface ReadableText extends Reader, TextSource {}

final class FileText implements ReadableText {
    @Override
    public String read() {
        return "hello";
    }
}
```

One `public String read()` implementation satisfies both contracts. Return types must also be compatible according to Java rules. For example, a method returning `Integer` can satisfy compatible declarations returning `Integer` and `Number` within the same hierarchy. Conversely, `String get()` and `Integer get()` cannot be distinguished by return type alone; an incompatible combination causes a compilation error.

With generic interfaces, type arguments are applied throughout the inheritance chain. Inheriting the same generic interface with incompatible type arguments may be rejected due to type conflicts or type erasure.

## 4. Default Method Conflicts

Two unrelated interfaces can both declare a `default` method. The subinterface must resolve the conflict rather than letting Java choose arbitrarily.

```java
interface Left {
    default String label() {
        return "left";
    }
}

interface Right {
    default String label() {
        return "right";
    }
}

interface Combined extends Left, Right {
    @Override
    default String label() {
        return Left.super.label() + "/" + Right.super.label();
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println(new Choice().label());
    }
}

final class Choice implements Combined {}
```

Output:

```text
left/right
```

`Left.super.label()` and `Right.super.label()` explicitly invoke the implementation from the appropriate direct superinterface. Another approach is to redeclare `String label();` in `Combined` to force a concrete class to provide an implementation. If a subinterface is a more specific branch and overrides a parent's default method, the specialized implementation can take precedence according to Java rules; a valid instance method from a class can also win over a default method.

## 5. Misconceptions to Avoid

- `extends A, B` uses a comma, not `&`, in the superinterface list.
- A parent's `static` method does not become `Child.staticMethod()`.
- A `private` helper is not part of the contract that an implementing class provides.
- A concrete class implementing a subinterface must still satisfy the inherited abstract methods.
- A `sealed interface` (Java 17+) can restrict the permitted direct subtypes; it does not change the fundamental principles of `extends`.

**Self-check:** If `Combined extends Left, Right` and both parents have a default method with the same signature, is an empty subinterface declaration always valid? No; overriding or redeclaring an abstract method is required when the conflict is not resolved by the inheritance rules.
