# `static final` Constants and Conditions for Compile-Time Constants in Java

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **`static`**, **`final`**, **`static final`**, **constant variable**, and **constant expression** according to the Java Language Specification (JLS).
- Explain the **exact conditions** for a `static final` field to be considered a *compile-time constant*: `primitive` or `String` type, `final` modifier, and an initializer that is a *constant expression*.
- Predict which fields are evaluated by the compiler from literals, operators, casts, and other constants, and which fields must be evaluated **at runtime**, even though both carry `static final`.
- Distinguish **not being able to reassign a field** from **immutability of the object** referenced by the field.
- Explain the impact on **class initialization**, `ConstantValue`, client **value inlining**, and the risks of changing API constants without recompiling the code that uses them.
- Recognize cases that require a **constant expression**, such as certain forms of `case` labels, annotation element values, and narrowing assignment from a constant integer.
- Understand `static final` in interfaces, fields assigned in a static block, local `final` variables, and the limitation that "final does not mean compile-time".
- Choose among compile-time constants, runtime-initialized fields, accessors, dynamic configuration, and immutable value objects to design clear, maintainable APIs.
- Compile and run Java 17+ examples yourself, read stdout accurately, and classify compiler errors.

## 1. First: `static` and `final` Do Two Different Things

Consider a class:

~~~java
class ServerConfig {
    static int activeConnections;
    final int serverId;
    static final int DEFAULT_PORT = 8080;

    ServerConfig(int serverId) {
        this.serverId = serverId;
    }
}
~~~

This is an **illustrative declaration snippet**, not a program with `main`.

- `static int activeConnections`: a field belonging to the **class**, shared within the same runtime class; write operations to it are permitted according to access rules and context.
- `final int serverId`: an **instance field**, where each instance has its own value; once assigned properly according to `final` initialization rules, the field cannot be reassigned.
- `static final int DEFAULT_PORT`: a class field **and** one that cannot be reassigned after valid initialization.

**However:** the two modifiers `static final` alone are **not enough** to conclude that a field is a **compile-time constant**. For example:

~~~java
static final int PORT_A = 8080;
static final int PORT_B = Integer.parseInt("8080");
~~~

Both are `static final int`, yet:

- `PORT_A` receives its value from an integer literal; it is a **constant variable**.
- `PORT_B` calls the `Integer.parseInt` method at runtime; it is **not** a constant variable.

The two fields may produce the **same number 8080** after initialization, but **when and how the compiler/JVM handles reading them can differ**.

### 1.1. Summary of the Four Concepts

| Concept | Core Meaning | Example |
| --- | --- | --- |
| `static` | Member associated with the class, not attached individually to each instance | `static int count` |
| `final` | Variable/field that cannot be reassigned after valid assignment | `final String name` |
| `static final` | Class-level field that cannot be reassigned after valid initialization | `static final List<String> NAMES` |
| **Constant variable** | A **`final` variable** of primitive or `String` type, initialized with a **constant expression** | `static final int MAX = 10` |

**A common class-level constant** is usually written as `public static final` or `private static final`. `public/private` determines accessibility; it **does not determine** whether the value is evaluated at compile time.

## 2. Exact Definition of a Constant Variable

According to **JLS `4.12.4**, a *constant variable* is **a `final` variable of primitive type or `String`, initialized with a *constant expression* (`15.29 in Java 17)**.

Three conditions must hold simultaneously:

1. **`final`:** the variable/field is declared `final`.
2. **Type:** one of the eight primitive types (`byte`, `short`, `int`, `long`, `char`, `float`, `double`, `boolean`) **or `java.lang.String`**.
3. **Initializer:** initialized with an expression belonging to the set of *constant expressions* defined by the language, not merely an expression that "looks easy to compute".

`static` **does not appear as a requirement in the general definition**, because a **local final variable** can also be a constant variable. For the topic of **class-level** constants, we add `static` to apply that definition to a static field.

### 2.1. Examples That Satisfy All Three Conditions

~~~java
static final int MAX_USERS = 100;
static final long TIMEOUT_MS = 1_000L;
static final char SEPARATOR = ':';
static final boolean DEBUG = false;
static final double PI_APPROX = 3.14;
static final String APP_NAME = "JavaCore";
static final int QUADRUPLE = MAX_USERS * 4;
static final String HEADER = APP_NAME + " v1";
~~~

The initializers here are literals, names of constant variables, or valid constant expression operations. If these declarations are placed inside a valid class, they are all **constant variables**.

Uppercase names and underscores are a **naming convention**, not a condition the compiler uses to identify constant variables. `static final int maxUsers = 100;` is still a constant variable even though it does not follow the convention.

### 2.2. Examples That Do Not Satisfy the Conditions, Even With `static final`

~~~java
static final Integer BOXED = 100;
static final int FROM_METHOD = Integer.parseInt("100");
static final String FROM_PROPERTY =
        System.getProperty("app.name", "JavaCore");
static final String RUNTIME_TEXT = new String("JavaCore");
static final int GENERATED = generate();
static final java.util.List<String> TAGS =
        java.util.List.of("java", "core");
~~~

Assume the `generate()` method exists and returns `int`. These fields are **not constant variables** because:

- `Integer` and `List<String>` are not of primitive or `String` type.
- Method calls such as `Integer.parseInt`, `System.getProperty`, and `generate()` are not constant expressions.
- `new String("JavaCore")` creates an object at runtime, even though its contents are known beforehand.

**Note:** `String` is the **only reference type permitted** in the definition of a constant variable; wrapper types such as `Integer`, `Boolean`, and `Long` are not included in the list simply because they are immutable.

### 2.3. Quick Classification Table

