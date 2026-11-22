# Interface Fields Are Implicitly public static final and Require Initialization

## 1. Three Default Modifiers

Every field declared directly in an interface is implicitly **public static final**.

~~~java
interface ConnectionOptions {
    int DEFAULT_PORT = 8080;
    String PROTOCOL = "https";
}
~~~

The fields above have the same modifiers as if written explicitly:

~~~java
interface ConnectionOptions {
    public static final int DEFAULT_PORT = 8080;
    public static final String PROTOCOL = "https";
}
~~~

| Modifier | Meaning |
| --- | --- |
| public | Code with access to the interface can read the field |
| static | The field belongs to the interface, shared at the type level |
| final | The field cannot be reassigned after initialization |

Because the field is static, the clear way to read it is ConnectionOptions.DEFAULT_PORT. There is no need to create an instance, and there is no separate field for each object implementing the interface.

## 2. An Initializer Is Required

Every interface field must have an initialization expression right at its declaration:

~~~java
interface ServerConfig {
    int TIMEOUT_SECONDS = 30;
    String HOST = "localhost";
}
~~~

The following snippet is invalid:

~~~java
interface BrokenConfig {
    int TIMEOUT_SECONDS;
}
~~~

An interface has no instance constructor to assign fields later and does not allow declaring class-style static initializer blocks. The constructor of an implementing class also cannot assign an interface field, because that field is static final and belongs to the interface.

The “having an initializer” requirement does not mean the value must be a compile-time constant. For example, **int TIMEOUT = Integer.parseInt("1500");** has a valid initializer, but it is evaluated when the interface is initialized. The lesson on compile-time constants explains this difference in more detail.

## 3. Runnable Example

Save to **InterfaceFieldRulesDemo.java**:

~~~java
interface Limits {
    int MAX_RETRIES = 3;
    String DEFAULT_MODE = "SAFE";
    long MAX_BYTES = 1_024L * 1_024;
}

public class InterfaceFieldRulesDemo {
    public static void main(String[] args) {
        System.out.println(Limits.MAX_RETRIES);
        System.out.println(Limits.DEFAULT_MODE);
        System.out.println(Limits.MAX_BYTES);
    }
}
~~~

Compile and run:

~~~bash
javac InterfaceFieldRulesDemo.java
java InterfaceFieldRulesDemo
~~~

Output:

~~~text
3
SAFE
1048576
~~~

The interface name in the access expression shows where the value is declared. You do not need to implement Limits to read the public fields. Only implement an interface when a class genuinely fulfills the contract that the interface represents.

## 4. Interface Fields Are Not Instance State

~~~java
interface PortDefaults {
    int PORT = 8080;
}

final class HttpClient {
    int defaultPort() {
        return PortDefaults.PORT;
    }
}
~~~

Every place that accesses PortDefaults.PORT reads that same static field. If each client needs its own port, place an instance field in the class and assign it via the constructor, instead of trying to use an interface field for per-object state.

An interface field also does not by itself make the referenced object immutable. For example, a field pointing to an array can still allow modifying elements; the lesson on final and immutability focuses on this boundary.

## 5. Invalid Modifiers

The following examples illustrate each error separately, not combined into a single program:

~~~java
interface InvalidAccess {
    private int PORT = 8080;      // Invalid: an interface field cannot be private
}
~~~

~~~java
interface InvalidVisibility {
    protected int PORT = 8080;    // Invalid: an interface field cannot be protected
}
~~~

~~~java
interface MissingValue {
    int PORT;                     // Invalid: missing initializer
}
~~~

~~~java
interface InvalidInitializer {
    int PORT = 8080;
    static {
        System.out.println("init"); // Invalid: an interface has no static initializer block
    }
}
~~~

The transient and volatile modifiers are also not valid for interface fields. You cannot remove static or final individually to turn a field into instance data or reassignable data.

## 6. Should All Constants Be Grouped Into an Interface?

An interface can publish constants when the values genuinely belong to its contract. However, using an interface merely as a constant holder, and having classes implement it just to be able to write short field names, often creates a misleading type relationship.

For utility constants that do not belong to a behavioral contract, you can use a utility class:

~~~java
public final class Defaults {
    private Defaults() {
        throw new AssertionError("No instances");
    }

    public static final int DEFAULT_TIMEOUT = 30;
}
~~~

Calling code writes **Defaults.DEFAULT_TIMEOUT** without needing to implement an interface. If values change depending on the environment or need to be re-read at runtime, use a configuration API or configuration object instead of assuming a final field will update automatically.

When multiple interfaces have fields with the same name, explicitly specify the interface that owns the field; the lesson on accessing constants handles those conflicts.

### Self-Check

1. What implicit modifiers does the field **int PORT = 8080;** in an interface have? **public static final**.
2. Can an interface field be assigned in the constructor of an implementing class? **No**.
3. Are all initializers compile-time constants? **No**; an initializer can call methods or create objects.
4. Should you implement an interface just to get short constant names? **Generally no**; accessing via the interface name is clearer.

The three default modifiers and the required initializer are foundational rules of interface fields. They determine who owns a field, who can read it, and when its value is provided.
