# Table of Valid Modifiers by Member Type

## Objectives

Java allows a modifier to appear only on the declaration kinds specified by the language. For example, a field in a class can be private, static, final, transient, or volatile; a method can be abstract, synchronized, or native; and default is a modifier for instance methods with a body in an interface. Choosing the right modifier helps express access privileges, inheritability, and how a member behaves.

This article uses Java 17 and later rules to look up modifiers by declaration kind, understand implicit modifiers in interfaces, identify invalid combinations, and read compiler errors according to their exact cause.

## 1. Access Modifiers and Behavior Modifiers

Four access levels to distinguish:

| Modifier | Access Scope |
|---|---|
| public | Accessible from where the type containing the member is visible and module rules are satisfied. |
| protected | Within the same package and according to inheritance rules in other packages. |
| No access modifier written | Package-private: only within the same package. |
| private | Restricted to the class or enclosing type permitted by Java. |

Not every declaration kind can use all four access levels. A top-level type can only be public or package-private; a top-level class/interface cannot be private or protected. Constructors and class members can use public, protected, private, or package-private. Interface members have their own rules: fields and methods have implicit modifiers, while member types declared in an interface are public static.

Other modifiers govern behavior:

- abstract: leaves the implementation to subclasses or implementing classes.
- final: prevents class inheritance, prevents method overriding, or prevents reassigning a variable after it has been assigned.
- static: the member belongs to the type rather than to individual objects; a static method is hidden rather than overridden under the polymorphic mechanism of instance methods.
- sealed and non-sealed: control the inheritance branches of a class or interface.
- transient and volatile: apply only to fields, but have different meanings regarding serialization and variable access.
- synchronized and native: method modifiers.
- default: declares a default behavior for an instance method in an interface.
- strictfp: can be used on classes, interfaces, and methods; starting in Java 17, floating-point expressions are strict by default, so this modifier is generally unnecessary.

## 2. Modifier Table by Declaration Kind

| Declaration Kind | Commonly Permitted Modifiers | Key Notes |
|---|---|---|
| Top-level class | public, abstract, final, sealed, non-sealed, strictfp; or package-private | Do not use private, protected, or static. abstract and final are mutually exclusive. |
| Top-level interface | public, abstract, sealed, non-sealed, strictfp; or package-private | Interfaces are implicitly abstract; do not use private, protected, final, or static at the top level. |
| Field in a class | public, protected, private, static, final, transient, volatile | Only one access modifier; final cannot be combined with volatile. |
| Method in a class | public, protected, private, abstract, static, final, synchronized, native, strictfp | abstract cannot be combined with private, static, final, native, synchronized, or strictfp. |
| Constructor | public, protected, private; or package-private | Do not use static, abstract, final, default, synchronized, or native. |
| Field in an interface | Implicitly public, static, final | Do not use private, protected, volatile, or transient. |
| Abstract method in an interface | Implicitly public, abstract | Has no body; do not use protected, final, synchronized, or native. |
| Default method in an interface | default; implicitly public | An instance method with a body; cannot simultaneously be abstract, static, or private. |
| Static method in an interface | static; implicitly public or private static | Call public static methods using the interface name; private helpers are only used inside the interface. |
| Private method in an interface | private or private static | Available since Java 9; must have a body. |
| Member type in a class | public, protected, private, or package-private; static for member classes; add class-type modifiers when appropriate | Nested interfaces, enums, and records are implicitly static. |
| Member type in an interface | Implicitly public static | Do not declare member types as private or protected. |
| Local variable or parameter | final or no modifier | Do not use public, private, protected, static, volatile, or transient. Effectively final variables can also be captured by lambdas. |

This table is a quick reference. A specific declaration must still satisfy the member kind, enclosing type, top-level/nested position, and mutually exclusive combinations.

## 3. Modifiers for Classes and Interfaces

A top-level class can be public or package-private, and can use abstract, final, sealed, non-sealed, or strictfp when the relevant rules are met. You cannot combine abstract with final: abstract is for classes that can be extended to complete the abstract parts, whereas final forbids inheritance.

~~~java
public abstract class Task {
    public abstract void run();
}

final class OneShotTask {
    void runOnce() {
        System.out.println("done");
    }
}
~~~

A top-level interface can also only be public or package-private. Interfaces are implicitly abstract; explicitly writing abstract is redundant but valid. An interface cannot be final because it is implemented by other classes, and it cannot be declared static at the top level.

~~~java
public sealed interface Command permits StartCommand, StopCommand {
    void execute();
}

final class StartCommand implements Command {
    @Override
    public void execute() {
        System.out.println("start");
    }
}

final class StopCommand implements Command {
    @Override
    public void execute() {
        System.out.println("stop");
    }
}
~~~