| Declaration | Has `static final`? | Constant variable? | Reason |
| --- | --- | --- | --- |
| `static final int A = 5;` | Yes | **Yes** | `int` + literal |
| `static final String B = "Hi";` | Yes | **Yes** | `String` + literal |
| `static final int C = 2 + 3 * 4;` | Yes | **Yes** | Constant expression |
| `static final int D = (int) 3.9;` | Yes | **Yes** | Cast in a constant expression |
| `static final int E = Math.abs(-5);` | Yes | **No** | Method call |
| `static final Integer F = 5;` | Yes | **No** | Wrapper type |
| `static final String G = "A".toLowerCase();` | Yes | **No** | Method call |
| `static final String H = "A" + "B";` | Yes | **Yes** | Concatenation of constant strings |
| `static final String I = new String("AB");` | Yes | **No** | `new` expression |
| `static final int J; static { J = 5; }` | Yes | **No** | Field has no constant expression initializer at declaration |
| `static int K = 5;` | No | **No** | Missing `final` |
| `final int local = 5;` | Not a static field | **Yes** | Local final constant variable |

## 3. What Can a Constant Expression Contain?

*Constant expression* is defined in **JLS `15.29 of Java 17**. This set of expressions consists of limited constructs with appropriate operands, not every pure expression without side effects.

Common components include:

- Literals of primitive types and `String`, such as `123`, `42L`, `true`, `'X'`, `"Java"`.
- Parentheses `( ... )`.
- Unary operators such as `+`, `-`, `~`, `!` when valid for the type.
- Arithmetic operators `+`, `-`, `*`, `/`, `%`; bitwise operators `&`, `|`, `^`; shift operators `<<`, `>>`, `>>>`.
- Comparison, equality, logical `&&`/`||`, and ternary `?:` operators in the types and cases permitted by the rules.
- Appropriate casts to primitive types or `String` in a constant-expression context.
- Simple names or qualified names **referencing constant variables**.
- String concatenation `+` when the operands are appropriate constant expressions.

Expressions **outside** this set include ordinary method calls, `new` object creation, reading mutable fields, assignments, `++`/`--`, and expressions that depend on runtime values.

### 3.1. Example Program on Constant Operations

Save **`ConstantExpressionDemo.java`**:

~~~java
public class ConstantExpressionDemo {
    static final int BASE = 7;
    static final int DOUBLE = BASE * 2;
    static final int MASK = 1 << 3;
    static final int ABS_BY_TERNARY = BASE > 0 ? BASE : -BASE;
    static final char LETTER = (char) ('A' + 2);
    static final boolean ALLOWED = BASE > 5 && MASK == 8;
    static final String TEXT = "value=" + DOUBLE + ",ok=" + ALLOWED;

    public static void main(String[] args) {
        System.out.println("double=" + DOUBLE);
        System.out.println("mask=" + MASK);
        System.out.println("ternary=" + ABS_BY_TERNARY);
        System.out.println("letter=" + LETTER);
        System.out.println("allowed=" + ALLOWED);
        System.out.println(TEXT);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ConstantExpressionDemo.java
java ConstantExpressionDemo
~~~

**Exact stdout:**

~~~text
double=14
mask=8
ternary=7
letter=C
allowed=true
value=14,ok=true
~~~

Each initializer is evaluated from literals, operators, and constant variables, **without needing to call a runtime method** to compute the result. The `TEXT` line concatenates constant expressions into a String.

### 3.2. Same Result, Different Constant Variable Status

~~~java
static final int FIRST = 2 + 5;
static final int SECOND = Math.addExact(2, 5);
~~~

`FIRST` is a compile-time constant; `SECOND` is **not**, because `Math.addExact` is a method call, even though it obviously returns 7. Do not infer "the compiler can optimize it" = "JLS semantics call it a constant expression".

The compiler/JIT may perform various runtime optimizations; that **does not change the language definition** of a constant variable.

## 4. Program Comparing Compile-Time and Runtime `static final`

Save **`StaticFinalClassificationDemo.java`**:

~~~java
public class StaticFinalClassificationDemo {
    static final int LITERAL = 12;
    static final int EXPRESSION = LITERAL * 2;
    static final String NAME = "Java" + "17";

    static final int RUNTIME_INT = makeInt();
    static final String RUNTIME_STRING = makeString();
    static final Integer BOXED = 42;

    private static int makeInt() {
        System.out.println("makeInt called");
        return 24;
    }

    private static String makeString() {
        System.out.println("makeString called");
        return "Java17";
    }

    static {
        System.out.println("static block finished");
    }

    public static void main(String[] args) {
        System.out.println("literal=" + LITERAL);
        System.out.println("expression=" + EXPRESSION);
        System.out.println("name=" + NAME);
        System.out.println("runtime int=" + RUNTIME_INT);
        System.out.println("runtime string=" + RUNTIME_STRING);
        System.out.println("boxed=" + BOXED);
    }
}
~~~

Commands:

~~~bash
javac StaticFinalClassificationDemo.java
java StaticFinalClassificationDemo
~~~

Output:

~~~text
makeInt called
makeString called
static block finished
literal=12
expression=24
name=Java17
runtime int=24
runtime string=Java17
boxed=42
~~~

**Exact explanation of the timing:**

- The `StaticFinalClassificationDemo` class contains `main`, so the JVM must initialize the class **before** invoking `main`; therefore, the runtime field initializers and static block print before the `literal=12` line.
- `LITERAL`, `EXPRESSION`, and `NAME` are constant variables.
- `RUNTIME_INT` and `RUNTIME_STRING` are assigned from method calls, not compile-time constants.
- `BOXED` is an `Integer`, not a primitive/String, so it is not a constant variable.
- Regardless of whether the fields have the same or different values, **the fact that the class is already initialized before `main`** can obscure the difference in class-initialization triggers if you only look at this program's output.

To observe that **merely reading a constant variable does not initialize the declaring class**, use the next example with a separate class.

## 5. Reading a Compile-Time Constant May Not Initialize the Class

This is an important distinction in **JLS `12.4.1**: reading a static field that is a **constant variable** does not require initializing the class/interface that declares it. The compiler can embed the **constant value** directly into the caller's code.

Conversely, reading a static field that is **not** a constant variable can trigger initialization of the class that declares it.

