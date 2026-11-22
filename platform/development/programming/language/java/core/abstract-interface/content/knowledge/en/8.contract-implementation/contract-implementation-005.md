# One Method Satisfying Multiple Interfaces with the Same Signature

In Java, a class can `implements` multiple interfaces that all require a method. When the declarations have compatible signatures, **a single instance method in the class (or inherited from a superclass) can satisfy all of those contracts**. There is no need, and it is not possible, to write two method bodies that differ only in the interface that “owns” the method.

The conditions do not stop at the name and parameters: the shared method must also be compatible with all return types, checked exceptions, access levels, and behavioral semantics required by each interface.

## 1. Basic Example: Two Interfaces, One Method

Create the file `SharedMethodDemo.java` (Java 17+):

```java
interface Describable {
    String code();
}

interface Trackable {
    String code();
}

final class Asset implements Describable, Trackable {
    private final String code;

    Asset(String code) {
        this.code = code;
    }

    @Override
    public String code() {
        return code;
    }
}

public class SharedMethodDemo {
    public static void main(String[] args) {
        Asset asset = new Asset("asset-42");
        Describable described = asset;
        Trackable tracked = asset;

        System.out.println("Describable: " + described.code());
        System.out.println("Trackable: " + tracked.code());
        System.out.println("Direct: " + asset.code());
    }
}
```

Compile and run:

```bash
javac SharedMethodDemo.java
java SharedMethodDemo
```

```text
Describable: asset-42
Trackable: asset-42
Direct: asset-42
```

`Describable.code()` and `Trackable.code()` both declare `String code()`. The single `public String code()` method in `Asset` satisfies both. The two interface-typed variables reference the same `Asset` object, so calls through each variable go to that same implementation body. The `@Override` annotation is used once so the compiler checks the contract.

The interface reference type determines which methods are allowed to be called at compile time; the class of the object at runtime determines which implementation is called. There are not two independent “copies” of `code()` just because there are two interfaces.

## 2. Same Signature vs. Same Return Type

For ordinary methods, the signature (`method signature`) is based on the **method name and parameter type list**, along with additional rules for generic methods. Parameter variable names do not affect the signature. The return type and the `throws` clause do not create a new overload.

| Declarations in Two Interfaces | Conclusion |
| --- | --- |
| `void save(String id)` and `void save(String key)` | Same signature; a single `public void save(String)` can satisfy both. |
| `String find(int id)` and `String find(int id)` | One matching method can implement both. |
| `Number value()` and `Integer value()` | Can use `Integer value()` thanks to a covariant return type. |
| `void send(String s)` and `void send(int n)` | Different signatures; two overloads are required if the class implements both. |
| `String value()` and `Integer value()` | No return type is compatible with both of these declarations. |
| `int count()` and `long count()` | Cannot use a single override to satisfy both primitive return types. |

**Covariant return types** allow an overriding method to return a reference subtype of the type declared in the contract. A runnable example in `CovariantReturnDemo.java`:

```java
interface NumericValue {
    Number value();
}

interface IntegralValue {
    Integer value();
}

final class NumberItem implements NumericValue, IntegralValue {
    @Override
    public Integer value() {
        return 42;
    }
}

public class CovariantReturnDemo {
    public static void main(String[] args) {
        NumberItem item = new NumberItem();
        NumericValue n = item;
        IntegralValue i = item;
        System.out.println(n.value());
        System.out.println(i.value());
    }
}
```

```bash
javac CovariantReturnDemo.java
java CovariantReturnDemo
```

```text
42
42
```

Because `Integer` is a subtype of `Number`, `Integer value()` is compatible with both. Conversely, you cannot write two methods `String value()` and `Integer value()` in the same class just to distinguish between interfaces: Java does not overload on return type.

## 3. Access Level and Checked Exceptions Must Also Be Compatible

An ordinary abstract method in an interface has `public` access by default. The implementing method must be an appropriate `public` instance method; omitting `public` to make it package-private, using `protected`, or making it `static` fails to satisfy that instance contract.

For checked exceptions, the implementing method must have a valid `throws` declaration **for each interface**. If one interface allows `IOException` while the other allows only `SQLException`, the shared method can declare no checked exceptions at all.

Example `CompatibleThrowsDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

interface FileAction {
    void run() throws IOException;
}

interface DatabaseAction {
    void run() throws SQLException;
}

final class UnifiedAction implements FileAction, DatabaseAction {
    @Override
    public void run() {
        System.out.println("finished");
    }
}

public class CompatibleThrowsDemo {
    public static void main(String[] args) {
        new UnifiedAction().run();
    }
}
```

```bash
javac CompatibleThrowsDemo.java
java CompatibleThrowsDemo
```

```text
finished
```

`UnifiedAction.run()` declares no checked exceptions, so it does not violate either one. If that method declares `throws IOException`, it is no longer compatible with `DatabaseAction.run()`, because `IOException` is not a subtype of `SQLException`. Unchecked exceptions such as `RuntimeException` have different rules.

