# Changing Interface Constants and the Risk of Values Being Embedded in Compiled Code

In Java, a field declared in an interface is always `public static final`. If that field is a **compile-time constant**, the compiler can copy its value directly into the bytecode of the class that uses it. Therefore, changing a constant value in a library and only re-releasing the library can cause an already-compiled program to continue using the old value.

This is an important issue in API evolution: the source code appears to be reading a library field, yet the client's bytecode may already contain the value. It is necessary to understand the conditions under which Java inlines constants, how to reproduce the bug, and how to design an API when values may change across versions.

## 1. Interface Fields Are Public Constants

In an interface, the declaration:

~~~java
interface RetryPolicy {
    int MAX_RETRIES = 3;
}
~~~

is equivalent in modifiers to:

~~~java
interface RetryPolicy {
    public static final int MAX_RETRIES = 3;
}
~~~

Interface fields must have an initial value and are implicitly:

- `public`: external code can access it if the interface's access level allows.
- `static`: the field belongs to the interface, not to individual objects.
- `final`: the field cannot be reassigned after initialization.

This is different from instance fields in a class. Interfaces do not have ordinary instance fields for each implementing object to hold its own value. Because an interface field is public, exposing it is also part of the API that clients may depend on.

## 2. When Can the Compiler Inline Constants?

According to Java's rules, a *constant variable* is a `final` variable of primitive type or `String`, initialized with a constant expression. Interface fields of primitive type or `String` initialized with a constant expression typically satisfy this condition.

Example:

~~~java
interface Protocol {
    int VERSION = 2;
    String HEADER = "X-Protocol-Version";
    long TIMEOUT_MILLIS = 1_000L * 5;
}
~~~

The values above are valid constant expressions. When other code directly references `Protocol.VERSION`, the compiler can put the value `2` into the bytecode of the calling code.

Not every `static final` field is a compile-time constant:

~~~java
interface RuntimeValues {
    Integer RETRIES = 3;
    int PARSED = Integer.parseInt("3");
    int RANDOM_EXAMPLE = (int) System.currentTimeMillis();
}
~~~

- `Integer RETRIES` is a reference type, so it is not a constant variable by Java's definition, even though the reference is `final`.
- `PARSED` uses a method call, not a constant expression.
- `RANDOM_EXAMPLE` depends on runtime.

Fields that are not compile-time constants must be read as fields at runtime; they are not replaced with a constant value by the same inlining mechanism. `final` means the variable cannot be reassigned after initialization, whereas “compile-time constant” is a narrower concept.

## 3. The Risk of Changing a Constant Value in an API

Suppose the first version of a library exposes:

~~~java
public interface ApiSettings {
    int MAX_RETRIES = 3;
    static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
~~~

A client is compiled against this version:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("constant=" + ApiSettings.MAX_RETRIES);
        System.out.println("method=" + ApiSettings.currentMaxRetries());
    }
}
~~~

Later, the library changes `MAX_RETRIES` from `3` to `5`. If only the library's class file is replaced without recompiling `Client.class`, the two lines can produce two different values:

- The direct access to `ApiSettings.MAX_RETRIES` may have already been embedded by the compiler as the value `3` in the client's bytecode.
- The call to `ApiSettings.currentMaxRetries()` remains a method call. If the new version of the interface is loaded at runtime, the new method body returns `5`.

Therefore, re-releasing the library does not automatically update constants that were embedded into previously compiled clients. This is typically a behavioral compatibility bug: the program still runs, but part of the code uses the old value.

## 4. Reproducing the Issue with Two Library Versions

This example uses Java 17 or later. We compile the client against version 1, then run that exact client bytecode with version 2 of the library. Do not recompile the client in the first step.

Create the directory structure:

~~~text
api-v1/
  ApiSettings.java
api-v2/
  ApiSettings.java
client-src/
  Client.java
~~~

Contents of `api-v1/ApiSettings.java`:

~~~java
public interface ApiSettings {
    int MAX_RETRIES = 3;

    static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
~~~

Contents of `api-v2/ApiSettings.java`:

~~~java
public interface ApiSettings {
    int MAX_RETRIES = 5;

    static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
~~~

Contents of `client-src/Client.java`:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("constant=" + ApiSettings.MAX_RETRIES);
        System.out.println("method=" + ApiSettings.currentMaxRetries());
    }
}
~~~

On macOS/Linux or a POSIX shell, run from the directory containing the three directories above:

~~~sh
mkdir -p out-v1 out-v2 out-client
javac -d out-v1 api-v1/ApiSettings.java
javac -cp out-v1 -d out-client client-src/Client.java
javac -d out-v2 api-v2/ApiSettings.java
java -cp out-client:out-v2 Client
~~~

On Windows PowerShell, use a semicolon as the classpath separator:

~~~powershell
New-Item -ItemType Directory -Force out-v1, out-v2, out-client | Out-Null
javac -d out-v1 api-v1/ApiSettings.java
javac -cp out-v1 -d out-client client-src/Client.java
javac -d out-v2 api-v2/ApiSettings.java
java -cp "out-client;out-v2" Client
~~~

Output from the client compiled against version 1 but running with version 2:

~~~text
constant=3
method=5
~~~