Save **`ConstantVsRuntimeInitDemo.java`**:

~~~java
public class ConstantVsRuntimeInitDemo {
    static class Settings {
        static final int PORT = 8080;
        static final String NAME = "service";

        static final int PORT_FROM_METHOD = portFromMethod();

        static {
            System.out.println("Settings static block");
        }

        private static int portFromMethod() {
            System.out.println("portFromMethod called");
            return 8080;
        }
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        System.out.println("port=" + Settings.PORT);
        System.out.println("name=" + Settings.NAME);
        System.out.println("before runtime field");
        System.out.println("runtime port=" + Settings.PORT_FROM_METHOD);
        System.out.println("after runtime field");
    }
}
~~~

Compile and run:

~~~bash
javac ConstantVsRuntimeInitDemo.java
java ConstantVsRuntimeInitDemo
~~~

Output:

~~~text
main starts
port=8080
name=service
before runtime field
portFromMethod called
Settings static block
runtime port=8080
after runtime field
~~~

**Explanation:**

1. The JVM initializes the outer class to run `main`; the nested class `Settings` is a separate runtime class.
2. `Settings.PORT` and `Settings.NAME` are constant variables, so these two reads do **not** trigger `Settings` initialization.
3. `Settings.PORT_FROM_METHOD` is a static final field, yet **not** a constant variable. Reading it for the first time forces `Settings` initialization.
4. The field initializer `portFromMethod()` executes in class-body order, and the static block executes afterward.
5. The static final fields have been properly initialized. `Settings` will not run its static initializer again merely because one of the fields is read a subsequent time.

### 5.1. Do Not Confuse "Field Accessed" With "Field Recomputed"

A `static final int PORT_FROM_METHOD` is computed during class initialization, and then the field's value is retained; subsequent reads do not automatically invoke `portFromMethod()` again.

Conversely, if a **static method** `currentPort()` calls `System.getProperty` each time, each call can read a new runtime configuration. An accessor method and a static final field carry different change contracts.

### 5.2. A Class Must Still Be Initialized in Certain Situations Even If It Only Has Constants

Creating an instance with `new Settings()`, calling an applicable static method, or using reflection with initialization enabled can cause `Settings` to be initialized according to the rules, even if only constant variables were read beforehand. The accurate statement is **"reading a constant variable does not itself require initialization"**, not "a class with constants will never be initialized".

## 6. `static final` Assigned in a Static Block: Final, Yet Not a Constant Variable

A `static final` field can be a **blank final field** and then be assigned in a static initializer:

~~~java
class Limits {
    static final int DEFAULT_LIMIT;

    static {
        DEFAULT_LIMIT = 25;
    }
}
~~~

Although the value is hardcoded as 25, `DEFAULT_LIMIT` does not have a **constant expression initializer directly at the field declaration**, so it is not a constant variable under the JLS definition.

It is still `static final`: Java requires one valid assignment during class initialization, satisfying definite assignment rules, and it cannot be arbitrarily reassigned.

### 6.1. Runnable Example

Save **`BlankFinalStaticDemo.java`**:

~~~java
public class BlankFinalStaticDemo {
    static class Limits {
        static final int DIRECT = 25;
        static final int FROM_BLOCK;

        static {
            FROM_BLOCK = 25;
            System.out.println("Limits initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("direct=" + Limits.DIRECT);
        System.out.println("before from block");
        System.out.println("from block=" + Limits.FROM_BLOCK);
        System.out.println("after from block");
    }
}
~~~

Commands:

~~~bash
javac BlankFinalStaticDemo.java
java BlankFinalStaticDemo
~~~

Output:

~~~text
direct=25
before from block
Limits initialized
from block=25
after from block
~~~

**Both values are 25**, yet their semantics differ:

- `DIRECT` is a constant variable; reading it does not itself initialize `Limits`.
- `FROM_BLOCK` is not a constant variable; reading it triggers initialization, runs the static block, and prints `Limits initialized`.

Therefore, **the condition "initializer is a constant expression" is a crucial part** and cannot be replaced by "the actual value observed at runtime is a fixed number".

### 6.2. Cannot Use a Direct Initializer and Reassign in a Static Block

~~~java
class Invalid {
    static final int LIMIT = 25;

    static {
        // LIMIT = 30; // Invalid: final field has already been assigned.
    }
}
~~~

The example intentionally comments out the erroneous line so the remaining code stays valid. `final` prevents reassigning the field after a valid assignment; a static block is not an exception that grants permission to "reset final".

## 7. `final` on Local Variables: Can Also Be a Constant Variable

The definition of a constant variable **does not require `static`**. A local final primitive/String initialized with a constant expression is also a constant variable:

~~~java
final int LIMIT = 10;
final String PREFIX = "ITEM";
~~~

If these two declarations are inside a method, they are **local constant variables**. The compiler can use them in contexts that require a constant expression according to the rules.

Conversely:

~~~java
final int fromArgument = Integer.parseInt("10");
final String fromMethod = System.getProperty("prefix", "ITEM");
~~~

These two local finals are **not** constant variables because their initializers are not constant expressions, even if the author never reassigns them again.

**Distinguish `effectively final`:** a variable not declared `final` that is never reassigned can be captured by a lambda under the effectively final rule; this **does not turn it into a constant variable** under the definition that requires the `final` modifier.

### 7.1. Program Demonstrating Local Final and Switch Labels

Save **`LocalConstantSwitchDemo.java`**:

~~~java
public class LocalConstantSwitchDemo {
    static String category(int code) {
        final int LOW = 1;
        final int HIGH = LOW + 2;

        return switch (code) {
            case LOW -> "low";
            case HIGH -> "high";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(category(1));
        System.out.println(category(3));
        System.out.println(category(2));
    }
}
~~~

Compile and run with Java 17:

~~~bash
javac LocalConstantSwitchDemo.java
java LocalConstantSwitchDemo
~~~

Output:

~~~text
low
high
other
~~~

`LOW` and `HIGH` are local constant variables, so they are validly used as `case` constants for a switch on `int`.

### 7.2. A `final` Parameter Does Not Mean a Compile-Time Constant

~~~java
static String classify(final int value) {
    return switch (value) {
        case 1 -> "one";
        default -> "other";
    };
}
~~~

`value` is a **parameter** assigned when the method is called; the `final` modifier only prevents reassigning the parameter inside the body. Its value is runtime input, so `case value -> ...` cannot be used as a compile-time constant label.

## 8. Using Constants in `switch` and Annotations

Some Java syntax constructs require a **compile-time constant expression**. Two commonly encountered groups are:

1. **`case` labels** in traditional switches or switch expressions for eligible primitive integral/String types, according to the rules of each switch form.
2. **Annotation element values** when the element type is primitive or `String`; they must satisfy the annotation constant expression rules.

### 8.1. Example of `switch` With a Static Final Constant

Save **`StaticFinalSwitchDemo.java`**:

~~~java
public class StaticFinalSwitchDemo {
    static final int STATUS_NEW = 1;
    static final int STATUS_DONE = 2;

