# Scope of Local Class Names in Java

## 1. Goal: Distinguishing Where a Type Name Is Valid from Where an Object Still Exists

A **local class** is a class declaration located inside a block, such as a method body, a constructor, or a nested block within a method. A local class name does not have scope across the entire file or the entire outer class; it is **in scope from the class declaration to the end of the block that directly encloses that declaration**, including blocks nested deeper within the remainder of that block.

Conceptual example:

```java
void example() {
    // The name Local cannot be used here yet.

    class Local {
        String message() {
            return "hello";
        }
    }

    Local value = new Local(); // Valid.
    System.out.println(value.message());
}
// Outside the method, the type Local cannot be referred to by that name.
```

The snippet above is **an illustrative instance method**, not a standalone program. Points to remember:

1. Before the `class Local` declaration, **that local class** name is not yet in scope.
2. Inside the declaration body of Local itself and in the remainder of the enclosing block, the name `Local` can be used according to Java rules.
3. After the closing `}` of **the block directly enclosing the declaration**, the name Local is no longer a type name visible from the outside.
4. An **instance of Local can still exist** after leaving the block if held through an appropriate public interface/superclass type.
5. The scope of a **type name** is not the same as the scope of a **local variable**, and it does not by itself determine **object lifetime on the heap**.

> **Key takeaway:** When reading Java code, find **which block contains the `class Local` line**, then identify positions before/after the declaration line. Do not assume a local class can be referred to by name everywhere simply because its class is created by the JVM.

This lesson focuses specifically on **the scope of local class names**, and expands into scenarios directly tied to scope: nested blocks, conditional branches, loops, duplicate-name declarations in separate regions, interface return types, variable capture, `this`, static contexts, and common compile-time errors. The programs below use Java 17+.

## 2. Basic Runnable Example: Using the Name After Declaration in the Same Block

Create the file **`LocalNameScopeDemo.java`**:

```java
public class LocalNameScopeDemo {
    public static void main(String[] args) {
        String prefix = "Hello";

        class Greeting {
            String text() {
                return prefix + ", Java";
            }
        }

        Greeting greeting = new Greeting();
        System.out.println(greeting.text());

        Greeting second = new Greeting();
        System.out.println(second.text());
    }
}
```

Compile and run:

```bash
javac LocalNameScopeDemo.java
java LocalNameScopeDemo
```

**Standard output:**

```text
Hello, Java
Hello, Java
```

Analysis:

- `Greeting` is declared **inside the main block**.
- Both `new Greeting()` statements **come after** the declaration and are **still in the same block**, so the compiler recognizes the type name.
- `prefix` is a local variable used by the Greeting class; the value of `prefix` is captured according to the final/effectively final rule. We will distinguish capture and class name scope later.
- Once `main` ends, code in another method cannot reference `Greeting` by a name that is not declared in that other method's scope.

**Do not write `LocalNameScopeDemo.Greeting`:** Greeting is a local class, not a member class declared directly in the body of `LocalNameScopeDemo`. A type name qualified by the outer class cannot turn a local class into a member class.

## 3. Scope Starts at the Declaration and Does Not Apply to Preceding Lines

Consider the following snippet that **intentionally does not compile**:

```java
public class BeforeDeclarationError {
    public static void main(String[] args) {
        // Local value = new Local(); // Error if uncommented:
        // no local type named Local exists in this scope yet.

        class Local {
            int value() {
                return 42;
            }
        }

        Local okay = new Local(); // Valid.
        System.out.println(okay.value());
    }
}
```

If the invalid part is kept as comments, the file above compiles and runs:

```bash
javac BeforeDeclarationError.java
java BeforeDeclarationError
```

```text
42
```

**The key point** is the position of `class Local`, not just where the method opens. Before the declaration, the name of this local class cannot be resolved.

### Why Can a Class Still Refer to Its Own Name?

Right inside the local class declaration, the class name is allowed to be used for its members, constructors, and types:

```java
class Node {
    Node next;

    Node(Node next) {
        this.next = next;
    }
}
```

That is a **local class declaration fragment** placed in a valid block. The name `Node` is used within the Node declaration itself, not as a "reference to an undeclared name" like on a line before the declaration.

**Do not mistakenly conclude that** only the lines *after the closing brace of the class* can use the name. The declaration body is a valid part of the class name's scope, while the lines **before the declaration line** are not.

## 4. The Directly Enclosing Block Determines the Boundary

A local class is in scope in **the remainder of the block that directly encloses it**, including subsequent nested blocks within that portion.

Create **`NestedBlockScopeDemo.java`**:

```java
public class NestedBlockScopeDemo {
    public static void main(String[] args) {
        class Ticket {
            String label() {
                return "TICKET";
            }
        }

        Ticket first = new Ticket();
        System.out.println(first.label());

        {
            Ticket second = new Ticket();
            System.out.println(second.label());

            {
                Ticket third = new Ticket();
                System.out.println(third.label());
            }
        }

        Ticket afterNestedBlocks = new Ticket();
        System.out.println(afterNestedBlocks.label());
    }
}
```

```bash
javac NestedBlockScopeDemo.java
java NestedBlockScopeDemo
```