The first line reflects the constant that was inlined when compiling `Client.java`. The second line calls the method from version 2 of `ApiSettings`, so it returns the new value.

To verify that recompiling the client updates the directly accessed value, compile the client against version 2:

~~~sh
mkdir -p out-client-v2
javac -cp out-v2 -d out-client-v2 client-src/Client.java
java -cp out-client-v2:out-v2 Client
~~~

On Windows PowerShell, the final commands to run are:

~~~powershell
New-Item -ItemType Directory -Force out-client-v2 | Out-Null
javac -cp out-v2 -d out-client-v2 client-src/Client.java
java -cp "out-client-v2;out-v2" Client
~~~

Output after recompiling:

~~~text
constant=5
method=5
~~~

This example shows the difference between a value copied into the client's bytecode and a value returned by a method present in the library at runtime. The directory-creation commands can be omitted if the corresponding directories already exist; for a clean reproduction from scratch, use empty output directories.

## 5. Why Is This a Risk During API Evolution?

Suppose a library is used by multiple applications or multiple modules:

1. Version 1 is released with `MAX_RETRIES = 3`.
2. A client module is compiled and released. Its bytecode may already contain the value `3`.
3. The library releases version 2 with `MAX_RETRIES = 5`.
4. The application updates only the library while keeping the client bytecode unchanged.
5. Some places still use `3`, while places that call the API in another way may see `5`.

This makes investigation difficult because the source code displays `ApiSettings.MAX_RETRIES`, leading readers to think that the value will be retrieved from the current library. In reality, the value may have already been replaced by a literal in the bytecode.

Changing the value of a compile-time constant usually does not cause linkage errors like `NoSuchFieldError` at direct reference sites that have been inlined, because the bytecode may no longer read that field at runtime. However, this is still a behavioral compatibility risk. Clients may need to be recompiled to synchronize with the new value.

Do not confuse this with assuming that all API changes are binary-compatible. Removing or renaming a field, changing a method signature, or altering type structure can cause other linkage errors. Each kind of change needs to be evaluated based on the contract and how compiled clients use the API.

## 6. Design Choices When Values May Change

If a value is expected to be stable over the long term and is an explicit part of the contract, a public constant may be appropriate. For example, a standardized protocol code value or an unchanging identifier string can be a reasonable constant. Even so, if clients need to update the value when the library changes versions, a release process that includes recompiling dependent clients is necessary.

If a value may vary by version, deployment environment, user configuration, or business policy, prefer an API that reads the value at runtime:

~~~java
public final class RetryPolicy {
    private RetryPolicy() {
    }

    public static int maxRetries() {
        return 5;
    }
}
~~~

The client calls `RetryPolicy.maxRetries()`. When the library is replaced with a new version whose method body returns a different value, a previously compiled client still calls the method at runtime and can receive the new value. This is only true if the new library class is actually deployed and loaded; if the entire application still runs with the old version, the result naturally remains the old one.

For per-application or per-run configuration, a configuration object is usually clearer than a static field:

~~~java
public record RetryConfig(int maxRetries) {
    public RetryConfig {
        if (maxRetries < 0) {
            throw new IllegalArgumentException("maxRetries must be >= 0");
        }
    }
}
~~~

A configuration object helps pass policies explicitly, check validity conditions, and use different values for different components. The record above must be saved in a `RetryConfig.java` file if declared as a top-level public type. This is an independent example of how to represent configuration, not a required part of the two-version example.

Moving a constant field from an interface to a utility class **does not by itself eliminate inlining**. A `public static final` field with a compile-time constant value in a class can also be inlined into clients. To have the value read from the library version at runtime, provide a method or a configuration object with an appropriate contract, rather than merely changing where the constant is declared.

## 7. Constants in Interfaces and Design Principles

Using an interface solely to group constants often creates a “constant interface”: classes implementing the interface bring those constant names into their scope even though they do not genuinely need to express a behavior or type relationship. This clutters the API and makes evolving public names more difficult.

Some practical principles:

- Place a constant alongside the concept it describes; avoid forcing classes to implement an interface just to use constants.
- Use compile-time constants for truly stable values, not for configuration values or policies that may change.
- If clients need to see the new value when only updating the library at runtime, use an accessor method or a configuration object.
- When changing a compile-time constant value in a released API, evaluate recompiling all dependent client modules.
- Write compatibility tests that match the deployment model: testing newly compiled source against the new library is not enough to detect old client bytecode that still contains the old constant.

## 8. Distinguishing Three Easily Confused Concepts

| Concept | Meaning | Implication |
|---|---|---|
| `final` field | The variable cannot be reassigned after initialization | Not synonymous with inlining |
| Compile-time constant | A `final` variable of primitive type or `String`, initialized with a constant expression | The compiler can copy the value into the client's bytecode |
| Runtime accessor | A method or configuration read when the program runs | Can provide the new value if the new implementation is loaded |

When investigating an old value after updating a library, check whether the source code directly references a compile-time constant or calls a method. Next, verify whether the client was recompiled, which version of the library the runtime classpath actually loads, and whether any other modules still carry old bytecode.

The core point when evolving an API is distinguishing **values fixed at compile time** from **values queried at runtime**. Interface constants are convenient, but an inlined value will not change on its own simply because the library is upgraded.
