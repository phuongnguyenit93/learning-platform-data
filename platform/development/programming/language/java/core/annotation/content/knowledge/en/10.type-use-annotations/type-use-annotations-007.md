# Receiver Parameter and Annotations on the this Type in Java

## 1. What Is a Receiver Parameter?

Java allows writing a **receiver parameter** to specify the type of the object receiving a call to an **instance method**, or the type of the enclosing object when declaring a constructor of an **inner class**. The primary goal of this syntax is to provide a **location in the source code for attaching annotations to the receiver's type**.

Example:

```java
class Account {
    void print(Account this, String message) {
        System.out.println(message);
    }
}
```

In `void print(Account this, String message)`:

- `Account this` is the **receiver parameter**: it represents the type of the `Account` object receiving the `print` call.
- `String message` is the actual **formal parameter**, which receives the argument when called.
- `Account this` **does not declare a new variable**, **does not accept an extra argument**, and **does not change the parameter count or the signature of the method**.
- Calling `new Account().print("hello")` is valid. No extra `Account` is passed in the argument list.

According to the Java Language Specification (JLS §8.4), the receiver parameter is an optional syntactic construct for representing the receiver's type so that it can be annotated. The presence or absence of a receiver parameter **does not change the runtime behavior** of the method.

This is an important difference from seemingly similar syntax in other languages, where the receiver can be declared as an actual parameter. In Java, the receiver parameter of an instance method is solely a location that can hold a **type-use annotation**.

## 2. Annotation Syntax for the this Type

To annotate the receiver type, define an annotation targeting `ElementType.TYPE_USE`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface ReceiverInfo {
    String value();
}
```

Then apply it to the receiver parameter:

```java
class Mailbox {
    void send(@ReceiverInfo("sender") Mailbox this, String text) {
        System.out.println(text);
    }
}
```

In `@ReceiverInfo("sender") Mailbox this`, the annotation applies to **the type use of `Mailbox` for the receiver**, not to the `send` method declaration and not to the `text` parameter.

For an instance method, the syntax has the form:

```text
ReturnType methodName(
    @TypeUseAnnotation ClassOrInterfaceName this,
    OtherType firstArgument,
    ...
)
```

The `@TypeUseAnnotation` part and other formal parameters are optional; when both a receiver parameter and formal parameters are present, the receiver must appear **at the beginning of the list**. The receiver type must be the class or interface type containing that method itself; the receiver name must be the `this` keyword.

For example, you can write `void send(Mailbox this, String text)` even without an annotation, though writing it this way generally offers no benefit; the most common practical purpose is to attach type-use metadata to the receiver.

### Why Is @Target(TYPE_USE) Needed Instead of PARAMETER?

Java makes a clear distinction:

| Target | Annotates | Example |
| --- | --- | --- |
| `ElementType.TYPE_USE` | A **type-use** location, including the receiver type | `void send(@ReceiverInfo Mailbox this)` |
| `ElementType.PARAMETER` | A **formal parameter declaration** of a method or constructor | `void send(@Input String message)` |
| `ElementType.METHOD` | A **method declaration** | `@Audited void send(...)` |

A receiver parameter **is not a formal parameter** and does not declare a variable. Therefore, an annotation with only `@Target(ElementType.PARAMETER)` is not sufficient to attach to the receiver type. If you want to use the same kind of annotation on both the receiver type and regular parameter declarations, you can consider `@Target({ElementType.TYPE_USE, ElementType.PARAMETER})`; however, this opens up two different application contexts and requires interpreting the metadata accurately.

Error illustration example (does not compile standalone):

```java
@Target(ElementType.PARAMETER)
@interface ParamOnly {}

// ERROR if @ParamOnly is placed on the receiver type:
class WrongExample {
    void run(@ParamOnly WrongExample this) {}
}
```

The compiler rejects this because at the receiver position, the annotation must be valid in a **type context**.

## 3. How Does a Receiver Differ from Regular this?

Let us compare:

```java
class Counter {
    private int value;