    static String describe(int status) {
        return switch (status) {
            case STATUS_NEW -> "new";
            case STATUS_DONE -> "done";
            default -> "unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(1));
        System.out.println(describe(2));
        System.out.println(describe(5));
    }
}
~~~

Run:

~~~bash
javac StaticFinalSwitchDemo.java
java StaticFinalSwitchDemo
~~~

Output:

~~~text
new
done
unknown
~~~

If you change `STATUS_DONE` to `static final int STATUS_DONE = Integer.parseInt("2");`, it is still `static final` yet **not** a constant variable; using it as a case label in an `int` switch on Java 17 is **invalid**.

### 8.2. Example of an Annotation With a Constant String

Save **`AnnotationConstantDemo.java`**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

public class AnnotationConstantDemo {
    static final String DESCRIPTION = "Demo" + "API";

    @Retention(RetentionPolicy.RUNTIME)
    @interface Label {
        String value();
    }

    @Label(DESCRIPTION)
    static class Service {
    }

    public static void main(String[] args) {
        Label label = Service.class.getAnnotation(Label.class);
        System.out.println(label.value());
    }
}
~~~

Commands:

~~~bash
javac AnnotationConstantDemo.java
java AnnotationConstantDemo
~~~

Output:

~~~text
DemoAPI
~~~

Here `DESCRIPTION` is a static final String constant variable; it can be used as the value of a `String` annotation element. If you replace the initializer with `"DemoAPI".toString()`, that is a method call and is no longer a constant expression for this purpose.

### 8.3. Not Every Annotation Element Is a String/Primitive

Annotations can have element types such as a `Class` literal, enum, another annotation, or arrays of valid types. They have their **own rules** for annotation values; do not force every case into the definition "a constant variable is primitive or String".

For example, an enum annotation element requires an enum constant appropriate to the context; a String constant variable cannot be used in its place.

## 9. Compile-Time Constant Integers and Narrowing Conversion

A useful Java rule: in an **assignment context**, implicit narrowing conversions from an `int` constant expression to `byte`, `short`, or `char` are allowed if **the constant value is representable** in the target type; JLS `5.2 explains this in detail.

~~~java
byte small = 100;        // Valid: constant int 100 fits in byte.
short size = 20_000;     // Valid: fits in short.
char letter = 65;        // Valid: char can represent 65.
~~~

These are illustrative declarations inside an appropriate method or class.

### 9.1. A `final int` Constant Can Also Be Narrowed in Assignment

~~~java
final int VALUE = 127;
byte result = VALUE; // Valid: constant variable VALUE = 127.
~~~

However:

~~~java
int runtimeValue = 127;
// byte result = runtimeValue; // Does not automatically narrow a regular int.

final int TOO_LARGE = 128;
// byte invalid = TOO_LARGE;   // Error: 128 is outside the byte range.
~~~

The compiler seeing that a regular variable has the value 127 is **not enough** if it is not a constant expression semantically. Similarly, `final int value = methodReturning127();` does not allow the narrowing conversion above merely because the method returns 127 at runtime.

### 9.2. Runnable Example

Save **`ConstantNarrowingDemo.java`**:

~~~java
public class ConstantNarrowingDemo {
    static final int MAX_BYTE = 127;
    static final int LETTER_CODE = 65;

    public static void main(String[] args) {
        byte small = MAX_BYTE;
        char letter = LETTER_CODE;

        final int limit = 12;
        short shortValue = limit;

        System.out.println("byte=" + small);
        System.out.println("char=" + letter);
        System.out.println("short=" + shortValue);
    }
}
~~~

Run:

~~~bash
javac ConstantNarrowingDemo.java
java ConstantNarrowingDemo
~~~

Output:

~~~text
byte=127
char=A
short=12
~~~

**Important:** This rule applies to contexts permitted by the JLS. A **method invocation context** does not automatically perform `int` → `byte` narrowing merely because an integer literal lies within the byte range:

~~~java
static void acceptByte(byte value) {
    System.out.println(value);
}

// Inside a method:
// acceptByte(100);       // Invalid: int -> byte narrowing does not apply automatically.
// acceptByte((byte)100);  // Valid: explicit cast.
// byte b = 100;
// acceptByte(b);          // Valid: the argument already has type byte.
~~~

Do not conflate variable assignment rules with method overload resolution rules.

## 10. String Compile-Time Constants and `==`

For String, compile-time constant expressions have a noticeable effect because **constant strings are interned** according to Java rules.

Save **`ConstantStringIdentityDemo.java`**:

~~~java
public class ConstantStringIdentityDemo {
    static final String COMPILED = "Ja" + "va";
    static final String RUNTIME = new String("Java");

    public static void main(String[] args) {
        String literal = "Java";

        System.out.println("compiled equals=" + COMPILED.equals(literal));
        System.out.println("compiled identity=" + (COMPILED == literal));

        System.out.println("runtime equals=" + RUNTIME.equals(literal));
        System.out.println("runtime identity=" + (RUNTIME == literal));
    }
}
~~~

Compile and run:

~~~bash
javac ConstantStringIdentityDemo.java
java ConstantStringIdentityDemo
~~~

Output:

~~~text
compiled equals=true
compiled identity=true
runtime equals=true
runtime identity=false
~~~

- `"Ja" + "va"` is a compile-time constant string expression with the same content as the literal `"Java"` and is interned under Java semantics. Therefore, the two references in the comparison expression here refer to the same String object.
- `new String("Java")` creates a new String object (distinct from the interned literal), even though the content is identical.
- `String.equals` compares contents according to the String contract, whereas `==` compares object identity.

**Do not overgeneralize:** You should not use `==` to compare application string contents. Two strings with identical contents received from a file, input, or a method can be two different objects. Use `equals`, or `Objects.equals` when null is possible.

### 10.1. Compile-Time Concatenation Differs From Runtime Concatenation

~~~java
static final String ONE = "A" + 1;
static final String TWO = "A" + Integer.toString(1);
~~~

`ONE` is a constant variable, whereas `TWO` is not, because `Integer.toString(1)` is a method call. Having the same result `"A1"` does not mean having the same compile-time condition.

## 11. The Java Compiler Can Inline Constants Into the Caller's Bytecode

When a client writes:

~~~java
System.out.println(Api.LIMIT);
~~~

and `Api.LIMIT` is a **static final primitive/String constant variable** with value 10, the compiler can **inline the value 10 directly into the client's bytecode**, instead of emitting a runtime field-read instruction.

This is not merely a "hint-like" optimization: the JLS defines the semantics of compile-time constants, and Java has related binary compatibility rules. In particular, already-compiled code may still use the **old value** if only the library containing the constant is updated without recompiling the client.

### 11.1. Demonstrating Two Packages: Updating the Library Without Recompiling the Client

Create the directory structure:

~~~text
project/
  lib/
    Api.java
  client/
    Main.java
~~~

Initial content of **`lib/Api.java`**:

~~~java
package lib;

public class Api {
    public static final int LIMIT = 10;
}
~~~

Content of **`client/Main.java`**:

~~~java
package client;

import lib.Api;

public class Main {
    public static void main(String[] args) {
        System.out.println("limit=" + Api.LIMIT);
    }
}
~~~

From the `project` directory, compile both:

~~~bash
javac -d out lib/Api.java client/Main.java
java -cp out client.Main
~~~

**First stdout:**

~~~text
limit=10
~~~

Now **edit only `lib/Api.java`** to:

~~~java
package lib;

public class Api {
    public static final int LIMIT = 20;
}
~~~

Then **recompile only the library**, without recompiling the client:

~~~bash
javac -d out lib/Api.java
java -cp out client.Main
~~~

**Stdout can still be (and is, with standard Java compilers in this example):**

~~~text
limit=10
~~~

Finally, recompile the client so that it picks up the new constant:

~~~bash
javac -cp out -d out client/Main.java
java -cp out client.Main
~~~

Output:

~~~text
limit=20
~~~

**This is a two-step compilation scenario for demonstration.** Do not place two versions of `Api.java` simultaneously in the same directory and expect them to build as two separate classes. When practicing, modify the file contents and run the commands in sequence.

### 11.2. Why Does the Client Still Use 10 When Api Was Changed to 20?

During the first compilation of the client, `Api.LIMIT` was the compile-time constant 10. The client's bytecode can use the embedded 10. Replacing `Api.class` alone does not rewrite the bytecode of `client.Main`.

This is a case of **a library change that does not break linking yet does not update the value observed by older clients**. For `public static final` constants of primitive/String type, **changing the value may require recompiling all code that uses the constant** if you want it to receive the new value.

### 11.3. Inspecting With `javap`

You can run:

~~~bash
javap -c -classpath out client.Main
javap -v -classpath out lib.Api
~~~

`javap -c` displays bytecode disassembly; `javap -v` provides detailed classfile information. For an eligible constant field, you may see the `ConstantValue` metadata; in the client, the call that prints the limit may use an instruction that loads the constant value instead of `getstatic` to read `Api.LIMIT`.

**Do not rely on the exact instruction-by-instruction bytecode text in this example**, because formatting and some details can vary by compiler/version. Rely on the principle: already-compiled clients can retain the old constant value.

## 12. `ConstantValue` and JVM Phases: Understanding the Scope Accurately

At the JVM level, a class goes through phases commonly described as **loading**, **linking** (which includes preparation), and **initialization**.

For static constant variables of primitive/String type with an appropriate `ConstantValue`, the value is handled at the phase related to **preparation** according to the JVM specification. Other static fields generally hold their default values before the class's runtime initializers execute.

This is why practical examples show that:

- Reading a constant variable from other code may not trigger the static initializer block.
- A static final field initialized via a method call is assigned its result only after running the runtime initializer when the class is initialized.
- In a complex initialization dependency cycle, a static field whose initializer has not yet run may still hold a default value such as `0`/`null`.

**Important:** Do not oversimplify this as "every `static final` is set to its true value by the JVM before the class is initialized" — that is **false** for runtime-computed fields.

### 12.1. `final` Does Not Bypass Initialization Order

~~~java
class Example {
    static final int FROM_METHOD = calculate();

    static int calculate() {
        return 7;
    }
}
~~~

`FROM_METHOD` still depends on class initialization. `final` only imposes a constraint on assigning the field; it does not turn a method call into a constant expression.

### 12.2. Constant Variables Declared in an Interface

Every field declared directly in an interface is implicitly `public static final`. However, its initializer can still be a **runtime expression**, so not every interface field is a constant variable according to the JLS.

For example:

~~~java
interface Options {
    int TIMEOUT = 30;
    int COMPUTED = compute();

    static int compute() {
        return 15;
    }
}
~~~

`TIMEOUT` is a constant variable, whereas `COMPUTED` is not. Do not assume interface fields are all compile-time constants simply because they are `public static final`.

## 13. Interface Example: Compile-Time Constants and Runtime Fields

Save **`InterfaceConstantDemo.java`**:

~~~java
public class InterfaceConstantDemo {
    interface Options {
        int FIXED = 7;
        int RUNTIME = initialize();

        static int initialize() {
            System.out.println("Options initialized");
            return 9;
        }
    }

    public static void main(String[] args) {
        System.out.println("fixed=" + Options.FIXED);
        System.out.println("before runtime");
        System.out.println("runtime=" + Options.RUNTIME);
    }
}
~~~

Run:

~~~bash
javac InterfaceConstantDemo.java
java InterfaceConstantDemo
~~~

Output:

~~~text
fixed=7
before runtime
Options initialized
runtime=9
~~~

`Options.FIXED` does not initialize the interface, whereas `Options.RUNTIME` must be evaluated when the interface is initialized. The mechanism for reading a constant variable remains consistent with the JLS definition, even when the owner is an interface.

### 13.1. Limitations of Storing All Constants in an Interface

Java has seen the "constant interface" design pattern, where a class implements an interface solely to bring constant names into scope. That practice leaks implementation details into the public API and mixes constants into the type hierarchy.

For library constants, it is usually clearer to use a **final utility class** that prevents instantiation, an appropriate enum, or a domain value object instead of implementing an interface just to borrow constant names.

## 14. A `static final` Field Referencing an Object Is Not an Immutable Object

A common mistake:

~~~java
class Registry {
    public static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();
}
~~~

The `NAMES` field cannot be reassigned to a different list from regular code after it is initialized. However, the **list object** itself can still be modified:

~~~java
Registry.NAMES.add("admin");
Registry.NAMES.clear();
~~~

If a caller can access the public field, they can mutate the shared list. `final` does **not** prevent mutations on the referenced object; `static` further turns that object into class-level shared state, increasing the risk.

### 14.1. A Safer Example With an Unmodifiable Collection

Save **`StaticFinalCollectionDemo.java`**:

~~~java
import java.util.List;

public class StaticFinalCollectionDemo {
    static final List<String> ROLES =
            List.of("READER", "WRITER");

    public static void main(String[] args) {
        System.out.println("roles=" + ROLES);
        System.out.println("size=" + ROLES.size());

        try {
            ROLES.add("ADMIN");
        } catch (UnsupportedOperationException expected) {
            System.out.println("roles cannot be modified");
        }

        System.out.println("roles after=" + ROLES);
    }
}
~~~

Run:

~~~bash
javac StaticFinalCollectionDemo.java
java StaticFinalCollectionDemo
~~~

Output:

~~~text
roles=[READER, WRITER]
size=2
roles cannot be modified
roles after=[READER, WRITER]
~~~

`ROLES` is **not** a constant variable because the field type is `List<String>`, not a primitive/String; the `List.of` expression is also a method call.

Even so, it is a **solid design** for a fixed list of roles because the `List.of` object cannot be modified through the list API. The two concepts "compile-time constant" and "immutable collection" serve **different needs**.

If the list contains **mutable elements**, an unmodifiable list only prevents structural modification; the element objects can still be mutated through aliases. When deep immutability is needed, appropriate element types/copies must be chosen.

## 15. Is a `static final` Runtime Value Suitable for Dynamic Configuration?

For example:

~~~java
static final String REGION =
        System.getProperty("region", "local");
~~~

This is a runtime-initialized static final String, not a constant variable. The field receives its value when the class is initialized; afterward, it retains a **snapshot from the time of initialization**.

If the program changes the system property later:

~~~java
System.setProperty("region", "remote");
~~~

`REGION` is **not automatically recomputed**. `final` prevents changing the field, and class initialization does not repeat merely because configuration changes.

### 15.1. Distinguishing Three Configuration APIs

| API | When the Value Is Determined | Can Runtime Changes Be Observed? |
| --- | --- | --- |
| `static final String REGION = "local";` | Compile-time constant | No; clients may inline "local" |
| `static final String REGION = System.getProperty(...);` | When the class is initialized | Does not automatically update after initialization |
| `static String region() { return System.getProperty(...); }` | When the caller invokes the method | Can read the current property according to the API contract |

A real application should consider configuration by environment, service lifecycle, caching, thread safety, and access permissions. Do not use a compile-time constant for something that needs to change per deployment without recompilation.

## 16. Why Should You Not Carelessly Expose `public static final` for Data That Changes Easily?

A constant such as `public static final int PROTOCOL_VERSION = 1` can be appropriate when it is genuinely a release-bound constant value and you accept that all clients need to rebuild after a change.

However, risks arise when:

- The library releases a new version with a changed constant value.
- A module/service deploys the new Java class without rebuilding the client.
- The client still uses the old inlined value.
- Code relying on fixed switch cases/annotations may need to change when business requirements evolve.
- Components in a distributed system are not deployed at the same time.

### 16.1. When Should You Use a Method Accessor Instead of a Constant Field?

A public method:

~~~java
public static int currentLimit() {
    return ConfigStore.limit();
}
~~~

this is an **illustrative snippet** requiring an appropriate `ConfigStore` class. The caller invokes the method at runtime; the result is not a compile-time constant inlined by the compiler like a `static final int LIMIT=10` field.

However, the trade-off is that callers **cannot use that runtime result in places that require a constant expression**, such as `case LIMIT:` in Java 17. This is an intentional design choice, not a free replacement for every constant.

## 17. Limits of Constant Expressions: Overflow and Arithmetic

Constant expressions are evaluated according to **Java semantic rules**, not arbitrary-precision arithmetic. For integer arithmetic, results still follow the overflow rules of the type.

~~~java
static final int MAX = Integer.MAX_VALUE;
static final int WRAPPED = MAX + 1;
~~~

`MAX` is a constant variable (the constant value can come from an appropriate library's final constant declaration), and `WRAPPED` is an integer constant expression; the result equals `Integer.MIN_VALUE` due to `int` overflow.

### 17.1. Runnable Example on Integer Overflow

Save **`ConstantOverflowDemo.java`**:

~~~java
public class ConstantOverflowDemo {
    static final int MAX = 2_147_483_647;
    static final int WRAPPED = MAX + 1;
    static final long SAFE = (long) MAX + 1L;

    public static void main(String[] args) {
        System.out.println("max=" + MAX);
        System.out.println("wrapped=" + WRAPPED);
        System.out.println("safe=" + SAFE);
    }
}
~~~

Compile and run:

~~~bash
javac ConstantOverflowDemo.java
java ConstantOverflowDemo
~~~

Output:

~~~text
max=2147483647
wrapped=-2147483648
safe=2147483648
~~~

**Explanation:** `WRAPPED` is evaluated within the `int` range and overflows to the minimum value. `SAFE` converts to `long` before computing, avoiding `int` overflow in that addition.

`final` and "compile-time" **do not mean the expression is guaranteed to be business-correct**. The compiler follows Java rules; developers must choose appropriate data types and bounds.

### 17.2. Integer Division by Zero in a Constant Expression

An integer constant expression with division by zero leads to a compile-time error under Java rules, for example:

~~~java
// static final int INVALID = 10 / 0; // Compile-time error.
~~~

You should not put such an erroneous expression in an example intended to compile and run. If division is performed at runtime with a denominator whose value is 0, the failure mechanism can be an `ArithmeticException` when the expression is evaluated. It is necessary to distinguish compile-time constant-expression rules from runtime exceptions.

## 18. `final` Does Not Mean "Assigned Immediately at Declaration"

Some `final` fields are validly assigned in a constructor or static block. Those fields still cannot be arbitrarily reassigned, yet the assignment can occur at runtime.

For example:

~~~java
class Session {
    final String token;

    Session(String token) {
        this.token = token;
    }
}
~~~

`token` is an instance final field whose value is supplied by the caller at runtime. It is not a compile-time constant variable merely because its type is `String` and the field is final; there is no constant-expression initializer at declaration.

For a static blank final:

~~~java
class RuntimeFlags {
    static final boolean ENABLED;

    static {
        ENABLED = Boolean.parseBoolean(
                System.getProperty("enabled", "false"));
    }
}
~~~

`ENABLED` is assigned in a static initializer at runtime. It is **not** a constant variable, even though it has boolean type and is declared static final.

### 18.1. When Is `final` Especially Useful Even Without Being a Compile-Time Constant?

- Ensures a reference or primitive field cannot be reassigned after valid initialization.
- Expresses an invariant such as an owner ID or configuration snapshot.
- Helps reason about data flow and object construction.
- Supports certain guarantees for final fields under the Java Memory Model when an object is constructed properly; this must not be equated with thread-safety of mutable referenced objects.

You should not judge the value of `final` solely by whether the compiler inlines the field.

## 19. Step-by-Step Check: "Is It a Constant Variable?"

When you encounter a declaration such as:

~~~java
public static final int TIMEOUT = SomeClass.calculateTimeout();
~~~

follow this sequence:

1. **Is this a variable declaration?** A field or a local variable?
2. **Does it have `final`?** If not, immediately rule it out from the constant variable definition.
3. **Is the type primitive or `String`?** If it is a wrapper, array, list, enum, or other object type, then no.
4. **Is there an initializer directly at the declaration, and does that initializer belong to the set of constant expressions?**
5. **Does the initializer call a method, create an object, read a nonconstant variable, use ++/--, or depend on runtime?** If so, it is not a constant expression.
6. **If another constant variable name is referenced, does it satisfy these conditions?** A constant calculation can be built from other constant variables.
7. **Is the value within the target type's range, and are the operations well-typed?** Constant expressions are still subject to type checking and overflow semantics.
8. **Where are you using it?** A case label, annotation, assignment narrowing, or public library API each has its own consequences.
9. **Could the value change in a future release?** If so, consider inlining and binary compatibility.
10. **Is there a shared mutable referent?** This is an independent question about immutability and encapsulation.

The classification result does not depend on how fast the JIT runs, whether the IDE displays a fixed number, or whether the developer "knows for sure the method always returns 10".

## 20. Common Misconceptions

| Misconception | What Is Actually True |
| --- | --- |
| "Anything `static final` is a compile-time constant." | It requires a primitive/String type and a constant-expression initializer. |
| "`static` is a mandatory requirement for a constant variable." | No; a local final primitive/String variable with a constant-expression initializer also satisfies the JLS. |
| "Every final `Integer` is a constant." | Wrapper types are not primitive/String types. |
| "`Math.abs(5)` obviously equals 5, so it is a constant expression." | Ordinary method invocations are not part of the set of constant expressions. |
| "`new String("A")` is the same as `"A"` regarding compile-time constants." | `new` is not a constant expression. |
| "`String` is immutable, so every static final String is a constant." | An immutable type is not enough; the initializer must be a constant expression. |
| "A blank final assigned a literal in a static block is a compile-time constant." | There is no constant expression initializer at the declaration. |
| "An uppercase variable name means a constant." | That is only a coding convention. |
| "Reading `Settings.LIMIT` definitely runs the static block." | If LIMIT is a constant variable, reading it does not require initializing the class. |
| "`static final List` is a constant variable." | List is not a primitive/String type. |
| "`static final List` is always immutable." | Final locks the field reference, whereas the list itself may be mutable. |
| "A method returning a fixed number is evaluated at compile time like a literal." | It may be optimized, but it does not become a constant expression under the JLS. |
| "`final int x = 7` cannot be used in a case because it is not static." | A local final int with a constant-expression initializer can be a constant variable. |
| "A `final` parameter is a compile-time constant." | Parameters receive runtime values and have no constant-expression initializer at declaration. |
| "Changing `public static final` from 10 to 20 means old clients will definitely get 20." | Clients may have inlined 10 and need recompilation. |
| "`javap` is what defines what counts as a constant." | The JLS defines constants; bytecode only lets you observe one consequence. |
| "Compile-time constants cannot overflow." | Integer constant expressions still follow Java arithmetic. |
| "Every interface field is a constant variable." | Implicitly `public static final`, yet the initializer can still be a runtime expression. |
| "Concatenating Strings with `+` is always a constant." | Only when the appropriate operands are constant expressions. |
| "`List.copyOf` makes mutable elements deeply immutable." | Only the list structure is protected; mutable elements can still be shared. |

## 21. Self-Check Exercises With Answers

**Question 1.** Is `static final int A = 5;` a constant variable?  
**Answer:** Yes. It is `final`, has primitive type `int`, and has an integer literal initializer.

**Question 2.** Is `static final Integer A = 5;` a constant variable?  
**Answer:** No. `Integer` is a wrapper reference type, not a primitive or String.

**Question 3.** What about `static final int A = Integer.parseInt("5");`?  
**Answer:** No. It involves a runtime method invocation.

**Question 4.** What about `static final String A = "ab" + "cd";`?  
**Answer:** Yes. Concatenating String constant expressions produces a String constant expression.

**Question 5.** Is `static final String A = new String("abcd");` a constant variable?  
**Answer:** No. `new` is not a constant expression.

**Question 6.** Is a field `static final int A; static { A = 5; }` a compile-time constant?  
**Answer:** No. This is a blank final field initialized at runtime by a static block.

**Question 7.** If only `Constants.A` is read and A is a constant variable, is the Constants class guaranteed to run its static block?  
**Answer:** No. Accessing a constant variable does not itself force class initialization.

**Question 8.** Is `final int LOCAL = 3;` inside a method a constant variable?  
**Answer:** Yes, even though it is not a static field. The JLS definition does not require `static`.

**Question 9.** Is `final int LOCAL = method();` a constant variable if method always returns 3?  
**Answer:** No. A method invocation is not a constant expression.

**Question 10.** Can a `final int n` parameter be used as `case n:` in a Java 17 `int` switch?  
**Answer:** Not as a compile-time constant label. A parameter receives its value when the method is called.

**Question 11.** Why is `byte b = 127;` valid while `byte b = 128;` is not?  
**Answer:** Certain assignments allow narrowing from an `int` constant expression when the value falls within the `byte` range; 128 exceeds that range.

**Question 12.** Is `acceptByte(127)` automatically valid when only the `acceptByte(byte)` overload exists?  
**Answer:** No. Method invocation does not automatically narrow an `int` literal to byte as assignment rules do.

**Question 13.** Is `static final List<String> NAMES = List.of("A");` a compile-time constant?  
**Answer:** No, neither the List type nor the method-call initializer satisfies the requirements; however, the resulting list is unmodifiable per its API.

**Question 14.** How do `"Ja" + "va"` and the literal `"Java"` relate to interning?  
**Answer:** Concatenating two constant strings yields a compile-time constant String, which is interned; in the example with the literal, the two references can point to the same object. For general content comparison, however, still use `equals`.

**Question 15.** Why can changing a public static final primitive constant in a library without rebuilding the client retain the old value?  
**Answer:** The client may have inlined the constant value at compile time.

**Question 16.** How are `static final int A = 2 + 3` and `static final int B = Math.addExact(2, 3)` similar, and how do they differ?  
**Answer:** Both evaluate to 5; A is a constant variable, whereas B is not because it calls a method.

**Question 17.** Is an interface field `int MAX = 10;` a compile-time constant?  
**Answer:** Yes. Interface fields are implicitly public static final, and the initializer is a constant expression.

**Question 18.** Is an interface field `int MAX = calculate();` automatically a compile-time constant because it is in an interface?  
**Answer:** No. A method invocation is a runtime initializer.

**Question 19.** What result does `static final int WRAPPED = 2_147_483_647 + 1;` produce?  
**Answer:** `-2147483648` due to int overflow under Java semantics.

**Question 20.** If you need to read a configuration value that changes on each deployment without rebuilding clients, what should you consider?  
**Answer:** Avoid public compile-time constants for values that change frequently; consider an accessor or runtime configuration matching the appropriate contract and design.

**Question 21.** Why does `private static final ArrayList<String> CACHE` not guarantee that other methods in the class cannot mutate the list?  
**Answer:** `final` only prevents reassigning the field reference; it does not prevent calling `add`/`clear` on the ArrayList object.

**Question 22.** Why do constant `case` labels and primitive/String annotation values genuinely require a compile-time expression?  
**Answer:** Those syntactic positions enforce compile-time constant expression rules; a value known only at runtime cannot substitute for them.

## References

- Java Language Specification (Java SE 17), [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): definition of **constant variable**.
- Java Language Specification (Java SE 17), [`15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): components of a **constant expression**.
- Java Language Specification (Java SE 17), [`12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): reading a constant variable and class initialization.
- Java Language Specification (Java SE 17), [`5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.2): narrowing integer constants in assignment.
- Java Language Specification (Java SE 17), [`13.4.9 — final Fields and static Constant Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.4.9): binary compatibility and changing constants.
- Java Language Specification (Java SE 17), [`9.3 — Field Declarations in Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.3): interface fields and implicit modifiers.
- Java Virtual Machine Specification (Java SE 17), [`4.7.2 — ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2): classfile metadata for constants.

## Key Takeaways

**`static final` does not mean "compile-time constant".** A **constant variable** requires `final`, a primitive or `String` type, and an initializer that is a **constant expression** according to the JLS. `static` makes it a class-level field; `public`/`private` governs access control and does not determine whether it is a constant.

This distinction directly affects **class initialization**, usage in **`case` labels/annotations**, special **narrowing** conversions from integer constants, and **value inlining into compiled clients**. If a public constant may change across versions, weigh the risk of clients using stale data. If a field references an object, `final` only protects against reassigning the field — **it does not automatically make the object immutable**. Understanding the three conceptual layers **modifier → constant-expression semantics → runtime behavior** thoroughly will help you write accurate and maintainable Java APIs.
