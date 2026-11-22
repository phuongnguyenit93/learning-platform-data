# Provider constructor, provider method, and differences by deployment mode

## 1. Why are there two ways to create a service provider?

In Java, **ServiceLoader<S>** is the mechanism for discovering implementations of a **service type** — typically an interface or abstract class — without the application needing to know the concrete name of each implementation at compile time.

For example, an application uses the **Transform** service, while the implementation provider may come from another module or JAR. Java supports two mechanisms for creating a service provider, but **the two mechanisms do not both work in every deployment mode**:

- **Provider constructor:** ServiceLoader directly invokes the **public no-argument constructor** of the provider class; the provider class must be a subtype/implementation of the service.
- **Provider method:** In an **explicit named module**, a provider class can declare a **public static no-argument method named exactly provider**, returning an object whose return type is assignable to the service; the class containing the provider method **is not required to implement the service**.

Key difference: for a JAR that registers a provider via **META-INF/services on the classpath**, ServiceLoader does not process a provider method as it does for an explicit named module. **Automatic modules** also require a provider constructor and do not support a provider method.

This lesson explains the JDK 17+ contract, a runnable example of both paths, the importance of module-info.java, how to read **ServiceLoader.Provider.type()/get()**, common errors, and the limitations of class loading/lazy discovery.

## 2. Key concepts

### 2.1 Service type

The service type **S** is usually a public interface visible to both the consumer and the providers:

~~~java
package lesson.api;

public interface Transform {
    String apply(String input);
}
~~~

The ClassLoader and module system must ensure that the consumer and provider use the **same runtime service type**, not merely the same binary name. If the host and plugin each define their own separate copy of **lesson.api.Transform**, ServiceLoader may reject the provider because it is not assignable or raise related type identity errors.

### 2.2 Provider class

A provider class is the type listed in **provides ... with ...** of a module descriptor, or in the **META-INF/services/<service-name>** configuration on the classpath.

Not every provider class is the **instance handed to the consumer**: with a provider method, the provider class may simply be a **factory holder**. The object the consumer receives is the result returned from the provider() method.

### 2.3 Provider constructor

A **provider constructor** is a public constructor with no parameters. When the provider class does not declare a provider method according to the named-module rules, ServiceLoader requires that class to be assignable to the service and instantiates it directly.

~~~java
public final class DirectTransform implements Transform {
    public DirectTransform() {
    }

    @Override
    public String apply(String input) {
        return input;
    }
}
~~~

This is a snippet within a context where the Transform interface and appropriate imports/package declaration already exist; it is not a standalone program.

### 2.4 Provider method

A provider method is a **public static no-args method named exactly provider**. For an explicit named module:

~~~java
public final class FactoryProvider {
    private FactoryProvider() {
    }

    public static Transform provider() {
        return new SomeTransform();
    }
}
~~~

This snippet requires the corresponding Transform/SomeTransform types. **FactoryProvider** does not need to implement Transform and does not need a public no-args constructor. ServiceLoader calls **FactoryProvider.provider()** to obtain the object that actually implements the service.

### 2.5 ServiceLoader.Provider<S>

Since Java 9, **ServiceLoader.stream()** provides elements of type **ServiceLoader.Provider<S>**. Each element has:

- **type()**: the Class of the provider type, which can be filtered/inspected before creating an instance. With a provider method, this is the **declared return type of provider()**, not necessarily the class containing the factory method or the exact runtime class of the object.
- **get()**: gets/instantiates an instance of the service; it may invoke a constructor or a provider method depending on the deployment mode.

Do not confuse **ServiceLoader.Provider.get()** with the method named **provider()** on a provider class: these are two different APIs.

## 3. Comparison table by deployment mode

| Deployment type | Where is the provider declared? | Creation mechanism | Required conditions |
| --- | --- | --- | --- |
| **Explicit named module, direct provider** | **module-info.java**: provides S with Impl | Invokes provider constructor | Provider class is public, implements/extends S, and has a public no-args constructor, if it has no provider method. |
| **Explicit named module, factory provider** | **module-info.java**: provides S with Factory | Invokes public static provider() | Provider class is public; provider() is public static with no parameters and a return type assignable to S; the factory class does not need to implement S. |
| **Classpath / unnamed module** | **META-INF/services/<fully-qualified-service-name>** | Invokes public no-args constructor | The listed class must implement/extend S; having only provider() is **not sufficient**. |
| **Automatic module on the module path** | Provider metadata derived from **META-INF/services** in the JAR | Invokes public no-args constructor | Provider class must be assignable to S and have a public no-args constructor; **a provider method is not supported**. |

**Warning:** "Placing a JAR on the module path" does not guarantee provider method support. The JAR must be an **explicit named module** with a **module-info.class** module descriptor (corresponding to module-info.java when compiled). An automatic module that derives its name automatically from the manifest/JAR filename is a different case.