    void increase(Counter this, int amount) {
        this.value += amount;
    }
}
```

- `Counter this` in the parameter list is **receiver parameter syntax**; it does not create a new `this` variable.
- `this.value` in the method body is an **expression referring to the current object**, and still works just as in a method without a receiver declaration.
- `amount` is the actual formal parameter.
- `increase(3)` accepts exactly **one argument**; the receiver parameter does not turn it into a two-argument method.
- You cannot assign a value to `this`, because `this` is not a parameter variable defined by this syntax.

**Type-use meaning:** an annotation on `Counter this` expresses a property of the **type of the object receiving the call** in the `increase` method. It does not automatically apply to every `Counter` in the program, nor does it automatically check properties such as immutable, thread-safe, or non-null.

### The Receiver Parameter Is Not a Hidden Parameter to Pass Manually

In Java, when calling an instance method, the expression before the dot already specifies the object receiving the call:

```java
Counter counter = new Counter();
counter.increase(3);
```

The `counter` object is the receiver of the call. Putting `Counter this` in the declaration merely creates a place to represent the receiver type in source code; it **does not add any parameter to the bytecode signature for the caller to supply**. When inspecting the method via reflection, `getParameterCount()` still counts only the formal parameter `amount`.

## 4. Which Methods Are Allowed to Have a Receiver Parameter?

The JLS restricts where a receiver parameter may appear:

1. **Instance methods** declared in a class or interface: may use a receiver parameter with an appropriate declared type.
2. **Constructors of an inner class** not declared in a static context: may use a **qualified receiver parameter** representing the enclosing instance.
3. **Static methods**: may not declare a receiver parameter, because a static method has no receiving object in the instance-method sense.
4. **Constructors of a top-level class, static nested class, local class, or anonymous class**: cannot use a receiver parameter according to the syntax reserved for inner member class constructors.
5. **Ordinary constructors of an outer class itself**: do not have a `ClassName this` receiver parameter. A constructor is creating the object, so there is no receiver in that role.

Invalid example (for error illustration only):

```java
class InvalidReceiver {
    static void utility(InvalidReceiver this) {} // ERROR: static method.

    InvalidReceiver(InvalidReceiver this) {}      // ERROR: top-level constructor.
}
```

In an instance method, the receiver type must match the class or interface declaring the method, and the name must be `this`:

```java
class Printer {
    void print(Printer this) {} // Valid.
    // void wrong(String this) {} // ERROR: incompatible receiver type.
}
```

The snippets in this section are **rule-illustration code**, not a single file intended to be run directly as a whole because invalid examples are intentionally included.

## 5. Complete Java 17+ Example: Receiver Annotation and Reflection

The following program uses only the JDK, defines a custom **TYPE_USE** annotation with `RUNTIME` retention, and reads it via `Method.getAnnotatedReceiverType()`.

Create the file **ReceiverAnnotationDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ReceiverTag {
    String value();
}

public class ReceiverAnnotationDemo {
    private final String prefix;

    public ReceiverAnnotationDemo(String prefix) {
        this.prefix = prefix;
    }

    public String greet(
            @ReceiverTag("greeting receiver")
            ReceiverAnnotationDemo this,
            String name) {
        return prefix + name;
    }

    public String ordinary(String name) {
        return prefix + name;
    }

    public static void utility() {}

    public static void main(String[] args)
            throws NoSuchMethodException {
        Method greetMethod = ReceiverAnnotationDemo.class
                .getDeclaredMethod("greet", String.class);
        AnnotatedType receiver = greetMethod.getAnnotatedReceiverType();
        ReceiverTag tag = receiver.getAnnotation(ReceiverTag.class);

        System.out.println("receiver type=" + receiver.getType().getTypeName());
        System.out.println("receiver tag=" + tag.value());
        System.out.println("formal parameters=" + greetMethod.getParameterCount());
        System.out.println("method tag="
                + greetMethod.isAnnotationPresent(ReceiverTag.class));

        Method ordinaryMethod = ReceiverAnnotationDemo.class
                .getDeclaredMethod("ordinary", String.class);
        System.out.println("ordinary receiver annotations="
                + ordinaryMethod.getAnnotatedReceiverType()
                        .getAnnotations().length);

        Method staticMethod = ReceiverAnnotationDemo.class
                .getDeclaredMethod("utility");
        System.out.println("static receiver="
                + staticMethod.getAnnotatedReceiverType());

        ReceiverAnnotationDemo demo = new ReceiverAnnotationDemo("Hello, ");
        System.out.println(demo.greet("Lan"));
    }
}
```

