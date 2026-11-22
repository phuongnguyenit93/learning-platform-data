# How to Determine Abstract Methods Inherited from Superinterfaces

In Java, an interface can `extends` multiple interfaces. When it does, the subinterface inherits member methods from the entire superinterface hierarchy, including those declared in more distant ancestor interfaces. To know which methods a concrete class must implement, you need to examine method signatures, inheritance relationships, return types, and `default` methods that already have a body. You cannot simply count the declaration lines with the `abstract` keyword.

## 1. Which Methods in an Interface Are Abstract?

An instance method declared in an interface without a body is usually implicitly `public abstract`. Therefore, the following two declarations are equivalent in meaning:

```java
interface Reader {
    String read();
}
```

and

```java
interface Reader {
    public abstract String read();
}
```

Method types to distinguish:

- **Abstract method:** has no body; a concrete class must provide a suitable implementation, unless a valid implementation is already inherited from a superclass or an appropriate `default` method.
- **Default method:** has a body and is inherited as an instance implementation. A class can use it directly or override it.
- **Static method:** belongs to the declaring interface itself; it is not inherited as an instance method and does not create an implementation obligation for a class.
- **Private method:** serves only inside the declaring interface and is not a method inherited by subinterfaces.

In an interface, an instance method that has no body and is not declared `private` or `default` is abstract according to Java's rules, even when the `abstract` keyword is not written.

## 2. Determining Obligations Across the Entire Interface Tree

Read from the interface under consideration and trace all direct and indirect superinterfaces. For example:

```java
interface HasId {
    String id();
}

interface HasName {
    String name();
}

interface Person extends HasId, HasName {
}
```

`Person` declares no methods directly, yet it still inherits two abstract methods:

- `String id()` from `HasId`.
- `String name()` from `HasName`.

A concrete class implementing `Person` must fulfill both obligations. The following standalone program runs on Java 17 and above:

```java
interface HasId {
    String id();
}

interface HasName {
    String name();
}

interface Person extends HasId, HasName {
}

final class User implements Person {
    @Override
    public String id() {
        return "u-1";
    }

    @Override
    public String name() {
        return "An";
    }
}

public class Main {
    public static void main(String[] args) {
        Person person = new User();
        System.out.println("id=" + person.id());
        System.out.println("name=" + person.name());
    }
}
```

Save the code to `Main.java`, then run:

```text
javac Main.java
java Main
```

Expected output:

```text
id=u-1
name=An
```

The file name must be `Main.java` because the `public` class is `Main`. If `User` is missing either method, the compiler reports an error because the concrete class has not fully fulfilled the contract of `Person`.

## 3. Grouping Declarations with the Same Signature

Multiple superinterfaces can declare the same method. If the declarations are compatible and represent the same method signature, a class only needs one implementation to satisfy them; there is no need to create a separate method for each interface.

```java
interface A {
    void reset();
}

interface B {
    void reset();
}

interface C extends A, B {
}

final class Device implements C {
    @Override
    public void reset() {
        System.out.println("reset");
    }
}
```

`C` inherits two declarations of `reset()`, but a single `public void reset()` method in `Device` satisfies both.

When comparing methods, pay attention to the following:

- The name and parameter type list determine the signature; the return type does not create a new overload.
- Two methods `m(int)` and `m(String)` have different signatures, so they can create two separate obligations.
- Two methods with the same name and the same parameter types but incompatible return types cannot be handled by having two methods that differ only in return type. Java does not allow overloading solely by return type.
- The `throws` clause does not create a different signature. When overriding, the declared checked exception types must follow the rules of the overridden method, typically keeping the same or narrowing the scope of permitted exceptions.
- With generics, you must examine the types substituted in the inheritance context, not merely compare the literal type names in the declarations.

### Covariant Return Types

Declarations with the same signature can have different return types if the chosen return type is compatible according to Java rules. For example, `Integer` is a subtype of `Number`:

```java
interface A {
    Number value();
}

interface B {
    Integer value();
}

interface C extends A, B {
}

final class NumberValue implements C {
    @Override
    public Integer value() {
        return 7;
    }
}

public class Main {
    public static void main(String[] args) {
        C value = new NumberValue();
        System.out.println(value.value());
    }
}
```

Output:

```text
7
```

`Integer value()` can satisfy both declarations. Conversely, if one superinterface requires `String value()` and another interface requires `Integer value()` with the same parameters, the two return types are incompatible; the subinterface cannot merge them into a valid contract. This is a compile-time error, not a situation that can be fixed by writing two methods with the same name and the same parameter list.

## 4. Generics and Inherited Methods

When a superinterface has type parameters, substitute the type parameters according to how the subinterface extends it:

```java
interface Box<T> {
    T get();
}

interface TextBox extends Box<String> {
}

final class MessageBox implements TextBox {
    @Override
    public String get() {
        return "hello";
    }
}
```

In `TextBox`, the contract `T get()` is applied with `T = String`. Therefore, the appropriate implementation in `MessageBox` is `String get()`.

With a complex generic interface hierarchy, you need to consider both type parameter substitution and type erasure rules. Declarations that would conflict after type erasure or that do not have compatible return types will be rejected by the compiler. You should not conclude that two methods are different merely because they use different type parameter names in the source code.

## 5. Distinguishing Abstract from Default Methods

A `default` method has a body, so it can provide an implementation for a class. If a subinterface inherits a default method from a more specific superinterface, that implementation usually takes precedence over a declaration with the same signature from its ancestor interface.

```java
interface A {
    default String label() {
        return "A";
    }
}

interface B extends A {
    @Override
    default String label() {
        return "B";
    }
}

interface C extends B {
}

final class Item implements C {
}

public class Main {
    public static void main(String[] args) {
        System.out.println(new Item().label());
    }
}
```

The output is:

```text
B
```

`Item` does not have to implement `label()` itself because an appropriate default method is inherited through `B`.

There are two other important situations:

1. **Two conflicting default methods:** if two superinterfaces with no parent-child relationship both provide a default method with equivalent signatures, Java does not automatically choose one. The subinterface or implementing class must override it to resolve the conflict. For example:

   ```java
   interface Left {
       default String name() {
           return "left";
       }
   }

   interface Right {
       default String name() {
           return "right";
       }
   }

   final class Both implements Left, Right {
       @Override
       public String name() {
           return Left.super.name();
       }
   }
   ```

   Here, `Both` explicitly chooses `Left`'s implementation using `Left.super.name()`. The class can write its own body instead of calling a default method.

2. **A subinterface redeclares a default method as abstract:** a subinterface can intentionally drop the default implementation for that contract. In that case, a concrete class implementing the subinterface must provide the corresponding method:

   ```java
   interface Base {
       default void run() {
           System.out.println("base");
       }
   }

   interface RequiresRun extends Base {
       @Override
       void run();
   }

   final class Job implements RequiresRun {
       @Override
       public void run() {
           System.out.println("job");
       }
   }
   ```

   `RequiresRun` redeclares `run()` without a body, so the `Job` class must implement that method.

When an abstract method and a default method both appear from different inheritance branches, examine the overriding rules and the specificity of the declarations. In particular, do not infer the result merely from seeing a method with a body: you must determine which method is actually inherited after applying Java's rules. If the declarations conflict or are incompatible, the compiler will report an error and you need to fix the declaration relationship or override explicitly.

## 6. When Does a Class Already Have an Implementation Without Rewriting It?

An abstract obligation can be satisfied by a suitable public instance method inherited from a superclass. Therefore, you do not always need to see the method written directly in the class under consideration.

```java
interface Identifiable {
    String id();
}

class BaseRecord {
    public String id() {
        return "base-1";
    }
}

final class Record extends BaseRecord implements Identifiable {
}

public class Main {
    public static void main(String[] args) {
        Identifiable record = new Record();
        System.out.println(record.id());
    }
}
```