## 4. Rules for explicit named modules

### 4.1 requires, exports, uses, and provides

A typical modular system has:

~~~text
lesson.api
  exports lesson.api
  contains interface Transform

lesson.providers
  requires lesson.api
  provides lesson.api.Transform with lesson.impl.CtorTransform,
      lesson.impl.FactoryProvider

lesson.app
  requires lesson.api
  uses lesson.api.Transform
  consumer calls ServiceLoader.load(Transform.class)
~~~

- **requires** in the provider/consumer module allows referencing the API module.
- **exports** of the API module allows other modules to access the service interface.
- **uses** in an explicit consumer module declares the requirement to use the service; ServiceLoader may report ServiceConfigurationError if it is missing, depending on the relevant overloads and context.
- **provides ... with ...** declares provider classes that actually belong to the provider module itself; it does not point to resource files.
- The provider module **does not necessarily have to export the implementation package**. The Javadoc even recommends keeping the implementation package encapsulated when possible.

### 4.2 What if a class has both a constructor and a provider method?

When a provider class in an explicit named module **declares a valid provider method**, ServiceLoader uses **that method** to create the instance, rather than choosing a constructor arbitrarily.

Therefore, a provider method is not merely a utility that the caller has to invoke manually via reflection. It is a rule that **ServiceLoader** applies when the module descriptor identifies the provider class.

### 4.3 A factory provider does not need to implement the service

Example:

~~~java
public final class FactoryProvider {
    private FactoryProvider() {
        throw new AssertionError("not constructed");
    }

    public static Transform provider() {
        return new ActualTransform();
    }
}
~~~

In an explicit module, this is valid if **ActualTransform implements Transform** and the method return type is assignable to Transform. ServiceLoader does not need to invoke the private constructor of FactoryProvider.

However, if FactoryProvider itself is listed in **META-INF/services** on the classpath without implementing Transform, the lookup will fail. That is the biggest difference in this topic.

### 4.4 Do not confuse a public method with a public instance

**provider()** must be public and static, with no parameters. It can return a **non-public** implementation class if the declared return type is compatible with the service and the module's accessibility rules allow it.

**Provider.type()** does not imply that the returned Class always has a public no-argument constructor or can be instantiated directly by the consumer. ServiceLoader.Provider.get() is the standard way to obtain an instance.

## 5. Runnable Java 17+ example #1: two providers in an explicit named module

This complete example has three modules: API, provider, and consumer. It demonstrates:

- The **CtorTransform** provider is created via a public constructor.
- **FactoryProvider** does not implement the service and only has a private constructor, yet it is accepted because it has provider().
- **ServiceLoader.stream()** allows reading type metadata before calling Provider.get().
- With a factory method, **Provider.type()** is the **declared return type** (here FactoryResult), not FactoryProvider.

### 5.1 File structure

~~~text
project/
└── src/
    ├── lesson.api/
    │   ├── module-info.java
    │   └── lesson/api/Transform.java
    ├── lesson.providers/
    │   ├── module-info.java
    │   └── lesson/impl/
    │       ├── CtorTransform.java
    │       └── FactoryProvider.java
    └── lesson.app/
        ├── module-info.java
        └── lesson/app/Main.java
~~~

**src/lesson.api/module-info.java**:

~~~java
module lesson.api {
    exports lesson.api;
}
~~~

**src/lesson.api/lesson/api/Transform.java**:

~~~java
package lesson.api;

public interface Transform {
    String apply(String input);
}
~~~

**src/lesson.providers/module-info.java**:

~~~java
module lesson.providers {
    requires lesson.api;

    provides lesson.api.Transform
            with lesson.impl.CtorTransform,
                 lesson.impl.FactoryProvider;
}
~~~

**src/lesson.providers/lesson/impl/CtorTransform.java**:

~~~java
package lesson.impl;

import lesson.api.Transform;

public final class CtorTransform implements Transform {
    public CtorTransform() {
        System.out.println("ctor invoked");
    }

    @Override
    public String apply(String input) {
        return "ctor:" + input;
    }
}
~~~

**src/lesson.providers/lesson/impl/FactoryProvider.java**:

~~~java
package lesson.impl;

import lesson.api.Transform;

public final class FactoryProvider {
    private FactoryProvider() {
        throw new AssertionError("not constructed");
    }

    public static FactoryResult provider() {
        System.out.println("factory method invoked");
        return new FactoryResult();
    }
}

final class FactoryResult implements Transform {
    @Override
    public String apply(String input) {
        return "factory:" + input;
    }
}
~~~

**src/lesson.app/module-info.java**:

~~~java
module lesson.app {
    requires lesson.api;
    uses lesson.api.Transform;
}
~~~

**src/lesson.app/lesson/app/Main.java**:

~~~java
package lesson.app;

