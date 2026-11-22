# Compile-Time Constants and Runtime-Initialized Fields in Java Interfaces

## 1. public static final Is Not Necessarily a Compile-Time Constant

Every field declared directly in an interface is implicitly public static final. However, a **constant variable** must also have a primitive type or String and be initialized with a constant expression according to Java rules.

~~~java
interface AppSettings {
    int MAX_RETRIES = 3;                    // Constant variable
    String PREFIX = "api-" + "v1";          // Constant variable
    int TIMEOUT_MS = Integer.parseInt("1500"); // Runtime initialization
    Integer BOXED_RETRIES = 3;               // Runtime initialization
}
~~~

| Declaration | Constant variable? | Reason |
| --- | --- | --- |
| int A = 10; | Yes | Primitive and literal |
| String B = "Java" + " Core"; | Yes | Concatenation of constant expressions |
| int C = A + 1; | Yes, if A is a declared constant variable | Constant expression |
| int D = Integer.parseInt("10"); | No | Method call |
| Integer E = 10; | No | Integer is a reference type |
| String F = new String("Hi"); | No | Object creation |
| int[] G = {1, 2}; | No | Arrays are objects |

A primitive type alone is not enough: an int field assigned by a method call is still not a constant variable. Similarly, final on a reference does not make the referenced object immutable; that topic is explained in the article on final and immutability.

## 2. Observing Initialization Timing

Save the following program to **InterfaceFieldsDemo.java**:

~~~java
interface Configuration {
    int MAX_RETRIES = 2 + 3;
    String PREFIX = "/api/" + "v1";
    int TIMEOUT_MS = readTimeout();

    static int readTimeout() {
        System.out.println("Configuration initializing");
        return 1500;
    }
}

public class InterfaceFieldsDemo {
    public static void main(String[] args) {
        System.out.println("max = " + Configuration.MAX_RETRIES);
        System.out.println("prefix = " + Configuration.PREFIX);
        System.out.println("before runtime field");
        System.out.println("timeout = " + Configuration.TIMEOUT_MS);
    }
}
~~~

Compile and run using JDK 17+:

~~~bash
javac InterfaceFieldsDemo.java
java InterfaceFieldsDemo
~~~

Stdout:

~~~text
max = 5
prefix = /api/v1
before runtime field
Configuration initializing
timeout = 1500
~~~

MAX_RETRIES and PREFIX are constant variables; the compiler can embed their values directly into the code that uses them. Reading them does not require initializing Configuration. The first read of TIMEOUT_MS requires initializing the interface, so readTimeout runs and prints the message. Type initialization occurs once for the type definition loaded by the corresponding class loader, not repeatedly on every field read.

Interfaces do not allow declaring static initializer blocks like classes do. Logic executed at initialization time must be expressed through field initializers or moved to an API/factory with a clear lifecycle.

## 3. Why Can Old Clients Retain Old Constant Values?

Constant variables can be embedded directly by the compiler into the bytecode of the code that uses them. For example, a library releases its first version:

~~~java
public interface ApiConstants {
    int VERSION = 1;
    int PORT = Integer.parseInt("8080");
}
~~~

Client:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("version = " + ApiConstants.VERSION);
        System.out.println("port = " + ApiConstants.PORT);
    }
}
~~~

After compiling both files, changing VERSION to 2 and PORT to the runtime value 9090, and recompiling only ApiConstants.java, the old client.class can print:

~~~text
version = 1
port = 9090
~~~

VERSION is a constant variable, so the value 1 may have been embedded into Client.class. PORT is not a constant variable, so the old client reads the field at runtime and sees 9090. Recompiling Client.java will cause the code to use the new VERSION value.

This is a binary compatibility issue for public APIs: changing the value of a compile-time constant may require recompiling dependent clients. Do not use a constant variable for configuration that users expect to change simply by replacing the JAR.

## 4. Actions That Can Trigger Initialization

Under normal circumstances, reading a static field declared by an interface that is not a constant variable or calling a static method declared by an interface can trigger type initialization. Reading a constant variable does not by itself trigger that. Runtime initializers are processed in declaration order; therefore, avoid circular dependencies or unpredictable side effects.

A field of type List, array, or object is also not a constant variable just because it is static final. It is initialized when the interface is initialized, while whether its internal state can be modified depends on the object itself.

To understand errors caused by using a later field in an initializer, see the article on reference restrictions and declaration order; that article distinguishes compile-time errors from reading default values at runtime.

## 5. Decision Rules

- Use a constant variable when a primitive or String value is genuinely stable as part of the public contract.
- Use a runtime-initialized field when it is acceptable for the value to be computed once when the interface initializes and it does not need to update automatically on every read.
- Use a method, service, or configuration object when the value depends on the environment, user, or request, or needs to be queried again.
- Avoid placing I/O, network access, or complex error handling inside a field initializer.
- When changing a public constant, evaluate whether already-compiled clients need to be rebuilt.

### Self-Check

1. Is Integer BOXED = 3 a constant variable? **No**, because Integer is a reference type.
2. Does reading a constant variable require initializing the interface? **No**.
3. Can a method call in an initializer be a constant expression? **No**.
4. Does changing a compile-time constant and releasing only a new JAR guarantee that old clients use the new value? **No**, because clients may have already inlined the value.

Specification sources: [JLS §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4), [JLS §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29), and [JLS §12.4 — Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).