Output:

```text
base-1
```

The `public String id()` method inherited from `BaseRecord` satisfies the `Identifiable` contract. The superclass method must be accessible and compatible with the interface contract; a `protected` method does not satisfy the `public` requirement of an interface method.

The class method precedence rule should also be kept in mind: an instance method inherited from a superclass plays an important role when it has the same signature as a default method. If the superclass has an abstract method, the superclass declaring that method can still require the subclass to provide a body, even when an interface also has a default method with the same signature.

A class declared `abstract` can retain unimplemented obligations. The final concrete class in the inheritance chain must satisfy all remaining abstract methods.

## 7. Practical Inspection Process

When tasked with determining the abstract methods inherited by an interface or class, follow this order:

1. **Identify the node under consideration.** Is it a subinterface using `extends`, or a class using `implements`, and which interfaces are involved?
2. **List all superinterfaces.** Follow both direct and indirect parent branches to avoid missing distant ancestors.
3. **Classify the methods.** Record abstract instance, default, static, and private methods; static/private methods do not create instance obligations for the implementing class.
4. **Normalize signatures.** Consider the name, parameters, substituted generics, and return type. Group equivalent declarations, then check whether they are compatible.
5. **Resolve inheritance and overriding.** Determine which declaration is more specific, which default method can be used, which abstract declaration overrides a default method, and whether there are conflicts from multiple branches.
6. **Check implementations from the superclass.** An inherited `public` instance method may satisfy the contract; do not look only inside the body of the current class.
7. **List the remaining obligations.** For a concrete class, each remaining abstract method must have a suitable public implementation. For an abstract class, obligations may be retained for subclasses to fulfill.
8. **Let the compiler confirm.** Compile all related interfaces and classes. Compilation errors help uncover incompatible signatures, default method conflicts, missing implementations, or generic errors that reading individual files separately can easily miss.

You can use the following quick checklist:

| Indicator | How to Handle |
| --- | --- |
| Interface declares `void m();` | Treat as an implicitly abstract method |
| Two superinterfaces both declare compatible `m()` | A single implementation can satisfy both |
| Return types with the same signature are compatible by subtype relationship | Choose an implementation whose return type satisfies all contracts |
| Return types with the same signature are incompatible | Compilation error; cannot create two overloads differing only in return type |
| A suitable default method exists from a superinterface | The inherited implementation can be used if not overridden or conflicting |
| Two unrelated default methods conflict | Override to resolve explicitly |
| Subinterface redeclares a default method without a body | The abstract obligation is restored for the implementing class |
| Superclass already has a compatible `public` method | The inherited method can satisfy the contract |
| Class is declared `abstract` | Unimplemented methods may be retained |

## 8. Common Reasoning Mistakes

- **Reading only direct interfaces:** methods can be inherited from ancestors multiple levels higher.
- **Counting each declaration as a separate obligation:** multiple compatible declarations with the same signature can be satisfied by a single implementation.
- **Ignoring `default`:** a method with a body can satisfy a contract, but you still need to check specificity relationships and conflicts.
- **Treating static/private as methods that must be implemented:** these two kinds are not instance obligations inherited by a class.
- **Using return types to distinguish overloads:** Java does not allow two methods that differ only in return type.
- **Ignoring generics:** you must substitute type parameters according to the subinterface before determining signatures and return types.
- **Assuming every class must rewrite the method:** a suitable implementation may already have been inherited from a superclass or a default method.
- **Assuming an abstract class must complete all methods:** an abstract class can pass remaining obligations down to subclasses, whereas a concrete class must satisfy them.
- **Guessing when inheritance branches conflict:** check the override rules and compilation result; do not arbitrarily pick one declaration.

The core point is to determine **the set of methods actually inherited after applying the rules for signatures, return types, overriding, and default methods**. Only the remaining set of abstract methods is the list of obligations that must be implemented, not the total number of declaration lines across the superinterfaces.