```text
TICKET
TICKET
TICKET
TICKET
```

**Explanation:**

- `Ticket` is inside the main block, and all subsequent code in the same block can refer to it by name.
- The nested blocks below remain within the scope of the local class declared at the higher level.
- Upon exiting a nested block, the name Ticket remains visible because **the block directly enclosing the Ticket declaration has not ended yet**.

This rule does not work in reverse: if Ticket is declared *inside* an inner block, code in the parent block after the inner block closes **cannot use that Ticket name**.

## 5. Declaration Inside an Inner Block: The Name Does Not "Leak" to the Parent Block

Create **`InnerBlockOnlyDemo.java`**:

```java
public class InnerBlockOnlyDemo {
    public static void main(String[] args) {
        {
            class Local {
                String id() {
                    return "INSIDE";
                }
            }

            Local instance = new Local();
            System.out.println(instance.id());
        }

        System.out.println("outer block continues");

        // Local outside = new Local(); // Invalid:
        // the name Local belongs only to the inner block that has closed.
    }
}
```

```bash
javac InnerBlockOnlyDemo.java
java InnerBlockOnlyDemo
```

```text
INSIDE
outer block continues
```

The `Local outside` line is commented out so the example can run. If uncommented, the compiler will not recognize the type name Local from the closed block.

Do not confuse this with **holding an object variable**: in this example, `instance` is also a local variable whose name exists only within the inner block. But even if the instance is passed outside via an interface, the Local class name still does not extend its scope. These two things must be distinguished.

## 6. Local Classes in Two Different Blocks Can Share the Same Name

Two `class Result` declarations in **two separate blocks with non-overlapping scopes** can share the name Result. Each declaration creates a local class of a different type.

Create **`DisjointLocalNamesDemo.java`**:

```java
public class DisjointLocalNamesDemo {
    public static void main(String[] args) {
        {
            class Result {
                String text() {
                    return "FIRST";
                }
            }

            Result a = new Result();
            System.out.println(a.text());
        }

        {
            class Result {
                String text() {
                    return "SECOND";
                }
            }

            Result b = new Result();
            System.out.println(b.text());
        }
    }
}
```

```bash
javac DisjointLocalNamesDemo.java
java DisjointLocalNamesDemo
```

```text
FIRST
SECOND
```

In the first block, `Result` is the type declared in the first block. After the block closes, that name goes out of scope. In the second block, a **new declaration** creates a different Result type.

**It does not mean** these two classes are the same type just because the name `Result` is written identically. Nor can you take a variable declared in the first block and use it in the second block after it has gone out of scope.

### What If the Scopes Overlap?

Do not declare two local classes with the same name in an overlapping scope region assuming Java will treat them as overloads. Choose different names or organize them into separate blocks with clear boundaries.

## 7. Declaring the Same Name in Two Different Methods

Method scopes are independent: each method can declare a local class with the same name without being the same type.

Create **`SameNameDifferentMethodsDemo.java`**:

```java
public class SameNameDifferentMethodsDemo {
    static void alpha() {
        class Helper {
            String message() {
                return "ALPHA";
            }
        }
        System.out.println(new Helper().message());
    }

    static void beta() {
        class Helper {
            String message() {
                return "BETA";
            }
        }
        System.out.println(new Helper().message());
    }

    public static void main(String[] args) {
        alpha();
        beta();
    }
}
```

```bash
javac SameNameDifferentMethodsDemo.java
java SameNameDifferentMethodsDemo
```

```text
ALPHA
BETA
```

`alpha.Helper` and `beta.Helper` **are not Java syntax for naming a local class**. Both only have the simple name `Helper` within the separate scope of each method body.

If you need a type shared across multiple methods, make it a **member class**, static nested class, top-level class, or use a common interface/superclass; do not turn a local class into a shared API by combining the method name and class name.

## 8. Local Classes in an `if` Branch Are Scoped by Braces

A local class declaration is a block statement, so it is usually placed inside the **`{ ... }`** of a conditional branch.

Create **`ConditionalLocalClassDemo.java`**:

```java
public class ConditionalLocalClassDemo {
    public static void main(String[] args) {
        boolean enabled = true;

        if (enabled) {
            class Choice {
                String value() {
                    return "YES";
                }
            }

            Choice chosen = new Choice();
            System.out.println(chosen.value());
        } else {
            class Choice {
                String value() {
                    return "NO";
                }
            }

            Choice chosen = new Choice();
            System.out.println(chosen.value());
        }

        System.out.println("after if");
        // Choice invalid = new Choice(); // Outside both blocks.
    }
}
```

```bash
javac ConditionalLocalClassDemo.java
java ConditionalLocalClassDemo
```

```text
YES
after if
```

**Why don't the two `Choice` names conflict?** Each declaration is in its own branch block; the name scopes do not overlap.

**Why can't `Choice` be used after `if`?** Both branch blocks have already ended. Even though the program created a Choice instance from the true branch, **there is no local type name Choice in the enclosing block after the if statement**.

If the result needs to be used after if, choose a **type exposed in a wider scope**, such as an interface/supertype.

## 9. Returning a Local Class Object Through an Interface