One important detail: if you call `run()` through a variable with static type `FileAction` or `DatabaseAction`, the compiler still checks the `throws` clause in the declaration of **that variable's type**, even though the concrete `UnifiedAction` implementation declares no checked exceptions.

## 4. Conflicting Default Methods: Forced to Choose or Combine Implementations

Two `abstract` declarations with the same signature can both be satisfied by a single method. However, when **two independent interfaces both provide a `default` method with the same signature**, Java does not automatically choose one of the two method bodies.

Example `DefaultConflictDemo.java`:

```java
interface LeftTitle {
    default String title() {
        return "Left";
    }
}

interface RightTitle {
    default String title() {
        return "Right";
    }
}

final class CombinedTitle implements LeftTitle, RightTitle {
    @Override
    public String title() {
        return LeftTitle.super.title() + " & " + RightTitle.super.title();
    }
}

public class DefaultConflictDemo {
    public static void main(String[] args) {
        System.out.println(new CombinedTitle().title());
    }
}
```

```bash
javac DefaultConflictDemo.java
java DefaultConflictDemo
```

```text
Left & Right
```

Removing the overriding method in `CombinedTitle` will cause a compile-time error about conflicting default methods. The syntax `LeftTitle.super.title()` and `RightTitle.super.title()` explicitly invokes the two default implementations from the direct superinterfaces. This is one option; the class can also write an entirely new `title()` logic on its own.

Another case is a **concrete method inherited from a superclass**. A compatible `public` method of the superclass can implement the interface and usually takes precedence over a default method (`class wins`):

```java
class ParentTitle {
    public String title() {
        return "class";
    }
}

interface Titled {
    default String title() {
        return "interface";
    }
}

final class ChildTitle extends ParentTitle implements Titled {
}

public class ClassMethodPriorityDemo {
    public static void main(String[] args) {
        System.out.println(new ChildTitle().title());
    }
}
```

Save in `ClassMethodPriorityDemo.java`, then run:

```bash
javac ClassMethodPriorityDemo.java
java ClassMethodPriorityDemo
```

```text
class
```

`ChildTitle` does not need to declare `title()` because the compatible method from `ParentTitle` is inherited and satisfies the `Titled` contract.

## 5. Distinguishing This from Overloading and Generics

The following two interfaces do **not** have the same signature:

```java
interface TextSink {
    void send(String value);
}

interface NumberSink {
    void send(int value);
}

final class MixedSink implements TextSink, NumberSink {
    @Override
    public void send(String value) {
        System.out.println("text=" + value);
    }

    @Override
    public void send(int value) {
        System.out.println("number=" + value);
    }
}
```

This is a code snippet illustrating classes and interfaces, without a standalone `main` method. `MixedSink` must have two overloads because the parameters are `String` and `int`, respectively. Java selects the overload matching the call at compile time.

With generics, you must analyze the method after substituting type parameters and consider the `erasure`/`override-equivalent` rules. For example, `interface Handler<T> { void handle(T v); }` implemented as `Handler<String>` requires `handle(String)`. Conversely, `List<String>` and `List<Integer>` both erase to `List`; two declarations having the same erasure can cause a name clash or require using raw types with type-safety warnings. Therefore, do not infer that “one method satisfies both” just by looking at the name after erasure.

Interface `static` and `private` methods are not abstract instance methods that a class that `implements` the interface must override. Do not confuse a matching name with having implemented the contract.

## 6. Matching Signatures Do Not Guarantee Correct Contract Semantics

Suppose `Auditable` requires `save(String id)` to record an audit event, while `Persistable` requires that very same signature to save data persistently. Java may accept a single `save(String)` method at the type level, but a body that only performs auditing will **not** fulfill the behavior that `Persistable` promises.

When unifying implementations, you must clarify the input conditions, side effects, exceptions, and postconditions of *every* interface. If the behavioral requirements conflict, you should revisit the interface design or separate the responsibilities; the compiler cannot resolve this semantic conflict on its own.

## 7. Verification Process and Common Mistakes

1. Place the interface declarations side by side and compare the method names and parameter types, including generics after type substitution.
2. Verify that a single return type satisfies all of them; do not try to distinguish methods by return type.
3. Verify that `public`, instance method, and checked `throws` are compatible with every interface.
4. Determine whether the declarations are abstract or default; if two default implementations conflict, write an explicit override.
5. Check whether a superclass already has a compatible concrete method.
6. Call the method through each interface type and write tests for the behavior promised by each contract.

Common mistakes include writing a package-private method, declaring a checked exception allowed by only one interface, forgetting to override when two default methods conflict, or assuming that two methods with different return types are two overloads.

**Exercise:** Create `EventPublisher` and `AuditPublisher` that both declare `void publish(String message)`. Have `ConsolePublisher` implement both with a single `public` method. Call it through two interface variables and explain why the same body is executed. Then add `default String channel()` to both interfaces with two different values; resolve the conflict yourself with an override and run `javac` to verify.

**Remember:** One implementation can fulfill multiple interface contracts with the same signature; the return type, checked exceptions, and behavior must together satisfy the contracts. Two conflicting default methods must be resolved explicitly, while a compatible `public` method inherited from a superclass may already be enough to satisfy the interface.