Compile and run with JDK 17 or later in the directory containing the file:

```bash
javac ReceiverAnnotationDemo.java
java ReceiverAnnotationDemo
```

Expected exact stdout:

```text
receiver type=ReceiverAnnotationDemo
receiver tag=greeting receiver
formal parameters=1
method tag=false
ordinary receiver annotations=0
static receiver=null
Hello, Lan
```

**Line-by-line explanation:**

1. `receiver.getType().getTypeName()` returns the receiver type of `greet`, which here is `ReceiverAnnotationDemo`.
2. `receiver.getAnnotation(ReceiverTag.class)` looks up the annotation directly on the **receiver type**, and then `tag.value()` returns the string `greeting receiver`.
3. `getParameterCount()` equals **1** because `name` is the only formal parameter; `ReceiverAnnotationDemo this` is not counted.
4. `greetMethod.isAnnotationPresent(ReceiverTag.class)` is **false** because `ReceiverTag` targets the **type use of the receiver**, not an annotation on the method declaration.
5. An instance method that does not declare a receiver parameter, such as `ordinary`, still has a receiver type that reflection can represent as an `AnnotatedType` **containing no annotations**. Therefore, the annotation array length is 0.
6. The static method `utility` **has no receiver**. `getAnnotatedReceiverType()` returns `null` for static methods.
7. `demo.greet("Lan")` returns `Hello, Lan` like an ordinary instance method; the annotation does not add any logic by itself.

This is an example of the **ability to store and read type-use metadata**, not an example of altering execution flow with annotations.

## 6. How getAnnotatedReceiverType() Differs from getParameters() and getAnnotatedParameterTypes()

On `java.lang.reflect.Executable`, each API answers a distinct question:

| API | Information Queried |
| --- | --- |
| `getAnnotatedReceiverType()` | The **receiver type** of an instance method or eligible enclosing instance, along with type-use annotations |
| `getParameters()` | The list of **formal parameters** of the method/constructor |
| `getParameterCount()` | The number of formal parameters according to reflection |
| `getAnnotatedParameterTypes()` | The types of the **formal parameters**, along with type-use annotations |
| `getAnnotation(ReceiverTag.class)` on `Method` | Annotations **on the method declaration**, rather than looking up receiver annotations |

The decisive point is that the receiver parameter **is not a formal parameter**. Consequently, do not look for the annotation on the `this` type in `method.getParameters()[0]`; the first element there is the formal parameter `name`.

In a program with an appropriately typed annotation retained at `RUNTIME`, the proper way to read it is typically:

```java
Method method = SomeClass.class.getDeclaredMethod("someMethod");
AnnotatedType receiver = method.getAnnotatedReceiverType();

if (receiver != null) {
    ReceiverTag annotation = receiver.getAnnotation(ReceiverTag.class);
    if (annotation != null) {
        System.out.println(annotation.value());
    }
}
```

This snippet is **only an API-usage pattern**; an actual program requires the `SomeClass` type, the `someMethod` method, and the definition/import of `ReceiverTag`. You should not call `receiver.getAnnotation(...)` without a `null` check when handling static methods or constructors that cannot have a receiver.

### When a Method Does Not Explicitly Declare a Receiver

According to the Java Reflection API, for an **instance method**, `getAnnotatedReceiverType()` can return an `AnnotatedType` **with no annotations**, even if the source code does not write `ClassName this`. Therefore:

- **The receiver object exists in instance method semantics**.
- **Whether a receiver parameter is written in source code is a syntactic choice**.
- **Whether the receiver type has annotations is a separate question**.

You cannot use the condition `getAnnotatedReceiverType() != null` to infer that the programmer necessarily wrote an explicit receiver parameter in the source code.