A local class can implement an interface **declared in a sufficiently wide scope**, allowing code outside the block to hold and invoke the object **without naming the local class**.

Create **`LocalClassFactoryDemo.java`**:

```java
interface Message {
    String text();
}

public class LocalClassFactoryDemo {
    static Message makeMessage(String prefix) {
        class LocalMessage implements Message {
            @Override
            public String text() {
                return prefix + " Java";
            }
        }

        return new LocalMessage();
    }

    public static void main(String[] args) {
        Message message = makeMessage("Hello");
        System.out.println(message.text());

        // LocalMessage x; // Invalid in main:
        // the name LocalMessage exists only inside makeMessage.
    }
}
```

```bash
javac LocalClassFactoryDemo.java
java LocalClassFactoryDemo
```

```text
Hello Java
```

Analysis:

- `LocalMessage` can only be named inside the `makeMessage` method block.
- `Message` is a package-private top-level interface in the same file, so main knows the interface name.
- The factory returns the object through `Message`, a type visible to the caller.
- When `makeMessage` finishes, **the LocalMessage object does not disappear** as long as `message` holds a reference to it. The JVM still has the instance with its corresponding runtime class, while code in main uses only **the interface name Message** to interact with it.

**A type name being out of scope does not mean the runtime object no longer exists.** This is the most important check in questions distinguishing scope from lifetime.

## 10. A Local Class Name Cannot Appear in a Method Signature Outside Its Block

If a class is declared only inside method A, its name is not in scope for:

- The return type declaration of another method.
- A field declaration of the enclosing class.
- A parameter declaration of another method.
- Another method body.
- A top-level class placed outside the block.

The lines below show **invalid code kept in comments**:

```java
class Enclosing {
    // LocalType saved;              // Cannot name the local class.
    // LocalType create() { ... }    // Cannot be used as the return type.

    Object create() {
        class LocalType {
        }
        return new LocalType();
    }

    void inspect() {
        Object x = create();         // Valid.
        // LocalType y = ...;        // Local class name is not visible.
    }
}
```

This is an **illustrative class** without main; the `...` only appears inside comments, not as a placeholder to implement.

**Meaningful fix:** Define an interface or base type that can be used in those places, then have the local class implement/extend it. That way, the API does not leak the local type name.

## 11. `Object` Can Be Used, but Only the `Object` API Is Visible

If a factory returns `Object` instead of a specific interface, the caller can hold the reference but **cannot call methods that exist only on the local class** through the static type Object.

Create **`LocalObjectReturnDemo.java`**:

```java
public class LocalObjectReturnDemo {
    static Object create() {
        class Local {
            String special() {
                return "SECRET";
            }

            @Override
            public String toString() {
                return special();
            }
        }

        return new Local();
    }

    public static void main(String[] args) {
        Object object = create();

        System.out.println(object);
        System.out.println(object != null);

        // object.special(); // Does not compile:
        // the static type Object does not declare special().
    }
}
```

```bash
javac LocalObjectReturnDemo.java
java LocalObjectReturnDemo
```

```text
SECRET
true
```

`Object.toString()` is a method already available on Object and overridden by the local class, so calling `System.out.println(object)` can display SECRET.

**Do not conclude:** that because the instance has runtime type Local, an Object variable anywhere else knows the name Local for casting. If the caller needs the `special()` API, use an appropriate public interface rather than relying on reflection or compiler-generated names as the main approach.

## 12. Using a Name Through a Superclass in the Same Package

An interface is not strictly required to hold the object. A local class can also **extend a superclass with a wider scope**.

Create **`LocalSubclassDemo.java`**:

```java
abstract class Operation {
    abstract int run();
}

public class LocalSubclassDemo {
    static Operation create(int amount) {
        class Addition extends Operation {
            @Override
            int run() {
                return amount + 1;
            }
        }

        return new Addition();
    }

    public static void main(String[] args) {
        Operation operation = create(9);
        System.out.println(operation.run());
    }
}
```

```bash
javac LocalSubclassDemo.java
java LocalSubclassDemo
```

```text
10
```

- `Addition` has a name only inside the `create` method.
- `Operation` is a supertype visible to main.
- Runtime polymorphism invokes the overridden `run()` on the Addition instance after the factory method finishes.

**This is not "a local class whose scope extends through the parent class"**: only the name `Operation` has a wider scope; the name `Addition` remains confined to the create method.

## 13. Scope in a Loop: A Declaration Can Be Executed Multiple Times, While the Name Still Follows the Block

Declaring a local class inside the body block of a loop is valid. Each iteration can create a **new instance**, but the local class name exists only within **the source-code region where it is defined**.

Create **`LocalClassInLoopDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LocalClassInLoopDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int index = i;

            class Printer implements Runnable {
                @Override
                public void run() {
                    System.out.println("index=" + index);
                }
            }

            tasks.add(new Printer());
        }

        for (Runnable task : tasks) {
            task.run();
        }

        // Printer p; // Not within the scope of the for-loop block.
    }
}
```

```bash
javac LocalClassInLoopDemo.java
java LocalClassInLoopDemo
```

```text
index=0
index=1
index=2
```

