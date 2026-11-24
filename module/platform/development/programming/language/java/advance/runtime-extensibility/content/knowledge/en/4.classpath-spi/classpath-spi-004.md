# Public Visibility, Assignability, and No-Arg Constructor Requirements for Classpath SPIs

## 1. Context: How Does ServiceLoader Load Providers from the Classpath?

A **Service Provider Interface (SPI)** describes a capability that the main application (host) needs, while a **provider** is a class implementing that capability. On the **classpath**, Java can find providers via **java.util.ServiceLoader** without the host directly calling each implementation's constructor.

For example, the host depends only on the `GreetingService` interface, while an extension JAR registers the `PoliteGreeting` class. When iterating over `ServiceLoader`, the JVM reads the resource **META-INF/services/<fully qualified binary name of service>**, loads the provider class name, and creates an instance.

The three core conditions for a provider registered via **META-INF/services on the classpath** are:

1. **The provider class must be public**, visible to the loader, and a concrete instantiable class.
2. **The provider class must be assignable to the service type**: implementing the SPI interface or extending the corresponding service class.
3. **The provider class must have a public no-argument constructor** so `ServiceLoader` can create an instance.

These are conditions for **constructor-based providers on the classpath**; do not confuse them with the `public static provider()` mechanism available in some **named modules**. A correct signature with a wrong runtime configuration can still prevent the application from finding the provider.

## 2. The Three Conditions and How to Distinguish Them

| Check | What Must Be True | Common Mistakes |
| --- | --- | --- |
| Public/accessibility | Provider is a proper public class, not a non-static inner class; class loader can find it | Package-private class, wrong provider name, JAR not on classpath |
| Assignability | `ServiceType.class.isAssignableFrom(ProviderType.class)` returns `true` | Has matching method names but forgot `implements`, extends wrong type, two SPI copies defined by different class loaders |
| No-argument constructor | Has a **public** constructor with **0 parameters**, callable successfully | Only has constructor taking `Config`, private/package-private constructor, constructor throws an error |

Beyond those three conditions, the provider must actually be instantiable: not `abstract`, not an `interface` when using direct instantiation, no class initialization failures, missing dependencies, or initialization cycles. The service registration file must also have the right name and format.

A class can pass two conditions yet fail the third. For example, being `public` and implementing the SPI does not guarantee a public no-arg constructor; conversely, a public constructor does not make a class a subtype of the SPI.

## 3. The Public Requirement: Public for Both Class and Constructor

### 3.1. A Public Class Is a Separate Requirement

In Java, a top-level class declared without `public` has package-private access. The following example is **invalid as a classpath provider under `ServiceLoader` rules**, even though the constructor is marked `public`:

~~~java
package example.provider;

import example.spi.GreetingService;

// Code illustrating an invalid case; does not replace the provider in the runnable example in Section 7.
final class HiddenGreeting implements GreetingService {
    public HiddenGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

A public constructor cannot compensate for a package-private class. A provider declared as a `public static` nested class can be used if it satisfies the remaining conditions; when registering, you must use the **binary name** with `$` between the outer class name and nested class name. A **non-static inner class** depends on an instance of the enclosing class and therefore is unsuitable for a provider instantiated directly via a public no-arg constructor.

The SPI interface also needs to be **accessible from both the provider and the caller**. For an SPI intended to be used across packages/JARs, it is normally declared as a `public interface` or `public abstract class`. Do not assume that merely adding `public` to the SPI makes providers valid.

### 3.2. Public Does Not Mean It Is on the Right Classpath

Even if a class is `public`, `ServiceLoader` still will not find it if its bytecode is absent from the relevant loader's classpath, the name in the service descriptor is wrong, or required dependencies are invisible. The `public` modifier governs Java code accessibility; **class and resource lookup paths** are determined by the class loader.

In most ordinary classpath applications, `ServiceLoader.load(ServiceType.class)` uses the current **thread context class loader**. In a host/plugin container with multiple loaders, provider lookup results can differ across threads or loaders. When needing to choose a loader explicitly, use the `ServiceLoader.load(serviceClass, classLoader)` overload and ensure that loader sees both the registration resource and the provider.

## 4. Assignability: Matching Method Signatures Does Not Mean the Same SPI

Java uses **nominal typing** for classes/interfaces; it does not infer that a class implements an interface merely because it has identical methods.

~~~java
// Illustration only: this class does not implement GreetingService.
public final class LooksLikeGreeting {
    public String greet(String name) {
        return "Hello, " + name;
    }