import lesson.api.Transform;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        List<ServiceLoader.Provider<Transform>> providers =
                ServiceLoader.load(Transform.class).stream()
                        .sorted(Comparator.comparing(
                                p -> p.type().getName()))
                        .toList();

        System.out.println("provider count = " + providers.size());

        for (ServiceLoader.Provider<Transform> p : providers) {
            System.out.println("type = " + p.type().getName());
            Transform service = p.get();
            System.out.println("result = "
                    + service.apply("abc"));
        }
    }
}
~~~

### 5.2 Compiling and running

From inside the **project** directory containing the source tree above:

~~~bash
javac --module-source-path src -d mods -m lesson.api,lesson.providers,lesson.app
java --module-path mods --add-modules lesson.providers -m lesson.app/lesson.app.Main
~~~

**Reason for using --add-modules lesson.providers:** ensures the provider module is present in the graph for this run so that the lookup can find the module containing the providers. Do not confuse a module JAR being present on the module path with a module being guaranteed to be resolved into the module graph.

**Verified stdout when compiling/running on JDK 21; code is compatible with Java 17+:**

~~~text
provider count = 2
type = lesson.impl.CtorTransform
ctor invoked
result = ctor:abc
type = lesson.impl.FactoryResult
factory method invoked
result = factory:abc
~~~

### 5.3 Step-by-step analysis

1. **ServiceLoader.load(Transform.class)** creates a service loader for the service type. The consumer module already has **uses lesson.api.Transform**.
2. **stream()** traverses provider metadata. **sorted()** makes the demo order deterministic by class name rather than relying on discovery order.
3. In the output, **provider count = 2** confirms that both entries in the provides directive were discovered.
4. **type = lesson.impl.CtorTransform** is the direct provider class, implementing Transform.
5. When **p.get()** is called for CtorTransform, the public no-argument constructor runs and prints **ctor invoked**.
6. **type = lesson.impl.FactoryResult** is the declared return type of FactoryProvider.provider(), not the name FactoryProvider.
7. The next **p.get()** invokes **FactoryProvider.provider()**, prints **factory method invoked**, and returns FactoryResult.
8. **FactoryProvider** has a private constructor that throws AssertionError. That error does not occur because ServiceLoader does **not** instantiate FactoryProvider via its constructor.
9. Both returned objects actually implement Transform, so the consumer simply calls **service.apply("abc")** without needing to know their origin.

### 5.4 Why can FactoryResult be package-private?

FactoryResult is a **non-public** top-level class that implements Transform; the provider method declares FactoryResult as its return type. It resides in the same module/package as FactoryProvider, so the provider code can access it.

The consumer **does not directly call new FactoryResult()** and does not need the implementation package to be exported. ServiceLoader supports instantiating the provider via the method declared in the module descriptor. If the consumer attempts to reflect on or use that non-public class directly, it must still respect Java/JPMS accessibility.

### 5.5 Things that cause incorrect results

If **uses** is omitted from the explicit consumer module, ServiceLoader may report ServiceConfigurationError according to the API rules.

If **--add-modules lesson.providers** is omitted in this exact example, the provider module will not necessarily be in the resolved graph and may not be found. If **provider()** is replaced with another name such as create(), ServiceLoader does not recognize it as a provider method.

If the method is only an instance method or takes parameters, it is **not** a valid provider method. If FactoryProvider does not implement Transform and has no valid provider method, the module declaration may be rejected by the compiler or the runtime lookup may fail depending on the error.

## 6. Runnable Java 17+ example #2: classpath using constructor only

The traditional case deploys an SPI on the **application classpath** without module-info.java. ServiceLoader discovers providers via a **provider-configuration file**:

~~~text
META-INF/services/<fully-qualified-binary-name-of-service>
~~~

For example, the **lesson.spi.Transform** service requires the file:

~~~text
META-INF/services/lesson.spi.Transform
~~~

with the contents:

~~~text
lesson.impl.ClassicTransform
~~~

### 6.1 Structure

~~~text
classpath-project/
├── cp-src/
│   └── lesson/
│       ├── spi/Transform.java
│       ├── impl/ClassicTransform.java
│       └── app/ClasspathDemo.java
└── cp-out/
    └── META-INF/
        └── services/
            └── lesson.spi.Transform
~~~

**cp-src/lesson/spi/Transform.java**:

~~~java
package lesson.spi;

public interface Transform {
    String apply(String input);
}
~~~

**cp-src/lesson/impl/ClassicTransform.java**:

~~~java
package lesson.impl;

import lesson.spi.Transform;

public final class ClassicTransform implements Transform {
    public ClassicTransform() {
        System.out.println("classic constructor invoked");
    }

    @Override
    public String apply(String input) {
        return "classic:" + input;
    }
}
~~~

**cp-src/lesson/app/ClasspathDemo.java**:

~~~java
package lesson.app;

import lesson.spi.Transform;
import java.util.ServiceLoader;