Points to understand:

1. The `class Printer` line is inside **the for body block**.
2. In the remainder of that body block, `new Printer()` can be created.
3. Upon exiting the for block, `Printer` is no longer a visible type name in the main block.
4. The `Runnable` objects added to `tasks` **still exist**; when `run()` is called after the loop, each instance produces the captured `index` value.
5. `index` is freshly declared on each entry into the loop block and is not reassigned afterward, so it is effectively final for the corresponding instance.

**Note:** In the example above, it is not said that each loop iteration creates a different *new class type*. It is **a single class declaration at one source location**, used multiple times to create objects.

## 14. `switch`, `try`, and Other Blocks: Find the Actual `{ }` Braces

The scope of a local class name depends on **the declaration position and the directly enclosing block**, not just the name of the control structure.

Create **`TryBlockLocalClassDemo.java`**:

```java
public class TryBlockLocalClassDemo {
    public static void main(String[] args) {
        try {
            class ResourceNote {
                String text() {
                    return "TRY";
                }
            }

            System.out.println(new ResourceNote().text());
        } catch (RuntimeException ex) {
            System.out.println("ERROR");
            // ResourceNote note; // Not visible from catch.
        }

        System.out.println("END");
        // ResourceNote note; // Also not visible after try.
    }
}
```

```bash
javac TryBlockLocalClassDemo.java
java TryBlockLocalClassDemo
```

```text
TRY
END
```

`ResourceNote` is declared **inside the try block**; the catch block is not part of that scope. This declaration does not "reach" across catch or past try.

**Be careful with switch:** Different forms of switch have their own rules for blocks, switch statement groups, and switch expressions. Do not simply assume that "each case always has its own new scope." When using a local class in a switch branch, the clear, less error-prone approach is to wrap the branch's logic in its own braced block, and then check against that block's boundaries.

### Two Switch Branches with Explicit Blocks

The code snippet below is **an illustrative method**, without its own main:

```java
void show(int kind) {
    switch (kind) {
        case 1: {
            class Marker {
                String text() {
                    return "ONE";
                }
            }
            System.out.println(new Marker().text());
            break;
        }
        default: {
            class Marker {
                String text() {
                    return "OTHER";
                }
            }
            System.out.println(new Marker().text());
        }
    }
}
```

The two `Marker` classes in two separate blocks are intentionally given the same name; they do not create a single Marker type whose scope covers all cases.

## 15. Class Name Scope Differs from Variable Name Scope

Consider:

```java
void example() {
    class Box {
    }

    Box first = new Box();

    {
        Box second = new Box();
    }

    Box third = new Box();
    // second is not visible here,
    // whereas Box is still visible because the class is declared in the outer block.
}
```

This is an **illustrative instance method**.

- The name **`Box`** is declared in the outer block and stays in scope until the end of the outer block.
- The local variable name **`second`** is declared in the inner block and goes out of scope when the inner block closes.
- `Box` can still be used to declare `third`.
- The variable second going out of scope does not immediately destroy the object, nor does it destroy the Box class definition.

**Further distinction:** Java has separate namespaces/lookup rules for types and variables. Do not use a same-named variable to assume a local class name is shadowed in the same way; you must check lookup according to the exact syntactic context requiring either a **type name** or an **expression name**.

## 16. "Scope" Does Not Mean "Access Control"

These are two different concepts:

- **Scope / lexical visibility:** On which lines of code can the name `Local` be used to specify a type, create an instance, or call a constructor?
- **Access control:** Once a name/type can be used, which members do `public`/package-private/`protected`/`private` rules allow accessing?

A local class is not declared directly as a public API at the class level:

```java
void make() {
    // public class Local { } // Invalid as a local class.
    class Local {
    }
}
```

This is a valid code snippet inside a class. A local class declaration does not accept the `public` modifier like a top-level public class. Even though member methods of the local class can be public if a contract requires it, the name **Local** still does not escape the block.

**Similarly:** A local class can implement a public interface and its instance can be returned outside; that **does not make the local class name public**.

## 17. Local Variables of the Enclosing Method Can Be Accessed, but Must Be Effectively Final

A local class can reference local variables and parameters of the enclosing method when those variables are **final or effectively final**.

Create **`CapturedValueLocalClassDemo.java`**:

```java
public class CapturedValueLocalClassDemo {
    static Runnable create(String prefix) {
        int count = 3;

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(prefix + "=" + count);
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        Runnable task = create("ITEM");
        task.run();
    }
}
```

```bash
javac CapturedValueLocalClassDemo.java
java CapturedValueLocalClassDemo
```

```text
ITEM=3
```

`prefix` is a parameter; `count` is a local variable. No assignment modifies them after being received/initialized, so both are effectively final.

When `create` returns, the variable `count` can no longer be used by name in main, yet the local task still holds the captured data according to the contract. Similarly, **the name `LocalTask` exists only inside create**, while the Runnable object continues to exist.

### A Compile-Time Error Example Caused by Capture

```java
void wrong() {
    int count = 1;

    class Local {
        int read() {
            return count;
        }
    }

    count++; // Since the same count variable has been captured by the local class,
             // it is no longer effectively final.
}
```