    public LooksLikeGreeting() {}
}
~~~

A class like `LooksLikeGreeting` can have a `public` method with the exact same parameters and return type yet **not be assignable to `GreetingService`**. To become a provider, it must declare:

~~~java
public final class PoliteGreeting implements GreetingService {
    public PoliteGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

These two snippets are abbreviated code to illustrate type relationships; the complete program and package/import declarations are in Section 7.

Check via reflection in the right direction:

~~~java
boolean compatible = GreetingService.class.isAssignableFrom(PoliteGreeting.class);
~~~

The value `compatible` is `true` when `PoliteGreeting` implements the `GreetingService` used by the host (or is a subtype of a service class). Writing it backwards as `PoliteGreeting.class.isAssignableFrom(GreetingService.class)` does not answer that question.

**Be careful with multiple class loaders.** Class identity at runtime depends on **binary name and defining class loader**. If the host and plugin accidentally package two copies of the SPI with the same name but defined by two different loaders, assignability can fail even though both sources write `implements example.spi.GreetingService`. Plugin designs should unify where the shared SPI copy is loaded and avoid embedding separate SPI copies in each plugin when they must exchange the same type with the host.

## 5. No-Arg Constructor: Public, Present, and Callable

### 5.1. Explicit Constructor and Default Constructor

`ServiceLoader` needs a **public constructor with no parameters** to instantiate a provider on the classpath. Declaring it explicitly makes the intent clear:

~~~java
public final class PoliteGreeting implements GreetingService {
    public PoliteGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

If a **`public` class declares no constructors at all**, the compiler generates a no-argument **default constructor** with matching access (`public`). Thus that case also satisfies the condition, provided the class can be instantiated.

However, **as soon as you explicitly declare a constructor taking parameters**, Java no longer auto-generates a default constructor:

~~~java
// Illustrates an invalid case for classpath ServiceLoader.
public final class ConfiguredGreeting implements GreetingService {
    private final String prefix;