## 7. Inner Class Constructors: Qualified Receiver Parameters

A **non-static inner member class** may contain a constructor that receives type information about the **enclosing instance** via a qualified receiver parameter. The syntax differs from that of an instance method:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface OwnerTag {
    String value();
}

class Outer {
    class Inner {
        Inner(@OwnerTag("enclosing") Outer Outer.this, int number) {
            System.out.println(number);
        }
    }
}
```

Here:

- `Inner` is a non-`static` inner class declared inside `Outer`.
- `Outer Outer.this` is the **qualified receiver parameter** of the `Inner` constructor; it describes the **type of the `Outer` object enclosing** the new `Inner` object.
- The receiver name must have the form **`Outer.this`**, where `Outer` is the simple name of the immediately enclosing type; the declared receiver type must match the enclosing type.
- `int number` is the actual formal parameter in source code. When instantiating, the user writes something like `outer.new Inner(5)` and **does not supply an extra argument named `Outer.this`**.

This snippet **illustrates the structure**. If you want to read `@OwnerTag` using reflection, the annotation needs `@Retention(RUNTIME)`; the current snippet does not declare a retention policy, so it defaults to `CLASS`.

**Detail to distinguish:** The JVM may use a synthetic/hidden parameter when executing an inner class constructor to pass the enclosing instance. This is part of how inner classes are compiled and can appear in constructor reflection. It **is not** the receiver parameter `Outer Outer.this` written by the programmer in the source code. Do not draw conclusions about the runtime parameter count of an inner class constructor solely from the receiver parameter syntax while ignoring compiler-generated parameters.

### Why Can't You Write a Receiver in a Top-Level Class Constructor?

A top-level class constructor is constructing the current object; in Java, a receiver parameter does not serve the role of describing the type of the object being created in that way. The JLS allows a receiver parameter only in constructors of eligible inner classes to annotate the enclosing instance type, and the compiler rejects other constructor cases.

## 8. Retention, Class Files, and Type Annotations

`@Target(TYPE_USE)` allows an annotation to appear in **type-use contexts**, including the receiver type. **`@Retention`** determines whether the metadata is kept across the compile/runtime lifecycle:

| Retention | Meaning for Type Annotations on the Receiver |
| --- | --- |
| `SOURCE` | Used for source/compile-time processing; not retained in the class file per the retention policy |
| `CLASS` | Metadata is retained in the class file at supported positions, but runtime reflection does not expose it in the RUNTIME manner |
| `RUNTIME` | The annotation on the receiver type can be retrieved via `getAnnotatedReceiverType()` and `AnnotatedType.getAnnotation()` |

If `@Retention` is not declared, the default is **`RetentionPolicy.CLASS`**, so to use reflection as in the Section 5 example, `RUNTIME` must be declared explicitly.

The tool `javap -v ReceiverAnnotationDemo` (after compilation) can help inspect type-annotation metadata at the class-file level. Runtime type annotations are typically represented via attributes such as `RuntimeVisibleTypeAnnotations` and the location identifying the method receiver. Do not confuse them with method-declaration annotations retrieved directly by `Method.getAnnotation(...)`.

## 9. TYPE_USE Metadata Does Not Automatically Enforce Constraints

Suppose a library defines:

```java
@Target(ElementType.TYPE_USE)
@interface ReadOnly {}