This is **error-demonstrating code**, not a runnable program. The issue here is **local variable capture**, not the name `Local` going out of scope.

**Distinguish:**
- Scope of the `Local` class name: determines where `new Local()` can be written.
- Effectively-final status of `count`: determines whether the local class can capture that variable.
- Lifetime of the Local object: depends on the references still held, and is not identical to the two above.

## 18. Mutating the State of a Captured Object Differs from Reassigning the Captured Variable

The effectively final requirement applies to the **reference variable**; it does not mean every object pointed to by the reference is immutable.

Create **`MutableCapturedObjectDemo.java`**:

```java
public class MutableCapturedObjectDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");

        class Printer {
            void addAndPrint(String suffix) {
                builder.append(suffix);
                System.out.println(builder);
            }
        }

        Printer printer = new Printer();

        printer.addAndPrint("1");
        builder.append("2");
        printer.addAndPrint("3");
    }
}
```

```bash
javac MutableCapturedObjectDemo.java
java MutableCapturedObjectDemo
```

```text
A1
A12
A123
```

`builder` remains effectively final because it is not **assigned a new reference**. However, `StringBuilder` is mutable, so the `append` calls modify the object's contents.

**Scope-related point:** The local class Printer has its name in scope for the rest of the main block. The builder variable can be used when capture satisfies the rule; mutable state is observed through an alias.

Do not confuse Java local class capture with a "deep copy" of the captured object; normally it is still a reference to the same object.

## 19. `this` in a Local Class Is the Object of That Class Itself

A local class is a class, not a lambda expression. In an instance method of a local class, `this` refers to **the local-class object**.

Create **`LocalThisDemo.java`**:

```java
class Outer {
    private final String label = "OUTER";

    void run() {
        class Local {
            private final String label = "LOCAL";

            void show() {
                System.out.println(this.label);
                System.out.println(Outer.this.label);
            }
        }

        new Local().show();
    }
}

public class LocalThisDemo {
    public static void main(String[] args) {
        new Outer().run();
    }
}
```

```bash
javac LocalThisDemo.java
java LocalThisDemo
```

```text
LOCAL
OUTER
```

- `this.label`: field belonging to the Local object.
- `Outer.this.label`: field belonging to the enclosing Outer instance inside the instance method Outer.run.
- `Local` is in scope only for the remainder of the `run()` block.

**Do not assume that** a Local class has an implicit Outer instance in every case. If a local class is declared inside a **static method**, there is no implicit `Outer.this`; the code needs an explicit Outer reference if it wants to use instance state.

## 20. A Local Class in a Static Method: Still Valid to Declare, Without `Outer.this`

A local class can appear inside a **static method**. The scope rules for **the local class name** remain unchanged, but accessing the enclosing Outer instance differs.

Create **`StaticMethodLocalClassDemo.java`**:

```java
class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    static String run(Outer owner) {
        class Local {
            String text() {
                // There is no Outer.this in a static context.
                return owner.label;
            }
        }

        Local result = new Local();
        return result.text();
    }
}

public class StaticMethodLocalClassDemo {
    public static void main(String[] args) {
        Outer owner = new Outer("EXPLICIT");
        System.out.println(Outer.run(owner));
    }
}
```

```bash
javac StaticMethodLocalClassDemo.java
java StaticMethodLocalClassDemo
```

```text
EXPLICIT
```

`owner` is an effectively final method parameter and is captured. `Local` is a local type name in scope from its declaration to the end of the static method block.

**Do not confuse** the following two questions:

- "Can a local class be declared in a static method?" → Yes.
- "Can `Outer.this` be written in a local class declared from a static method without an enclosing Outer instance?" → No.

## 21. Local Classes and Member Nested Classes Have Different Name Scopes

Quick comparison:

| Feature | Local class | Member nested class |
| --- | --- | --- |
| Declaration location | Inside a valid method/constructor/initializer block | Inside a class/interface body according to the rules |
| Does the name's scope span the entire enclosing class? | No; covers the remainder of the declaring block | Declared as a member type and resolved according to member-type lookup rules |
| Can `Outer.Local` be written from outside? | No | Possible for a member type if access allows |
| Can other methods in Outer use the name directly? | No if outside the block scope | Yes when the member type is visible |
| Can an instance be created after leaving the block? | Yes, through a retained interface/supertype/reference | Yes |
| Is every nested class an inner class? | No; there are static nested classes | Member nested classes can be static or non-static |
| Is an implicit outer instance needed? | Depends on the context where the local class is declared | Non-static member inner classes have an enclosing instance; static nested classes do not |

**Key rule to remember:** A local class has its name scoped inside a **block**, while a member nested class has a name that is a **member type of the enclosing class**. Do not use the same qualified-name syntax for both.

### Example of a Member Class Usable from Another Method

File **`MemberVersusLocalDemo.java`**:

```java
public class MemberVersusLocalDemo {
    static class Member {
        String name() {
            return "MEMBER";
        }
    }

    static void first() {
        class Local {
            String name() {
                return "LOCAL";
            }
        }

        System.out.println(new Local().name());
    }

    static void second() {
        System.out.println(new Member().name());
        // new Local(); // Local from first is not visible here.
    }

    public static void main(String[] args) {
        first();
        second();
    }
}
```