The example illustrates a sealed hierarchy. If placed together in a single source file, only one top-level type can be public and the file name must match the public type. Command restricts its direct subtypes using permits; each direct subtype must be final, sealed, or non-sealed. The non-sealed modifier is only valid when the type directly extends a sealed class or implements a sealed interface.

## 4. Modifiers for Fields

A field in a class can combine an access modifier with static, final, transient, or volatile if the specific combination is valid.

~~~java
class CacheEntry {
    public static final int MAX_SIZE = 100;
    private transient String serializedAway;
    protected volatile boolean refreshNeeded;
    private final String key;

    CacheEntry(String key) {
        this.key = key;
    }
}
~~~

- static final is commonly used for class-level constants. To be a compile-time constant, the value must be a suitable constant expression and the type must be a primitive type or String.
- transient marks a field as not being saved as part of the default state when using Java Serialization.
- volatile provides visibility and ordering under the Java Memory Model. It does not make a multi-step sequence of operations atomic.
- final on a field requires a single assignment according to definite assignment rules. For a reference field, final locks reassigning the reference rather than automatically making the referenced object immutable.

The combination final volatile is invalid. Interface fields are always public static final, even when these three modifiers are not written out. Therefore, private, protected, volatile, or transient cannot be used to alter how an interface field is declared.

## 5. Modifiers for Methods in a Class

Common modifiers include access modifiers, abstract, static, final, synchronized, native, and strictfp.

- abstract declares a method without a body; a class containing an abstract method must be abstract.
- final prevents subclasses from overriding an instance method.
- static belongs to the class; it does not use polymorphic dispatch based on runtime type like instance methods.
- synchronized synchronizes execution on the object's monitor for an instance method, or on the class's monitor for a static method.
- native indicates that the implementation is provided outside Java and the declaration has no Java body.
- strictfp is generally no longer needed in Java 17 because floating-point expressions are strict by default.

An abstract method cannot simultaneously be private, static, final, native, synchronized, or strictfp. These modifiers conflict with a bodyless method needing to be implemented in a subclass, or are directly forbidden by the language.

~~~java
abstract class Processor {
    protected abstract String transform(String input);

    public final String process(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        return transform(input);
    }

    public static String version() {
        return "1.0";
    }

    protected synchronized void record() {
        // Update shared state in a synchronized manner.
    }
}
~~~

process is final to preserve the input validation step and the call to transform. transform is abstract so that subclasses provide the transformation logic. version is static, so it is called via Processor.version(); record is synchronized to synchronize the method body on the corresponding monitor.

## 6. Modifiers for Interface Methods

Unless declared private, default, or static, a regular interface method is implicitly public abstract. Interfaces do not allow protected, final, synchronized, or native methods.

~~~java
interface Formatter {
    String format(String input); // implicitly public abstract

    default String label(String input) {
        return normalize(input);
    }

    static String kind() {
        return "text";
    }

    private String normalize(String input) {
        return input == null ? "" : input.trim();
    }

    private static boolean missing(String input) {
        return input == null || input.isBlank();
    }

    static boolean accepts(String input) {
        return !missing(input);
    }
}
~~~

- format has no body, so it is implicitly public abstract.
- label is an instance method with a body; default allows implementing classes to inherit default behavior.
- kind is static and is called via Formatter.kind(). Static methods in an interface are not instance methods overridden by implementing classes.
- normalize is a private instance helper; missing is a private static helper. Both forms of private methods in interfaces have been supported since Java 9.
- accepts is implicitly public static because it has static without the private access modifier.

The default keyword is for instance methods with a body in an interface. It is not a valid modifier for regular methods in a class. Also do not confuse default methods with the default value syntax for annotation elements, where the default keyword follows its own grammar.

## 7. Constructors and Nested Member Types

A constructor can only use public, protected, private, or package-private. It has no return type and is not a regular instance method, so static, abstract, and final cannot be used. A private constructor is commonly used to restrict object creation from outside; a protected constructor can be useful for base classes used in inheritance.

~~~java
public class Factory {
    private Factory() {
    }

    public static Factory create() {
        return new Factory();
    }

    public static abstract class Worker {
        protected abstract void execute();
    }
}
~~~

Factory has a private constructor, while Worker is a public static abstract member class. Member types in a class can use access modifiers; a member class can be static or an inner class. For member interfaces, enums, and records, Java applies implicit static rules and restrictions specific to each kind.

Member types in an interface are always implicitly public static; you cannot use private or protected to narrow the access level of that member type. Records are implicitly final, so do not add abstract, sealed, or non-sealed to a record.

## 8. Common Invalid Combinations

### Disallowed Access Modifiers at the Top Level

~~~java
private class Hidden {
}
~~~

This does not compile because a top-level class cannot be private. If you need to restrict access to the package, omit the access modifier; if you need a type used only inside another type, declare a nested class and choose the appropriate access modifier.

### Combining abstract and final

~~~java
abstract final class Impossible {
}
~~~