public class ClasspathDemo {
    public static void main(String[] args) {
        for (Transform service : ServiceLoader.load(
                Transform.class)) {
            System.out.println("result = "
                    + service.apply("abc"));
        }
    }
}
~~~

**cp-out/META-INF/services/lesson.spi.Transform** is a UTF-8 text file:

~~~text
lesson.impl.ClassicTransform
~~~

### 6.2 Compiling and running

Start from the **classpath-project** directory. First, create the source tree and service file as described. Make sure the provider configuration file is **inside cp-out/META-INF/services**, not only in cp-src.

~~~bash
javac -d cp-out   cp-src/lesson/spi/Transform.java   cp-src/lesson/impl/ClassicTransform.java   cp-src/lesson/app/ClasspathDemo.java
java -cp cp-out lesson.app.ClasspathDemo
~~~

A multi-line javac command uses a **backslash** continuation character for Linux/macOS shells. If using Windows PowerShell, enter it on a single line:

~~~powershell
javac -d cp-out cp-src/lesson/spi/Transform.java cp-src/lesson/impl/ClassicTransform.java cp-src/lesson/app/ClasspathDemo.java
java -cp cp-out lesson.app.ClasspathDemo
~~~

Actual stdout verified on JDK 21:

~~~text
classic constructor invoked
result = classic:abc
~~~

ServiceLoader reads the text provider-configuration file, finds **lesson.impl.ClassicTransform**, uses the appropriate class loader to locate the class, checks that it is assignable to the service, and then invokes the **public no-args constructor**.

There is no module-info.java, no provides directive is used, and no provider method is used. When packaging a JAR, you must preserve the exact path **META-INF/services/lesson.spi.Transform** inside the archive; if this entry is missing, ServiceLoader may fail to discover the provider even though the class file still exists.

### 6.3 Provider-configuration file syntax

According to the Javadoc, the provider configuration is **UTF-8 text**. Each line is the **fully qualified binary name** of a provider, optionally with whitespace and comments starting with **#**:

~~~text
# Providers of lesson.spi.Transform
lesson.impl.ClassicTransform
# lesson.impl.AnotherTransform
~~~

Blank lines and comments are ignored. Duplicate provider names within a file or across multiple files are deduplicated by ServiceLoader according to the API rules. If there are multiple JARs, the loader may use **ClassLoader.getResources** to find multiple files sharing the same META-INF/services/... path.

**This file is not Java source and does not contain a provides lesson.spi.Transform with ... line**. That line belongs in the module-info.java of an explicit named module.

## 7. Intentional failure scenario: classpath does not use a provider method

Suppose there is a class:

~~~java
package lesson.impl;

import lesson.spi.Transform;

public final class FactoryOnly {
    private FactoryOnly() {
    }

    public static Transform provider() {
        return new ClassicTransform();
    }
}
~~~

This is a valid Java source class if ClassicTransform/Transform already exist, but FactoryOnly **does not implement Transform**. When the provider-configuration file is changed to:

~~~text
lesson.impl.FactoryOnly
~~~

ServiceLoader follows the **classpath rule**, requiring FactoryOnly to be assignable to lesson.spi.Transform and to have a public no-args constructor. Because FactoryOnly does not satisfy this, the loader fails **even though it has public static provider()**.

With the same ClasspathDemo and the modified provider-configuration file above, JDK 21 reports an error starting with:

~~~text
Exception in thread "main" java.util.ServiceConfigurationError: lesson.spi.Transform: lesson.impl.FactoryOnly not a subtype
~~~

The stack trace and line numbers may vary by JDK. The line above was observed when running the actual example on JDK 21.

**This is the most significant difference between explicit modules and the classpath:** the classpath ServiceLoader does not see a provider() method and automatically apply the explicit module's provider factory rules.

### 7.1 How to fix the classpath scenario

There are two main approaches:

- **Stay on the classpath:** register a **public class that implements Transform and has a public no-argument constructor**, such as ClassicTransform.
- **Switch to an explicit named module:** write a **module-info.java** with provides ... with FactoryOnly and provide a valid provider() according to the module rules.

Simply adding the **static** keyword or renaming the META-INF/services file does not switch to a factory provider. The registration model is the deciding factor.

## 8. Automatic module: close to a named module, but with constructor rules

An **automatic module** is a JAR without an explicit module descriptor that is placed on the **module path** and treated by the module system as a named automatic module according to its own rules.

Regarding ServiceLoader, the Javadoc explicitly states that **an automatic module must have a provider constructor**; provider methods **are not supported**.

| Case | Descriptor | Provider method? | Constructor requirement |
| --- | --- | --- | --- |
| Explicit module | Actual module-info.class | Yes | Not required if using a provider method. |
| Automatic module | Automatically generated from a JAR without a descriptor | **No** | Required, public no-args and assignable to the service. |
| Unnamed module/classpath | No descriptor | **No** | Required, public no-args and assignable to the service. |