```bash
javac MemberVersusLocalDemo.java
java MemberVersusLocalDemo
```

```text
LOCAL
MEMBER
```

Member is a static nested member class of the outer class; Local exists by name only within the block of `first`.

## 22. A Local Class Does Not Have a Qualified Name for Source Clients

The compiler/JVM may generate an internal binary name for local classes, typically containing `$` and sequence numbers. However, that is **not source-level type access syntax** guaranteed to be stable for an API.

Do not write:

```java
// Outer$1Local x;       // Not a stable way to name a local class.
// Outer.Local x;        // Local is not a member type of Outer.
// someMethod.Local x;   // Java does not use a method name to qualify a type.
```

**Do not rely on** class file names generated by the compiler as a substitute for scope. A change in source code position/structure can cause compiler-generated artifacts to differ.

Reflection can inspect the runtime class of a local object:

```java
Object instance = ...; // Illustrative: instance from a local class.
Class<?> runtimeType = instance.getClass();
```

That is runtime reflection; it does not make the Java compiler accept the type name `Local` at a location outside its lexical scope.

### Safe Reflection Example Without Guessing Binary Names

Create **`LocalClassReflectionDemo.java`**:

```java
public class LocalClassReflectionDemo {
    static Object create() {
        class LocalValue {
            @Override
            public String toString() {
                return "VALUE";
            }
        }

        return new LocalValue();
    }

    public static void main(String[] args) {
        Object value = create();
        Class<?> type = value.getClass();

        System.out.println(type.isLocalClass());
        System.out.println(value.toString());
    }
}
```

```bash
javac LocalClassReflectionDemo.java
java LocalClassReflectionDemo
```

```text
true
VALUE
```

`Class.isLocalClass()` indicates through the API whether the runtime class is a local class. The program does not print `getName()` or `getCanonicalName()` because compiler-generated names should not be used as an output contract.

## 23. Local Classes Differ from Anonymous Classes and Lambda Expressions

All three forms can define local behavior, yet they differ in naming and types:

- **Local named class**: has a type name in scope within the block starting from its declaration; multiple instances can be created with `new Local()` within that scope.
- **Anonymous class**: has no new source-level class name to refer to again with `new AnonymousName()`; the expression directly creates the object.
- **Lambda expression**: is not a named local class declaration and has different lexical `this` rules from an anonymous class.

### Comparison Example Independent of Runtime Class Names

Create **`LocalAnonymousLambdaDemo.java`**:

```java
public class LocalAnonymousLambdaDemo {
    public static void main(String[] args) {
        class LocalAction implements Runnable {
            @Override
            public void run() {
                System.out.println("LOCAL");
            }
        }

        Runnable named = new LocalAction();
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("ANONYMOUS");
            }
        };
        Runnable lambda = () -> System.out.println("LAMBDA");

        named.run();
        anonymous.run();
        lambda.run();
    }
}
```

```bash
javac LocalAnonymousLambdaDemo.java
java LocalAnonymousLambdaDemo
```

```text
LOCAL
ANONYMOUS
LAMBDA
```

`LocalAction` is a type name in scope for the remainder of main. An anonymous class has no name to write `new Anonymous()`, whereas a lambda uses the target type `Runnable` according to functional-interface rules.

All of them can still be held and invoked through a `Runnable` variable if the API fits.

## 24. Local Records Are Not Completely Identical to Regular Local Classes Regarding Capture

Java 17 supports **local record declarations** inside blocks. A record has different characteristics: a local record is **implicitly static** and does not capture local variables from the enclosing method like a regular local inner class.

File **`LocalRecordContrastDemo.java`**:

```java
public class LocalRecordContrastDemo {
    public static void main(String[] args) {
        int offset = 10;

        class LocalAdder {
            int add(int value) {
                return value + offset;
            }
        }

        record Pair(int left, int right) {
            int sum() {
                return left + right;
            }
        }

        System.out.println(new LocalAdder().add(5));
        System.out.println(new Pair(2, 3).sum());
    }
}
```

```bash
javac LocalRecordContrastDemo.java
java LocalRecordContrastDemo
```

```text
15
5
```

**Distinguish two aspects:**

- The names `LocalAdder` and `Pair` are both in scope within the block according to their respective declarations.
- However, `LocalAdder` can capture the effectively-final `offset`.
- `Pair` is a local record and cannot automatically capture `offset` inside the record's instance methods; to use the offset value, pass it into a component/parameter or data structure per the contract.

Do not assume that **every kind of local type declaration** allows capture the same way member/local inner classes do.

## 25. A Local Class Creating Linked Nodes: Using Its Name Inside Its Own Body

Practical example of self-reference:

Create **`LocalLinkedNodesDemo.java`**:

```java
public class LocalLinkedNodesDemo {
    public static void main(String[] args) {
        class Node {
            final int value;
            Node next;

            Node(int value) {
                this.value = value;
            }
        }

        Node first = new Node(1);
        Node second = new Node(2);
        first.next = second;

        int sum = 0;
        for (Node node = first; node != null; node = node.next) {
            sum += node.value;
        }

        System.out.println(sum);
    }
}
```

