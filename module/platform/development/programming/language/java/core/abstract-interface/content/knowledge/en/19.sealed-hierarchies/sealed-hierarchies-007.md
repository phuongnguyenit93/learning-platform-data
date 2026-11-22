# Abstract Classes That Are Both `abstract` and `sealed` or `non-sealed`

In Java, `abstract` and `sealed` / `non-sealed` solve two different problems. `abstract` governs whether a class can be instantiated directly and whether the class can leave methods unimplemented; `sealed` controls which classes are permitted to inherit directly; `non-sealed` reopens an inheritance branch that lies under a `sealed` type. Therefore, a class can be both `abstract` and `sealed`, or both `abstract` and `non-sealed`.

The examples in this article use Java 17 or later, which is the version in which sealed classes were standardized.

## 1. Meaning of Each Modifier

- **`abstract`:** `new` cannot be used to directly create an object from that class. The class can declare abstract methods and let subclasses implement them. An abstract class can still have fields, constructors, methods with bodies, and shared logic.
- **`sealed`:** restricts direct subclasses to a permitted list. This list is usually written using the `permits` clause. Each permitted subclass must declare one of the modifiers `final`, `sealed`, or `non-sealed`.
- **`non-sealed`:** applies to a direct subclass of a `sealed` type to allow that branch to continue being extended without having to list every descendant in advance.
- **`final`:** does not allow the class to have subclasses. A `final` class cannot simultaneously be `abstract` because the two purposes contradict each other.

These modifiers do not replace one another. `abstract` does not by itself restrict the inheritance hierarchy; `sealed` does not by itself make a class abstract; `non-sealed` does not require a class to be concrete.

## 2. Combining `abstract sealed`

The declaration `abstract sealed class Shape permits Circle, Group { ... }` means:

1. `Shape` cannot be instantiated directly.
2. `Shape` can contain abstract methods that concrete subclasses must implement.
3. Only the types listed in `permits` are permitted to directly inherit from `Shape`.
4. Each direct subclass must decide its inheritance branch using `final`, `sealed`, or `non-sealed`.

An `abstract sealed` class is suitable when you want to model an incomplete foundational concept while also controlling the direct types permitted to appear in the system. For example, an expression class can define the `evaluate()` contract but only allow certain known expression branches.

## 3. Combining `abstract non-sealed`

A declaration such as `abstract non-sealed class PluginNode extends Node { ... }` means that this class still cannot be instantiated directly and can leave methods abstract, but the inheritance branch from it is open. Other classes can inherit from `PluginNode` without needing to be listed in the `permits` clause of the root class `Node`.

Important condition: `non-sealed` is only valid when the class directly extends a `sealed` class or implements a `sealed` interface. `non-sealed` cannot be arbitrarily added to a class that does not lie under a sealed type.

## 4. Complete Example: A Class Hierarchy with All Three Branch Types

The following program shows an `abstract sealed` root class, an `abstract sealed` branch that continues to restrict subclasses, an `abstract non-sealed` branch that allows free extension, and a concrete `final` class.

Save all the code in `Main.java`:

```java
abstract sealed class Node
        permits NumberNode, GroupNode, ExtensionNode {
    abstract int value();
}

final class NumberNode extends Node {
    private final int number;

    NumberNode(int number) {
        this.number = number;
    }

    @Override
    int value() {
        return number;
    }
}

abstract sealed class GroupNode extends Node
        permits PairNode {
    // Can keep the abstract value() method
    // for a concrete subclass to complete.
}

final class PairNode extends GroupNode {
    private final Node left;
    private final Node right;

    PairNode(Node left, Node right) {
        this.left = left;
        this.right = right;
    }

    @Override
    int value() {
        return left.value() + right.value();
    }
}

abstract non-sealed class ExtensionNode extends Node {
    // This branch is open to arbitrary subclasses.
}

final class CustomNode extends ExtensionNode {
    private final int number;

    CustomNode(int number) {
        this.number = number;
    }

    @Override
    int value() {
        return number;
    }
}

public class Main {
    public static void main(String[] args) {
        Node number = new NumberNode(3);
        Node pair = new PairNode(
                new NumberNode(4),
                new NumberNode(5));
        Node custom = new CustomNode(10);

        System.out.println(number.value());
        System.out.println(pair.value());
        System.out.println(custom.value());
    }
}
```