A JAR with **Automatic-Module-Name** in its manifest is still an **automatic module** if it lacks an explicit module-info.class. That manifest attribute gives the module a more stable name; **it does not grant the provider method feature**.

A provider can be distributed in the classpath style first, and later migrated to an explicit module. When migrating, you must clearly specify the registration mechanism:

~~~text
Classpath / automatic module:
  META-INF/services/lesson.spi.Transform
    lesson.impl.ClassicTransform

Explicit module:
  module lesson.providers {
    requires lesson.api;
    provides lesson.api.Transform with lesson.impl.CtorTransform,
        lesson.impl.FactoryProvider;
  }
~~~

In an explicit module, you should not rely on ServiceLoader finding a provider method solely from a service file without a provides directive.

## 9. Provider constructor and provider method: detailed validity rules

### 9.1 Provider constructor

For the direct path:

- The provider class must be **public**.
- The provider class must be an instantiable concrete class and **implement/extend the service**.
- It must have a **public no-args constructor**; a private/package-private no-args constructor does not satisfy the contract.
- The constructor may perform dependency setup, but exceptions from the constructor are typically wrapped by ServiceLoader into a **ServiceConfigurationError** when invoked.
- A constructor with parameters is not automatically dependency-injected by ServiceLoader. If you need factory logic, an explicit named module can use a provider method.
- If the class is abstract or cannot be instantiated, the constructor-path configuration is invalid.

### 9.2 Provider method

For an explicit named module:

- The method name is exactly **provider**, lowercase.
- **public static**, **with no parameters**.
- The declared return type must be **assignable to the service type**.
- The method may return an object of an implementation class different from the factory holder itself.
- The method must not return **null**; ServiceLoader.Provider.get() treats that as a configuration error.
- The method may throw exceptions; ServiceLoader reports **ServiceConfigurationError**, typically preserving the appropriate cause.
- If a class file has multiple public static no-args methods named provider with different descriptors, ServiceLoader may treat this as ambiguous/an error.
- The provider class resides in the **same module** as the provides directive.
- A public no-args constructor on the factory holder is not needed when a valid provider method is present.

**Avoid confusion:** a FactoryProvider class with a static method named makeProvider or newInstance is not automatically recognized as a provider method. Only the exact name **provider()** satisfies the contract.

### 9.3 Top-level or static nested providers

The JLS requires a service provider named in a module declaration to be an appropriate public top-level or static nested class or interface. A non-static inner class is not suitable as a provider type in a provides directive. For the constructor path, instantiability via a public no-args constructor must also satisfy Java's constructor requirements.

You should not use an enum class as a provider in a provides directive; the JLS specifies this as a compile-time error. An abstract class or interface can serve as a provider holder if it has a valid provider method, but it cannot be a direct provider requiring a constructor.

## 10. ServiceLoader.Provider.type() can mislead readers

**Provider.type()** is not synonymous with "the class in the module descriptor entry" in all cases.

### 10.1 Provider constructor

For the provider class CtorTransform:

~~~text
module-info.java:
  provides Transform with CtorTransform

ServiceLoader.Provider.type():
  lesson.impl.CtorTransform
~~~

### 10.2 Provider method

For FactoryProvider:

~~~text
module-info.java:
  provides Transform with FactoryProvider

FactoryProvider declares:
  public static FactoryResult provider()

ServiceLoader.Provider.type():
  lesson.impl.FactoryResult
~~~

This is the **declared return type**, not necessarily the exact runtime class of the object if the method returns a more specific subtype. If declared as:

~~~java
public static Transform provider() {
    return new FactoryResult();
}
~~~

then **Provider.type()** can be **lesson.api.Transform**, even though the runtime object is FactoryResult.

Therefore:

- Use **Provider.type()** to inspect/filter according to the ServiceLoader contract, while understanding what type it represents.
- Do not assume **type()** returns FactoryProvider.class.
- Do not use **type().getConstructor().newInstance()** to instantiate a provider in general.
- Use **Provider.get()** if you want the proper instantiation mechanism supported by ServiceLoader.

### 10.3 Annotation filtering needs to account for the return type

A system that places an annotation on the provider factory holder will not necessarily see that annotation via Provider.type() if the factory method returns a different type. If a framework uses **stream().filter(p -> p.type().isAnnotationPresent(...))**, place metadata/annotations on the **declared return type** or choose an intentional lookup strategy.

This is important in plugin systems with multiple implementations that need to be filtered by provider capabilities.

## 11. Lazy discovery, instantiation, and caching

### 11.1 load() does not mean creating every instance immediately

~~~java
ServiceLoader<Transform> loader =
        ServiceLoader.load(Transform.class);
~~~

This only creates the ServiceLoader. Provider discovery/instantiation occurs primarily **lazily** when the iterator or stream is actually processed.

With the iterator:

~~~java
for (Transform transform : loader) {
    System.out.println(transform.apply("x"));
}
~~~