Invalid because abstract requires that subclasses can be created to complete the abstract parts, whereas final prohibits all subclasses. Choose one intent: abstract for an extensible base class or final for a class that forbids inheritance.

### Using protected in an Interface

~~~java
interface BadApi {
    protected void execute();
}
~~~

Invalid because interface methods cannot be protected. If this is a contract method that implementing classes must provide, declare void execute(); and leave it implicitly public abstract. If you need a helper used only inside the interface, use a private method with a body.

### Using default in a Class

~~~java
class OrdinaryClass {
    default void run() {
    }
}
~~~

Invalid because the default modifier is for instance methods in an interface. In a class, use an appropriate access modifier and provide a normal method body.

### Combining final and volatile on a Field

~~~java
class BadState {
    final volatile int count = 0;
}
~~~

Invalid because final prevents reassignment after initialization, while volatile applies volatile variable read/write rules; Java forbids combining these two modifiers on the same field.

### Declaring a private abstract Method

~~~java
abstract class BadProcessor {
    private abstract void process();
}
~~~

Invalid because a private method cannot be overridden for a subclass to provide an implementation, which contradicts the purpose of an abstract method. If subclasses need to implement it, use protected or public abstract depending on the access contract.

## 9. Compilable and Runnable Java 17 Example

Save all of the following code to a file named ModifierMatrixDemo.java. The example uses fields, class methods, a nested abstract class, and an interface with default/static/private methods to illustrate many valid modifier types.

~~~java
public class ModifierMatrixDemo {
    protected static final int LIMIT = 10;
    private volatile boolean dirty;
    private transient String cache;

    public synchronized void markDirty() {
        dirty = true;
    }

    protected final int limit() {
        return LIMIT;
    }

    public abstract static class Worker {
        protected abstract String executeTask(String input);

        public final String execute(String input) {
            if (input == null || input.isBlank()) {
                throw new IllegalArgumentException("input must not be blank");
            }
            return executeTask(input);
        }
    }

    public interface Plugin {
        int API_VERSION = 1;

        default String name() {
            return normalize(" plugin ");
        }

        static int apiVersion() {
            return API_VERSION;
        }

        static boolean supported(String candidate) {
            return !isBlank(candidate);
        }

        private String normalize(String value) {
            return value.trim();
        }

        private static boolean isBlank(String value) {
            return value == null || value.isBlank();
        }
    }

    private static final class UppercaseWorker extends Worker {
        @Override
        protected String executeTask(String input) {
            return input.toUpperCase(java.util.Locale.ROOT);
        }
    }

    private static final class DemoPlugin implements Plugin {
    }

    public static void main(String[] args) {
        Worker worker = new UppercaseWorker();
        System.out.println(worker.execute("java"));

        Plugin plugin = new DemoPlugin();
        System.out.println(plugin.name());
        System.out.println(Plugin.apiVersion());
        System.out.println(Plugin.supported("demo"));
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac ModifierMatrixDemo.java
java ModifierMatrixDemo
~~~

Exact stdout output:

~~~text
JAVA
plugin
1
true
~~~

The example shows that protected static final is a valid field combination; volatile is used for mutable state; synchronized is a method modifier; final prevents the limit and execute methods from being overridden; and abstract requires subclasses to implement executeTask. In Plugin, API_VERSION is implicitly public static final, name is a default method, apiVersion and supported are static methods, and normalize and isBlank are private helpers. The nested classes use private static final or public static abstract according to their purpose.

## 10. Reading Compiler Errors and Checklist

When the compiler reports an invalid modifier, check in the following order:

1. Declaration kind: top-level type, nested type, field, method, constructor, or local variable?
2. Access level: does this declaration kind allow public, protected, or private?
3. Kind-specific modifiers: transient is only for fields, synchronized is for methods, and sealed/non-sealed are for classes or interfaces.
4. Conflicting combinations: abstract with final/private/static/native/synchronized; final with volatile; or default in a regular class.
5. Inheritance context: sealed/non-sealed are only valid when the relationship with the sealed parent satisfies the rules; abstract methods must be implemented by concrete classes.
6. Implicit modifiers: interface fields are already public static final; regular interface methods are already public abstract; member types in an interface are already public static.
7. Java version: private interface methods require Java 9 or later; the examples in this article target Java 17+.

Do not add a modifier simply because it appears in another similar-looking declaration. Java distinguishes declaration kinds and contexts: a modifier valid for a field may be invalid for a method; a modifier valid for a member class may be invalid for a top-level class; and interface modifiers are not always the same as class modifiers.

## Conclusion

A modifier table is only useful when read alongside the declaration kind and its enclosing context. Identify the member kind, verify the access level, and then check behavioral modifiers and conflicting combinations. Understanding implicit interface modifiers, the differences between class and interface methods, and sealed hierarchy rules helps you write Java APIs that are syntactically valid, readable, and more intentional.