```bash
javac LocalLinkedNodesDemo.java
java LocalLinkedNodesDemo
```

```text
3
```

Inside the body of `class Node`, declaring the field `Node next` is valid. After the declaration, main uses Node for variables, constructor calls, and the for-loop variable.

**Note:** The example only has two nodes with no cycle; the for loop stops at null. When using a Node-style local class for a larger graph algorithm, scope does not prevent creating linked objects while the name remains visible, yet the class is used only internally by that algorithm.

## 26. A Factory Inside an Inner Block: The Object Escapes, the Name Does Not

The scope can be narrower than even the method if declared inside an inner block. To use the object after the block, **a variable of an appropriate type declared outside the block** is needed.

Create **`EscapingLocalInstanceDemo.java`**:

```java
public class EscapingLocalInstanceDemo {
    public static void main(String[] args) {
        Runnable action;

        {
            String label = "BLOCK";

            class LocalAction implements Runnable {
                @Override
                public void run() {
                    System.out.println(label);
                }
            }

            action = new LocalAction();
        }

        action.run();

        // LocalAction x; // Not visible after the inner block.
    }
}
```

```bash
javac EscapingLocalInstanceDemo.java
java EscapingLocalInstanceDemo
```

```text
BLOCK
```

**Two scopes to pay attention to:**

- The variable `action` is declared in the main block, so it remains in scope after the inner block and is definitely assigned before being invoked.
- The name `LocalAction` exists only inside the inner block, so it cannot be used as a type declaration after that block.

When `action.run()` is called, the LocalAction object still exists. This also demonstrates that the local variable `label` can be captured; the end of a variable's lexical scope does not mean the data captured by the object must be lost.

## 27. Why Not Declare a Local Class as a Public API?

A local class is appropriate when an implementation is needed only inside a single method/block, for example:

- A short helper for an algorithm.
- An object implementing a strategy/interface solely for one factory.
- A comparator/callback that needs local state (when not using a lambda).
- A temporary data structure within a single computation.
- A localized handler that does not need to be reused by name in other methods.

If multiple methods or callers need to **name that type**, a local class is generally not suitable as an API, because:

1. The local class name is not visible in other methods.
2. The local class itself cannot be declared as the return type in a method signature outside its scope.
3. External code cannot easily use members that are not present on a public interface/superclass.
4. If an implementation is used in multiple places, copy-pasting local declarations can create multiple distinct types with the same name and increase duplication.

**Alternative approaches:** a member class, a static nested class, a top-level class, or a public interface paired with a local implementation depending on the need.

It does not mean a local class is "slower" or "less object-oriented." This is primarily a decision about **name scope and level of implementation hiding**.

## 28. Common Compilation Errors

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using `new Local()` before the `class Local` line | The local class name is not yet in scope | Place the declaration before the usage site |
| Using `Local x` after the closing `}` of the declaring block | Already out of scope | Use an interface/supertype outside |
| Using `Local` in another method | Scope is limited to the declaring method's block | Use a member type or interface |
| Using `Outer.Local` | Local is not a member class | Choose a type with an appropriate scope |
| Declaring `public class Local` inside a block | Not a valid modifier for a local class declaration | Use only valid local class syntax |
| Putting two local classes with the same name into an overlapping region | Name conflict per language rules | Separate the blocks or rename |
| Expecting `if (x) class Local { }` to work as a blockless statement | A local class declaration is a block declaration | Place it inside `{...}` |
| Assuming `Object result = create()` allows calling `result.special()` | Static type Object does not declare special | Use an interface that declares the special method |
| Expecting the local class object to disappear when the method returns | Name scope differs from instance lifetime | Understand references/GC |
| Using a reassigned local variable from inside a local class | Capture requires final/effectively final | Avoid reassigning, or design separate state |
| Treating a captured mutable object as a deep copy | Only the reference is captured; the object remains mutable | Use an immutable snapshot if needed |
| Confusing the local class's `this` with `Outer.this` | They are two different receivers | Qualify the receiver properly |
| Using `Outer.this` in a local class inside a static method | No implicit enclosing Outer instance | Pass an owner reference |
| Guessing runtime names like `Outer$1Local` | Compiler details are not stable for an API | Use `Class.isLocalClass()` when reflection is needed |
| Assuming the same name in two methods creates the same type | Two separate declarations | Use a common interface/supertype |
| Confusing a local record with a capturing local class | Local records are implicitly static | Pass values via record components |
| Checking only code running inside the block without checking the external API | Overlooking the type-name scope boundary | Test before/after the declaration and after the block |

## 29. Self-Practice Questions with Answers

**Question 1.** A local class is declared inside a method's block. What is the scope of the class name?

**Answer:** From the declaration (inclusive) to the end of the directly enclosing block, including nested blocks in the remainder of that block.

**Question 2.** Can `new Local()` be used before `class Local`?

**Answer:** No, *that local class declaration* cannot be used before it enters scope.

**Question 3.** Can `Local next;` be written right inside the body of `class Local`?

**Answer:** Yes; a local class can use its own name inside its own body, such as a self-referential linked node.