Provider instances are created during iteration, and ServiceLoader maintains a cache of the loaded providers.

With the stream:

~~~java
loader.stream()
        .filter(p -> p.type().getName().contains("Factory"))
        .map(ServiceLoader.Provider::get)
        .forEach(p -> System.out.println(p.apply("x")));
~~~

Filtering by **type()** can happen before **get()**. You should not assume that merely creating the Stream causes the factory method/constructor to run; however, when processing the stream, class loading and provider discovery may already have runtime effects before get().

### 11.2 Distinguishing the two caches

- **Iterator** caches the instantiated provider objects according to ServiceLoader rules.
- **Stream** caches the discovered provider descriptors/Provider objects; **Provider.get()** is what creates or retrieves an instance according to the method's contract. Do not assume that every call to get() always returns the same singleton.
- **reload()** clears the provider caches of that ServiceLoader instance itself. Any Iterator/Stream in use before reload must be discarded; they may throw **ConcurrentModificationException** if used after reload.
- A ServiceLoader object is not guaranteed to be thread-safe for concurrent use by multiple threads.

The provider constructor and provider() should be designed with clear instantiation semantics. Singleton, pooling, or dependency caching is an implementation responsibility, not something ServiceLoader automatically guarantees merely by using a provider method.

## 12. Provider lifecycle and practical usage

### 12.1 Constructor-path is suitable when

- The direct implementation is simple and has a public default constructor.
- No complex runtime decisions are needed before creating the object.
- It needs to run on the classpath or in automatic modules.
- You want easy packaging via META-INF/services and broad compatibility.

### 12.2 Provider method is suitable when

- An explicit named module wants to **hide the concrete implementation** behind a factory holder.
- The object needs to be created via a dependency graph, cache, singleton, or internal module configuration.
- The provider class does not want to or cannot implement the service directly.
- You want to use an internal implementation without a public constructor while still returning a service object to the consumer.
- You want to defer the decision of choosing a subtype until ServiceLoader calls provider().

**Limitation:** the provider() method does not automatically receive context/arguments from ServiceLoader; it is **no-args**. If you need to receive configuration from the caller, design the service interface to return a factory object or provide a method that accepts parameters after ServiceLoader delivers the instance, rather than assuming ServiceLoader passes arguments into provider().

### 12.3 Package encapsulation

With explicit modules, you should **not export the implementation package** if the consumer only needs the public service API. This allows the implementation to change without bloating the public module surface.

Example provider module:

~~~java
module lesson.providers {
    requires lesson.api;
    provides lesson.api.Transform with lesson.impl.FactoryProvider;
}
~~~

There is no exports lesson.impl. The consumer uses Transform without having to reference FactoryProvider directly.

## 13. ServiceLoader.load: choosing the right context loader

Notable overloads:

~~~java
ServiceLoader.load(Transform.class);
ServiceLoader.load(Transform.class, explicitLoader);
ServiceLoader.load(layer, Transform.class);
~~~

This is a snippet; the explicitLoader/layer variables are needed when running.

- **load(service)**: selects the **Thread Context ClassLoader** of the current thread according to the API contract.
- **load(service, classLoader)**: specifies the loader as the starting point for locating providers and provider configuration resources.
- **load(ModuleLayer, service)**: searches in the specified layer and parent layers according to module layer rules, useful for plugin runtimes that create layers dynamically.

Do not equate the **TCCL** with the **defining loader** of the service interface. If the host's service type has a duplicate defined by the plugin loader itself, the provider may not be assignable to the host service type. Check **serviceClass.getClassLoader()**, **provider.getClass().getClassLoader()**, and the module graph during diagnosis.

**The TCCL must be restored** if the system replaces it temporarily in a shared thread pool: a long-lived worker may retain the old plugin ClassLoader, causing memory retention after unload.

## 14. Service providers in a dynamic ModuleLayer

When a plugin runtime creates a **new ModuleLayer**, the host code can use:

~~~java
ServiceLoader<Transform> services =
        ServiceLoader.load(pluginLayer, Transform.class);
~~~

This is a snippet; it requires appropriate pluginLayer and Transform service variables, with valid providers already in the module graph.

**ServiceLoader.load(layer, service)** inspects providers in the layer and its ancestors. With one-loader/many-loaders modules, ServiceLoader also has provider-lookup semantics based on the module layer, rather than merely reading a single META-INF/services file in the current working directory.

Things to ensure:

1. The provider's module descriptor has **provides S with Provider**.
2. The module containing the service interface has the appropriate exports.
3. The consumer/module context has the **uses** permission according to the API.
4. The plugin layer has been defined and contains the provider modules.
5. The runtime service Class passed by the caller has the **same service identity** that the provider was designed to implement.
6. The provider/loader lifecycle is managed when the plugin stops; ServiceLoader caches, futures, and threads can retain old loaders.