    public ConfiguredGreeting(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String greet(String name) {
        return prefix + name;
    }
}
~~~

`ConfiguredGreeting` is `public` and implements the SPI, but lacks a public no-argument constructor. You cannot expect classpath `ServiceLoader` to guess a `Config` to pass into the constructor.

Private, protected, or package-private constructors do not satisfy the `public` requirement, even if they take no parameters. A superclass's constructor is **not inherited** like a method; the condition must be checked on the actual provider class listed in the descriptor.

### 5.2. Having a Constructor Is Not Enough If Calling It Fails

A public no-arg constructor can still throw an exception or trigger a class initialization error. When `ServiceLoader` creates an instance, such failures can be reported as **`ServiceConfigurationError`**, with the root cause if available. Do not make the constructor depend on uninitialized global state or perform long undocumented network work.

If a provider needs runtime configuration, with a classpath SPI you can:
- Instantiate the provider via the no-arg constructor and then call a configuration/initialization method published by the SPI, with controlled lifecycle and error handling.
- Supply context via a dedicated contract method rather than embedding hidden dependencies in the constructor.
- If you control a JPMS named-module architecture, consider a provider factory method as in Section 10; do not misapply that approach to classpath JARs.

Do not use reflection to force a private constructor to be accessible to "fix" `ServiceLoader`; doing so creates a different instantiation mechanism dependent on access and module policies, and does not solve the classpath provider contract.

## 6. Registering META-INF/services Properly on the Classpath

For the SPI `example.spi.GreetingService`, the resource path **must be exact**:

~~~text
META-INF/services/example.spi.GreetingService
~~~

The file contents, encoded in **UTF-8**, list the **fully qualified binary name** of each provider, one name per line:

~~~text
example.provider.PoliteGreeting
~~~

Do not add `.class` or `.java` extensions to the configuration file name or class names inside. The file name follows the **service**, while content lines follow the **provider**. There may be multiple providers, one per line; blank lines are ignored and `#` starts a comment. If the same provider is listed multiple times, `ServiceLoader` skips duplicates according to its rules.

This resource can reside in the provider JAR or another classpath entry, but at runtime the loader must be able to find the resource and load the corresponding class. A file sitting in the right source directory of a project is not guaranteed to be copied into the JAR or placed on the final classpath. When packaging, inspect inside the artifact rather than looking only at the source tree.

## 7. Complete, Runnable Example on Java 17+

The following example uses one public SPI, one public provider with a public no-arg constructor, one host that does not import the provider, and one service descriptor.

Directory structure, relative to the `demo` directory:

~~~text
demo/
├── src/
│   └── example/
│       ├── spi/GreetingService.java
│       ├── provider/PoliteGreeting.java
│       └── app/Main.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── example.spi.GreetingService
└── out/                    (output directory created before compiling)
~~~

**src/example/spi/GreetingService.java**:

~~~java
package example.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

**src/example/provider/PoliteGreeting.java**:

~~~java
package example.provider;

import example.spi.GreetingService;

public final class PoliteGreeting implements GreetingService {
    public PoliteGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

**src/example/app/Main.java**:

~~~java
package example.app;

import example.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        int found = 0;
        for (GreetingService provider : loader) {
            System.out.println(provider.greet("Java"));
            found++;
        }

        System.out.println("Providers: " + found);
    }
}
~~~

**resources/META-INF/services/example.spi.GreetingService** (plain UTF-8 text file):

~~~text
example.provider.PoliteGreeting
~~~

From the `demo` directory, create the `out` directory and compile the `.java` files:

~~~bash
mkdir out
javac -encoding UTF-8 --release 17 -d out src/example/spi/GreetingService.java src/example/provider/PoliteGreeting.java src/example/app/Main.java
~~~

On Linux/macOS, run with **:** separating the two classpath entries:

~~~bash
java -cp "out:resources" example.app.Main
~~~

On Windows, use **;** instead:

~~~powershell
java -cp "out;resources" example.app.Main
~~~

**Exact stdout** (only one provider is registered):

~~~text
Xin chao, Java!
Providers: 1
~~~

Because `Main` imports only the `GreetingService` interface, the host never needs to reference `PoliteGreeting` directly. `ServiceLoader` reads the descriptor from `resources`, loads the class, and instantiates the provider when the `for` loop iterates to it.

To see the difference between **failing to find a provider** and **a provider violating conditions**, try removing `resources` from the runtime classpath and running:

~~~bash
java -cp out example.app.Main
~~~

When only the classes in `out` exist and no other descriptor copy is present, the result is:

~~~text
Providers: 0
~~~

In this case **there is no `ServiceConfigurationError`** because the loader found no registered provider. Conversely, when the descriptor contains a class name that is invalid, an error typically occurs while iterating and loading the provider.

## 8. Proactively Checking the Three Conditions Using Reflection

To diagnose in the example environment, you can inspect the class properties before registration. This is an **inspection tool**, not a replacement for how `ServiceLoader` creates instances.

Create the file **src/example/app/Inspector.java**:

~~~java
package example.app;

import example.spi.GreetingService;
import java.lang.reflect.Modifier;

public final class Inspector {
    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> candidate = Class.forName("example.provider.PoliteGreeting");