**Question 4.** A local class is declared inside an inner block; can code in the parent block see the name after the inner block closes?

**Answer:** No.

**Question 5.** Can a local class declared in an outer block be used in a subsequent inner block?

**Answer:** Yes, if the inner block is within the remainder of the enclosing scope.

**Question 6.** Do two separate blocks that both declare `class Result` always conflict?

**Answer:** No, if the scopes do not overlap and each declaration follows the rules; they are two different types.

**Question 7.** Can two different methods declare a local class with the same name `Worker`?

**Answer:** Yes. The name is visible only within each corresponding method block.

**Question 8.** After a factory returns a local class object under an interface type, can the object still be used?

**Answer:** Yes, through the methods of the visible interface/supertype.

**Question 9.** If an object is returned under static type `Object`, can a method that exists only in the local class be called?

**Answer:** Not through the static type Object; use an interface declaring the desired method.

**Question 10.** Is `SomeMethod.Local` valid syntax for naming a local class type?

**Answer:** No. A local class is not a member type that can be qualified by a method name.

**Question 11.** Is the scope of a local variable referencing an object the same as the object's lifetime?

**Answer:** No. The object can continue to live if another reference still holds it.

**Question 12.** Can a local class use a parameter of the enclosing method?

**Answer:** Yes, if the parameter is final/effectively final and its usage satisfies all other Java rules.

**Question 13.** Does capturing a `StringBuilder` mean the builder can no longer be mutated?

**Answer:** No. The reference variable is effectively final, but the referenced object can be mutable.

**Question 14.** Is a local class declared inside a static method valid?

**Answer:** Yes. However, there is no implicit `Outer.this` in a static context.

**Question 15.** Inside an instance method of a local class, which object is `this`?

**Answer:** The object of that local class.

**Question 16.** Can a local record be declared and its name used in the remainder of the block?

**Answer:** Yes. However, a local record is implicitly static, differing from regular local inner classes regarding capture.

**Question 17.** How do a local class and an anonymous class differ in naming?

**Answer:** A local class has a name within the block; an anonymous class has no new source-level name to reuse.

**Question 18.** Does using `Class.isLocalClass()` enable naming the class outside its scope in source code?

**Answer:** No. Reflection inspects the runtime type; it does not change compile-time name scope.

**Question 19.** When writing a switch with same-named local classes, what do you need to pay attention to?

**Answer:** The actual lexical block boundaries of each declaration; use braces for each branch when independent scopes are desired.

**Question 20.** When multiple modules need to create the same helper class, should you choose a local or member class?

**Answer:** If a reusable name and shared contract are needed, choose a member/static nested/top-level type; a local class is suitable when the implementation is needed only inside a block.

## 30. Checklist When Reviewing Code with Local Classes

- [ ] Have you correctly identified **the `class Local` line**?
- [ ] Have you found **the directly enclosing block** of the declaration?
- [ ] Are there any lines using the name Local **before** the declaration?
- [ ] Are there any lines using Local **after** the block enclosing the declaration closes?
- [ ] Is code in inner blocks actually within the remainder of the scope?
- [ ] Are there two local types with the same name and overlapping scopes?
- [ ] If two separate blocks share the same name, is it clear that they are **two different classes**?
- [ ] Are there `if`, `try`, `switch`, or loop branches that make block boundaries easy to confuse?
- [ ] Is a local class being confused with a member nested class (`Outer.Local`)?
- [ ] If a caller outside the block needs the object, is there an appropriate **visible interface/supertype**?
- [ ] Are you avoiding calling local-class-specific methods through a variable that only has static type Object?
- [ ] Are you avoiding confusing name scope with variable scope or runtime object lifetime?
- [ ] If the local class captures a parameter/variable, is it final/effectively final?
- [ ] If the captured value is a mutable reference, have aliasing and state changes been considered?
- [ ] If the local class is in a static method, has implicit `Outer.this` been avoided?
- [ ] If the local class is in an instance method, are `this` and `Outer.this` understood?
- [ ] Is there any accidental reliance on compiler-generated binary names?
- [ ] Is a member/static nested/top-level class needed instead of a hard-to-reuse local type?
- [ ] When a local class is inside a loop, have you checked that the type declaration differs from the instances/captured values?
- [ ] Are you avoiding confusing a local record with a local inner class regarding capture?
- [ ] Do runnable Java 17+ examples have the right public class/file names and `javac`/`java` commands?
- [ ] Does the output describe values and ordering determined by the code, without relying on hashes/runtime binary names?

---

**Final takeaway:** The name of a **local class** in Java is in scope **from its declaration (inclusive) to the end of the block that directly encloses it**. That name can be used in subsequent inner blocks, but **cannot be used before the declaration or after the declaring block has closed**. Separate blocks/methods can declare local classes with the same name while creating **different types**. When an object needs to be used after leaving the class name's scope, hold it through an **interface or superclass with a sufficiently wide scope**; the object can continue to exist even when the local class name is no longer available. Finally, do not confuse **type-name** scope with final/effectively-final variable capture, the `this`/`Outer.this` receiver, or runtime instance lifetime.