A provider method does not change the module access/identity rules. It only changes how the object is created from the provider class after the provider is found.

## 15. Common errors and messages to understand

### 15.1 ServiceConfigurationError: not a subtype

**Typical causes:**

- On the classpath/automatic module, the provider class in META-INF/services does not implement the service.
- The runtime has two copies of the service class with the same binary name but different defining loaders.
- Classpath registration points to a factory holder that only has static provider() instead of a direct implementation.

**Action:** check the deployment mode, service interface identity, META-INF/services file, and public provider constructor. Do not use a provider method on the classpath to bypass the subtype requirement.

### 15.2 ServiceConfigurationError: Unable to get public no-arg constructor

The provider class uses the constructor-path, yet does not have a **public** no-argument constructor. You may have declared a constructor taking dependencies:

~~~java
public DirectProvider(Config config) {
}
~~~

ServiceLoader does not automatically inject Config. In an explicit named module, consider a provider method; whereas on the classpath/automatic module, you must provide a public no-args constructor or change the provider model into a service factory with a no-args constructor.

### 15.3 Provider method returns null

In an explicit named module:

~~~java
public static Transform provider() {
    return null;
}
~~~

This violates the contract when ServiceLoader invokes the method. ServiceLoader.Provider.get() reports **ServiceConfigurationError**. Always return an object that is assignable to the service and already in a valid state.

### 15.4 Provider method throws an exception

~~~java
public static Transform provider() {
    throw new IllegalStateException("Configuration missing");
}
~~~

ServiceLoader reports ServiceConfigurationError, typically preserving the underlying reason in the cause. Investigate the internal factory error rather than simply catching and silently ignoring it in all cases.

### 15.5 Missing uses in an explicit consumer module

A module whose consumer code calls ServiceLoader without declaring **uses service.type** may encounter ServiceConfigurationError. Do not assume that merely having **requires service-api-module** is sufficient for the service-use rule in an explicit named module.

### 15.6 Provider module is on the module path but not resolved

Having a provider module JAR does not mean ServiceLoader will always find it. The module graph at startup may not yet contain the provider module. Check **--add-modules**, root modules, service binding, or the appropriate ModuleLayer definition.

### 15.7 Provider not found due to missing META-INF/services

In a classpath deployment missing the **META-INF/services/fully.qualified.Service** file, ServiceLoader may return zero providers even though the implementation class compiles normally. Check the output/JAR entries, not only the source tree.

### 15.8 Multiple provider implementations are not discovered in the expected order

Different modules do not have a guaranteed discovery order matching what you see on the filesystem. Provider entries within **a single provides directive** are ordered according to the module descriptor, whereas modules in a layer may not have a deterministic order.

If you need to select a provider based on priority, define explicit metadata/config/ordering and sort them, as in the named module example.

### 15.9 Confusing ServiceLoader.Provider.type with the provider class

With a provider method, type() is the **declared return type** of provider(), so it differs from the factory holder. Do not use this to access the factory holder's constructor or to infer annotations placed on the factory holder.

### 15.10 Concurrent use or reload while iterating

ServiceLoader instances are not thread-safe. Calling reload while traversing an existing iterator/stream may throw ConcurrentModificationException. Design caching and synchronization at the appropriate application/framework level instead of using an unlocked shared ServiceLoader object across multiple threads.

## 16. Decision table when designing providers

| Question | Approach |
| --- | --- |
| Is there an explicit module-info.java with provides? | Can use either a provider constructor **or** a provider method. |
| Does the provider class directly implement the service and have a public no-args constructor? | The constructor-path is simple and portable. |
| Does a factory class not implement the service yet return a service object? | Use public static provider() in an **explicit named module**. |
| Is the provider in a JAR on the classpath? | META-INF/services + public subtype + public no-args constructor. |
| Is the provider an automatic module on the module path? | Constructor-path; provider methods are not supported. |
| Want to hide the implementation from consumer modules? | Encapsulate the implementation package and export only the service API. |
| Want to inspect the type before creating an instance? | ServiceLoader.stream() and Provider.type(), keeping the factory return type in mind. |
| Want to create the instance properly without caring about the mechanism? | Use Provider.get() or iterator(). |
| Want to find providers in a dynamic ModuleLayer? | ServiceLoader.load(layer, service). |
| Want to hot reload providers? | ServiceLoader.reload() and manage loader/layer creation/lifecycles appropriately; reload does not replace already-defined classes by itself. |
| Want a singleton/provider cache? | Design it explicitly in the implementation; do not rely on calling get() to always return the same object. |

## 17. Security, reliability, and compatibility

### 17.1 Do not treat SPI discovery as a trust mechanism

ServiceLoader can load classes and run constructors/provider methods from modules/JARs at runtime. That is **executable code**, which can cause side effects, network I/O, or data access. Only load providers from sources that conform to your application's trust policy; a ClassLoader/module boundary alone is not a complete security sandbox.