class Document {
    void inspect(@ReadOnly Document this) {
        // ...
    }
}
```

Attaching `@ReadOnly` to the receiver type **does not automatically make Document immutable**. It is purely static information; any effect depends on whether a compiler plugin, static analyzer, framework, or custom rule reads and interprets that annotation.

A system checking nullness, access permissions, or receiver state might design annotations on the `this` type as part of a contract, but **core Java does not enforce by default** the requirements expressed by arbitrary annotations. Nor does having an annotation on the receiver turn the method into a static method or cause it to take an extra argument.

If the problem is simply describing the called method or recording audit metadata at the method level, `@Target(METHOD)` may be more appropriate. When you want to describe the **type of the object receiving the call**, a type-use annotation on the receiver provides a more accurate model.

## 10. Common Pitfalls

**1. Treating the receiver parameter as a formal parameter.** `ClassName this` is not a variable that receives an argument and does not increase the parameter count when calling the method. `getParameters()` does not return the receiver parameter in the list of formal parameters.

**2. Using @Target(PARAMETER) for the receiver.** Annotating the receiver belongs to a **type-use context**. If an annotation applies only to PARAMETER, the compiler will reject it at the receiver position.

**3. Writing the receiver after a regular parameter.** If declaring a receiver alongside formal parameters, the receiver must come first in the list.

**4. Writing a receiver in a static method.** A static method has no instance receiver, so declaring `ClassName this` there is a compile-time error.

**5. Writing a receiver in a top-level constructor.** Only constructors of eligible non-static inner classes can use an enclosing-instance receiver. Top-level constructors do not allow it.

**6. Confusing a method receiver with a constructor receiver.** An instance method uses the form `CurrentType this`. An inner class constructor uses the qualified form `EnclosingType EnclosingName.this`.

**7. Querying receiver annotations using Method.getAnnotation.** That API returns annotations on the method declaration. You need to obtain the `AnnotatedType` from `getAnnotatedReceiverType()` to query type-use annotations.

**8. Assuming a non-null AnnotatedType proves the source code has a receiver parameter.** An instance method without an explicit declaration can still have a receiver `AnnotatedType` with no annotations. Inspect metadata according to its actual meaning.

**9. Forgetting @Retention(RUNTIME) when using reflection.** A TYPE_USE annotation without an explicit retention policy defaults to CLASS and is not visible via runtime reflection.

**10. Treating type-use annotations as an automatic checking mechanism.** Java only provides the syntax, language constraints, and metadata query capability; business logic processing must be carried out by supporting components.

**11. Assuming every inner class constructor has only the parameter count shown in source code.** The enclosing-instance mechanism can generate a parameter in bytecode/reflection; this differs from the receiver syntax and must be distinguished.

## 11. Self-Check Exercises

1. In `ReceiverAnnotationDemo`, change the value of `@ReceiverTag("greeting receiver")` to `@ReceiverTag("service receiver")`, recompile, and predict the `receiver tag=...` line.
2. Add a formal parameter `int times` to `greet`; update `getDeclaredMethod` and `getParameterCount()`. Explain why the parameter count increases from 1 to 2 even though the receiver parameter remains unchanged.
3. Try changing `greet` to `static` while keeping `ReceiverAnnotationDemo this`; record the compiler error and explain it.
4. Try changing `@Target(ElementType.TYPE_USE)` on `ReceiverTag` to `@Target(ElementType.PARAMETER)`. Find the cause of the error on the receiver syntax and distinguish it from the formal parameter `name`.
5. Remove `@Retention(RetentionPolicy.RUNTIME)` from `ReceiverTag`. Before calling `tag.value()`, modify the code to check `tag == null` and explain why reflection cannot read the default CLASS annotation.
6. Add another instance method without an explicit receiver declaration. Compare `getAnnotatedReceiverType()`, its annotations, and the return value on a static method.
7. For the `Outer.Inner` snippet, explain the difference between `Outer Outer.this` in the constructor declaration and the expression `outer.new Inner(5)` in object-creation code.

## 12. Authoritative References

- [JLS §8.4 – Method Declarations and Receiver Parameter (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4): defines the receiver parameter, valid locations, and required type and name.
- [JLS §9.7.4 – Where Annotations May Appear (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): distinguishes declaration annotations from type-use annotations.
- [Executable.getAnnotatedReceiverType() (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getAnnotatedReceiverType()): reflection result for the receiver type, both with and without annotations.

**Conclusion:** A receiver parameter is the syntax that enables Java to attach a **TYPE_USE annotation to the type of `this`** or to the enclosing instance type of an inner class constructor. It **does not declare a new formal parameter, does not change calls, and does not automatically create runtime behavior**. To read metadata at runtime, use an annotation with `RUNTIME` retention along with `getAnnotatedReceiverType()`, while clearly distinguishing it from `getParameters()` and `Method.getAnnotation()`.