Compile and run:

```text
javac Main.java
java Main
```

Standard output:

```text
3
9
10
```

In this example:

- `Node` is `abstract sealed`: it cannot be instantiated directly, has the `value()` contract, and permits only the three listed direct subclasses.
- `NumberNode` is `final`, so this branch ends.
- `GroupNode` is `abstract sealed`, so it is allowed to defer implementing `value()` and continue controlling subclasses via `permits PairNode`.
- `PairNode` is `final` and implements `value()`.
- `ExtensionNode` is `abstract non-sealed`: it can still leave methods abstract, but allows classes like `CustomNode` to continue inheriting from it.
- `CustomNode` implements `value()`, so it can be instantiated.

## 5. Compilation Rules to Remember

**Rules for `sealed`:**

- Every direct subclass of a sealed class must belong to the permitted list.
- A permitted subclass must directly extend that sealed class and must declare `final`, `sealed`, or `non-sealed`.
- Permitted types must satisfy Java's module/package rules: within the same named module, or in the same package when using an unnamed module.
- `permits` names the direct subclasses; it does not list all descendants. For example, `Node` lists `ExtensionNode`, while `CustomNode` is a descendant under the `non-sealed` branch.
- If the subclasses are declared in the same compilation unit, Java has rules to infer the permitted list in appropriate cases; writing `permits` explicitly is usually easier to read when learning.

**Rules for `abstract`:**

- An abstract class cannot be instantiated directly with `new`.
- An abstract class can keep unimplemented abstract methods. A subclass that is also abstract can continue to defer them; a concrete class must fully implement all remaining abstract methods.
- The constructor of an abstract class still runs when a subclass is instantiated. An abstract class can contain state and shared methods.
- `abstract` does not force subclasses to be abstract. A `final` or concrete `non-sealed` subclass is still valid if it fully implements the contract.

## 6. Valid and Invalid Combinations

| Declaration | Valid? | Meaning |
| --- | --- | --- |
| `abstract sealed class A permits B {}` | Yes, if `B` is a valid direct subclass | Cannot instantiate `A`; restricts direct subclasses |
| `abstract non-sealed class B extends A {}` | Yes, if `A` is sealed | Cannot instantiate `B`; opens the inheritance branch for extension |
| `sealed class A permits B {}` | Yes, if subclasses are declared according to the rules | The class can be concrete or abstract |
| `abstract final class A {}` | No | Abstract needs to be inheritable to be completed, while final forbids inheritance |
| `non-sealed class B {}` when there is no sealed parent | No | `non-sealed` only opens a branch originating from a sealed type |
| `sealed non-sealed class A {}` | No | Two modifiers controlling sealed status conflict with each other |

## 7. Which Combination to Choose in Design?

Use `abstract sealed` when the class represents an incomplete concept and you need clear control over the kinds of classes that can directly inherit from it. This approach is useful in domain models, syntax trees, expressions, messages, or event types that have a controlled set of variants.

Use `abstract non-sealed` when a branch needs to retain an abstract contract and shared behavior, while allowing another module or extension code to define additional subclasses itself. Consider the API boundary: opening a `non-sealed` branch means client code cannot assume that all descendants of that branch have been listed.

If you do not need to control the set of subclasses, a regular abstract class is usually simpler. If you need a closed hierarchy, use `sealed` and decide whether each branch should end with `final`, continue to be controlled with `sealed`, or open with `non-sealed`.

When reading a declaration like `abstract sealed` or `abstract non-sealed`, answer two separate questions: **can the class be instantiated directly and has it fully implemented its behavior?** (`abstract`) and **who is permitted to inherit from this class or continue extending the branch?** (`sealed` / `non-sealed`). The two answers combined will accurately determine the class's role in the hierarchy.