### 17.2 Separate configuration errors from application errors

If no provider is found, ServiceLoader may yield zero items. If a provider is declared but **invalid**, ServiceLoader typically reports **ServiceConfigurationError** during iteration, stream processing, or get(). Do not catch all Throwables to silently ignore them; a deployment configuration error is a signal that needs fixing.

### 17.3 Design provider() not to perform overly surprising work

A provider method can be complex, but initialization costs, thread creation, opening connections, and cleanup should be clearly documented. A factory method that performs expensive operations on the first lookup can increase latency; side effects or exceptions will surface when the consumer uses ServiceLoader.

### 17.4 Class loader leaks during redeployment

If the application retains a ServiceLoader, Provider descriptors, provider instances, or the plugin's TCCL after shutdown, the old defining loader may remain reachable. **reload()** only clears the cache of that ServiceLoader instance; it does not automatically shut down plugin executors or immediately reclaim the module layer. The plugin manager must coordinate its lifecycle separately.

## 18. Self-check exercises

**Question 1.** A provider class in an explicit named module does not implement the service and has a private constructor, but has a public static no-args provider() returning the service. Is this valid?

**Answer:** Yes, if the provider method and module descriptor are valid. ServiceLoader uses provider() to obtain the instance.

**Question 2.** Classpath META-INF/services lists the class from Question 1. Does ServiceLoader automatically invoke static provider()?

**Answer:** No. A classpath provider must be assignable to the service and have a public no-args constructor.

**Question 3.** Does an automatic module on the module path support provider methods?

**Answer:** No. According to the Javadoc, an automatic module must use a provider constructor.

**Question 4.** In an explicit named module, a provider class has both a public no-args constructor and a valid public static provider(). Which path does ServiceLoader use?

**Answer:** The provider method, according to the rule when a provider method is declared.

**Question 5.** ServiceLoader.Provider.type() for FactoryProvider.provider() returning FactoryResult: is type() FactoryProvider.class or FactoryResult.class?

**Answer:** FactoryResult.class, because it is the declared return type of the provider method.

**Question 6.** If provider() declares the return type Transform but actually returns FactoryResult, does type() automatically change to FactoryResult.class?

**Answer:** No. type() reflects the **declared return type**, so it is Transform.class.

**Question 7.** Without module-info.java, can a JAR with Automatic-Module-Name use a factory-only provider()?

**Answer:** No. Automatic-Module-Name does not turn an automatic module into an explicit module with provider-method support.

**Question 8.** Why should an explicit consumer module have uses?

**Answer:** To declare the service dependency to the module system and satisfy ServiceLoader's requirement when called from an explicit module.

**Question 9.** What happens if a provider method returns null?

**Answer:** ServiceLoader reports ServiceConfigurationError when attempting to create the service object.

**Question 10.** Does ServiceLoader.load(Transform.class) necessarily create all instances immediately?

**Answer:** No. Discovery/instantiation is primarily lazy via iterator/stream/get().

**Question 11.** If you want the same service type to be shared between host and plugin, what is important about the ClassLoader?

**Answer:** The host and provider must use the same runtime Class identity of the service, not merely the same string name.

**Question 12.** Can a provider method receive a Config parameter automatically injected by ServiceLoader?

**Answer:** No. By contract, a provider method is public static no-args. Configuration must be handled through another design.

## 19. Summary

~~~text
                     ServiceLoader<S>
                            |
              +-------------+-------------+
              |                           |
       Explicit named module     Classpath / automatic module
              |                           |
       module-info.java          META-INF/services / metadata
       provides S with P                  |
              |                           |
    Has public static provider()?         |
           |         |                    |
          Yes        No                   |
           |         |                    |
           v         v                    v
     call P.provider()   create P via public no-args constructor
           |                       |
           v                       v
     S-compatible object     P must implement/extend S
              |                           |
              +-------------+-------------+
                            |
                            v
                   consumer receives S
~~~

**Five points to remember:**

1. **Provider constructor** requires a public no-args constructor and the provider class to be assignable to the service.
2. **Provider method** is only supported for an **explicit named module** via the provides directive; the factory holder does not necessarily have to implement the service.
3. **Classpath and automatic modules** use the constructor-path, not merely relying on static provider().
4. **ServiceLoader.Provider.type()** on the method-path is the **declared return type** of provider(), while **get()** obtains the instance.
5. Discovery/instantiation is **lazy**, uses caching, reports errors as **ServiceConfigurationError**, and must still respect class-loader identity, module boundaries, and lifecycle.

### Official documentation

- Java SE 17 **ServiceLoader API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 **ServiceLoader.Provider API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java SE 17 **JLS §7.7.4 Service Provision**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4
- Java SE 17 **ModuleLayer API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Dev.java **Decoupling Modules with Services**: https://dev.java/learn/organizing/modules/services/
