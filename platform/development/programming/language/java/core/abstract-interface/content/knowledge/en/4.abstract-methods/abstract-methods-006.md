# Uncommon Modifiers That Are Invalid with `abstract` Methods in Java

An `abstract` method has no Java body and needs to be implemented according to the inheritance contract. In addition to the three common conflicts `private`, `static`, and `final`, there are the uncommon modifiers `synchronized`, `native`, and `strictfp`, along with the `default` keyword in interfaces. This article focuses on these uncommon cases and distinguishes them from keywords that are not method modifiers.

## 1. `synchronized abstract`: no body to lock during execution

```java
abstract class Job {
    public synchronized abstract void runJob(); // Compilation error
}
```

`synchronized` controls acquiring the monitor when a method with a body is executed. An abstract declaration does not have a body yet, so an execution locking policy cannot be placed on that declaration. An implementing class can choose to synchronize on its own:

```java
abstract class Job {
    public abstract void runJob();
}

final class SafeJob extends Job {
    @Override
    public synchronized void runJob() {
        System.out.println("Running safely");
    }
}
```

The two classes above are valid declarations. However, `abstract` does not by itself guarantee that every subclass uses `synchronized`; if correctness requires a common threading policy, place that mechanism in a shared concrete method or explicitly design the contract and shared state.

## 2. `native abstract`: two different implementation mechanisms

```java
abstract class NativeBridge {
    public native abstract int callNative(); // Compilation error
}
```

`native int callNative();` can be valid without a Java body because the implementation is provided through a native mechanism such as JNI. When actually called, the program still needs the native library and function to be properly linked; if they are missing, an `UnsatisfiedLinkError` may occur.

Conversely, `abstract int callNative();` requires a Java subclass to provide the body. Two ways of providing an implementation cannot be combined on the same method. Choose `native` when the implementation is in native code, or `abstract` when a Java subclass must implement the contract.

## 3. `strictfp abstract`: a computation modifier does not replace a method body

```java
abstract class Geometry {
    public strictfp abstract double area(); // Compilation error
}
```

`strictfp` was formerly used to constrain floating-point arithmetic semantics. Since Java 17, floating-point arithmetic has strict semantics by default, so `strictfp` on declarations where it is permitted is no longer necessary and may emit a warning. Even so, `strictfp abstract` remains an invalid combination. The declaration `public abstract double area();` is valid.

## 4. `default abstract` in an interface

A regular instance method without a body in an interface is `public abstract` by default:

```java
interface MessageFormatter {
    String format(String text);
}
```

A `default` method, on the other hand, provides a default body:

```java
interface Formatter {
    String format(String text);

    default String wrap(String text) {
        return "[" + format(text) + "]";
    }

    static boolean isBlank(String text) {
        return text == null || text.isBlank();
    }

    private String decorate(String text) {
        return "[" + text + "]";
    }
}
```

`default`, `static`, and `private` in the example all have bodies. The following declaration is invalid:

```java
interface InvalidFormatter {
    default abstract String format(String text); // Compilation error
}
```

`default` requires a default implementation, whereas `abstract` indicates there is no body. In an interface, a `private` method must also have a body; it is an internal helper, not a contract for implementing classes. Do not confuse this `default` keyword with the package-private access level of a class member without an access modifier.

## 5. Keywords that are not method modifiers

Some keywords inherently apply to other elements, so declaring a method with them is invalid whether `abstract` is present or not:

| Keyword | Applies to | Reason |
|---|---|---|
| `volatile` | Field | Not a method modifier |
| `transient` | Field | Controls serialization of a field, not a method |
| `sealed` / `non-sealed` | Class or interface in a sealed hierarchy | Controls which types can extend/implement, does not apply to methods |

For example, `volatile abstract void compute();` is invalid because `volatile` is not a method modifier; `volatile void compute() { ... }` is also invalid. A constructor cannot be declared `abstract` either, because constructors are not overridden like instance methods. There is no `abstract field` or `abstract constructor` in Java.

For comparison, `private`, `static`, and `final` also cannot be combined with an abstract method: private prevents overriding, static uses method hiding instead of instance overriding, and final forbids overriding. An abstract class can still contain private/static/final methods **with a body**; validity is evaluated per declaration.

## 6. Runnable Java 17+ example: valid modifiers on different methods

Save everything to `AbstractModifierDemo.java`:

```java
abstract class Processor {
    protected abstract String transform(String input);

    private String normalize(String input) {
        return input.strip();
    }

    public final String process(String input) {
        return "[" + transform(normalize(input)) + "]";
    }

    public static String version() {
        return "v1";
    }
}

final class UppercaseProcessor extends Processor {
    @Override
    protected String transform(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}

public class AbstractModifierDemo {
    public static void main(String[] args) {
        Processor processor = new UppercaseProcessor();
        System.out.println(processor.process("  Java  "));
        System.out.println(Processor.version());
    }
}
```

Compile and run:

```bash
javac --release 17 AbstractModifierDemo.java
java AbstractModifierDemo
```

Output:

```text
[JAVA]
v1
```

`transform` is the abstract hook that subclasses implement; `normalize` is a private helper with a body; `process` is a concrete final method that fixes the sequence; `version` is a static method with a body. Those modifiers can appear together in an abstract class because they are on separate declarations.

## 7. Quick diagnostic table

| Declaration | Valid? | Interpretation |
|---|---|---|
| `synchronized abstract void run();` | No | No body to execute the synchronization mechanism |
| `native abstract int call();` | No | Native implementation and abstract subclass implementation are two different mechanisms |
| `strictfp abstract double area();` | No | Modifier cannot be combined with abstract |
| `default abstract String format();` in an interface | No | Default method requires a body |
| `private void helper() { ... }` in an abstract class | Yes | Concrete helper, does not require overriding |
| `public final void process() { ... }` in an abstract class | Yes | Concrete method, forbids overriding |
| `static String version() { ... }` in an abstract class | Yes | Class method with a body |

When reading modifier errors, distinguish between three causes: the modifier prevents overriding; the modifier requires a different execution mechanism; or the keyword does not apply to methods. Diagnosing by these groups helps choose the right fix instead of just deleting keywords at random.