        boolean isPublic = Modifier.isPublic(candidate.getModifiers());
        boolean isConcrete = !candidate.isInterface()
                && !Modifier.isAbstract(candidate.getModifiers());
        boolean isAssignable = GreetingService.class.isAssignableFrom(candidate);

        boolean hasPublicNoArg;
        try {
            candidate.getConstructor();
            hasPublicNoArg = true;
        } catch (NoSuchMethodException ex) {
            hasPublicNoArg = false;
        }

        System.out.println("public: " + isPublic);
        System.out.println("concrete: " + isConcrete);
        System.out.println("assignable: " + isAssignable);
        System.out.println("public no-arg: " + hasPublicNoArg);
    }
}
~~~

After compiling the example in Section 7, also run:

~~~bash
javac -encoding UTF-8 --release 17 -cp out -d out src/example/app/Inspector.java
java -cp out example.app.Inspector
~~~

**Exact stdout:**

~~~text
public: true
concrete: true
assignable: true
public no-arg: true
~~~

**Explanation:** `Modifier.isPublic` checks class accessibility; `!Modifier.isAbstract` and `!isInterface` check that it is a directly instantiable type; `isAssignableFrom` checks the type relationship in the right direction; `Class.getConstructor()` looks for a public no-argument constructor (throwing `NoSuchMethodException` if none exists).

Four `true` results still **do not guarantee successful discovery**: `Inspector` has not checked the descriptor, classpath entries, class loader consistency, dependencies, class initialization errors, or constructor logic. `Inspector` uses simple class loading in the example; in a real plugin host, you must check with the exact class loader configured for `ServiceLoader`.

## 9. Identifying Errors and How to Handle Them

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| No providers found, no error thrown | Missing `META-INF/services` on runtime classpath or descriptor not seen by loader | Check resource path, JAR contents, classpath, and context class loader |
| `ServiceConfigurationError` when iterating providers | Descriptor contains wrong name, class cannot be loaded, or fails contract | Check binary name, classpath, and error cause |
| Package-private class | Provider class is not `public` | Change to a `public` top-level class or a valid `public static` nested class |
| Has methods matching SPI without `implements`/`extends` | No nominal type relationship | Implement the SPI properly, unify class loader for shared API |
| Public class without public no-arg constructor | Only parameterized constructors or non-public no-arg constructor | Declare an appropriate `public Provider() {}` |
| Constructor exists but throws error | Config dependency or initializer failure | Inspect cause, move fallible initialization to an explicit contract lifecycle |
| Multiple copies with same SPI name | Two class loaders defined two distinct classes | Share one SPI copy in the appropriate loader, avoid duplicate packaging |
| Abstract or non-static inner provider | Cannot be instantiated via direct constructor | Use a concrete `public` class with a no-arg constructor |
| Added only `static provider()` to a classpath provider | Confused named-module mechanism with classpath | On classpath, still must have public no-arg constructor and be a provider subtype |

**When `ServiceConfigurationError` occurs**, remember that `ServiceLoader` loads providers **lazily**. The error can happen when calling `Iterator.hasNext()`, `Iterator.next()`, iterating with for-each, or processing a `Stream`/`Provider.get()`, rather than immediately at `ServiceLoader.load(...)`. Catch this error type at the *discovery/loading* boundary to record the failing provider and apply a defined fail-fast or fallback policy:

~~~java
// Snippet illustrating discovery handling, not a standalone program.
try {
    for (GreetingService provider : ServiceLoader.load(GreetingService.class)) {
        System.out.println(provider.greet("Java"));
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("Invalid service provider configuration: "
            + error.getMessage());
}
~~~

Do not default to `catch(Throwable)` to swallow every `Error`. `ServiceConfigurationError` is a specialized error of the service-loading mechanism; fundamental JVM errors require a different policy. If one provider fails, the decision to skip or stop must be implemented carefully: continuing to use the same iterator after an error may keep encountering an error state, and you should not assume a single `next()` call cleanly skips the bad provider.

When creating a JAR, you can check archive entries with **`jar --list --file filename.jar`** and confirm the presence of the `META-INF/services` resource and the specified class. Do not rely on source directory names or IDE compilation success to conclude that runtime discovery is right.

## 10. Key Differences from Java Modules

Considering only **SPIs on the classpath**, `ServiceLoader` uses **`META-INF/services`** and instantiates providers via a **public no-arg constructor**. With a **named module** explicitly declared via `module-info.java`, services are registered by **`provides ... with ...`** and gain the **provider method** mechanism:

~~~java
// Illustrative module-info.java snippet, not a standalone program.
provides example.spi.GreetingService
    with example.provider.GreetingFactory;
~~~

~~~java
// Factory-style snippet in a named module, requiring the module's classes/imports.
public final class GreetingFactory {
    public static GreetingService provider() {
        return new PoliteGreeting();
    }
}
~~~

When a `public static provider()` method with no parameters and a return type assignable to the service exists, `ServiceLoader` for a **named module** can call that method instead of a constructor; **the factory class does not have to implement the SPI**, nor is it required to have a public no-arg constructor under this instantiation path. If a named-module provider **has no provider method**, it must have a public no-arg provider constructor and must be assignable to the SPI. An **automatic module** on the module path must still use a provider constructor; it does not support the provider method under this mechanism.

**Do not infer** that a JAR placed on the classpath only needs to declare `static provider()`. A classpath provider must be a subtype of the SPI and have a public no-arg constructor for `ServiceLoader` to create it. That is the scope of this lesson.

## 11. Minimal Test Suite for Each Provider

| Test Case | Expected Result |
| --- | --- |
| Valid provider, valid descriptor, valid classpath | `ServiceLoader` finds and creates the provider |
| Remove descriptor from runtime classpath | Provider not found; may yield 0 results |
| Change provider class to package-private | Reports invalid provider configuration when loading |
| Remove `implements`/`extends` SPI while keeping matching method | Fails because it is not assignable |
| Keep only parameterized constructor | Fails due to missing public no-arg constructor |
| Change no-arg constructor to `private` | Fails because constructor is not `public` |
| Constructor throws `IllegalStateException` | Provider loading fails; inspect cause |
| Duplicate SPI API via another class loader | Check assignability of the actual runtime class |
| Convert JAR to named module/automatic module | Re-verify registration/instantiation rules for the module type |

In systems with third-party plugins, you should automatically test each artifact after packaging: verify the properly named `META-INF/services` exists, run `ServiceLoader` using a class loader simulating the host environment, invoke a minimal behavior, and verify the error type when a provider lacks a required condition.

## 12. Checklist Before Releasing a Classpath SPI

1. The SPI is an interface/class accessed by both host and provider through a shared API; the provider uses the **exact same SPI type at runtime**.
2. The provider is a **public concrete class** (or appropriate `public static` nested class) that actually implements/extends the SPI.
3. There is a **public no-argument constructor**, and the constructor executes safely.
4. Exact resource name **META-INF/services/<service binary name>**, UTF-8 encoded; each line contains only the **provider binary name**.
5. The descriptor, provider, and dependencies are all present on the runtime classpath used by `ServiceLoader`.
6. Tested with actual `ServiceLoader`, not just `javac` or reflection; errors are observed at provider iteration/instantiation time.
7. Clearly distinguished the classpath mechanism from the provider method mechanism in named modules.

**Remember:** **`public`** determines class accessibility, **assignability** determines whether it matches the SPI type, and the **public no-arg constructor** determines whether classpath `ServiceLoader` has a way to instantiate it. All three conditions must hold simultaneously; the descriptor and class loader must deliver the provider to where it needs to be loaded.

Standard API reference: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html